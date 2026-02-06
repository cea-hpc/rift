#
# Copyright (C) 2023 CEA
#

import os
import shutil
from unittest.mock import patch

from .TestUtils import make_temp_dir, RiftTestCase
from rift.Repository import ConsumableRepository, LocalRepository, ProjectArchRepositories
from rift.Config import _DEFAULT_REPO_CMD, Config
from rift.RPM import RPM
from rift import RiftError

class LocalRepositoryTest(RiftTestCase):
    """
    Tests class for Repository
    """

    def test_init(self):
        """ Test LocalRepository instanciation with a specific configuration """
        arch = 'x86_64'
        _config = { 'arch': [arch], 'createrepo': 'mycustom_create_repo' }
        _options = {
            'module_hotfixes': True,
            'excludepkgs': 'somepkg',
            'proxy': 'myproxy',
        }
        repo_name = 'nowhere'
        repo = LocalRepository(
            '/{}'.format(repo_name),
            _config,
            options=_options
        )

        self.assertEqual(repo.path, '/{}'.format(repo_name))
        self.assertEqual(repo.srpms_dir, '/{}/{}'.format(repo_name, 'SRPMS'))
        self.assertEqual(list(repo.consumables.keys()), [arch])
        self.assertEqual(repo.consumables[arch].name, repo_name)
        self.assertEqual(
            repo.consumables[arch].url, 'file:///{}/{}'.format(repo_name, arch)
        )
        self.assertEqual(
            repo.rpms_dir(arch), '/{}/{}'.format(repo_name, arch)
        )
        self.assertEqual(repo.consumables[arch].priority, 1)
        self.assertEqual(repo.consumables[arch].module_hotfixes, True)
        self.assertEqual(repo.consumables[arch].excludepkgs, 'somepkg')
        self.assertEqual(repo.consumables[arch].proxy, 'myproxy')
        self.assertEqual(repo.createrepo, _config['createrepo'])

    def test_init_multiple_archs(self):
        """ Test LocalRepository instanciation with multiple architectures """
        archs = ['x86_64', 'aarch64']
        _config = { 'arch': archs }
        repo_name = 'nowhere'
        repo = LocalRepository('/{}'.format(repo_name), _config)

        self.assertEqual(repo.createrepo, _DEFAULT_REPO_CMD)
        self.assertEqual(list(repo.consumables.keys()), archs)
        for arch in archs:
            self.assertEqual(repo.consumables[arch].name, repo_name)
            self.assertEqual(
                repo.consumables[arch].url, 'file:///{}/{}'.format(repo_name, arch)
            )
            self.assertEqual(
                repo.rpms_dir(arch), '/{}/{}'.format(repo_name, arch)
            )

    def test_init_rpms_dir(self):
        """ Test LocalRepository rpm_dirs """
        archs = ['x86_64', 'aarch64']
        _config = { 'arch': archs }
        repo_name = 'nowhere'
        path = f"/{repo_name}"
        repo = LocalRepository(path, _config)

        self.assertEqual(repo.rpms_dir(archs[0]), os.path.join(path, archs[0]))
        self.assertEqual(repo.rpms_dir(archs[1]), os.path.join(path, archs[1]))
        with self.assertRaisesRegex(
            RiftError,
            '^Unable to get repository RPM directory for unsupported '
            'architecture fail$'
        ):
            repo.rpms_dir('fail')

    @patch('rift.Repository.Popen')
    def test_create(self, mock_popen):
        """ Test LocalRepository create """
        # Emulate successful createrepo execution
        mock_popen.return_value.__enter__.return_value.returncode = 0
        arch = 'x86_64'
        _config = { 'arch': [arch] }
        repo_name = 'nowhere'
        local_repo_path = make_temp_dir()
        repo = LocalRepository(local_repo_path, _config)
        repo.create()
        self.assertTrue(os.path.exists(repo.srpms_dir))
        self.assertTrue(os.path.exists(repo.rpms_dir(arch)))
        shutil.rmtree(local_repo_path)

    @patch('rift.Repository.Popen')
    def test_create_failure(self, mock_popen):
        """ Test LocalRepository create failure """
        # Emulate createrepo execution failure
        mock_popen.return_value.__enter__.return_value.returncode = 1
        mock_popen.return_value.__enter__.return_value.communicate.return_value = ["output"]
        arch = 'x86_64'
        _config = { 'arch': [arch] }
        repo_name = 'nowhere'
        local_repo_path = make_temp_dir()
        repo = LocalRepository(local_repo_path, _config)
        with self.assertRaisesRegex(RiftError, '^output$'):
            repo.create()
        shutil.rmtree(local_repo_path)

    @patch('rift.Repository.Popen')
    def test_update(self, mock_popen):
        """ Test LocalRepository update """
        # Emulate successful createrepo execution
        mock_popen.return_value.__enter__.return_value.returncode = 0
        arch = 'x86_64'
        _config = { 'arch': [arch] }
        repo_name = 'nowhere'
        local_repo_path = make_temp_dir()
        repo = LocalRepository(local_repo_path, _config)
        repo.create()  # create() calls update()
        # createrepo must have been executed twice, one for SRPMS and the other
        # for x86_64.
        self.assertEqual(mock_popen.call_count, 2)
        # Reset the mock, call update() explicitely and check again.
        mock_popen.reset_mock()
        repo.update()
        self.assertEqual(mock_popen.call_count, 2)
        shutil.rmtree(local_repo_path)

    @patch('rift.Repository.Popen')
    def test_update_failure(self, mock_popen):
        """ Test LocalRepository update failure """
        # Emulate createrepo execution failure
        mock_popen.return_value.__enter__.return_value.returncode = 0
        arch = 'x86_64'
        _config = { 'arch': [arch] }
        repo_name = 'nowhere'
        local_repo_path = make_temp_dir()
        repo = LocalRepository(local_repo_path, _config)
        repo.create()
        mock_popen.return_value.__enter__.return_value.returncode = 1
        mock_popen.return_value.__enter__.return_value.communicate.return_value = ["output"]
        with self.assertRaisesRegex(RiftError, '^output$'):
            repo.update()
        shutil.rmtree(local_repo_path)

    @staticmethod
    def _add_packages(repo):
        """
        Add packages from tests materials to repository and return RPM objects.
        """
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        # Add source and binary packages from tests materials
        src_rpm = RPM(
            os.path.join(tests_dir, 'materials', 'pkg-1.0-1.src.rpm')
        )
        bin_rpm = RPM(
            os.path.join(tests_dir, 'materials', 'pkg-1.0-1.noarch.rpm')
        )
        repo.add(bin_rpm)
        repo.add(src_rpm)

        # Update repository
        repo.update()

        return src_rpm, bin_rpm

    def test_add(self):
        """ Test LocalRepository add """
        archs = ['x86_64', 'aarch64']
        _config = { 'arch': archs }
        repo_name = 'nowhere'
        local_repo_path = make_temp_dir()
        repo = LocalRepository(local_repo_path, _config)

        # Create repository and add packages
        repo.create()
        (src_rpm, bin_rpm) = self._add_packages(repo)

        # Verify packages are present
        for arch in archs:
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        local_repo_path,
                        arch,
                        os.path.basename(bin_rpm.filepath)
                    )
                )
            )
        self.assertTrue(
            os.path.exists(
                os.path.join(
                    local_repo_path, 'SRPMS', os.path.basename(src_rpm.filepath)
                )
            )
        )

        shutil.rmtree(local_repo_path)

    def test_search(self):
        """Test search packages on a repository"""
        archs = ['x86_64', 'aarch64']
        _config = { 'arch': archs }
        local_repo_path = make_temp_dir()
        repo = LocalRepository(local_repo_path, _config)

        # Create repository and add packages
        repo.create()
        (src_rpm, bin_rpm) = self._add_packages(repo)

        # Test multiple search in repository

        # With a package name that does not exist in this repos, it must return
        # 0 result.
        pkgs = repo.search('fail')
        self.assertEqual(len(pkgs), 0)

        # With the name of the package in testing materials, it must return 3
        # results: the source package, the binary package in x86_64 architecture
        # and the same binary package in aarch64 architecture.
        pkgs = repo.search('pkg')
        self.assertEqual(len(pkgs), 3)

        # Verify search results match source and binary packages from tests
        # materials.
        for pkg in pkgs:
            if pkg.is_source:
                self.assertEqual(
                    os.path.basename(pkg.filepath),
                    os.path.basename(src_rpm.filepath)
                )
            else:
                self.assertEqual(
                    os.path.basename(pkg.filepath),
                    os.path.basename(bin_rpm.filepath)
                )

        # Cleanup temporary repository
        shutil.rmtree(local_repo_path)

    def test_delete(self):
        """Test delete packages on a repository"""
        archs = ['x86_64', 'aarch64']
        _config = { 'arch': archs }
        local_repo_path = make_temp_dir()
        repo = LocalRepository(local_repo_path, _config)

        # Create repository and add packages
        repo.create()
        (src_rpm, bin_rpm) = self._add_packages(repo)

        # Search and retrieve packages from repo
        pkgs = repo.search('pkg')

        # Search must return 3 results: the source package, the binary package
        # in x86_64 architecture and the same binary package in aarch64
        # architecture.
        self.assertEqual(len(repo.search('pkg')), 3)

        # Delete packages from repository
        for pkg in pkgs:
            repo.delete(pkg)
        repo.update()

        # Verify packages are absent
        for arch in archs:
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        local_repo_path,
                        arch,
                        os.path.basename(bin_rpm.filepath)
                    )
                )
            )
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    local_repo_path, 'SRPMS', os.path.basename(src_rpm.filepath)
                )
            )
        )

        # Verify search does not return any result
        self.assertEqual(len(repo.search('pkg')), 0)

        # Cleanup temporary repository
        shutil.rmtree(local_repo_path)

class ConsumableRepositoryTest(RiftTestCase):
    """
    Tests class for ConsumableRepository
    """

    def test_path_local_file(self):
        """ test path method """
        directory = '/somewhere'
        repo = ConsumableRepository(directory)
        self.assertEqual(repo.path, directory)
        self.assertTrue(repo.is_file())
        self.assertFalse(repo.exists())

    def test_path_local_file_url(self):
        """ test path method with a local url"""
        directory = '/somewhere'
        repo = ConsumableRepository('file://{}'.format(directory))
        self.assertEqual(repo.path, directory)
        self.assertTrue(repo.is_file())
        self.assertFalse(repo.exists())

    def test_path_remote_url(self):
        """ test path method with a remote url"""
        directory = '/somewhere'
        repo =  ConsumableRepository('http://{}'.format(directory))
        self.assertFalse(repo.is_file())
        with self.assertRaisesRegex(
            RiftError, "^Unable to return path of remote repository$"
        ):
            path = repo.path
        with self.assertRaisesRegex(
            RiftError, "^Unable to return path of remote repository$"
        ):
            repo.exists()

    def test_generic_url(self):
        directory = '/some/where/there'
        repo =  ConsumableRepository('http:/{}'.format(directory))
        self.assertEqual(repo.generic_url('x86_64'), 'http:/{}'.format(directory))
        repo =  ConsumableRepository('http://some/where/x86_64')
        self.assertEqual(repo.generic_url('x86_64'), 'http://some/where/$basearch')

class ProjectArchRepositoriesTest(RiftTestCase):
    """
    Tests class for ProjectArchRepositories
    """
    def setUp(self):
        self.config = Config()

    def test_basic(self):
        """Test one simple supplementary repository"""
        self.config.options['repos'] = {
            'os': {
                'url': 'file:///rift/packages/x86_64/os',
                'priority': 90,
            }
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.working, None)
        self.assertEqual(len(repos.supplementaries), 1)
        self.assertEqual(len(repos.all), 1)
        self.assertEqual(repos.supplementaries[0].name, 'os')
        self.assertEqual(repos.all[0], repos.supplementaries[0])

    def test_working(self):
        """Test working repository without supplementary repository"""
        working_repo_path = make_temp_dir()
        self.config.options['working_repo'] = working_repo_path
        self.config.options['repos'] = {}
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertIsInstance(repos.working, LocalRepository)
        self.assertEqual(len(repos.supplementaries), 0)
        self.assertEqual(len(repos.all), 1)
        self.assertEqual(repos.working.consumables['x86_64'].name, 'working')
        self.assertEqual(repos.working.path, working_repo_path)
        self.assertEqual(repos.all[0], repos.working.consumables['x86_64'])
        shutil.rmtree(working_repo_path)

    def test_working_and_supplementaries(self):
        """Test working repository and two supplementary repositories"""
        working_repo_path = make_temp_dir()
        self.config.options['working_repo'] = working_repo_path
        self.config.options['repos'] = {
            'os': {
                'url': 'file:///rift/packages/x86_64/os',
                'priority': 90,
            },
            'extra': {
                'url': 'file:///rift/packages/x86_64/extra',
                'priority': 90,
            },
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertIsInstance(repos.working, LocalRepository)
        self.assertEqual(len(repos.supplementaries), 2)
        self.assertEqual(len(repos.all), 3)
        self.assertEqual(repos.working.consumables['x86_64'].name, 'working')
        self.assertEqual(repos.supplementaries[0].name, 'os')
        self.assertEqual(repos.all[0], repos.working.consumables['x86_64'])
        self.assertEqual(repos.all[1], repos.supplementaries[0])
        shutil.rmtree(working_repo_path)

    def test_can_publish(self):
        """Test ProjectArchRepositories.can_publish() method"""
        working_repo_path = make_temp_dir()
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertFalse(repos.can_publish())
        self.config.options['working_repo'] = working_repo_path
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertTrue(repos.can_publish())
        shutil.rmtree(working_repo_path)

    def test_working_with_arch(self):
        """Test working repo with $arch placeholder and arch specific value"""
        working_repo_path = make_temp_dir()
        self.config.options['working_repo'] = os.path.join(
                working_repo_path, '$arch'
        )
        self.config.options['repos'] = {}
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertIsInstance(repos.working, LocalRepository)
        self.assertEqual(repos.working.consumables['x86_64'].name, 'working')
        self.assertEqual(
            repos.working.path, os.path.join(working_repo_path, 'x86_64')
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
        self.assertEqual(repos.working.path, other_working_repo_path)
        repos = ProjectArchRepositories(self.config, 'aarch64')
        self.assertEqual(
            repos.working.path, os.path.join(working_repo_path, 'aarch64')
        )
        shutil.rmtree(working_repo_path)
        shutil.rmtree(other_working_repo_path)

    def test_supplementaries_with_arch(self):
        """Test supplementary with $arch placeholder and arch specific value"""
        self.config.options['repos'] = {
            'os': {
                'url': 'file:///rift/packages/$arch/os',
                'priority': 90,
            },
            'extra': {
                'url': 'file:///rift/packages/$arch/extra',
                'priority': 90,
            },
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.supplementaries[0].name, 'os')
        self.assertEqual(
            repos.supplementaries[0].url,
            'file:///rift/packages/x86_64/os'
        )
        self.assertEqual(repos.supplementaries[1].name, 'extra')
        self.assertEqual(
            repos.supplementaries[1].url,
            'file:///rift/packages/x86_64/extra'
        )

        # If an arch specific repos parameter is defined in configuration, it
        # should override generic repos parameter for this arch.

        # Declare supported architectures.
        self.config.options['arch'] = ['x86_64', 'aarch64']
        self.config.options['x86_64'] = {}
        self.config.options['x86_64']['repos'] = {
            'other-os': {
                'url': 'file:///rift/other/packages/os',
                'priority': 90,
            },
            'other-extra': {
                'url': 'file:///rift/other/packages/extra',
                'priority': 90,
            },
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.supplementaries[0].name, 'other-os')
        self.assertEqual(
            repos.supplementaries[0].url,
            'file:///rift/other/packages/os'
        )
        self.assertEqual(repos.supplementaries[1].name, 'other-extra')
        self.assertEqual(
            repos.supplementaries[1].url,
            'file:///rift/other/packages/extra'
        )

        repos = ProjectArchRepositories(self.config, 'aarch64')
        self.assertEqual(repos.supplementaries[0].name, 'os')
        self.assertEqual(
            repos.supplementaries[0].url,
            'file:///rift/packages/aarch64/os'
        )
        self.assertEqual(repos.supplementaries[1].name, 'extra')
        self.assertEqual(
            repos.supplementaries[1].url,
            'file:///rift/packages/aarch64/extra'
        )
