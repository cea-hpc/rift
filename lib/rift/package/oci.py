#
# Copyright (C) 2025 CEA
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
"""Manage packages in OCI format."""

import os
import shutil
import time
import tempfile
import tarfile
import glob
import logging

from rift import RiftError
from rift.Config import _DEFAULT_VARIANT
from rift.package._base import Package, ActionableArchPackage
from rift.annex import Annex
from rift.TestResults import TestCase, TestResults
from rift.container import ContainerRuntime
from rift.utils import message, banner

class PackageOCI(Package):
    """Handle rift project package in OCI format."""

    def __init__(self, name, config, staff, modules):
        super().__init__(name, config, staff, modules, 'oci', 'Containerfile')
        self.version = None
        self.release = None
        self.main_source = None
        self.source_topdir = None

    def _serialize_specific_metadata(self):
        """Return dict of format specific metadata to write in metadata file."""
        data = {}
        data['oci'] = {
            'version': self.version,
            'release': self.release
        }
        if self.main_source:
            data['oci']['main_source'] = self.main_source
        if self.source_topdir:
            data['oci']['source_topdir'] = self.source_topdir
        return data

    def _deserialize_specific_metadata(self, data):
        """Set format specific object attribute with values in metadata dict."""
        oci = data.get('oci')
        def str_or_none(value):
            """If value is not None, return its string representation."""
            if value is not None:
                return str(value)
            return value
        if oci:
            self.version = str_or_none(oci.get('version'))
            self.release = str_or_none(oci.get('release'))
            self.main_source = oci.get('main_source')
            self.source_topdir = oci.get('source_topdir')

    def _check_specific_info(self):
        """Check info.yaml OCI specific content is correct."""
        if not self.version:
            raise RiftError("Unable to load oci version from metadata")
        if not self.release:
            raise RiftError("Unable to load oci release from metadata")

    def subpackages(self):
        """Returns list with container name."""
        # Containerfile do not really provide subpackages, then just return name
        # of container in the list.
        return [self.name]

    def build_requires(self):
        """Returns empty list."""
        # Containerfile do not really have build requirements, then just return
        # an empty list.
        return []

    def add_changelog_entry(self, maintainer, comment, bump):
        """Not supported for OCI packages."""
        raise NotImplementedError

    def analyze(self, review, configdir):
        """Not supported for OCI packages."""
        raise NotImplementedError

    def supports_arch(self, arch):
        """
        Return True if arch is the same as host as building container image
        without foreign architecture is not supported.
        """
        return arch in ContainerRuntime.ARCHS_MAP

    def for_arch(self, arch):
        """
        Return OCI package specialized for a given architecture.
        """
        return ActionableArchPackageOCI(self, arch)


class ActionableArchPackageOCI(ActionableArchPackage):
    """Handle rift project package in OCI format for a specific architecture."""

    def __init__(self, package, arch):
        super().__init__(package, arch)
        self.tempdir = tempfile.TemporaryDirectory(prefix='rift-container-setup-')
        self.runtime = ContainerRuntime(self.config)

    @property
    def default_source_topdir(self):
        """Default name of expected top folder in software source archive."""
        return f"{self.name}-{self.package.version}"

    @property
    def default_main_source_glob(self):
        """
        The wildcard expression used by default to find main software source
        archive in package sources subfolder.
        """
        return f"{self.name}?{self.package.version}.*"

    def build(self, **kwargs):
        """Build container image of an OCI package."""
        # Unfortunately, podman does not support signatures on OCI images, only
        # on images pushed in remote registries. Warn signature is skipped when
        # requested.
        if kwargs.get('sign', False):
            logging.warning(
                "Signing OCI container image is not supported, skipping %s OCI "
                "package signature",
                self.name
            )

        sources_topdir = self._setup_sources()
        message(f"Building container image '{self.name}' on "
                f"architecture {self.arch}")
        self.runtime.build(self, sources_topdir)
        message("Container image successfully built")

    def _setup_sources(self):
        extracted_archive = None
        tmp_sourcesdir = Annex(self.config).import_dir(self.package.sourcesdir,
                                                       force_temp=True)
        if not self.package.sources:
            raise RiftError(f"Unable to find sources for package {self.name}")
        if len(self.package.sources) == 1:
            _main_source = os.path.join(tmp_sourcesdir.path,
                                        self.package.sources.pop())
            self._extract_archive(_main_source)
            extracted_archive = _main_source
        else:
            # If main source is defined, check it exists and use it.
            if self.package.main_source:
                if self.package.main_source not in self.package.sources:
                    raise RiftError(
                        f"Unable to find main source {self.package.main_source} among "
                        f"available package sources: {self.package.sources}")
                _main_source = os.path.join(tmp_sourcesdir.path,
                                            self.package.main_source)
                self._extract_archive(_main_source)
                extracted_archive = _main_source
            else:
                # Search archive matching default glob
                found_sources = glob.glob(
                    os.path.join(tmp_sourcesdir.path,
                                 self.default_main_source_glob))
                if len(found_sources) != 1:
                    raise RiftError(
                        "Unable to determine main package source among "
                        f"available package sources: {self.package.sources}")
                self._extract_archive(found_sources[0])
                extracted_archive = found_sources[0]
        # Determine top dir
        topdir = os.path.join(self.tempdir.name,
                              self.package.source_topdir or self.default_source_topdir)
        if not os.path.isdir(topdir):
            raise RiftError(
                f"Unable to find package source top directory {topdir}")
        # Copy all other sources
        for source in self.package.sources:
            _source = os.path.join(tmp_sourcesdir.path, source)
            if _source != extracted_archive:
                shutil.copy(_source, topdir)
        # Copy container file
        shutil.copy(self.buildfile, topdir)
        tmp_sourcesdir.delete()
        return topdir

    def _extract_archive(self, tarball):
        try:
            logging.info("Extracting source tarball %s", tarball)
            with tarfile.open(tarball) as _tarball:
                for member in self._safe_members(_tarball):
                    logging.debug("Extracting file %s", member.name)
                    # With Python >= 3.12, it is possible and recommended to use
                    # filter='data' to avoid path traversal attacks. To stay
                    # compatible with older Python version, fallback without
                    # this argument.
                    try:
                        _tarball.extract(member, path=self.tempdir.name, filter='data')
                    except TypeError:
                        _tarball.extract(member, path=self.tempdir.name)
        except (tarfile.ReadError, tarfile.CompressionError) as err:
            raise RiftError(
                f"Unable to extract source tarball {tarball}: {err}"
            ) from err

    def _safe_members(self, tarball):
        for member in tarball.getmembers():
            if os.path.isabs(member.name):
                raise RiftError(
                    f"Source archive contains file {member.name} with absolute "
                    "path")
            target = os.path.realpath(os.path.join(self.tempdir.name, member.name))
            if os.path.commonpath([target, self.tempdir.name]) != self.tempdir.name:
                raise RiftError(
                    f"Source archive contains file {target} outside file tree")
            yield member

    def test(self, **kwargs):
        """Execute test in OCI container and return TestResults"""
        results = TestResults('test')
        banner(f"Starting tests of package {self.name} on architecture {self.arch}")
        tests = list(self.package.tests())
        for test in tests:
            case = TestCase(
                test.name, self.name, _DEFAULT_VARIANT, self.arch, 'oci'
            )
            now = time.time()
            message(f"Running test '{case.fullname}' on architecture '{self.arch}'")
            if test.local:
                run = self.run_local_test(test)
            else:
                run = self.runtime.run_test(self, test)
            if run.returncode == 0:
                results.add_success(case, time.time() - now, out=run.out, err=run.err)
                message(f"Test '{case.fullname}' on architecture {self.arch}: OK")
            else:
                results.add_failure(case, time.time() - now, out=run.out, err=run.err)
                message(f"Test '{case.fullname}' on architecture {self.arch}: ERROR")
        return results

    def publish(self, **kwargs):
        """Publish archive of a container in OCI registry."""
        # No notion of staging repository in OCI format, no-op in this case.
        if kwargs.get('staging', False):
            return

        assert self.repos.path is not None

        message("Publishing container image...")
        self.repos.ensure_created()
        archive_path = os.path.join(self.repos.path,
            f"{self.name}_{self.package.version}-{self.package.release}.{self.arch}.tar")
        self.runtime.archive(self, archive_path)
