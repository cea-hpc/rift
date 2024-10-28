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
Helper classes to manipulate RPM files and SPEC files.
"""

import logging
import os
import re
import shutil
from subprocess import Popen, PIPE, STDOUT, run, CalledProcessError
import time

import rpm


from rift import RiftError
from rift.Annex import Annex, is_binary
import rift.utils

RPMLINT_CONFIG_V1 = 'rpmlint'
RPMLINT_CONFIG_V2 = 'rpmlint.toml'

def _header_values(values):
    """ Convert values from header specfile to strings """
    if isinstance(values, list):
        return [_header_values(val) for val in values]
    if isinstance(values, bytes):
        return values.decode("utf8")
    return str(values)


def rpmlint_v2():
    """Return True if rpmlint major version is 2."""
    # check --version output
    try:
        proc = run(['rpmlint', '--version'], stdout=PIPE, check=True)
    except CalledProcessError as err:
        raise RiftError(
            f"Unable to get rpmlint version: {str(err)}"
        ) from err
    return proc.stdout.decode().startswith("2")


class RPM():
    """Manipulate a source or binary RPM."""

    def __init__(self, filepath, config=None):
        self.filepath = filepath
        self._config = config

        self.name = None
        self.is_source = False
        self.arch = None
        self.source_rpm = None
        self._srcfiles = []

        self._load()

    def _load(self):
        """Extract interesting information from RPM file header"""
        # Read header
        fileno = os.open(self.filepath, os.O_RDONLY)
        transaction = rpm.TransactionSet()
        transaction.setVSFlags(rpm._RPMVSF_NOSIGNATURES)
        hdr = transaction.hdrFromFdno(fileno)
        os.close(fileno)

        # Extract data
        self.name = _header_values(hdr[rpm.RPMTAG_NAME])
        self.arch = _header_values(hdr[rpm.RPMTAG_ARCH])
        self.source_rpm = _header_values(hdr[rpm.RPMTAG_SOURCERPM])
        # With RPM format v3, signature can be found in SIGPIP tag. Starting
        # with RPM format v4, signature is either stored in RSAHEADER or
        # DSAHEADER tags.
        #
        # For reference, see:
        # https://github.com/rpm-software-management/rpm/blob/master/docs/manual/format_v4.md#signature
        #
        # In order to check presence of the signature whatever the RPM package
        # format, we look at all three tags.
        self.is_signed = (
            hdr[rpm.RPMTAG_SIGPGP] is not None
            or hdr[rpm.RPMTAG_RSAHEADER] is not None
            or hdr[rpm.RPMTAG_DSAHEADER] is not None
        )
        self.is_source = hdr.isSource()
        self._srcfiles.extend(_header_values(hdr[rpm.RPMTAG_SOURCE]))
        self._srcfiles.extend(_header_values(hdr[rpm.RPMTAG_PATCH]))

    def extract_srpm(self, specdir, srcdir, annex=None):
        """
        Extract source rpm files into `specdir' and `srcdir'.

        If some binary files are extracted, they are moved to default annex
        or provided one.
        """
        assert self.is_source

        srcdir = os.path.realpath(srcdir)

        # Extract (install) source file and spec file from source rpm
        cmd = ['rpm', '-iv']
        cmd += ['--define', f"_sourcedir {srcdir}"]
        cmd += ['--define', f"_specdir {os.path.realpath(specdir)}"]
        cmd += [self.filepath]
        with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as popen:
            stdout = popen.communicate()[0]
            if popen.returncode != 0:
                raise RiftError(stdout)

        # Backup original spec file
        specfile = os.path.join(specdir, f"{self.name}.spec")
        shutil.copy(specfile, f"{specfile}.orig")

        # Move binary source files to Annex
        annex = annex or Annex(self._config)
        for filename in self._srcfiles:
            filepath = os.path.join(srcdir, filename)
            if is_binary(filepath):
                annex.push(filepath)

    def sign(self):
        """
        Cryptographically sign RPM package with GPG key. Raise RiftError if GPG
        parameters are missing in project configuration or GPG key is not found.
        """
        # GPG parameters not defined in project config, raise RiftError.
        if self._config is None or self._config.get('gpg') is None:
            raise RiftError(
                "Unable to retrieve GPG configuration, unable to sign package "
                f"{self.filepath}",
            )

        gpg = self._config.get('gpg')
        keyring = os.path.expanduser(gpg.get('keyring'))

        # Check gpg_keyring path exists or raise error
        if not os.path.exists(keyring):
            raise RiftError(
                f"GPG keyring path {keyring} does not exist, unable to sign "
                f"package {self.filepath}"
            )

        # If passphrase is defined, add the passphrase to gpg sign command
        # parameters and make it non-interactive.
        gpg_sign_cmd_passphrase = ""
        if gpg.get('passphrase') is not None:
            gpg_sign_cmd_passphrase = (
                f"--batch --passphrase '{gpg.get('passphrase')}' "
                "--pinentry-mode loopback"
            )
        cmd = [
            'rpmsign',
            '--define',
            f"%_gpg_name {gpg.get('key')}",
            '--define',
            f"%_gpg_path {keyring}",
            '--define',
            (
                "%__gpg_sign_cmd %{__gpg} gpg --force-v3-sigs --verbose "
                f"--no-armor {gpg_sign_cmd_passphrase} --no-secmem-warning "
                "-u \"%{_gpg_name}\" -sbo %{__signature_filename} "
                "--digest-algo sha256 %{__plaintext_filename}"
            ),
            '--addsign',
            self.filepath
        ]
        # Run rpmsign command and raise error in case of failure.
        try:
            run(cmd, check=True)
        except CalledProcessError as err:
            raise RiftError(
                f"Error with signing package {self.filepath} command: "
                f"{str(err)}"
            ) from err


class Spec():
    """Access information from a Specfile and build SRPMS."""

    def __init__(self, filepath=None, config=None):
        self.filepath = filepath
        self.srpmname = None
        self.pkgnames = []
        self.sources = []
        self.basename = None
        self.version = None
        self.release = None
        self.changelog_name = None
        self.changelog_time = None
        self.evr = None
        self.arch = None
        self.exclusive_archs = []
        self.epoch = None
        self.dist = None
        self.buildrequires = None
        self.lines = []
        self.variables = {}
        self._config = config or {}
        if self.filepath is not None:
            self.load()

    def _set_macros(self):
        """Set macros specified in configuration file"""
        macros = self._config.get('rpm_macros', {})
        for macro, value in macros.items():
            rpm.delMacro(macro)
            if value:
                rpm.addMacro(macro, value)

    def _parse_vars(self):
        self.variables = {}
        pattern = r"%(?P<keyword>(global|define))\s+(?P<name>.*?)\s+(?P<value>.*)"
        for index, line in enumerate(self.lines):
            match = re.match(pattern, line)
            if match:
                name = match.group('name')
                value = match.group('value')
                keyword = match.group('keyword')
                if name and value:
                    self.variables[name] = Variable(index=index,
                                                    name=name,
                                                    value=value,
                                                    keyword=keyword)

    def load(self):
        """Extract interesting information from spec file."""
        if not os.path.exists(self.filepath):
            raise RiftError(f"{self.filepath} does not exist")
        try:
            rpm.reloadConfig()
            self._set_macros()
            spec = rpm.TransactionSet().parseSpec(self.filepath)
        except ValueError as exp:
            raise RiftError(f"{self.filepath}: {exp}") from exp
        self.pkgnames = [_header_values(pkg.header['name']) for pkg in spec.packages]
        hdr = spec.sourceHeader
        self.srpmname = hdr.sprintf('%{NAME}-%{VERSION}-%{RELEASE}.src.rpm')
        self.basename = hdr.sprintf('%{NAME}')
        self.version = hdr.sprintf('%{VERSION}')
        self.arch = hdr.sprintf('%{ARCH}')
        self.exclusive_archs = _header_values(hdr[rpm.RPMTAG_EXCLUSIVEARCH])
        if hdr[rpm.RPMTAG_CHANGELOGNAME]:
            self.changelog_name = _header_values(
                hdr[rpm.RPMTAG_CHANGELOGNAME][0])
        if hdr[rpm.RPMTAG_CHANGELOGTIME]:
            self.changelog_time = int(_header_values(
                hdr[rpm.RPMTAG_CHANGELOGTIME][0]))
        self.sources.extend(_header_values(
            hdr[rpm.RPMTAG_SOURCE]))
        self.sources.extend(_header_values(
            hdr[rpm.RPMTAG_PATCH]))
        self.buildrequires = ' '.join(_header_values(
            hdr[rpm.RPMTAG_REQUIRENEVRS]))
        self.release = hdr.sprintf('%{RELEASE}')
        self.epoch = hdr.sprintf('%|epoch?{%{epoch}:}:{}|')
        self.dist = rpm.expandMacro('%dist')
        self.update_evr()

        with open(self.filepath, 'r', encoding='utf-8') as fspec:
            self.lines = fspec.readlines()

        self._parse_vars()

    def update_evr(self):
        """
        Update epoch:version-release
        """
        self.evr = "{}{}-{}".format(self.epoch,
                                    self.version,
                                    rift.utils.removesuffix(self.release, self.dist))

    def _inc_release(self, release):
        dist = self.dist
        pattern = r"(?P<baserelease>.*?)?(?P<num>[0-9]+)"
        dist_match = re.match(r".*(?P<dist>%{\??dist}(\s+|$))", release)

        if release.endswith(self.dist):
            pattern += f"({dist})"
        elif dist_match:
            dist = dist_match.group('dist')
            pattern += "(" + dist.replace('?', r'\?') + ")"
        else:
            dist = ''
        pattern += '$'
        release_id = re.match(pattern, release)
        if release_id is None:
            raise RiftError(f"Cannot parse package release: {release}")
        newrelease = int(release_id.group('num')) + 1
        logging.debug("New release from %s to %s", release_id.group('num'),
                      newrelease)
        baserelease = release_id.group('baserelease')
        return f"{baserelease}{newrelease}{dist}"


    def _match_var(self, expression, pattern='.*[0-9]$'):
        """ Get variable with value matching pattern in expression """
        match = re.match(r'(?P<leftbehind>.*)%{?\??(?P<varname>[^}]*)}?', expression)
        if match:
            name = match.group('varname')
            left = match.group('leftbehind')
            if name:
                logging.debug('Spec._match_var: found %s', name)
                try:
                    if re.match(pattern, str(self.variables[name])):
                        return self.variables[name]
                    var = self._match_var(str(self.variables[name]), pattern)
                    if var:
                        return var
                    if left:
                        return self._match_var(left, pattern)
                except KeyError:
                    logging.warning("Warning: unable to resolve %s", name)
            if left:
                return self._match_var(left, pattern)
        return None

    def bump_release(self):
        """
        Increase package release
        """
        self.release = self._inc_release(self.release)
        self.update_evr()


    def add_changelog_entry(self, userstring, comment, bump=False):
        """
        Add a new entry to changelog.

        New record is based on current time and is first in list.
        """

        if bump:
            self.bump_release()

        date = time.strftime("%a %b %d %Y", time.gmtime())
        newchangelogentry = f"* {date} {userstring} - {self.evr}\n{comment}\n"
        chlg_match = None
        for i, _ in enumerate(self.lines):
            if bump:
                release_match = re.match(r'^[Rr]elease:(?P<spaces>\s+)(?P<release>.*$)',
                                         self.lines[i])
                if release_match:
                    release_str = release_match.group('release')
                    # If Release field contains only variables, we may need to
                    # resolv and increment last variable:
                    # Release: %{something}%{?dist}
                    # If no variables found, increment last numeric ID from release
                    try:
                        self.lines[i] = (
                            f"Release:{release_match.group('spaces')}"
                            f"{self._inc_release(release_str)}\n"
                        )
                    except RiftError:
                        var = self._match_var(release_str)
                        if var:
                            var.value = self._inc_release(var.value)
                            var.spec_output(self.lines)

            chlg_match = re.match(r'^%changelog(\s|$)', self.lines[i])
            if chlg_match:
                if len(self.lines) > i + 1 and self.lines[i + 1].strip() != "":
                    newchangelogentry += "\n"

                self.lines[i] += newchangelogentry
                break
        if not chlg_match:
            if self.lines[-1].strip() != "":
                self.lines.append("\n")
            self.lines.append("%changelog\n")
            self.lines.append(newchangelogentry)

        with open(self.filepath, 'w', encoding='utf-8') as fspec:
            fspec.writelines(self.lines)

        # Reload
        self.load()

    def build_srpm(self, srcdir, destdir):
        """
        Build a Source RPM described by this spec file.

        Return a RPM instance of this source RPM.
        """
        cmd = ['rpmbuild', '-bs']
        cmd += ['--define', f"_sourcedir {srcdir}"]
        cmd += ['--define', f"_srcrpmdir {destdir}"]
        cmd += [self.filepath]

        with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as popen:
            stdout = popen.communicate()[0]
            if popen.returncode != 0:
                raise RiftError(stdout)

        return RPM(os.path.join(destdir, self.srpmname))

    def _check(self, configdir=None):
        if configdir:
            env = os.environ.copy()
            env['XDG_CONFIG_HOME'] = configdir
        else:
            env = None

        if rpmlint_v2():
            cmd = ['rpmlint', self.filepath]
            config = os.path.join(os.path.dirname(self.filepath), RPMLINT_CONFIG_V2)
            if os.path.exists(config):
                cmd[1:1] = ['-c', config]
        else:
            # rpmlint v1. Does not fail when config file is missing.
            cmd = ['rpmlint', '-o', 'NetworkEnabled False', '-f',
                os.path.join(os.path.dirname(self.filepath), RPMLINT_CONFIG_V1),
                self.filepath]
        logging.debug('Running rpmlint: %s', ' '.join(cmd))
        return cmd, env

    def check(self, pkg=None):
        """
        Check specfile content using `rpmlint' tool and check missing items
        in package directory.
        """
        configdir = None
        if pkg:
            configdir = pkg.dir
            if self.basename != pkg.name:
                msg = f"name '{pkg.name}' does not match '{self.basename}' in spec file"
                raise RiftError(msg)

            # Changelog section is mandatory
            if not (self.changelog_name or self.changelog_time):
                raise RiftError('Proper changelog section is needed in specfile')

            # Check if all sources are declared and present in package directory
            if pkg.sources - set(self.sources):
                msg = f"Unused source file(s): {' '.join(pkg.sources - set(self.sources))}"
                raise RiftError(msg)
            if set(self.sources) - pkg.sources:
                msg = f"Missing source file(s): {' '.join(set(self.sources) - pkg.sources)}"
                raise RiftError(msg)

        cmd, env = self._check(configdir)
        with Popen(cmd, stderr=PIPE, env=env, universal_newlines=True) as popen:
            stderr = popen.communicate()[1]
            if popen.returncode != 0:
                raise RiftError(stderr or 'rpmlint reported errors')

    def analyze(self, review, configdir=None):
        """Run `rpmlint' for this specfile and fill provided `review'."""
        cmd, env = self._check(configdir)
        with Popen(cmd, stdout=PIPE, stderr=PIPE, env=env, universal_newlines=True) as popen:
            stdout, stderr = popen.communicate()
            if popen.returncode not in (0, 64, 66):
                raise RiftError(stderr or f"rpmlint returned {popen.returncode}")

        for line in stdout.splitlines():
            if line.startswith(self.filepath + ':'):
                line = line[len(self.filepath + ':'):]
                try:
                    linenbr = None
                    code, txt = line.split(':', 1)
                    if code.isdigit():
                        linenbr = int(code)
                        code, txt = txt.split(':', 1)
                    review.add_comment(self.filepath, linenbr,
                                       code.strip(), txt.strip())
                except (ValueError, KeyError):
                    pass

        if popen.returncode != 0:
            review.invalidate()

    def supports_arch(self, arch):
        """
        Returns True is package spec file does not restrict ExclusiveArch or if
        the arch in argument is explicitely set in package ExclusiveArch.
        """
        return not self.exclusive_archs or arch in self.exclusive_archs


class Variable():

    """
        This class represents specfile variables
        Args:
            index (int): Line where variable is defined in specfile
            name: The variable name
            value: The variable value
            keyword: The keyword used to define the variable

        Attributes:
            index (int): Line where variable is defined in specfile
            name: The variable name
            value: The variable value
            keyword: The keyword used to define the variable
    """
    def __init__(self, index, name, value, keyword):
        self.index = index
        self.name = name
        self.value = value
        self.keyword = keyword

    def __str__(self):
        return str(self.value)

    def spec_output(self, buffer=None):
        """
            Return variable definition with specfile syntax.
            Args:
                buffer (list): Buffer containing specfile content

            Raises:
                IndexError: If buffer is not large enough

            Returns:
                define_str: String syntax to define the variable
        """
        define_str = f"%{self.keyword} {self.name} {self.value}"
        if buffer:
            buffer[self.index] = f"{define_str}\n"
        return define_str
