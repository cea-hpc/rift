#
# Copyright (C) 2020 CEA
#
import os

from rift import RiftError
from rift.package import Package
from rift.package._base import _SOURCES_DIR, _META_FILE, _TESTS_DIR
from ..TestUtils import RiftProjectTestCase


class PackageTest(RiftProjectTestCase):
    """
    Tests class for Package
    """
    def test_init(self):
        """ Test Package initialisation """
        pkgname = 'pkg'
        self.config.project_dir = '/'
        pkg = Package(pkgname, self.config, self.staff, self.modules, 'rpm', f"{pkgname}.spec")
        self.assertEqual(pkg.dir, '/{0}/{1}'.format(self.config.get('packages_dir'), pkgname))
        self.assertEqual(pkg.sourcesdir, os.path.join(pkg.dir, _SOURCES_DIR))
        self.assertEqual(pkg.testsdir, os.path.join(pkg.dir, _TESTS_DIR))
        self.assertEqual(pkg.metafile, os.path.join(pkg.dir, _META_FILE))
        self.assertEqual(pkg.format, 'rpm')
        self.assertEqual(pkg.buildfile, '{0}/{1}.spec'.format(pkg.dir, pkgname))

    def test_init_invalid_format(self):
        with self.assertRaisesRegex(RiftError, "^Unsupported package format fail$"):
            Package('pkg', self.config, self.staff, self.modules, 'fail', 'build.fail')

    def test_load(self):
        """ Test Package information loading """
        self.make_pkg()
        pkg = Package('pkg', self.config, self.staff, self.modules, 'rpm', 'pkg.spec')
        pkg.load()
        self.assertEqual(pkg.module, 'Great module')
        self.assertEqual(pkg.maintainers, ['Myself'])
        self.assertEqual(pkg.reason, 'Missing feature')
        self.assertEqual(pkg.origin, 'Vendor')
