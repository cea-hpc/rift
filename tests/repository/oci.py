#
# Copyright (C) 2025 CEA
#

import os
import shutil

from rift.repository.oci import ArchRepositoriesOCI

from ..TestUtils import RiftProjectTestCase, make_temp_dir


class ArchRepositoriesOCITest(RiftProjectTestCase):

    def test_init(self):
        repo = ArchRepositoriesOCI(self.config, None, 'x86_64')
        self.assertIsNone(repo.path)
        self.assertIsNone(repo.working_dir)
        self.assertEqual(repo.arch, 'x86_64')

    def test_init_working(self):
        working_repo_path = make_temp_dir()
        repo = ArchRepositoriesOCI(self.config, working_repo_path, 'x86_64')
        self.assertEqual(repo.path, os.path.join(working_repo_path, 'oci'))
        self.assertEqual(repo.working_dir, working_repo_path)
        self.assertEqual(repo.arch, 'x86_64')
        shutil.rmtree(working_repo_path)

    def test_ensure_created(self):
        working_repo_path = make_temp_dir()
        os.rmdir(working_repo_path)
        repo = ArchRepositoriesOCI(self.config, working_repo_path, 'x86_64')
        self.assertFalse(os.path.exists(repo.working_dir))
        with self.assertLogs(level='DEBUG') as log:
            repo.ensure_created()
        self.assertIn(
            f"DEBUG:root:Creating working directory {working_repo_path}",
            log.output
        )
        self.assertIn(
            f"DEBUG:root:Creating oci repository directory {working_repo_path}/oci",
            log.output
        )
        self.assertTrue(os.path.exists(repo.working_dir))
        self.assertTrue(os.path.exists(repo.path))
        shutil.rmtree(working_repo_path)

    def test_delete_matching(self):
        working_repo_path = make_temp_dir()
        repo = ArchRepositoriesOCI(self.config, working_repo_path, 'x86_64')
        repo.ensure_created()
        open(f"{repo.path}/pkg_1.0-2.x86_64.tar", 'w+').close()
        open(f"{repo.path}/pkg_1.0-2.aarch64.tar", 'w+').close()
        open(f"{repo.path}/other-pkg_2.0-3.x86_64.tar", 'w+').close()
        open(f"{repo.path}/other-pkg_2.0-3.aarch64.tar", 'w+').close()
        with self.assertLogs(level='INFO') as log:
            repo.delete_matching('pkg')
        self.assertIn(
            f"INFO:root:Deleting OCI image {repo.path}/pkg_1.0-2.x86_64.tar",
            log.output
        )
        self.assertFalse(os.path.exists(f"{repo.path}/pkg_1.0-2.x86_64.tar"))
        self.assertTrue(os.path.exists(f"{repo.path}/pkg_1.0-2.aarch64.tar"))
        self.assertTrue(os.path.exists(f"{repo.path}/other-pkg_2.0-3.x86_64.tar"))
        self.assertTrue(os.path.exists(f"{repo.path}/other-pkg_2.0-3.aarch64.tar"))
        shutil.rmtree(working_repo_path)

    def test_delete_matching_other_arch(self):
        working_repo_path = make_temp_dir()
        repo = ArchRepositoriesOCI(self.config, working_repo_path, 'aarch64')
        repo.ensure_created()
        open(f"{repo.path}/pkg_1.0-2.x86_64.tar", 'w+').close()
        open(f"{repo.path}/pkg_1.0-2.aarch64.tar", 'w+').close()
        open(f"{repo.path}/other-pkg_2.0-3.x86_64.tar", 'w+').close()
        open(f"{repo.path}/other-pkg_2.0-3.aarch64.tar", 'w+').close()
        with self.assertLogs(level='INFO') as log:
            repo.delete_matching('other-pkg')
        self.assertIn(
            f"INFO:root:Deleting OCI image {repo.path}/other-pkg_2.0-3.aarch64.tar",
            log.output
        )
        self.assertTrue(os.path.exists(f"{repo.path}/pkg_1.0-2.x86_64.tar"))
        self.assertTrue(os.path.exists(f"{repo.path}/pkg_1.0-2.aarch64.tar"))
        self.assertTrue(os.path.exists(f"{repo.path}/other-pkg_2.0-3.x86_64.tar"))
        self.assertFalse(os.path.exists(f"{repo.path}/other-pkg_2.0-3.aarch64.tar"))
        shutil.rmtree(working_repo_path)
