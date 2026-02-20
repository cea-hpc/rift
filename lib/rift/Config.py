#
# Copyright (C) 2014-2016 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#
"""
Config:
    This package manage rift configuration files.
"""
import errno
import os
import warnings
import logging

import yaml

from rift import DeclError

try:
    # included in standard lib from Python 2.7
    from collections import OrderedDict
except ImportError:
    # try importing the backported drop-in replacement, it's available on PyPI
    from ordereddict import OrderedDict

# Very simplified version of
# http://stackoverflow.com/questions/5121931/in-python-how-can-you-load-yaml-mappings-as-ordereddicts
# This does not implement the matching dumper.
class OrderedLoader(yaml.SafeLoader):
    """Specific yaml SafeLoader which imports yaml mapping using OrderedDict"""

def _construct_mapping(loader, node):
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))

class RiftDeprecatedConfWarning(FutureWarning):
    """Warning emitted when deprecated configuration parameter is loaded."""

OrderedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping)


_DEFAULT_PKG_DIR = 'packages'
_DEFAULT_STAFF_FILE = os.path.join(_DEFAULT_PKG_DIR, 'staff.yaml')
_DEFAULT_MODULES_FILE = os.path.join(_DEFAULT_PKG_DIR, 'modules.yaml')
_DEFAULT_ARCH = ['x86_64']
_DEFAULT_VM_CPUS = 4
_DEFAULT_VM_MEMORY = 8192
_DEFAULT_VM_ADDRESS = '10.0.2.15'
_DEFAULT_VM_ADDITIONAL_RPMS = []
_DEFAULT_VM_CLOUD_INIT_TPL = 'cloud-init.tpl'
_DEFAULT_VM_BUILD_POST_SCRIPT = 'build-post.sh'
_DEFAULT_VM_PORT_RANGE_MIN = 10000
_DEFAULT_VM_PORT_RANGE_MAX = 15000
_DEFAULT_QEMU_CMD = 'qemu-system-$arch'
_DEFAULT_REPO_CMD = 'createrepo_c'
_DEFAULT_SHARED_FS_TYPE = '9p'
_DEFAULT_VIRTIOFSD = '/usr/libexec/virtiofsd'
_DEFAULT_SYNC_METHOD = 'dnf'
_DEFAULT_SYNC_INCLUDE = []
_DEFAULT_SYNC_EXCLUDE = []
_DEFAULT_VARIANT = 'main'
_DEFAULT_REPOS_VARIANTS = [_DEFAULT_VARIANT]
_DEFAULT_DEPENDENCY_TRACKING = False
_DEFAULT_S3_CREDENTIAL_FILE = '~/.rift/auth.json'


class Config():
    """
    Config: Manage rift configuration files
        This class parses project.conf and local.conf from the current working
        package repository. It merges content of both files and gives access to
        stored values.
    """
    # XXX: Support hierarchical configuration (vm.image = ...)

    _DEFAULT_FILES = ['project.conf', 'local.conf']
    ALLOW_MISSING = True

    SYNTAX = {
        'staff_file': {
            'default':   _DEFAULT_STAFF_FILE,
        },
        'modules_file': {
            'default':   _DEFAULT_MODULES_FILE,
        },
        'proxy': {},
        'no_proxy': {},
        'packages_dir': {
            'default':   _DEFAULT_PKG_DIR,
        },
        's3_credential_file': {
            'required': False,
            'default':  _DEFAULT_S3_CREDENTIAL_FILE,
        },
        's3_auth_endpoint': {
            'required': False,
        },
        'idp_auth_endpoint': {
            'required': False
        },
        'idp_app_token': {
            'required': False
        },
        'annex_restore_cache': {
            'required': False,
        },
        'set_annex': {
            'check': 'dict',
            'required': True,
            'syntax': {
                'address': {
                    'required': True,
                },
                'type': {
                    'check': 'enum',
                    'required': True,
                    'values': ['directory', 'server', 's3']
                }
            }
        },
        'annex': {
            'deprecated': 'set_annex.address'
        },
        'annex_is_s3': {
            'deprecated': 'set_annex.type'
        },
        'staging_annex': {
            'check': 'dict',
            'required': False,
            'syntax': {
                'address': {
                    'required': True,
                },
                'type': {
                    'check': 'enum',
                    'required': True,
                    'values': ['directory', 'server', 's3']
                }
            }
        },
        'working_repo': {
        },
        'repos': {
            'check':    'record',
            'content':  'dict',
            'syntax': {
                'sync': {
                    'check': 'dict',
                    'default': None,
                    'syntax': {
                        'method': {
                            'check': 'enum',
                            'default': _DEFAULT_SYNC_METHOD,
                            'values': ['lftp', 'epel', 'dnf']
                        },
                        'source': {
                            'required': True,
                        },
                        'subdir': {},
                        'include': {
                            'check': 'list',
                            'default': _DEFAULT_SYNC_INCLUDE,
                        },
                        'exclude': {
                            'check': 'list',
                            'default': _DEFAULT_SYNC_EXCLUDE,
                        },
                    },
                },
                'url': {
                    'required': True,
                },
                'priority': {
                    'check': 'digit',
                },
                'excludepkgs': {},
                'module_hotfixes': {
                    'check': 'bool'
                },
                'proxy': {},
                'variants': {
                    'check': 'list',
                    'default': _DEFAULT_REPOS_VARIANTS,
                }
            }
        },
        'arch': {
            'check': 'list',
            'default':  _DEFAULT_ARCH,
        },
        'arch_efi_bios': {},
        'version': {},
        'maintainer':  {},
        'qemu': {
            'default':  _DEFAULT_QEMU_CMD,
        },
        'createrepo': {
            'default':  _DEFAULT_REPO_CMD,
        },
        'gpg': {
            'check':    'dict',
            'syntax': {
                'keyring': {
                    'required': True,
                },
                'passphrase': {},
                'key': {
                    'required': True,
                }
            }
        },
        'vm': {
            'check':    'dict',
            'required': True,
            'syntax': {
                'image':    {
                    'required': True,
                    # XXX?: default value?
                },
                'image_copy':    {
                    'check':    'digit',
                    'default': 0,
                },
                'port_range': {
                    'check':    'dict',
                    'syntax': {
                        'min': {
                            'check': 'digit',
                            'default': _DEFAULT_VM_PORT_RANGE_MIN,
                        },
                        'max': {
                            'check': 'digit',
                            'default': _DEFAULT_VM_PORT_RANGE_MAX,
                        }
                    }
                },
                'cpu': {},
                'cpus': {
                    'check':    'digit',
                    'default':  _DEFAULT_VM_CPUS,
                },
                'memory': {
                    'check':    'digit',
                    'default':   _DEFAULT_VM_MEMORY,
                },
                'address': {
                    'default':  _DEFAULT_VM_ADDRESS,
                },
                'images_cache': {},
                'additional_rpms': {
                    'check':    'list',
                    'default':  _DEFAULT_VM_ADDITIONAL_RPMS,
                },
                'cloud_init_tpl': {
                    'default': _DEFAULT_VM_CLOUD_INIT_TPL,
                },
                'build_post_script': {
                    'default': _DEFAULT_VM_BUILD_POST_SCRIPT,
                },
            }
        },
        'vm_image':    {
            'deprecated': 'vm.image'
        },
        'vm_image_copy':    {
            'deprecated': 'vm.image_copy'
        },
        'vm_port_range': {
            'deprecated': 'vm.port_range'
        },
        'vm_cpu': {
            'deprecated': 'vm.cpu'
        },
        'vm_cpus': {
            'deprecated': 'vm.cpus'
        },
        'vm_memory': {
            'deprecated': 'vm.memory'
        },
        'vm_address': {
            'deprecated': 'vm.address'
        },
        'vm_images_cache': {
            'deprecated': 'vm.images_cache'
        },
        'vm_additional_rpms': {
            'deprecated': 'vm.additional_rpms'
        },
        'vm_cloud_init_tpl': {
            'deprecated': 'vm.cloud_init_tpl'
        },
        'vm_build_post_script': {
            'deprecated': 'vm.build_post_script'
        },
        'gerrit': {
            'check': 'dict',
            'syntax': {
                'realm': {},
                'server': {},
                'url': {},
                'username': {},
                'password': {},
            }
        },
        'gerrit_realm': {
            'deprecated': 'gerrit.realm'
        },
        'gerrit_server': {
            'deprecated': 'gerrit.server'
        },
        'gerrit_url': {
            'deprecated': 'gerrit.url'
        },
        'gerrit_username': {
            'deprecated': 'gerrit.username'
        },
        'gerrit_password': {
            'deprecated': 'gerrit.password'
        },
        'rpm_macros': {
            'check':    'dict',
        },
        'virtiofsd': {
            'default': _DEFAULT_VIRTIOFSD,
        },
        'shared_fs_type': {
            'default': _DEFAULT_SHARED_FS_TYPE,
            'check': 'enum',
            'values': ['9p', 'virtiofs'],
        },
        'sync_output': {},
        'dependency_tracking': {
            'check': 'bool',
            'default': _DEFAULT_DEPENDENCY_TRACKING,
        },
        # XXX?: 'mock.name' ?
        # XXX?: 'mock.template' ?
    }

    def __init__(self):
        self.options = {}
        self.project_dir = None

    def find_project_dir(self, filenames=None):
        """
        Look for project base directory looking for configuration filenames.

        It will recursively look for name from filenames, starting from
        name directory and going up if file is not found.

        If found, it returns a tuple for the matching file directory and file
        name, if never found, it returns (None, None).
        """
        if filenames is None:
            filenames = self._DEFAULT_FILES
        if isinstance(filenames, str):
            filenames = [filenames]

        for filepath in filenames:
            filepath = os.path.abspath(filepath)
            dirname, filename = os.path.split(filepath)
            if os.path.exists(filepath):
                return dirname

            while dirname != '/':
                dirname = os.path.split(dirname)[0]
                filepath = os.path.join(dirname, filename)
                if os.path.exists(filepath):
                    return dirname

        return None

    def project_path(self, filepath):
        """
        Transform a path relative to project root dir to a usable path.

        filepath should either be an absolute path or relative to project root
        dir.
        """
        if not self.project_dir:
            self.project_dir = self.find_project_dir()

        if self.project_dir and not os.path.isabs(filepath):
            filepath = os.path.join(self.project_dir, filepath)

        return filepath

    def get(self, option, default=None, arch=None):
        """
        Config getter (manage default values).

        If arch optional argument is provided, 2 additional steps are performed:

        1/ An architecture specific option value is first searched by suffixing
           the arch to the option name. If not found, it fallbacks to the option
           without suffix.
        2/ $arch placeholder is replaced recursively in the value by the
           provided argument.

        The additional logic is skipped for the special arch option.
        """
        # If arch argument is provided, check it is one of the project
        # supported architectures.
        if arch is not None and arch not in self.get('arch'):
            raise DeclError(
                "Unable to get configuration option for unsupported "
                f"architecture '{arch}'"
            )
        # Except for arch option, if arch argument is provided, select the
        # architecture specific option (suffixed by the arch) in priority.
        if (
                option != 'arch' and
                arch is not None and
                arch in self.options and
                option in self.options[arch]
            ):
            value = self.options[arch][option]
        elif option in self.options:
            value = self.options[option]
        elif option in self.SYNTAX:
            value = Config._syntax_default(self.SYNTAX, option, default)
        else:
            value = default

        # Except for arch option, if arch argument is provided, replace $arch
        # placeholder by this value.
        if option == 'arch' or arch is None:
            return value
        return self._replace_arch(value, arch)

    @staticmethod
    def _syntax_default(syntax, option, default=None):
        """
        Return the default value of the option in config syntax.
        If the option is a dictionnary and it has no global default value but a
        syntax, generate dict default value with default values defined in
        syntax. In all other cases, just use optional global default value from
        syntax or provided default value.
        """
        if (
                'default' not in syntax[option] and
                syntax[option].get('check') == 'dict' and
                'syntax' in syntax[option]
            ):
            return Config._extract_default_dict_syntax(syntax[option]['syntax'])
        return syntax[option].get('default', default)

    @staticmethod
    def _extract_default_dict_syntax(syntax):
        """
        Return the default dict value as defined in dict syntax, recursively.
        """
        result = {}
        for key, option in syntax.items():
            if 'default' in option:
                result[key] = option['default']
            elif option.get('check') == 'dict' and 'syntax' in option:
                result[key] = Config._extract_default_dict_syntax(
                    option['syntax']
                )
        return result if result else None

    def _replace_arch(self, value, arch):
        """
        Replace $arch placeholder in all strings found in value recursively.
        """
        if isinstance(value, str):
            return value.replace('$arch', arch)
        if isinstance(value, list):
            return [
                item.replace('$arch', arch)
                if isinstance(item, str)
                else item
                for item in value
            ]
        if isinstance(value, dict):
            return {
                key: self._replace_arch(item, arch)
                for key, item
                in value.items()
            }
        return value

    def load(self, filenames=None):
        """
        Read and parse the list of named configuration files, given by name. A
        single filename is also allowed. Non-existing files are ignored.

        If filenames is not omited, self._DEFAULT_FILES is used.
        """
        if filenames is None:
            filenames = self._DEFAULT_FILES
        if isinstance(filenames, str):
            filenames = [filenames]

        for filepath in filenames:
            try:
                # Initialize project_dir using project config files
                if self.project_dir is None:
                    self.find_project_dir(filepath)

                with open(self.project_path(filepath), encoding='utf-8') as fyaml:
                    data = yaml.load(fyaml, Loader=OrderedLoader)

                if data:
                    self.update(data)

            except yaml.error.YAMLError as exp:
                raise DeclError(str(exp)) from exp
            except IOError as exp:
                if exp.errno == errno.ENOENT:
                    if not self.ALLOW_MISSING:
                        raise DeclError(f"Could not find '{filepath}'") from exp
                else:
                    raise DeclError(str(exp)) from exp

        self._check()

    def _arch_options(self, arch):
        """
        Return the options dictionnary for the given architecture. If arch is
        None, return the global options dict.
        """
        if arch is None:
            return self.options
        if arch not in self.get('arch'):
            raise DeclError(
                "Unable to set configuration option for unsupported "
                f"architecture '{arch}'"
            )
        if arch not in self.options:
            self.options[arch] = {}
        return self.options[arch]

    def set(self, key, value, arch=None):
        """
        Config setter (check value type)
        """

        # Check key is known.
        if key not in self.SYNTAX:
            raise DeclError(f"Unknown '{key}' key")

        # Check not deprecated
        replacement = self.SYNTAX[key].get('deprecated')
        if replacement:
            raise DeclError(f"Parameter {key} is deprecated, use "
                            f"{' > '.join(replacement.split('.'))} instead")

        options = self._arch_options(arch)
        value = self._key_value(
            self.SYNTAX[key],
            key,
            value,
            self.SYNTAX[key].get('check', 'string'),
        )
        # If the key is a dict or a record and it already has a value, merge it
        # with the new value.
        if (self.SYNTAX[key].get('check') in ['dict', 'record']
                and key in options):
            options[key].update(value)
        else:
            options[key] = value

    def _key_value(self, syntax, key, value, check):
        """
        Validate type of value against syntax definition and return its value.
        """
        # Check type
        assert check in ('string', 'dict', 'record', 'list', 'digit', 'bool',
                         'enum')

        # All checks values which don't need conversion with their associated
        # python types
        types_no_conv = {
            "string": str,
            "list": list,
            "digit": int,
            "bool": bool,
        }

        if check == 'bool':
            if not isinstance(value, bool):
                raise DeclError(
                    f"Bad data type {value.__class__.__name__} for '{key}'"
                )
            return value
        if check == 'dict':
            if not isinstance(value, dict):
                raise DeclError(
                    f"Bad data type {value.__class__.__name__} for '{key}'"
                )
            return self._dict_value(syntax.get('syntax'), key, value)
        if check == 'record':
            if not isinstance(value, dict):
                raise DeclError(
                    f"Bad data type {value.__class__.__name__} for '{key}'"
                )
            return self._record_value(syntax, value)
        if check == 'enum':
            enum_values = syntax.get('values', [])
            if not value in enum_values:
                raise DeclError(
                    f"Bad value {value} ({value.__class__.__name__}) for "
                    f"'{key}' (correct values: {', '.join(enum_values)})"
                )
            return value
        # At this stage, check is necessary one of the types which don't need
        # conversion.
        if not isinstance(value, types_no_conv[check]):
            raise DeclError(
                f"Bad data type {value.__class__.__name__} for '{key}'"
            )
        return value

    def _dict_value(self, syntax, key, value):
        """
        Validate dict value against syntax if defined and return value.
        """

        # Just set the dict without further validation if syntax dict is not
        # defined.
        if syntax is None:
            return value

        result = {}

        # Check for unknown keys
        unknown_keys = set(value.keys()).difference(set(syntax.keys()))
        if unknown_keys:
            raise DeclError(f"Unknown {key} keys: {', '.join(unknown_keys)}")

        # Iterate over the keys defined in syntax. If the subvalue or default
        # value is defined, set it.
        for subkey in syntax.keys():
            subkey_value = value.get(subkey,
                                     Config._syntax_default(syntax, subkey))
            if subkey_value is not None:
                result[subkey] = self._key_value(
                    syntax[subkey],
                    subkey,
                    subkey_value,
                    syntax[subkey].get('check', 'string')
                )

        return result

    def _record_value(self, syntax, value):
        """
        Associate dict value to key and validate the values based on content
        specification.
        """
        result = {}
        for _key, _value in value.items():
            result[_key] = self._key_value(
                syntax,
                _key,
                _value,
                syntax.get('content', 'string')
            )
        return result

    @staticmethod
    def _get_replacement_dict_key(data, replacement):
        """
        Return a 2-tuple with the dict that contains the replacement parameter
        and the key of this parameter in this dict.
        """
        sub = data
        replacement_items = replacement.split('.')
        # Browse in data dict depth until last replacement item.
        for index, item in enumerate(replacement_items, start=1):
            if index < len(replacement_items):
                if item not in sub:
                    sub[item] = {}
                sub = sub[item]
            else:
                return sub, item
        return None

    def _move_deprecated_param(self, data, param, value):
        """
        If the given parameter is deprecated, move its value to its replacement
        parameter.
        """
        # Leave if parameter not found in syntax, the error is managed in set()
        # method eventually.
        if param not in self.SYNTAX:
            return
        # Check presence of deprecated attribute and leave if not defined.
        replacement = self.SYNTAX[param].get("deprecated")
        if replacement is None:
            return
        # Warn user with FutureWarning.
        warnings.warn(f"Configuration parameter {param} is deprecated, use "
                      f"{' > '.join(replacement.split('.'))} instead",
                      RiftDeprecatedConfWarning)
        # Get position of replacement parameter.
        sub, item = Config._get_replacement_dict_key(data, replacement)
        # If both new and deprecated parameter are defined, emit warning log to
        # explain deprecated parameter is ignored. Else, move deprecated
        # parameter to its new place.
        if item in sub:
            logging.warning("Both deprecated parameter %s and new parameter "
                            "%s are declared in configuration, deprecated "
                            "parameter %s is ignored",
                            param, replacement, param)
        else:
            sub[item] = value
        del data[param]

    def _move_deprecated(self, data):
        """
        Iterate over data dict to check for deprecated parameters and move them
        to their replacements.
        """
        # Load generic options (ie. not architecture specific)
        for param, value in data.copy().items():
            # Skip architecture specific options
            if param in self.get('arch'):
                continue
            self._move_deprecated_param(data, param, value)

        # Load architecture specific options
        for arch in self.get('arch'):
            if arch in data and isinstance(data[arch], dict):
                for param, value in data.copy()[arch].items():
                    self._move_deprecated_param(data[arch], param, value)

    def update(self, data):
        """
        Update config content with data dict, checking data content respect
        SYNTAX spec.
        """
        # Set arch first
        if 'arch' in data:
            self.set('arch', data['arch'])
            del data['arch']

        # Look for deprecated parameters, and update dict with new parameters.
        self._move_deprecated(data)

        # Load generic options (ie. not architecture specific)
        for key, value in data.items():
            # Skip architecture specific options
            if key in self.get('arch'):
                continue
            self.set(key, value)

        # Load architecture specific options
        for arch in self.get('arch'):
            if arch in data:
                if not isinstance(data[arch], dict):
                    raise DeclError(
                        f"Architecture specific override for {arch} must be a "
                        "mapping"
                    )
                for key, value in data[arch].items():
                    self.set(key, value, arch=arch)

    def _check(self):
        """Checks for required options in main syntax recursively."""
        self._check_syntax(self.SYNTAX, self.options)

    def _check_syntax(self, syntax, options, param='__main__'):
        """Checks for mandatory options regarding the provided syntax recursively."""
        for key in syntax:
            if (
                    syntax[key].get('required', False) and
                    'default' not in syntax[key]
                ):
                # Check key is in options or defined in all supported arch
                # specific options.
                if (
                        key not in options and
                        not all(
                            arch in options and key in options[arch]
                            for arch in self.get('arch')
                        )
                    ):
                    if param == '__main__':
                        raise DeclError(f"'{key}' is not defined")
                    raise DeclError(
                        f"Key {key} is required in dict parameter {param}"
                    )
            # If the parameter is a dict with a syntax, check the value.
            if (
                    syntax[key].get('check') == 'dict' and
                    syntax[key].get('syntax') is not None and key in options
                ):
                self._check_syntax(syntax[key]['syntax'], options[key], key)
            # If the parameter is a record with dict values and a syntax, check
            # all values.
            if (
                    syntax[key].get('check') == 'record' and
                    syntax[key].get('content') == 'dict' and
                    syntax[key].get('syntax') is not None and key in options
                ):
                for value in options[key].values():
                    self._check_syntax(syntax[key]['syntax'], value, key)


class Staff():
    """
    List of staff members of a rift project.

    This class helps loading and checking the underlying yaml file content.
    """

    DEFAULT_PATH = _DEFAULT_STAFF_FILE
    DATA_NAME = 'staff'
    ITEMS_HEADER = 'staff'
    ITEMS_KEYS = ['email']

    def __init__(self, config):
        self._data = {}
        self._config = config

    def __contains__(self, item):
        return item in self._data

    def get(self, item):
        """
        Staff getter
        """
        return self._data.get(item)

    def load(self, filepath=None):
        """
        Load yaml file content.

        If filepath is not defined, the default file path is used.
        """
        if filepath is None:
            filepath = self.DEFAULT_PATH

        try:
            with open(self._config.project_path(filepath), encoding='utf-8') as fyaml:
                data = yaml.load(fyaml, Loader=OrderedLoader)

            self._data = data.pop(self.ITEMS_HEADER) or {}

            self._check()

        except AttributeError as exp:
            raise DeclError(f"Bad data format in {self.DATA_NAME} file") from exp
        except KeyError as exp:
            raise DeclError(f"Missing {exp} at top level in {self.DATA_NAME} file") from exp
        except yaml.error.YAMLError as exp:
            raise DeclError(str(exp)) from exp
        except IOError as exp:
            if exp.errno == errno.ENOENT:
                raise DeclError(f"Could not find '{filepath}'") from exp
            raise DeclError(str(exp)) from exp

    def _check(self):
        """
        Verify declaration is correct.

        No missing element, no unnecessary one.
        """
        for people, data in self._data.items():
            # Missing elements
            missing = set(self.ITEMS_KEYS) - set(data.keys())
            if missing:
                items = ', '.join([f"'{item}'" for item in missing])
                raise DeclError(f"Missing {items} item(s) for {people}")

            # Unnecessary elements
            not_needed = set(data.keys()) - set(self.ITEMS_KEYS)
            if not_needed:
                items = ', '.join(sorted([f"'{item}'" for item in not_needed]))
                raise DeclError(f"Unknown {items} item(s) for {people}")


class Modules(Staff):
    """
    List of project modules.

    This class helps loading and checking the underlying yaml file content.
    """

    DEFAULT_PATH = _DEFAULT_MODULES_FILE
    DATA_NAME = 'modules'
    ITEMS_HEADER = 'modules'
    ITEMS_KEYS = ['manager']

    def __init__(self, config, staff):
        Staff.__init__(self, config)
        self.staff = staff

    def _check(self):
        """
        Verify modules declaration is correct.

        No missing element, no unnecessary one.
        """
        Staff._check(self)

        for module in self._data.values():
            # Maintainer exists
            if isinstance(module['manager'], str):
                module['manager'] = [module['manager']]
            for mngr in module['manager']:
                if mngr not in self.staff:
                    msg = f"Manager '{mngr}' does not exist in staff list"
                    raise DeclError(msg)
