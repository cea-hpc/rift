#
# Copyright (C) 2025 CEA
#

import os
import shutil
from unittest.mock import Mock

from ..TestUtils import make_temp_dir, RiftTestCase

from rift import RiftError
from rift.Config import Config
from rift.repository._project import ProjectArchRepositories, StagingRepository
from rift.repository._base import ArchRepositoriesBase
from rift.repository.rpm import ArchRepositoriesRPM, StagingRepositoryRPM

class ProjectArchRepositoriesTest(RiftTestCase):
    """
    Tests class for ProjectArchRepositories
    """
    def setUp(self):
        self.config = Config()

    def test_working_with_arch(self):
        """Test working repo with $arch placeholder and arch specific value"""
        working_repo_path = make_temp_dir()
        self.config.options['working_repo'] = os.path.join(
                working_repo_path, '$arch'
        )
        self.config.options['repos'] = {}
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(
            repos.working_dir, os.path.join(working_repo_path, 'x86_64')
        )

        # If an arch specific working_repo parameter is defined in
        # configuration, it should override generic working_repo parameter for
        # this arch.

        other_working_repo_path = make_temp_dir()
        # Declare supported architectures.
        self.config.options['arch'] = ['x86_64', 'aarch64']
        self.config.options['x86_64'] = {
            'working_repo': other_working_repo_path
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.working_dir, other_working_repo_path)
        repos = ProjectArchRepositories(self.config, 'aarch64')
        self.assertEqual(
            repos.working_dir, os.path.join(working_repo_path, 'aarch64')
        )
        shutil.rmtree(working_repo_path)
        shutil.rmtree(other_working_repo_path)

    def test_can_publish(self):
        """Test ProjectArchRepositories.can_publish() with working_repo"""
        working_repo_path = make_temp_dir()
        self.config.options['working_repo'] = working_repo_path
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertTrue(repos.can_publish())
        shutil.rmtree(working_repo_path)

    def test_cannot_publish(self):
        """Test ProjectArchRepositories.can_publish() without working_repo"""
        self.assertNotIn('working_repo', self.config.options)
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertFalse(repos.can_publish())

    def test_delete_matching(self):
        repos = ProjectArchRepositories(self.config, 'x86_64')
        # mock all format specific classes
        repos.FORMAT_CLASSES = { _format: Mock(spec=ArchRepositoriesBase)
                                 for _format in repos.FORMAT_CLASSES.keys() }
        repos.delete_matching('pkg')
        # Check delete_matching() method has been called with provided package
        # for all supported formats.
        for _format in repos.FORMAT_CLASSES.keys():
            repos.FORMAT_CLASSES[_format].return_value.delete_matching \
                .assert_called_once_with('pkg')

    def test_for_format(self):
        """Test ProjectArchRepositories.for_format()"""
        repos = ProjectArchRepositories(self.config, 'x86_64')
        format_repos = repos.for_format('rpm')
        self.assertIsInstance(format_repos, ArchRepositoriesBase)
        self.assertIsInstance(format_repos, ArchRepositoriesRPM)

    def test_for_format_unsupported(self):
        """Test ProjectArchRepositories.for_format() unsupported format"""
        with self.assertRaisesRegex(
            RiftError,
            "^Unable to get configuration option for unsupported architecture 'fail'$"
        ):
            ProjectArchRepositories(self.config, 'fail')


class StagingRepositoryTest(RiftTestCase):
    def setUp(self):
        self.config = Config()
        self.staging = StagingRepository(self.config)

    def tearDown(self):
        self.staging.delete()

    def test_create_delete(self):
        # Check temporary stagedir has been created
        path = self.staging.stagedir.path
        self.assertTrue(os.path.exists(path))
        # Check it is removed after delete()
        self.staging.delete()
        self.assertFalse(os.path.exists(path))

    def test_formats(self):
        self.assertIsInstance(self.staging.for_format('rpm'), StagingRepositoryRPM)

    def test_format_unsupported(self):
        with self.assertRaisesRegex(
            RiftError, "^Unsupported staging repository format fail$"
        ):
            self.staging.for_format('fail')
