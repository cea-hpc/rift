#
# Copyright (C) 2024 CEA
#

import os
import shutil
import tarfile
import textwrap
import time
from unittest.mock import patch

from rift.annex import Annex
from rift.annex.utils import (
    get_digest_from_path,
    get_info_from_digest,
    hashfile,
)
from rift.Config import Config, Modules, Staff
from rift.package import ProjectPackages
from rift.package.rpm import PackageRPM

from ..TestUtils import (
    RiftTestCase,
    gen_rpm_spec,
    make_temp_file,
    make_temp_filename,
    read_file,
)

_TEST_ANNEX_PATH = '/tmp/rift-test-annex'


class AnnexTest(RiftTestCase):

    """
    Test class for the Rift Annex
    """

    def setUp(self):
        # Create a minimal project configuration
        self.config = Config()
        self.config.project_dir = '/tmp/rift-working-repo'
        # Create the working repo
        self.working_repo = '/tmp/rift-working-repo'
        os.mkdir(self.working_repo)
        os.mkdir(self.working_repo + '/packages')

        self.staff = Staff(config=self.config)
        self.staff_file = make_temp_file(textwrap.dedent("""
        staff:
            'J. Doe':
                email: 'j.doe@rift.org'
        """))

        self.staff.load(self.staff_file.name)
        self.config_file = make_temp_file(textwrap.dedent("""
        modules:
            'Tools':
                manager: 'J. Doe'
        """))
        self.modules = Modules(config=self.config, staff=self.staff)
        self.modules.load(self.config_file.name)

        # Create a Annex for the tests
        os.mkdir(_TEST_ANNEX_PATH)
        self.config.set(
            'set_annex',
            {
                'address': _TEST_ANNEX_PATH,
                'type': 'directory',
            },
        )
        self.annex = Annex(self.config)

        self.source = make_temp_file(textwrap.dedent("""
        This file is an annex test
        """))

        self.source_digest = hashfile(self.source.name)
        self.source_pointer = make_temp_file(self.source_digest)

        # Create a mock package in the working repo
        self.package_infos = make_temp_file(textwrap.dedent("""
        package:
           maintainers:
           - J. Doe
           module: Tools
           reason: Missing package
           origin: Company
        """))
        self.package = PackageRPM('foo-pkg', self.config, self.staff, self.modules)
        self.package.load_info(infopath=self.package_infos.name)
        self.package.write()
        with open(self.package.buildfile, "w") as fh:
            fh.write(
                gen_rpm_spec(
                    name='foo-pkg',
                    version="1.0",
                    release="1",
                    arch="x86_64",
                )
            )

    def tearDown(self):
        # Remove the Annex and the working repo created for the tests
        shutil.rmtree('/tmp/rift-test-annex')
        shutil.rmtree(self.working_repo)

    def test_init(self):
        """ Test local annex initialisation """

        self.assertEqual(self.annex.set_annex.annex_path, _TEST_ANNEX_PATH)

    def test_get(self):
        """ Test get method """

        self.annex.push(self.source.name)
        dest = make_temp_filename()
        self.annex.get(self.source_digest, dest)

        # Compute hash to be sure we get the same file
        self.assertEqual(hashfile(dest), self.source_digest)

    def test_get_by_path(self):
        """ Test get_by_path method """

        self.annex.push(self.source.name)
        dest = make_temp_filename()
        self.annex.get_by_path(self.source_pointer.name, dest)

        # Compute hash to be sure we get the same file
        self.assertEqual(hashfile(dest), self.source_digest)

    def test_delete(self):
        """ Test delete method """

        # We can not use tempfile in this test
        # because even if we delete the file
        # tempfile will try to delete it again
        # raising an exception
        source_file = make_temp_file('Rift Annex Test', delete=False)

        # Push the file into the Annex and retrieve the digest (pointer)
        self.annex.push(source_file.name)
        file_pointer = get_digest_from_path(source_file.name)
        self.annex.delete(file_pointer)

        # Check if the file is not present in the Annex
        with self.assertRaises(FileNotFoundError):
            self.annex.get_by_path(source_file.name, '/dev/null')

    def test_list(self):
        """Test the list method"""

        source_size = os.stat(self.source.name).st_size
        source_insertion_time = time.time()
        self.annex.push(self.source.name)

        for filename, size, insertion_time, names in self.annex.list():
            self.assertEqual(get_digest_from_path(self.source.name), filename)
            self.assertEqual(source_size, size)
            self.assertAlmostEqual(source_insertion_time, insertion_time, delta=1) # delta for potentials delay
        self.assertTrue(os.path.basename(self.source.name) in names)

    def test_push(self):
        """ Test push method """

        # Push the file into the annex
        self.annex.push(self.source.name)
        digest_path = os.path.join(self.annex.set_annex.annex_path, self.source_digest)

        # Check if the file is correctly created
        # and pushed into the annex
        self.assertTrue(os.path.exists(digest_path))
        self.assertTrue(os.path.exists(os.path.join(
            self.annex.set_annex.annex_path,
            get_info_from_digest(self.source_digest))
        ))

        self.assertEqual(hashfile(digest_path), self.source_digest)

    def test_annex_backup(self):
        """ Test the Annex backup method """

        os.mkdir(self.package.sourcesdir)
        pkg_src_file = self.package.sourcesdir + '/src.tar'
        with open(pkg_src_file, 'wb') as source_file:
            source_file.write(os.urandom(4096 * 8))

        # Push this file into the annex
        self.annex.push(pkg_src_file)

        # Generate another file, not related to a package
        orphaned_file = make_temp_file('Rift Annex Test (Backup')
        self.annex.push(orphaned_file.name)

        # Backup the annex
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            annex_backup = self.annex.backup(
                ProjectPackages.list(self.config, self.staff, self.modules)
            )

        # Get the files present in the annex backup
        with tarfile.open(annex_backup, 'r') as backup:
            annexed_files = [f.name for f in backup.getmembers()]

        # Check if the package-1 files are present in the archive
        self.assertTrue(get_digest_from_path(pkg_src_file) in annexed_files)
        self.assertTrue(
            get_info_from_digest(get_digest_from_path(pkg_src_file))
            in annexed_files
        )

        # Check if the orphaned file is not in the archive
        self.assertTrue(get_digest_from_path(orphaned_file.name) not in annexed_files)
        self.assertTrue(
            get_info_from_digest(get_digest_from_path(orphaned_file.name))
            not in annexed_files
        )

        os.remove(annex_backup)
