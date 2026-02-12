#
# Copyright (C) 2024 CEA
#
from unittest import mock

from .TestUtils import RiftTestCase
from rift.Config import Config
from rift.Gerrit import Review
from rift import RiftError

class GerritTest(RiftTestCase):
    def setUp(self):
        self.config = Config()
        self.config.set(
            'gerrit',
            {
                'realm': 'Rift',
                'server': 'localhost',
                'username': 'rift',
                'password': 'SECR3T',
            }
        )
        self.review = Review()
        self.review.add_comment('/path/to/file', 42, 'E', 'test error message')

    def test_invalidate(self):
        """ Test Review.invalidate() method"""
        self.assertEqual(self.review.validated, True)
        self.review.invalidate()
        self.assertEqual(self.review.validated, False)

    @mock.patch("rift.Gerrit.urllib.urlopen")
    def test_push(self, mock_urlopen):
        """ Test Review push """
        self.review.push(self.config, 4242, 42)
        # Check push successfully send HTTP request with urllib.urlopen() and
        # reads its result.
        mock_urlopen.assert_called_once()
        mock_urlopen.return_value.read.assert_called_once()

    def test_push_no_config(self):
        """ Test Review push w/o gerrit config error """
        del self.config.options['gerrit']
        with self.assertRaisesRegex(RiftError, "Gerrit configuration is not defined"):
            self.review.push(self.config, 4242, 42)

    def test_push_missing_conf_param(self):
        """ Test Review push with missing parameter error """
        gerrit_conf = self.config.get('gerrit')
        for parameter, value in gerrit_conf.copy().items():
            # temporary remove parameter
            del gerrit_conf[parameter]
            with self.assertRaisesRegex(RiftError, "Gerrit .* is not defined"):
                self.review.push(self.config, 4242, 42)
            # restore value
            gerrit_conf[parameter] = value
