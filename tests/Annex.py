#
# Copyright (C) 2024 CEA
#

import datetime
import os
import time
import shutil
import tarfile
import textwrap

from rift.Annex import *
from rift.Config import Config, Staff, Modules
from rift.Package import _SOURCES_DIR, _DOC_FILES, _META_FILE, _TESTS_DIR, Package

from TestUtils import make_temp_file, make_temp_filename, make_temp_dir, RiftTestCase

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

        self.staff = Staff(config = self.config)
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
        self.modules = Modules(config = self.config, staff = self.staff)
        self.modules.load(self.config_file.name)

        # Create a Annex for the tests
        os.mkdir(_TEST_ANNEX_PATH)
        self.config.annex = _TEST_ANNEX_PATH
        self.annex = Annex(self.config, annex_path=_TEST_ANNEX_PATH)

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

        self.package = Package('foo-pkg', self.config, self.staff, self.modules)
        self.package.load(infopath = self.package_infos.name)
        self.package.check_info()
        self.package.write()

    def tearDown(self):
        # Remove the Annex and the working repo created for the tests
        shutil.rmtree('/tmp/rift-test-annex')
        shutil.rmtree(self.working_repo)

    def test_is_binary_with_binary(self):
        """
        Test is a fully binary file is correctly
        detected as binary file
        """
        # Generate a random fully binary file*
        # make_temp_file from test_utils cant be used
        # here since it does not support binary content
        with open('/tmp/binary_file', 'wb') as bin_file:
            bin_file.write(os.urandom(4096 * 8))

        self.assertTrue(is_binary('/tmp/binary_file'))
        os.remove('/tmp/binary_file')

    def test_is_binary_with_non_binary(self):
        """
        Test if a fully non binary file is correctly detected as an non binary file
        """

        non_binary_file = make_temp_file('ACTG' * 40)
        self.assertFalse(is_binary(non_binary_file.name))

    def test_is_binary_with_empty_file(self):
         """
         Test if an empty is correctly detected by is_binary
         """

         empty_file = make_temp_file('')
         self.assertFalse(is_binary(empty_file.name))

    def test_get_digest_from_path(self):
        """
        Test if a file is able to be readed by this method
        """

        file_content = 'Red Hat Enterprise Linux release 8.8 (Ootpa)'
        file_path = make_temp_file(file_content)
        self.assertEqual(file_content, get_digest_from_path(file_path.name))

    def test_get_info_from_digest(self):
        """
        Test the concetenation between the digest and the metadata suffix
        """

        digest = '7CF2DB5EC261A0FA27A502D3196A6F60'
        self.assertEqual(digest + '.info', get_info_from_digest(digest))

    def test_hashfile(self):
        """ Test if the hashfile method hash the filepath correctly """

        path = make_temp_file('OCEAN')
        self.assertNotEqual(path.name, hashfile(path.name))

    def test_init(self):
        """ Test local annex initialisation """

        self.assertEqual(self.annex.annex_path, _TEST_ANNEX_PATH)

    def test_is_pointer_valid_identifier(self):
        """ Test if is_pointer correctly detect a valid identifier """

        correct_identifier = '7CF2DB5EC261A0FA27A502D3196A6F60'
        temp_file = make_temp_file(correct_identifier)
        self.assertTrue(Annex.is_pointer(temp_file.name))

    def test_is_pointer_valid_identifier_with_line_feed(self):
        """ Test if is_pointer correctly detect a valid identifier with a line feed """

        correct_identifier = '7CF2DB5EC261A0FA27A502D3196A6F60\n'
        temp_file = make_temp_file(correct_identifier)
        self.assertTrue(Annex.is_pointer(temp_file.name))

    def test_is_pointer_valid_identifier_with_carriage_return(self):
        """
        Test if is_pointer correctly detect a valid identifier with a carriage return.
        """

        correct_identifier = '7CF2DB5EC261A0FA27A502D3196A6F60\r\n'
        temp_file = make_temp_file(correct_identifier)
        self.assertTrue(Annex.is_pointer(temp_file.name))

    def test_is_pointer_invalid_identifier(self):
        """ Test if is_pointer correctly detect a invalid identifier """

        incorrect_identifier = 'rift annex test'
        temp_file = make_temp_file(incorrect_identifier)
        self.assertFalse(Annex.is_pointer(temp_file.name))

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
        digest_path = os.path.join(self.annex.annex_path, self.source_digest)

        # Check if the file is correctly created
        # and pushed into the annex
        self.assertTrue(os.path.exists(digest_path))
        self.assertTrue(os.path.exists(os.path.join(
            self.annex.annex_path,
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
        annex_backup = self.annex.backup(Package.list(self.config, self.staff, self.modules))

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
        self.assertTrue(get_digest_from_path(orphaned_file.name)  not in annexed_files)
        self.assertTrue(
            get_info_from_digest(get_digest_from_path(orphaned_file.name))
            not in annexed_files
        )

        os.remove(annex_backup)

