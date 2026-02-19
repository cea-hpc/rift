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

import hashlib
import logging
import os
import shutil
import string
import sys
import tarfile
import tempfile
import time
from datetime import datetime as dt
from urllib.parse import urlparse

import boto3
import botocore
import requests
import yaml

from rift import RiftError
from rift.auth import Auth
from rift.Config import OrderedLoader
from rift.TempDir import TempDir
from rift.annex.Directory import *
from rift.annex.Server import *
from rift.annex.S3 import *

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


class Annex:
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

    def __init__(self, config, annex_path=None, staging_annex_path=None):
        # Annex path
        # should be either a filesystem path, or else http/https uri for an s3 endpoint
        self.annex_is_remote = None
        self.annex_type = None

        self.annex_path = annex_path or config.get('annex')

        url = urlparse(self.annex_path, allow_fragments=False)
        if url.scheme in ("http", "https"):
            self.annex_is_remote = True
            self.annex_type = url.scheme
        elif url.scheme in ("", "file"):
            self.annex_is_remote = False
            self.annex_type = "file"
            self.annex_path = url.path
        else:
            logging.error("invalid value for config option: 'annex'")
            logging.error("the annex should be either a file:// path or http(s):// url")
            sys.exit(1)

        self.annex_is_s3 = config.get('annex_is_s3')

        self.dirannex = (DirectoryAnnex(config, annex_path, staging_annex_path) if
                        not self.annex_is_s3 else None)
        self.servannex = (ServerAnnex(config, annex_path, staging_annex_path) if
                        not self.annex_is_s3 and self.annex_is_remote else None)
        self.s3annex = (S3Annex(config, annex_path, staging_annex_path) if
                        self.annex_is_s3 else None)

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

    def make_restore_cache(self):
        """
        Creates the restore_cache directory
        """
        if not os.path.isdir(self.restore_cache):
            if os.path.exists(self.restore_cache):
                msg = f"{self.restore_cache} should be a directory"
                raise RiftError(msg)
            os.makedirs(self.restore_cache)

    def get_cached_path(self, path):
        """
        Returns the location where 'path' would be in the restore_cache
        """
        return os.path.join(self.restore_cache, path)

    def get(self, identifier, destpath):
        """Get a file identified by identifier and copy it at destpath."""
        if self.dirannex:
            self.dirannex.get(identifier, destpath)
        elif self.servannex:
            self.servannex.get(identifier, destpath)
        else:
            self.s3annex.get(identifier, destpath)

        return

        # 1. See if we can restore from cache
        if self.restore_cache:
            self.make_restore_cache()
            cached_path = self.get_cached_path(identifier)
            if os.path.isfile(cached_path):
                logging.debug('Extract %s to %s using restore cache', identifier, destpath)
                shutil.copyfile(cached_path, destpath)
                return

        # 2. See if object is in the annex
        if self.annex_is_remote:
            self.servannex.get(identifier, destpath)

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

                            if self.restore_cache:
                                cached_path = self.get_cached_path(identifier)
                                shutil.move(tmp_file, cached_path)
                                logging.debug('Extracting %s to %s', identifier, destpath)
                                cached_path = self.get_cached_path(identifier)
                                shutil.copyfile(cached_path, destpath)
                            else:
                                logging.debug('Extracting %s to %s', identifier, destpath)
                                shutil.move(tmp_file, destpath)

                            return
                    elif res.status_code != 404:
                        res.raise_for_status()
                except requests.exceptions.RequestException as e:
                    raise RiftError(f"failed to fetch file from annex: {idpath}: {e}") from e

            logging.info("did not find object in annex, will search staging_annex next")

        # 3. See if object is in the staging_annex location
        if self.push_over_s3:
            # Checking annex push, expecting annex push path to be an s3-providing http(s) url
            key = os.path.join(self.push_s3_prefix, identifier)

            s3 = self.get_push_s3_client()
            # s3.meta.events.register('choose-signer.s3.*', botocore.handlers.disable_signing)

            success = False
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_file:
                try:
                    s3.download_fileobj(self.push_s3_bucket, key, tmp_file)
                    success = True
                except botocore.exceptions.ClientError as error:
                    if error.response['Error']['Code'] == '404':
                        logging.info("object not found: %s", key)
                    logging.error(error)
                except Exception as error:
                    raise error

            if not success:
                sys.exit(1)

            logging.debug('Extracting %s to %s', identifier, destpath)
            if self.restore_cache:
                cached_path = self.get_cached_path(identifier)
                shutil.move(tmp_file.name, cached_path)
                shutil.copyfile(cached_path, destpath)
            else:
                shutil.move(tmp_file.name, destpath)

            return

    def get_by_path(self, idpath, destpath):
        """Get a file identified by idpath content, and copy it at destpath."""
        self.get(get_digest_from_path(idpath), destpath)

    def delete(self, identifier):
        """Remove a file from annex, whose ID is `identifier'"""
        return self.dirannex.delete(identifier)

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

    def list(self):
        """
        Iterate over annex files, returning for them: filename, size and
        insertion time.
        """
        if self.annex_is_s3:
            yield from self.s3annex.list()
        elif self.annex_is_remote:
            yield from self.servannex.list()
        else:
            yield from self.dirannex.list()

    def push(self, filepath):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """
        if self.annex_is_s3:
            self.s3annex.push(filepath)
        elif self.annex_is_remote:
            self.servannex.push(filepath)
        else:
            self.dirannex.push(filepath)

        return

        # Compute hash
        digest = hashfile(filepath)

        self._push_to_s3(filepath, digest)

        # Verify permission are correct before updating original file
        os.chmod(filepath, self.RMODE)

        # Create fake pointer file
        with open(filepath, 'w', encoding='utf-8') as fakefile:
            fakefile.write(digest)

    def backup(self, packages, output_file=None):
        """
        Create a full backup of package list
        """
        if self.annex_is_remote:
            return self.servannex.backup(packages, output_file)
        else:
            return self.dirannex.backup(packages, output_file)


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

        with tempfile.TemporaryDirectory() as tmp_dir:
            with tarfile.open(output_file, "w:gz") as tar:
                for _file in filelist:
                    digest = get_digest_from_path(_file)
                    annex_file = os.path.join(self.annex_path, digest)
                    annex_file_info = os.path.join(self.annex_path, get_info_from_digest(digest))

                    if self.annex_is_remote:
                        for f in (annex_file, annex_file_info):
                            basename = os.path.basename(f)
                            tmp = os.path.join(tmp_dir.name, basename)

                            try:
                                res = requests.get(f, stream=True, timeout=15)
                                if res:
                                    with open(tmp, 'wb') as f:
                                        for chunk in res.iter_content(chunk_size=8192):
                                            f.write(chunk)
                                        tar.add(tmp, arcname=basename)
                                elif res.status_code != 404:
                                    res.raise_for_status()
                            except requests.exceptions.RequestException as e:
                                raise RiftError(f"failed to fetch file from annex: {f}: {e}") from e
                    else:
                        tar.add(annex_file, arcname=os.path.basename(annex_file))
                        tar.add(annex_file_info, arcname=os.path.basename(annex_file_info))

                    print(f"> {pkg_nb}/{total_packages} ({round((pkg_nb*100)/total_packages,2)})%\r"
                        , end="")
                    pkg_nb += 1

        return output_file
