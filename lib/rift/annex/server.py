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
Class and function to detect binary files and push them into a file repository
called an annex.
"""

import errno
import logging
import os
import shutil
import sys
import tarfile
import tempfile

import requests

from rift import RiftError
from rift.annex.generic_annex import GenericAnnex
from rift.annex.utils import get_digest_from_path, get_info_from_digest


class ServerAnnex(GenericAnnex):
    """
    Repository of binary files.

    It simply adds and removes binary files addressed by their digest.
    When importing files, they are replaced by 'pointer files' containing
    only a digest or original file content.

    For now, files are stored in a flat namespace.
    """
    def __init__(self, _, annex_path):
        self.annex_path = annex_path

    def get_cached_path(self, path):
        """
        Returns the location where 'path' would be in the restore_cache
        """
        return os.path.join(self.restore_cache, path)

    def get(self, identifier, destpath):
        """Get a file identified by identifier and copy it at destpath."""
        # Checking annex, expecting annex path to be an http(s) url
        idpath = os.path.join(self.annex_path, identifier)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_file = os.path.join(tmp_dir, identifier)
            try:
                res = requests.get(idpath, stream=True, timeout=15)

                if res:
                    with open(tmp_file, 'wb') as f:
                        # If the annex object to get is a gzip, reading it
                        # with the standard 'iter_content()' method will
                        # mistakenly gunzip it, which will cause errors
                        # later in a build/validate. So instead, we read
                        # the raw content, and let future gunzip do its job
                        chunk = res.raw.read(8192)
                        while chunk:
                            f.write(chunk)
                            chunk = res.raw.read(8192)

                        logging.debug('Extracting %s to %s',
                                      identifier, destpath)
                        shutil.move(tmp_file, destpath)

                        return True
                elif res.status_code != 404:
                    res.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise RiftError(f"failed to fetch file from annex: {idpath}: {e}") from e

        return False

    def delete(self, identifier):
        """Remove a file from annex, whose ID is `identifier'"""
        logging.error("Delete not implemented for server annex")
        sys.exit(errno.ENOTSUP)

    def list(self):
        """
        Iterate over annex files, returning for them: filename, size and
        insertion time.
        """
        logging.error("List not implemented for server annex")
        sys.exit(errno.ENOTSUP)

    def push(self, filepath, digest):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """
        logging.info("Push not implemented for server annex")
        sys.exit(errno.ENOTSUP)

    def backup(self, filelist, output_file):
        """
        Create a full backup of package list
        """
        # Manage progession
        total_packages = len(filelist)
        pkg_nb = 0

        with tempfile.TemporaryDirectory() as tmp_dir:
            with tarfile.open(output_file, "w:gz") as tar:
                for _file in filelist:
                    digest = get_digest_from_path(_file)
                    annex_file = os.path.join(self.annex_path, digest)
                    annex_file_info = os.path.join(self.annex_path,
                                                   get_info_from_digest(digest))

                    for f in (annex_file, annex_file_info):
                        basename = os.path.basename(f)
                        tmp = os.path.join(tmp_dir.name, basename)

                        try:
                            res = requests.get(f, stream=True, timeout=15)
                            if res.status_code != 404:
                                res.raise_for_status()

                            with open(tmp, 'wb') as f:
                                for chunk in res.iter_content(chunk_size=8192):
                                    f.write(chunk)
                                tar.add(tmp, arcname=basename)
                        except requests.exceptions.RequestException as e:
                            raise RiftError(f"failed to fetch file from annex: {f}: {e}") from e

                    percentage = round((pkg_nb * 100) / total_packages, 2)
                    print(f"> {pkg_nb}/{total_packages} ({percentage})%\r",
                          end="")
                    pkg_nb += 1

        return output_file
