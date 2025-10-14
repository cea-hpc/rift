#
# Copyright (C) 2014-2018 CEA
#

import os.path
import os
import textwrap

from TestUtils import make_temp_file, make_temp_dir, RiftTestCase

from rift import DeclError
from rift.Config import Staff, Modules, Config, _DEFAULT_PKG_DIR, \
                         _DEFAULT_STAFF_FILE, _DEFAULT_MODULES_FILE, \
                         _DEFAULT_VM_CPUS, _DEFAULT_VM_ADDRESS, \
                         _DEFAULT_VM_PORT_RANGE_MIN, \
                         _DEFAULT_VM_PORT_RANGE_MAX, \
                         _DEFAULT_QEMU_CMD, _DEFAULT_REPO_CMD, \
                         _DEFAULT_SHARED_FS_TYPE, _DEFAULT_VIRTIOFSD, \
                         _DEFAULT_SYNC_METHOD, _DEFAULT_SYNC_INCLUDE, \
                         _DEFAULT_SYNC_EXCLUDE, \
                         RiftDeprecatedConfWarning

class ConfigTest(RiftTestCase):

    def test_get(self):
        """get() default values"""
        config = Config()

        # Default config value
        self.assertEqual(config.get('packages_dir'), _DEFAULT_PKG_DIR)
        self.assertEqual(config.get('staff_file'), _DEFAULT_STAFF_FILE)
        self.assertEqual(config.get('modules_file'), _DEFAULT_MODULES_FILE)
        self.assertEqual(config.get('vm').get('cpus'), _DEFAULT_VM_CPUS)
        self.assertEqual(config.get('vm').get('address'), _DEFAULT_VM_ADDRESS)
        self.assertEqual(config.get('shared_fs_type'), _DEFAULT_SHARED_FS_TYPE)
        self.assertEqual(config.get('virtiofsd'), _DEFAULT_VIRTIOFSD)
        self.assertEqual(
            config.get('vm').get('port_range'),
            {
                'min': _DEFAULT_VM_PORT_RANGE_MIN,
                'max': _DEFAULT_VM_PORT_RANGE_MAX
            }
        )
        self.assertEqual(config.get('sync'), None)

        # Default value argument
        self.assertEqual(config.get('doesnotexist', 'default value'),
                         'default value')
        # Default external tools path
        self.assertEqual(config.get('qemu'), _DEFAULT_QEMU_CMD)
        self.assertEqual(config.get('createrepo'), _DEFAULT_REPO_CMD)

        # Default gpg settings
        self.assertEqual(config.get('gpg'), None)

    def test_get_set(self):
        """simple set() and get()"""
        config = Config()
        # set an 'int'
        config.set('vm', {'image': '/path/to/image', 'cpus': 42})
        self.assertEqual(config.get('vm').get('cpus'), 42)

        # set a 'dict'
        config.set(
            'vm',
            {
                'image': '/path/to/image',
                'port_range': {'min': 5000, 'max': 6000}
            }
        )
        self.assertEqual(
            config.get('vm').get('port_range'),
            {'min': 5000, 'max': 6000}
        )

        # set a 'record'
        config.set('repos', {'os': {'url': 'http://myserver/pub'}})
        self.assertEqual(config.get('repos'), {'os': {'url': 'http://myserver/pub'}})

        # set a 'list'
        config.set('arch', ['x86_64', 'aarch64'])
        self.assertEqual(config.get('arch'), ['x86_64', 'aarch64'])

        # set a 'enum'
        config.set('shared_fs_type', 'virtiofs')
        self.assertEqual(config.get('shared_fs_type'), 'virtiofs')

    def test_set_bad_type(self):
        """set() using wrong type raises an error"""
        self.assert_except(DeclError, "Bad data type str for 'cpus'",
                Config().set, 'vm', {'image': '/path/to/image', 'cpus': 'a string'})
        self.assert_except(DeclError, "Bad data type str for 'repos'",
                           Config().set, 'repos', 'a string')
        # Default check is 'string'
        self.assert_except(DeclError, "Bad data type int for 'image'",
                Config().set, 'vm', {'image': 42})
        self.assert_except(DeclError,
                           "Bad data type str for 'arch'",
                           Config().set, 'arch', 'x86_64')
        # Check bad enum
        self.assertRaises(DeclError, Config().set, 'shared_fs_type', 'badtype')

    def test_set_bad_key(self):
        """set() an undefined key raises an error"""
        self.assert_except(DeclError, "Unknown 'myval' key",
                           Config().set, 'myval', 'value')
        self.assert_except(DeclError, "Unknown 'myval' key",
                           Config().set, 'myval', 'value')

    def test_get_arch_placeholder(self):
        """get() with $arch placeholder"""
        config = Config()

        # Declare supported architectures
        config.set('arch', ['x86_64', 'aarch64'])
        # $arch placeholder replacement with string
        config.set('vm', {'image': '/path/to/image-$arch.qcow2'})
        self.assertEqual(
            config.get('vm', arch='x86_64').get('image'),
            '/path/to/image-x86_64.qcow2'
        )
        self.assertEqual(
            config.get('vm', arch='aarch64').get('image'),
            '/path/to/image-aarch64.qcow2'
        )
        # $arch placeholder replacement with dict
        config.set(
            'repos',
            {
                'os': {
                    'url': 'file:///rift/packages/$arch/os',
                    'priority': 90,
                },
                'extra': {
                    'url': 'file:///rift/packages/$arch/extra',
                    'priority': 90,
                },
            }
        )
        self.assertEqual(
            config.get('repos', arch='x86_64'),
            {
                'os': {
                    'url': 'file:///rift/packages/x86_64/os',
                    'priority': 90,
                },
                'extra': {
                    'url': 'file:///rift/packages/x86_64/extra',
                    'priority': 90,
                },
            }
        )
        self.assertEqual(
            config.get('repos', arch='aarch64'),
            {
                'os': {
                    'url': 'file:///rift/packages/aarch64/os',
                    'priority': 90,
                },
                'extra': {
                    'url': 'file:///rift/packages/aarch64/extra',
                    'priority': 90,
                },
            }
        )

    def test_get_arch_specific_override(self):
        """get() with specific arch override"""
        config = Config()

        # Declare supported architectures
        config.set('arch', ['x86_64', 'aarch64'])
        # Override with arch specific value
        config.set('vm', {'image': '/path/to/image-$arch.qcow2'})
        config.set('vm', {'image': '/path/to/other-image.qcow2'}, arch='x86_64')
        self.assertEqual(
            config.get('vm', arch='aarch64').get('image'),
            '/path/to/image-aarch64.qcow2'
        )
        self.assertEqual(
            config.get('vm', arch='x86_64').get('image'),
            '/path/to/other-image.qcow2'
        )

    def test_get_unsupported_arch(self):
        """get() with unsupported arch"""
        config = Config()

        # Get with unsupported arch must fail
        with self.assertRaisesRegex(
            DeclError,
            "^Unable to get configuration option for unsupported architecture "
            "'fail'$"
        ):
            config.get('vm', arch='fail')

    def test_set_unsupported_arch(self):
        """set() with unsupported arch"""
        config = Config()

        with self.assertRaisesRegex(
            DeclError,
            "^Unable to set configuration option for unsupported architecture "
            "'fail'$"
        ):
            config.set('vm', {'image': '/path/to/image.qcow2'}, arch='fail')


    def test_load(self):
        """load() checks mandatory options are present"""
        emptyfile = make_temp_file("")
        self.assert_except(DeclError, "'annex' is not defined",
                           Config().load, emptyfile.name)

        cfgfile = make_temp_file("annex: /a/dir\nvm:\n  image: /a/image.img")
        config = Config()
        # Simple filename
        config.load(cfgfile.name)

        config = Config()
        # List of filenames
        config.load([cfgfile.name])

        # Default config files
        self.assert_except(DeclError, "'annex' is not defined",
                           Config().load)

    def test_load_multiple_files(self):
        """load() loads multiple files"""
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    annex: /a/dir
                    vm:
                      image: /a/image.img
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    vm:
                      image: /b/image.img
                    arch:
                    - x86_64
                    - aarch64
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        # Value from 1st file should be loaded
        self.assertEqual(config.get('annex'), '/a/dir')
        # Value from 2nd file should override value from 1st file
        self.assertEqual(config.get('vm').get('image'), '/b/image.img')
        # Value from 2nd file should be loaded
        self.assertEqual(config.get('arch'), ['x86_64', 'aarch64'])

    def test_load_arch_specific(self):
        """load() properly loads architecture specific options"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                arch:
                - x86_64
                - aarch64
                x86_64:
                  vm:
                    image: /b/image.img
                aarch64:
                  vm:
                    image: /c/image.img
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('vm').get('image'), '/a/image.img')
        self.assertEqual(config.get('vm', arch='x86_64').get('image'), '/b/image.img')
        self.assertEqual(config.get('vm', arch='aarch64').get('image'), '/c/image.img')

    def test_load_arch_specific_invalid_mapping(self):
        """load() fail with not mapping architecture specific options"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                x86_64: fail
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            '^Architecture specific override for x86_64 must be a mapping$',
        ):
            config.load(cfgfile.name)

    def test_load_arch_specific_invalid_key(self):
        """load() fail with architecture specific invalid key"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                x86_64:
                    fail: value
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            "^Unknown 'fail' key$",
        ):
            config.load(cfgfile.name)

    def test_load_missing_required_key(self):
        """load() fail when required key is missing"""
        contents = {
            # vm_image is not defined at all
            """
            annex: /a/dir
            """,
            # vm_image is not defined for aarch64
            """
            annex: /a/dir
            arch:
            - x86_64
            - aarch64
            x86_64:
              vm:
                image: /a/image.img
            """
        }
        for content in contents:
            cfgfile = make_temp_file(textwrap.dedent(content))
            config = Config()
            with self.assertRaisesRegex(
                DeclError,
                "^'vm' is not defined$",
            ):
                config.load(cfgfile.name)

    def test_load_required_key_in_archs_ok(self):
        """load() succeeds when required key is declared for all architectures."""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                arch:
                - x86_64
                - aarch64
                x86_64:
                  vm:
                    image: /b/image.img
                aarch64:
                  vm:
                    image: /c/image.img
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)

    def test_load_missing_file(self):
        """load() an non-existent file raises a nice error"""
        config = Config()
        config.ALLOW_MISSING = False
        self.assert_except(DeclError, "Could not find '/does/not/exist'",
                           config.load, "/does/not/exist")

        # Wrong file type
        self.assert_except(DeclError, "[Errno 21] Is a directory: '/'",
                           config.load, "/")

    def test_load_bad_syntax(self):
        """load() an bad YAML syntax file raises an error"""
        cfgfile = make_temp_file("[value= not really YAML] [ ]\n")
        self.assertRaises(DeclError, Config().load, cfgfile.name)

    def test_load_repos_merged(self):
        """load() merges repos from multiple files"""
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    annex: /a/dir
                    vm:
                      image: /a/image.img
                    repos:
                      os:
                        url: https://os/url/file1
                      extra:
                        url: https://extra/url/file1
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    repos:
                      os:
                        url: https://os/url/file2
                        module_hotfixes: true
                      update:
                        url: https://update/url/file2
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        repos = config.get('repos')
        self.assertTrue('os' in repos)
        self.assertTrue('update' in repos)
        self.assertTrue('extra' in repos)
        self.assertEqual(repos['os']['url'], 'https://os/url/file2')
        self.assertTrue('module_hotfixes' in repos['os'])
        self.assertEqual(repos['update']['url'], 'https://update/url/file2')
        self.assertEqual(repos['extra']['url'], 'https://extra/url/file1')

    def test_load_port_partial_port_range(self):
        """Load partial port range dict"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                  port_range:
                    min: 2000
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('vm').get('port_range').get('min'), 2000)
        self.assertEqual(
            config.get('vm').get('port_range').get('max'),
            _DEFAULT_VM_PORT_RANGE_MAX
        )
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                  port_range:
                    max: 30000
                """
            )
        )
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('vm').get('port_range').get('min'),
            _DEFAULT_VM_PORT_RANGE_MIN
        )
        self.assertEqual(config.get('vm').get('port_range').get('max'), 30000)

    def test_load_gpg(self):
        """Load gpg parameters"""
        # Check without passphrase
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                gpg:
                  keyring: /path/to/keyring
                  key: rift
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('gpg').get('keyring'), '/path/to/keyring')
        self.assertEqual(config.get('gpg').get('key'), 'rift')
        self.assertEqual(config.get('gpg').get('passphrase'), None)

        # Check with passphrase
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                gpg:
                  keyring: /path/to/keyring
                  key: rift
                  passphrase: secr3t
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('gpg').get('keyring'), '/path/to/keyring')
        self.assertEqual(config.get('gpg').get('key'), 'rift')
        self.assertEqual(config.get('gpg').get('passphrase'), 'secr3t')

    def test_load_gpg_missing_keyring_or_key(self):
        """Skip gpg parameters load if missing keyring or key"""
        # Check missing both key and keyring or one of them
        for gpg_config in ['{}', '{keyring: /path/to/keyring}', '{key: rift}']:
            cfgfile = make_temp_file(
                textwrap.dedent(
                    f"""
                    annex: /a/dir
                    vm:
                      image: /a/image.img
                    gpg: {gpg_config}
                    """
                )
            )
            config = Config()
            with self.assertRaisesRegex(
                    DeclError,
                    '^Key (key|keyring) is required in dict parameter gpg$'
                ):
                config.load(cfgfile.name)

    def test_load_gpg_unknown_key(self):
        """Load gpg parameters raise DeclError if unknown key"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                gpg:
                  epic: fail
                  keyring: /path/to/keyring
                  key: rift
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(DeclError, '^Unknown gpg keys: epic$'):
            config.load(cfgfile.name)

    def test_load_sync(self):
        """load() loads repositories synchronization parameters."""
        # Load full config
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                sync_output: /sync/output
                repos:
                  repo1:
                    sync:
                      source: https://server1/repo1
                      method: epel
                      include:
                      - include1
                      - include2
                    url: file:///sync/output/repo1
                  repo2:
                    sync:
                      source: https://server2/repo2
                      exclude:
                      - exclude1
                      - exclude2
                    url: file:///sync/output/repo2
                  repo3:
                    url: https://server3/repo3
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('sync_output'), '/sync/output')
        self.assertEqual(
            config.get('repos')['repo1']['sync']['source'], 'https://server1/repo1'
        )
        self.assertEqual(
            config.get('repos')['repo1']['sync']['method'], 'epel'
        )
        self.assertEqual(
            config.get('repos')['repo1']['sync']['include'],
            ['include1', 'include2']
        )
        self.assertEqual(
            config.get('repos')['repo1']['sync']['exclude'],
            _DEFAULT_SYNC_EXCLUDE
        )
        self.assertEqual(
            config.get('repos')['repo2']['sync']['source'], 'https://server2/repo2'
        )
        self.assertEqual(
            config.get('repos')['repo2']['sync']['method'], _DEFAULT_SYNC_METHOD
        )
        self.assertEqual(
            config.get('repos')['repo2']['sync']['include'],
            _DEFAULT_SYNC_EXCLUDE
        )
        self.assertEqual(
            config.get('repos')['repo2']['sync']['exclude'],
            ['exclude1', 'exclude2']
        )
        self.assertIsNone(config.get('repos')['repo3'].get('sync'))

    def test_load_sync_repo_missing_source(self):
        """load() fails with DeclError when repositories synchronization source URL is missing."""
        # Load minimal config
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                repos:
                  repo1:
                    sync: {}
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            r"Key source is required in dict parameter sync"
        ):
            config.load(cfgfile.name)

    def test_load_sync_repo_invalid_method(self):
        """load() fails with DeclError when repositories synchronization method is invalid."""
        # Load minimal config
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                repos:
                  repo1:
                    sync:
                      source: https://server1/repo1
                      method: fail
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            r"Bad value fail \(str\) for 'method' \(correct values: lftp, "
            r"epel, dnf\)"
        ):
            config.load(cfgfile.name)

    def test_load_deprecated_vm_parameters(self):
        """load() deprecated vm_* parameters."""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /my/custom/image.img
                vm_cpus: 42
                vm_memory: 1234
                """
            )
        )
        config = Config()
        with self.assertWarns(RiftDeprecatedConfWarning):
            config.load(cfgfile.name)
        self.assertEqual(config.get('vm').get('image'), '/my/custom/image.img')
        self.assertEqual(config.get('vm').get('cpus'), 42)
        self.assertEqual(config.get('vm').get('memory'), 1234)

    def test_load_deprecated_gerrit_parameters(self):
        """load() deprecated gerrit_* parameters."""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm:
                  image: /a/image.img
                gerrit_realm: Rift
                gerrit_url: https://localhost
                gerrit_username: rift
                """
            )
        )
        config = Config()
        with self.assertWarns(RiftDeprecatedConfWarning):
            config.load(cfgfile.name)
        self.assertEqual(config.get('gerrit').get('realm'), 'Rift')
        self.assertEqual(config.get('gerrit').get('url'), 'https://localhost')
        self.assertEqual(config.get('gerrit').get('username'), 'rift')


class ConfigTestSyntax(RiftTestCase):
    """Test Config with modified syntax."""
    def setUp(self):
        # Save reference to original Config syntax class attribute. There is no
        # need to copy the dict as a new dict is allocated and assigned to class
        # attribute right after this.
        self.syntax_backup = Config.SYNTAX
        # Initialize syntax with arch which is the only hard requirement in
        # class logic.
        Config.SYNTAX = {
            'arch': {
                'check': 'list',
                'default': ['x86_64'],
            }
        }

    def tearDown(self):
        # Restore reference to original syntax dict in class attribute.
        Config.SYNTAX = self.syntax_backup

    def test_load_bool(self):
        """Load bool parameter"""
        Config.SYNTAX.update({
            'bool0': {
                'check': 'bool',
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                bool0: true
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('bool0'), True)

    def test_load_invalid_bool(self):
        """Test load invalid bool parameter"""
        Config.SYNTAX.update({
            'bool0': {
                'check': 'bool',
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                bool0: failure
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError, "^Bad data type str for 'bool0'$"
        ):
            config.load(cfgfile.name)

    def test_load_dict_without_syntax(self):
        """Load dict without syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  with: anything
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value1')
        self.assertEqual(config.get('param0').get('with'), 'anything')

    def test_load_dict_with_arch(self):
        """Load dict with archs"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                arch:
                - x86_64
                - aarch64
                param0:
                  key1: value1
                  with: anything
                aarch64:
                    param0:
                        key1: value2
                        with: another
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value1')
        self.assertEqual(config.get('param0').get('with'), 'anything')
        self.assertEqual(
            config.get('param0', arch='x86_64').get('key1'), 'value1'
        )
        self.assertEqual(
            config.get('param0', arch='x86_64').get('with'), 'anything'
        )
        self.assertEqual(
            config.get('param0', arch='aarch64').get('key1'), 'value2'
        )
        self.assertEqual(
            config.get('param0', arch='aarch64').get('with'), 'another'
        )

    def _add_fake_params(self):
        """Load dict with syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'required': True
                    },
                    'key2': {
                        'check': 'digit'
                    }
                }
            },
            'record0': {
                'check': 'record',
                'content': 'digit',
            }
        })

    def test_load_dict_with_syntax(self):
        """Load dict with syntax"""
        self._add_fake_params()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  key2: 2
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value1')
        self.assertEqual(config.get('param0').get('key2'), 2)

        # Test with another value for key1 and key2 undefined.
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value2
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value2')
        self.assertEqual(config.get('param0').get('key2'), None)

    def test_load_dict_bad_subkey_type(self):
        """Load dict with bad subkey type"""
        self._add_fake_params()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  key2: fail
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Bad data type str for 'key2'$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_missing_subkey(self):
        """Load dict with missing subkey."""
        self._add_fake_params()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key2: 2
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Key key1 is required in dict parameter param0$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_unknown_subkey(self):
        """Load dict with unknown subkey."""
        self._add_fake_params()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  key3: value2
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Unknown param0 keys: key3$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_recursive_syntax(self):
        """Load dict with resursive syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'check': 'dict',
                        'syntax': {
                            'subkey2': {
                                'required': True
                            },
                            'subkey3': {
                                'check': 'digit'
                            },
                        },
                    },
                },
            },
        })
        # Check load of valid param0
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1:
                    subkey2: value2
                    subkey3: 5
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('param0').get('key1').get('subkey2'), 'value2'
        )
        self.assertEqual(
            config.get('param0').get('key1').get('subkey3'), 5
        )

        # Check syntax is really enforced on sub-sub-dict
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1:
                    subkey2: value2
                    subkey3: fail
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Bad data type str for 'subkey3'$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_with_syntax_default_value_partial_def(self):
        """Load dict with default value defined in syntax and partial definition"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'default': 'default_key1',
                    },
                    'key2': {
                        'check': 'dict',
                        'syntax': {
                            'subkey2': {
                                'default': 'default_subkey2',
                            },
                            'subkey3': {
                                'default': 'default_subkey3',
                            }
                        }
                    },
                    'key3': {
                        'check': 'dict',
                        'default': {
                            'subkey5': 'default_subkey5',
                        },
                    },
                }
            }
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                    key1: overriden_subkey1
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('param0'),
            {
                'key1': 'overriden_subkey1',
                'key2': {
                    'subkey2': 'default_subkey2',
                    # Value defined in config file must be properly loaded
                    'subkey3': 'default_subkey3',
                },
                'key3': {
                    'subkey5': 'default_subkey5',
                }
            }
        )


    def test_load_dict_with_syntax_default_value(self):
        """Load dict with default value defined in syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'default': 'default_key1',
                    },
                    'key2': {
                        'check': 'dict',
                        'syntax': {
                            'subkey2': {
                                'default': 'default_subkey2',
                            },
                            'subkey3': {
                                'default': 'default_subkey3',
                            }
                        }
                    },
                    'key3': {
                        'check': 'dict',
                        'default': {
                            'subkey5': 'default_subkey5',
                        },
                        'syntax': {
                            'subkey4': {
                                'default': 'default_subkey4',
                            },
                            'subkey5': {}
                        },
                    },
                }
            }
        })
        cfgfile = make_temp_file('')
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('param0'),
            {
                'key1': 'default_key1',
                'key2': {
                    # Default values must be extracted from key2 syntax.
                    'subkey2': 'default_subkey2',
                    'subkey3': 'default_subkey3',
                },
                'key3': {
                    # Default value defined at key3 level has the priority over
                    # the default value defined at subkeys level in syntax.
                    'subkey5': 'default_subkey5',
                }
            }
        )

    def test_load_dict_merged_syntax(self):
        """load() merges dict from multiple files with syntax"""
        self._add_fake_params()
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    param0:
                      key1: value1
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    param0:
                      key1: value2
                      key2: 1
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        param0 = config.get('param0')
        self.assertTrue('key1' in param0)
        self.assertTrue('key2' in param0)
        self.assertEqual(param0['key1'], 'value2')
        self.assertEqual(param0['key2'], 1)

    def test_load_dict_merged_syntax_missing_required(self):
        """load() merges dict from multiple files with syntax and required param missing in one file"""
        self._add_fake_params()
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    param0:
                      key1: value1
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    param0:
                      key2: 1
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        param0 = config.get('param0')
        self.assertTrue('key1' in param0)
        self.assertTrue('key2' in param0)
        self.assertEqual(param0['key1'], 'value1')
        self.assertEqual(param0['key2'], 1)

    def test_load_record(self):
        """Load record without content"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'record',
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  key2: value2
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value1')
        self.assertEqual(config.get('param0').get('key2'), 'value2')

    def test_load_record_with_content(self):
        """Load record with content specification."""
        Config.SYNTAX.update({
            'param0': {
                'check': 'record',
                'content': 'digit',
            },
            'param1': {
                'check': 'record',
                'content': 'dict',
            },
            'param2': {
                'check': 'record',
                'content': 'dict',
                'syntax': {
                    'p2subkey1': {
                        'check': 'digit',
                        'default': -1,
                    },
                    'p2subkey2': {
                        'required': True
                    },
                },
            },
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  p0key1: 1
                  p0key2: 2
                param1:
                  p1key1:
                    p1k1key1: p1k1value1
                    p1k1key2: p1k1value2
                  p1key2:
                    p1k1key3: p1k1value3
                    p1k1key4: p1k1value4
                param2:
                  p2key1:
                    p2subkey1: 0
                    p2subkey2: p2k2value1
                  p2key2:
                    p2subkey2: p2k2value2
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('p0key1'), 1)
        self.assertEqual(config.get('param0').get('p0key2'), 2)
        self.assertEqual(
            config.get('param1')['p1key1'].get('p1k1key1'), 'p1k1value1'
        )
        self.assertEqual(
            config.get('param1')['p1key1'].get('p1k1key2'), 'p1k1value2'
        )
        self.assertEqual(
            config.get('param1')['p1key2'].get('p1k1key3'), 'p1k1value3'
        )
        self.assertEqual(
            config.get('param1')['p1key2'].get('p1k1key4'), 'p1k1value4'
        )
        self.assertEqual(
            config.get('param2')['p2key1'].get('p2subkey1'), 0
        )
        self.assertEqual(
            config.get('param2')['p2key1'].get('p2subkey2'), 'p2k2value1'
        )
        self.assertEqual(config.get('param2')['p2key2'].get('p2subkey1'), -1)
        self.assertEqual(
            config.get('param2')['p2key2'].get('p2subkey2'), 'p2k2value2'
        )

    def test_load_record_with_invalid_content(self):
        """Load record with invalid content type"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'record',
                'content': 'digit'
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: fail
                  key2: 2
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            "^Bad data type str for 'key1'$"
        ):
            config.load(cfgfile.name)

    def test_load_record_with_invalid_dict_content(self):
        """Load record with invalid dict syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'record',
                'content': 'dict',
                'syntax': {
                    'key1': {},
                    'key2': {},
                },
            },
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  item1:
                    key1: value1
                    key2: value2
                  item2:
                    key3: value3
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            "^Unknown item2 keys: key3$"
        ):
            config.load(cfgfile.name)

    def test_load_record_merged(self):
        """load() merges records from multiple files"""
        self._add_fake_params()
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    record0:
                        value1: 1
                        value2: 2
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    record0:
                      value2: 20
                      value3: 3
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        record0 = config.get('record0')
        self.assertTrue('value1' in record0)
        self.assertTrue('value2' in record0)
        self.assertTrue('value3' in record0)
        self.assertEqual(record0['value1'], 1)
        self.assertEqual(record0['value2'], 20)
        self.assertEqual(record0['value3'], 3)

    def test_deprecated_param(self):
        """Load deprecated parameter"""
        Config.SYNTAX.update({
            'new_parameter': {},
            'old_parameter': {
                'deprecated': 'new_parameter',
            },
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                old_parameter: test_value
                """
            )
        )
        config = Config()
        with self.assertWarns(RiftDeprecatedConfWarning) as cm:
            config.load(cfgfile.name)
        self.assertEqual(
            config.get('new_parameter'), 'test_value'
        )
        self.assertIsNone(config.get('old_parameter'))
        self.assertEqual(
            str(cm.warning),
            "Configuration parameter old_parameter is deprecated, use "
            "new_parameter instead"
        )
        # Check set() on deprecated parameter raise declaration error.
        with self.assertRaisesRegex(
            DeclError,
            "^Parameter old_parameter is deprecated, use new_parameter instead$"
        ):
            config.set('old_parameter', 'another value')


    def test_deprecated_param_with_arch(self):
        """Load deprecated parameter with arch override"""
        Config.SYNTAX.update({
            'new_parameter_1': {},
            'old_parameter_1': {
                'deprecated': 'new_parameter_1',
            },
            'new_parameter_2': {},
            'old_parameter_2': {
                'deprecated': 'new_parameter_2',
            },
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                arch:
                - x86_64
                - aarch64
                old_parameter_1: generic_value
                aarch64:
                    old_parameter_1: aarch64_value
                old_parameter_2: generic_value_$arch
                """
            )
        )
        config = Config()
        with self.assertWarns(RiftDeprecatedConfWarning):
            config.load(cfgfile.name)
        self.assertEqual(config.get('new_parameter_1'), 'generic_value')
        self.assertEqual(
            config.get('new_parameter_1', arch='x86_64'), 'generic_value'
        )
        self.assertEqual(
            config.get('new_parameter_1', arch='aarch64'), 'aarch64_value'
        )
        self.assertEqual(
            config.get('new_parameter_2', arch='x86_64'), 'generic_value_x86_64'
        )
        self.assertEqual(
            config.get('new_parameter_2', arch='aarch64'),
            'generic_value_aarch64'
        )
        self.assertIsNone(config.get('old_parameter_1'))
        self.assertIsNone(config.get('old_parameter_2'))

    def test_deprecated_param_subdict(self):
        """Load deprecated parameter moved in subdict"""
        Config.SYNTAX.update({
            'new_parameter': {
                'check': 'dict',
                'syntax': {
                    'sub_dict1': {
                        'check': 'dict',
                        'syntax': {
                            'new_key1': {}
                        },
                    },
                },
            },
            'old_parameter': {
                'deprecated': 'new_parameter.sub_dict1.new_key1',
            },
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                old_parameter: test_value
                """
            )
        )
        config = Config()
        with self.assertWarns(RiftDeprecatedConfWarning) as cm:
            config.load(cfgfile.name)
        self.assertEqual(
            config.get('new_parameter').get('sub_dict1').get('new_key1'), 'test_value'
        )
        self.assertIsNone(config.get('old_parameter'))
        self.assertEqual(
            str(cm.warning),
            "Configuration parameter old_parameter is deprecated, use "
            "new_parameter > sub_dict1 > new_key1 instead"
        )

    def test_deprecated_param_invalid_type(self):
        """Deprecated parameter with invalid type error"""
        Config.SYNTAX.update({
            'new_parameter': {
                'check': 'digit',
            },
            'old_parameter': {
                'deprecated': 'new_parameter',
            },
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                old_parameter: test_value
                """
            )
        )
        config = Config()
        # In this case, Config.set() should emit a declaration error on
        # new_parameter. Also check warning is emited for old_parameter.
        with self.assertWarns(RiftDeprecatedConfWarning) as aw:
            with self.assertRaisesRegex(
                DeclError,
                "Bad data type str for 'new_parameter'"
            ):
                config.load(cfgfile.name)
        self.assertEqual(
            str(aw.warning),
            "Configuration parameter old_parameter is deprecated, use "
            "new_parameter instead"
        )

    def test_deprecated_param_unexisting_replacement(self):
        """Deprecated parameter without replacement error"""
        Config.SYNTAX.update({
            'old_parameter': {
                'deprecated': 'new_parameter',
            },
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                old_parameter: test_value
                """
            )
        )
        config = Config()
        # In this case, Config.set() should emit a declaration error.
        with self.assertWarns(RiftDeprecatedConfWarning) as aw:
            with self.assertRaisesRegex(
                DeclError, "Unknown 'new_parameter' key"):
                config.load(cfgfile.name)
        self.assertEqual(
            str(aw.warning),
            "Configuration parameter old_parameter is deprecated, use "
            "new_parameter instead"
        )

    def test_deprecated_param_conflict(self):
        """Load deprecated parameter conflict with replacement parameter"""
        Config.SYNTAX.update({
            'new_parameter': {},
            'old_parameter': {
                'deprecated': 'new_parameter',
            },
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                new_parameter: test_new_value
                old_parameter: test_old_value
                """
            )
        )
        config = Config()
        with self.assertWarns(RiftDeprecatedConfWarning) as aw:
            with self.assertLogs(level='WARNING') as al:
                config.load(cfgfile.name)
        self.assertEqual(
            config.get('new_parameter'), 'test_new_value'
        )
        self.assertIsNone(config.get('old_parameter'))
        self.assertEqual(
            str(aw.warning),
            "Configuration parameter old_parameter is deprecated, use "
            "new_parameter instead"
        )
        self.assertEqual(
            al.output,
            ['WARNING:root:Both deprecated parameter old_parameter and new '
             'parameter new_parameter are declared in configuration, '
             'deprecated parameter old_parameter is ignored']
        )

class ProjectConfigTest(RiftTestCase):

    def setUp(self):
        self.cwd = os.getcwd()
        self.projdir = make_temp_dir()
        self.packagesdir = os.path.join(self.projdir, 'packages')
        os.mkdir(self.packagesdir)
        self.foodir = os.path.join(self.projdir, 'packages', 'foo')
        os.mkdir(self.foodir)
        self.projectpath = os.path.join(self.projdir, Config._DEFAULT_FILES[0])
        os.mknod(self.projectpath)

    def tearDown(self):
        os.unlink(self.projectpath)
        os.rmdir(self.foodir)
        os.rmdir(self.packagesdir)
        os.rmdir(self.projdir)
        os.chdir(self.cwd)

    def test_find_project_dir(self):
        """find_project_dir() in sub-directories"""
        for path in (self.projdir, self.packagesdir, self.foodir):
            os.chdir(path)
            self.assertEqual(Config().find_project_dir(), self.projdir)

    def test_project_path_absolute(self):
        """project_path() using absolute path is ok"""
        absolutepath = os.path.abspath('foo')
        for path in (self.projdir, self.packagesdir, self.foodir):
            os.chdir(path)
            self.assertEqual(Config().project_path(absolutepath), absolutepath)

    def test_project_path_relative(self):
        """project_path() using project root relative dir is ok"""
        relativepath = os.path.join('relative', 'path')
        realpath = os.path.join(self.projdir, relativepath)
        os.chdir(self.projdir)
        self.assertEqual(Config().project_path(relativepath), realpath)


class StaffTest(RiftTestCase):

    def setUp(self):
        config = Config()
        self.staff = Staff(config)

    def test_empty(self):
        """create an empty Staff object"""
        self.assertEqual(self.staff._data, {})

    def test_load_ok(self):
        """load a staff file"""
        tmp = make_temp_file("{staff: {'J. Doe': {email: 'j.doe@rift.org'}} }")
        self.staff.load(tmp.name)
        self.assertEqual(self.staff.get('J. Doe'), {'email': 'j.doe@rift.org'})

    def test_load_default_ok(self):
        """load a staff file using default path"""
        self.assertFalse(self.staff.get('J. Doe'))

        tmp = make_temp_file("{staff: {'J. Doe': {email: 'j.doe@rift.org'}} }")
        self.staff.DEFAULT_PATH = tmp.name
        self.staff.load()
        self.assertEqual(self.staff.get('J. Doe'), {'email': 'j.doe@rift.org'})

    def test_load_missing_file(self):
        """load a missing staff file"""
        self.assert_except(DeclError, "Could not find '/tmp/does_not_exist'",
                           self.staff.load, '/tmp/does_not_exist')

    def test_load_unreadable_file(self):
        """load an unaccessible staff file"""
        tmp = make_temp_file("{staff: {'J. Doe': {email: 'j.doe@rift.org'}} }")
        self.staff.load(tmp.name)
        # Compat python2/3 syntax
        os.chmod(tmp.name, int(oct(0o200), 8))
        self.assertRaises(DeclError, self.staff.load, tmp.name)

    def test_load_error(self):
        """load a staff file with a bad yaml syntax"""
        tmp = make_temp_file("bad syntax: { , }")
        self.assertRaises(DeclError, self.staff.load, tmp.name)

    def test_load_bad_format(self):
        """load a staff file with a bad yaml structure (list instead of dict)"""
        tmp = make_temp_file("{staff: ['John Doe', 'Ben Harper']}")
        self.assert_except(DeclError, "Bad data format in staff file",
                           self.staff.load, tmp.name)

    def test_load_bad_syntax(self):
        """load a staff file with a bad yaml structure (missing 'staff')"""
        tmp = make_temp_file("{people: ['John Doe', 'Ben Harper']}")
        self.assert_except(DeclError, "Missing 'staff' at top level in staff file",
                           self.staff.load, tmp.name)

    def test_load_useless_items(self):
        """load a staff file with unknown items"""
        tmp = make_temp_file("""{staff:
           {'J. Doe': {email: 'john.doe@rift.org', id: 145, reg: 'foo'}} }""")
        self.assert_except(DeclError, "Unknown 'id', 'reg' item(s) for J. Doe",
                           self.staff.load, tmp.name)

    def test_load_missing_item(self):
        """load a staff file with missing items"""
        tmp = make_temp_file("""{staff: {'John Doe': {id: 145}} }""")
        self.assert_except(DeclError, "Missing 'email' item(s) for John Doe",
                           self.staff.load, tmp.name)


class ModulesTest(RiftTestCase):

    def setUp(self):
        config = Config()
        self.staff = Staff(config)
        self.modules = Modules(config, self.staff)

    def test_empty(self):
        """create an empty Modules object"""
        self.assertEqual(self.modules._data, {})

    def test_load_error(self):
        """load a modules file with a bad yaml syntax"""
        tmp = make_temp_file("bad syntax: { , }")
        self.assertRaises(DeclError, self.modules.load, tmp.name)

    def test_load_ok(self):
        """load a modules file"""
        self.staff._data['John Doe'] = {'email': 'john.doe@rift.org'}

        tmp = make_temp_file("{modules: {Kernel: {manager: 'John Doe'}} }")
        self.modules.load(tmp.name)
        self.assertEqual(self.modules.get('Kernel'), {'manager': ['John Doe']})

    def test_load_managers(self):
        """load a modules file with several managers"""
        self.staff._data['John Doe'] = {'email': 'john.doe@rift.org'}
        self.staff._data['Boo'] = {'email': 'boo@rift.org'}

        tmp = make_temp_file("""{modules: {Kernel:
                                {manager: ['John Doe', 'Boo']}} }""")
        self.modules.load(tmp.name)
        self.assertEqual(self.modules.get('Kernel'),
                         {'manager': ['John Doe', 'Boo']})

    def test_load_missing_managers(self):
        """load a modules file with a undeclared manager"""
        tmp = make_temp_file("{modules: {Kernel: {manager: 'John Doe'}} }")
        self.assert_except(DeclError,
                           "Manager 'John Doe' does not exist in staff list",
                           self.modules.load, tmp.name)
