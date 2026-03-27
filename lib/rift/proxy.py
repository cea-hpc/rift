#
# Copyright (C) 2026 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#

"""
HTTP repository proxy for idp_token protected repositories.
"""

import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from rift import RiftError
from rift.auth import Auth

# Hop-by-hop headers apply only to a single HTTP connection hop
# (client<->proxy or proxy<->upstream), not to the full end-to-end message.
# Forwarding them as-is may break framing/connection semantics (for example
# Connection and Transfer-Encoding), so this proxy strips them on both request
# forwarding and response forwarding.
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """
    Threading HTTP server for repository proxy.
    """
    # Handle each request in its own daemon thread so long-running RPM downloads
    # do not block other clients and do not prevent process exit.
    daemon_threads = True
    # Allow fast restart on the same host/port without waiting for TIME_WAIT.
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, runtime):
        super().__init__(server_address, RequestHandlerClass)
        self.runtime = runtime


class _TokenAuthRepositoryProxyHandler(BaseHTTPRequestHandler):
    """
    HTTP repository proxy request handler for bearer token protected repositories.
    """
    # Advertise a proxy-specific Server header for troubleshooting.
    server_version = "RiftAuthRepoProxy/1.0"
    # Use HTTP/1.1 responses to keep transfer/framing behavior aligned with
    # modern upstream repository clients.
    protocol_version = "HTTP/1.1"

    def _log_proxy_request(self, upstream_url, status_code):
        """Log proxy requests at DEBUG level."""
        logging.debug(
            "proxy request %s %s -> %s [%s]",
            self.command,
            self.path,
            upstream_url,
            status_code,
        )

    def send_error(self, code, message=None, explain=None):
        """Override parent class send_error() to log proxy errors at ERROR level."""
        logging.error(
            "proxy error %s %s [%s] %s",
            self.command,
            self.path,
            code,
            message if message is not None else "-",
        )
        super().send_error(code, message, explain)

    def _handle(self):
        # Make sure this handler is running on custom Rift threading HTTP server
        # with AuthenticatedRepositoryProxyRuntime instance.
        assert isinstance(self.server, _ThreadingHTTPServer)

        repo_key, relpath, query = self._parse_repo_route()
        if repo_key is None:
            return

        repo = self.server.runtime.repositories.get(repo_key)
        if repo is None:
            self.send_error(404, "Unknown repository key")
            return

        upstream_url = self._build_upstream_url(repo.url, relpath, query)
        headers = self._build_forward_headers(self.server.runtime.token)

        request = urllib.request.Request(
            upstream_url,
            headers=headers,
            method=self.command,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.server.runtime.timeout) as response:
                self._log_proxy_request(upstream_url, response.getcode())
                self._send_upstream_response(response)
        except urllib.error.HTTPError as err:
            self._log_proxy_request(upstream_url, err.code)
            self._send_error_response(err)
        except (urllib.error.URLError, OSError) as err:
            logging.error("Repository proxy request failed: %s", err)
            self.send_error(502, "Bad gateway")

    def _parse_repo_route(self):
        """
        Extract upstream repository route from request path. Return (repo_key,
        relpath, query) tuple where:
        - repo_key is the upstream repository key (ie. the first path component
          of the request path)
        - relpath is the relative path to the upstream repository base URL (ie.
          the remaining path components of the request path)
        - query is the query string
        """
        split = urllib.parse.urlsplit(self.path)
        route = split.path.lstrip("/")
        if not route:
            self.send_error(400, "Missing repository key in URL")
            return None, None, None

        route_parts = route.split("/", 1)
        repo_key = urllib.parse.unquote(route_parts[0]).strip()
        if not repo_key:
            self.send_error(400, "Invalid repository key")
            return None, None, None

        if len(route_parts) == 2:
            relpath = route_parts[1]
        else:
            relpath = ""

        return repo_key, relpath, split.query

    @staticmethod
    def _build_upstream_url(base_url, relpath, query):
        base = base_url
        if not base.endswith("/"):
            base += "/"
        upstream = urllib.parse.urljoin(base, relpath)
        if query:
            upstream = f"{upstream}?{query}"
        return upstream

    def _build_forward_headers(self, token):
        headers = {}
        for key in self.headers.keys():
            key_lower = key.lower()
            if key_lower in _HOP_BY_HOP_HEADERS or key_lower == "host":
                continue
            headers[key] = self.headers.get(key)
        headers["Authorization"] = f"Bearer {token}"
        return headers

    def _send_upstream_response(self, response):
        """
        Relay a successful upstream urllib response to the client.

        Sends the HTTP status line, forwards upstream headers except hop-by-hop
        headers, then ends the header block. For GET, streams the body in chunks;
        for HEAD, sends headers only (no body).
        """
        self.send_response(response.getcode())
        for key, value in response.getheaders():
            key_lower = key.lower()
            if key_lower in _HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.end_headers()

        if self.command == "HEAD":
            return

        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            self.wfile.write(chunk)

    def _send_error_response(self, error):
        """
        Relay an urllib HTTPError response to the client.

        Sends the error status code, forwards the error response headers except
        hop-by-hop headers, then ends the header block. For GET, forwards the
        error body when present; for HEAD, omits the body.
        """
        self.send_response(error.code)
        for key, value in error.headers.items():
            key_lower = key.lower()
            if key_lower in _HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            body = error.read()
            if body:
                self.wfile.write(body)

    def do_GET(self):  # pylint: disable=invalid-name
        """Handle GET requests."""
        self._handle()

    def do_HEAD(self):  # pylint: disable=invalid-name
        """Handle HEAD requests."""
        self._handle()

    def log_message(self, format, *args):
        """
        Override parent class log_message() to suppress default http.server
        per-request stderr/INFO logging.
        """


class AuthenticatedRepositoryProxyRuntime:
    """
    Runtime helper around a local HTTP proxy for authenticated repos.
    """

    def __init__(self, config, repositories, timeout=60):
        self._config = config
        self._timeout = timeout
        self.repositories = {
            repo.name: repo
            for repo in repositories
            if repo.authenticated()
        }
        self.token = None
        self.server = None
        self._thread = None

    @property
    def timeout(self):
        """Get repository proxy timeout."""
        return self._timeout

    @property
    def active(self):
        """Check if repository proxy is active."""
        return self.server is not None

    @property
    def required(self):
        """Check if repository proxy is required."""
        return len(self.repositories) > 0

    def start(self):
        """Start repository proxy."""
        if self.server is not None:
            return
        if not self.required:
            logging.debug("No repositories need proxy, skipping proxy startup")
            return

        # Get IDP token non-interactively.
        self.token = Auth(self._config).get_idp_token_noninteractive()

        # Start HTTP server in a separate thread.
        self.server = _ThreadingHTTPServer(
            ("127.0.0.1", 0), _TokenAuthRepositoryProxyHandler, self
        )
        # Make thread daemon to avoid hanging when the main thread finishes (e.g.
        # after mock build or VM test). Daemon threads are stopped on interpreter
        # exit.
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        logging.info("Started repository proxy on port %s", self.port)

    def stop(self):
        """Stop repository proxy."""
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.server = None
        self._thread = None
        self.token = None
        logging.debug("Stopped repository proxy")

    @property
    def port(self):
        """Get repository proxy port."""
        if self.server is None:
            raise RiftError("Repository proxy is not started")
        return self.server.server_port

    def repo_url(self, repo, host):
        """Get repository URL for proxy."""
        if not self.required or not repo.authenticated():
            return repo.url
        if self.server is None:
            raise RiftError("Repository proxy is not started")
        if repo.name not in self.repositories:
            raise RiftError(
                f"Missing repository route for key '{repo.name}' in repository proxy"
            )
        return f"http://{host}:{self.port}/{urllib.parse.quote(repo.name)}/"
