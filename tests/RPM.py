#
# Copyright (C) 2020 CEA
#
import os
import time
import rpm
import shutil
import subprocess

from TestUtils import (
    make_temp_dir,
    gen_rpm_spec,
    RiftTestCase,
    RiftProjectTestCase,
)
from rift import RiftError
from rift.RPM import Spec, Variable, RPMLINT_CONFIG_V1, RPMLINT_CONFIG_V2, RPM, rpmlint_v2

class SpecTest(RiftTestCase):
    """
    Tests class for Spec
    """

    def setUp(self):
        self.name='pkg'
        self.version='1.0'
        self.release='1'
        self.arch='noarch'
        # /tmp/rift-*/pkg.spec
        self.directory = make_temp_dir()
        self.spec = os.path.join(self.directory, "{0}.spec".format(self.name))
        self.prepsteps = ""
        self.buildsteps = ""
        self.installsteps = ""
        self.files = ""
        self.exclusive_arch = None
        self.update_spec()


    def update_spec(self):
        with open(self.spec, "w") as spec:
            spec.write(
                gen_rpm_spec(
                    name=self.name,
                    version=self.version,
                    release=self.release,
                    arch=self.arch,
                    prepsteps=self.prepsteps,
                    buildsteps=self.buildsteps,
                    installsteps=self.installsteps,
                    files=self.files,
                    exclusive_arch=self.exclusive_arch,
                )
            )

    def tearDown(self):
        os.unlink(self.spec)
        os.rmdir(self.directory)


    def test_init(self):
        """ Test Spec instanciation """
        spec = Spec(self.spec)
        self.assertTrue(self.name in spec.pkgnames)
        self.assertEqual(len(spec.pkgnames), 1)
        self.assertEqual(spec.exclusive_archs, [])
        self.assertEqual(spec.arch, self.arch)
        self.assertTrue("{0}-{1}.tar.gz".format(self.name, self.version) in spec.sources)
        self.assertEqual(len(spec.lines), 42)

    def test_init_fails(self):
        """ Test Spec instanciation with error """
        path = '/nowhere.spec'
        self.assert_except(RiftError, "{0} does not exist".format(path), Spec, path)


    def test_specfile_check(self):
        """ Test specfile check function """
        self.assertIsNone(Spec(self.spec).check())


    def test_specfile_check_with_rpmlint_v1(self):
        """ Test specfile check function with a custom rpmlint v1 file"""
        # Make an errorneous specfile with hardcoded /lib
        if rpmlint_v2():
            self.skipTest("This test requires rpmlint v1")
        self.files = "/lib/test"
        self.update_spec()
        with self.assertRaisesRegex(RiftError, 'rpmlint reported errors'):
            Spec(self.spec).check()

        # Create rpmlint config to ignore hardcoded library path
        rpmlintfile = os.sep.join([self.directory, RPMLINT_CONFIG_V1])
        with open(rpmlintfile, "w") as rpmlint:
            rpmlint.write('addFilter("E: hardcoded-library-path")')
        self.assertIsNone(Spec(self.spec).check())
        os.unlink(rpmlintfile)

    def test_specfile_check_with_rpmlint_v2(self):
        """ Test specfile check function with a custom rpmlint v2 file"""
        if not rpmlint_v2():
            self.skipTest("This test requires rpmlint v2")
        self.buildsteps = "$RPM_BUILD_ROOT"
        self.update_spec()

        with self.assertRaisesRegex(RiftError, 'rpmlint reported errors'):
            Spec(self.spec).check()

        # Create rpmlint config file to ignore rpm-buildroot-usage
        rpmlintfile = os.sep.join([self.directory, RPMLINT_CONFIG_V2])
        with open(rpmlintfile, "w") as rpmlint:
            rpmlint.write('Filters = ["rpm-buildroot-usage"]')
        self.assertIsNone(Spec(self.spec).check())
        os.unlink(rpmlintfile)

    def test_bump_release(self):
        """ Test bump_release """
        spec = Spec(self.spec)
        spec.release = '1'
        spec.bump_release()
        self.assertEqual(spec.release, '2')
        # Check with %dist macro
        dist = rpm.expandMacro('%dist')
        spec.release = "1{}".format(dist)
        spec.bump_release()
        self.assertEqual(spec.release, '2{}'.format(dist))
        # Check with prefix in release
        spec.release = "1.keyword1{}".format(dist)
        spec.bump_release()
        self.assertEqual(spec.release, '1.keyword2{}'.format(dist))
        # Check with invalid release
        spec.release = 'a'
        self.assert_except(RiftError,
                           'Cannot parse package release: {}'.format(spec.release),
                           spec.bump_release)

    def test_add_changelog_entry(self):
        """ Test add_changelog_entry """
        spec = Spec(self.spec)
        comment = "- New feature"
        userstr = "John Doe"
        date = time.strftime("%a %b %d %Y", time.gmtime())

        # Check adding changelog entry
        spec.add_changelog_entry(userstr, comment)
        with open(spec.filepath, 'r') as fspec:
            lines = fspec.readlines()
        self.assertTrue("* {} {} - {}\n".format(date, userstr, spec.evr) in lines)
        self.assertTrue("{}\n".format(comment) in lines)

    def test_add_changelog_entry_bump(self):
        """ Test add_changelog_entry with bump release"""
        spec = Spec(self.spec)
        comment = "- New feature (Bumped)"
        userstr = "John Doe"
        date = time.strftime("%a %b %d %Y", time.gmtime())

        spec.add_changelog_entry(userstr, comment, bump=True)
        with open(spec.filepath, 'r') as fspec:
            lines = fspec.readlines()
        self.assertTrue("Release:        {}\n".format(spec.release) in lines)
        self.assertTrue("* {} {} - {}\n".format(date, userstr, spec.evr) in lines)
        self.assertTrue("{}\n".format(comment) in lines)


    def test_parse_vars(self):
        """ Test spec variables parsing """
        spec = Spec(self.spec)
        self.assertTrue(str(spec.variables['foo']) == '1.%{bar}')
        self.assertTrue(spec.variables['foo'].value == '1.%{bar}')
        self.assertTrue(spec.variables['foo'].name == 'foo')
        self.assertTrue(spec.variables['foo'].index == 0)
        self.assertTrue(spec.variables['foo'].keyword == 'global')
        self.assertTrue(str(spec.variables['bar']) == '1')
        self.assertTrue(spec.variables['bar'].keyword == 'define')
        self.assertTrue(spec.variables['bar'].index == 1)

    def test_match_var(self):
        """ Tests variable detection in pattern """
        spec = Spec(self.spec)
        foo = spec.variables['foo']
        bar = spec.variables['bar']
        self.assertTrue(spec._match_var('%{foo}', r'^1') == foo)
        self.assertTrue(spec._match_var('%{foo}') == bar)
        self.assertTrue(spec._match_var('%{?foo}') == bar)
        self.assertTrue(spec._match_var('%{foo}%{bar}') == bar)
        self.assertTrue(spec._match_var('%{bar}') == bar)
        self.assertTrue(spec._match_var('%{notthere}') is None)
        self.assertTrue(spec._match_var('%{notthere}%{foo}') == bar)
        self.assertTrue(spec._match_var('%{foo}%{?dist}') == bar)
        self.assertTrue(spec._match_var('%{foo}%{bar}%{?dist}') == bar)
        self.assertTrue(spec._match_var('no vars inside') is None)

    def test_supports_arch_w_exclusive_arch(self):
        """ Test supports_arch() with ExclusiveArch"""
        self.exclusive_arch = "x86_64"
        self.update_spec()
        spec = Spec(self.spec)
        self.assertTrue(spec.supports_arch('x86_64'))
        self.assertFalse(spec.supports_arch('aarch64'))

    def test_supports_arch_wo_exclusive_arch(self):
        """ Test supports_arch() without ExclusiveArch"""
        spec = Spec(self.spec)
        self.assertTrue(spec.supports_arch('x86_64'))
        self.assertTrue(spec.supports_arch('aarch64'))

class VariableTest(RiftTestCase):
    """ Test Variable class """
    def test_str(self):
        """ Test string representation """
        var = Variable(index=3, name='foo', value='bar', keyword='define')
        self.assertTrue(str(var) == 'bar' )

    def test_spec_output(self):
        """ Test variable format output """
        var = Variable(index=0, name='foo', value='bar', keyword='define')
        self.assertTrue(var.spec_output() == '%define foo bar' )
        buff = ['']
        var.spec_output(buff)
        self.assertTrue(buff[0] == '%define foo bar\n')


class RPMTest(RiftProjectTestCase):
    """ Test RPM class """
    def setUp(self):
        super().setUp()
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_rpm = os.path.join(
            tests_dir, 'materials', 'pkg-1.0-1.noarch.rpm'
        )
        self.src_rpm = os.path.join(
            tests_dir, 'materials', 'pkg-1.0-1.src.rpm'
        )

    def test_load(self):
        """RPM initializer works with bin/src RPM with/without conf."""
        # test load bin RPM without config
        rpm = RPM(self.bin_rpm)
        self.assertEqual(rpm.name, 'pkg')
        self.assertEqual(rpm.arch, 'noarch')
        self.assertEqual(rpm.is_source, False)

        # test load src RPM with config
        rpm = RPM(self.src_rpm, self.config)
        self.assertEqual(rpm.name, 'pkg')
        self.assertEqual(rpm.arch, 'noarch')
        self.assertEqual(rpm.is_source, True)

    def test_extract_srpm(self):
        """RPM.extract_srpm() extracts files from source RPM."""
        rpm = RPM(self.src_rpm, self.config)
        specdir = make_temp_dir()
        srcdir = make_temp_dir()

        # Extract source RPM
        rpm.extract_srpm(specdir, srcdir)

        # Verify files have been properly extracted
        for spec in ['pkg.spec', 'pkg.spec.orig']:
            self.assertTrue(os.path.exists(os.path.join(specdir, spec)))
        self.assertTrue(os.path.exists(os.path.join(srcdir, 'pkg-1.0.tar.gz')))

        # Clean up everything
        shutil.rmtree(specdir)
        shutil.rmtree(srcdir)

    def test_extract_srpm_on_bin(self):
        """RPM.extract_srpm() raises assertion error with binary RPM."""
        rpm = RPM(self.bin_rpm, self.config)
        with self.assertRaises(AssertionError):
            rpm.extract_srpm(None, None)

    def test_sign_no_conf(self):
        """RPM.sign() fail with nonexistent keyring."""
        rpm = RPM(self.src_rpm, self.config)
        with self.assertRaisesRegex(
            RiftError,
            "^Unable to retrieve GPG configuration, unable to sign package "
            ".*\.rpm$"
        ):
            rpm.sign()

    def test_sign_no_keyring(self):
        """RPM.sign() fail with nonexistent keyring."""
        self.config.options.update(
            {
                'gpg': {
                  'keyring': '/path/to/nonexistent/keyring',
                  'key': 'rift',
                }
            }
        )
        self.config._check()
        rpm = RPM(self.src_rpm, self.config)
        with self.assertRaisesRegex(
            RiftError,
            "^GPG keyring path /path/to/nonexistent/keyring does not exist, "
            "unable to sign package .*\.rpm$"
        ):
            rpm.sign()

    def sign_copy(self, gpg_passphrase, rpm_pkg, conf_passphrase=None, preset_passphrase=None):
        """
        Generate keyring with provided gpg passphrase, update configuration with
        generated keyring, copy unsigned rpm_pkg, sign it, verify signature and
        cleanup everything.
        """
        gpg_home = os.path.join(self.projdir, '.gnupg')

        # Launch the agent with --allow-preset-passphrase to accept passphrase
        # provided non-interactively by gpg-preset-passphrase.
        cmd = [
          'gpg-agent',
          '--homedir',
          gpg_home,
          '--allow-preset-passphrase',
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
            gpg_passphrase or '',
            '--quick-generate-key',
            gpg_key,
        ]
        subprocess.run(cmd)

        # If preset passphrase is provided, add it to the agent
        # non-interactively with gpg-preset-passphrase.
        if preset_passphrase:
            # First find keygrip
            keygrip = None
            cmd = [
                'gpg',
                '--homedir',
                gpg_home,
                '--fingerprint',
                '--with-keygrip',
                '--with-colons',
                gpg_key
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE)
            for line in proc.stdout.decode().split('\n'):
                if line.startswith('grp'):
                    keygrip = line.split(':')[9]
                    break
            # Run gpg-preset-passphrase to add passphrase in agent
            cmd = ['/usr/libexec/gpg-preset-passphrase', '--preset', keygrip]
            subprocess.run(
                cmd,
                env={'GNUPGHOME': gpg_home},
                input=preset_passphrase.encode()
            )

        # Update project configuration with generated key
        self.config.options.update(
            {
                'gpg': {
                    'keyring': gpg_home,
                    'key': gpg_key,
                }
            }
        )

        if conf_passphrase is not None:
            self.config.options['gpg']['passphrase'] = conf_passphrase
        self.config._check()

        # Copy provided rpm_pkg in temporary project directory
        rpm_copy = os.path.join(self.projdir, os.path.basename(rpm_pkg))
        shutil.copy(rpm_pkg, rpm_copy)

        # Load RPM package, verify it is not signed and sign it
        rpm = RPM(rpm_copy, self.config)
        self.assertFalse(rpm.is_signed)
        try:
            os.environ['GNUPGHOME'] = gpg_home
            rpm.sign()
            del os.environ['GNUPGHOME']
            # Reload RPM package and check signature
            rpm._load()
            self.assertTrue(rpm.is_signed)
        finally:
            # Remove signed copy of RPM package and keyring
            os.remove(rpm_copy)

            # Kill GPG agent launched for the test
            cmd = ['gpgconf', '--homedir', gpg_home, '--kill', 'gpg-agent']
            subprocess.run(cmd)

            # Remove temporary GPG home with generated key
            shutil.rmtree(gpg_home)

    def test_sign_src_rpm(self):
        """Source RPM package signature."""
        self.sign_copy('TOPSECRET', self.src_rpm, 'TOPSECRET')

    def test_sign_bin_rpm(self):
        """Binary RPM package signature."""
        self.sign_copy('TOPSECRET', self.bin_rpm, 'TOPSECRET')

    def test_sign_wrong_passphrase(self):
        """Package signature raises RiftError with wrong passphrase."""
        with self.assertRaisesRegex(
            RiftError,
            "^Error with signing package.*"
        ):
            self.sign_copy('TOPSECRET', self.src_rpm, 'WRONG_PASSPHRASE')

    def test_sign_passphrase_agent_not_interactive(self):
        """Package signature with passphrase in agent not interactive."""
        # When the key is encrypted with passphrase, the passphrase is not set
        # in Rift configuration but loaded in GPG agent, Rift must sign the
        # package without making the agent launch pinentry to ask for the
        # passphrase interactively.
        self.sign_copy('TOPSECRET', self.src_rpm, preset_passphrase='TOPSECRET')

    def test_sign_empty_passphrase_not_interactive(self):
        """Package signature with empty passphrase no interactive passphrase."""
        # When the key is NOT encrypted with passphrase, Rift must sign the
        # package without making the agent launch pinentry to ask for the
        # passphrase interactively.
        self.sign_copy(None, self.src_rpm)
