#
# Copyright (C) 2024 CEA
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
Synchronize remote repositories.
"""

import os
import time
from datetime import datetime
import shlex
import subprocess
import urllib
import tempfile
import glob
import shutil
import re
import collections
import logging

import dnf

from rift.TempDir import TempDir
from rift.utils import download_file, setup_dl_opener
from rift import RiftError

SyncPatterns = collections.namedtuple('SyncPatterns', ['include', 'exclude'])


class RepoSyncBase:
    """Common parent to all RepoSync* classes."""
    def __init__(self, config, name, output, sync, max_size=None, arch=None):
        self.config = config
        self.name = name
        subdir = sync.get('subdir', '').lstrip('/')
        if arch is not None:
            self.output = os.path.join(output, self.name, subdir, arch)
        else:
            self.output = os.path.join(output, self.name, subdir)
        self.source = urllib.parse.urlparse(os.path.join(sync['source'], subdir))
        self.logfile = os.path.join(
            output,
            f"sync_{name}_{datetime.now().strftime('%Y-%m-%d_%H:%M')}.log"
        )
        self._logfh = None  # Initialized in _log_open()
        self.patterns = SyncPatterns(sync['include'], sync['exclude'])
        self.max_size = max_size

    @property
    def base_url(self):
        """Return base URL (scheme and server) for the repository source URL."""
        return f"{self.source.scheme}://{self.source.netloc}"

    def run(self):
        """
        Run repository synchronization. Ensure repository local directory exists
        and call _run() method on concrete class.
        """
        tic = time.perf_counter()
        setup_dl_opener(self.config.get('proxy'), self.config.get('noproxy'))
        self._ensure_repo_dir()
        self._run()
        self._log_close()
        toc = time.perf_counter()
        logging.info(
            "Repository %s synchronized in %0.4f seconds", self.name, toc - tic
        )

    def _run(self):
        """Synchronization is not actually implemented on base class."""
        raise NotImplementedError

    def _log_open(self):
        self._logfh = open(self.logfile, 'w+', encoding='utf-8')

    def log_write(self, entry):
        """Add entry message in synchronizer log file."""
        if self._logfh is None:
            self._log_open()
        self._logfh.write(entry + '\n')

    def _log_close(self):
        if self._logfh is not None:
            self._logfh.close()

    def _ensure_repo_dir(self):
        """
        Create local directory for this repository if it does not exist.
        """
        if not os.path.exists(self.output):
            os.makedirs(self.output)


class RepoSyncLftp(RepoSyncBase):
    """Synchronize remote repositories with LFTP."""
    def __init__(self, config, name, output, sync, max_size=None, arch=None):
        super().__init__(config, name, output, sync, max_size, arch)
        self.include_arg = ' '.join(
            [f"--include={pattern}" for pattern in self.patterns.include]
        )
        self.exclude_arg = ' '.join(
            [f"--exclude={pattern}" for pattern in self.patterns.exclude]
        )

    @staticmethod
    def _cmd_str(cmd):
        """Transform a list of command arguments into a quoted string."""
        return ' '.join([shlex.quote(arg) for arg in cmd])

    def _run(self):
        """Run repository synchronization with LFTP."""
        cmd = [
            'lftp',
            self.base_url,
            '-e',
            "set ssl:verify-certificate off; mirror --no-empty-dirs "
            f"{self.include_arg} {self.exclude_arg} --delete "
            f"--log {self.logfile} {self.source.path} {self.output}; quit"
        ]
        logging.debug(
            "running synchronization command: %s",
            self._cmd_str(cmd)
        )
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as err:
            raise RiftError(
                f"Error while running command: {self._cmd_str(cmd)}: "
                "exit code: {err.returncode}"
            ) from err


class RepoSyncIndexed(RepoSyncBase):
    """
    Base class for RepoSync* synchronizers that needs to track files files
    declared in index.
    """

    def __init__(self, config, name, output, sync, max_size=None, arch=None):
        super().__init__(config, name, output, sync, max_size, arch)
        self.indexed_files = []

    def _relpath_matches(self, relpath):
        # Check file matches at least one include pattern, if defined.
        if self.patterns.include:
            match_include = False
            for pattern in self.patterns.include:
                if not re.match(pattern, relpath) is None:
                    match_include = True
                    break
            if not match_include:
                logging.debug(
                    "Skipping file %s which does not match any include pattern",
                    relpath
                )
                return False

        # Check file does not match any exclude pattern.
        for pattern in self.patterns.exclude:
            if not re.search(pattern, relpath) is None:
                logging.debug(
                    "Skipping file %s which matches exclude pattern %s",
                    relpath,
                    pattern,
                )
                return False
        return True

    def _clean_output(self, skip_repodata=False):
        """
        Remove unindexed files and empty directories from local mirror. Skip
        repodata directory and its content in output root directory when
        skip_repodata boolean parameter is True.
        """
        for root, dirs, files in os.walk(self.output, topdown=False):
            for filename in files:
                if skip_repodata and filename.startswith('repodata'):
                    continue
                path = os.path.join(root, filename)
                if not path in self.indexed_files:
                    self.log_write(f"rm {path}")
                    logging.info("Removing unindexed file %s", path)
                    os.remove(path)
            for dirname in dirs:
                if skip_repodata and dirname.startswith('repodata'):
                    continue
                path = os.path.join(root, dirname)
                if not os.listdir(path):
                    self.log_write(f"rmdir {path}")
                    logging.info("Removing empty directory %s", path)
                    os.rmdir(path)

    def _run(self):
        """Synchronization is not actually implemented on base class."""
        raise NotImplementedError


class RepoSyncEpel(RepoSyncIndexed):
    """Synchronize EPEL remote repositories."""

    PUB_ROOT = "/pub/epel"

    def __init__(self, config, name, output, sync, max_size=None, arch=None):
        super().__init__(config, name, output, sync, max_size, arch)
        self.pub_url = f"{self.base_url}{self.PUB_ROOT}"

    def _process_line(self, line):
        """Process one EPEL files index line."""
        try:
            (timestamp_s, ftype, _, relpath) = line.split('\t')
        except ValueError:
            # Ignore all lines outside [Files] section with less than 4
            # values separated with tabs
            logging.debug("Skipping non-file line '%s'", line)
            return
        if ftype != 'f':
            logging.debug("Skipping filetype '%s' for path %s", ftype, relpath)
            return
        # Prefix filepath with EPEL public root directory
        abspath = f"{self.PUB_ROOT}/{relpath}"
        if not abspath.startswith(self.source.path):
            logging.debug(
                "Skipping file %s outside of source URL path %s",
                abspath,
                self.source.path,
            )
            return

        # To check against include/exclude pattern, use path relative to
        # repository source URL.
        relpath = abspath[len(self.source.path):].lstrip('/')

        # Check relative path against include/exclude pattern
        if not self._relpath_matches(relpath):
            return

        # The filename in the output directory is the filename in
        # fullfiletimelist-epel index in which the path of source URL is
        # removed after the public root directory.
        output_file = os.path.join(
            self.output,
            relpath,
        )

        # Append output file to the list of indexed files, so it is flagged to
        # not be removed in the end.
        self.indexed_files.append(output_file)

        # Check file exists and its timestamp. If the modification timestamp
        # is over the timestamp in index file, consider the file unmodified
        # and skip it. Else, remove the file so it can be downloaded again.
        if os.path.exists(output_file):
            if int(os.stat(output_file).st_mtime) > int(timestamp_s):
                logging.debug("Ignoring unmodified %s", output_file)
                return
            logging.info("Removing updated file %s", output_file)
            os.unlink(output_file)

        # Create output file parent directories if missing.
        output_directory = os.path.dirname(output_file)
        if not os.path.exists(output_directory):
            # Mention directory creation in log file
            self.log_write(f"mkdir {output_directory}")
            os.makedirs(output_directory)

        url_file = f"{self.base_url}{abspath}"
        self.log_write(f"download {url_file}")
        logging.info("Downloading file %s", url_file)
        try:
            download_file(url_file, output_file, self.max_size)
        except RiftError as err:
            logging.warning("Download failed, skipping entry: %s", str(err))

    def _run(self):
        """Run EPEL repository synchronization."""
        # Download EPEL files index in temporary file
        with tempfile.NamedTemporaryFile(
            mode='r', prefix='rift-epel-filelist-'
        ) as tmp_file:
            filelist_url = f"{self.pub_url}/fullfiletimelist-epel"
            logging.debug("Downloading EPEL files index %s", filelist_url)
            try:
                download_file(filelist_url, tmp_file.name, self.max_size)
            except RiftError as err:
                logging.warning("Download failed, skipping entry: %s", str(err))


            # Open synchronization log file
            logging.debug("Creating synchronization log file %s", self.logfile)

            # Process all lines in index file
            for line in tmp_file:
                self._process_line(line.strip())

        # Remove unindexed files and empty dirs
        self._clean_output()


class RepoSyncDnf(RepoSyncIndexed):
    """Synchronize DNF remote repositories."""

    def _process_package(self, package):
        """Process one package found in DNF repository."""

        relpath = package.remote_location()[len(self.source.geturl()):].lstrip('/')

        # Check relative path against include/exclude pattern
        if not self._relpath_matches(relpath):
            return

        output_file = os.path.join(
            self.output,
            relpath,
        )
        # Append output file to the list of indexed files, so it is flagged to
        # not be removed in the end.
        self.indexed_files.append(output_file)

        # Check file exists and skip download.
        if os.path.exists(output_file):
            logging.debug("Ignoring existing file %s", output_file)
            return

        # Create output file parent directories if missing.
        output_directory = os.path.dirname(output_file)
        if not os.path.exists(output_directory):
            # Mention directory creation in log file
            self.log_write(f"mkdir {output_directory}")
            os.makedirs(output_directory)

        url = package.remote_location()
        self.log_write(f"download {url}")
        logging.info("Downloading file '%s' to '%s'", url, output_directory)
        try:
            download_file(url, output_file, self.max_size)
        except RiftError as err:
            logging.warning("Download failed, skipping entry: %s", str(err))

    def _run(self):
        """Run DNF repository synchronization."""
        # Initialize DNF runtime
        base = dnf.Base()

        # Create temporary directory and use it for DNF metadata cache in order
        # to force re-download of repository metadata at every synchronizations,
        # no matter metadata expiry datetime.
        dnf_metadata_cache_dir = TempDir("dnf-metadata")
        dnf_metadata_cache_dir.create()
        base.conf.cachedir = dnf_metadata_cache_dir.path

        # Add repository in runtime DNF configuration
        base.repos.add_new_repo(
            self.name, base.conf, baseurl=[self.source.geturl()]
        )
        try:
            base.fill_sack(load_system_repo=False)
        except dnf.exceptions.RepoError as err:
            raise RiftError(
                "Unable to download repository metadata from URL "
                f"{self.source.geturl()}: {err}"
            ) from err

        # Query all available packages in remote repository and process them
        query = base.sack.query().available()
        for package in query.run():
            self._process_package(package)

        # Close DNF runtime
        base.close()

        # Remove unindexed files and empty dirs, except repodata in output root
        # directory.
        self._clean_output(skip_repodata=True)

        # Copy repodata directory from cache
        cached_repodata_dirs = glob.glob(f"{dnf_metadata_cache_dir.path}/"
                                         f"{self.name}-*/repodata")
        # Check there is only one result.
        try:
            assert len(cached_repodata_dirs) == 1
        except AssertionError as err:
            raise RiftError("Unexpected number of repodata directory in DNF "
                            f"cache: {cached_repodata_dirs}") from err

        # Remove repodata destination directory, if existing
        repodata = os.path.join(self.output, "repodata")
        if os.path.exists(repodata):
            logging.info("Removing existing repository metadata %s",
                         repodata)
            shutil.rmtree(repodata)

        # Copy new repodata downloaded in DNF metadata cache temporary directory
        logging.info("Copying new cached repository metadata %s",
                     cached_repodata_dirs[0])
        shutil.copytree(cached_repodata_dirs[0], repodata)

        # Remove DNF metadata cache temporary directory
        dnf_metadata_cache_dir.delete()


class RepoSyncFactory:
    """Factory class for all implementations of RepoSync."""
    METHODS = {
        'lftp': RepoSyncLftp,
        'epel': RepoSyncEpel,
        'dnf':  RepoSyncDnf,
    }

    @staticmethod
    def check_valid_method(method):
        """Check given method is supported or raise RiftError"""
        if method not in RepoSyncFactory.METHODS:
            raise RiftError(
                f"Unsupported repository synchronization method {method}"
            )

    @staticmethod
    def get(config, name, output, sync, max_size=None, arch=None):
        """Return the concrete RepoSync* class corresponding to the method."""
        RepoSyncFactory.check_valid_method(sync['method'])
        return RepoSyncFactory.METHODS[sync['method']](
            config, name, output, sync, max_size, arch
        )
