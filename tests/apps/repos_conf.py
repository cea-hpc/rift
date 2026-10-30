#
# Copyright (C) 2026 CEA
#

import logging
import os
import tempfile
from io import StringIO
from unittest.mock import patch

from rift import RiftError
from rift.apps.repos_conf import (
    RepositoryHost,
    main,
    make_parser,
    parse_host,
    parse_token_proxy,
    render_dnf_repo,
)
from rift.config import Config
from rift.repository.rpm import ConsumableRepository

from ..test_utils import RiftTestCase

_DECLARED = "httpss://pkgs.internal:8443/foo/bar"

_PROJECT_CONF = """\
set_annex:
  address: /tmp/rift-annex
  type: directory
vm:
  image: test.img
arch:
  - x86_64
  - aarch64
repos:
  os:
    url: https://pkgs.internal:8443/8.8/BaseOS/$arch/os
    module_hotfixes: true
    excludepkgs: kernel
    proxy: http://127.0.0.1:8080
  private:
    url: https://pkgs.internal/private/$arch
    auth: idp_token
    proxy: http://proxy:3128
  local:
    url: file:///var/repos/$arch
aarch64:
  repos:
    alt:
      url: https://pkgs.internal:8443/alt
"""


class ReposConfParseTest(RiftTestCase):
    """Tests for parse_host and parse_token_proxy."""

    def test_parse_host(self):
        self.assertEqual(
            parse_host("pkgs.external"),
            RepositoryHost(None, "pkgs.external", None),
        )
        self.assertEqual(
            parse_host("pkgs.external:9443"),
            RepositoryHost(None, "pkgs.external", 9443),
        )
        self.assertEqual(
            parse_host("http://pkgs.external"),
            RepositoryHost("http", "pkgs.external", None),
        )
        self.assertEqual(
            parse_host("http://pkgs.external:8080"),
            RepositoryHost("http", "pkgs.external", 8080),
        )
        with self.assertRaisesRegex(RiftError, "expected no path"):
            parse_host("pkgs.external/extra")
        with self.assertRaisesRegex(RiftError, "expected no path"):
            parse_host("http://pkgs.external/extra")
        with self.assertRaisesRegex(RiftError, "expected host, host:port"):
            parse_host("http://user:pass@pkgs.external")
        with self.assertRaisesRegex(RiftError, "expected host, host:port"):
            parse_host("http://pkgs.external?arch=1")
        with self.assertRaisesRegex(RiftError, "expected host, host:port"):
            parse_host("http://")
        with self.assertRaisesRegex(RiftError, "expected host, host:port"):
            parse_host("pkgs.external:abc")

    def test_parse_token_proxy(self):
        self.assertEqual(
            parse_token_proxy("http://127.0.0.1:8765"),
            "127.0.0.1:8765",
        )
        self.assertEqual(
            parse_token_proxy("http://127.0.0.1:8765/"),
            "127.0.0.1:8765",
        )
        with self.assertRaisesRegex(RiftError, "expected an http URL with a host"):
            parse_token_proxy("https://127.0.0.1:8765")
        with self.assertRaisesRegex(RiftError, "expected an http URL with a host"):
            parse_token_proxy("http://")
        with self.assertRaisesRegex(RiftError, "expected no path other than /"):
            parse_token_proxy("http://127.0.0.1:8765/extra")
        with self.assertRaisesRegex(RiftError, "expected no user info, query"):
            parse_token_proxy("http://user:pass@127.0.0.1:8765")
        with self.assertRaisesRegex(RiftError, "expected no user info, query"):
            parse_token_proxy("http://127.0.0.1:8765?arch=1")


class DnfRepoRenderTest(RiftTestCase):
    def test_render(self):
        repo = ConsumableRepository(
            "https://pkgs.internal/8.8/BaseOS/x86_64/os",
            name="os",
            options={
                "module_hotfixes": True,
                "excludepkgs": "kernel",
                "proxy": "http://127.0.0.1:8080",
            },
        )
        text = render_dnf_repo([repo], "x86_64")
        self.assertEqual(
            text,
            "\n".join(
                [
                    "[os]",
                    "name=os",
                    "baseurl=https://pkgs.internal/8.8/BaseOS/$basearch/os",
                    "gpgcheck=0",
                    "priority=999",
                    "enabled=1",
                    "module_hotfixes=True",
                    "excludepkgs=kernel",
                    "proxy=http://127.0.0.1:8080",
                    "",
                ]
            ),
        )

    def test_priority(self):
        repos = [
            ConsumableRepository("https://a.example/repo", name="a"),
            ConsumableRepository("https://b.example/repo", name="b", priority=5),
            ConsumableRepository("https://c.example/repo", name="c", priority=0),
            ConsumableRepository("https://d.example/repo", name="d"),
        ]
        text = render_dnf_repo(repos, "x86_64")
        self.assertIn("name=a\nbaseurl=https://a.example/repo\n", text)
        self.assertIn("gpgcheck=0\npriority=999\n", text)
        self.assertIn("name=b\nbaseurl=https://b.example/repo\n", text)
        self.assertIn("priority=5\n", text)
        self.assertIn("name=c\nbaseurl=https://c.example/repo\n", text)
        self.assertIn("priority=4\n", text)
        self.assertIn("name=d\nbaseurl=https://d.example/repo\n", text)
        self.assertIn("priority=3\n", text)

    def test_variants(self):
        repos = [
            ConsumableRepository("https://a.example/repo", name="a"),
            ConsumableRepository(
                "https://b.example/repo", name="b", variants=["extra"]
            ),
            ConsumableRepository("https://c.example/repo", name="c", variants=["main"]),
        ]
        text = render_dnf_repo(repos, "x86_64")
        self.assertIn("name=a\nbaseurl=https://a.example/repo\n", text)
        self.assertIn("priority=999\nenabled=1\n", text)
        self.assertIn("name=b\nbaseurl=https://b.example/repo\n", text)
        self.assertIn("priority=998\nenabled=0\n", text)
        self.assertIn("name=c\nbaseurl=https://c.example/repo\n", text)
        self.assertIn("priority=997\nenabled=1\n", text)

    def test_host_replacement(self):
        def baseurl(url, host):
            text = render_dnf_repo(
                [ConsumableRepository(url, name="os")],
                "x86_64",
                host=parse_host(host),
            )
            for line in text.splitlines():
                if line.startswith("baseurl="):
                    return line.split("=", 1)[1]
            self.fail("missing baseurl")

        self.assertEqual(
            baseurl(_DECLARED, "pkgs.external"), "httpss://pkgs.external/foo/bar"
        )
        self.assertEqual(
            baseurl(_DECLARED, "pkgs.external:9443"),
            "httpss://pkgs.external:9443/foo/bar",
        )
        self.assertEqual(
            baseurl(_DECLARED, "http://pkgs.external"), "http://pkgs.external/foo/bar"
        )
        self.assertEqual(
            baseurl(_DECLARED, "http://pkgs.external:8080"),
            "http://pkgs.external:8080/foo/bar",
        )
        self.assertEqual(
            baseurl("https://pkgs.internal:8443/bla/bli?arch=1", "pkgs.external"),
            "https://pkgs.external/bla/bli?arch=1",
        )
        self.assertEqual(
            baseurl("file:///var/repos/os", "pkgs.external"), "file:///var/repos/os"
        )
        self.assertEqual(baseurl("/var/repos/os", "pkgs.external"), "/var/repos/os")
        self.assertEqual(baseurl("http:///missing", "pkgs.external"), "http:///missing")

    def test_authenticated_without_token_proxy(self):
        repo = ConsumableRepository(
            "https://pkgs.internal/private/x86_64",
            name="private",
            options={"auth": "idp_token", "proxy": "http://127.0.0.1:8080"},
        )
        text = render_dnf_repo([repo], "x86_64", host=parse_host("pkgs.external"))
        self.assertIn(
            "baseurl=https://pkgs.external/private/$basearch\n",
            text,
        )
        self.assertNotIn("proxy=", text)

    def test_token_proxy_rewrites_only_authenticated_repos(self):
        public = ConsumableRepository(
            "https://pkgs.internal:8443/os/x86_64",
            name="os",
            options={"proxy": "http://proxy:3128"},
        )
        private = ConsumableRepository(
            "https://pkgs.internal/private/x86_64",
            name="private repo",
            options={"auth": "idp_token", "proxy": "http://proxy:3128"},
        )
        text = render_dnf_repo(
            [public, private],
            "x86_64",
            host=parse_host("pkgs.external"),
            token_proxy=parse_token_proxy("http://127.0.0.1:8765/"),
        )
        self.assertIn(
            "baseurl=https://pkgs.external/os/$basearch\n",
            text,
        )
        self.assertIn("proxy=http://proxy:3128\n", text)
        self.assertIn("baseurl=http://127.0.0.1:8765/private%20repo/\n", text)
        self.assertNotIn("proxy=", text.split("\n\n")[1])
        self.assertNotIn("pkgs.external/private", text)

    def test_empty(self):
        self.assertEqual(render_dnf_repo([], "x86_64"), "")


class ReposConfMainTest(RiftTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self._tmpdir.name, "project.conf")
        with open(self.config_path, "w", encoding="utf-8") as conf:
            conf.write(_PROJECT_CONF)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_stdout(self):
        buf = StringIO()
        with patch(
            "rift.apps.repos_conf.render_dnf_repo", return_value="rendered\n"
        ) as render, patch("sys.stdout", buf):
            rc = main(["--arch", "x86_64", self.config_path])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue(), "rendered\n")
        args, kwargs = render.call_args
        repos, arch = args
        self.assertEqual(arch, "x86_64")
        self.assertEqual([repo.name for repo in repos], ["os", "private", "local"])
        self.assertIsNone(kwargs["host"])
        self.assertIsNone(kwargs["token_proxy"])

    def test_default_arch(self):
        config = Config()
        config.load(self.config_path)
        with patch(
            "rift.apps.repos_conf.render_dnf_repo", return_value=""
        ) as render, patch("sys.stdout", StringIO()):
            rc = main([self.config_path])
        self.assertEqual(rc, 0)
        self.assertEqual(render.call_args[0][1], config.chroot_arch())

    def test_output_file(self):
        output = os.path.join(self._tmpdir.name, "rift.repo")
        with patch(
            "rift.apps.repos_conf.render_dnf_repo", return_value="rendered\n"
        ) as render:
            rc = main(
                [
                    "-H",
                    "pkgs.external",
                    "--token-proxy",
                    "http://127.0.0.1:8765",
                    "-o",
                    output,
                    "--arch",
                    "x86_64",
                    self.config_path,
                ]
            )
        self.assertEqual(rc, 0)
        with open(output, encoding="utf-8") as repo_file:
            self.assertEqual(repo_file.read(), "rendered\n")
        kwargs = render.call_args[1]
        self.assertEqual(kwargs["host"], RepositoryHost(None, "pkgs.external", None))
        self.assertEqual(kwargs["token_proxy"], "127.0.0.1:8765")

    def test_arch_repos(self):
        with patch(
            "rift.apps.repos_conf.render_dnf_repo", return_value=""
        ) as render, patch("sys.stdout", StringIO()):
            rc = main(
                [
                    "--arch",
                    "aarch64",
                    "-H",
                    "http://pkgs.external",
                    self.config_path,
                ]
            )
        self.assertEqual(rc, 0)
        args, kwargs = render.call_args
        repos, arch = args
        self.assertEqual(arch, "aarch64")
        self.assertEqual([repo.name for repo in repos], ["alt"])
        self.assertEqual(kwargs["host"], RepositoryHost("http", "pkgs.external", None))

    def test_main_missing_config(self):
        root = logging.getLogger()
        previous = root.level
        root.setLevel(logging.ERROR)
        try:
            with self.assertLogs(level="ERROR") as logs:
                rc = main(["/no/such/rift-project.conf"])
        finally:
            root.setLevel(previous)
        self.assertEqual(rc, 1)
        self.assertTrue(any("Could not find" in message for message in logs.output))

    def test_main_missing_config_reraises_when_debug(self):
        root = logging.getLogger()
        previous = root.level
        root.setLevel(logging.DEBUG)
        try:
            with self.assertRaisesRegex(RiftError, "Could not find"):
                main(["/no/such/rift-project.conf"])
        finally:
            root.setLevel(previous)


class ReposConfArgsTest(RiftTestCase):
    def test_make_parser_defaults(self):
        opts = make_parser().parse_args(["project.conf"])
        self.assertEqual(opts.config, "project.conf")
        self.assertIsNone(opts.output)
        self.assertIsNone(opts.arch)
        self.assertIsNone(opts.host)
        self.assertIsNone(opts.token_proxy)
        self.assertEqual(opts.verbose, 0)

    def test_make_parser_options(self):
        opts = make_parser().parse_args(
            [
                "-vv",
                "-o",
                "out.repo",
                "--arch",
                "aarch64",
                "--token-proxy",
                "http://127.0.0.1:8765",
                "project.conf",
            ]
        )
        self.assertEqual(opts.output, "out.repo")
        self.assertEqual(opts.arch, "aarch64")
        self.assertEqual(opts.token_proxy, "http://127.0.0.1:8765")
        self.assertEqual(opts.verbose, 2)

    def test_host_short_and_long_options(self):
        short = make_parser().parse_args(["-H", "pkgs.external", "project.conf"])
        long = make_parser().parse_args(["--host", "pkgs.external", "project.conf"])
        self.assertEqual(short.host, "pkgs.external")
        self.assertEqual(long.host, short.host)
