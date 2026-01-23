#
# Copyright (C) 2024 CEA
#

import os
import shutil
from unittest.mock import patch

from TestUtils import RiftTestCase, make_temp_dir
from rift.Config import Config
from rift.Repository import LocalRepository
from rift.RPM import RPM
from rift.sync import (
    RepoSyncFactory,
    RepoSyncBase,
    RepoSyncLftp,
    RepoSyncEpel,
    RepoSyncDnf,
)
from rift import RiftError

class RepoSyncFactoryTest(RiftTestCase):
    """
    Tests class for RepoSyncFactory
    """
    def test_check_valid_method_valid(self):
        """ Test RepoSyncFactory check_valid_method() does not fail with valid value."""
        RepoSyncFactory.check_valid_method('lftp')
        RepoSyncFactory.check_valid_method('epel')

    def test_check_valid_method_invalid_value(self):
        """ Test RepoSyncFactory check_valid_method() raises RiftError with invalid value."""
        with self.assertRaisesRegex(
            RiftError,
            '^Unsupported repository synchronization method fail$'
        ):
            RepoSyncFactory.check_valid_method('fail')

    def test_get(self):
        """ Test RepoSyncFactory get() return instance corresponding to method. """
        sync = {
            'method': 'lftp',
            'source': 'http://repo',
            'include': [],
            'exclude': [],
        }
        self.assertIsInstance(
            RepoSyncFactory.get(Config(), 'repo', '/output', sync), RepoSyncLftp
        )
        sync['method'] = 'epel'
        self.assertIsInstance(
            RepoSyncFactory.get(Config(), 'repo', '/output', sync), RepoSyncEpel
        )


class RepoSyncBaseTest(RiftTestCase):
    """
    Tests class for RepoSyncBase
    """
    def test_run(self):
        """ Test RepoSyncBaseTest synchronization run raises NotImplementedError. """
        sync = {
            'method': 'lftp',
            'source': 'http://repo/directory',
            'include': [],
            'exclude': [],
        }
        output = make_temp_dir()
        synchronizer = RepoSyncBase(Config(), 'repo', output, sync)
        with self.assertRaises(NotImplementedError):
            synchronizer.run()
        shutil.rmtree(output)


class RepoSyncLftpTest(RiftTestCase):
    """
    Tests class for RepoSyncLftp
    """
    def setUp(self):
        # Create temporary directory to store local mirror of remote repository
        self.output = make_temp_dir()
        self.config = Config()

    def tearDown(self):
        # Remove temporary directory with local mirror
        shutil.rmtree(self.output)

    @patch('subprocess.run')
    def test_run(self, mock_subprocess_run):
        """ Test RepoSyncLftpTest synchronization run. """
        sync = {
            'method': 'lftp',
            'source': 'http://repo/directory',
            'include': [],
            'exclude': [],
        }
        synchronizer = RepoSyncLftp(self.config, 'repo', self.output, sync)
        synchronizer.run()
        mock_subprocess_run.assert_called_once()
        args = mock_subprocess_run.call_args[0]
        self.assertEqual(args[0][0], 'lftp')
        self.assertEqual(args[0][1], 'http://repo')
        self.assertTrue(f"--log {self.output}/sync_repo_" in args[0][3])
        self.assertTrue(f"/directory/ {self.output}/repo" in args[0][3])
        self.assertFalse("--include" in args[0][3])
        self.assertFalse("--exclude" in args[0][3])

    @patch('subprocess.run')
    def test_run_with_include_exclude(self, mock_subprocess_run):
        """ Test RepoSyncLftpTest synchronization run with include/exclude. """
        sync = {
            'method': 'lftp',
            'source': 'http://repo/directory',
            'include': [ 'include1', 'include2'],
            'exclude': [ 'exclude1', 'exclude2'],
        }
        synchronizer = RepoSyncLftp(self.config, 'repo', self.output, sync)
        synchronizer.run()
        mock_subprocess_run.assert_called_once()
        args = mock_subprocess_run.call_args[0]
        self.assertTrue("--include=include1" in args[0][3])
        self.assertTrue("--include=include2" in args[0][3])
        self.assertTrue("--exclude=exclude1" in args[0][3])
        self.assertTrue("--exclude=exclude2" in args[0][3])

class RepoSyncEpelTest(RiftTestCase):
    """
    Tests class for RepoSyncEpel
    """
    def setUp(self):
        self.config = Config()
        # Create temporary directory to store fake EPEL repository, set it as
        # PUB_ROOT class attribute and keep reference to previous value.
        self.fake_epel_dir = make_temp_dir()
        self.pub_root_backup = RepoSyncEpel.PUB_ROOT
        RepoSyncEpel.PUB_ROOT = self.fake_epel_dir
        # Create temporary directory to store local mirror of remote repository
        self.output = make_temp_dir()

    def tearDown(self):
        # Restore previous value of PUB_ROOT class attribute and remove
        # temporary directory.
        RepoSyncEpel.PUB_ROOT = self.pub_root_backup
        shutil.rmtree(self.fake_epel_dir)
        # Remove temporary directory with local mirror
        shutil.rmtree(self.output)

    def _init_fake_epel_repo(self, content):
        with open(
            os.path.join(self.fake_epel_dir, 'fullfiletimelist-epel'), 'w+'
        ) as fh:
            fh.write("[Files]\n")
            for repo, dirs in content.items():
                fh.write(f"1\td\t0\t{repo}\n")
                for _dir, items in dirs.items():
                    fh.write(f"1\td\t0\t{repo}/{_dir}\n")
                    for item in items:
                        fh.write(
                            f"{item[0]}\t{item[1]}\t0\t"
                            f"{repo}/{_dir}/{item[2]}\n"
                        )

        for repo, dirs in content.items():
            os.mkdir(os.path.join(self.fake_epel_dir, repo))
            for _dir, items in dirs.items():
                os.mkdir(os.path.join(self.fake_epel_dir, repo, _dir))
                for item in items:
                    open(
                        os.path.join(
                            self.fake_epel_dir, repo, _dir, item[2]
                        ), 'w+'
                    ).close()

    def test_run(self):
        """ Test RepoSyncEpelTest synchronization run. """
        self._init_fake_epel_repo({
            'repo1': {
                'p': [
                    (1, 'f', 'package1.rpm'),
                    (1, 'l', 'package2.rpm'),
                ],
            },
            'repo2': {
                'p': [
                    (1, 'f', 'package3.rpm'),
                ],
            },
        })
        sync = {
            'method': 'epel',
            'source': f"file://{self.fake_epel_dir}/repo1",
            'include': [],
            'exclude': [],
        }
        synchronizer = RepoSyncEpel(self.config, 'repo', self.output, sync)
        synchronizer.run()
        self.assertTrue(os.path.isdir(os.path.join(self.output, 'repo', 'p')))
        # File package1.rpm in repo1 must be present
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.output, 'repo', 'p', 'package1.rpm')
            )
        )
        # File declared as symlink in repo1 must not be present
        self.assertFalse(
            os.path.exists(
                os.path.join(self.output, 'repo', 'p', 'package2.rpm')
            )
        )
        # File in repo2 must not be present
        self.assertFalse(
            os.path.exists(
                os.path.join(self.output, 'repo', 'p', 'package3.rpm')
            )
        )

    def test_include_exclude(self):
        """ Test RepoSyncEpelTest synchronization run with include/exclude. """
        self._init_fake_epel_repo({
            'repo1': {
                'e': [
                    (1, 'f', 'exclude1.rpm'),
                    (1, 'f', 'exclude2.rpm'),
                ],
                'o': [
                    (1, 'f', 'other1.rpm'),
                    (1, 'f', 'other2.rpm'),
                ],
                'p': [
                    (1, 'f', 'package1.rpm'),
                    (1, 'f', 'package2.rpm'),
                ],
            },
        })
        sync = {
            'method': 'epel',
            'source': f"file://{self.fake_epel_dir}/repo1",
            'include': [
                '^o/',
                '^p/'
            ],
            'exclude': [
                '/other2.rpm$',
            ],
        }
        synchronizer = RepoSyncEpel(self.config, 'repo', self.output, sync)
        synchronizer.run()
        self.assertTrue(os.path.isdir(os.path.join(self.output, 'repo', 'o')))
        self.assertTrue(os.path.isdir(os.path.join(self.output, 'repo', 'p')))
        # All files in e/* are not included
        self.assertFalse(os.path.exists(os.path.join(self.output, 'repo', 'e')))
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.output, 'repo', 'p', 'package1.rpm')
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.output, 'repo', 'p', 'package2.rpm')
            )
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.output, 'repo', 'o', 'other1.rpm'))
        )
        # Package other2.rpm is excluded
        self.assertFalse(
            os.path.exists(os.path.join(self.output, 'repo', 'o', 'other2.rpm'))
        )

    def test_update(self):
        """ Test RepoSyncEpelTest synchronization update packages based on timestamp. """
        self._init_fake_epel_repo({
            'repo1': {
                'p': [
                    (1, 'f', 'package1.rpm'),
                    (2**32, 'f', 'package2.rpm'),
                ],
            },
        })
        sync = {
            'method': 'epel',
            'source': f"file://{self.fake_epel_dir}/repo1",
            'include': [],
            'exclude': [],
        }
        os.mkdir(os.path.join(self.output, 'repo'))
        os.mkdir(os.path.join(self.output, 'repo', 'p'))
        with open(
            os.path.join(self.output, 'repo', 'p', 'package1.rpm'), 'w+'
        ) as fh:
            fh.write("content1")
        with open(
            os.path.join(self.output, 'repo', 'p', 'package2.rpm'), 'w+'
        ) as fh:
            fh.write("content2")
        synchronizer = RepoSyncEpel(self.config, 'repo', self.output, sync)
        synchronizer.run()
        self.assertFalse(
            os.path.isdir(os.path.join(self.output, 'repo', 'outside'))
        )
        # package1 must not be updated (with content unchanged) as mtime on FS
        # is younger than timestamp in files index.
        self.assertEqual(
            open(os.path.join(self.output, 'repo', 'p', 'package1.rpm')).read(),
            "content1"
        )
        # package2 must be updated (with content removed) as mtime on FS is
        # older than timestamp in files index
        self.assertEqual(
            open(os.path.join(self.output, 'repo', 'p', 'package2.rpm')).read(),
            ""
        )

    def test_clean(self):
        """ Test RepoSyncEpelTest synchronization clean unindexed files and directories. """
        self._init_fake_epel_repo({
            'repo1': {
                'p': [
                    (1, 'f', 'package1.rpm'),
                    (1, 'f', 'package2.rpm'),
                ],
            },
        })
        sync = {
            'method': 'epel',
            'source': f"file://{self.fake_epel_dir}/repo1",
            'include': [],
            'exclude': [],
        }
        os.mkdir(os.path.join(self.output, 'repo'))
        os.mkdir(os.path.join(self.output, 'repo', 'outside'))
        os.mkdir(os.path.join(self.output, 'repo', 'p'))
        open(
            os.path.join(self.output, 'repo', 'p', 'package3.rpm'), 'w+'
        ).close()
        synchronizer = RepoSyncEpel(self.config, 'repo', self.output, sync)
        synchronizer.run()
        self.assertFalse(
            os.path.isdir(os.path.join(self.output, 'repo', 'outside'))
        )
        # File package1.rpm in repo1 must be present
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.output, 'repo', 'p', 'package1.rpm')
            )
        )
        # File declared as symlink in repo1 must not be present
        self.assertTrue(
            os.path.exists(
                os.path.join(self.output, 'repo', 'p', 'package2.rpm')
            )
        )
        # File in repo2 must not be present
        self.assertFalse(
            os.path.exists(
                os.path.join(self.output, 'repo', 'p', 'package3.rpm')
            )
        )

    def test_wrong_url(self):
        """ Test RepoSyncEpelTest synchronization raises RiftError with wrong URLs. """
        sync = {
            'method': 'epel',
            'source': 'https://127.0.0.1/fail',
            'include': [],
            'exclude': [],
        }
        synchronizer = RepoSyncEpel(self.config, 'repo', self.output, sync)
        with self.assertRaisesRegex(
            RiftError,
            r"^URL error while downloading https://127.0.0.1/.*: .*$",
        ):
            synchronizer.run()
        sync['source'] =  'https://google.com/failure'
        synchronizer = RepoSyncEpel(self.config, 'repo', self.output, sync)
        with self.assertRaisesRegex(
            RiftError,
            r"^HTTP error while downloading https://google.com/.*: "
            "HTTP Error 404: Not Found$",
        ):
            synchronizer.run()

class RepoSyncDnfTest(RiftTestCase):
    """
    Tests class for RepoSyncDnf
    """
    def setUp(self):
        self.config = Config()
        self.arch = self.config.get('arch')[0]
        # Create temporary directory to store fake DNF repository.
        self.fake_dnf_repo = make_temp_dir()
        # Create repository
        repo = LocalRepository(self.fake_dnf_repo, self.config)
        repo.create()
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        # Add source and binary packages from tests materials
        self.src_rpm = RPM(
            os.path.join(tests_dir, 'materials', 'pkg-1.0-1.src.rpm')
        )
        self.bin_rpm = RPM(
            os.path.join(tests_dir, 'materials', 'pkg-1.0-1.noarch.rpm')
        )
        repo.add(self.bin_rpm)
        repo.add(self.src_rpm)
        # Update repository
        repo.update()
        # Create temporary directory to store local mirror of remote repository
        self.output = make_temp_dir()

    def tearDown(self):
        # Remove fake DNF repository
        shutil.rmtree(self.fake_dnf_repo)
        # Remove temporary directory with local mirror
        shutil.rmtree(self.output)

    def test_run(self):
        """ Test RepoSyncDnfTest synchronization run. """
        sync = {
            'method': 'dnf',
            'source': f"file://{self.fake_dnf_repo}",
            'subdir': self.arch,
            'include': [],
            'exclude': [],
        }
        repo_name = 'repo'
        synchronizer = RepoSyncDnf(self.config, repo_name, self.output, sync)
        synchronizer.run()
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.output,
                    repo_name,
                    self.arch,
                    os.path.basename(self.bin_rpm.filepath)
                )
            )
        )
        self.assertTrue(
            os.path.isdir(
                os.path.join(self.output, repo_name, self.arch, 'repodata')
            )
        )

    def test_include_exclude(self):
        """ Test RepoSyncDnfTest synchronization run with include/exclude. """
        # First test without exclude pattern but with an include pattern that
        # does not match any package. The binary package must not be
        # synchronized (because it does not match include pattern).
        sync = {
            'method': 'dnf',
            'source': f"file://{self.fake_dnf_repo}",
            'subdir': self.arch,
            'include': [
                r"fail",
            ],
            'exclude': [],
        }
        repo_name = 'repo'
        bin_pkg_path = os.path.join(
            self.output,
            repo_name,
            self.arch,
            os.path.basename(self.bin_rpm.filepath)
        )
        synchronizer = RepoSyncDnf(self.config, repo_name, self.output, sync)
        synchronizer.run()
        self.assertFalse(os.path.exists(bin_pkg_path))
        # Then test without exclude pattern but with an include pattern that
        # matches the binary package name. The binary package must be
        # synchronized.
        sync['include'] = [os.path.basename(self.bin_rpm.filepath)]
        synchronizer = RepoSyncDnf(self.config, repo_name, self.output, sync)
        synchronizer.run()
        self.assertTrue(os.path.isfile(bin_pkg_path))
        # Finally test without include pattern but with an exclude pattern that
        # matches the binary package name. The binary package must be removed.
        sync['include'] = []
        sync['exclude'] = [ r"^pkg-\d" ]
        synchronizer = RepoSyncDnf(self.config, repo_name, self.output, sync)
        synchronizer.run()
        self.assertFalse(os.path.exists(bin_pkg_path))

    def test_skip_downloaded(self):
        """ Test RepoSyncDnfTest skip already downloaded packages. """
        # First test without exclude pattern but with an include pattern that
        # does not match any package. The binary package must not be
        # synchronized (because it does not match include pattern).
        sync = {
            'method': 'dnf',
            'source': f"file://{self.fake_dnf_repo}",
            'subdir': self.arch,
            'include': [],
            'exclude': [],
        }
        repo_name = 'repo'
        bin_pkg_path = os.path.join(
            self.output,
            repo_name,
            self.arch,
            os.path.basename(self.bin_rpm.filepath)
        )
        synchronizer = RepoSyncDnf(self.config, repo_name, self.output, sync)
        # Create empty file to simulate package presence
        os.makedirs(os.path.dirname(bin_pkg_path))
        open(bin_pkg_path, 'w+').close()
        # Check debug log to indicate skipped file is emited
        with self.assertLogs(level='DEBUG') as log:
            synchronizer.run()
            self.assertIn(
                f"DEBUG:root:Ignoring existing file {bin_pkg_path}", log.output
            )

    def test_wrong_url(self):
        """ Test RepoSyncDnfTest synchronization raises RiftError with wrong URLs. """
        sync = {
            'method': 'dnf',
            'source': 'https://127.0.0.1/fail',
            'include': [],
            'exclude': [],
        }
        synchronizer = RepoSyncDnf(self.config, 'repo', self.output, sync)
        with self.assertRaisesRegex(
            RiftError,
            r"^Unable to download repository metadata from URL "
            r"https://127.0.0.1/fail/:.*",
        ):
            synchronizer.run()
