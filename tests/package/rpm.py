#
# Copyright (C) 2025 CEA
#
from unittest.mock import Mock, patch
import os
import textwrap

from rift import RiftError
from rift.package.rpm import PackageRPM, ActionableArchPackageRPM
from rift.run import RunResult
from rift.TestResults import TestResults
from rift.Config import _DEFAULT_VARIANT
from rift.Gerrit import Review

from ..TestUtils import RiftProjectTestCase, make_temp_file, gen_rpm_spec


class PackageRPMTest(RiftProjectTestCase):
    """
    Tests class for PackageRPM
    """
    def test_init(self):
        """ Test PackageRPM initialisation """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        self.assertEqual(pkg.format, 'rpm')
        self.assertEqual(pkg.buildfile, '{0}/{1}.spec'.format(pkg.dir, pkgname))
        self.assertIsNone(pkg.ignore_rpms)
        self.assertIsNone(pkg.rpmnames)
        self.assertCountEqual(pkg.variants, [])

    def test_load(self):
        """ Test PackageRPM information loading """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
                rpm_names:
                - pkg
                - pkg-devel
                ignore_rpms:
                - pkg-debuginfos
                variants:
                - variant1
                - variant2
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.rpmnames, [ 'pkg', 'pkg-devel' ])
        self.assertEqual(pkg.ignore_rpms, [ 'pkg-debuginfos' ])
        self.assertCountEqual(pkg.variants, ['variant1', 'variant2'])

    def test_check(self):
        """ Test PackageRPM.check() does not fail with error """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        # Create sources dir and source
        sources_dir = os.path.join(pkg.dir, 'sources')
        os.makedirs(sources_dir)
        with open(os.path.join(sources_dir, "pkg-1.0.tar.gz"), 'w+') as fh:
            fh.write("data")
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        pkg.check()

    def test_check_missing_source(self):
        """ Test PackageRPM.check() detect missing source """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        with self.assertRaisesRegex(RiftError,
            r'Missing source file\(s\): pkg-1.0.tar.gz'):
            pkg.check()

    def test_check_unused_source(self):
        """ Test PackageRPM.check() detect unused source """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        # Create sources dir, source and unused source
        sources_dir = os.path.join(pkg.dir, 'sources')
        os.makedirs(sources_dir)
        with open(os.path.join(sources_dir, 'pkg-1.0.tar.gz'), 'w+') as fh:
            fh.write("data")
        with open(os.path.join(sources_dir, 'unused-1.0.tar.gz'), 'w+') as fh:
            fh.write("data")
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        with self.assertRaisesRegex(RiftError,
            r'Unused source file\(s\): unused-1.0.tar.gz'):
            pkg.check()

    def test_add_changelog_entry(self):
        """ Test PackageRPM add changelog entry"""
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        pkg.add_changelog_entry("Myself", "Package modification", False)
        pkg.spec.load()
        self.assertEqual(pkg.spec.changelog_name, "Myself <buddy@somewhere.org> - 1.0-1")

    def test_add_changelog_entry_bump(self):
        """ Test PackageRPM add changelog entry with release bump"""
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        pkg.add_changelog_entry("Myself", "Package modification", True)
        pkg.spec.load()
        self.assertEqual(pkg.spec.changelog_name, "Myself <buddy@somewhere.org> - 1.0-2")

    def test_add_changelog_entry_unknown_maintainer(self):
        """ Test PackageRPM add changelog entry with unknown maintainer """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        with self.assertRaisesRegex(
            RiftError, "Unknown maintainer Unknown, cannot be found in staff"
        ):
            pkg.add_changelog_entry("Unknown", "Package modification", False)

    def test_has_real_variants(self):
        """ Test PackageRPM has_real_variants() """
        pkg = PackageRPM('pkg', self.config, self.staff, self.modules)
        with self.assertRaises(AssertionError):
            pkg.has_real_variants()
        pkg.variants = [_DEFAULT_VARIANT]
        self.assertFalse(pkg.has_real_variants())
        pkg.variants = ['variant1']
        self.assertTrue(pkg.has_real_variants())
        pkg.variants = [_DEFAULT_VARIANT, 'variant2']
        self.assertTrue(pkg.has_real_variants())
        pkg.variants = ['variant1', 'variant2']
        self.assertTrue(pkg.has_real_variants())

    def test_supports_arch_w_exclusive_arch(self):
        """ Test PackageRPM supports_arch() method with ExclusiveArch"""
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        self.assertTrue(pkg.supports_arch('x86_64'))
        self.assertFalse(pkg.supports_arch('aarch64'))

    def test_supports_arch_wo_exclusive_arch(self):
        """ Test PackageRPM supports_arch() method without ExclusiveArch"""
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        self.assertTrue(pkg.supports_arch('x86_64'))
        self.assertTrue(pkg.supports_arch('aarch64'))

    def test_analyze(self):
        """ Test PackageRPM analyze success """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
            ),
            suffix='.spec'
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        review = Mock(spec=Review)
        pkg.analyze(review, pkg.dir)
        review.invalidate.assert_not_called()

    def test_analyze_invalidate(self):
        """ Test PackageRPM analyze failure """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """))
        # Use $$RPM_SOURCE_DIR and $RPM_BUILD_ROOT in build steps in order to
        # produce error in both rpmlint v1 and v2.
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                buildsteps="$RPM_SOURCE_DIR\n$RPM_BUILD_ROOT",
            ),
            suffix='.spec'
        )
        pkg.buildfile = spec_file.name
        pkg.load(infopath = pkgfile.name)
        review = Mock(spec=Review)
        pkg.analyze(review, pkg.dir)
        review.invalidate.assert_called_once()

    def test_for_arch(self):
        """ Test PackageRPM for_arch() returns ActionableArchPackageRPM object. """
        pkgname = 'pkg'
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkg_arch = pkg.for_arch('x86_64')
        self.assertIsInstance(pkg_arch, ActionableArchPackageRPM)
        self.assertEqual(pkg_arch.name, pkg.name)
        self.assertEqual(pkg_arch.buildfile, pkg.buildfile)
        self.assertEqual(pkg_arch.config, pkg._config)
        self.assertEqual(pkg_arch.package, pkg)
        self.assertEqual(pkg_arch.arch, 'x86_64')


class ActionableArchPackageRPMTest(RiftProjectTestCase):
    """
    Tests class for ActionableArchPackageRPM
    """
    def setup_package(self, variants=None):
        self.make_pkg(variants=variants)
        _pkg = PackageRPM('pkg', self.config, self.staff, self.modules)
        _pkg.load()
        self.pkg = ActionableArchPackageRPM(_pkg, 'x86_64')

    @patch('rift.package.rpm.message')
    @patch('rift.package.rpm.Mock.build_rpms')
    @patch('rift.package.rpm.Mock.build_srpm')
    @patch('rift.package.rpm.Mock.init')
    def test_build(
        self,
        mock_mock_init,
        mock_mock_build_srpm,
        mock_mock_build_rpms,
        mock_message
    ):
        """ Test ActionableArchPackageRPM build """
        self.setup_package()
        self.pkg.build()
        # Check build() has called expected Mock methods.
        mock_mock_init.assert_called_once()
        mock_mock_build_srpm.assert_called_once()
        mock_mock_build_rpms.assert_any_call(
            mock_mock_build_srpm.return_value, _DEFAULT_VARIANT, self.pkg.repos, False
        )
        mock_message.assert_any_call("Building RPMS...")

    @patch('rift.package.rpm.Mock.build_rpms')
    @patch('rift.package.rpm.Mock.build_srpm')
    @patch('rift.package.rpm.Mock.init')
    def test_build_sign(self, mock_mock_init, mock_mock_build_srpm, mock_mock_build_rpms):
        """ Test ActionableArchPackageRPM build with sign enabled"""
        self.setup_package()
        self.pkg.build(sign=True)
        # Check build() has called expected Mock methods.
        mock_mock_init.assert_called_once()
        mock_mock_build_srpm.assert_called_once()
        mock_mock_build_rpms.assert_any_call(
            mock_mock_build_srpm.return_value, _DEFAULT_VARIANT, self.pkg.repos, True
        )

    @patch('rift.package.rpm.message')
    @patch('rift.package.rpm.Mock.build_rpms')
    @patch('rift.package.rpm.Mock.build_srpm')
    @patch('rift.package.rpm.Mock.init')
    def test_build_multiple_variants(
        self,
        mock_mock_init,
        mock_mock_build_srpm,
        mock_mock_build_rpms,
        mock_message,
    ):
        """ Test ActionableArchPackageRPM build with multiple variants"""
        variants = ['variant1', 'variant2']
        self.setup_package(variants=variants)
        self.pkg.package.variants = variants
        self.pkg.build()
        # Check build() has called expected Mock methods.
        mock_mock_init.assert_called_once()
        mock_mock_build_srpm.assert_called_once()
        for variant in variants:
            mock_mock_build_rpms.assert_any_call(
                mock_mock_build_srpm.return_value, variant, self.pkg.repos, False
            )
            mock_message.assert_any_call(f"Building RPMS variant {variant}...")

    @patch('rift.package.rpm.banner')
    @patch('rift.package.rpm.BasicTest')
    @patch('rift.package.rpm.time.sleep')
    @patch('rift.package.rpm.VM')
    def test_test(self, mock_vm, mock_time_sleep, mock_basic_test, mock_banner):
        """ Test ActionableArchPackageRPM test """
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(0, None, None)
        self.setup_package()
        results = self.pkg.test()
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 1)
        self.assertEqual(results.global_result, True)
        # Check VM run_test() called once for basic test
        mock_vm_obj.run_test.assert_called_with(
            mock_basic_test.return_value, _DEFAULT_VARIANT
        )
        # Check VM is stopped after the tests
        mock_vm_obj.stop.assert_called_once()
        mock_banner.assert_called_once_with(
            'Starting tests of package pkg on architecture x86_64'
        )

    @patch('rift.package.rpm.banner')
    @patch('rift.package.rpm.BasicTest')
    @patch('rift.package.rpm.time.sleep')
    @patch('rift.package.rpm.VM')
    def test_test_multiple_variants(
        self,
        mock_vm,
        mock_time_sleep,
        mock_basic_test,
        mock_banner
    ):
        """ Test ActionableArchPackageRPM test """
        variants = ['variant1', 'variant2']
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(0, None, None)
        self.setup_package(variants=variants)
        results = self.pkg.test()
        self.assertIsInstance(results, TestResults)
        # There should be one test result per variant, ie. 2 results
        self.assertEqual(len(results), 2)
        self.assertEqual(results.global_result, True)
        # Check VM run_test() called for basic test on all variants
        for variant in variants:
            mock_vm_obj.run_test.assert_any_call(mock_basic_test.return_value, variant)
            mock_banner.assert_any_call(
                f"Starting tests of package pkg variant {variant} on architecture "
                "x86_64"
            )
        # Check VM is stopped after the tests
        mock_vm_obj.stop.assert_called_once()

    @patch('rift.package.rpm.time.sleep')
    @patch('rift.package.rpm.VM')
    def test_test_vm_running(self, mock_vm, mock_time_sleep):
        """ Test ActionableArchPackageRPM test error VM running """
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = True
        self.setup_package()
        with self.assertRaisesRegex(RiftError, "^VM is already running$"):
            self.pkg.test()

    @patch('rift.package.rpm.time.sleep')
    @patch('rift.package.rpm.VM')
    def test_test_failure(self, mock_vm, mock_time_sleep):
        """ Test ActionableArchPackageRPM test failure """
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(1, None, None)
        self.setup_package()
        results = self.pkg.test()
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 1)
        self.assertEqual(results.global_result, False)

    @patch('rift.package.rpm.time.sleep')
    @patch('rift.package.rpm.VM')
    def test_test_noauto(self, mock_vm, mock_time_sleep):
        """ Test ActionableArchPackageRPM test noauto """
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        self.setup_package()
        results = self.pkg.test(noauto=True)
        # Check empty TestResults
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 0)
        self.assertEqual(results.global_result, True)

    @patch('rift.package.rpm.VM')
    def test_test_noquit(self, mock_vm):
        """ Test ActionableArchPackageRPM test noquit """
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(0, None, None)
        self.setup_package()
        self.pkg.test(noquit=True)
        # Check VM is NOT stopped after the tests
        mock_vm_obj.stop.assert_not_called()

    @patch('rift.package.rpm.Mock.publish')
    def test_publish_working_repo(self, mock_mock_publish):
        """ Test ActionableArchPackageRPM publish in working repository """
        mock_repository = Mock()
        self.setup_package()
        self.pkg.repos.working = mock_repository
        self.pkg.publish()
        mock_mock_publish.assert_called_once_with(mock_repository)
        mock_repository.update.assert_called_once()

    @patch('rift.package.rpm.Mock.publish')
    def test_publish_staging_repo(self, mock_mock_publish):
        """ Test ActionableArchPackageRPM publish in staging repository """
        mock_repository = Mock()
        self.setup_package()
        self.pkg.publish(staging=mock_repository)
        mock_mock_publish.assert_called_once_with(mock_repository)
        mock_repository.update.assert_called_once()

    @patch('rift.package.rpm.Mock.publish')
    def test_publish_no_update(self, mock_mock_publish):
        """ Test ActionableArchPackageRPM publish """
        mock_repository = Mock()
        self.setup_package()
        self.pkg.repos.working = mock_repository
        self.pkg.publish(updaterepo=False)
        mock_mock_publish.assert_called_once_with(mock_repository)
        # Check repo is NOT uppdated
        mock_repository.update.assert_not_called()

    @patch('rift.package.rpm.Mock.clean')
    def test_clean(self, mock_mock_clean):
        """ Test ActionableArchPackageRPM clean """
        self.setup_package()
        self.pkg.clean()
        # Check clean() has called expected Mock method.
        mock_mock_clean.assert_called_once()
