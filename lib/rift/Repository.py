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
Helper class for YUM repository structure management.
"""

import os
import logging
import shutil
import glob
from subprocess import Popen, PIPE, STDOUT, run, CalledProcessError

from rift import RiftError
from rift.RPM import RPM, Spec
from rift.TempDir import TempDir
from rift.Config import _DEFAULT_REPO_CMD

class ConsumableRepository():
    """
    Manipulate RPM packages repository to be consumed by dnf/yum and Mock.
    """
    FILE_SCHEME = 'file://'

    def __init__(self, url, name=None, priority=None, options=None, default_proxy=None):
        self.url = url
        self.name = name
        self.priority = priority
        if options is None:
            options = {}
        self.module_hotfixes = options.get('module_hotfixes')
        self.excludepkgs = options.get('excludepkgs')
        self.proxy = options.get('proxy', default_proxy)

    def is_file(self):
        """True if repository URL looks like a file URI."""
        return self.url.startswith(self.FILE_SCHEME) or self.url.startswith('/')

    @property
    def path(self):
        """
        Absolute path to the local (aka. file) consumable repository. Raise
        RiftError if the ConsumableRepository is not local/file."
        """
        if not self.is_file():
            raise RiftError("Unable to return path of remote repository")
        if self.url.startswith(self.FILE_SCHEME):
            return self.url[len(self.FILE_SCHEME):]
        return self.url

    def generic_url(self, arch):
        """
        Return the URL with all occurrences of the given architecture replaced
        by generic $basearch placeholder.
        """
        return self.url.replace(arch, "$basearch")

    def exists(self):
        """
        Return true if path the local (aka. file) consumable repository actually
        exists on filesystem, or false otherwise. Raise RiftError if the
        ConsumableRepository is not local/file.
        """
        return os.path.exists(self.path)


class LocalRepository:
    """
    Manipulate local multi-architectures and source RPM packages repository with
    its structure and metadata using createrepo tool.
    """

    def __init__(self, path, config, name=None, options=None):
        self.path = os.path.realpath(path)
        self.config = config
        self.srpms_dir = os.path.join(self.path, 'SRPMS')
        if options is None:
            options = {}
        self.createrepo = config.get('createrepo', _DEFAULT_REPO_CMD)

        self.consumables = {
            arch: ConsumableRepository(
                f"{ConsumableRepository.FILE_SCHEME}"
                f"{os.path.realpath(self.path)}/{arch}",
                name=name or os.path.basename(self.path),
                priority=1,  # top priority for local repositories
                options=options,
                default_proxy=config.get('proxy')
            )
            for arch in self.config.get('arch')
        }

    def rpms_dir(self, arch):
        """
        Path to RPMS directory for the given architecture.
        """
        if arch not in self.config.get('arch'):
            raise RiftError(
                "Unable to get repository RPM directory for unsupported "
                f"architecture {arch}"
            )
        return os.path.join(self.path, arch)

    def create(self):
        """
        Create repository directory structure and metadata.
        """
        # Create main repository directory and the SRPM sub-directory.
        for path in (self.path, self.srpms_dir):
            if not os.path.exists(path):
                os.mkdir(path)
        # Create all architectures RPM sub-directories and their repodata.
        for arch in self.config.get('arch'):
            path = self.rpms_dir(arch)
            if not os.path.exists(path):
                os.mkdir(path)
        self.update()

    def update(self):
        """
        Update the repository metadata for SRPMS repository and all
        architectures RPMS repositories.
        """
        def run_update(path):
            with Popen(
                [self.createrepo, '-q', '--update', path],
                stdout=PIPE,
                stderr=STDOUT,
                universal_newlines=True,
            ) as popen:
                stdout = popen.communicate()[0]
                if popen.returncode != 0:
                    raise RiftError(stdout)

        run_update(self.srpms_dir)
        for arch in self.config.get('arch'):
            run_update(self.rpms_dir(arch))

    def search(self, name):
        """
        Return a list of RPM packages containing the source RPM packages found
        in the repository whose name match provided name and all the binary RPM
        packages reported as built by the spec files of these sources RPM
        packages and found in the repository.
        """
        src_rpms = []
        logging.debug(
            'Searching for package %s in repository %s', name, self.path
        )
        for srcrpm_p in glob.glob(os.path.join(self.srpms_dir, '*.src.rpm')):
            src_rpm = RPM(srcrpm_p)
            if src_rpm.name == name:
                logging.debug('Source package %s found: %s', name, srcrpm_p)
                src_rpms.append(src_rpm)

        bin_rpm_names = set()

        # Extract binary packages names from spec files of matching source RPMs
        for src_rpm in src_rpms:
            # Extract spec file in tmp directory
            tmp_dir = TempDir()
            tmp_dir.create()
            cmd = [
                'rpm',
                '-iv',
                '--define',
                f"_topdir {tmp_dir.path}",
                src_rpm.filepath
            ]
            try:
                run(cmd, check=True)
            except CalledProcessError as err:
                raise RiftError(err) from err
            # Parse spec file
            spec = Spec(os.path.join(tmp_dir.path,
                                     'SPECS',
                                     f"{src_rpm.name}.spec"))
            # Remove tmp directory
            tmp_dir.delete()
            # Merge list of bin package names into bin_rpm_names (and avoid
            # duplicates)
            bin_rpm_names |= set(spec.pkgnames)

        logging.debug(
            'Binary built by source package %s: %s', name, bin_rpm_names
        )

        # Search all binary RPMs whose name match packages names extracted from
        # specs.
        bin_pkgs = []

        for arch in self.config.get('arch'):
            for bin_rpm_p in glob.glob(
                    os.path.join(self.rpms_dir(arch), '*.rpm')
                ):
                bin_rpm = RPM(bin_rpm_p)
                if bin_rpm.name in bin_rpm_names:
                    logging.debug(
                        'Binary package %s found: %s', name, bin_rpm_p
                    )
                    bin_pkgs.append(bin_rpm)

        return src_rpms + bin_pkgs

    def add(self, rpm):
        """
        Copy RPM file pointed `rpm' into the repository, in the correct
        subdirectory based on RPM type and architecture.
        """
        def add_bin_arch(arch):
            logging.debug(
                "Adding %s to repo %s", rpm.filepath, self.rpms_dir(arch)
            )
            # rpms_dir already points to architecture directory
            shutil.copy(rpm.filepath, self.rpms_dir(arch))
        if rpm.is_source:
            logging.debug("Adding %s to repo %s", rpm.filepath, self.srpms_dir)
            shutil.copy(rpm.filepath, self.srpms_dir)
        else:
            # Add noarch binary package in all architectures repositories
            if rpm.arch == 'noarch':
                for arch in self.config.get('arch'):
                    add_bin_arch(arch)
            else:
                add_bin_arch(rpm.arch)

    def delete(self, rpm):
        """Delete provided RPM package from repository."""
        logging.info("Deleting %s from repository %s", rpm.filepath, self.path)
        os.remove(rpm.filepath)


class ProjectArchRepositories:
    """
    Manipulate repositories defined in a project for a particular architecture.
    """
    def __init__(self, config, arch):

        self.working = None
        self.arch = arch
        if config.get('working_repo'):
            self.working = LocalRepository(
                path=config.get('working_repo', arch=arch),
                config=config,
                name='working',
                options={"module_hotfixes": "true"},
            )
            self.working.create()
        self.supplementaries = []
        repos = config.get('repos', arch=arch)
        if repos:
            for name, data in repos.items():
                self.supplementaries.append(
                    ConsumableRepository(
                        data['url'],
                        name=name,
                        priority=data.get('priority'),
                        options=data,
                        default_proxy=config.get('proxy'),
                    )
                )

    @property
    def all(self):
        """
        The list of all repositories defined in the project for an architecture
        including the supplementary repositories and the working repository (if
        defined).
        """
        return (
            (
                [self.working.consumables[self.arch]]
                if self.working is not None
                else []
            ) + self.supplementaries
        )

    def can_publish(self):
        """
        Return True if it is possible to publish packages in project
        repositories, ie. if working repository is defined.
        """
        return self.working is not None
