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
import threading
from contextlib import contextmanager
import shlex
from textwrap import dedent
from jinja2 import Template

from rift import RiftError
from rift.TempDir import TempDir
from rift.RPM import RPM
from rift.run import run_command
from rift.Config import _DEFAULT_VARIANT
from rift.proxy import AuthenticatedRepositoryProxyRuntime

# Global dictionary of re-entrant locks for each mock name.
_mock_chroot_locks = {}
# Mutex to serialize access to _mock_chroot_locks dictionary.
_mock_chroot_global_mutex = threading.Lock()

RPMLINT_CONFIG_V1 = 'rpmlint'
RPMLINT_CONFIG_V2 = 'rpmlint.toml'


def rpmlint_env(configdir=None):
    """
    Return a copy of the process environment with XDG_CONFIG_HOME set when
    configdir is set (rpmlint config next to the spec uses that layout).
    Otherwise return None (caller inherits the current environment).
    """
    if not configdir:
        return None
    env = os.environ.copy()
    env['XDG_CONFIG_HOME'] = os.path.realpath(configdir)
    return env


def rpmlint_chroot_script(spec_filepath):
    """
    Return a shell script for ``bash -c`` that runs rpmlint with v1- or v2-style
    argv depending on whether ``rpmlint --version`` looks like major version 2.
    """
    spec_dir = os.path.dirname(spec_filepath)
    q_spec = shlex.quote(spec_filepath)
    q_run_v1 = (
        f"rpmlint -o 'NetworkEnabled False' -f "
        f"{shlex.quote(os.path.join(spec_dir, RPMLINT_CONFIG_V1))} {q_spec}"
    )
    config_v2 = os.path.join(spec_dir, RPMLINT_CONFIG_V2)
    if os.path.exists(config_v2):
        q_run_v2 = f"rpmlint -c {shlex.quote(config_v2)} {q_spec}"
    else:
        q_run_v2 = f"rpmlint {q_spec}"
    return dedent(f"""
        set +e
        VERLINE=$(rpmlint --version 2>/dev/null | head -1)
        if echo "$VERLINE" | grep -q '^2'; then
            {q_run_v2}
        else
            {q_run_v1}
        fi
        exit $?
    """).strip()


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
        self._repo_proxy = None
        self._mockname = f"rift-{self._arch}-{getpass.getuser()}"
        if proj_vers:
            self._mockname = f"{self._mockname}-{proj_vers}"
        logging.debug(self._mockname)

    @contextmanager
    def lock(self):
        """Serialize mock operations sharing this instance's chroot on disk."""
        # Acquire mutex to avoid race condition between multiple threads trying
        # to acquire lock for the same mock name.
        with _mock_chroot_global_mutex:
            # Acquire lock for this mock name.
            _lock = _mock_chroot_locks.get(self._mockname)
            # If no lock for this mock name, create a new one.
            if _lock is None:
                _lock = threading.RLock()
                _mock_chroot_locks[self._mockname] = _lock
        _lock.acquire()
        try:
            yield
        finally:
            _lock.release()

    def _build_template_ctx(self, repolist):
        """ Create a context to build mock template """
        context = {'name': self._mockname, 'arch': self._arch, 'repos': []}
        # Populate with repolist
        prio = 1000
        for idx, repo in enumerate(repolist, start=1):
            assert repo.url is not None
            prio = repo.priority or (prio - 1)
            repo_url = repo.generic_url(self._arch)
            if self._repo_proxy and repo.authenticated():
                repo_url = self._repo_proxy.repo_url(repo, "127.0.0.1")
            repo_ctx = {
                'name': repo.name or f"repo{idx}",
                'priority': prio,
                'url': repo_url,
                'variants': repo.variants,
                'authenticated': repo.authenticated(),
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

        # Skip only when tmpdir exists and still has a path (not after clean()).
        if self._tmpdir is not None and self._tmpdir.path is not None:
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
        with open(macropath, 'w', encoding='utf-8') as fmacro:
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

    def _exec(self, cmd, merge_out_err=True):
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
            merge_out_err=merge_out_err,
            cwd='/'
        )
        if proc.returncode != 0:
            raise RiftError(proc.out if merge_out_err else proc.err)

        return proc

    def init(self, repolist):
        """
        Create a Mock environment.

        This should be cleaned with clean().
        """
        self._repo_proxy = AuthenticatedRepositoryProxyRuntime(self._config, repolist)
        self._repo_proxy.start()
        self._init_tmp_conf(repolist)
        self._exec(['--init'])

    def _bind_mount_dirs_opt(self, paths):
        """Return mock bind_mount plugin option for dirs (host path = chroot path)."""
        unique = sorted({os.path.realpath(p) for p in paths})
        pairs = ",".join(f"('{p}', '{p}')" for p in unique)
        return f'--plugin-option=bind_mount:dirs=[{pairs}]'

    def read_spec(self, filepath):
        """
        Interpret RPM spec file in chroot by running rpmspec command. Return output of
        rpmspec command with some prefixed messages filtered out to make it parsable
        by RPM library.
        """
        filepath_rp = os.path.realpath(filepath)
        proc = self._exec(
            [
                self._bind_mount_dirs_opt([filepath_rp]),
                'chroot',
                'rpmspec',
                '--parse',
                filepath_rp
            ],
            merge_out_err=False
        )

        lines = []

        rpmspec_ignore_prefixes = ("error: ", "warning: ", "rpm: ", "sh: ")
        for line in proc.out.splitlines():
            # filter out rpmspec errors and warings
            ignore_line = False
            for prefix in rpmspec_ignore_prefixes:
                if line.startswith(prefix):
                    ignore_line = True
            if not ignore_line:
                lines.append(line)

        return "\n".join(lines)

    def rpmlint(self, spec_filepath, configdir=None):
        """
        Install rpmlint in the chroot, run rpmlint on spec file in chroot, then
        clean the chroot. Return RunResult of rpmlint command.
        """
        spec_fp = os.path.realpath(spec_filepath)
        spec_dir = os.path.dirname(spec_fp)
        mount_paths = {spec_dir}
        if configdir:
            mount_paths.add(os.path.realpath(configdir))
        bind_opt = self._bind_mount_dirs_opt(mount_paths)

        # Install rpmlint in the chroot.
        self._exec(
            [
                '--no-clean',
                '--no-cleanup-after',
                '--quiet',
                '--pm-cmd',
                'install',
                '-y',
                'rpmlint',
            ]
        )

        # Run rpmlint in the chroot. The self._exec() method is not used here
        # because callers need return code and output of rpmlint command.
        cmd = self._mock_base() + [
            bind_opt,
            '--quiet',
            'chroot',
            '--',
            'bash',
            '-c',
            rpmlint_chroot_script(spec_fp),
        ]
        logging.debug('Running mock rpmlint chroot: %s', ' '.join(cmd[:8]))
        try:
            return run_command(
                cmd,
                capture_output=True,
                merge_out_err=False,
                cwd='/',
                env=rpmlint_env(configdir),
            )
        finally:
            # Clean the chroot to remove rpmlint.
            self._exec(['--quiet', '--clean'])

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
        if self._tmpdir:
            self._tmpdir.delete()
            # Clear handle to avoid later init() skipping _init_tmp_conf()
            # and mock seeing --configdir=None.
            self._tmpdir = None
        self._stop_repo_proxy()
        for rpm in self.resultrpms():
            os.unlink(rpm.filepath)

    def scrub(self):
        """Remove Mock environments (ie. chroots directories) from disk."""
        with self.lock():
            self._init_tmp_conf()
            self._exec(['--scrub=all'])

    def _stop_repo_proxy(self):
        """Stop repository proxy runtime if currently active."""
        if self._repo_proxy is None:
            return
        self._repo_proxy.stop()
        self._repo_proxy = None

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

    def build_rpms(self, srpm, variant, repos, sign):
        """Build binary RPMS using the provided Source RPM pointed by `srpm'"""
        cmd = ['--no-clean', '--no-cleanup-after']

        cmd += [srpm.filepath]
        if variant != _DEFAULT_VARIANT:
            cmd += ['--with', variant]
            for repo in repos.for_variant(variant):
                cmd += ['--enablerepo', repo.name]
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
