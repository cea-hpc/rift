#
# Copyright (C) 2025 CEA
#

from io import StringIO, BytesIO
from unittest.mock import patch, Mock, call, MagicMock
import os
import urllib.error

from rift import RiftError
from rift.utils import message, banner, download_file, last_modified
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

    def test_download_file(self):
        download_file("file:///etc/hosts", "/tmp/blob", 40000)
        self.assert_file_exists("/tmp/blob")
        os.remove("/tmp/blob")

    @patch('urllib.request.urlopen')
    def test_download_file_bearer_token(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = BytesIO(b'x')
        download_file('https://test', '/tmp/blob', bearer_token='tok')
        # Check that Authorization header is set
        req = mock_urlopen.call_args[0][0]
        hdrs = dict(req.header_items())
        self.assertEqual(hdrs.get('Authorization'), 'Bearer tok')
        os.remove('/tmp/blob')

    @patch('urllib.request.urlopen')
    def test_download_file_too_large(self, mock_urlopen):
        mock_url = Mock()
        mock_url.info.return_value = {
            "Content-Length": "50"
        }
        mock_urlopen.return_value.__enter__.return_value = mock_url
        with self.assertRaisesRegex(
                RiftError,
                "'https://test' has a size of '50' bytes, larger than "
                "max size '20', skipping download"
        ):
            download_file("https://test", "/tmp/blob", 20)

    def test_download_file_url_error(self):
        with self.assertRaisesRegex(
                RiftError,
                "Error while downloading blob:localhost: "
                "<urlopen error unknown url type: blob>"
        ):
            download_file("blob:localhost", "/tmp/blob")

    @patch('rift.utils.time.sleep')
    @patch('urllib.request.urlopen')
    def test_download_file_retries_success(self, mock_urlopen, mock_sleep):
        url = 'https://example.test/file'

        open_cm = MagicMock()
        open_cm.__enter__.return_value = BytesIO(b'payload')
        open_cm.__exit__.return_value = False

        # Simulate a transient error followed by a successful download
        mock_urlopen.side_effect = [urllib.error.URLError('transient'), open_cm]

        out = '/tmp/rift-dl-retry-test'
        with self.assertLogs(level='INFO') as log_cm:
            download_file(url, out, retries=2)

        self.assert_file_exists(out)
        mock_sleep.assert_called_once_with(3)
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(
            log_cm.output,
            [
                f'INFO:root:Error while downloading {url}: <urlopen error transient>, '
                f'will retry in 3 seconds…',
            ],
        )
        os.remove(out)

    @patch('rift.utils.time.sleep')
    @patch('urllib.request.urlopen')
    def test_download_file_retries_failure(
            self, mock_urlopen, mock_sleep):
        url = 'https://example.test/missing'
        out = '/tmp/never-written'
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url, 503, 'Service Unavailable', None, None
        )

        with self.assertLogs(level='INFO') as log_cm:
            with self.assertRaisesRegex(
                RiftError,
                r'^Error while downloading https://example\.test/missing: '
                r'HTTP Error 503: Service Unavailable$',
            ):
                download_file(url, out, retries=2)

        self.assertFalse(os.path.isfile(out))
        self.assertCountEqual(
            log_cm.output,
            [
                f'INFO:root:Error while downloading {url}: HTTP Error 503: '
                f'Service Unavailable, will retry in 3 seconds…',
                f'INFO:root:Error while downloading {url}: HTTP Error 503: '
                f'Service Unavailable, will retry in 6 seconds…',
            ],
        )
        mock_sleep.assert_has_calls([call(3), call(6)])

    @patch('urllib.request.urlopen')
    def test_last_modified(self, mock_urlopen):
        mock_response = Mock()
        mock_response.getheader.return_value = "Sat, 1 Jan 2000 00:00:00 GMT"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        self.assertEqual(last_modified("http://test"), 946684800)

    @patch('urllib.request.urlopen')
    def test_last_modified_bearer_token(self, mock_urlopen):
        mock_response = Mock()
        mock_response.getheader.return_value = "Sat, 1 Jan 2000 00:00:00 GMT"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        self.assertEqual(last_modified("http://test", bearer_token='tok'), 946684800)
        # Check that Authorization header is set
        req = mock_urlopen.call_args[0][0]
        hdrs = dict(req.header_items())
        self.assertEqual(hdrs.get('Authorization'), 'Bearer tok')

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
