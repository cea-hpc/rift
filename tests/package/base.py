#
# Copyright (C) 2020 CEA
#
import os

from rift import RiftError
from rift.package import Package
from rift.package._base import (
    _SOURCES_DIR,
    _META_FILE,
    _TESTS_DIR,
    ActionableArchPackage,
)
from ..TestUtils import RiftProjectTestCase


class PackageTestingConcrete(Package):
    """Dummy Package concrete child for testing purpose."""
    def __init__(self, name, config, staff, modules, _format):
        super().__init__(name, config, staff, modules, _format, f"{name}.buildfile")

    def _serialize_specific_metadata(self):
        return {}

    def _deserialize_specific_metadata(self, data):
        pass

    def for_arch(self, arch):
        return ActionableArchPackageTestingConcrete(self, arch)


class ActionableArchPackageTestingConcrete(ActionableArchPackage):
    """Dummy ActionableArchPackage concrete child for testing purpose."""
    def __init__(self, package, arch):
        super().__init__(package, arch)

    def build(self, **kwargs):
        pass

    def test(self, **kwargs):
        pass

    def publish(self, **kwargs):
        pass


class PackageTest(RiftProjectTestCase):
    """
    Tests class for Package
    """

    def test_init_abstract(self):
        with self.assertRaisesRegex(
            TypeError,
            "^Can't instantiate abstract class Package .*"
        ):
            Package('pkg', self.config, self.staff, self.modules, 'fail', 'build.fail')

    def test_init_concrete(self):
        """ Test Package initialisation """
        pkgname = 'pkg'
        self.config.project_dir = '/'
        pkg = PackageTestingConcrete(
            pkgname, self.config, self.staff, self.modules, 'rpm'
        )
        self.assertEqual(
            pkg.dir, '/{0}/{1}'.format(self.config.get('packages_dir'), pkgname)
        )
        self.assertEqual(pkg.sourcesdir, os.path.join(pkg.dir, _SOURCES_DIR))
        self.assertEqual(pkg.testsdir, os.path.join(pkg.dir, _TESTS_DIR))
        self.assertEqual(pkg.metafile, os.path.join(pkg.dir, _META_FILE))
        self.assertEqual(pkg.format, 'rpm')
        self.assertEqual(pkg.buildfile, f"{pkg.dir}/{pkgname}.buildfile")

    def test_init_invalid_format(self):
        with self.assertRaisesRegex(RiftError, "^Unsupported package format fail$"):
            PackageTestingConcrete('pkg', self.config, self.staff, self.modules, 'fail')

    def test_load(self):
        """ Test Package information loading """
        self.make_pkg(
            metadata={'depends': ['foo', 'bar'], 'exclude_archs': ['aarch64']}
        )
        pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )
        pkg.load()
        self.assertEqual(pkg.module, 'Great module')
        self.assertEqual(pkg.maintainers, ['Myself'])
        self.assertEqual(pkg.reason, 'Missing feature')
        self.assertEqual(pkg.origin, 'Vendor')
        self.assertCountEqual(pkg.depends, ['foo', 'bar'])
        self.assertCountEqual(pkg.exclude_archs, ['aarch64'])

    def test_for_arch(self):
        pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )
        actionable_pkg = pkg.for_arch('x86_64')
        self.assertIsInstance(actionable_pkg, ActionableArchPackageTestingConcrete)
        self.assertEqual(actionable_pkg.name, 'pkg')
        self.assertEqual(actionable_pkg.package, pkg)
        self.assertEqual(actionable_pkg.buildfile, f"{pkg.dir}/{pkg.name}.buildfile")
        self.assertEqual(actionable_pkg.config, self.config)
        self.assertEqual(actionable_pkg.arch, 'x86_64')


class ActionableArchPackageTest(RiftProjectTestCase):

    def setUp(self):
        super().setUp()
        self.pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )

    def test_init_abstract(self):
        with self.assertRaisesRegex(
            TypeError,
            "^Can't instantiate abstract class ActionableArchPackage .*"
        ):
            ActionableArchPackage(self.pkg, 'x86_64')

    def test_init_concrete(self):
        ActionableArchPackageTestingConcrete(self.pkg, 'x86_64')
