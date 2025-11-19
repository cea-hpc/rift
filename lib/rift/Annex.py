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
        elif url.scheme in ("", "file"):
            self.annex_is_remote = False
            self.annex_type = "file"
            self.annex_path = url.path
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
            if url.scheme in ("http", "https"):
                self.push_over_s3 = True
                self.push_s3_endpoint = f"{url.scheme}://{url.netloc}"
                self.push_s3_bucket = parts[0]
                self.push_s3_prefix = "/".join(parts[1:])
                self.push_s3_auth = Auth(config)
            elif url.scheme in ("file", ""):
                self.staging_annex_path = url.path
        else:
            # allow staging_annex_path to default to annex when annex is s3:// or file://
            if self.annex_is_s3:
                self.staging_annex_path = self.annex_path
                self.push_over_s3 = True
                self.push_s3_endpoint = self.read_s3_endpoint
                self.push_s3_bucket = self.read_s3_bucket
                self.push_s3_prefix = self.read_s3_prefix
                self.push_s3_auth = Auth(config)
            elif self.annex_type == "file":
                self.staging_annex_path = self.annex_path
                self.push_over_s3 = False

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
        meta = os.stat(filepath)

        # MD5 or SHA3 256
        if meta.st_size in (32, 64):
            with open(filepath, encoding='utf-8') as fh:
                identifier = fh.read(meta.st_size)
            return all(byte in string.hexdigits for byte in identifier)

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
            # Checking annex, expecting annex path to be an http(s) url

            idpath = os.path.join(self.annex_path, identifier)
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_file = os.path.join(tmp_dir, identifier)
                try:
                    res = requests.get(idpath, stream=True, timeout=15)

                    if res:
                        with open(tmp_file, 'wb') as f:
                            for chunk in res.iter_content(chunk_size=8192):
                                f.write(chunk)

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
        else:
            # Checking annex, expecting annex path to be a filesystem location
            logging.debug('Extracting %s to %s', identifier, destpath)
            idpath = os.path.join(self.annex_path, identifier)
            if os.path.exists(idpath):
                shutil.copyfile(idpath, destpath)
                return

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

        # Checking staging_annex location, expecting staging_annex path to be a filesystem location
        logging.debug('Extracting %s to %s', identifier, destpath)
        idpath = os.path.join(self.staging_annex_path, identifier)
        shutil.copyfile(idpath, destpath)

    def get_by_path(self, idpath, destpath):
        """Get a file identified by idpath content, and copy it at destpath."""
        self.get(get_digest_from_path(idpath), destpath)

    def delete(self, identifier):
        """Remove a file from annex, whose ID is `identifier'"""

        if self.annex_is_remote:
            logging.info("delete functionality is not implemented for remote annex")
            return False

        # local annex (file://)
        idpath = os.path.join(self.annex_path, identifier)
        logging.debug('Deleting from annex: %s', idpath)
        infopath = get_info_from_digest(idpath)
        if os.path.exists(infopath):
            os.unlink(infopath)
        os.unlink(idpath)

        return True

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
        metapath = os.path.join(self.annex_path, get_info_from_digest(digest))
        metadata = {}

        if not self.annex_is_s3:
            # Read current metadata if present
            if os.path.exists(metapath):
                with open(metapath, encoding="utf-8") as fyaml:
                    metadata = yaml.load(fyaml, Loader=OrderedLoader) or {}
                    # Protect against empty file
        return metadata

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

    def list_local_annex(self):
        """
        Iterate over local annex files, returning for them: filename, size and
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
                if not isinstance(insertion_time, str):
                    raise ValueError(f"Invalid date format in metadata: "
                                     f"{insertion_time} "
                                     f"(type {type(insertion_time)})")

                fmt = '%a %b %d %H:%M:%S %Y'
                try:
                    insertion_time = datetime.datetime.strptime(
                        insertion_time, fmt
                    ).timestamp()
                except ValueError:
                    fmt = '%a %d %b %Y %H:%M:%S %p %Z'
                    try:
                        insertion_time = datetime.datetime.strptime(
                            insertion_time, fmt
                        ).timestamp()
                    except ValueError:
                        raise ValueError(f"Unknown date format in "
                                         f"metadata: {insertion_time}")

                # The file size must come from the filesystem
                meta = os.stat(os.path.join(self.path, filename))
                yield filename, meta.st_size, insertion_time, [annexed_file]

    def list(self):
        """
        Iterate over annex files, returning for them: filename, size and
        insertion time.
        """
        if self.annex_is_remote:
            yield from self.list_s3()
        else:
            yield from self.list_local_annex()

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

    def _push_to_local_repo(self, filepath, digest):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.

        Push is done to the local repository annex
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

        # Verify permission are correct before copying
        os.chmod(filepath, self.RMODE)

        # Create fake pointer file
        with open(filepath, 'w', encoding='utf-8') as fakefile:
            fakefile.write(digest)

    def push(self, filepath):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """
        # Compute hash
        digest = hashfile(filepath)

        if self.push_over_s3:
            self._push_to_s3(filepath, digest)
        else:
            self._push_to_local_repo(filepath, digest)

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
