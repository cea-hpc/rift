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
CLI for the repos-conf standalone executable.
"""

import argparse
import logging
import urllib.parse
from collections import namedtuple

from rift import RiftError
from rift.config import _DEFAULT_VARIANT, Config
from rift.repository.rpm import ConsumableRepository, project_repositories

RepositoryHost = namedtuple("RepositoryHost", ["scheme", "hostname", "port"])


def make_parser():
    """Create command line parser for repos-conf."""
    parser = argparse.ArgumentParser(
        prog="repos-conf",
        description="Generate a dnf/yum repository file from a project configuration",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase output verbosity (twice for debug)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="write the repository file to this path (default: stdout)",
    )
    parser.add_argument(
        "--arch",
        help=(
            "architecture used to resolve repositories "
            "(default: host architecture when the project supports it)"
        ),
    )
    parser.add_argument(
        "-H",
        "--host",
        help=(
            "replacement host for declared repository URLs, "
            "as host, host:port, scheme://host, or scheme://host:port"
        ),
    )
    parser.add_argument(
        "--token-proxy",
        help="base URL of a running repos-token-proxy, such as http://127.0.0.1:8765",
    )
    parser.add_argument(
        "config",
        metavar="CONFIG",
        help="path to project configuration file",
    )
    return parser


def parse_host(value):
    """
    Parse a --host value into a RepositoryHost.

    The value is [scheme://]host[:port]. scheme is None when the value does not set one.
    port is None when the value does not set one.
    """
    host_form = "expected host, host:port, scheme://host, or scheme://host:port"
    if "://" in value:
        parts = urllib.parse.urlsplit(value)
    else:
        if any(char in value for char in "/?#@"):
            raise RiftError(f"Invalid host '{value}': expected no path")
        parts = urllib.parse.urlsplit(f"//{value}")
    if parts.path not in ("",):
        raise RiftError(f"Invalid host '{value}': expected no path")
    if parts.query or parts.fragment or parts.username or parts.password:
        raise RiftError(f"Invalid host '{value}': {host_form}")
    if not parts.hostname or ("://" in value and not parts.scheme):
        raise RiftError(f"Invalid host '{value}': {host_form}")
    try:
        port = parts.port
    except ValueError as err:
        raise RiftError(f"Invalid host '{value}': {host_form}") from err
    scheme = parts.scheme if "://" in value else None
    return RepositoryHost(scheme, parts.hostname, port)


def parse_token_proxy(value):
    """
    Parse a --token-proxy value.

    The value must be an http URL with a host and no path other than /.
    """
    parts = urllib.parse.urlsplit(value)
    if parts.scheme != "http" or not parts.hostname:
        raise RiftError(
            f"Invalid token proxy URL '{value}': expected an http URL with a host"
        )
    if parts.path not in ("", "/"):
        raise RiftError(
            f"Invalid token proxy URL '{value}': expected no path other than /"
        )
    if parts.query or parts.fragment or parts.username or parts.password:
        raise RiftError(
            f"Invalid token proxy URL '{value}': expected no user info, query, "
            "or fragment"
        )
    return parts.netloc


def _replace_repository_host(url, host):
    """
    Replace the host of a repository URL.

    file:// URLs and URLs with no host are returned unchanged. The declared port is
    dropped. A scheme on host overrides the declared scheme; otherwise the declared
    scheme is kept. The path and query are kept.
    """
    if url.startswith("/") or url.startswith(f"{ConsumableRepository.FILE_SCHEME}"):
        return url
    parts = urllib.parse.urlsplit(url)
    if not parts.hostname:
        return url
    if host.scheme is None:
        scheme = parts.scheme
    else:
        scheme = host.scheme
    # Bracket IPv6 hosts so the port separator stays unambiguous.
    if ":" in host.hostname:
        hostname = f"[{host.hostname}]"
    else:
        hostname = host.hostname
    if host.port is None:
        netloc = hostname
    else:
        netloc = f"{hostname}:{host.port}"
    return urllib.parse.urlunsplit(
        (scheme, netloc, parts.path, parts.query, parts.fragment)
    )


def _dnf_repo_lines(repo, arch, priority, host, token_proxy):
    """Return the lines of one dnf/yum repository stanza."""
    proxy = None
    # When repository is authenticated and token proxy is provided, the repository
    # uses this proxy.
    if token_proxy is not None and repo.authenticated():
        baseurl = f"http://{token_proxy}/{urllib.parse.quote(repo.name)}/"
    else:
        # Replaces the concrete architecture in declared URLs with $basearch.
        baseurl = repo.generic_url(arch)
        # If host is provided, use it in the repository URL.
        if host is not None:
            baseurl = _replace_repository_host(baseurl, host)
        if repo.proxy and not repo.authenticated():
            proxy = repo.proxy
    enabled = 1 if _DEFAULT_VARIANT in repo.variants else 0
    lines = [
        f"[{repo.name}]",
        f"name={repo.name}",
        f"baseurl={baseurl}",
        "gpgcheck=0",
        f"priority={priority}",
        f"enabled={enabled}",
    ]
    if repo.module_hotfixes:
        lines.append(f"module_hotfixes={repo.module_hotfixes}")
    if repo.excludepkgs:
        lines.append(f"excludepkgs={repo.excludepkgs}")
    if proxy:
        lines.append(f"proxy={proxy}")
    return lines


def render_dnf_repo(repos, arch, host=None, token_proxy=None):
    """Render a dnf/yum repository file for the given repositories."""
    stanzas = []
    prio = 1000
    for repo in repos:
        prio = repo.priority or (prio - 1)
        stanzas.append("\n".join(_dnf_repo_lines(repo, arch, prio, host, token_proxy)))
    if not stanzas:
        return ""
    return "\n\n".join(stanzas) + "\n"


def main(args=None):
    """Main code of 'repos-conf'."""
    args = make_parser().parse_args(args)

    logging.basicConfig(
        format="%(levelname)-8s %(message)s", level=logging.WARNING - args.verbose * 10
    )

    try:
        config = Config()
        config.ALLOW_MISSING = False
        config.load(args.config)
        # Use the architecture specified on the command line, or the chroot
        # architecture for the project (ie. the host architecture if supported or the
        # first supported architecture).
        arch = args.arch or config.chroot_arch()
        # Get the consumable repositories declared in project configuration for the
        # architecture.
        repos = project_repositories(config, arch)
        # Parse the host replacement specified on the command line, if any.
        host = parse_host(args.host) if args.host else None
        # Parse the token proxy base URL specified on the command line, if any.
        token_proxy = parse_token_proxy(args.token_proxy) if args.token_proxy else None
        # Render the repository file.
        text = render_dnf_repo(repos, arch, host=host, token_proxy=token_proxy)
        # Write the repository file to the output file, if specified, or to stdout.
        if args.output:
            with open(args.output, "w", encoding="utf-8") as repo_file:
                repo_file.write(text)
        else:
            print(text, end="")
    except (RiftError, IOError, OSError) as exp:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            raise
        logging.error(str(exp))
        return 1

    return 0
