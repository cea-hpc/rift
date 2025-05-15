#
# Copyright (C) 2023 CEA
#

import os
import getpass
from unittest.mock import patch

from TestUtils import make_temp_dir, RiftProjectTestCase
from rift.Mock import Mock
from rift.Repository import ConsumableRepository
from rift import RiftError

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

    @patch('rift.Mock.Popen')
    def test_init(self, mock_popen):
        """ Test Mock init creates all files required by mock """
        # Emulate successful mock execution
        mock_popen.return_value.returncode = 0
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

    @patch('rift.Mock.Popen')
    def test_init_mock_failure(self, mock_popen):
        """ Test Mock init raise error on mock command failure """
        # Emulate mock execution failure
        mock_popen.return_value.returncode = 1
        mock_popen.return_value.communicate.return_value = ["output"]
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
