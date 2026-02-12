#
# Copyright (C) 2023 CEA
#

import os
from .TestUtils import RiftTestCase
from rift.TempDir import TempDir

class TempDirTest(RiftTestCase):
    """
    Tests class for TempDir
    """

    def test_init(self):
        """ Test TempDir instance """
        tmpdir = TempDir('somewhere')
        self.assertIsNone(tmpdir.path)
        self.assertEqual(tmpdir.name, 'somewhere')

    def test_create(self):
        """ Test TempDir creation"""
        tmpdir = TempDir('somewhere')
        tmpdir.create()
        self.assertTrue(tmpdir.name in tmpdir.path)
        self.assertTrue(os.path.isdir(tmpdir.path))

    def test_delete(self):
        """ Test TempDir deletion"""
        tmpdir = TempDir('somewhere')
        tmpdir.create()
        oldpath=tmpdir.path
        tmpdir.delete()
        self.assertIsNone(tmpdir.path)
        self.assertFalse(os.path.isdir(oldpath))
