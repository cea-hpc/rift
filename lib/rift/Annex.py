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
Class and function to detect binary files and push them into a file repository
called an annex.
"""

import datetime
import hashlib
import logging
import os
import string
import shutil
import tarfile
import time
import tempfile
import yaml

from rift.TempDir import TempDir
from rift.Config import OrderedLoader

# List of ASCII printable characters
_TEXTCHARS = bytearray([9, 10, 13] + list(range(32, 127)))

# Suffix of metadata filename
_INFOSUFFIX = '.info'


def get_digest_from_path(path):
    """Get file id from the givent path"""
    return open(path, encoding='utf-8').read()


def get_info_from_digest(digest):
    """Get file info id"""
    return digest + _INFOSUFFIX


def is_binary(filepath, blocksize=65536):
    """
    Look for non printable characters in the first blocksize bytes of filepath.

    Note it only looks for the first bytes. If binary data appeared farther in
    that file, it will be wrongly detected as a non-binary one.

    If there is a very small number of binary characters compared to the whole
    file, we still consider it as non-binary to avoid using Annex uselessly.
    """
    with open(filepath, 'rb') as srcfile:
        data = srcfile.read(blocksize)
        binchars = data.translate(None, _TEXTCHARS)
        if len(data) == 0:
            result = False
        # If there is very few binary characters among the file, consider it as
        # plain us-ascii.
        elif float(len(binchars)) / float(len(data)) < 0.01:
            result = False
        else:
            result = bool(binchars)
    return result

def hashfile(filepath, iosize=65536):
    """Compute a digest of filepath content."""
    hasher = hashlib.sha3_256()
    with open(filepath, 'rb') as srcfile:
        buf = srcfile.read(iosize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = srcfile.read(iosize)
    return hasher.hexdigest()


class Annex():
    """
    Repository of binary files.

    It simply adds and removes binary files addressed by their digest.
    When importing files, they are replaced by 'pointer files' containing
    only a digest or original file content.

    For now, files are stored in a flat namespace.
    """
    # Read and Write file modes
    RMODE = 0o644
    WMODE = 0o664

    def __init__(self, config, path=None):
        self.path = path or config.get('annex')

    @classmethod
    def is_pointer(cls, filepath):
        """
        Return true if content of file at filepath looks like a valid digest
        identifier.
        """
        meta = os.stat(filepath)

        # MD5 or SHA3 256
        if meta.st_size == 32 or meta.st_size == 64:
            with open(filepath, encoding='utf-8') as fh:
                identifier = fh.read(meta.st_size)
            return all(byte in string.hexdigits for byte in identifier)

        return False

    def get(self, identifier, destpath):
        """Get a file identified by identifier and copy it at destpath."""
        # Copy file from repository to destination path
        idpath = os.path.join(self.path, identifier)
        logging.debug('Extracting %s to %s', identifier, destpath)
        shutil.copyfile(idpath, destpath)

    def get_by_path(self, idpath, destpath):
        """Get a file identified by idpath content, and copy it at destpath."""
        self.get(get_digest_from_path(idpath), destpath)

    def delete(self, identifier):
        """Remove a file from annex, whose ID is `identifier'"""
        idpath = os.path.join(self.path, identifier)
        logging.debug('Deleting from annex: %s', idpath)
        infopath = get_info_from_digest(idpath)
        if os.path.exists(infopath):
            os.unlink(infopath)
        os.unlink(idpath)

    def import_dir(self, dirpath, force_temp=False):
        """
        Look for identifier files in `dirpath' directory and setup a usable
        directory.

        It returns a TempDir instance.
        If `dirpath' does not contain any identifier file, this temporary
        directory is not created.

        If it does, this temporary directory is created and text files from
        dirpath and identified ones are copied into it. It is caller
        responsability to delete it when it does not need it anymore.

        If `force_temp' is True, temporary is always created and source files
        copied in it even if there is no binary files.
        """
        tmpdir = TempDir('sources')
        if force_temp:
            tmpdir.create()

        filelist = []
        if os.path.exists(dirpath):
            filelist = os.listdir(dirpath)

        textfiles = []
        for filename in filelist:
            filepath = os.path.join(dirpath, filename)

            # Is a pointer to a binary file?
            if self.is_pointer(filepath):

                # We have our first binary file, we need a temp directory
                if tmpdir.path is None:
                    tmpdir.create()
                    for txtpath in textfiles:
                        shutil.copy(txtpath, tmpdir.path)

                # Copy the real binary content
                self.get_by_path(filepath, os.path.join(tmpdir.path, filename))

            else:
                if tmpdir.path is None:
                    textfiles.append(filepath)
                else:
                    shutil.copy(filepath, tmpdir.path)
        return tmpdir

    def _load_metadata(self, digest):
        """
        Return metadata for specified digest if the annexed file exists.
        """
        # Prepare metadata file
        metapath = os.path.join(self.path, get_info_from_digest(digest))
        metadata = {}
        # Read current metadata if present
        if os.path.exists(metapath):
            with open(metapath, encoding='utf-8') as fyaml:
                metadata = yaml.load(fyaml, Loader=OrderedLoader) or {}
                # Protect against empty file
        return metadata

    def _save_metadata(self, digest, metadata):
        """Write metadata file for specified digest and data."""
        metapath = os.path.join(self.path, get_info_from_digest(digest))
        with open(metapath, 'w', encoding='utf-8') as fyaml:
            yaml.dump(metadata, fyaml, default_flow_style=False)
        os.chmod(metapath, self.WMODE)

    def list(self):
        """
        Iterate over annex files, returning for them: filename, size and
        insertion time.
        """
        for filename in os.listdir(self.path):
            if filename.endswith(_INFOSUFFIX):
                continue

            info = self._load_metadata(filename)
            names = info.get('filenames', [])
            for annexed_file, details in names.items():
                insertion_time = details['date']

                # Handle different date formats (old method)
                if isinstance(insertion_time, str):
                    for fmt in ('%a %b %d %H:%M:%S %Y', '%a %d %b %Y %H:%M:%S %p %Z'):
                        try:
                            insertion_time = datetime.datetime.strptime(insertion_time, fmt).timestamp()
                            break
                        except ValueError:
                            continue
                 else:
                    raise ValueError(f"Invalid date format in metadata: {insertion_time}")

                # UNIX timestamp
                elif isinstance(insertion_time, int):
                    insertion_time = insertion_time
                else:
                    raise ValueError(f"Invalid date format in metadata: {type(insertion_time)})")

                # The file size must come from the filesystem
                meta = os.stat(os.path.join(self.path, filename))
                yield filename, meta.st_size, insertion_time, [annexed_file]

    def push(self, filepath):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """
        # Compute hash
        digest = hashfile(filepath)
        destpath = os.path.join(self.path, digest)
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
        self._save_metadata(digest, metadata)

        # Move binary file to annex
        logging.debug('Importing %s into annex (%s)', filepath, digest)
        shutil.copyfile(filepath, destpath)
        os.chmod(destpath, self.WMODE)

        # Verify permission are correct before copying
        os.chmod(filepath, self.RMODE)

        # Create fake pointer file
        with open(filepath, 'w', encoding='utf-8') as fakefile:
            fakefile.write(digest)


    def backup(self, packages, output_file=None):
        """
        Create a full backup of package list
        """

        filelist = []

        for package in packages:
            package.load()
            for source in package.sources:
                source_file = os.path.join(package.sourcesdir, source)
                if self.is_pointer(source_file):
                    filelist.append(source_file)

        # Manage progession
        total_packages = len(filelist)
        pkg_nb = 0

        if output_file is None:
            output_file = tempfile.NamedTemporaryFile(delete=False,
                                                      prefix='rift-annex-backup',
                                                      suffix='.tar.gz').name

        with tarfile.open(output_file, "w:gz") as tar:
        # translate sourcefiles path to annex path and add it to the output_file
            for _file in filelist:
                digest = get_digest_from_path(_file)
                annex_file = os.path.join(self.path, digest)
                annex_file_info = os.path.join(self.path, get_info_from_digest(digest))

                tar.add(annex_file, arcname=os.path.basename(annex_file))
                tar.add(annex_file_info, arcname=os.path.basename(annex_file_info))

                print(f"> {pkg_nb}/{total_packages} ({round((pkg_nb*100)/total_packages,2)})%\r"
                      , end="")
                pkg_nb += 1
        return output_file
