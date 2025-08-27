#
# Copyright (C) 2014-2018 CEA
#

"""
Helper module to write unit tests for Rift project.
It contains several helper methods or classes like temporary file management.
"""

import logging
import tempfile
import unittest
import os
from collections import OrderedDict

import shutil
import jinja2
import yaml
from collections import namedtuple
from contextlib import contextmanager

from rift.Config import Config, Staff, Modules
from rift.Mock import Mock

MOCK_CONF = '''\
config_opts['chroot_setup_cmd'] = 'install tar gcc-c++ redhat-rpm-config redhat-release which xz sed make bzip2 gzip gcc coreutils unzip diffutils cpio bash gawk rpm-build info patch util-linux findutils grep'
config_opts['dist'] = 'el8.alma'  # only useful for --resultdir variable subst
config_opts['releasever'] = '8'
config_opts['package_manager'] = 'dnf'
config_opts['extra_chroot_dirs'] = [ '/run/lock', ]
config_opts['bootstrap_image'] = 'quay.io/almalinuxorg/almalinux:8'
config_opts['dnf.conf'] = """

[main]
keepcache=1
debuglevel=2
reposdir=/dev/null
logfile=/var/log/yum.log
retries=20
obsoletes=1
gpgcheck=0
assumeyes=1
syslog_ident=mock
syslog_device=
metadata_expire=0
mdpolicy=group:primary
best=1
install_weak_deps=0
protected_packages=
module_platform_id=platform:el8
user_agent={{ user_agent }}


{% for repo in repos %}
[{{ repo.name }}]
name={{ repo.name }}
baseurl={{ repo.url }}
priority={{ repo.priority }}
{%if repo.module_hotfixes %}
module_hotfixes={{ repo.module_hotfixes }}
{% endif %}
{% endfor %}
"""
'''

SPEC_TPL = """\
%global foo 1.%{bar}
%define bar 1
Name:           {{ name }}
Version:        {{ version }}
Release:        {{ release }}
Summary:        A package
Group:          System Environment/Base
License:        GPL
URL:            http://nowhere.com/projects/%{name}/
Source0:        https://nowhere.com/sources/%{name}-%{version}.tar.gz
{% if exclusive_arch %}
ExclusiveArch:  {{ exclusive_arch }}
{% endif -%}
BuildArch:      {{ arch }}
BuildRequires:  br-package
Requires:       another-package
Provides:       {{ name }}-provide

%description
A package

%prep
{{ prepsteps | default("") }}

%build
# Nothing to build
{{ buildsteps | default("") }}

%install
# Nothing to install
{{ installsteps | default("") }}

%files
# No files
{{ files | default("") }}

%changelog
* Tue Feb 26 2019 Myself <buddy@somewhere.org> {{ version }}-{{release}}
- Update to {{ version }} release
"""

SubPackage = namedtuple("SubPackage", ["name"])


class RiftTestCase(unittest.TestCase):
    """unittest.TestCase subclass with additional features"""

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)
        # Allow to show the full content of a diff
        self.maxDiff = None

    def assert_except(self, exc_cls, exc_str, callable_obj, *args, **kwargs):
        """
        Same as TestCase.assertRaises() but with an additional argument to
        verify raised exception string is correct.
        """
        try:
            callable_obj(*args, **kwargs)
        except exc_cls as exp:
            self.assertEqual(str(exp), exc_str)
        else:
            self.fail("%s not raised" % exc_cls.__name__)

class RiftProjectTestCase(RiftTestCase):
    """
    RiftTestCase that setup a dummy project tree filled with minimal
    requirements.
    """

    def setUp(self):
        self.cwd = os.getcwd()
        self.projdir = make_temp_dir()
        # ./packages/
        self.packagesdir = os.path.join(self.projdir, 'packages')
        os.mkdir(self.packagesdir)
        # ./packages/staff.yaml
        self.staffpath = os.path.join(self.packagesdir, 'staff.yaml')
        with open(self.staffpath, "w") as staff:
            staff.write('staff: {Myself: {email: buddy@somewhere.org}}')
        # ./packages/modules.yaml
        self.modulespath = os.path.join(self.packagesdir, 'modules.yaml')
        with open(self.modulespath, "w") as mod:
            mod.write('modules: {Great module: {manager: Myself}}')
        # ./annex/
        self.annexdir = os.path.join(self.projdir, 'annex')
        os.mkdir(self.annexdir)
        # ./project.conf
        self.projectconf = os.path.join(self.projdir, Config._DEFAULT_FILES[0])
        with open(self.projectconf, "w") as conf:
            conf.write("annex:           %s\n" % self.annexdir)
            conf.write("vm_image:        test.img\n")
            conf.write("repos:           {}\n")
        os.chdir(self.projdir)
        # Dict of created packages
        self.pkgdirs = {}
        self.pkgspecs = {}
        self.pkgsrc = {}
        # Load project/staff/modules
        self.config = Config()
        self.config.load()
        self.staff = Staff(config=self.config)
        self.staff.load(self.staffpath)
        self.modules = Modules(config=self.config, staff=self.staff)
        self.modules.load(self.modulespath)
        # ./mock.tpl
        self.mocktpl = os.path.join(self.projdir, Mock.MOCK_TEMPLATE)
        with open(self.mocktpl, "w") as fh:
            fh.write(MOCK_CONF)

    def tearDown(self):
        os.chdir(self.cwd)
        os.unlink(self.projectconf)
        os.unlink(self.staffpath)
        os.unlink(self.modulespath)
        os.unlink(self.mocktpl)
        os.rmdir(self.annexdir)
        for spec in self.pkgspecs.values():
            os.unlink(spec)
        for src in self.pkgsrc.values():
            os.unlink(src)
        for pkgdir in self.pkgdirs.values():
            os.unlink(os.path.join(pkgdir, 'info.yaml'))
            os.rmdir(os.path.join(pkgdir, 'sources'))
            os.rmdir(pkgdir)
        # Remove potentially generated files for VM related tests
        for path in [
            self.config.project_path(self.config.get('vm_cloud_init_tpl')),
            self.config.project_path(self.config.get('vm_build_post_script')),
            self.config.project_path(self.config.get('vm_image')),
        ]:
            if os.path.exists(path):
                os.unlink(path)
        os.rmdir(self.packagesdir)
        os.rmdir(self.projdir)

    def update_project_conf(self):
        """Update project YAML configuration file with new Config options."""
        class OrderedDumper(yaml.SafeDumper):
            pass
        def _dict_representer(dumper, data):
            return dumper.represent_mapping(
                yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                data.items()
            )
        OrderedDumper.add_representer(OrderedDict, _dict_representer)
        with open(self.projectconf, 'w') as fh:
            fh.write(yaml.dump(self.config.options, Dumper=OrderedDumper))

    def make_pkg(
        self,
        name='pkg',
        version='1.0',
        release='1',
        metadata=None,
        build_requires=['br-package'],
        requires=['another-package'],
        subpackages=[],
    ):
        # ./packages/pkg
        self.pkgdirs[name] = os.path.join(self.packagesdir, name)
        os.mkdir(self.pkgdirs[name])
        # ./packages/pkg/info.yaml
        info = os.path.join(self.pkgdirs[name], 'info.yaml')
        if metadata is None:
            metadata = {}
        with open(info, "w") as nfo:
            nfo.write("package:\n")
            nfo.write("    maintainers:\n")
            nfo.write("        - Myself\n")
            nfo.write(
                "    module: {}\n".format(
                    metadata.get('module', 'Great module')
                )
            )
            nfo.write(
                "    origin: {}\n".format(metadata.get('origin', 'Vendor'))
            )
            nfo.write(
                "    reason: {}\n".format(
                    metadata.get('reason', 'Missing feature')
                )
            )

        # ./packages/pkg/pkg.spec
        self.pkgspecs[name] = os.path.join(self.pkgdirs[name],
                                           "{0}.spec".format(name))
        with open(self.pkgspecs[name], "w") as spec:
            spec.write("Name:    {0}\n".format(name))
            spec.write("Version:        {0}\n".format(version))
            spec.write("Release:        {0}\n".format(release))
            spec.write("Summary:        A package\n")
            spec.write("Group:          System Environment/Base\n")
            spec.write("License:        GPL\n")
            spec.write("URL:            http://nowhere.com/projects/%{name}/\n")
            spec.write("Source0:        %{name}-%{version}.tar.gz\n")
            spec.write("BuildArch:      noarch\n")
            for build_require in build_requires:
                spec.write(f"BuildRequires:  {build_require}\n")
            for require in requires:
                spec.write(f"Requires:       {require}\n")
            spec.write("Provides:       {0}-provide\n".format(name))
            spec.write("%description\n")
            spec.write("A package\n")
            for subpackage in subpackages:
                spec.write(f"%package -n {subpackage.name}\n")
                spec.write(f"Summary: Sub-package {subpackage.name}\n")
                spec.write(f"%description -n {subpackage.name}\n")
                spec.write(f"Description for package {subpackage.name}\n")

            spec.write("%prep\n")
            spec.write("%build\n")
            spec.write("# Nothing to build\n")
            spec.write("%install\n")
            spec.write("# Nothing to install\n")
            spec.write("%files\n")
            spec.write("# No files\n")
            spec.write("%changelog\n")
            spec.write("* Tue Feb 26 2019 Myself <buddy@somewhere.org>"
                       " - {0}-{1}\n".format(version, release))
            spec.write("- Update to {0} release\n".format(version))

        # ./packages/pkg/sources
        srcdir = os.path.join(self.pkgdirs[name], 'sources')
        os.mkdir(srcdir)

        # ./packages/pkg/sources/pkg-version.tar.gz
        self.pkgsrc[name] = os.path.join(srcdir,
                                         "{0}-{1}.tar.gz".format(name, version))
        with open(self.pkgsrc[name], "w") as src:
            src.write("ACACACACACACACAC")

    def clean_mock_environments(self):
        """Remove mock build environments."""
        for arch in self.config.get('arch'):
            mock = Mock(self.config, arch)
            mock.scrub()

    def copy_cloud_init_tpl(self):
        """Copy cloud-init template in project tree."""
        shutil.copy(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                '..',
                'template',
                'cloud-init.tpl',
            ),
            self.config.project_path(self.config.get('vm_cloud_init_tpl')),
        )

    def copy_build_post_script(self):
        """Copy example build post script in project tree."""
        shutil.copy(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                '..',
                'template',
                'build-post.sh',
            ),
            self.config.project_path(self.config.get('vm_build_post_script')),
        )

    def ensure_vm_images_cache_dir(self):
        """Ensure VM images cache directory exists."""
        cache_dir =  self.config.project_path(
            self.config.get('vm_images_cache')
        )
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)

#
# RPM spec file
#
def gen_rpm_spec(**kwargs):
    return jinja2.Template(SPEC_TPL).render(**kwargs)


#
# Temp files
#
def make_temp_dir():
    """Create and return the name of a temporary directory."""
    return tempfile.mkdtemp(prefix='rift-test-')

def make_temp_filename():
    """Return a temporary name for a file."""
    return (tempfile.mkstemp(prefix='rift-test-'))[1]

def make_temp_file(text, delete=True):
    """ Create a temporary file with the provided text."""
    tmp = tempfile.NamedTemporaryFile(prefix='rift-test-', delete=delete)
    tmp.write(text.encode())
    tmp.flush()
    return tmp
