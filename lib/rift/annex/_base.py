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
import tempfile

from rift import RiftError
from rift.TempDir import TempDir
from rift.annex.directory import DirectoryAnnex
from rift.annex.server import ServerAnnex
from rift.annex.s3 import S3Annex
from rift.annex.utils import hashfile, is_pointer, get_digest_from_path


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

    def __init__(self, config, set_annex=None, staging_annex=None):
        self.restore_cache = config.get('annex_restore_cache')
        if self.restore_cache is not None:
            self.restore_cache = os.path.expanduser(self.restore_cache)

         # Set/Staging annex paths
        if set_annex is None:
            set_annex = config.get('set_annex')

        self.set_annex = self.annex_from_type(config, set_annex)
        if self.set_annex is None:
            self.set_annex = DirectoryAnnex(config, set_annex)

        if staging_annex is None:
            staging_annex = config.get('staging_annex')
            if staging_annex is None:
                staging_annex = set_annex

        self.staging_annex = self.annex_from_type(config, staging_annex)
        if self.staging_annex is None:
            self.staging_annex = DirectoryAnnex(config, set_annex)

    def annex_from_type(self, config, annex):
        """
        Return an instance of GenericAnnex based on the given annex address and
        type
        """
        annex_type = annex.get('type')
        if annex_type == 'directory':
            return DirectoryAnnex(config, annex.get('address'))
        if annex_type == 'server':
            return ServerAnnex(config, annex.get('address'))
        if annex_type == 's3':
            return S3Annex(config, annex.get('address'))

        return None

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

    def copy_to_cache(self, identifier, new_file_path):
        """Copy a newly-obtained file to the cache"""
        cached_path = self.get_cached_path(identifier)
        shutil.copyfile(new_file_path, cached_path)

    def get(self, identifier, destpath):
        """Get a file identified by identifier and copy it at destpath."""
        # 1. See if we can restore from cache
        if self.restore_cache:
            self.make_restore_cache()
            cached_path = self.get_cached_path(identifier)
            if os.path.isfile(cached_path):
                logging.debug('Extract %s to %s using restore cache',
                              identifier, destpath)
                shutil.copyfile(cached_path, destpath)
                return

        # 2. See if object is in the set_annex
        if self.set_annex.get(identifier, destpath):
            if self.restore_cache:
                self.copy_to_cache(identifier, destpath)

            return

        logging.info("did not find object in set_annex, will search staging_annex next")

        if self.staging_annex and self.staging_annex.get(identifier, destpath):
            if self.restore_cache:
                self.copy_to_cache(identifier, destpath)

            return

        sys.exit(errno.ENOENT)

    def get_by_path(self, idpath, destpath):
        """Get a file identified by idpath content, and copy it at destpath."""
        self.get(get_digest_from_path(idpath), destpath)

    def delete(self, identifier):
        """Remove a file from set_annex, whose ID is `identifier'"""
        return self.set_annex.delete(identifier)

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
            if is_pointer(filepath):

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
        Iterate over set_annex files, returning for them: filename, size and
        insertion time.
        """
        yield from self.set_annex.list()

    def push(self, filepath):
        """
        Copy file at `filepath' into the staging_annex and replace the original
        file by a fake one pointed to it.

        If the same content is already present, do nothing.
        """
        if self.staging_annex is None:
            logging.error("Staging annex undefined but necessary for push")
            sys.exit(errno.EINVAL)

        # Compute hash
        digest = hashfile(filepath)

        self.staging_annex.push(filepath, digest)

        # Verify permission are correct before updating original file
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
                if is_pointer(source_file):
                    filelist.append(source_file)

        if output_file is None:
            output_file = tempfile.NamedTemporaryFile(delete=False,
                                                      prefix='rift-annex-backup',
                                                      suffix='.tar.gz').name

        return self.set_annex.backup(filelist, output_file)
