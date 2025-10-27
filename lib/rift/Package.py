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
Class to manipulate packages and package tests with Rift.
"""

import logging
import os
import shutil
import yaml

from rift import RiftError
from rift.Annex import Annex
from rift.Config import OrderedLoader

_META_FILE = 'info.yaml'
_SOURCES_DIR = 'sources'
_TESTS_DIR = 'tests'
_DOC_FILES = ['README', 'README.md', 'README.rst', 'README.txt']

class Package():
    """
    Base object in Rift framework.

    It creates, load, update, check, build and test a package.
    """

    def __init__(self, name, config, staff, modules):
        self._config = config
        self._staff = staff
        self._modules = modules
        self.name = name

        # infos.yaml
        self.module = None
        self.maintainers = []
        self.reason = None
        self.origin = None
        self.ignore_rpms = None
        self.rpmnames = None

        # Static paths
        pkgdir = os.path.join(self._config.get('packages_dir'), self.name)
        self.dir = self._config.project_path(pkgdir)
        self.sourcesdir = os.path.join(self.dir, _SOURCES_DIR)
        self.testsdir = os.path.join(self.dir, _TESTS_DIR)
        self.metafile = os.path.join(self.dir, _META_FILE)
        self.specfile = os.path.join(self.dir, f"{self.name}.spec")
        self.docfiles = []
        for doc in _DOC_FILES:
            self.docfiles.append(os.path.join(self.dir, doc))

        self.sources = set()

    def check_info(self):
        """
        Check info.yaml content is correct.

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

    def write(self):
        """
        Create or update the file and directory structure for this package
        instance.
        """

        # Create package directory if needed
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)

        # Write meta information
        data = {}
        if self.module:
            data['module'] = self.module
        if self.reason:
            data['reason'] = self.reason
        if self.maintainers:
            data['maintainers'] = self.maintainers
        if self.origin:
            data['origin'] = self.origin
        if self.rpmnames:
            data['rpm_names'] = self.rpmnames
        if self.ignore_rpms:
            data['ignore_rpms'] = self.ignore_rpms

        with open(self.metafile, 'w', encoding='utf-8') as fyaml:
            yaml.dump({'package': data}, fyaml, default_flow_style=False)

    def load(self, infopath=None):
        """Read package metadata 'info.yaml' and check its content."""

        if infopath is None:
            if not os.path.exists(self.dir):
                msg = f"Package '{self.name}' directory does not exist"
                raise RiftError(msg)
            infopath = self.metafile

        with open(infopath, encoding='utf-8') as fyaml:
            data = yaml.load(fyaml, Loader=OrderedLoader)

        data = data.pop('package') or {}
        self.module = data.get('module')
        if isinstance(data.get('maintainers'), str):
            self.maintainers = [data['maintainers']]
        else:
            self.maintainers = data.get('maintainers')
        self.reason = data.get('reason')
        self.origin = data.get('origin')
        if isinstance(data.get('rpm_names'), str):
            self.rpmnames = [data.get('rpm_names')]
        else:
            self.rpmnames = data.get('rpm_names')
        if isinstance(data.get('ignore_rpms'), str):
            self.ignore_rpms = [data.get('ignore_rpms')]
        else:
            self.ignore_rpms = data.get('ignore_rpms', [])

        self.check_info()

        if os.path.exists(self.sourcesdir):
            self.sources = set(os.listdir(self.sourcesdir))

    def tests(self):
        """
        Return a Test object for each test present
        in the "tests" directory of a Rift Package.
        A test is any kind of file which the execution
        permission.
        """

        if not os.path.isdir(self.testsdir):
            logging.info('%s not found, this package has no custom tests', self.testsdir)
            return

        for filepath in os.scandir(self.testsdir):
            if os.access(filepath, os.X_OK):
                logging.info("found '%s' executable file", filepath)
                yield Test(filepath)

            else:
                logging.debug(f"'%s' is not executable, not considered as a test", filepath)

    def build_srpm(self, mock, sign):
        """
        Build package source RPM
        """
        tmpdir = Annex(self._config).import_dir(self.sourcesdir,
                                                force_temp=True)

        # To avoid root_squash issue, also copy the specfile in the temp dir
        tmpspec = os.path.join(tmpdir.path, os.path.basename(self.specfile))
        shutil.copyfile(self.specfile, tmpspec)

        srpm = mock.build_srpm(tmpspec, tmpdir.path or self.sourcesdir, sign)
        tmpdir.delete()
        return srpm

    def build_rpms(self, mock, srpm, sign):
        """
        Build package RPMS using provided `srpm' and repository list for build
        requires.
        """
        return mock.build_rpms(srpm, sign)

    @classmethod
    def list(cls, config, staff, modules, names=None):
        """
        Iterate over Package instances from 'names' list or all packages
        if list is not provided.
        """
        if not names:
            pkgdir = config.project_path(config.get('packages_dir'))
            names = [path for path in os.listdir(pkgdir)
                     if os.path.isdir(os.path.join(pkgdir, path))]

        for name in names:
            yield cls(name, config, staff, modules)


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
