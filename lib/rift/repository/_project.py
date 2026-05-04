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

"""Module to manage repositories in projects."""

import logging

from rift import RiftError
from rift.TempDir import TempDir
from rift.repository.rpm import ArchRepositoriesRPM, StagingRepositoryRPM


class ProjectArchRepositories:
    """
    Intermediate class to manage repositories in a project for multiple packages
    formats.
    """

    FORMAT_CLASSES = {
        'rpm': ArchRepositoriesRPM
    }

    def __init__(self, config, arch):
        self.config = config
        self.arch = arch
        self.working_dir = config.get('working_repo', arch=arch)

    def can_publish(self):
        """
        Return True if it is possible to publish packages in project
        repositories, ie. if working repository is defined.
        """
        return self.working_dir is not None

    def delete_matching(self, package):
        """
        For all supported repositories formats, delete package matching provided
        name.
        """
        for _format in self.FORMAT_CLASSES:
            repos = self.for_format(_format)
            repos.delete_matching(package)

    def for_format(self, _format):
        """Get concrete repository object for the provided format."""
        if _format not in ProjectArchRepositories.FORMAT_CLASSES:
            raise RiftError(f"Unsupported repository format {_format}")
        return self.FORMAT_CLASSES[_format](
            self.config, self.working_dir, self.arch)


class StagingRepository:
    """Handle staging repositories for all supported packages formats."""
    FORMAT_CLASSES = {
        'rpm': StagingRepositoryRPM
    }

    def __init__(self, config):
        self.config = config
        logging.info('Creating temporary staging repository')
        self.stagedir = TempDir('stagedir')
        self.stagedir.create()
        self._repos = {}
        for _format, _class in self.FORMAT_CLASSES.items():
            self._repos[_format] = self.FORMAT_CLASSES[_format](
                self.config, self.stagedir.path
            )

    def for_format(self, _format):
        """Return the staged repository backend for the given format."""
        if _format not in self._repos:
            raise RiftError(f"Unsupported staging repository format {_format}")
        return self._repos[_format]

    def delete(self):
        """Remove the temporary staging repository directory."""
        self.stagedir.delete()
