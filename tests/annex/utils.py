#
# Copyright (C) 2026 CEA
#

import os

from rift.annex.utils import (
    get_digest_from_path,
    get_info_from_digest,
    hashfile,
    is_binary,
    is_pointer,
)

from ..TestUtils import RiftTestCase, make_temp_file


class AnnexUtilsTest(RiftTestCase):
    """Tests for rift.annex.utils helpers."""

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

    def test_is_pointer_valid_identifier(self):
        """ Test if is_pointer correctly detect a valid identifier """

        correct_identifier = '7CF2DB5EC261A0FA27A502D3196A6F60'
        temp_file = make_temp_file(correct_identifier)
        self.assertTrue(is_pointer(temp_file.name))

    def test_is_pointer_valid_identifier_with_line_feed(self):
        """ Test if is_pointer correctly detect a valid identifier with a line feed """

        correct_identifier = '7CF2DB5EC261A0FA27A502D3196A6F60\n'
        temp_file = make_temp_file(correct_identifier)
        self.assertTrue(is_pointer(temp_file.name))

    def test_is_pointer_valid_identifier_with_carriage_return(self):
        """
        Test if is_pointer correctly detect a valid identifier with a carriage return.
        """

        correct_identifier = '7CF2DB5EC261A0FA27A502D3196A6F60\r\n'
        temp_file = make_temp_file(correct_identifier)
        self.assertTrue(is_pointer(temp_file.name))

    def test_is_pointer_valid_identifier_with_whitespace(self):
        """
        Test if is_pointer correctly detect a valid identifier with a whitespace.
        """

        correct_identifier = '7CF2DB5EC261A0FA27A502D3196A6F60 '
        temp_file = make_temp_file(correct_identifier)
        self.assertTrue(is_pointer(temp_file.name))

    def test_is_pointer_invalid_identifier(self):
        """ Test if is_pointer correctly detect a invalid identifier """

        incorrect_identifier = 'rift annex test'
        temp_file = make_temp_file(incorrect_identifier)
        self.assertFalse(is_pointer(temp_file.name))
