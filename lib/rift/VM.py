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
Class to start, stop and manipulate VM used mostly for testing.
"""

import os
import pwd
import grp
import sys
import time
import datetime
import shlex
import platform
import logging
import tempfile
import textwrap
import termios
import select
import struct
import socket
import uuid
import shutil
import atexit
import hashlib
from subprocess import Popen, PIPE, STDOUT, check_output, run, CalledProcessError

from jinja2 import Template

from rift import RiftError
from rift.Config import _DEFAULT_VIRTIOFSD
from rift.Repository import ProjectArchRepositories
from rift.TempDir import TempDir
from rift.utils import download_file, setup_dl_opener
from rift.run import run_command

__all__ = ['VM']

ARCH_EFI_BIOS = "./usr/share/edk2/aarch64/QEMU_EFI.silent.fd"
CLOUD_INIT_SEED_ISO = 'seed.iso'

def is_virtiofs_qemu(virtiofsd=_DEFAULT_VIRTIOFSD):
    """
    This function checks if virtiofsd is from qemu package or a standalone rust
    version
    """
    output = b''
    try:
        output = check_output(f"{virtiofsd} --version",
                              stderr=STDOUT,
                              shell=True)
    except CalledProcessError:
        try:
            # virtiofsd from qemu need to be lauched as 'root'...
            output = check_output(f"sudo {virtiofsd} --version",
                                  stderr=STDOUT,
                                  shell=True)
        except CalledProcessError:
            logging.error("Cannot get %s version", virtiofsd)

    if 'qemu' in output.decode() or 'FUSE' in output.decode():
        logging.debug("%s: Qemu version detected", virtiofsd)
        return True

    logging.debug("%s: Qemu version not detected", virtiofsd)
    return False


def gen_virtiofs_args(socket_path, directory, qemu=False, virtiofsd=_DEFAULT_VIRTIOFSD):
    """
    Handle virtiofsd args.
    Both version don't have the same argument handling, this function provide
    the correct arguments for the two versions.
    """
    if qemu:
        return ['sudo', virtiofsd,
                f"--socket-path={socket_path}",
                '-o', f"source={directory}",
                '-o', 'cache=auto', '--syslog', '--daemonize']
    return [virtiofsd,
            '--socket-path', socket_path,
            '--sandbox=none', '--shared-dir', directory,
            '--cache', 'auto']

class VM():
    """Manipulate VM process and related temporary files."""

    _PROJ_MOUNTPOINT = '/rift.project'
    NAME = 'rift1.domain'
    SUPPORTED_FS = ('9p', 'virtiofs')

    def __init__(self, config, arch, tmpmode=True, extra_repos=None):
        self.version = config.get('version', '0')
        self.arch = arch

        self._image = config.get('vm_image', arch=arch)
        self._project_dir = config.project_dir

        if extra_repos is None:
            extra_repos = []

        self._repos = ProjectArchRepositories(config, arch).all + extra_repos

        self.address = config.get('vm_address')
        self.port = self.default_port(config.get('vm_port_range'))
        self.cpus = config.get('vm_cpus', 1)
        self.memory = config.get('vm_memory')
        self.qemu = config.get('qemu', arch=arch)

        # default emulated cpu architecture
        if self.arch == 'aarch64':
            self.cpu_type = config.get('vm_cpu', 'cortex-a72')
        else:
            self.cpu_type = config.get('vm_cpu', 'host')

        # Specific aarch64 options
        self.arch_efi_bios = config.get('arch_efi_bios', ARCH_EFI_BIOS)
        ##

        # Get guest shared fstype
        self.virtiofsd = config.get('virtiofsd', _DEFAULT_VIRTIOFSD)
        self.shared_fs_type = config.get('shared_fs_type', '9p')
        if self.shared_fs_type not in self.SUPPORTED_FS:
            raise RiftError(f"{self.shared_fs_type} not supported to share filesystems")
        ##


        self.tmpmode = tmpmode
        self.copymode = config.get('vm_image_copy')
        self._vm = None
        self._helpers = []
        self._tmpimg = None
        self.consolesock = f"/tmp/rift-vm-console-{self.vmid}.sock"
        self.proxy = config.get('proxy')
        self.no_proxy = config.get('no_proxy')
        self.additional_rpms = config.get('vm_additional_rpms')
        self.cloud_init_tpl = config.project_path(
            config.get('vm_cloud_init_tpl')
        )
        self.build_post_script = config.project_path(
            config.get('vm_build_post_script')
        )
        self.images_cache = config.get('vm_images_cache')

    @property
    def vmid(self):
        """
        Generate a checksum for the triplet current user, architecture and version
        that can be used to uniquely identify a VM for this combination.
        """
        return hashlib.sha1(
            f"{os.getuid()}-{self.arch}-{self.version}".encode()
        ).hexdigest()

    def default_port(self, port_range):
        """
        Return the default port number for this VM considering its unique
        identifier and the given port range.
        """
        try:
            assert port_range['max'] > port_range['min']
        except AssertionError as exc:
            raise RiftError(
                "VM port range maximum must be greater than the minimum"
            ) from exc
        return (
            int(self.vmid, 16) % (port_range['max'] - port_range['min'])
        ) + port_range['min']

    def _mk_tmp_img(self):
        """Create a temp VM image to avoid modifying the real image disk."""

        # Create a temporary file for VM image
        # XXX: Maybe a mkstemp() is better here to avoid removing file
        # when VM process is not stopped in purpose
        self._tmpimg = tempfile.NamedTemporaryFile(prefix='rift-vm-img-')

        if self.copymode:
            # Copy qcow image for VM, based on temp file
            cmd = ['dd', 'status=progress', 'conv=sparse', 'bs=1M']
            cmd += [f"if={os.path.realpath(self._image)}"]
            cmd += [f"of={self._tmpimg.name}"]
        else:
            # Create qcow image for VM, based on temp file
            cmd = ['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2']
            cmd += ['-o', f"backing_file={os.path.realpath(self._image)}"]
            cmd += [self._tmpimg.name]

        logging.debug("Creating VM image file: %s", ' '.join(cmd))
        with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as popen:
            stdout = popen.communicate()[0]
            if popen.returncode != 0:
                raise RiftError(stdout)

    def _make_drive_cmd(self):
        cmd = []
        helper_cmd = []
        if self.shared_fs_type == '9p':
            cmd += ['-virtfs', f"local,id=project,path={self._project_dir},"
                    'mount_tag=project,security_model=none']
            for repo in self._repos:
                if repo.is_file():
                    if not repo.exists():
                        raise RiftError(
                            f"Repository {repo.path} does not exist, unable to "
                            "start VM"
                        )
                    cmd += ['-virtfs',
                            f"local,id={repo.name},path={repo.path},"
                            f"mount_tag={repo.name},security_model=none"]
        elif self.shared_fs_type == 'virtiofs':
            # Add a shared memory object to allow virtiofsd shares
            cmd += ['-object',
                    f'memory-backend-file,id=mem,size={str(self.memory)}M,mem-path=/tmp,share=on']
            # Use platform.machine() instead of platform.proccessor to be container
            # compatible.
            if self.arch == platform.machine():
                cmd += ['-machine', 'memory-backend=mem,accel=kvm']
            else:
                cmd += ['-machine', 'memory-backend=mem']
            cmd += ['-chardev', 'socket,id=project,path=/tmp/.virtio_fs_project',
                    '-device', 'vhost-user-fs-pci,queue-size=1024,chardev=project,tag=project']

            qemu_version = is_virtiofs_qemu(self.virtiofsd)
            helper_cmd.append(
                gen_virtiofs_args(
                    socket_path='/tmp/.virtio_fs_project',
                    directory=self._project_dir,
                    qemu=qemu_version,
                    virtiofsd=self.virtiofsd
                )
            )
            for repo in self._repos:
                if repo.is_file():
                    if not repo.exists():
                        raise RiftError(
                            f"Repository {repo.path} does not exist, unable to "
                            "start VM"
                        )
                    cmd += ['-chardev',
                            f"socket,id={repo.name},path=/tmp/.virtio_fs_{repo.name}",
                            '-device',
                            "vhost-user-fs-pci,queue-size=1024,"
                            f"chardev={repo.name},tag={repo.name}"]
                    helper_cmd.append(
                        gen_virtiofs_args(
                            socket_path=f"/tmp/.virtio_fs_{repo.name}",
                            directory=repo.path,
                            qemu=qemu_version,
                            virtiofsd=self.virtiofsd
                        )
                    )
        return cmd, helper_cmd

    def _fix_socket_rights(self):
        """
        Ugly hack to have root accessible sockets for virtiofsd...
        """
        sockets = []
        if self.shared_fs_type == 'virtiofs':
            sockets = ['/tmp/.virtio_fs_project']
            for repo in self._repos:
                if repo.is_file():
                    sockets.append(f"/tmp/.virtio_fs_{repo.name}")
            with Popen(['sudo', '/bin/chmod', '777'] + sockets) as popen:
                popen.wait()

    def _gen_qemu_args(self, image_file, seed):
        """ Generate qemu command line arguments """
        # Start VM process
        cmd = shlex.split(self.qemu)

        # If we are on the same architecture we should be able to use kvm
        # acceleration
        # Use platform.machine() instead of platform.proccessor to be container
        # compatible.
        if self.arch == platform.machine():
            cmd += ['-enable-kvm']
        else:
            cmd += ['-machine', 'virt']

        cmd += ['-cpu', self.cpu_type]

        cmd += ['-name', 'rift', '-display', 'none']
        cmd += ['-m', str(self.memory), '-smp', str(self.cpus)]


        # UEFI for aarch64
        if self.arch == 'aarch64':
            cmd += ['-bios', self.arch_efi_bios]

        # Drive
        # TODO: switch to --device syntax
        cmd += ['-drive', f"file={image_file},if=virtio,format=qcow2,cache=unsafe"]

        # Console
        cmd += ['-chardev', f"socket,id=charserial0,path={self.consolesock},"
                "server=on,wait=off"]
        # aarch64 platform need specific serial configuration
        if self.arch == 'aarch64':
            cmd += ['-device', 'virtio-serial,id=ser0,max_ports=8']
            cmd += ['-serial', 'chardev:charserial0']
        else:
            cmd += ['-device', 'isa-serial,chardev=charserial0,id=serial0']


        # NIC
        cmd += ['-netdev', f"user,id=hostnet0,hostname={self.NAME},"
                f"hostfwd=tcp::{self.port}-:22"]
        # aarch64 platform don't support PCI
        if self.arch == 'aarch64':
            cmd += ['-device', 'virtio-net-device,netdev=hostnet0']
        else:
            cmd += ['-device', 'virtio-net-pci,netdev=hostnet0,bus=pci.0,addr=0x3']

        if seed is not None:
            cmd += ['-drive', f"driver=raw,file={seed},if=virtio"]

        return cmd


    def spawn(self, seed=None):
        """Start VM process in background"""

        # TODO: use -snapshot from qemu cmdline instead of creating temporary VM image
        if self.tmpmode:
            self._mk_tmp_img()
            imgfile = self._tmpimg.name
        else:
            imgfile = self._image

        cmd = self._gen_qemu_args(imgfile, seed)
        fs_cmds, helper_cmds = self._make_drive_cmd()
        cmd += fs_cmds


        logging.info("Qemu shared fs type: %s", self.shared_fs_type)
        for helper_cmd in helper_cmds:
            logging.info("Starting helper process (%s)", helper_cmd)
            self._helpers.append(Popen(helper_cmd, stderr=PIPE))

        logging.info("Waiting 5s for helper processes VM")
        time.sleep(5)
        logging.debug("Fix sockets right...")
        self._fix_socket_rights()

        logging.info("Starting VM process")
        logging.debug("Running VM command: %s", ' '.join(cmd))
        self._vm = Popen(cmd, stderr=PIPE)


    def prepare(self):
        """
        Post-boot VM configuration.

        This configure user, group, hosts, yum repos and mount points.
        """
        # Be sure current user/group exists in VM
        userline = ':'.join([str(item) for item in pwd.getpwuid(os.getuid())])
        (g_name, g_passwd, g_gid, g_mem) = grp.getgrgid(os.getgid())
        groupline = f"{g_name}:{g_passwd}:{g_gid}:{','.join(g_mem)}"

        if self.shared_fs_type == '9p':
            options = 'trans=virtio,version=9p2000.L,msize=131096'
        else:
            options = 'defaults'
            # For guest kernel > 5.6
            #options = 'defaults'
        # Build shared mount point info.
        mkdirs = [self._PROJ_MOUNTPOINT]
        fstab = [f"project {self._PROJ_MOUNTPOINT} {self.shared_fs_type} {options},ro 0 0"]
        repos = []
        prio = 1000
        for repo in self._repos:
            if repo.is_file():
                mkdirs.append(f"/rift.{repo.name}")
                fstab.append(f"{repo.name} /rift.{repo.name} {self.shared_fs_type} "
                             "{options} 0 0")
                url = f"file:///rift.{repo.name}/"
            else:
                url = repo.url
            prio = repo.priority or (prio - 1)
            repos.append(textwrap.dedent(f"""\
                [{repo.name}]
                name={repo.name}
                baseurl={url}
                gpgcheck=0
                priority={prio}
                """))
            if repo.excludepkgs:
                repos.append(f"excludepkgs={repo.excludepkgs}\n")
            if repo.module_hotfixes:
                repos.append(f"module_hotfixes={repo.module_hotfixes}\n")
            if repo.proxy:
                repos.append(f"proxy={repo.proxy}\n")

        # Build the full command line
        def joinl(items):
            """
            Join list of strings with new line character. This inner function is
            used as a workaround for f-string limitation which lack support of
            new line character.
            """
            return "\n".join(items)

        # Construct the command to write fstab entries
        fstab_cmd = joinl([f'echo "{line}" >> /etc/fstab' for line in fstab])

        cmd = textwrap.dedent(f"""
            # Static host resolution
            echo '{self.address} {self.NAME}'  >> /etc/hosts

            echo '{userline}' >> /etc/passwd
            echo '{groupline}' >> /etc/group
            
            # Mount shared fs (9p, virtiofs,...)
            mkdir {' '.join(mkdirs)}
            {fstab_cmd}
            mount -t {self.shared_fs_type} -a

            # Uses repos from the Rift configuration
            /bin/rm -f /etc/yum.repos.d/*.repo
            echo "{joinl(repos)}" > /etc/yum.repos.d/rift.repo

            if [ -x /usr/bin/dnf ] ; then
                dnf -d1 makecache
            else
                yum -d1 makecache fast
            fi
        """)
        self.cmd(cmd)

    def cmd(self, command=None, options=('-T',), **kwargs):
        """Run specified command inside this VM"""
        cmd = ['ssh', '-oStrictHostKeyChecking=no', '-oLogLevel=ERROR',
               '-oUserKnownHostsFile=/dev/null',
               '-oBatchMode=yes', '-p', str(self.port),
               'root@127.0.0.1']
        if options:
            cmd += options
        if command:
            cmd.append(command)
        logging.debug("Running command in VM: %s", ' '.join(cmd))
        return run_command(cmd, **kwargs)

    def copy(self, source, dest, stderr=None):
        """Copy files from or to VM"""
        cmd = ['scp', '-oStrictHostKeyChecking=no', '-oLogLevel=ERROR',
               '-oUserKnownHostsFile=/dev/null', '-r', '-P', str(self.port)]
        cmd.append(source.replace('rift:', 'root@127.0.0.1:'))
        cmd.append(dest.replace('rift:', 'root@127.0.0.1:'))
        logging.debug("Copy files with VM: %s", ' '.join(cmd))
        with Popen(cmd, stderr=stderr) as popen:
            popen.wait()
            return popen.returncode


    def console(self):
        """Console of VM Hit Ctrl-C 3 times to exit"""
        retcode = 0
        output = memoryview(bytearray(32))

        # We use SOCK_STREAM as it comes the qemu UNIX socket confiuration
        console_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        console_socket.connect(self.consolesock)
        console_socket.setblocking(0)

        self_stdin = sys.stdin.fileno()
        old = termios.tcgetattr(self_stdin)
        new = list(old)
        new[3] = new[3] & ~termios.ECHO & ~termios.ISIG & ~termios.ICANON
        termios.tcsetattr(self_stdin, termios.TCSANOW, new)

        last_int = datetime.datetime.now()
        int_count = 0
        while 1:
            rdy = select.select([sys.stdin, console_socket], [], [console_socket])
            if console_socket in rdy[2]:
                sys.stderr.write('Connection closed\n')
                retcode = 1
                break
            # Exit if Ctrl-C is pressed repeatedly
            if sys.stdin in rdy[0]:
                buf = os.read(self_stdin, 4)
                # Here 3 == ^C
                if len(buf) > 0 and struct.unpack('b', buf[0:1])[0] == 3:
                    if (datetime.datetime.now() - last_int).total_seconds() > 2:
                        last_int = datetime.datetime.now()
                        int_count = 1
                    else:
                        int_count += 1

                    if int_count == 3:
                        print('\nDetaching ...')
                        break
                console_socket.sendall(buf)

            ## Get distant output (recv_into metod)
            if console_socket in rdy[0]:
                msg_len = console_socket.recv_into(output, 32)
                # Write to bytes array converted into strings
                sys.stdout.write(''.join([f"{m:c}" for m in output[:msg_len]]))
                sys.stdout.flush()

        # Restore terminal now to let user interrupt the wait if needed
        termios.tcsetattr(self_stdin, termios.TCSANOW, old)
        return retcode


    def run_test(self, test):
        """
        Run specified test using this VM.

        If test is local, it is run on local host, if not, it is run inside the
        VM.
        """
        funcs = {}
        funcs['vm_cmd'] = (
            "ssh -oUserKnownHostsFile=/dev/null -oStrictHostKeyChecking=no "
            f"-oLogLevel=ERROR -T -p {self.port} root@127.0.0.1 \"$@\""
        )
        funcs['vm_wait'] = textwrap.dedent("""\
            rc=1
            for i in {1..7}
            do
              sleep 5
              echo -n .
              vm_cmd echo -e '\\\\nConnection is OK' && rc=0 && break
            done
            return $rc""")
        funcs['vm_reboot'] = textwrap.dedent("""\
            echo -n 'Restarting VM...'
            vm_cmd 'reboot' || true; sleep 5 && vm_wait || return 1""")

        if not test.local:
            if test.command.startswith(self._project_dir):
                testcmd = test.command[len(self._project_dir) + 1:]
            else:
                testcmd = test.command
            cmd = f"cd {self._PROJ_MOUNTPOINT}; {testcmd}"
            return self.cmd(cmd, capture_output=True)

        cmd = ''
        for func, code in funcs.items():
            cmd += f"{func}() {{ {code}; }}; export -f {func}; "
        cmd += shlex.quote(test.command)

        logging.debug("Running command outside VM: %s", cmd)
        return run_command(cmd, capture_output=True, shell=True)

    def running(self):
        """Check if VM is already running."""
        return self.cmd('/bin/true', live_output=False).returncode == 0

    def ready(self):
        """
        Wait until VM is ready to accept commands.

        Return False if it is not ready after 25 seconds.
        """
        sleeping_time = 5
        if self.arch == 'aarch64': # VM very long to boot in emulation mode
            sleeping_time = 20

        for _ in range(1, 5):
            # Check if Qemu process is really running
            if self._vm.poll() is not None:
                raise RiftError(f"Unable to get VM running {self._vm.stderr.read().decode()}")
            time.sleep(sleeping_time)
            if self.running():
                return True
            sys.stdout.write('.')
            sys.stdout.flush()
        return False

    def stop(self, unlink=True):
        """
        Shutdown the VM and remove temporary files if unlink argument is True.

        First try to terminate it cleanly for 5 sec. It fails, kill it.
        """
        # Sending TERM signal
        if self._vm.poll() is None:
            pid = self._vm.pid
            logging.debug("Sending TERM signal to VM process (%d)", pid)
            self._vm.terminate()

        # Delay for VM to cleanly shutdown before killing it
        for _ in range(1, 5):
            if self._vm.poll() is not None:
                break
            time.sleep(1)
        else:
            pid = self._vm.pid
            logging.debug("Sending KILL signal to VM process (%d)", pid)
            self._vm.kill()

        # Stop helper processes
        for helper in self._helpers:
            if helper.poll() is None:
                pid = helper.pid
                logging.debug("Sending TERM signal to helper process (%d)", pid)
                helper.terminate()


        # Unlink temp VM image
        if unlink:
            self.unlink()

    def unlink(self):
        """
        Remove temporary image if used.
        """
        if self._tmpimg and not self._tmpimg.closed:
            logging.debug("Unlink VM temporary image file '%s'",
                          self._tmpimg.name)
            self._tmpimg.close()
            self._tmpimg = None

    def restart(self):
        """
        Restart a running VM.
        """
        logging.info("Restarting VM")
        if not self.running():
            raise RiftError("Unable to restart unreachable VM")
        self.cmd("reboot")
        time.sleep(5)  # let 5 seconds for the VM to stop properly
        # wait for the VM to restart or fail after timeout
        if not self.ready():
            raise RiftError("Failed to restart VM")

    def _dl_base_image(self, url, force):
        """
        Download in cache the base cloud image whose URL is provided in
        argument. The download is skipped if the image is already present in
        cache. Return the path to the downloaded file on the filesystem.
        """
        # If images cache directory is not defined, create a temporary
        # directory and register its deletion at exit. If it is defined in
        # configuration, check it exists or fail with RiftError.
        if not self.images_cache:
            tmp_cache_dir = TempDir("cache")
            tmp_cache_dir.create()
            self.images_cache = tmp_cache_dir.path
            atexit.register(tmp_cache_dir.delete)
        elif (
                not os.path.exists(self.images_cache) or
                not os.path.isdir(self.images_cache)
            ):
            raise RiftError(
                f"Cloud images cache directory {self.images_cache} does not "
                "exist"
            )

        base_image_path = os.path.join(self.images_cache, os.path.basename(url))

        # File is already present in cache, just return its path and skip
        # download.
        if os.path.exists(base_image_path):
            if force:
                logging.info(
                    "Download is forced, removing cached file %s",
                    base_image_path)
                os.remove(base_image_path)
            else:
                logging.info(
                    "Using cached file %s, skipping download",
                    base_image_path
                )
                return base_image_path

        logging.info("Downloading file %s", url)

        # Setup proxy if defined
        setup_dl_opener(self.proxy, self.no_proxy)

        # Download file
        download_file(url, base_image_path)

        return base_image_path

    def _build_seed_iso(self):
        """
        Generate cloud-init meta-data file and user-data file based on the
        template in project directory. An ISO image is then generated in
        conformity with cloud-init expectations for nocloud datasource.
        """
        # Create temporary directory and register its deletion on program exit.
        tmp_seed_dir = TempDir("seed")
        tmp_seed_dir.create()
        atexit.register(tmp_seed_dir.delete)

        seed_iso_file = os.path.join(
            tmp_seed_dir.path,
            CLOUD_INIT_SEED_ISO
        )
        # Generate cloud-init meta_data file
        meta_data_file = os.path.join(tmp_seed_dir.path, "meta-data")
        with open(meta_data_file, 'w', encoding='utf-8') as fh_meta:
            fh_meta.write(
                f"instance-id: {uuid.uuid4()}\nlocal-hostname: rift\n"
            )

        # Generate cloud-init user_data file
        user_data_file = os.path.join(tmp_seed_dir.path, "user-data")

        try:
            with open(self.cloud_init_tpl, encoding='utf-8') as fh:
                tpl = Template(fh.read())
        except FileNotFoundError as err:
            raise RiftError(
                "Unable to find cloud-init template file "
                f"{self.cloud_init_tpl}"
            ) from err
        with open(user_data_file, 'w', encoding='utf-8') as fh_user:
            fh_user.write(
                tpl.render(
                    proxy=self.proxy,
                    no_proxy=self.no_proxy,
                    repositories=self._repos
                )
            )

        # Generate seed iso
        logging.info("Generating cloud-init seed ISO %s", seed_iso_file)
        try:
            run(
                ['genisoimage', '-output', seed_iso_file,
                 '-input-charset', 'utf-8', '-volid', 'cidata', '-joliet',
                 '-rock', user_data_file, meta_data_file],
                cwd=tmp_seed_dir.path,
                check=True)
        except CalledProcessError as error:
            raise RiftError(
                f"Error while generating seed iso: {str(error)}"
            ) from error

        return seed_iso_file

    def _build_run_post_script(self, rpm_basenames):
        """
        Run VM build post script if it exists. The list of RPM packages
        basenames in argument are provided as an environment variable to the
        script.
        """
        if not os.path.exists(self.build_post_script):
            logging.info(
                "Build post script %s not found, skipping its execution…",
                self.build_post_script
            )
            return

        # Run build post script in the VM with some parameters bundled in
        # environment variables.
        env_str = (
            f"RIFT_SHARED_FS_TYPE={self.shared_fs_type} "
            f"RIFT_ADDITIONAL_RPMS={':'.join(rpm_basenames)} "
            f"RIFT_REPOS={':'.join([repo.name for repo in self._repos])}"
        )
        with open(self.build_post_script, encoding='utf-8') as fh:
            if self.cmd(
                    f"{env_str} bash -",
                    stdin=fh
                ).returncode:
                self.stop()
                raise RiftError("Error while running build post script")

    def _build_write_output(self, output):
        """
        Write built VM image in output.
        """
        if self.copymode:
            # In copymode, just copy the image file to its resulting name
            shutil.copy(self._tmpimg.name, output)
        else:
            # If an overlay over the cloud image was used, convert it to a full
            # image with qemu-img.
            try:
                run(
                    ['qemu-img', 'convert', '-c', '-O', 'qcow2',
                     self._tmpimg.name, output],
                    check=True)
            except CalledProcessError as error:
                raise RiftError(
                    f"Error while converting resulting image: {str(error)}"
                ) from error

    def build(self, url, force, keep, output):
        """
        Build VM image.
        """

        # Check the VM is not already running or fail.
        if self.running():
            raise RiftError(
                'VM is already running then unable to build image, stop the VM '
                'first.'
            )

        # Download image if necessary
        base_image_path = self._dl_base_image(url, force)

        # Build cloud-init seed iso
        seed_iso_file = self._build_seed_iso()

        # Use cloud base image for current VM and start it with seed iso
        self._image = base_image_path
        self.spawn(seed=seed_iso_file)

        if not self.ready():
            # Unless keep is true, stop virtual machin and unlink temporary
            # image.
            if not keep:
                self.stop()
            raise RiftError("Failed to start VM with base cloud image")

        # Copy additional RPM and fill a list with all basenames
        rpm_basenames = []
        for additional_rpm in self.additional_rpms:
            rpm_abs_path = os.path.expanduser(additional_rpm)
            rpm_basename = os.path.basename(rpm_abs_path)
            self.copy(rpm_abs_path, f"rift:/tmp/{rpm_basename}")
            rpm_basenames.append(rpm_basename)

        # Run post script
        self._build_run_post_script(rpm_basenames)

        # Restart the VM to check everything is OK.
        self.restart()

        # Export the final image
        logging.info("Exporting image %s", output)

        # Stop VM without removing temporary image
        self.stop(unlink=False)

        # Check if output already exists
        if os.path.exists(output):
            # Ask user interactively if image can be overwritten.
            user_input = input(
                f"Image {output} already exist, overwrite this file? (yes/NO): "
            )
            if user_input.lower() == "yes":
                logging.debug("Removing image %s", output)
                os.remove(output)
            else:
                self.unlink()  # remove temporary image
                logging.info("Exiting")
                return

        # Write output image
        self._build_write_output(output)

        # Remove temporary image
        self.unlink()
