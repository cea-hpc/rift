#
# Copyright (C) 2023 CEA
#

import os
import getpass
from unittest.mock import patch, MagicMock

from .TestUtils import RiftProjectTestCase
from rift.Mock import Mock
from rift.repository import ProjectArchRepositories
from rift.repository.rpm import ConsumableRepository
from rift.RPM import RPM
from rift.TempDir import TempDir
from rift.run import RunResult
from rift.Config import _DEFAULT_VARIANT
from rift import RiftError

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


class MockTest(RiftProjectTestCase):
    """
    Tests class for Mock
    """

    def test_mock_object(self):
        """ Test Mock instanciation """
        mock = Mock(config=[], arch='x86_64', proj_vers=1.0)
        self.assertEqual(mock._mockname, "rift-x86_64-{}-1.0".format(getpass.getuser()))
        self.assertEqual(mock._config, [])

    def test_build_context(self):
        """ Test mock context generation """
        arch = 'aarch64'
        _repo_config = {
                        'module_hotfixes': True,
                        'excludepkgs': 'somepkg',
                        'proxy': 'myproxy',
                    }
        mock = Mock({}, arch)
        repolist = [
            ConsumableRepository(
                f"file:///tmp/{arch}", name='tmp', options=_repo_config
            )
        ]
        context = mock._build_template_ctx(repolist)
        self.assertEqual(context['name'], 'rift-{}-{}'.format(arch, getpass.getuser()))
        self.assertEqual(context['arch'], arch)
        repos_ctx = context['repos'][0]
        self.assertEqual(repos_ctx['name'], 'tmp')
        self.assertEqual(repos_ctx['priority'], 999)
        self.assertEqual(repos_ctx['url'], 'file:///tmp/$basearch')
        self.assertEqual(repos_ctx['module_hotfixes'], True)
        self.assertEqual(repos_ctx['excludepkgs'], 'somepkg')
        self.assertEqual(repos_ctx['proxy'], 'myproxy')

    @patch('rift.Mock.run_command')
    def test_init(self, mock_run_command):
        """ Test Mock init creates all files required by mock """
        # Emulate successful mock execution
        mock_run_command.return_value = RunResult(0, None, None)
        mock = Mock(config=self.config, arch='x86_64', proj_vers=1.0)
        mock.init([])
        self.assertTrue(
            os.path.exists(os.path.join(mock._tmpdir.path, mock.MOCK_DEFAULT))
        )
        for filename in mock.MOCK_FILES:
            self.assertTrue(
                os.path.exists(os.path.join(mock._tmpdir.path, filename))
            )
        mock.clean()

    @patch('rift.Mock.run_command')
    def test_init_mock_failure(self, mock_run_command):
        """ Test Mock init raise error on mock command failure """
        # Emulate mock execution failure
        mock_run_command.return_value = RunResult(1, "output", None)
        mock = Mock(config=self.config, arch='x86_64', proj_vers=1.0)
        with self.assertRaisesRegex(RiftError, "^output$"):
            mock.init([])
        mock.clean()

    def test_init_unexisting_repo(self):
        """ Test Mock init raise error on unexisting local file repository """
        # Emulate mock execution failure
        mock = Mock(config=self.config, arch='x86_64', proj_vers=1.0)
        with self.assertRaisesRegex(
            RiftError,
            "^Repository /fail does not exist, unable to initialize Mock "
            "environment$"
        ):
            mock.init([ConsumableRepository("file:///fail")])
        mock.clean()

    def test_args(self):
        """ Test mock standard arguments """
        mock = Mock(config={}, arch='x86_64', proj_vers=1.0)
        # Init tmp directory
        mock._tmpdir = TempDir('test_mock')
        mock._tmpdir.create()
        self.assertEqual(mock._mock_base(),
                         ['mock',
                          '--config-opts',
                          'print_main_output=yes',
                          f'--configdir={mock._tmpdir.path}'])

    def test_args_with_macros(self):
        """ Test Mock macro arguments """
        mock = Mock(config={"rpm_macros": {"my_version" : 1}}, arch='x86_64', proj_vers=1.0)
        # Init tmp directory
        mock._tmpdir = TempDir('test_mock')
        mock._tmpdir.create()

        macro_file = os.path.join(mock._tmpdir.path, 'rpm.macro')
        self.assertEqual(mock._mock_base(),
                         ['mock',
                          '--config-opts',
                          'print_main_output=yes',
                          f'--configdir={mock._tmpdir.path}',
                          f'--macro-file={macro_file}'])
        self.assertEqual(open(macro_file).readlines(), ["%my_version 1\n"])

    @patch('rift.Mock.run_command')
    def test_build_rpms(self, mock_run_command):
        """ Test Mock build_rpms() mock build command line """
        # Emulate successful mock execution
        mock_run_command.return_value = RunResult(0, None, None)
        mock = Mock(config=self.config, arch='x86_64', proj_vers=1.0)
        # Init tmp directory
        mock._tmpdir = TempDir('test_mock')
        mock._tmpdir.create()

        src_rpm_path = os.path.join(
            TESTS_DIR, 'materials', 'pkg-1.0-1.src.rpm'
        )
        repos = ProjectArchRepositories(self.config, 'x86_64').for_format('rpm')
        srpm = RPM(src_rpm_path)
        mock.build_rpms(srpm, _DEFAULT_VARIANT, repos, False)
        mock_run_command.assert_called_once_with(
            [
                'mock',
                '--config-opts',
                'print_main_output=yes',
                f"--configdir={mock._tmpdir.path}",
                '--no-clean',
                '--no-cleanup-after',
                src_rpm_path
            ],
            live_output=True,
            capture_output=True,
            merge_out_err=True,
            cwd='/'
        )

    @patch('rift.Mock.run_command')
    def test_build_rpms_variant(self, mock_run_command):
        """ Test Mock build_rpms() mock build command line with variant """
        # Emulate successful mock execution
        mock_run_command.return_value = RunResult(0, None, None)
        mock = Mock(config=self.config, arch='x86_64', proj_vers=1.0)
        # Init tmp directory
        mock._tmpdir = TempDir('test_mock')
        mock._tmpdir.create()
        src_rpm_path = os.path.join(
            TESTS_DIR, 'materials', 'pkg-1.0-1.src.rpm'
        )
        repos = ProjectArchRepositories(self.config, 'x86_64').for_format('rpm')
        repos.for_variant = MagicMock(
            return_value=[
                ConsumableRepository('http://repo1', name='variant1-repo1'),
                ConsumableRepository('http://repo2', name='variant1-repo2'),
            ]
        )
        srpm = RPM(src_rpm_path)
        mock.build_rpms(srpm, 'variant1', repos, False)
        mock_run_command.assert_called_once_with(
            [
                'mock',
                '--config-opts',
                'print_main_output=yes',
                f"--configdir={mock._tmpdir.path}",
                '--no-clean',
                '--no-cleanup-after',
                src_rpm_path,
                '--with',
                'variant1',
                '--enablerepo',
                'variant1-repo1',
                '--enablerepo',
                'variant1-repo2',
            ],
            live_output=True,
            capture_output=True,
            merge_out_err=True,
            cwd='/'
        )
