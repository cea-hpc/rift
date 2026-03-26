#
# Copyright (C) 2025-2026 CEA
#
import os
import textwrap
from unittest.mock import patch

from rift import RiftError
from rift.package import Package
from rift.package._base import (
    _SOURCES_DIR,
    _META_FILE,
    _TESTS_DIR,
    ActionableArchPackage,
    Test,
)
from ..TestUtils import RiftProjectTestCase, make_temp_file
from rift.Gerrit import Review


class PackageTestingConcrete(Package):
    """Dummy Package concrete child for testing purpose."""
    def __init__(self, name, config, staff, modules, _format):
        super().__init__(name, config, staff, modules, _format, f"{name}.buildfile")

    def _serialize_specific_metadata(self):
        return {}

    def _deserialize_specific_metadata(self, data):
        pass

    def subpackages(self):
        return []

    def build_requires(self):
        return []

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

    def test_tests(self):
        """ Test Package tests method """
        self.make_pkg()
        pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )
        pkg.load()
        tests = [test for test in pkg.tests()]
        self.assertEqual(len(tests), 1)
        self.assertIsInstance(tests[0], Test)
        self.assertEqual(tests[0].name, '0_test')

    def test_subpackages(self):
        """ Test Package subpackages (dummy implementation) """
        pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )
        self.assertCountEqual(pkg.subpackages(), [])

    def test_build_requires(self):
        """ Test Package build requires (dummy implementation) """
        pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )
        self.assertCountEqual(pkg.build_requires(), [])

    def test_add_changelog_entry(self):
        """ Test Package add changelog entry (not implemented) """
        pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )
        with self.assertRaises(NotImplementedError):
            pkg.add_changelog_entry("Myself", "Package modification", False)

    def test_analyze(self):
        """ Test Package analyze (not implemented) """
        pkg = PackageTestingConcrete(
            'pkg', self.config, self.staff, self.modules, 'rpm'
        )
        with self.assertRaises(NotImplementedError):
            pkg.analyze(Review(), pkg.dir)


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

    @patch('rift.package._base.run_command')
    def test_run_local_test(self, mock_run_command):
        actionable_pkg = ActionableArchPackageTestingConcrete(self.pkg, 'x86_64')
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                /bin/true
                """),
            suffix='.sh'
        )
        test = Test(command.name)
        actionable_pkg.run_local_test(test)
        mock_run_command.assert_called_once_with(
            command.name, capture_output=True, shell=True)

    @patch('rift.package._base.run_command')
    def test_run_local_test_with_funcs(self, mock_run_command):
        actionable_pkg = ActionableArchPackageTestingConcrete(self.pkg, 'x86_64')
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                /bin/true
                """),
            suffix='.sh'
        )
        test = Test(command.name)
        actionable_pkg.run_local_test(test, { 'hey': 'echo hey!'})
        mock_run_command.assert_called_once_with(
            f"hey() {{ echo hey!; }}; export -f hey; {command.name}",
            capture_output=True, shell=True)

    def test_clean(self):
        """ Test clean method no-op on abstract class """
        actionable_pkg = ActionableArchPackageTestingConcrete(self.pkg, 'x86_64')
        actionable_pkg.clean()


class TestTest(RiftProjectTestCase):
    def test_init(self):
        """ Test with command """
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                # fake test
                /bin/true
                """),
            suffix='.sh'
        )
        test = Test(command.name)
        self.assertEqual(test.command, command.name)
        self.assertFalse(test.local)
        self.assertEqual(
            test.name, os.path.splitext(os.path.basename(command.name))[0])

    def test_init_local(self):
        """ Test with command to run locally """
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                #
                # *** RIFT LOCAL ***
                #
                /bin/true
                """),
            suffix='.sh'
        )
        with self.assertLogs(level='DEBUG') as logs:
            test = Test(command.name)
        self.assertTrue(test.local)
        self.assertIn(
            f"DEBUG:root:Test '{test.name}' detected as local", logs.output)
