#
# Copyright (C) 2026 CEA
#

from unittest.mock import Mock, patch

from rift import RiftError
from rift.apps.proxy import main, make_parser

from ..test_utils import RiftTestCase


class _DummyRepo:
    def __init__(self, name, url, authenticated):
        self.name = name
        self.url = url
        self._authenticated = authenticated

    def authenticated(self):
        return self._authenticated


class ReposTokenProxyCLITest(RiftTestCase):
    def test_make_parser_defaults(self):
        opts = make_parser().parse_args(["/path/to/project.conf"])
        self.assertEqual(opts.config, "/path/to/project.conf")
        self.assertEqual(opts.host, "127.0.0.1")
        self.assertEqual(opts.port, 0)
        self.assertEqual(opts.verbose, 0)

    def test_make_parser_host_port_verbose(self):
        opts = make_parser().parse_args(
            ["-vv", "--host", "0.0.0.0", "--port", "8080", "project.conf"]
        )
        self.assertEqual(opts.config, "project.conf")
        self.assertEqual(opts.host, "0.0.0.0")
        self.assertEqual(opts.port, 8080)
        self.assertEqual(opts.verbose, 2)

    @patch("rift.apps.proxy.signal.pause", side_effect=KeyboardInterrupt)
    @patch("rift.apps.proxy.signal.signal")
    @patch("rift.apps.proxy.AuthenticatedRepositoryProxyRuntime")
    @patch("rift.apps.proxy.ProjectArchRepositories")
    @patch("rift.apps.proxy.Config")
    def test_main_starts_and_stops_on_interrupt(
        self,
        mock_config_cls,
        mock_repos_cls,
        mock_runtime_cls,
        _mock_signal,
        _mock_pause,
    ):
        mock_config = Mock()
        mock_config_cls.return_value = mock_config

        repo = _DummyRepo("private", "https://repo/private", True)
        mock_repos_cls.return_value.for_format.return_value.all = [repo]

        mock_runtime = Mock()
        mock_runtime.required = True
        mock_runtime.repositories = {repo.name: repo}
        mock_runtime.repo_url.return_value = "http://0.0.0.0:8080/private/"
        mock_runtime_cls.return_value = mock_runtime

        rc = main(["--host", "0.0.0.0", "--port", "8080", "project.conf"])

        self.assertEqual(rc, 0)
        self.assertFalse(mock_config.ALLOW_MISSING)
        mock_config.load.assert_called_once_with("project.conf")
        mock_runtime.start.assert_called_once_with(host="0.0.0.0", port=8080)
        mock_runtime.stop.assert_called_once()

    @patch("rift.apps.proxy.AuthenticatedRepositoryProxyRuntime")
    @patch("rift.apps.proxy.ProjectArchRepositories")
    @patch("rift.apps.proxy.Config")
    def test_main_errors_when_no_authenticated_repos(
        self,
        mock_config_cls,
        mock_repos_cls,
        mock_runtime_cls,
    ):
        mock_config_cls.return_value = Mock()
        mock_repos_cls.return_value.for_format.return_value.all = []
        mock_runtime = Mock()
        mock_runtime.required = False
        mock_runtime_cls.return_value = mock_runtime

        # pytest.ini sets log_level=DEBUG, so main() re-raises RiftError.
        with self.assertRaisesRegex(
            RiftError,
            "^No repositories with auth: idp_token found in configuration$",
        ):
            main(["project.conf"])

        mock_runtime.start.assert_not_called()
        mock_runtime.stop.assert_called_once()
