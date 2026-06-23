#
# Copyright (C) 2025 CEA
#
from unittest.mock import patch

from .TestUtils import RiftProjectTestCase

from rift.container import ContainerRuntime
from rift.package.oci import PackageOCI
from rift.run import RunResult
from rift import RiftError

class ContainerTest(RiftProjectTestCase):
    """Tests class for ContainerRuntime"""

    def test_tag(self):
        self.make_pkg()
        package = PackageOCI('pkg', self.config, self.staff, self.modules)
        package.load()
        actionable_package = package.for_arch('x86_64')
        container = ContainerRuntime(self.config)
        self.assertEqual(container.tag(actionable_package), 'pkg:1.0-1-x86_64')

    @patch('rift.container.run_command')
    def test_build(self, mock_run_command):
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
