#
# Copyright (C) 2018 CEA
#

import os.path
import shutil
import atexit
from unittest.mock import patch, Mock, call
import subprocess
import textwrap
from io import StringIO

from .TestUtils import (
    make_temp_file, make_temp_dir, gen_rpm_spec, RiftTestCase, RiftProjectTestCase, SubPackage
)

from .VM import GLOBAL_CACHE, VALID_IMAGE_URL, PROXY
from rift.Controller import (
    main,
    get_packages_in_graph,
    get_packages_to_build,
    remove_packages,
    make_parser,
)
from rift.package.rpm import PackageRPM, ActionableArchPackageRPM
from rift.TestResults import TestResults
from rift.RPM import RPM, Spec
from rift import RiftError, DeclError

VALID_REPOS = {
    'os': {
        'url': 'https://repo.almalinux.org/almalinux/8/BaseOS/$arch/os/',
    },
    'appstream': {
        'url': 'https://repo.almalinux.org/almalinux/8/AppStream/$arch/os/',
    },
    'powertools': {
        'url': 'https://repo.almalinux.org/almalinux/8/PowerTools/$arch/os/',
    },
}


class ControllerTest(RiftTestCase):

    def test_main_version(self):
        """simple 'rift --version'"""
        self.assert_except(SystemExit, "0", main, ['--version'])


class ControllerProjectActionCreateTest(RiftProjectTestCase):
    """
    Tests class for Controller action create
    """

    def test_create_missing_pkg_module_reason(self):
        """create without package, module or reason fails"""
        for cmd in (['create', '-m', 'Great module', '-r', 'Good reason'],
                    ['create', 'pkg', '-r', 'Good reason'],
                    ['create', 'pkg', '-m', 'Great module']):
            with self.assertRaisesRegex(SystemExit, "2"):
                main(cmd)

    def test_create_missing_maintainer(self):
        """create without maintainer"""
        with self.assertRaisesRegex(RiftError, "You must specify a maintainer"):
            main(['create', 'pkg', '-m', 'Great module', '-r', 'Good reason'])

    def test_create(self):
        """simple create"""
        main(['create', 'pkg', '-m', 'Great module', '-r', 'Good reason',
              '--maintainer', 'Myself'])
        pkg = PackageRPM('pkg', self.config, self.staff, self.modules)
        pkg.load_info()
        self.assertEqual(pkg.module, 'Great module')
        self.assertEqual(pkg.reason, 'Good reason')
        self.assertCountEqual(pkg.maintainers, ['Myself'])
        os.unlink(pkg.metafile)
        os.rmdir(os.path.dirname(pkg.metafile))

    def test_create_unknown_maintainer(self):
        """create with unknown maintainer fails"""
        with self.assertRaisesRegex(
            RiftError, "Maintainer 'Fail' is not defined"):
            main(['create', 'pkg', '-m', 'Great module', '-r', 'Good reason',
                  '--maintainer', 'Fail'])


class ControllerProjectActionImportTest(RiftProjectTestCase):
    """
    Tests class for Controller action import
    """
    @property
    def src_rpm(self):
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'materials', 'pkg-1.0-1.src.rpm'
        )

    @property
    def bin_rpm(self):
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'materials', 'pkg-1.0-1.noarch.rpm'
        )

    def test_import_missing_pkg_module_reason(self):
        """import without package, module or reason fails"""
        for cmd in (['import', '-m', 'Great module', '-r', 'Good reason'],
                    ['import', 'pkg.src.rpm', '-r', 'Good reason'],
                    ['import', 'pkg.src.rpm', '-m', 'Great module']):
            with self.assertRaisesRegex(SystemExit, "2"):
                main(cmd)

    def test_import_missing_maintainer(self):
        """import without maintainer"""
        with self.assertRaisesRegex(RiftError, "You must specify a maintainer"):
            main(['import', self.src_rpm, '-m', 'Great module', '-r', 'Good reason'])

    def test_import_bin_rpm(self):
        """import binary rpm"""
        with self.assertRaisesRegex(
            RiftError,
            ".*pkg-1.0-1.noarch.rpm is not a source RPM$"):
            main(['import', self.bin_rpm, '-m', 'Great module',
                  '-r', 'Good reason', '--maintainer', 'Myself'])

    def test_import(self):
        """simple import"""
        main(['import', self.src_rpm, '-m', 'Great module', '-r', 'Good reason',
              '--maintainer', 'Myself'])
        pkg = PackageRPM('pkg', self.config, self.staff, self.modules)
        pkg.load()
        self.assertEqual(pkg.module, 'Great module')
        self.assertEqual(pkg.reason, 'Good reason')
        self.assertCountEqual(pkg.maintainers, ['Myself'])
        spec = Spec(filepath=pkg.buildfile)
        spec.load()
        self.assertEqual(spec.changelog_name, 'Myself <buddy@somewhere.org> - 1.0-1')
        self.assertEqual(spec.version, '1.0')
        self.assertEqual(spec.release, '1')
        self.assertTrue(os.path.exists(f"{pkg.buildfile}.orig"))
        shutil.rmtree(os.path.dirname(pkg.metafile))

    def test_import_unknown_maintainer(self):
        """import with unknown maintainer fails"""
        with self.assertRaisesRegex(
            RiftError, "Maintainer 'Fail' is not defined"):
            main(['import', self.src_rpm, '-m', 'Great module',
                    '-r', 'Good reason', '--maintainer', 'Fail'])


class ControllerProjectActionReimportTest(RiftProjectTestCase):
    """
    Tests class for Controller actionre import
    """
    @property
    def src_rpm(self):
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'materials', 'pkg-1.0-1.src.rpm'
        )

    @property
    def bin_rpm(self):
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'materials', 'pkg-1.0-1.noarch.rpm'
        )

    def test_reimport_missing_maintainer(self):
        """reimport without maintainer"""
        with self.assertRaisesRegex(RiftError, "You must specify a maintainer"):
            main(['reimport', self.src_rpm, '-m', 'Great module', '-r', 'Good reason'])

    def test_reimport(self):
        """simple reimport"""
        self.make_pkg(name='pkg')
        main(['reimport', self.src_rpm, '--maintainer', 'Myself'])
        pkg = PackageRPM('pkg', self.config, self.staff, self.modules)
        pkg.load()
        self.assertEqual(pkg.module, 'Great module')
        self.assertEqual(pkg.reason, 'Missing feature')
        self.assertCountEqual(pkg.maintainers, ['Myself'])
        spec = Spec(filepath=pkg.buildfile)
        spec.load()
        self.assertEqual(spec.changelog_name, 'Myself <buddy@somewhere.org> - 1.0-1')
        self.assertEqual(spec.version, '1.0')
        self.assertEqual(spec.release, '1')
        self.assertTrue(os.path.exists(f"{pkg.buildfile}.orig"))
        os.unlink(f"{pkg.buildfile}.orig")


class ControllerProjectActionQueryTest(RiftProjectTestCase):
    """
    Tests class for Controller action query
    """

    def test_action_query(self):
        """simple 'rift query' is ok """
        self.assertEqual(main(['query']), 0)

    def test_action_query_on_pkg(self):
        """ Test query on one package """
        self.make_pkg()
        self.assertEqual(main(['query', 'pkg']), 0)

    def test_action_query_on_bad_pkg(self):
        """ Test query on multiple packages with one errorneous package """
        self.make_pkg()
        ## A package with no name should be wrong but the command should not fail
        self.make_pkg(name='pkg2', metadata={})
        self.assertEqual(main(['query']), 0)

    @patch('sys.stdout', new_callable=StringIO)
    def test_action_query_output_default(self, mock_stdout):
        self.make_pkg(name="pkg1")
        self.make_pkg(name="pkg2", version='2.1', release='3')
        self.assertEqual(main(['query']), 0)
        self.assertIn(
            "NAME MODULE       MAINTAINERS VERSION RELEASE MODULEMANAGER",
            mock_stdout.getvalue())
        self.assertIn(textwrap.dedent("""
            ---- ------       ----------- ------- ------- -------------
            pkg1 Great module Myself      1.0     1       buddy@somewhere.org
            pkg2 Great module Myself      2.1     3       buddy@somewhere.org
            """),
            mock_stdout.getvalue())

    @patch('sys.stdout', new_callable=StringIO)
    def test_action_query_output_format(self, mock_stdout):
        self.make_pkg(name="pkg1")
        self.make_pkg(name="pkg2", version='2.1', release='3')
        self.assertEqual(
            main([
                'query', '--format',
                '%name %module %origin %reason %tests %version %arch %release '
                '%changelogname %changelogtime %maintainers %modulemanager '
                '%buildrequires']), 0)
        self.assertIn(
            "NAME MODULE       ORIGIN REASON          TESTS VERSION ARCH   "
            "RELEASE CHANGELOGNAME                      CHANGELOGTIME "
            "MAINTAINERS MODULEMANAGER       BUILDREQUIRES",
            mock_stdout.getvalue())
        self.assertIn(textwrap.dedent("""
            ---- ------       ------ ------          ----- ------- ----   ------- -------------                      ------------- ----------- -------------       -------------
            pkg1 Great module Vendor Missing feature 0     1.0     noarch 1       Myself <buddy@somewhere.org> 1.0-1 2019-02-26    Myself      buddy@somewhere.org br-package
            pkg2 Great module Vendor Missing feature 0     2.1     noarch 3       Myself <buddy@somewhere.org> 2.1-3 2019-02-26    Myself      buddy@somewhere.org br-package
            """),
            mock_stdout.getvalue())


class ControllerProjectActionCheckTest(RiftProjectTestCase):
    """
    Tests class for Controller action check
    """

    def test_check_without_type(self):
        """check without type fails"""
        with self.assertRaisesRegex(SystemExit, "2"):
            main(['check'])

    def test_check_staff(self):
        """simple check staff"""
        with self.assertLogs(level='INFO') as log:
            exit_code = main(['check', 'staff'])
        self.assertEqual(exit_code, 0)
        self.assertIn(
            'INFO:root:Staff file is OK.',
            log.output
        )

    def test_check_staff_not_found(self):
        """check staff file not found fails"""
        with self.assertRaisesRegex(DeclError, "Could not find '/dev/fail'"):
            exit_code = main(['check', 'staff', '-f', '/dev/fail'])
            self.assertEqual(exit_code, 1)

    def test_check_modules(self):
        """simple check modules"""
        with self.assertLogs(level='INFO') as log:
            exit_code = main(['check', 'modules'])
        self.assertEqual(exit_code, 0)
        self.assertIn(
            'INFO:root:Modules file is OK.',
            log.output
        )

    def test_check_modules_not_found(self):
        """check modules file not found fails"""
        with self.assertRaisesRegex(DeclError, "Could not find '/dev/fail'"):
            exit_code = main(['check', 'modules', '-f', '/dev/fail'])
            self.assertEqual(exit_code, 1)

    def test_check_info_without_file(self):
        """check info without file fails"""
        with self.assertRaisesRegex(
            RiftError, r"You must specifiy a file path \(-f\)"
        ):
            exit_code = main(['check', 'info'])
            self.assertEqual(exit_code, 1)

    def test_check_info(self):
        """simple check info"""
        self.make_pkg()
        with self.assertLogs(level='INFO') as log:
            exit_code = main(
                ['check', 'info', '-f',
                 os.path.join(self.pkgdirs['pkg'], 'info.yaml')]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn(
            'INFO:root:Info file is OK.',
            log.output
        )

    def test_check_info_not_found(self):
        """check info file not found fails"""
        self.make_pkg()
        with self.assertRaises(FileNotFoundError):
            exit_code = main(['check', 'info', '-f', '/dev/fail'])
            self.assertEqual(exit_code, 1)

    def test_check_spec_without_file(self):
        """check spec without file fails"""
        with self.assertRaisesRegex(
            RiftError, r"You must specifiy a file path \(-f\)"
        ):
            exit_code = main(['check', 'spec'])
            self.assertEqual(exit_code, 1)

    def test_check_spec(self):
        """simple check spec"""
        self.make_pkg()
        with self.assertLogs(level='INFO') as log:
            exit_code = main(
                ['check', 'spec', '-f', self.pkgspecs['pkg']]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn(
            'INFO:root:Spec file is OK.',
            log.output
        )

    def test_check_spec_not_found(self):
        """check spec file not found fails"""
        self.make_pkg()
        with self.assertRaisesRegex(RiftError, "/dev/fail does not exist"):
            main(['check', 'spec', '-f', '/dev/fail'])


class ControllerProjectActionValiddiffTest(RiftProjectTestCase):
    """
    Tests class for Controller action validdiff
    """
    @patch('rift.Controller.remove_packages')
    @patch('rift.Controller.validate_pkgs')
    @patch('rift.Controller.get_packages_from_patch')
    def test_action_validdiff(self, mock_get_packages_from_patch,
                              mock_validate_pkgs, mock_remove_packages):
        """ Test validdiff action calls expected functions """
        mock_get_packages_from_patch.return_value = (
            {'pkg': PackageRPM('pkg', self.config, self.staff, self.modules)}, {}
        )
        self.assertEqual(main(['validdiff', '/dev/null']), 0)
        mock_get_packages_from_patch.assert_called_once()
        mock_validate_pkgs.assert_called_once()
        mock_remove_packages.assert_called_once()

    @patch('rift.Controller.ProjectArchRepositories')
    def test_remove_packages(self, mock_parepository_class):
        """remove_packages() search, delete and update repository."""
        mock_parepository_objects = mock_parepository_class.return_value

        # Preparer Repository.search() return value
        rpm = RPM(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'materials',
                'pkg-1.0-1.src.rpm',
            )
        )
        mock_parepository_objects.working.search.return_value = [ rpm ]

        # Enable publish arg
        args = Mock()
        args.publish = True

        # Define a list of packages to remove
        pkgs_to_remove = [
            PackageRPM('pkg', self.config, self.staff, self.modules)
        ]

        # Define working_repo in configuration
        self.config.options['working_repo'] = '/path/to/working/repo'

        # Call remove_packages()
        remove_packages(self.config, args, pkgs_to_remove, 'x86_64')

        # Check Repository object has been instanciated
        mock_parepository_class.assert_called()
        # Check Repository.search() has been called
        mock_parepository_objects.working.search.assert_called_once_with(
            pkgs_to_remove[0].name
        )
        # Check Repository.delete() has been called
        mock_parepository_objects.working.delete.assert_called_once_with(rpm)
        # Check Repository.update() has been called
        mock_parepository_objects.working.update.assert_called_once()

    @patch('rift.Controller.ProjectArchRepositories')
    def test_remove_packages_noop(self, mock_parepository_class):
        """remove_packages() is noop if no publish arg or no working_repo"""
        pkgs_to_remove = []
        args = Mock()

        # publish is False, remove_packages() must be noop
        args.publish = False
        self.config.options['working_repo'] = '/path/to/working/repo'
        remove_packages(self.config, args, pkgs_to_remove, 'x86_64')
        mock_parepository_class.assert_called_once()
        mock_parepository_class.working.assert_not_called()

        # working_repo is not defined, remove_packages() must be noop
        args.publish = True
        del self.config.options['working_repo']
        mock_parepository_class.reset_mock()
        remove_packages(self.config, args, pkgs_to_remove, 'x86_64')
        mock_parepository_class.assert_called_once()
        mock_parepository_class.working.assert_not_called()


class ControllerProjectActionBuildTest(RiftProjectTestCase):
    """
    Tests class for Controller actions build, test and validate
    """
    def _check_qemuuserstatic(self):
        """Skip the test if none qemu-$arch-static executable is found for all
        architectures declared in project configuration."""
        if not any(
            [
                os.path.exists(f"/usr/bin/qemu-{arch}-static")
                for arch in self.config.get('arch')
            ]
        ):
            self.skipTest("qemu-user-static is not available")

    @patch('rift.package._project.PackageRPM', autospec=PackageRPM)
    def test_action_build(self, mock_pkg_rpm):

        # Declare supported archs.
        self.config.set('arch', ['x86_64', 'aarch64'])

        # Create temporary working repo and register its deletion at exit
        working_repo = make_temp_dir()
        atexit.register(shutil.rmtree, working_repo)

        self.config.set('working_repo', working_repo)
        self.update_project_conf()

        # Create fake package without build requirement
        self.make_pkg(build_requires=[])

        # Get PackageRPM instances mock
        mock_pkg_rpm_objs = mock_pkg_rpm.return_value
        # Initialize PackageRPM object attributes
        PackageRPM.__init__(
            mock_pkg_rpm_objs, 'pkg', self.config, self.staff, self.modules)
        # Make PackageRPM.supports_arch() return True for all archs
        mock_pkg_rpm_objs.supports_arch.return_value = True

        # Mock ActionableArchPackageRPM objects
        mock_act_arch_pkg_rpm = Mock(spec=ActionableArchPackageRPM)
        mock_pkg_rpm_objs.for_arch.return_value = mock_act_arch_pkg_rpm

        self.assertEqual(main(['build', 'pkg', '--publish']), 0)

        # Check RPM package supports_arch() method is called for all supported
        # archs.
        for arch in self.config.get('arch'):
            mock_pkg_rpm_objs.supports_arch.assert_any_call(arch)

        # Check actionable RPM package build(), publish() and clean() methods
        # are called for all supported arch (ie. twice).
        mock_act_arch_pkg_rpm.build.assert_has_calls(
            [call(sign=False, staging=None), call(sign=False, staging=None)])
        mock_act_arch_pkg_rpm.publish.assert_has_calls(
            [call(updaterepo=True), call(updaterepo=True)])
        mock_act_arch_pkg_rpm.clean.assert_has_calls([call(), call()])

        # Remove temporary working repo and unregister its deletion at exit
        shutil.rmtree(working_repo)
        atexit.unregister(shutil.rmtree)

    def test_action_build_publish_functional(self):
        """Functional RPM build and publish test"""
        # Declare supported archs and check qemu-user-static is available for
        # these architectures or skip the test.
        self.config.set('arch', ['x86_64', 'aarch64'])
        self._check_qemuuserstatic()

        # Create temporary working repo and register its deletion at exit
        working_repo = make_temp_dir()
        atexit.register(shutil.rmtree, working_repo)

        self.config.set('working_repo', working_repo)
        self.config.options['repos'] = VALID_REPOS
        self.update_project_conf()

        # Create fake package without build requirement
        self.make_pkg(build_requires=[])

        self.assertEqual(main(['build', 'pkg', '--publish']), 0)
        for arch in self.config.get('arch'):
            self.assertTrue(
                os.path.exists(f"{working_repo}/{arch}/pkg-1.0-1.noarch.rpm")
            )

        # Remove mock build environments
        self.clean_mock_environments()

        # Remove temporary working repo and unregister its deletion at exit
        shutil.rmtree(working_repo)
        atexit.unregister(shutil.rmtree)

    @patch('rift.package._project.PackageRPM', autospec=PackageRPM)
    def test_action_test(self, mock_pkg_rpm):

        # Declare supported archs.
        self.config.set('arch', ['x86_64', 'aarch64'])
        self.update_project_conf()

        # Create fake package without build requirement
        self.make_pkg(build_requires=[])

        # Get PackageRPM instances mock
        mock_pkg_rpm_objs = mock_pkg_rpm.return_value
        # Initialize PackageRPM object attributes
        PackageRPM.__init__(
            mock_pkg_rpm_objs, 'pkg', self.config, self.staff, self.modules)
        # Make PackageRPM.supports_arch() return True for all archs
        mock_pkg_rpm_objs.supports_arch.return_value = True
        # Mock ActionableArchPackageRPM objects
        mock_act_arch_pkg_rpm = Mock(spec=ActionableArchPackageRPM)
        mock_pkg_rpm_objs.for_arch.return_value = mock_act_arch_pkg_rpm
        # Make ActionableArchPackageRPM.test() return empty but successful test
        # results.
        mock_act_arch_pkg_rpm.test.return_value = TestResults()

        # Run test on package
        self.assertEqual(main(['test', 'pkg']), 0)

        # Check RPM package supports_arch() method is called for all supported
        # archs.
        for arch in self.config.get('arch'):
            mock_pkg_rpm_objs.supports_arch.assert_any_call(arch)

        # Check actionable RPM package test() method is called for all
        # supported arch (ie. twice).
        mock_act_arch_pkg_rpm.test.assert_has_calls(
            [call(noauto=False, noquit=False),
             call(noauto=False, noquit=False)])

    @patch('rift.Controller.create_staging_repo')
    @patch('rift.package._project.PackageRPM', autospec=PackageRPM)
    def test_action_validate(self, mock_pkg_rpm, mock_create_staging_repo):

        # Declare supported archs.
        self.config.set('arch', ['x86_64', 'aarch64'])
        self.update_project_conf()

        # Create fake package without build requirement
        self.make_pkg(build_requires=[])

        # Get PackageRPM instances mock
        mock_pkg_rpm_objs = mock_pkg_rpm.return_value
        # Initialize PackageRPM object attributes
        PackageRPM.__init__(
            mock_pkg_rpm_objs, 'pkg', self.config, self.staff, self.modules)
        # Make PackageRPM.supports_arch() return True for all archs
        mock_pkg_rpm_objs.supports_arch.return_value = True
        # Mock ActionableArchPackageRPM objects
        mock_act_arch_pkg_rpm = Mock(spec=ActionableArchPackageRPM)
        mock_pkg_rpm_objs.for_arch.return_value = mock_act_arch_pkg_rpm
        # MakeActionableArchPackageRPM.test() return empty but successful test
        # results.
        mock_act_arch_pkg_rpm.test.return_value = TestResults()
        # Mock create_staging_repo() to assert its return value is provided to
        # actional package methods.
        mock_staging_repo = Mock()
        mock_create_staging_repo.return_value = (mock_staging_repo, Mock())

        # Run validate on pkg
        self.assertEqual(main(['validate', 'pkg']), 0)

        # Check RPM package supports_arch() method is called for all supported
        # archs.
        for arch in self.config.get('arch'):
            mock_pkg_rpm_objs.supports_arch.assert_any_call(arch)

        # Check RPM package check() method is called for all supported arch
        # (ie. twice).
        mock_pkg_rpm_objs.check.assert_has_calls([call(), call()])

        # Check actionable RPM package build(), publish(staging), test() and
        # clean() methods are called for all supported arch (ie. twice).
        mock_act_arch_pkg_rpm.build.assert_has_calls(
            [call(sign=False, staging=mock_staging_repo),
             call(sign=False, staging=mock_staging_repo)])
        mock_act_arch_pkg_rpm.publish.assert_has_calls(
            [call(staging=mock_staging_repo), call(staging=mock_staging_repo)])
        mock_act_arch_pkg_rpm.test.assert_has_calls(
            [call(noauto=False, staging=mock_staging_repo, noquit=False),
             call(noauto=False, staging=mock_staging_repo, noquit=False)])
        mock_act_arch_pkg_rpm.clean.assert_has_calls(
            [call(noquit=False), call(noquit=False)])

    @patch('rift.Controller.PackagesDependencyGraph')
    def test_build_graph(self, mock_graph_class):
        """ Test build generates graph of packages dependencies with dependency tracking enabled. """
        # Enable dependency tracking in configuration
        self.config.set('dependency_tracking', True)
        self.update_project_conf()
        main(['build', 'pkg'])
        mock_graph_class.from_project.assert_called_once()

    @patch('rift.Controller.ProjectPackages')
    @patch('rift.Controller.PackagesDependencyGraph')
    def test_build_graph_tracking_disabled(self, mock_graph_class, mock_project_packages_class):
        """ Test build does not build graph of packages dependencies with dependency tracking disabled. """
        # Return empty list of packages with Package.list() to avoid actual
        # build iterations.
        mock_project_packages_class.list.return_value = []
        # By default, dependency tracking is disabled
        main(['build', 'pkg'])
        mock_graph_class.from_project.assert_not_called()

    @patch('rift.Controller.ProjectPackages')
    @patch('rift.Controller.PackagesDependencyGraph')
    def test_build_graph_skip_deps(self, mock_graph_class, mock_project_packages_class):
        """ Test build --skip-deps does not build graph of packages dependencies. """
        # Return empty list of packages with Package.list() to avoid actual
        # build iterations.
        mock_project_packages_class.list.return_value = []
        # Enable dependency tracking in configuration
        self.config.set('dependency_tracking', True)
        self.update_project_conf()
        main(['build', '--skip-deps', 'pkg'])
        mock_graph_class.from_project.assert_not_called()

    @patch('rift.Controller.PackagesDependencyGraph')
    def test_validate_graph(self, mock_graph_class):
        """ Test validate generates graph of packages dependencies with dependency tracking enabled. """
        # Enable dependency tracking in configuration
        self.config.set('dependency_tracking', True)
        self.update_project_conf()
        main(['validate', 'pkg'])
        mock_graph_class.from_project.assert_called_once()

    @patch('rift.Controller.ProjectPackages')
    @patch('rift.Controller.PackagesDependencyGraph')
    def test_validate_graph_tracking_disabled(self, mock_graph_class, mock_project_packages_class):
        """ Test validate does not build graph of packages dependencies with dependency tracking disabled. """
        # Return empty list of packages with Package.list() to avoid actual
        # build iterations.
        mock_project_packages_class.list.return_value = []
        # By default, dependency tracking is disabled
        main(['validate', 'pkg'])
        mock_graph_class.from_project.assert_not_called()

    @patch('rift.Controller.ProjectPackages')
    @patch('rift.Controller.PackagesDependencyGraph')
    def test_validate_graph_skip_deps(self, mock_graph_class, mock_project_packages_class):
        """ Test validate --skip-deps does not build graph of packages dependencies. """
        # Return empty list of packages with Package.list() to avoid actual
        # build iterations.
        mock_project_packages_class.list.return_value = []
        self.config.set('dependency_tracking', True)
        self.update_project_conf()
        main(['validate', '--skip-deps', 'pkg'])
        mock_graph_class.from_project.assert_not_called()

    def test_get_packages_to_build_tracking_disabled(self):
        """ Test get_packages_to_build() with tracking disabled (by default) returns user provided packages. """
        args = Mock()
        args.skip_deps = False
        args.packages = ['pkg']
        pkgs = get_packages_to_build(
            self.config, self.staff, self.modules, args
        )
        self.assertEqual([pkg.name for pkg in pkgs], ['pkg'])

    def test_get_packages_to_build_skip_deps(self):
        """ Test get_packages_to_build() with skip deps (tracking enabled) returns user provided packages. """
        self.config.set('dependency_tracking', True)
        args = Mock()
        args.skip_deps = True
        args.packages = ['pkg']
        pkgs = get_packages_to_build(
            self.config, self.staff, self.modules, args
        )
        self.assertEqual([pkg.name for pkg in pkgs], ['pkg'])

    def test_get_packages_to_build_no_package(self):
        """ Test get_packages_to_build() (tracking enabled, w/o skip deps) returns empty with unexisting package. """
        self.config.set('dependency_tracking', True)
        args = Mock()
        args.skip_deps = False
        args.packages = ['pkg']
        pkgs = get_packages_to_build(
            self.config, self.staff, self.modules, args
        )
        # Package 'pkg' does not exist in project directory, graph solving must
        # return an empty list.
        self.assertEqual(pkgs, [])

    def test_get_packages_to_build_package_order(self):
        """ Test get_packages_to_build() returns correctly ordered list of reverse dependencies. """
        self.make_pkg(
            name='libone',
            build_requires=['libtwo-devel'],
            subpackages=[
                SubPackage('libone-bin'),
                SubPackage('libone-devel')
            ]
        )
        self.make_pkg(
            name='libtwo',
            subpackages=[
                SubPackage('libtwo-bin'),
                SubPackage('libtwo-devel')
            ]
        )
        self.make_pkg(
            name='my-software',
            build_requires=['libone-devel, libtwo-devel']
        )
        # Enable tracking, disable --skip-deps
        self.config.set('dependency_tracking', True)
        args = Mock()
        args.skip_deps = False
        args.packages = ['libone']
        pkgs = get_packages_to_build(
            self.config, self.staff, self.modules, args
        )
        self.assertEqual(
            [pkg.name for pkg in pkgs], ['libone', 'my-software']
        )
        args.skip_deps = False
        args.packages = ['libone', 'libtwo']
        pkgs = get_packages_to_build(
            self.config, self.staff, self.modules, args
        )
        # Package libone must be present after libtwo and my-software must be
        # present after both libtwo and libone in the order list of build
        # requirements.
        self.assertEqual(
            [pkg.name for pkg in pkgs], ['libtwo', 'libone', 'my-software']
        )

    def test_get_packages_to_build_cyclic_deps(self):
        """ Test get_packages_to_build() returns correctly ordered list of reverse dependencies. """
        self.make_pkg(
            name='libone',
            metadata={
                'depends': 'libtwo'
            }
        )
        self.make_pkg(
            name='libtwo',
            metadata={
                'depends': 'libthree'
            }
        )
        self.make_pkg(
            name='libthree',
            metadata={
                'depends': 'libone'
            }
        )
        # Enable tracking, disable --skip-deps
        self.config.set('dependency_tracking', True)
        args = Mock()
        args.skip_deps = False
        args.packages = ['libone']
        with self.assertLogs(level="DEBUG") as cm:
            pkgs = get_packages_to_build(
                self.config, self.staff, self.modules, args
            )
        # Package libone must be present after libtwo and my-software must be
        # present after both libtwo and libone in the order list of build
        # requirements.
        self.assertCountEqual(
            [pkg.name for pkg in pkgs], ['libthree', 'libtwo', 'libone']
        )
        self.assertIn(
            'DEBUG:root:       ⥀ Loop detected on node libone at depth 2: libone→libthree→libtwo→libone',
            cm.output
        )


class ControllerProjectActionVMTest(RiftProjectTestCase):
    """
    Tests class for Controller action vm
    """
    @patch('rift.Controller.VM')
    def test_vm_arch_option(self, mock_vm_class):
        """Test vm --arch option required with multiple supported archs."""
        # With only one supported architecture in project, --arch argument must
        # not be required.
        main(['vm', 'connect'])

        # Define multiple supported architectures.
        self.config.set('arch', ['x86_64', 'aarch64'])
        self.update_project_conf()

        # With multiple supported architectures, --arch argument must be
        # required.
        with self.assertRaisesRegex(
            RiftError,
            "^VM architecture must be defined with --arch argument.*$"
        ):
            main(['vm', 'connect'])

        # It should run without error with --arch.
        main(['vm', '--arch', 'x86_64', 'connect'])

        # Test invalid value of --arch argument is reported.
        with self.assertRaisesRegex(
            RiftError,
            "^Project does not support architecture 'fail'$"
        ):
            main(['vm', '--arch', 'fail', 'connect'])

        # Remove mock build environment
        self.clean_mock_environments()

    @patch('rift.Controller.VM')
    def test_action_vm_build(self, mock_vm_class):
        """simple 'rift vm build' is ok """

        mock_vm_objects = mock_vm_class.return_value
        mock_vm_objects.image_is_remote.return_value = False
        mock_vm_objects.image_local = 'test.qcow2'

        main(['vm', 'build', 'http://image', '--deploy'])
        # check VM class has been instanciated
        mock_vm_class.assert_called()

        mock_vm_objects.build.assert_called_once_with(
            'http://image', False, False, 'test.qcow2'
        )
        mock_vm_objects.build.reset_mock()
        main(['vm', 'build', 'http://image', '--deploy', '--force'])
        mock_vm_objects.build.assert_called_once_with(
            'http://image', True, False, 'test.qcow2'
        )
        mock_vm_objects.build.reset_mock()
        main(['vm', 'build', 'http://image', '--deploy', '--keep'])
        mock_vm_objects.build.assert_called_once_with(
            'http://image', False, True, 'test.qcow2'
        )
        mock_vm_objects.build.reset_mock()
        main(
            ['vm', 'build', 'http://image', '--output', 'OUTPUT.img', '--force']
        )
        mock_vm_objects.build.assert_called_once_with(
            'http://image', True, False, 'OUTPUT.img'
        )
        mock_vm_objects.build.reset_mock()
        with self.assertRaisesRegex(
            RiftError, "^Either --deploy or -o,--output option must be used$"
        ):
            main(['vm', 'build', 'http://image'])
        with self.assertRaisesRegex(
            RiftError,
            "^Both --deploy and -o,--output options cannot be used together$",
        ):
            main(
                [
                    'vm',
                    'build',
                    'http://image',
                    '--deploy',
                    '--output',
                    'OUTPUT.img',
                ]
            )
        # Test --deploy with remote image
        mock_vm_objects.image_is_remote.return_value = True
        with self.assertRaisesRegex(
            RiftError,
            "^Cannot build VM image with remote image URL and --deploy option, -o, "
            "--output option must be used$"
        ):
            main(['vm', 'build', 'http://image', '--deploy'])


    def test_vm_build_and_validate(self):
        """Test VM build and validate package"""
        self.skipTest("Too much instability")
        if not os.path.exists("/usr/bin/qemu-img"):
            self.skipTest("qemu-img is not available")
        self.config.options['vm']['images_cache'] = GLOBAL_CACHE
        # Reduce memory size from default 8GB to 2GB because it is sufficient to
        # run this VM and it largely reduces storage required by virtiofs memory
        # backend file which is the same size as the VM memory, thus reducing
        # the risk to fill up small partitions when running the tests.
        self.config.options['vm']['memory'] = 2048
        self.config.options['proxy'] = PROXY
        self.config.options['repos'] = {
            'os': {
                'url': (
                    'https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/'
                ),
                'priority': 90
            },
            'updates': {
                'url': (
                    'https://repo.almalinux.org/almalinux/8/AppStream/x86_64/'
                    'os/'
                ),
                'priority': 90
            },
            'extras':  {
                'url': (
                    'https://repo.almalinux.org/almalinux/8/PowerTools/x86_64/'
                    'os/'
                ),
                'priority': 90
            }
        }
        # Enable virtiofs that is natively supported by Alma without requirement
        # of additional RPM.
        self.config.options['shared_fs_type'] = 'virtiofs'
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        # Copy example cloud-init template
        self.copy_cloud_init_tpl()
        # Copy example build post script
        self.copy_build_post_script()
        # Ensure cache directory exists
        self.ensure_vm_images_cache_dir()
        # Build virtual machine image
        main(['vm', 'build', VALID_IMAGE_URL['x86_64'], '--deploy'])
        # Create source package and launch validation on fresh VM image
        pkg = 'pkg'
        self.make_pkg(name=pkg, build_requires=[], requires=[])
        main(['validate', pkg])
        # Remove mock build environments
        self.clean_mock_environments()


class ControllerProjectActionSignTest(RiftProjectTestCase):
    """
    Tests class for Controller action sign
    """
    def test_action_sign(self):
        """ Test sign package """
        gpg_home = os.path.join(self.projdir, '.gnupg')

        # Launch GPG agent for this test
        cmd = [
          'gpg-agent',
          '--homedir',
          gpg_home,
          '--daemon',
        ]
        subprocess.run(cmd)

        # Generate keyring
        gpg_key = 'rift'
        cmd = [
            'gpg',
            '--homedir',
            gpg_home,
            '--batch',
            '--passphrase',
            '',
            '--quick-generate-key',
            gpg_key,
        ]
        subprocess.run(cmd)

        # Update project configuration with generated key
        self.config.options.update(
            {
                'gpg': {
                    'keyring': gpg_home,
                    'key': gpg_key,
                }
            }
        )
        self.update_project_conf()

        # Path of RPM packages assets
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        original_bin_rpm = os.path.join(
            tests_dir, 'materials', 'pkg-1.0-1.noarch.rpm'
        )
        original_src_rpm = os.path.join(
            tests_dir, 'materials', 'pkg-1.0-1.src.rpm'
        )

        # Copy RPM packages assets in temporary project directory
        copy_bin_rpm = os.path.join(self.projdir, os.path.basename(original_bin_rpm))
        shutil.copy(original_bin_rpm, copy_bin_rpm)
        copy_src_rpm = os.path.join(self.projdir, os.path.basename(original_src_rpm))
        shutil.copy(original_src_rpm, copy_src_rpm)

        # Load packages and check they are not signed
        bin_rpm = RPM(copy_bin_rpm, self.config)
        src_rpm = RPM(copy_src_rpm, self.config)
        self.assertFalse(bin_rpm.is_signed)
        self.assertFalse(src_rpm.is_signed)

        # Launch rift sign
        os.environ['GNUPGHOME'] = gpg_home
        self.assertEqual(main(['sign', copy_bin_rpm, copy_src_rpm]), 0)
        del os.environ['GNUPGHOME']

        # Reload packages and check they are signed now
        bin_rpm._load()
        src_rpm._load()
        self.assertTrue(bin_rpm.is_signed)
        self.assertTrue(src_rpm.is_signed)

        # Kill GPG agent launched for the test
        cmd = ['gpgconf', '--homedir', gpg_home, '--kill', 'gpg-agent']
        subprocess.run(cmd)

        # Remove copy of packages assets
        os.unlink(copy_bin_rpm)
        os.unlink(copy_src_rpm)

        # Remove temporary GPG home with generated key
        shutil.rmtree(gpg_home)

class ControllerProjectActionSyncTest(RiftProjectTestCase):
    """
    Tests class for Controller action sync
    """
    @patch('rift.sync.RepoSyncBase.run')
    @patch('sys.stdout', new_callable=StringIO)
    def test_action_sync_skip_repo_wo_params(self, mock_stdout, mock_reposyncbase_run):
        """ Test rift runs sync action skips repo without synchronization parameters. """
        sync_parent = make_temp_dir()
        sync_output = os.path.join(sync_parent, 'output')
        self.config.set('arch', ['x86_64'])

        self.config.options['sync_output'] = sync_output
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                    'subdir': '$arch',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'url': 'https://server2/repo2',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        # Run sync and check debug log is emited to indicate repo2 is skipped.
        with self.assertLogs(level='DEBUG') as log:
            main(['sync'])
            self.assertIn(
                'WARNING:root:x86_64: Skipping repository repo2: no '
                'synchronization parameters found',
                log.output
            )
        # RepoSyncBase.run() must have been called once for repo1.
        self.assertEqual(mock_reposyncbase_run.call_count, 1)
        self.assertIn(
            '** x86_64: Synchronizing repository repo1: '
            'https://server1/repo1/x86_64 **',
            mock_stdout.getvalue()
        )
        # Clean synchronization output parent
        shutil.rmtree(sync_parent)

    @patch('rift.Controller.RepoSyncFactory')
    def test_action_sync(self, mock_reposync):
        """ Test rift runs sync action with or without sync conf. """
        # First run sync without sync conf nor -o, --output argument.
        # Check warning message log is emitted
        with self.assertLogs(level='INFO') as log:
            main(['sync'])
            self.assertIn(
                'ERROR:root:Synchronization output directory must be defined '
                'with sync_output parameter in Rift configuration or -o, '
                '--output command line option to synchronize repositories',
                log.output
            )
        # Check factory is not called
        self.assertEqual(mock_reposync.get.call_count, 0)

        # Create temporary synchronization output parent directory
        sync_parent = make_temp_dir()
        sync_output = os.path.join(sync_parent, 'output')

        # Add repositories with synchronization parameters in conf.
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'sync': {
                    'source': 'https://server2/repo2',
                },
                'url': 'https://server2/repo2',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()

        # Run with --output parameter (without sync_output in conf)
        main(['sync', '--output', sync_output])

        # Check factory has been called twice, for repo1 and repo2
        self.assertEqual(mock_reposync.get.call_count, 2)
        # Check output directory has been created
        self.assertTrue(os.path.isdir(sync_output))
        # Clean synchronization output directory
        shutil.rmtree(sync_output)

        # Reset mock to check the second run.
        mock_reposync.get.reset_mock()

        # Add sync_output parameter in conf.
        self.config.options['sync_output'] = sync_output
        self.update_project_conf()

        # Run sync without -o, --output parameter.
        main(['sync'])
        # Check factory has been called twice, for repo1 and repo2
        self.assertEqual(mock_reposync.get.call_count, 2)
        # Check output directory has been created
        self.assertTrue(os.path.isdir(sync_output))
        # Clean synchronization output parent
        shutil.rmtree(sync_parent)

    @patch('rift.sync.RepoSyncBase.run')
    @patch('sys.stdout', new_callable=StringIO)
    def test_action_sync_multiarch(self, mock_stdout, mock_reposyncbase_run):
        """ Test rift runs sync action with multiple architectures. """
        sync_parent = make_temp_dir()
        sync_output = os.path.join(sync_parent, 'output')
        self.config.set('arch', ['x86_64', 'aarch64'])

        self.config.options['sync_output'] = sync_output
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                    'subdir': '$arch',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'sync': {
                    'source': 'https://server2/$arch',
                },
                'url': 'https://server2/$arch',
            },
            'repo3': {
                'sync': {
                    'source': 'https://server3/repo3',
                },
                'url': 'https://server3/repo3',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        # Run sync and check debug log is emited to indicate repo3 is skipped
        # with the 2nd architecture (as the URL is the same as for the 1st
        # arch).
        with self.assertLogs(level='DEBUG') as log:
            main(['sync'])
            self.assertIn(
                'DEBUG:root:Skipping already synchronized source '
                'https://server3/repo3/',
                log.output
            )
        # RepoSyncBase.run() must have been called 5 times:
        # - 2 calls for repo1
        # - 2 calls for repo2
        # - 1 call for repo3
        self.assertEqual(mock_reposyncbase_run.call_count, 5)
        self.assertIn(
            '** x86_64: Synchronizing repository repo1: '
            'https://server1/repo1/x86_64 **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** aarch64: Synchronizing repository repo1: '
            'https://server1/repo1/aarch64 **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** x86_64: Synchronizing repository repo2: '
            'https://server2/x86_64/ **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** aarch64: Synchronizing repository repo2: '
            'https://server2/aarch64/ **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** x86_64: Synchronizing repository repo3: '
            'https://server3/repo3/ **',
            mock_stdout.getvalue()
        )
        # Clean synchronization output parent
        shutil.rmtree(sync_parent)

    def test_action_sync_missing_output_parent(self):
        """ Test rift raises RiftError when sync output parent is not found. """
        sync_output = "/tmp/rift/output"
        self.config.options['sync_output'] = sync_output
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'sync': {
                    'source': 'https://server2/repo2',
                },
                'url': 'https://server2/repo2',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        with self.assertRaisesRegex(
            RiftError,
            "Unable to create repositories synchronization directory "
            "/tmp/rift/output, parent directory /tmp/rift does not exist."
        ):
            main(['sync'])


class ControllerProjectActionGraphTest(RiftProjectTestCase):
    """
    Tests class for Controller action graph
    """

    def test_get_packages_in_graph(self):
        """ Test get_packages_in_graph(). """
        self.make_pkg(
            name='libone',
            metadata={'module': 'Great module'},
        )
        self.make_pkg(
            name='libtwo',
            metadata={'module': 'Great module'},
        )
        self.make_pkg(
            name='my-software',
            metadata={'module': 'Other module'},
        )
        args = Mock()
        args.module = 'Great module'
        args.packages = []
        self.assertCountEqual(
            get_packages_in_graph(args, self.config, self.staff, self.modules),
            ['libone', 'libtwo']
        )
        args.module = None
        args.packages = ['libone', 'my-software']
        self.assertCountEqual(
            get_packages_in_graph(args, self.config, self.staff, self.modules),
            ['libone', 'my-software']
        )
        # When module arg is not set and packages args is empty,
        # get_packages_in_graph() must return an empty list. This empty list
        # eventually means all projects packages when passed to
        # PackagesDependencyGraph.draw().
        args.module = None
        args.packages = []
        self.assertCountEqual(
            get_packages_in_graph(args, self.config, self.staff, self.modules),
            []
        )
        args.module = 'fail'
        args.packages = []
        with self.assertRaisesRegex(RiftError, r"^Invalid module name fail$"):
            get_packages_in_graph(args, self.config, self.staff, self.modules)


class ControllerProjectActionGerritTest(RiftProjectTestCase):
    """
    Tests class for Controller action gerrit
    """

    def test_gerrit_missing_patch_change_patchset(self):
        """gerrit without patch, change or patchset fails"""
        for cmd in (['gerrit', '--change', '1', '--patchset', '2'],
                    ['gerrit', '--patchset', '2', '/dev/null'],
                    ['gerrit', '--change', '1', '/dev/null']):
            with self.assertRaisesRegex(SystemExit, "2"):
                main(cmd)

    @patch('rift.Controller.Review')
    def test_gerrit(self, mock_review):
        """simple gerrit"""
        self.make_pkg()
        patch = make_temp_file(
            textwrap.dedent("""
                diff --git a/packages/pkg/pkg.spec b/packages/pkg/pkg.spec
                index d1a0d0e7..b3e36379 100644
                --- a/packages/pkg/pkg.spec
                +++ b/packages/pkg/pkg.spec
                @@ -1,6 +1,6 @@
                 Name:    pkg
                 Version:        1.0
                -Release:        1
                +Release:        2
                 Summary:        A package
                 Group:          System Environment/Base
                 License:        GPL
                """))
        main(['gerrit', '--change', '1', '--patchset', '2', patch.name])
        # Check review has not been invalidated and pushed
        mock_review.return_value.invalidate.assert_not_called()
        mock_review.return_value.push.assert_called_once()

    @patch('rift.Controller.Review')
    def test_gerrit_review_invalidated(self, mock_review):
        """gerrit review invalidated"""
        # Make package and inject rpmlint error ($RPM_BUILD_ROOT and
        # RPM_SOURCE_DIR in buildsteps) in RPM spec file, with both rpmlint v1
        # and v2.
        self.make_pkg()
        with open(self.pkgspecs['pkg'], "w") as spec:
            spec.write(
                gen_rpm_spec(
                    name='pkg',
                    version='1.0',
                    release='2',
                    arch='noarch',
                    buildsteps="$RPM_SOURCE_DIR\n$RPM_BUILD_ROOT",
                )
            )
        patch = make_temp_file(
            textwrap.dedent("""
                diff --git a/packages/pkg/pkg.spec b/packages/pkg/pkg.spec
                index d1a0d0e7..b3e36379 100644
                --- a/packages/pkg/pkg.spec
                +++ b/packages/pkg/pkg.spec
                @@ -1,6 +1,6 @@
                 Name:    pkg
                 Version:        1.0
                -Release:        1
                +Release:        2
                 Summary:        A package
                 Group:          System Environment/Base
                 License:        GPL
                """))
        main(['gerrit', '--change', '1', '--patchset', '2', patch.name])
        # Check review has been invalidated and pushed
        mock_review.return_value.invalidate.assert_called_once()
        mock_review.return_value.push.assert_called_once()


class ControllerProjectActionChangelogTest(RiftProjectTestCase):
    """
    Tests class for Controller action changelog
    """

    def test_action_changelog_without_pkg(self):
        """changelog without package fails """
        with self.assertRaisesRegex(SystemExit, "2"):
            main(['changelog'])

    def test_action_changelog_without_comment(self):
        """changelog without comment fails """
        with self.assertRaisesRegex(SystemExit, "2"):
            main(['changelog', 'pkg'])

    def test_action_changelog_without_maintainer(self):
        """changelog without maintainer """
        with self.assertRaisesRegex(RiftError, "You must specify a maintainer"):
            main(['changelog', 'pkg', '-c', 'basic change'])

    def test_action_changelog_pkg_not_found(self):
        """changelog package not found"""
        with self.assertRaisesRegex(
            RiftError,
            "Package 'pkg' directory does not exist"):
            main(['changelog', 'pkg', '-c', 'basic change', '-t', 'Myself'])

    def test_action_changelog(self):
        """simple changelog"""
        self.make_pkg()
        self.assertEqual(
            main(['changelog', 'pkg', '-c', 'basic change', '-t', 'Myself']), 0)
        spec = Spec(filepath=self.pkgspecs['pkg'])
        spec.load()
        self.assertEqual(spec.changelog_name, 'Myself <buddy@somewhere.org> - 1.0-1')
        self.assertEqual(spec.version, '1.0')
        self.assertEqual(spec.release, '1')

    def test_action_changelog_bump(self):
        """simple changelog with bump"""
        self.make_pkg()
        self.assertEqual(
            main(['changelog', 'pkg', '-c', 'basic change', '-t', 'Myself', '--bump']),
            0)
        spec = Spec(filepath=self.pkgspecs['pkg'])
        spec.load()
        self.assertEqual(spec.changelog_name, 'Myself <buddy@somewhere.org> - 1.0-2')
        self.assertEqual(spec.version, '1.0')
        self.assertEqual(spec.release, '2')

    def test_action_changelog_unknown_maintainer(self):
        """changelog with unknown maintainer"""
        self.make_pkg()
        with self.assertRaisesRegex(
            RiftError, "Unknown maintainer Fail, cannot be found in staff"
        ):
            main(['changelog', 'pkg', '-c', 'basic change', '-t', 'Fail'])


class ControllerArgumentsTest(RiftTestCase):
    """ Arguments parsing tests for Controller module"""

    def test_make_parser_updaterepo(self):
        """ Test option parsing """
        args = ["build", "a_package", "--dont-update-repo"]
        parser = make_parser()
        opts = parser.parse_args(args)
        self.assertFalse(opts.updaterepo)

    def test_make_parser_vm(self):
        """ Test vm command options parsing """
        parser = make_parser()

        args = ['vm', '--arch', 'x86_64']
        opts = parser.parse_args(args)
        self.assertEqual(opts.command, 'vm')

        args = ['vm', 'start']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'start')
        self.assertFalse(opts.force)

        args = ['vm', 'start', '--force']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'start')
        self.assertTrue(opts.force)

        args = ['vm', 'connect']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'connect')

        args = ['vm', '--arch', 'x86_64', 'connect']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'connect')

        args = ['vm', 'build']
        # This must fail due to missing image URL
        with self.assertRaises(SystemExit):
            parser.parse_args(args)

        args = ['vm', 'build', 'http://image']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'build')
        self.assertEqual(opts.url, 'http://image')
        self.assertFalse(opts.force)

        args = ['vm', 'build', 'http://image', '--force']
        opts = parser.parse_args(args)
        self.assertTrue(opts.force)

        args = ['vm', 'build', 'http://image', '--deploy']
        opts = parser.parse_args(args)
        self.assertTrue(opts.deploy)

        OUTPUT_IMG = 'OUTPUT'

        args = ['vm', 'build', 'http://image', '-o', OUTPUT_IMG]
        opts = parser.parse_args(args)
        self.assertEqual(opts.output, OUTPUT_IMG)

        args = ['vm', 'build', 'http://image', '--output', OUTPUT_IMG]
        opts = parser.parse_args(args)
        self.assertEqual(opts.output, OUTPUT_IMG)

        # This must fail due to missing output filename
        args = ['vm', 'build', 'http://image', '--output']
        with self.assertRaises(SystemExit):
            parser.parse_args(args)
