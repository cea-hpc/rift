#
# Copyright (C) 2026 CEA
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
"""Module to instanciate container and manage container images."""

import os
import getpass
import logging

from rift import RiftError
from rift.run import run_command

class ContainerRuntime:
    """Handle containers and images."""
    ARCHS_MAP = {
        'x86_64': 'amd64',
        'aarch64': 'arm64'
    }

    def __init__(self, config):
        self.config = config
        self.rootdir = f"/tmp/rift-containers-{getpass.getuser()}"

    def tag(self, actionable_pkg):
        """Return container tag for the provided actionable package."""
        return (
            f"{actionable_pkg.name}:{actionable_pkg.package.version}-"
            f"{actionable_pkg.package.release}-{actionable_pkg.arch}"
        )

    def build(self, actionable_pkg, sources_topdir):
        """Execute command to build OCI package container image."""
        cmd = [
            self.config.get('containers').get('command'),
            '--root', self.rootdir, 'build',
            '--arch', self.ARCHS_MAP[actionable_pkg.arch],
            '--annotation',
            f"org.opencontainers.image.version={actionable_pkg.package.version}"
            f"-{actionable_pkg.package.release}",
            '--annotation', f"org.opencontainers.image.title={actionable_pkg.name}",
            '--annotation', "org.opencontainers.image.vendir=rift",
            '--tag', self.tag(actionable_pkg),
            sources_topdir ]
        proc = run_command(cmd)
        if proc.returncode:
            raise RiftError(f"Container image build error: exit code {proc.returncode}")

    def run_test(self, actionable_pkg, test):
        """
        Execute command to run the provided actionable package test in OCI
        container.
        """
        cmd = [
            self.config.get('containers').get('command'),
            '--root', self.rootdir,
            'run', '--rm', '-i',
            '--mount',
            f"type=bind,src={test.command},"
            f"dst=/run/{os.path.basename(test.command)},ro=true",
            '--arch', self.ARCHS_MAP[actionable_pkg.arch],
            f"localhost/{self.tag(actionable_pkg)}",
            f"/run/{os.path.basename(test.command)}"
        ]
        return run_command(cmd, capture_output=True)

    def archive(self, actionable_pkg, path):
        """
        Execute command to export the provided OCI actionable package container
        image as OCI archive in the provided path.
        """
        cmd = [
            self.config.get('containers').get('command'),
            '--root', self.rootdir,
            'push', self.tag(actionable_pkg),
            f"oci-archive:{path}:{self.tag(actionable_pkg)}"
        ]
        return run_command(cmd)


class ContainerFile:
    """Handle Containerfile with checks and review analysis."""
    def __init__(self, config, path):
        self.config = config
        self.path = path
        if not os.path.exists(self.path):
            raise RiftError(f"Unable to find Containerfile {self.path}")

    @property
    def linter(self):
        """Return linter path or executable name in configuration."""
        return self.config.get('containers').get('linter')

    def _check(self, configdir):
        cmd = [self.linter, self.path]

        if configdir:
            pkg_config = os.path.join(configdir, 'hadolint.yaml')
            if os.path.exists(pkg_config):
                cmd[1:1] = ['--config', pkg_config]

        logging.debug('Running OCI linter command: %s', ' '.join(cmd))
        return run_command(cmd, capture_output=True, merge_out_err=True)

    def check(self, pkg=None):
        """
        Check Containerfile content using container checker tool.
        """
        try:
            result = self._check(pkg.dir if pkg else None)
        except FileNotFoundError:
            logging.error(
                "Unable to find Containerfile linter executable '%s'", self.linter
            )
        else:
            if result.returncode:
                raise RiftError(f"Containerfile check error: {result.out}")

    def analyze(self, review, configdir):
        """Analyze Containerfile"""
        try:
            result = self._check(configdir)
        except FileNotFoundError as err:
            raise RiftError(
                f"Unable to find Containerfile linter executable '{self.linter}'"
            ) from err

        if result.returncode not in (0, 1):
            raise RiftError(f"hadolint returned {result.returncode}: {result.out}")

        for line in result.out.splitlines():
            if line.startswith(self.path + ':'):
                line = line[len(self.path + ':'):]
                try:
                    (linenbr, code, _, txt) = line.split(' ', 3)
                    review.add_comment(self.path, linenbr,
                                       code.strip(), txt.strip())
                except (ValueError, KeyError):
                    pass

        if result.returncode:
            review.invalidate()
