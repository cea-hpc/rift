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

"""
Generic class and functions to detect binary files and push them into a
repository called an annex.
"""

import string

from abc import ABC, abstractmethod

class GenericAnnex(ABC):
    """
    XXX: name or description not final
    """
    @classmethod
    def is_pointer(cls, filepath):
        """
        Return true if content of file at filepath looks like a valid digest
        identifier.
        """
        try:
            with open(filepath, encoding='utf-8') as fh:
                identifier = fh.read()
                # Remove possible trailing whitespace, newline and carriage return
                # characters.
                identifier = identifier.rstrip()

        except UnicodeDecodeError:
            # Binary fileis cannot be decoded with UTF-8
            return False

        # Check size corresponds to MD5 (32) or SHA3 256 (64).
        if len(identifier) in (32, 64):
            return all(byte in string.hexdigits for byte in identifier)

        # If the identifier is not a valid Rift Annex pointer
        return False

    @abstractmethod
    def get(self, identifier, destpath):
        """
        Get the entry from annex whose IS is `identifier` and copy it to
        destpath.
        """

    @abstractmethod
    def delete(self, identifier):
        """Remove an entry from annex whose ID is `identifier'"""

    @abstractmethod
    def list(self):
        """
        Iterate over annex entries, returning for them: name, size and insertion
        time.
        """

    @abstractmethod
    def push(self, filepath, digest):
        """
        Copy file at `filepath' into this annex and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """

    @abstractmethod
    def backup(self, packages, output_file=None):
        """
        Create a full backup of package list
        """
