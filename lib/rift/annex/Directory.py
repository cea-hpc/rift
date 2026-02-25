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
Implementation of the Annex class for a directory annex
"""
import logging
import os
import shutil
import tarfile
import tempfile
import time

from datetime import datetime as dt
from urllib.parse import urlparse

import yaml

from rift.annex.GenericAnnex import GenericAnnex
from rift.annex.Utils import ( get_digest_from_path, get_info_from_digest,
                               _INFOSUFFIX )
from rift.Config import OrderedLoader


class DirectoryAnnex(GenericAnnex):
    """
    Repository of binary files.

    It simply adds and removes binary files addressed by their digest.
    When importing files, they are replaced by 'pointer files' containing
    only a digest or original file content.

    For now, files are stored in a flat namespace.
    """
    # Read and Write file modes
    WMODE = 0o664

    def __init__(self, _, annex_path, staging_annex_path):
        url = urlparse(annex_path, allow_fragments=False)
        self.annex_path = url.path

        if staging_annex_path is not None:
            url = urlparse(staging_annex_path, allow_fragments=False)
            self.staging_annex_path = url.path
        else:
            self.staging_annex_path = self.annex_path

    def get(self, identifier, destpath):
        """Get a file identified by identifier and copy it at destpath."""
        logging.debug('Extracting %s to %s', identifier, destpath)
        idpath = os.path.join(self.staging_annex_path, identifier)
        shutil.copyfile(idpath, destpath)

        return True

    def delete(self, identifier):
        """Remove a file from annex, whose ID is `identifier'"""
        idpath = os.path.join(self.annex_path, identifier)
        logging.debug('Deleting from annex: %s', idpath)
        infopath = get_info_from_digest(idpath)
        if os.path.exists(infopath):
            os.unlink(infopath)
        os.unlink(idpath)

        return True

    def _load_metadata(self, digest):
        """
        Return metadata for specified digest if the annexed file exists.
        """
        # Prepare metadata file
        metapath = os.path.join(self.annex_path, get_info_from_digest(digest))
        metadata = {}

        # Read current metadata if present
        if os.path.exists(metapath):
            with open(metapath, encoding="utf-8") as fyaml:
                metadata = yaml.load(fyaml, Loader=OrderedLoader) or {}
                # Protect against empty file

        return metadata

    def list(self):
        """
        Iterate over local annex files, returning for them: filename, size and
        insertion time.
        """
        for filename in os.listdir(self.annex_path):
            if filename.endswith(_INFOSUFFIX):
                continue

            info = self._load_metadata(filename)
            names = info.get('filenames', [])
            for annexed_file, details in names.items():
                insertion_time = details['date']

                # Handle different date formats (old method)
                if not isinstance(insertion_time, (int, float, str)):
                    raise ValueError(f"Invalid date format in metadata: "
                                     f"{insertion_time} "
                                     f"(type {type(insertion_time)})")

                if isinstance(insertion_time, str):
                    fmt = '%a %b %d %H:%M:%S %Y'
                    try:
                        insertion_time = dt.strptime(insertion_time, fmt).timestamp()
                    except ValueError:
                        fmt = '%a %d %b %Y %H:%M:%S %p %Z'
                        try:
                            insertion_time = dt.strptime(insertion_time, fmt).timestamp()
                        except ValueError as exc:
                            raise ValueError(f"Unknown date format in "
                                             f"metadata: {insertion_time}") from exc

                elif isinstance(insertion_time, float):
                    insertion_time = int(insertion_time)
                # else insertion_time is already a timestamp, nothing to convert

                # The file size must come from the filesystem
                meta = os.stat(os.path.join(self.annex_path, filename))
                yield filename, meta.st_size, insertion_time, [annexed_file]

    def push(self, filepath, digest):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """
        destpath = os.path.join(self.staging_annex_path, digest)
        filename = os.path.basename(filepath)

        # Prepare metadata file
        metadata = self._load_metadata(digest)

        # Is file already present?
        originfo = os.stat(filepath)
        destinfo = None
        if os.path.exists(destpath):
            destinfo = os.stat(destpath)
            if destinfo and destinfo.st_size == originfo.st_size and \
            filename in metadata.get('filenames', {}):
                logging.debug('%s is already into annex, skipping it', filename)
                return

        # Update them and write them back
        fileset = metadata.setdefault('filenames', {})
        fileset.setdefault(filename, {})
        fileset[filename]['date'] = time.time()  # Unix timestamp

        metapath = os.path.join(self.staging_annex_path,
                                get_info_from_digest(digest))
        with open(metapath, 'w', encoding="utf-8") as fyaml:
            yaml.dump(metadata, fyaml, default_flow_style=False)
        os.chmod(metapath, self.WMODE)

        # Move binary file to annex
        logging.debug('Importing %s into annex (%s)', filepath, digest)
        shutil.copyfile(filepath, destpath)
        os.chmod(destpath, self.WMODE)

    def backup(self, filelist, output_file):
        """
        Create a full backup of package list
        """
        # Manage progession
        total_packages = len(filelist)
        pkg_nb = 0

        with tarfile.open(output_file, "w:gz") as tar:
            for _file in filelist:
                digest = get_digest_from_path(_file)
                annex_file = os.path.join(self.annex_path, digest)
                annex_file_info = os.path.join(self.annex_path, get_info_from_digest(digest))
                tar.add(annex_file, arcname=os.path.basename(annex_file))
                tar.add(annex_file_info, arcname=os.path.basename(annex_file_info))

                percentage = round((pkg_nb * 100) / total_packages, 2)
                print(f"> {pkg_nb}/{total_packages} ({percentage})%\r",
                      end="")
                pkg_nb += 1

        return output_file
