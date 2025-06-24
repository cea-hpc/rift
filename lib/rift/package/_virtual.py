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
"""Manage virtual packages."""

from rift.package._base import Package
from rift import RiftError


class PackageVirtual(Package):
    """
    Handle Rift virtual project package. Virtual packages are packages do not
    exist in Rift project packages directory, for which there is no way to
    determine actual format.

    This concept is useful to handle removed package for instance.
    """

    def __init__(self, name, config, staff, modules):
        super().__init__(name, config, staff, modules, '_virtual', None)

    def add_changelog_entry(self, maintainer, comment, bump):
        """Must not be called on virtual package."""
        raise RiftError("Unable to add changelog entry on virtual package")

    def analyze(self, review, configdir):
        """Must not be called on virtual package."""
        raise RiftError("Unable to analyze a virtual package")

    def _serialize_specific_metadata(self):
        """
        Dummy implementation because virtual packages have not any specific metadata.
        """
        return {}

    def _deserialize_specific_metadata(self, data):
        """
        Dummy implementation because virtual packages have not any specific metadata.
        """
        pass

    def subpackages(self):
        """Must not be called on virtual package."""
        raise RiftError("Unable to get subpackages of a virtual package")

    def build_requires(self):
        """Must not be called on virtual package."""
        raise RiftError("Unable to get build requirements of a virtual package")

    def for_arch(self, arch):
        """Must not be called on virtual package."""
        raise RiftError(
            "Unable to get actionable architecture package of a virtual package"
        )
