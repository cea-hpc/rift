#
# Copyright (C) 2026 CEA
#
import os
import subprocess
from unittest.mock import Mock, patch

from rift import RiftError
from rift.container import ContainerArchive, ContainerFile, ContainerRuntime
from rift.gerrit import Review
from rift.package.oci import PackageOCI
from rift.run import RunResult

from .test_utils import (
    EXPECTED_HADOLINT_EXEC,
    RiftProjectTestCase,
    command_available,
    gen_containerfile,
    make_temp_file,
    make_temp_tar,
    remove_gpg_home,
)


class ContainerRuntimeTest(RiftProjectTestCase):
    """Tests class for ContainerRuntime"""

    def test_tag(self):
        """Test ContainerRuntime tag generation."""
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch("x86_64")
        container = ContainerRuntime(self.config)
        self.assertEqual(container.tag(actionable_package), "pkg:1.0-1-x86_64")

    @patch("rift.container.run_command")
    def test_build(self, mock_run_command):
        """Test ContainerRuntime build command."""
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch("x86_64")
        container = ContainerRuntime(self.config)
        mock_run_command.return_value = RunResult(0, "ok", None)
        container.build(actionable_package, "pkg_1.0")
        mock_run_command.assert_called_once_with(
            [
                "podman",
                "--root",
                container.rootdir,
                "build",
                "--arch",
                "amd64",
                "--annotation",
                "org.opencontainers.image.version=1.0-1",
                "--annotation",
                "org.opencontainers.image.title=pkg",
                "--annotation",
                "org.opencontainers.image.vendir=rift",
                "--tag",
                "pkg:1.0-1-x86_64",
                "pkg_1.0",
            ]
        )

    @patch("rift.container.run_command")
    def test_build_failure(self, mock_run_command):
        """Test ContainerRuntime build failure handling."""
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch("x86_64")
        container = ContainerRuntime(self.config)
        mock_run_command.return_value = RunResult(1, None, "failure")
        with self.assertRaisesRegex(
            RiftError, "^Container image build error: exit code 1$"
        ):
            container.build(actionable_package, "pkg_1.0")

    @patch("rift.container.run_command")
    def test_run_test(self, mock_run_command):
        """Test ContainerRuntime run_test command."""
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch("x86_64")
        test = [test for test in package.tests()].pop()
        container = ContainerRuntime(self.config)
        test_result = RunResult(0, "ok", None)
        mock_run_command.return_value = test_result
        self.assertEqual(container.run_test(actionable_package, test), test_result)
        mock_run_command.assert_called_once_with(
            [
                "podman",
                "--root",
                container.rootdir,
                "run",
                "--rm",
                "-i",
                "--mount",
                f"type=bind,src={package.dir}/tests/0_test.sh,dst=/run/0_test.sh,ro=true",
                "--arch",
                "amd64",
                "localhost/pkg:1.0-1-x86_64",
                "/run/0_test.sh",
            ],
            capture_output=True,
        )

    @patch("rift.container.run_command")
    def test_archive(self, mock_run_command):
        """Test ContainerRuntime archive command."""
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch("x86_64")
        container = ContainerRuntime(self.config)
        archive_result = RunResult(0, "ok", None)
        mock_run_command.return_value = archive_result
        self.assertEqual(
            container.archive(
                actionable_package,
                ContainerArchive(self.config, "/path/to/container.tar"),
            ),
            archive_result,
        )
        mock_run_command.assert_called_once_with(
            [
                "podman",
                "--root",
                container.rootdir,
                "push",
                "pkg:1.0-1-x86_64",
                "oci-archive:/path/to/container.tar:pkg:1.0-1-x86_64",
            ]
        )


class ContainerArchiveTest(RiftProjectTestCase):
    def setUp(self):
        super().setUp()
        # Initialize ContainerArchive with temporary tarball
        self.container_archive = ContainerArchive(self.config, make_temp_tar())

    def tearDown(self):
        super().tearDown()
        os.unlink(self.container_archive.path)
        if os.path.exists(self.container_archive.signature):
            os.unlink(self.container_archive.signature)

    def test_sign_no_conf(self):
        """ContainerArchive.sign() fail with nonexistent keyring."""
        with self.assertRaisesRegex(
            RiftError,
            r"^Unable to retrieve GPG configuration, unable to sign OCI "
            r"archive .*\.tar$",
        ):
            self.container_archive.sign()
        self.assertFalse(os.path.exists(self.container_archive.signature))

    def test_sign_no_keyring(self):
        """ContainerArchive.sign() fail with nonexistent keyring."""
        self.config.options.update(
            {
                "gpg": {
                    "keyring": "/path/to/nonexistent/keyring",
                    "key": "rift",
                }
            }
        )
        self.config._check()
        with self.assertRaisesRegex(
            RiftError,
            r"^GPG keyring path /path/to/nonexistent/keyring does not exist, "
            r"unable to sign OCI archive .*\.tar$",
        ):
            self.container_archive.sign()
        self.assertFalse(os.path.exists(self.container_archive.signature))

    def sign_copy(self, gpg_passphrase, conf_passphrase=None, preset_passphrase=None):
        """
        Generate keyring with provided gpg passphrase, update configuration with
        generated keyring, copy unsigned rpm_pkg, sign it, verify signature and
        cleanup everything.
        """
        gpg_home = os.path.join(self.projdir, ".gnupg")

        # Launch the agent with --allow-preset-passphrase to accept passphrase
        # provided non-interactively by gpg-preset-passphrase.
        cmd = [
            "gpg-agent",
            "--homedir",
            gpg_home,
            "--allow-preset-passphrase",
            "--daemon",
        ]
        subprocess.run(cmd)

        # Generate keyring
        gpg_key = "rift"
        cmd = [
            "gpg",
            "--homedir",
            gpg_home,
            "--batch",
            "--passphrase",
            gpg_passphrase or "",
            "--quick-generate-key",
            gpg_key,
        ]
        subprocess.run(cmd)

        # If preset passphrase is provided, add it to the agent
        # non-interactively with gpg-preset-passphrase.
        if preset_passphrase:
            # First find keygrip
            keygrip = None
            cmd = [
                "gpg",
                "--homedir",
                gpg_home,
                "--fingerprint",
                "--with-keygrip",
                "--with-colons",
                gpg_key,
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE)
            for line in proc.stdout.decode().split("\n"):
                if line.startswith("grp"):
                    keygrip = line.split(":")[9]
                    break
            # Run gpg-preset-passphrase to add passphrase in agent
            cmd = ["/usr/libexec/gpg-preset-passphrase", "--preset", keygrip]
            subprocess.run(
                cmd, env={"GNUPGHOME": gpg_home}, input=preset_passphrase.encode()
            )

        # Update project configuration with generated key
        self.config.options.update(
            {
                "gpg": {
                    "keyring": gpg_home,
                    "key": gpg_key,
                }
            }
        )

        if conf_passphrase is not None:
            self.config.options["gpg"]["passphrase"] = conf_passphrase
        self.config._check()

        try:
            self.container_archive.sign()

        finally:
            remove_gpg_home(gpg_home)

    def test_sign(self):
        """Container archive signature."""
        self.sign_copy("TOPSECRET", "TOPSECRET")
        self.assertTrue(os.path.exists(self.container_archive.signature))

    def test_sign_wrong_passphrase(self):
        """
        Container archive signature raises RiftError with wrong passphrase.
        """
        with self.assertRaisesRegex(RiftError, "^Error with signing OCI archive .*"):
            self.sign_copy("TOPSECRET", "WRONG_PASSPHRASE")
        self.assertFalse(os.path.exists(self.container_archive.signature))

    def test_sign_passphrase_agent_not_interactive(self):
        """
        Container archive signature with passphrase in agent not interactive.
        """
        # When the key is encrypted with passphrase, the passphrase is not set
        # in Rift configuration but loaded in GPG agent, Rift must sign the
        # package without making the agent launch pinentry to ask for the
        # passphrase interactively.
        self.sign_copy("TOPSECRET", preset_passphrase="TOPSECRET")
        self.assertTrue(os.path.exists(self.container_archive.signature))

    def test_sign_empty_passphrase_not_interactive(self):
        """
        Container archive signature with empty passphrase no interactive
        passphrase.
        """
        # When the key is NOT encrypted with passphrase, Rift must sign the
        # package without making the agent launch pinentry to ask for the
        # passphrase interactively.
        self.sign_copy(None)
        self.assertTrue(os.path.exists(self.container_archive.signature))


class ContainerFileTest(RiftProjectTestCase):
    """Tests class for ContainerFile"""

    def test_check(self):
        """ContainerFile check"""
        if not command_available(EXPECTED_HADOLINT_EXEC):
            self.skipTest("hadolint executable not found")
        self.config.update({"containers": {"linter": EXPECTED_HADOLINT_EXEC}})
        tmp_container_file = make_temp_file(gen_containerfile())
        container_file = ContainerFile(self.config, tmp_container_file.name)
        container_file.check()

    def test_check_error(self):
        """ContainerFile check with error"""
        if not command_available(EXPECTED_HADOLINT_EXEC):
            self.skipTest("hadolint executable not found")
        self.config.update({"containers": {"linter": EXPECTED_HADOLINT_EXEC}})
        tmp_container_file = make_temp_file(gen_containerfile(lines=["WORKDIR fail"]))
        container_file = ContainerFile(self.config, tmp_container_file.name)
        with self.assertRaisesRegex(
            RiftError, r"^Containerfile check error\: .* Use absolute WORKDIR"
        ):
            container_file.check()

    def test_check_linter_not_found(self):
        """ContainerFile check error log linter not found"""
        self.config.update({"containers": {"linter": "hadolint-not-found"}})
        tmp_container_file = make_temp_file(gen_containerfile())
        container_file = ContainerFile(self.config, tmp_container_file.name)
        with self.assertLogs(level="ERROR") as log:
            container_file.check()
        self.assertIn(
            "ERROR:root:Unable to find Containerfile linter executable "
            "'hadolint-not-found'",
            log.output,
        )

    def test_analyze(self):
        """ContainerFile analyze"""
        if not command_available(EXPECTED_HADOLINT_EXEC):
            self.skipTest("hadolint executable not found")
        self.config.update({"containers": {"linter": EXPECTED_HADOLINT_EXEC}})
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        tmp_container_file = make_temp_file(gen_containerfile())
        container_file = ContainerFile(self.config, tmp_container_file.name)
        review = Mock(spec=Review)
        container_file.analyze(review, package.dir)
        review.add_comment.assert_not_called()
        review.invalidate.assert_not_called()

    def test_analyze_with_error(self):
        """ContainerFile analyze with error"""
        if not command_available(EXPECTED_HADOLINT_EXEC):
            self.skipTest("hadolint executable not found")
        self.config.update({"containers": {"linter": EXPECTED_HADOLINT_EXEC}})
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        tmp_container_file = make_temp_file(gen_containerfile(lines=["WORKDIR fail"]))
        container_file = ContainerFile(self.config, tmp_container_file.name)
        review = Mock(spec=Review)
        container_file.analyze(review, package.dir)
        review.add_comment.assert_called_with(
            container_file.path, "3", "DL3000", "Use absolute WORKDIR"
        )
        review.invalidate.assert_called_once()

    def test_analyze_linter_not_found(self):
        """ContainerFile analyze error when linter not found"""
        self.config.update({"containers": {"linter": "hadolint-not-found"}})
        self.make_pkg()
        package = PackageOCI("pkg", self.config, self.staff, self.modules)
        tmp_container_file = make_temp_file(gen_containerfile())
        container_file = ContainerFile(self.config, tmp_container_file.name)
        review = Mock(spec=Review)
        with self.assertRaisesRegex(
            RiftError,
            "Unable to find Containerfile linter executable 'hadolint-not-found'",
        ):
            container_file.analyze(review, package.dir)
        review.invalidate.assert_not_called()
