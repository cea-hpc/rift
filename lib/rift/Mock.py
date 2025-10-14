#
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
Contains helper class to work with 'mock' tool, used to build RPMS in a chroot
environment.
"""

import os
import shutil
import glob
import getpass
import logging
from jinja2 import Template

from rift import RiftError
from rift.TempDir import TempDir
from rift.RPM import RPM
from rift.run import run_command

class Mock():
    """
    Interact with 'mock' command, manage its config files and created RPMS.
    """

    MOCK_DIR = '/etc/mock'
    MOCK_TEMPLATE = 'mock.tpl'
    MOCK_DEFAULT = 'default.cfg'
    MOCK_FILES = ['logging.ini', 'site-defaults.cfg']
    MOCK_RESULT = '/var/lib/mock/%s/result'

    def __init__(self, config, arch, proj_vers=None):
        self._config = config
        self._arch = arch
        self._tmpdir = None
        self._mockname = f"rift-{self._arch}-{getpass.getuser()}"
        if proj_vers:
            self._mockname = f"{self._mockname}-{proj_vers}"
        logging.debug(self._mockname)

    def _build_template_ctx(self, repolist):
        """ Create a context to build mock template """
        context = {'name': self._mockname, 'arch': self._arch, 'repos': []}
        # Populate with repolist
        prio = 1000
        for idx, repo in enumerate(repolist, start=1):
            assert repo.url is not None
            prio = repo.priority or (prio - 1)
            repo_ctx = {
                'name': repo.name or f"repo{idx}",
                'priority': prio,
                'url': repo.generic_url(self._arch),
                }
            if repo.module_hotfixes:
                repo_ctx['module_hotfixes'] = repo.module_hotfixes
            if repo.excludepkgs:
                repo_ctx['excludepkgs'] = repo.excludepkgs
            if repo.proxy:
                repo_ctx['proxy'] = repo.proxy
            context['repos'].append(repo_ctx)
        return context


    def _create_template(self, repolist, dstpath):
        """Create 'default.cfg' config file based on a template."""
        # Read template
        tplfile = self._config.project_path(self.MOCK_TEMPLATE)
        with open(tplfile, encoding='utf-8') as fh:
            tpl = Template(fh.read())
        # Write file content
        with open(dstpath, 'w', encoding='utf-8') as fmock:
            fmock.write(tpl.render(self._build_template_ctx(repolist)))
        # We have to keep template timestamp to avoid being detected as a new
        # one each time.
        shutil.copystat(tplfile, dstpath)

    def _init_tmp_conf(self, repolist=None):
        """
        Initialize mock temporary custom configuration directory, unless it is
        already initialized.
        """

        # If _tmpdir is already defined (ie. _init_tmp_conf() has already been
        # called), do nothing.
        if self._tmpdir is not None:
            return

        # Set empty repolist by default.
        if repolist is None:
            repolist = []

        self._tmpdir = TempDir('mock')
        self._tmpdir.create()
        dstpath = os.path.join(self._tmpdir.path, self.MOCK_DEFAULT)
        self._create_template(repolist, dstpath)
        for filename in self.MOCK_FILES:
            filepath = os.path.join(self.MOCK_DIR, filename)
            shutil.copy2(filepath, self._tmpdir.path)

        # Be sure all repos are initialized or raise error
        for repo in repolist:
            if repo.is_file() and not repo.exists():
                raise RiftError(
                    f"Repository {repo.path} does not exist, unable to "
                    "initialize Mock environment"
                )
    def _build_macro_args(self):
        """ Return mock argument to define rpm_macros file """
        rpm_macros = self._config.get('rpm_macros', {})
        if not rpm_macros:
            return []
        # Generate rpm.macro file
        macropath = os.path.join(self._tmpdir.path, 'rpm.macro')
        with open(macropath, 'w') as fmacro:
            for key, value in rpm_macros.items():
                logging.debug("> adding macro %s=%s", key, value)
                fmacro.write(f"%{key} {value}\n")
        return [f"--macro-file={macropath}"]

    def _mock_base(self):
        """Return base argument to launch mock"""
        args = [f'--configdir={self._tmpdir.path}'] + self._build_macro_args()
        logging.debug("> adding mock arguments %s", args)
        # Force mock to print build commands output with print_main_output=yes,
        # no matter if stdout/stderr is a TTY. It is required to capture this
        # output and have the possibility to report it junit files in case of
        # failure, in all execution environments.
        return [
            'mock',
            '--config-opts',
            'print_main_output=yes',
            f"--configdir={self._tmpdir.path}"
        ] + self._build_macro_args()

    def _exec(self, cmd):
        """
        Execute mock command in argument, check its return code and raise
        RiftError with its output in case of error.
        """
        cmd = self._mock_base() + cmd
        logging.debug('Running mock: %s', ' '.join(cmd))
        proc = run_command(
            cmd,
            live_output=logging.getLogger().isEnabledFor(logging.INFO),
            capture_output=True,
            merge_out_err=True,
            cwd='/'
        )
        if proc.returncode != 0:
            raise RiftError(proc.out)

    def init(self, repolist):
        """
        Create a Mock environment.

        This should be cleaned with clean().
        """
        self._init_tmp_conf(repolist)
        self._exec(['--init'])

    def resultrpms(self, pattern='*.rpm', sources=True):
        """
        Iterate over built RPMS matching `pattern' in mock result directory.
        """
        pathname = os.path.join(self.MOCK_RESULT % self._mockname, pattern)
        for filepath in glob.glob(pathname):
            rpm = RPM(filepath, config=self._config)
            if sources or not rpm.is_source:
                yield rpm

    def clean(self):
        """Clean temporary files and RPMS created for this instance."""
        self._tmpdir.delete()
        for rpm in self.resultrpms():
            os.unlink(rpm.filepath)

    def scrub(self):
        """Remove Mock environments (ie. chroots directories) from disk."""
        self._init_tmp_conf()
        self._exec(['--scrub=all'])

    def build_srpm(self, specpath, sourcedir, sign):
        """
        Build a source RPM using the provided spec file and source directory.
        """
        specpath = os.path.realpath(specpath)
        sourcedir = os.path.realpath(sourcedir)
        cmd = ['--buildsrpm']
        cmd += ['--no-clean', '--no-cleanup-after']
        cmd += ['--spec', specpath, '--source', sourcedir]
        self._exec(cmd)
        package = list(self.resultrpms('*.src.rpm'))[0]
        # Sign source package
        if sign:
            package.sign()

        return package

    def build_rpms(self, srpm, sign):
        """Build binary RPMS using the provided Source RPM pointed by `srpm'"""
        cmd = ['--no-clean', '--no-cleanup-after']
        cmd += [srpm.filepath]
        self._exec(cmd)

        packages = list(self.resultrpms('*.rpm', sources=False))
        # Sign all built binary packages
        if sign:
            for package in packages:
                package.sign()

        # Return the list of built RPMs here.
        return packages

    def publish(self, repo):
        """
        Copy binary RPMS from Mock result directory into provided repository
        `repo'.
        """
        for rpm in self.resultrpms():
            repo.add(rpm)
