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
import errno

import boto3
import botocore
import requests
import yaml

from rift import RiftError
from rift.auth import Auth
from rift.Config import OrderedLoader
from rift.TempDir import TempDir
from rift.annex.GenericAnnex import *

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
        self.restore_cache = config.get('annex_restore_cache')
        if self.restore_cache is not None:
            self.restore_cache = os.path.expanduser(self.restore_cache)

        # Annex path
        # should be either a filesystem path, or else http/https uri for an s3 endpoint
        self.read_s3_endpoint = None
        self.read_s3_bucket = None
        self.read_s3_prefix = None
        self.read_s3_client = None
        self.annex_is_remote = None
        self.annex_type = None

        self.annex_path = annex_path or config.get('annex')

        url = urlparse(self.annex_path, allow_fragments=False)
        if url.scheme in ("http", "https"):
            self.annex_is_remote = True
            self.annex_type = url.scheme
        else:
            logging.error("invalid value for config option: 'annex'")
            logging.error("the annex should be either a file:// path or http(s):// url")
            sys.exit(1)

        self.annex_is_s3 = config.get('annex_is_s3')
        if self.annex_is_s3:
            if not self.annex_is_remote:
                msg = "invalid pairing of configuration settings for: annex, annex_is_s3\n"
                msg += "annex_is_s3 is True but the annex url is not an http(s) url,"
                msg += " as required in this case"
                raise RiftError(msg)

            parts = url.path.lstrip("/").split("/")
            self.read_s3_endpoint = f"{url.scheme}://{url.netloc}"
            self.read_s3_bucket = parts[0]
            self.read_s3_prefix = "/".join(parts[1:])

        # Staging annex path
        # should be an http(s) url containing s3 endpoint, bucket, and prefix
        self.staging_annex_path = staging_annex_path or config.get('staging_annex')
        self.push_over_s3 = False
        self.push_s3_endpoint = None
        self.push_s3_bucket = None
        self.push_s3_prefix = None
        self.push_s3_client = None
        self.push_s3_auth = None

        if self.staging_annex_path is not None:
            url = urlparse(self.staging_annex_path, allow_fragments=False)
            parts = url.path.lstrip("/").split("/")
            self.push_over_s3 = True
            self.push_s3_endpoint = f"{url.scheme}://{url.netloc}"
            self.push_s3_bucket = parts[0]
            self.push_s3_prefix = "/".join(parts[1:])
            self.push_s3_auth = Auth(config)
        else:
            # allow staging_annex_path to default to annex when annex is s3:// or file://
            self.staging_annex_path = self.annex_path
            self.push_over_s3 = True
            self.push_s3_endpoint = self.read_s3_endpoint
            self.push_s3_bucket = self.read_s3_bucket
            self.push_s3_prefix = self.read_s3_prefix
            self.push_s3_auth = Auth(config)

    def get_read_s3_client(self):
        """
        Returns an boto3 s3 client for the read_s3_endpoint
        If one already exists, return that; otherwise create one
        """
        if self.read_s3_client is None:
            self.read_s3_client = boto3.client('s3', endpoint_url = self.read_s3_endpoint)

        return self.read_s3_client

    def get_push_s3_client(self):
        """
        Returns an boto3 s3 client for the push_s3_endpoint
        If one already exists, return that; otherwise create one
        """
        if self.push_s3_client is not None:
            return self.push_s3_client

        if not self.push_s3_auth.authenticate():
            raise RiftError("authentication failed; cannot get push_s3_client")

        self.push_s3_client = boto3.client('s3',
            aws_access_key_id = self.push_s3_auth.config["access_key_id"],
            aws_secret_access_key = self.push_s3_auth.config["secret_access_key"],
            aws_session_token = self.push_s3_auth.config["session_token"],
            endpoint_url = self.push_s3_endpoint)

        return self.push_s3_client

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

    def get_cached_path(self, path):
        """
        Returns the location where 'path' would be in the restore_cache
        """
        return os.path.join(self.restore_cache, path)

    def get(self, identifier, destpath):
        """Get a file identified by identifier and copy it at destpath."""
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
        sys.exit(errno.ENOTSUP)

    def list_s3(self):
        """
        Iterate over s3 files, returning for them: filename, size and
        insertion time.
        """
        if not self.annex_is_s3:
            # non-S3, remote annex
            print("list functionality is not implemented for public annex over non-S3, http")
            return

        # s3 list
        # if http(s) uri is s3-compliant, then listing is easy
        s3 = self.get_read_s3_client()

        # disable signing if accessing anonymously
        s3.meta.events.register('choose-signer.s3.*', botocore.handlers.disable_signing)

        response = s3.list_objects_v2(
            Bucket=self.read_s3_bucket,
            Prefix=self.read_s3_prefix
        )
        if 'Contents' not in response:
            logging.info("No files found in %s", self.read_s3_prefix)
            return

        for obj in response['Contents']:
            key = obj['Key']
            filename = os.path.basename(key)

            if filename.endswith(_INFOSUFFIX):
                continue

            meta_obj_name = get_info_from_digest(key)
            meta_obj = s3.get_object(Bucket=self.read_s3_bucket, Key=meta_obj_name)
            info = yaml.safe_load(meta_obj['Body']) or {}
            names = info.get('filenames', [])
            for annexed_file in names.values():
                insertion_time = annexed_file['date']
                insertion_time = dt.strptime(insertion_time, "%c").timestamp()

            size = obj['Size']

            yield filename, size, insertion_time, names

    def list(self):
        """
        Iterate over annex files, returning for them: filename, size and
        insertion time.
        """
        if self.annex_is_s3:
            yield from self.list_s3()
        elif self.annex_is_remote:
            yield from self.servannex.list()
        else:
            yield from self.dirannex.list()

    def _push_to_s3(self, filepath, digest):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.

        Push is done to the S3 annex
        """
        s3 = self.get_push_s3_client()
        if s3 is None:
            logging.error("could not get s3 client: get_push_s3_client failed")
            sys.exit(1)

        destpath = os.path.join(self.push_s3_prefix, digest)
        filename = os.path.basename(filepath)
        key = destpath

        # Prepare metadata file
        meta_obj_name = get_info_from_digest(key)
        metadata = {}
        try:
            meta_obj = s3.get_object(Bucket=self.push_s3_bucket, Key=meta_obj_name)
            metadata = yaml.safe_load(meta_obj['Body']) or {}
        except s3.exceptions.NoSuchKey:
            logging.info("metadata not found in s3: %s", meta_obj_name)
        except yaml.YAMLError:
            logging.info("retrieved metadata could not be parsed as yaml: %s", meta_obj_name)

        originfo = os.stat(filepath)
        destinfo = None
        try:
            destinfo = s3.get_object(Bucket=self.push_s3_bucket, Key=key)
        except s3.exceptions.NoSuchKey:
            logging.info("key not found in s3: %s", key)
        if destinfo and destinfo["ContentLength"] == originfo.st_size and \
          filename in metadata.get('filenames', {}):
            logging.debug("%s is already into annex, skipping it", filename)
        else:
            # Update them and write them back
            fileset = metadata.setdefault('filenames', {})
            fileset.setdefault(filename, {})
            fileset[filename]['date'] = time.strftime("%c")

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.info') as f:
                yaml.dump(metadata, f, default_flow_style=False)
                s3.upload_file(f.name, self.push_s3_bucket, meta_obj_name)
            logging.debug("Importing %s into annex (%s)", filepath, digest)

            s3.upload_file(filepath, self.push_s3_bucket, key)

    def push(self, filepath):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """
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
        sys.exit(errno.ENOTSUP)
