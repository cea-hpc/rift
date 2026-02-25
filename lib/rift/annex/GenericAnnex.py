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

from abc import ABC, abstractmethod
from urllib.parse import urlparse

class GenericAnnex(ABC):
    """
    Generic implemention of an annex and the methods it should define
    """
    def __init__(self, annex_path, staging_annex_path):
        url = urlparse(annex_path, allow_fragments=False)
        self.annex_path = url.path

        if staging_annex_path is not None:
            url = urlparse(staging_annex_path, allow_fragments=False)
            self.staging_annex_path = url.path
        else:
            self.staging_annex_path = self.annex_path

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
    def backup(self, filelist, output_file):
        """
        Create a full backup of the given filelist to output_file
        """
