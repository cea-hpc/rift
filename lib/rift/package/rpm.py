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
"""Manage packages in RPM format."""

import logging
import os
import random
import shutil
import textwrap
import time
import re

from rift import RiftError
from rift.package._base import Package, ActionableArchPackage, Test
from rift.Annex import Annex
from rift.Repository import ProjectArchRepositories
from rift.Mock import Mock
from rift.RPM import Spec
from rift.TestResults import TestCase, TestResults
from rift.VM import VM
from rift.Config import _DEFAULT_VARIANT
from rift.utils import message, banner

class PackageRPM(Package):
    """Handle rift project package in RPM format."""

    def __init__(self, name, config, staff, modules):
        super().__init__(name, config, staff, modules, 'rpm', f"{name}.spec")

        # Attributes assigned in load()
        # Extracted from infos.yaml
        self.ignore_rpms = None
        self.rpmnames = None
        self.variants = []
        # Spec object
        self.spec = None

    def _serialize_specific_metadata(self):
        """Return dict of format specific metadata to write in metadata file."""
        data = {}
        if self.rpmnames:
            data['rpm_names'] = self.rpmnames
        if self.ignore_rpms:
            data['ignore_rpms'] = self.ignore_rpms
        if self.variants:
            data['variants'] = self.variants
        return data

    def _deserialize_specific_metadata(self, data):
        """Set format specific object attribute with values in metadata dict."""
        if isinstance(data.get('rpm_names'), str):
            self.rpmnames = [data.get('rpm_names')]
        else:
            self.rpmnames = data.get('rpm_names', [])
        if isinstance(data.get('ignore_rpms'), str):
            self.ignore_rpms = [data.get('ignore_rpms')]
        else:
            self.ignore_rpms = data.get('ignore_rpms', [])
        if isinstance(data.get('variants'), str):
            self.variants = [data.get('variants')]
        else:
            self.variants = data.get('variants', [_DEFAULT_VARIANT])

    def load(self, infopath=None):
        """Load package metadata, check its content and load RPM spec file with
        its main attributes."""
        # load infos.yaml with parent class
        super().load(infopath)
        self.spec = Spec(self.buildfile, config=self._config)
        self.version = self.spec.version
        self.release = self.spec.release
        self.arch = self.spec.arch
        self.changelog_name = self.spec.changelog_name
        self.changelog_time = self.spec.changelog_time
        self.buildrequires = self.spec.buildrequires

    def check(self):
        # Check generic package metadata
        super().check()

        # Check spec
        assert self.spec is not None
        message('Validate specfile...')
        self.spec.check(self)

    def subpackages(self):
        """Returns list of provides declared in spec file."""
        # Check if spec is already loaded
        assert self.spec is not None

        return self.spec.provides

    def build_requires(self):
        """Returns list of build requirements declared in spec file."""
        # Parse buildrequires string in spec file to discard explicit versions
        # enforcement.
        #
        # Note this is currently done this way for the sake of simplicity,
        # despite the value that could be provided by these version constraints.
        # It could notably be interesting to extract lesser version constraints
        # when a dependency is updated to a greater version.
        #
        # Currently, the automatic rebuilds of recursive reverse dependencies
        # eventually fail at some point because of invalid versioning in this
        # case but it could be nice to fail faster by detecting mismatching
        # versions before the actual builds.
        return [
            value.group(1)
            for value
            in re.finditer(r"(\S+)( (>|>=|=|<=|<) \S+)?", self.spec.buildrequires)
        ]

    def add_changelog_entry(self, maintainer, comment, bump):
        """Add entry in RPM spec changelog."""
        # Check spec is already loaded
        assert self.spec is not None

        # Check maintainer is present in staff of raise error
        if maintainer not in self._staff:
            raise RiftError(
                f"Unknown maintainer {maintainer}, cannot be found in staff"
            )

        # Compute author string
        author = f"{maintainer} <{self._staff.get(maintainer)['email']}>"
        # Format comment.
        # Grab bullet, insert one if not found.
        bullet = "-"
        match = re.search(r'^([^\s\w])\s', comment, re.UNICODE)
        if match:
            bullet = match.group(1)
        else:
            comment = bullet + " " + comment

        if comment.find("\n") == -1:
            wrapopts = {"subsequent_indent": (len(bullet) + 1) * " ",
                        "break_long_words": False,
                        "break_on_hyphens": False}
            comment = textwrap.fill(comment, 80, **wrapopts)

        logging.info("Adding changelog record for '%s'", author)
        self.spec.add_changelog_entry(author, comment, bump)

    def has_real_variants(self):
        """Return True if package has more then the default main variant."""
        assert(len(self.variants))  # Cannot be called with empty variants list.
        return len(self.variants) > 1 or self.variants[0] != _DEFAULT_VARIANT

    def supports_arch(self, arch):
        """
        Returns True if provided architecture is listed in package spec file's
        ExclusiveArch (or if spec file does not have ExclusiveArch).
        """
        assert self.spec is not None
        return super().supports_arch(arch) and (
            not self.spec.exclusive_archs or arch in self.spec.exclusive_archs
        )

    def for_arch(self, arch):
        """
        Return RPM package specialized for a given architecture.
        """
        return ActionableArchPackageRPM(self, arch)


class ActionableArchPackageRPM(ActionableArchPackage):
    """Handle rift project package in RPM format for a specific architecture."""

    def __init__(self, package, arch):
        super().__init__(package, arch)
        self.mock = Mock(self.config, arch, self.config.get('version'))
        self.repos = ProjectArchRepositories(self.config, self.arch)

    def build(self, **kwargs):
        message(f"Building RPM package '{self.name}' on architecture {self.arch}")

        # Define list of repositories included in mock build environment
        mock_repos = self.repos.all
        # If staging is set, append it to the list of repositories in mock build
        # environment.
        staging = kwargs.get('staging')
        if staging:
            mock_repos += staging.consumables[self.arch]

        message('Preparing Mock environment...')
        self.mock.init(mock_repos)

        message("Building SRPM...")
        sign = kwargs.get('sign', False)
        srpm = self._build_srpm(sign)
        logging.info("Built: %s", srpm.filepath)

        for variant in self.package.variants:
            message(
                "Building RPMS"
                + (f" variant {variant}" if self.package.has_real_variants() else '')
                + "..."
            )
            for rpm in self._build_rpms(srpm, variant, sign):
                logging.info('Built: %s', rpm.filepath)

        message("RPMS successfully built")

    def test(self, **kwargs):
        """Execute test and return TestResults"""

        results = TestResults('test')
        staging = kwargs.get('staging')
        if staging:
            extra_repos=[staging.consumables[self.arch]]
        else:
            extra_repos=[]
        vm = VM(self.config, self.arch, extra_repos=extra_repos)

        if vm.running():
            raise RiftError('VM is already running')

        message(f"Preparing {self.arch} test environment")
        vm.start(False)

        for variant in self.package.variants:
            # Setup repos in VM considering the variant and presence of working
            # repository.
            repos_args = ''
            if variant != _DEFAULT_VARIANT:
                for repo in self.repos.for_variant(variant):
                    repos_args += f"--enablerepo={repo} "
            if self.repos.working is None:
                repos_args = '--disablerepo=working'
            vm.cmd(f"yum -y -d0 {repos_args} update")

            banner(
                f"Starting tests of package {self.name}"
                + (f" variant {variant}" if self.package.has_real_variants() else '')
                + f" on architecture {self.arch}"
            )

            tests = list(self.package.tests())
            if not kwargs.get('noauto', False):
                tests.insert(0, BasicTest(self.package, variant, config=self.config))
            for test in tests:
                case = TestCase(test.name, self.name, variant, self.arch)
                now = time.time()
                message(f"Running test '{case.fullname}' on architecture '{self.arch}'")
                proc = vm.run_test(test, variant)
                if proc.returncode == 0:
                    results.add_success(
                        case, time.time() - now, out=proc.out, err=proc.err
                    )
                    message(f"Test '{case.fullname}' on architecture {self.arch}: OK")
                else:
                    results.add_failure(
                        case, time.time() - now, out=proc.out,  err=proc.err
                    )
                    message(
                        f"Test '{case.fullname}' on architecture {self.arch}: ERROR"
                    )

        if not kwargs.get('noquit', False):
            message(f"Cleaning {self.arch} test environment")
            vm.cmd("poweroff")
            time.sleep(5)
            vm.stop()

        return results

    def publish(self, **kwargs):
        staging = kwargs.get('staging')
        if staging:
            repo = staging
        else:
            repo = self.repos.working

        assert repo is not None

        message("Publishing RPMS...")
        self.mock.publish(repo)

        if kwargs.get('updaterepo', True):
            message("Updating repository...")
            repo.update()

    def clean(self, **kwargs):
        if kwargs.get('noquit', False):
            message("Keep environment, VM is running. Use: rift vm connect")
        else:
            self.mock.clean()

    def _build_srpm(self, sign):
        """
        Build package source RPM
        """
        tmpdir = Annex(self.config).import_dir(self.package.sourcesdir,
                                               force_temp=True)

        # To avoid root_squash issue, also copy the specfile in the temp dir
        tmpspec = os.path.join(tmpdir.path, os.path.basename(self.buildfile))
        shutil.copyfile(self.buildfile, tmpspec)

        srpm = self.mock.build_srpm(tmpspec, tmpdir.path or self.package.sourcesdir, sign)
        tmpdir.delete()
        return srpm

    def _build_rpms(self, srpm, variant, sign):
        """
        Build package RPMS using provided `srpm' and repository list for build
        requires.
        """
        return self.mock.build_rpms(srpm, variant, self.repos, sign)


class BasicTest(Test):
    """
    Auto-generated test for a PackageRPM.
    Setup a test to install a package and its dependencies.
        - pkg: package to test
        - variant: package variant
        - config: rift configuration
    """

    def __init__(self, pkg, variant, config=None):
        if pkg.rpmnames:
            rpmnames = pkg.rpmnames
        else:
            rpmnames = Spec(pkg.buildfile, config=config, variant=variant).pkgnames

        try:
            for name in pkg.ignore_rpms:
                rpmnames.remove(name)
        except ValueError as exc:
            raise RiftError(f"'{name}' is not in RPMS list") from exc

        # Avoid always processing the rpm list in the same order
        random.shuffle(rpmnames)

        cmd = textwrap.dedent(f"""
        if [ -x /usr/bin/dnf ] ; then
            YUM="dnf"
        else
            YUM="yum"
        fi
        i=0
        for pkg in {' '.join(rpmnames)}; do
            i=$(( $i + 1 ))
            echo -e "[Testing '${{pkg}}' (${{i}}/{len(rpmnames)})]"
            rm -rf /var/lib/${{YUM}}/history*
            if rpm -q --quiet $pkg; then
              ${{YUM}} -y -d1 upgrade $pkg || exit 1
            else
              ${{YUM}} -y -d1 install $pkg || exit 1
            fi
            if [ -n "$(${{YUM}} history | tail -n +3)" ]; then
                echo '> Cleanup last transaction'
                ${{YUM}} -y -d1 history undo last || exit 1
            else
                echo '> Warning: package already installed and up to date !'
            fi
        done""")
        Test.__init__(self, cmd, "basic_install")
        self.local = False
