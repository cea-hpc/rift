#
# Copyright (C) 2026 CEA
#

from unittest.mock import Mock, patch

from rift import RiftError
from rift.proxy import (
    AuthenticatedRepositoryProxyRuntime,
    _TokenAuthRepositoryProxyHandler,
)
from .TestUtils import RiftTestCase


class _DummyRepo:
    def __init__(self, name, url, authenticated):
        self.name = name
        self.url = url
        self._authenticated = authenticated

    def authenticated(self):
        return self._authenticated


class TokenAuthRepositoryProxyHandlerTest(RiftTestCase):
    def test_build_upstream_url(self):
        url = _TokenAuthRepositoryProxyHandler._build_upstream_url(
            "https://example.org/repo",
            "x86_64/repodata/repomd.xml",
            "a=1&b=2",
        )
        self.assertEqual(
            url,
            "https://example.org/repo/x86_64/repodata/repomd.xml?a=1&b=2",
        )

    def test_build_forward_headers(self):
        handler = _TokenAuthRepositoryProxyHandler.__new__(
            _TokenAuthRepositoryProxyHandler
        )
        handler.headers = {
            "Host": "127.0.0.1:8080",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
            "Accept": "application/json",
            "User-Agent": "curl/8.0",
        }

        headers = handler._build_forward_headers("token-123")
        self.assertEqual(
            headers,
            {
                "Accept": "application/json",
                "User-Agent": "curl/8.0",
                "Authorization": "Bearer token-123",
            },
        )


class AuthenticatedRepositoryProxyRuntimeTest(RiftTestCase):
    @patch("rift.proxy.Auth")
    def test_init(self, mock_auth):
        repos = [
            _DummyRepo("public", "https://repo/public", False),
            _DummyRepo("private", "https://repo/private", True),
        ]

        runtime = AuthenticatedRepositoryProxyRuntime({"idp_app_token": "x"}, repos)

        self.assertTrue(runtime.required)
        self.assertEqual(list(runtime.repositories.keys()), ["private"])
        mock_auth.assert_not_called()

    @patch("rift.proxy.threading.Thread")
    @patch("rift.proxy._ThreadingHTTPServer")
    @patch("rift.proxy.Auth")
    def test_runtime_start(
        self,
        mock_auth_cls,
        mock_server_cls,
        mock_thread_cls,
    ):
        mock_server = Mock()
        mock_server.server_port = 51234
        mock_server_cls.return_value = mock_server

        mock_thread = Mock()
        mock_thread_cls.return_value = mock_thread

        mock_auth = Mock()
        mock_auth.get_idp_token_noninteractive.return_value = "idp-token"
        mock_auth_cls.return_value = mock_auth

        repos = [_DummyRepo("private repo", "https://repo/private", True)]
        runtime = AuthenticatedRepositoryProxyRuntime({"idp_app_token": "x"}, repos)

        runtime.start()

        mock_auth.get_idp_token_noninteractive.assert_called_once()
        mock_server_cls.assert_called_once_with(
            ("127.0.0.1", 0),
            _TokenAuthRepositoryProxyHandler,
            runtime,
        )
        mock_thread_cls.assert_called_once_with(
            target=mock_server.serve_forever,
            daemon=True,
        )
        mock_thread.start.assert_called_once()
        self.assertTrue(runtime.active)
        self.assertEqual(runtime.token, "idp-token")
        self.assertEqual(runtime.port, 51234)

    @patch("rift.proxy.Auth")
    def test_start_skips_when_no_authenticated_repos(self, mock_auth):
        repos = [_DummyRepo("public", "https://repo/public", False)]
        runtime = AuthenticatedRepositoryProxyRuntime({"idp_app_token": "x"}, repos)

        runtime.start()

        self.assertFalse(runtime.active)
        self.assertIsNone(runtime.token)
        mock_auth.return_value.get_idp_token_noninteractive.assert_not_called()
        mock_auth.assert_not_called()

    @patch("rift.proxy.Auth")
    def test_stop(self, mock_auth):
        runtime = AuthenticatedRepositoryProxyRuntime(
            {"idp_app_token": "x"},
            [_DummyRepo("private", "https://repo/private", True)],
        )
        server = Mock()
        runtime.server = server
        runtime._thread = Mock()
        runtime.token = "idp-token"

        runtime.stop()

        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        self.assertIsNone(runtime.server)
        self.assertIsNone(runtime._thread)
        self.assertIsNone(runtime.token)

    @patch("rift.proxy.Auth")
    def test_port_raises_when_not_started(self, mock_auth):
        runtime = AuthenticatedRepositoryProxyRuntime(
            {"idp_app_token": "x"},
            [_DummyRepo("private", "https://repo/private", True)],
        )
        with self.assertRaisesRegex(RiftError, "^Repository proxy is not started$"):
            _ = runtime.port

    @patch("rift.proxy.Auth")
    def test_repo_url_returns_original_when_not_authenticated(self, mock_auth):
        repo = _DummyRepo("public", "https://repo/public", False)
        runtime = AuthenticatedRepositoryProxyRuntime({"idp_app_token": "x"}, [repo])

        self.assertEqual(runtime.repo_url(repo, "127.0.0.1"), repo.url)

    @patch("rift.proxy.Auth")
    def test_repo_url_raises_when_not_started(self, mock_auth):
        repo = _DummyRepo("private", "https://repo/private", True)
        runtime = AuthenticatedRepositoryProxyRuntime({"idp_app_token": "x"}, [repo])

        with self.assertRaisesRegex(RiftError, "^Repository proxy is not started$"):
            runtime.repo_url(repo, "127.0.0.1")

    @patch("rift.proxy.Auth")
    def test_repo_url_encoded_repo_name(self, mock_auth):
        repo = _DummyRepo("private repo", "https://repo/private", True)
        runtime = AuthenticatedRepositoryProxyRuntime({"idp_app_token": "x"}, [repo])
        runtime.server = Mock()
        runtime.server.server_port = 41234

        url = runtime.repo_url(repo, "10.0.2.2")

        self.assertEqual(url, "http://10.0.2.2:41234/private%20repo/")

    @patch("rift.proxy.Auth")
    def test_repo_url_missing_repo_key(self, mock_auth):
        runtime = AuthenticatedRepositoryProxyRuntime(
            {"idp_app_token": "x"},
            [_DummyRepo("private", "https://repo/private", True)],
        )
        runtime.server = Mock()
        runtime.server.server_port = 41234
        not_registered = _DummyRepo("other", "https://repo/other", True)

        with self.assertRaisesRegex(
            RiftError,
            "^Missing repository route for key 'other' in repository proxy$",
        ):
            runtime.repo_url(not_registered, "127.0.0.1")
