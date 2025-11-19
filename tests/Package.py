#
# Copyright (C) 2020 CEA
#
import os

from rift.Config import Config, Staff, Modules
from rift.Package import _SOURCES_DIR, _DOC_FILES, _META_FILE, _TESTS_DIR, Package
from TestUtils import make_temp_file, make_temp_dir, RiftTestCase

class PackageTest(RiftTestCase):
    """
    Tests class for Package
    """
    def setUp(self):
        self.config = Config()
        self.config.project_dir = '/'
        self.staff = Staff(config = self.config)
        self.staff_file = make_temp_file("""
staff:
  'J. Doe':
    email: 'j.doe@rift.org'
""")
        self.staff.load(self.staff_file.name)
        self.config_file = make_temp_file("""
modules:
  'Tools':
    manager: 'J. Doe'
""")
        self.modules = Modules(config = self.config, staff = self.staff)
        self.modules.load(self.config_file.name)

    def test_init(self):
        """ Test Package initialisation """
        pkgname = 'pkg'
        pkg = Package(pkgname, self.config, self.staff, self.modules)
        self.assertEqual(pkg.dir, '/{0}/{1}'.format(self.config.get('packages_dir'), pkgname))
        self.assertEqual(pkg.sourcesdir, os.path.join(pkg.dir, _SOURCES_DIR))
        self.assertEqual(pkg.testsdir, os.path.join(pkg.dir, _TESTS_DIR))
        self.assertEqual(pkg.metafile, os.path.join(pkg.dir, _META_FILE))
        self.assertEqual(pkg.specfile, '{0}/{1}.spec'.format(pkg.dir, pkgname))

    def test_load(self):
        """ Test Package information loading """
        pkgfile = make_temp_file("""
package:
  maintainers:
  - J. Doe
  module: Tools
  reason: Missing package
  origin: Company
  rpm_names:
  - pkg
  - pkg-devel
  ignore_rpms:
  - pkg-debuginfos
        """)
        pkg = Package('pkg', self.config, self.staff, self.modules)
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.module, 'Tools')
        self.assertEqual(pkg.maintainers, ['J. Doe'])
        self.assertEqual(pkg.reason, 'Missing package')
        self.assertEqual(pkg.origin, 'Company')
        self.assertEqual(pkg.rpmnames, [ 'pkg', 'pkg-devel' ])
        self.assertEqual(pkg.ignore_rpms, [ 'pkg-debuginfos' ])
        self.assertCountEqual(pkg.exclude_archs, [])

    def test_load_exclude_archs_str(self):
        """ Test Package information loading with exclude_archs string """
        pkgfile = make_temp_file("""
package:
  maintainers:
  - J. Doe
  module: Tools
  reason: Missing package
  origin: Company
  exclude_archs: x86_64
        """)
        pkg = Package('pkg', self.config, self.staff, self.modules)
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.module, 'Tools')
        self.assertEqual(pkg.maintainers, ['J. Doe'])
        self.assertEqual(pkg.reason, 'Missing package')
        self.assertEqual(pkg.origin, 'Company')
        self.assertCountEqual(pkg.exclude_archs, ['x86_64'])

    def test_load_exclude_archs_list(self):
        """ Test Package information loading with exclude_archs list """
        pkgfile = make_temp_file("""
package:
  maintainers:
  - J. Doe
  module: Tools
  reason: Missing package
  origin: Company
  exclude_archs:
  - x86_64
  - aarch64
        """)
        pkg = Package('pkg', self.config, self.staff, self.modules)
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.module, 'Tools')
        self.assertEqual(pkg.maintainers, ['J. Doe'])
        self.assertEqual(pkg.reason, 'Missing package')
        self.assertEqual(pkg.origin, 'Company')
        self.assertCountEqual(pkg.exclude_archs, ['x86_64', 'aarch64'])

    def test_supports_arch(self):
        """ Test Package.supports_arch() """
        pkg = Package('pkg', self.config, self.staff, self.modules)
        pkg.exclude_archs = []
        self.assertTrue(pkg.supports_arch('x86_64'))
        self.assertTrue(pkg.supports_arch('aarch64'))
        pkg.exclude_archs = ['x86_64']
        self.assertFalse(pkg.supports_arch('x86_64'))
        self.assertTrue(pkg.supports_arch('aarch64'))
