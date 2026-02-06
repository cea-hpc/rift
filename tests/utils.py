#
# Copyright (C) 2025 CEA
#

from io import StringIO
from unittest.mock import patch, Mock

from rift import RiftError
from rift.utils import message, banner, last_modified
from .TestUtils import RiftTestCase


class UtilsTest(RiftTestCase):

    @patch('sys.stdout', new_callable=StringIO)
    def test_message(self, mock_stdout):
        message("foo")
        self.assertEqual(mock_stdout.getvalue(), "> foo\n")

    @patch('sys.stdout', new_callable=StringIO)
    def test_banner(self, mock_stdout):
        banner("bar")
        self.assertEqual(mock_stdout.getvalue(), "** bar **\n")

    @patch('urllib.request.urlopen')
    def test_last_modified(self, mock_urlopen):
        mock_response = Mock()
        mock_response.getheader.return_value = "Sat, 1 Jan 2000 00:00:00 GMT"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        self.assertEqual(last_modified("http://test"), 946684800)

    @patch('urllib.request.urlopen')
    def test_last_modified_header_not_found(self, mock_urlopen):
        mock_response = Mock()
        mock_response.getheader.return_value = None
        mock_urlopen.return_value.__enter__.return_value = mock_response
        with self.assertRaisesRegex(
            RiftError, "^Unable to get Last-Modified header for URL http://test$"
        ):
            last_modified("http://test")

    @patch('urllib.request.urlopen')
    def test_last_modified_header_conversion_error(self, mock_urlopen):
        mock_response = Mock()
        mock_response.getheader.return_value = "Sat, 1 Jan 2000 00:00:00"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        with self.assertRaisesRegex(
            RiftError,
            "^Unable to convert Last-Modified header to datetime for URL http://test$"
        ):
            last_modified("http://test")

    def test_last_modified_url_error(self):
        with self.assertRaisesRegex(
            RiftError,
            "^Unable to send HTTP HEAD request for URL http://localhost: .*$"
        ):
            last_modified("http://localhost")
