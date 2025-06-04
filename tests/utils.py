#
# Copyright (C) 2025 CEA
#

from io import StringIO
from unittest.mock import patch

from TestUtils import RiftTestCase
from rift.utils import message, banner

class UtilsTest(RiftTestCase):

    @patch('sys.stdout', new_callable=StringIO)
    def test_message(self, mock_stdout):
        message("foo")
        self.assertEqual(mock_stdout.getvalue(), "> foo\n")

    @patch('sys.stdout', new_callable=StringIO)
    def test_banner(self, mock_stdout):
        banner("bar")
        self.assertEqual(mock_stdout.getvalue(), "** bar **\n")
