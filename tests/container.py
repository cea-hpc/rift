#
# Copyright (C) 2026 CEA
#
from unittest.mock import patch, Mock

from .TestUtils import (
    RiftProjectTestCase,
    command_available,
    make_temp_file,
    gen_containerfile,
    EXPECTED_HADOLINT_EXEC
)

from rift.container import ContainerRuntime, ContainerFile
from rift.package.oci import PackageOCI
from rift.run import RunResult
from rift.Gerrit import Review
from rift import RiftError


class ContainerRuntimeTest(RiftProjectTestCase):
    """Tests class for ContainerRuntime"""

    def test_tag(self):
        """Test ContainerRuntime tag generation."""
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch('x86_64')
        container = ContainerRuntime(self.config)
        self.assertEqual(container.tag(actionable_package), 'pkg:1.0-1-x86_64')

    @patch('rift.container.run_command')
    def test_build(self, mock_run_command):
        """Test ContainerRuntime build command."""
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch('x86_64')
        container = ContainerRuntime(self.config)
        mock_run_command.return_value = RunResult(0, 'ok', None)
        container.build(actionable_package, 'pkg_1.0')
        mock_run_command.assert_called_once_with(
            ['podman', '--root', container.rootdir, 'build',
             '--arch', 'amd64',
             '--annotation', 'org.opencontainers.image.version=1.0-1',
             '--annotation', 'org.opencontainers.image.title=pkg',
             '--annotation', 'org.opencontainers.image.vendir=rift',
             '--tag', 'pkg:1.0-1-x86_64', 'pkg_1.0'])

    @patch('rift.container.run_command')
    def test_build_failure(self, mock_run_command):
        """Test ContainerRuntime build failure handling."""
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch('x86_64')
        container = ContainerRuntime(self.config)
        mock_run_command.return_value = RunResult(1, None, 'failure')
        with self.assertRaisesRegex(
            RiftError, "^Container image build error: exit code 1$"):
            container.build(actionable_package, 'pkg_1.0')

    @patch('rift.container.run_command')
    def test_run_test(self, mock_run_command):
        """Test ContainerRuntime run_test command."""
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch('x86_64')
        test = [test for test in package.tests()].pop()
        container = ContainerRuntime(self.config)
        test_result = RunResult(0, 'ok', None)
        mock_run_command.return_value = test_result
        self.assertEqual(container.run_test(actionable_package, test), test_result)
        mock_run_command.assert_called_once_with(
            ['podman', '--root', container.rootdir, 'run', '--rm',
             '-i', '--mount',
             f'type=bind,src={package.dir}/tests/0_test.sh,dst=/run/0_test.sh,ro=true',
             '--arch', 'amd64', 'localhost/pkg:1.0-1-x86_64', '/run/0_test.sh'],
             capture_output=True)

    @patch('rift.container.run_command')
    def test_archive(self, mock_run_command):
        """Test ContainerRuntime archive command."""
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch('x86_64')
        container = ContainerRuntime(self.config)
        archive_result = RunResult(0, 'ok', None)
        mock_run_command.return_value = archive_result
        self.assertEqual(
            container.archive(actionable_package, '/path/to/container.tar'),
            archive_result)
        mock_run_command.assert_called_once_with(
            ['podman', '--root', container.rootdir, 'push', 'pkg:1.0-1-x86_64',
             'oci-archive:/path/to/container.tar:pkg:1.0-1-x86_64'])

class ContainerFileTest(RiftProjectTestCase):
    """Tests class for ContainerFile"""

    def test_check(self):
        """ContainerFile check"""
        if not command_available(EXPECTED_HADOLINT_EXEC):
            self.skipTest("hadolint executable not found")
        self.config.update({'containers': { 'linter': EXPECTED_HADOLINT_EXEC }})
        tmp_container_file = make_temp_file(gen_containerfile())
        container_file = ContainerFile(self.config, tmp_container_file.name)
        container_file.check()

    def test_check_error(self):
        """ContainerFile check with error"""
        if not command_available(EXPECTED_HADOLINT_EXEC):
            self.skipTest("hadolint executable not found")
        self.config.update({'containers': { 'linter': EXPECTED_HADOLINT_EXEC }})
        tmp_container_file = make_temp_file(gen_containerfile(lines=["WORKDIR fail"]))
        container_file = ContainerFile(self.config, tmp_container_file.name)
        with self.assertRaisesRegex(
            RiftError, r"^Containerfile check error\: .* Use absolute WORKDIR"
        ):
            container_file.check()

    def test_check_linter_not_found(self):
        """ContainerFile check error log linter not found"""
        self.config.update({'containers': { 'linter': 'hadolint-not-found' }})
        tmp_container_file = make_temp_file(gen_containerfile())
        container_file = ContainerFile(self.config, tmp_container_file.name)
        with self.assertLogs(level='ERROR') as log:
            container_file.check()
        self.assertIn(
            "ERROR:root:Unable to find Containerfile linter executable "
            "'hadolint-not-found'",
            log.output
        )

    def test_analyze(self):
        """ContainerFile analyze"""
        if not command_available(EXPECTED_HADOLINT_EXEC):
            self.skipTest("hadolint executable not found")
        self.config.update({'containers': { 'linter': EXPECTED_HADOLINT_EXEC }})
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
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
        self.config.update({'containers': { 'linter': EXPECTED_HADOLINT_EXEC }})
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        tmp_container_file = make_temp_file(gen_containerfile(lines=["WORKDIR fail"]))
        container_file = ContainerFile(self.config, tmp_container_file.name)
        review = Mock(spec=Review)
        container_file.analyze(review, package.dir)
        review.add_comment.assert_called_with(
            container_file.path, '3', 'DL3000', 'Use absolute WORKDIR')
        review.invalidate.assert_called_once()

    def test_analyze_linter_not_found(self):
        """ContainerFile analyze error when linter not found"""
        self.config.update({'containers': { 'linter': 'hadolint-not-found' }})
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        tmp_container_file = make_temp_file(gen_containerfile())
        container_file = ContainerFile(self.config, tmp_container_file.name)
        review = Mock(spec=Review)
        with self.assertRaisesRegex(
            RiftError,
            "Unable to find Containerfile linter executable 'hadolint-not-found'"
        ):
            container_file.analyze(review, package.dir)
        review.invalidate.assert_not_called()
