#
# Copyright (C) 2014-2025 CEA
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
Class to manipulate packages and package tests with Rift.
"""

import glob
import logging
import os
import yaml

from rift import RiftError
from rift.Config import OrderedLoader
from rift.utils import message

_META_FILE = 'info.yaml'
_SOURCES_DIR = 'sources'
_TESTS_DIR = 'tests'
_DOC_FILES = ['README', 'README.md', 'README.rst', 'README.txt']

class Package():
    """
    Base object in Rift framework.

    It creates, load, update, check, build and test a package.
    """

    def __init__(self, name, config, staff, modules, _format, buildfile):
        self._config = config
        self._staff = staff
        self._modules = modules
        self.name = name
        # check package format
        if _format != 'rpm':
            raise RiftError(f"Unsupported package format {_format}")
        self.format = _format

        # infos.yaml
        self.module = None
        self.maintainers = []
        self.reason = None
        self.origin = None
        self.depends = None
        self.exclude_archs = None

        # Static paths
        pkgdir = os.path.join(self._config.get('packages_dir'), self.name)
        self.dir = self._config.project_path(pkgdir)
        self.sourcesdir = os.path.join(self.dir, _SOURCES_DIR)
        self.testsdir = os.path.join(self.dir, _TESTS_DIR)
        self.metafile = os.path.join(self.dir, _META_FILE)
        self.buildfile = os.path.join(self.dir, buildfile)
        self.docfiles = []
        for doc in _DOC_FILES:
            self.docfiles.append(os.path.join(self.dir, doc))

        self.sources = set()

    def check(self):
        """Load package and check info."""
        message('Validate package info...')
        self.check_info()

    def _check_generic_info(self):
        """
        Check info.yaml generic content is correct.

        This uses Staff and Modules content.
        """

        # Check maintainers
        if not self.maintainers:
            raise RiftError("Maintainers are missing")
        for maintainer in self.maintainers:
            if maintainer not in self._staff:
                raise RiftError(f"Maintainer '{maintainer}' is not defined")

        # Check module
        if not self.module:
            raise RiftError("Module is missing")
        if self.module not in self._modules:
            raise RiftError(f"Module '{self.module}' is not defined")

        # Check reason
        if self.reason is None:
            raise RiftError("Missing reason")

    def _check_specific_info(self):
        """
        Check info.yaml format specific content is correct. No-op in base class,
        designed to be overriden when necessary in format specific class.
        """

    def check_info(self):
        """Check info.yaml generic and format specific content is correct."""
        self._check_generic_info()
        self._check_specific_info()

    def _serialize_generic_metadata(self):
        """Return dict of package generic metadata to write in metadata file."""
        data = {}
        if self.module:
            data['module'] = self.module
        if self.reason:
            data['reason'] = self.reason
        if self.maintainers:
            data['maintainers'] = self.maintainers
        if self.origin:
            data['origin'] = self.origin
        if self.depends:
            data['depends'] = self.depends
        if self.exclude_archs:
            data['exclude_archs'] = self.exclude_archs
        return data

    def _serialize_specific_metadata(self):
        """
        Return dict of format specific metadata to write in metadata file. This
        is an empty in base class, designed to be overriden when necessary in
        format specific classes.
        """
        return {}

    def _serialize_metadata(self):
        """Return dict of package metadata to write in metadata file."""
        data = self._serialize_generic_metadata()
        data.update(self._serialize_specific_metadata())
        return data

    def write(self):
        """
        Create or update the file and directory structure for this package
        instance.
        """

        # Create package directory if needed
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)

        # Write meta information
        data = self._serialize_metadata()
        with open(self.metafile, 'w', encoding='utf-8') as fyaml:
            yaml.dump({'package': data}, fyaml, default_flow_style=False)

    def _deserialize_generic_metadata(self, data):
        """Set generic package object attribute with values in metadata dict."""
        self.module = data.get('module')
        if isinstance(data.get('maintainers'), str):
            self.maintainers = [data['maintainers']]
        else:
            self.maintainers = data.get('maintainers')
        self.reason = data.get('reason')
        self.origin = data.get('origin')
        depends = data.get('depends')
        if depends is not None:
            if isinstance(depends, str):
                self.depends = [depends]
            else:
                self.depends = depends
        if isinstance(data.get('exclude_archs'), str):
            self.exclude_archs = [data.get('exclude_archs')]
        else:
            self.exclude_archs = data.get('exclude_archs', [])

    def _deserialize_specific_metadata(self, data):
        """
        Set format specific package object attribute with values in metadata
        dict. No-op in base class, designed to be overriden when necessary in
        format specific classes.
        """

    def _deserialize_metadata(self, data):
        """Set package object attribute with values in metadata dict."""
        self._deserialize_generic_metadata(data)
        self._deserialize_specific_metadata(data)

    def load_info(self, infopath=None):
        """Read package metadata 'info.yaml' and check its content."""

        if infopath is None:
            if not os.path.exists(self.dir):
                msg = f"Package '{self.name}' directory does not exist"
                raise RiftError(msg)
            infopath = self.metafile

        with open(infopath, encoding='utf-8') as fyaml:
            data = yaml.load(fyaml, Loader=OrderedLoader)

        data = data.pop('package') or {}
        self._deserialize_metadata(data)

        self.check_info()

        if os.path.exists(self.sourcesdir):
            self.sources = set(os.listdir(self.sourcesdir))

    def load(self, infopath=None):
        """Read package metadata 'info.yaml' and check its content."""
        self.load_info(infopath)

    def tests(self):
        """An iterator over Test objects for each test files."""
        testspattern = os.path.join(self.testsdir, '*.sh')
        for testpath in glob.glob(testspattern):
            yield Test(testpath)

    def supports_arch(self, arch):
        """
        Return True if package does not exclude any architecture or the given
        arch is not listed in excluded architectures.
        """
        return not self.exclude_archs or arch not in self.exclude_archs

class ActionableArchPackage:
    """
    Abstract class to build, test and publish package for a specific format and
    architecture. This class must be overriden with expected methods for every
    supported package formats.
    """
    def __init__(self, package, arch):
        self.name = package.name
        self.buildfile = package.buildfile
        self.config = package._config
        self.package = package
        self.arch = arch

    def build(self, **kwargs):
        """Build package. Must be overriden in concrete format classes."""
        raise NotImplementedError

    def test(self, **kwargs):
        """Test package. Must be overriden in concrete format classes."""
        raise NotImplementedError

    def publish(self, **kwargs):
        """Publish package. Must be overriden in concrete format classes."""
        raise NotImplementedError

    def clean(self, **kwargs):
        """
        Clean package build environment. No-op by default but can be overriden
        in concrete format class.
        """


class Test():
    """
    Wrapper around test scripts or test commands.

    It analyzes if test script is flagged as local one or if it should be run
    inside the VM.
    """

    _LOCAL_PATTERN = '*** RIFT LOCAL ***'

    def __init__(self, command, name=None):
        self.command = command
        self.local = False
        self.name = name
        if os.path.exists(self.command):
            self.name = name or os.path.splitext(os.path.basename(command))[0]
            self._analyze()

    def _analyze(self, blocksize=4096):
        """
        Look for special LOCAL PATTERN in file header and flag the file
        accordingly.
        """
        with open(self.command, 'rt', encoding='utf-8') as ftest:
            data = ftest.read(blocksize)
            if self._LOCAL_PATTERN in data:
                logging.debug("Test '%s' detected as local", self.name)
                self.local = True
