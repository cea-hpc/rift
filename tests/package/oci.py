#
# Copyright (C) 2025 CEA
#
import os
import textwrap
from unittest.mock import Mock, patch

from rift import RiftError
from rift.package.oci import PackageOCI, ActionableArchPackageOCI
from rift.repository.oci import ArchRepositoriesOCI
from rift.Gerrit import Review
from rift.run import RunResult
from rift.TestResults import TestResults

from ..TestUtils import RiftProjectTestCase, PackageTestDef, make_temp_file


class PackageOCITest(RiftProjectTestCase):
    """
    Tests class for PackageOCI
    """
    def test_init(self):
        """PackageOCI initialisation """
        pkgname = 'pkg'
        pkg = PackageOCI(pkgname, self.config, self.staff, self.modules)
        self.assertEqual(pkg.format, 'oci')
        self.assertEqual(pkg.buildfile, f"{pkg.dir}/Containerfile")

    def test_load(self):
        """PackageOCI infos loading"""
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
                oci:
                    version: 0.0.1
                    release: 1
            """))
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.version, '0.0.1')
        self.assertEqual(pkg.release, '1')

    def test_load_source_topdir(self):
        """PackageOCI infos loading with source topdir"""
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
                oci:
                    version: 0.0.1
                    release: 1
                    source_topdir: pkg-main
            """))
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.source_topdir, 'pkg-main')

    def test_load_main_source(self):
        """PackageOCI infos loading with main source"""
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
                oci:
                    version: 0.0.1
                    release: 1
                    main_source: pkg-full.tar.bz2
            """))
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.main_source, 'pkg-full.tar.bz2')

    def test_load_missing_version(self):
        """PackageOCI infos missing version"""
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
                oci:
                    release: 1
            """))
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        with self.assertRaisesRegex(
            RiftError, "Unable to load oci version from metadata"):
            pkg.load(infopath = pkgfile.name)

    def test_load_missing_release(self):
        """PackageOCI infos missing release"""
        pkgfile = make_temp_file(textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
                oci:
                    version: 0.0.1
            """))
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        with self.assertRaisesRegex(
            RiftError, "Unable to load oci release from metadata"):
            pkg.load(infopath = pkgfile.name)

    def test_write(self):
        """PackageOCI write"""
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        pkg.module = 'Great module'
        pkg.maintainers = ['Myself']
        pkg.reason = 'Missing package'
        pkg.origin = 'Company'
        pkg.version = '0.0.1'
        pkg.release = '2'
        pkg.main_source = 'pkg-1.0.tar.gz'
        pkg.source_topdir = 'pkg_1.0'
        os.makedirs(pkg.dir)
        pkg.write()
        loaded = PackageOCI('pkg', self.config, self.staff, self.modules)
        loaded.load()
        self.assertEqual(pkg.module, loaded.module)
        self.assertCountEqual(pkg.maintainers, loaded.maintainers)
        self.assertEqual(pkg.reason, loaded.reason)
        self.assertEqual(pkg.origin, loaded.origin)
        self.assertEqual(pkg.version, loaded.version)
        self.assertEqual(pkg.release, loaded.release)
        self.assertEqual(pkg.main_source, loaded.main_source)
        self.assertEqual(pkg.source_topdir, loaded.source_topdir)

    def test_add_changelog_entry(self):
        """PackageOCI add changelog entry (not implemented)"""
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        with self.assertRaises(NotImplementedError):
            pkg.add_changelog_entry("Myself", "Modify package", False)

    def test_analyze(self):
        """PackageOCI analyse (not implemented)"""
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        review = Review()
        with self.assertRaises(NotImplementedError):
            pkg.analyze(review, pkg.dir)

    def test_supports_arch(self):
        """ PackageOCI supports_arch() """
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        self.assertTrue(pkg.supports_arch('x86_64'))
        self.assertTrue(pkg.supports_arch('aarch64'))
        self.assertFalse(pkg.supports_arch('fail'))

    def test_for_arch(self):
        """ PackageOCI for_arch() returns ActionableArchPackageOCI object. """
        pkgname = 'pkg'
        pkg = PackageOCI(pkgname, self.config, self.staff, self.modules)
        pkg_arch = pkg.for_arch('x86_64')
        self.assertIsInstance(pkg_arch, ActionableArchPackageOCI)
        self.assertEqual(pkg_arch.name, pkg.name)
        self.assertEqual(pkg_arch.buildfile, pkg.buildfile)
        self.assertEqual(pkg_arch.config, pkg._config)
        self.assertEqual(pkg_arch.package, pkg)
        self.assertEqual(pkg_arch.arch, 'x86_64')


class ActionableArchPackageOCITest(RiftProjectTestCase):
    """
    Tests class for ActionableArchPackageOCI
    """
    def setup_package(self, src_top_dir=None, tests=None):
        self.make_pkg(src_top_dir=src_top_dir, tests=tests)
        _pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        _pkg.load()
        self.pkg = ActionableArchPackageOCI(_pkg, 'x86_64')

    @patch('rift.package.oci.ContainerRuntime')
    def test_build(self, mock_container_runtime):
        self.setup_package()
        self.pkg.build()
        mock_container_runtime.return_value.build.assert_called_once()

    @patch('rift.package.oci.ContainerRuntime')
    def test_build_missing_source(self, mock_container_runtime):
        self.setup_package()
        # Delete package source archive
        os.unlink(self.pkgsrc['pkg'])
        self.pkg.package.load()
        with self.assertRaisesRegex(
            RiftError, "^Unable to find sources for package pkg$"):
            self.pkg.build()
        mock_container_runtime.return_value.build.assert_not_called()

    @patch('rift.package.oci.ContainerRuntime')
    def test_build_multiple_sources_with_main_source(self, mock_container_runtime):
        self.setup_package()
        # create another source to introduce conflict
        another_source_path = os.path.join(
            os.path.dirname(self.pkgsrc['pkg']), 'another-source')
        with open(another_source_path, 'w+') as fh:
            fh.write('dummy')
        self.pkg.package.load()
        self.pkg.package.main_source = 'pkg-1.0.tar.gz'
        self.pkg.build()
        mock_container_runtime.return_value.build.assert_called_once()
        # remove additional source
        os.unlink(another_source_path)

    @patch('rift.package.oci.ContainerRuntime')
    def test_build_multiple_sources_without_main_source(self, mock_container_runtime):
        self.setup_package()
        # create another source to introduce conflict
        another_source_path = os.path.join(
            os.path.dirname(self.pkgsrc['pkg']), 'another-source')
        with open(another_source_path, 'w+') as fh:
            fh.write('dummy')
        self.pkg.package.load()
        self.pkg.build()
        mock_container_runtime.return_value.build.assert_called_once()
        # remove additional source
        os.unlink(another_source_path)

    @patch('rift.package.oci.ContainerRuntime')
    def test_build_missing_main_source(self, mock_container_runtime):
        self.setup_package()
        # create another source to introduce conflict
        another_source_path = os.path.join(
            os.path.dirname(self.pkgsrc['pkg']), 'another-source')
        with open(another_source_path, 'w+') as fh:
            fh.write('dummy')
        self.pkg.package.load()
        self.pkg.package.main_source = "fail"
        with self.assertRaisesRegex(
            RiftError,
            r"^Unable to find main source fail among available package sources: .*$"):
            self.pkg.build()
        mock_container_runtime.return_value.build.assert_not_called()
        # remove additional source
        os.unlink(another_source_path)

    @patch('rift.package.oci.ContainerRuntime')
    def test_build_unable_determine_source(self, mock_container_runtime):
        self.setup_package()
        # create another source to introduce conflict
        another_source_path = os.path.join(
            os.path.dirname(self.pkgsrc['pkg']), 'pkg-1.0.tar.bz2')
        with open(another_source_path, 'w+') as fh:
            fh.write('dummy')
        self.pkg.package.load()
        with self.assertRaisesRegex(
            RiftError,
            r"^Unable to determine main package source among available package "
            r"sources: .*$"):
            self.pkg.build()
        mock_container_runtime.return_value.build.assert_not_called()
        # remove additional source
        os.unlink(another_source_path)

    @patch('rift.package.oci.ContainerRuntime')
    def test_build_unable_find_top_dir(self, mock_container_runtime):
        self.setup_package(src_top_dir='fail')
        self.pkg.package.load()
        with self.assertRaisesRegex(
            RiftError, "^Unable to find package source top directory .*/pkg-1.0$"):
            self.pkg.build()
        mock_container_runtime.return_value.build.assert_not_called()

    @patch('rift.package.oci.ContainerRuntime')
    def test_build_sign_warn(self, mock_container_runtime):
        self.setup_package()
        self.pkg.package.load()
        with self.assertLogs(level='WARNING') as log:
            self.pkg.build(sign=True)
        self.assertIn(
            'WARNING:root:Signing OCI container image is not supported, '
            'skipping pkg OCI package signature',
            log.output
        )

    @patch('rift.package.oci.ContainerRuntime')
    def test_test_success(self, mock_container_runtime):
        self.setup_package()
        self.pkg.run_local_test = Mock(return_value=RunResult(0, None, None))
        mock_container_runtime.return_value.run_test.return_value = RunResult(0, 'ok', None)
        results = self.pkg.test()
        # Check run_local_test() has not been called.
        self.pkg.run_local_test.assert_not_called()
        # Check ContainerRuntime.run_test() has been called once.
        mock_container_runtime.return_value.run_test.assert_called_once()
        self.assertIsInstance(results, TestResults)
        self.assertEqual(results.global_result, True)

    @patch('rift.package.oci.ContainerRuntime')
    def test_test_local(self, mock_container_runtime):
        # Create fake package with one local test.
        self.setup_package(
            tests=[PackageTestDef(name='0_test.sh', local=True, formats=[])])
        self.pkg.run_local_test = Mock(return_value=RunResult(0, None, None))
        mock_container_runtime.return_value.run_test.return_value = RunResult(0, 'ok', None)
        results = self.pkg.test()
        # Check run_local_test() has been called once for local test
        self.pkg.run_local_test.assert_called_once()
        # Check ContainerRuntime.run_test() has not been called.
        mock_container_runtime.return_value.run_test.assert_not_called()
        self.assertIsInstance(results, TestResults)
        self.assertEqual(results.global_result, True)

    @patch('rift.package.oci.ContainerRuntime')
    def test_test_failure(self, mock_container_runtime):
        self.setup_package()
        mock_container_runtime.return_value.run_test.return_value = RunResult(1, 'ko', None)
        results = self.pkg.test()
        mock_container_runtime.return_value.run_test.assert_called_once()
        self.assertIsInstance(results, TestResults)
        self.assertEqual(results.global_result, False)

    @patch('rift.package.oci.ContainerRuntime')
    def test_publish(self, mock_container_runtime):
        self.setup_package()
        self.pkg.repos = Mock(spec=ArchRepositoriesOCI)
        self.pkg.repos.path = '/oci'
        self.pkg.publish()
        self.pkg.repos.ensure_created.assert_called_once()
        mock_container_runtime.return_value.archive.assert_called_once_with(
            self.pkg, '/oci/pkg_1.0-1.x86_64.tar')

    @patch('rift.package.oci.ContainerRuntime')
    def test_publish_staging(self, mock_container_runtime):
        self.setup_package()
        self.pkg.repos = Mock(spec=ArchRepositoriesOCI)
        self.pkg.publish(staging=True)
        self.pkg.repos.ensure_created.assert_not_called()
        mock_container_runtime.return_value.archive.assert_not_called()

    def test_clean(self):
        self.setup_package()
        self.pkg.clean()
