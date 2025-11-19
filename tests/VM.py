#
# Copyright (C) 2024 CEA
#
import os
import shutil
import atexit
from unittest.mock import patch, Mock

import platform
from TestUtils import RiftTestCase, RiftProjectTestCase, make_temp_dir
from rift.Config import (
    Config,
    _DEFAULT_VM_ADDRESS,
    _DEFAULT_QEMU_CMD,
    _DEFAULT_VM_MEMORY,
    _DEFAULT_VIRTIOFSD,
    _DEFAULT_VM_PORT_RANGE_MIN,
    _DEFAULT_VM_PORT_RANGE_MAX,
)
from rift.Repository import ConsumableRepository
from rift.VM import VM, ARCH_EFI_BIOS, gen_virtiofs_args
from rift import RiftError

# For optimization purpose, create a global cache directory that is removed
# only when all tests are finished. If this cache directory would have been
# created in VMTest.setUp(), many tests would trigger image download which
# would cause multiple GB of data transfer on the Internet and would
# significantly extend tests duration.
GLOBAL_CACHE = make_temp_dir()
atexit.register(shutil.rmtree, GLOBAL_CACHE)

# Use https_proxy as proxy project configuration parameter if defined in
# environment.
PROXY = os.environ.get('https_proxy')
VALID_IMAGE_URL = {
    'x86_64': (
        'https://repo.almalinux.org/almalinux/8/cloud/x86_64/images/'
        'AlmaLinux-8-GenericCloud-latest.x86_64.qcow2'
    ),
    'aarch64': (
        'https://repo.almalinux.org/almalinux/8/cloud/aarch64/images/'
        'AlmaLinux-8-GenericCloud-latest.aarch64.qcow2'
    )
}

class VMTest(RiftTestCase):
    """
    Tests class for VMs
    """
    def setUp(self):
        self.config = Config()
        self.config.project_dir = '/'

    def test_init(self):
        """ Test VM initialisation """
        # default
        vm = VM(self.config, 'x86_64')
        self.assertEqual(vm.arch, 'x86_64')
        self.assertEqual(vm.cpu_type, 'host')
        self.assertEqual(vm.cpus, 4)
        self.assertEqual(vm.memory, _DEFAULT_VM_MEMORY)
        self.assertEqual(vm.arch_efi_bios, ARCH_EFI_BIOS)
        self.assertEqual(vm.address, _DEFAULT_VM_ADDRESS)
        self.assertEqual(vm._image, None)
        self.assertEqual(vm.qemu, 'qemu-system-x86_64')
        self.assertEqual(vm._repos, [])
        self.assertTrue(vm.tmpmode)
        self.assertFalse(vm.copymode)
        self.assertIsNone(vm._vm)
        self.assertIsNone(vm._tmpimg)

        # arch specific
        self.config.set('arch', ['aarch64'])
        vm = VM(self.config, 'aarch64')
        self.assertEqual(vm.arch, 'aarch64')
        self.assertEqual(vm.cpu_type, 'cortex-a72')

        vm_custom_memory = 4096

        # custom
        self.config.set('arch', ['aarch64'])
        self.config.set(
            'vm',
            {
                'cpu': 'custom',
                'cpus': 32,
                'memory': vm_custom_memory,
                'image_copy': 1,
                'address': '192.168.0.5',
                'image': '/my_image',
            }
        )
        self.config.set('arch_efi_bios', '/my_bios')
        self.config.set('qemu', '/my_custom_qemu')

        vm = VM(self.config, 'aarch64')
        self.assertEqual(vm.arch, 'aarch64')
        self.assertEqual(vm.cpu_type, 'custom')
        self.assertEqual(vm.cpus, 32)
        self.assertEqual(vm.memory, vm_custom_memory)
        self.assertEqual(vm.arch_efi_bios, '/my_bios')
        self.assertEqual(vm.address, '192.168.0.5')
        self.assertEqual(vm._image, '/my_image')
        self.assertEqual(vm.qemu, '/my_custom_qemu')
        self.assertTrue(vm.port >= _DEFAULT_VM_PORT_RANGE_MIN)
        self.assertTrue(vm.port <= _DEFAULT_VM_PORT_RANGE_MAX)
        self.assertTrue(vm.copymode)
        self.assertIsNone(vm._vm)
        self.assertIsNone(vm._tmpimg)
        # Check VM unique ID is a hash of 40 chars
        self.assertEqual(len(vm.vmid), 40)

    def test_vmid(self):
        """Check VM ID stability an uniqueness"""
        # Declare 2 supported architectures for this test
        self.config.set('arch', ['x86_64', 'aarch64'])
        # 2 successive calls to id property with same object must return the
        # same value.
        vm1 = VM(self.config, 'x86_64')
        self.assertEqual(vm1.vmid, vm1.vmid)
        vm2 = VM(self.config, 'aarch64')
        self.assertEqual(vm2.vmid, vm2.vmid)
        # Verify vm1 and vm2 ID are different due because of their different
        # architecture.
        self.assertNotEqual(vm1.vmid, vm2.vmid)
        # Get another vm object with the same architecture (and user/version)
        # than vm1 and check it has the same ID.
        vm3 = VM(self.config, 'x86_64')
        self.assertEqual(vm1.vmid, vm3.vmid)
        # Change version for vm3 and check ID is now different of vm1.
        self.config.set('version', '2.0')
        vm3 = VM(self.config, 'x86_64')
        self.assertNotEqual(vm1.vmid, vm3.vmid)

    def test_default_port(self):
        """Check VM default port uniqueness and range conformity"""
        # Declare 2 supported architectures for this test
        self.config.set('arch', ['x86_64', 'aarch64'])
        vm1 = VM(self.config, 'x86_64')
        vm2 = VM(self.config, 'aarch64')
        vm3 = VM(self.config, 'x86_64')
        port_range = {'min': 2000,  'max': 3000}
        # Verify vm1 and vm2 default are different because of their different
        # architecture.
        self.assertNotEqual(
            vm1.default_port(port_range),
            vm2.default_port(port_range)
        )
        # Verify vm1 and vm3 have the same default port because they share the
        # same combination of user/arch/version.
        self.assertEqual(
            vm1.default_port(port_range),
            vm3.default_port(port_range)
        )
        # Verify both default ports are included in range
        self.assertTrue(vm1.default_port(port_range) >= port_range['min'])
        self.assertTrue(vm1.default_port(port_range) < port_range['max'])
        self.assertTrue(vm2.default_port(port_range) >= port_range['min'])
        self.assertTrue(vm2.default_port(port_range) < port_range['max'])

    def test_default_port_invalid_range(self):
        """Check VM default port raise error with invalid range"""
        vm1 = VM(self.config, 'x86_64')
        port_range = {'min': 2001,  'max': 2000}
        with self.assertRaisesRegex(
            RiftError,
            "^VM port range maximum must be greater than the minimum$"
        ):
            vm1.default_port(port_range)

    def test_gen_virtiofs_args(self):
        """
        Check virtiofsd args generator
        """
        # test default values non qemu mode
        args = gen_virtiofs_args('/socket', '/source', False)
        self.assertEqual(args, [_DEFAULT_VIRTIOFSD, '--socket-path', '/socket',
                                '--sandbox=none', '--shared-dir', '/source',
                                '--cache', 'auto'])
        # test default values qemu mode
        args = gen_virtiofs_args('/socket', '/source', True)
        self.assertEqual(args, ['sudo', _DEFAULT_VIRTIOFSD,
                                '--socket-path=/socket',
                                '-o', 'source=/source',
                                '-o', 'cache=auto', '--syslog', '--daemonize'])
        # test custom values
        args = gen_virtiofs_args('/socket', '/source', False, '/virtiofsd')
        self.assertEqual(args, ['/virtiofsd', '--socket-path', '/socket',
                               '--sandbox=none', '--shared-dir', '/source',
                               '--cache', 'auto'])

    def test_make_drive_cmd_nine_p(self):
        """
        Check drive command line generation for 9p
        """
        vm = VM(self.config, None)

        # Test 9p configuration without any repos
        vm.shared_fs_type = '9p'
        vm._project_dir = '/somewhere'
        args, helper_args = vm._make_drive_cmd()
        nine_p_args = ['-virtfs',
                       f"local,id=project,path={vm._project_dir},mount_tag=project,"
                       'security_model=none']
        self.assertEqual(args, nine_p_args)
        self.assertEqual(helper_args, [])

        # Test 9p configuration with repos
        # Use ConsumableRepostory to avoid any createrepo stuff in tests
        reponame = 'custom'
        vm._repos = [
            ConsumableRepository(url='/tmp', name=reponame)
        ]

        repo_args = ['-virtfs',
                     f'local,id={reponame},path=/tmp,mount_tag={reponame},security_model=none']

        args, helper_args = vm._make_drive_cmd()
        self.assertEqual(args, nine_p_args + repo_args)
        self.assertEqual(helper_args, [])

    def test_make_drive_cmd_vitiofs(self):
        """
        Check drive command line generation for virtiofs
        """
        vm = VM(self.config, platform.machine())
        # Test virtiofs configuration without any repos
        vm.shared_fs_type = 'virtiofs'
        vm._project_dir = '/somewhere/else'
        args, helper_args = vm._make_drive_cmd()
        virtiofs_same_arch = ['-object',
                              f'memory-backend-file,id=mem,size={str(vm.memory)}M,'
                              'mem-path=/tmp,share=on',
                              '-machine', 'memory-backend=mem,accel=kvm',
                              '-chardev',
                              'socket,id=project,path=/tmp/.virtio_fs_project',
                              '-device',
                              'vhost-user-fs-pci,queue-size=1024,chardev=project,'
                              'tag=project']
        self.assertEqual(args, virtiofs_same_arch)
        self.assertNotEqual(helper_args, [])
        vm.arch = 'not_the_same_arch'
        args, helper_args = vm._make_drive_cmd()
        virtiofs_diff_arch = ['-object',
                              f'memory-backend-file,id=mem,size={str(vm.memory)}M,'
                              'mem-path=/tmp,share=on',
                              '-machine', 'memory-backend=mem',
                              '-chardev',
                              'socket,id=project,path=/tmp/.virtio_fs_project',
                              '-device',
                              'vhost-user-fs-pci,queue-size=1024,chardev=project,'
                              'tag=project']
        self.assertEqual(args, virtiofs_diff_arch)
        # Content of helper_args is not tested here see test_gen_virtiofs_args
        self.assertNotEqual(helper_args, [])

        # Test virtiofs configuration with repos
        # Use ConsumableRepostory to avoid any createrepo stuff in tests
        reponame = 'custom'
        vm._repos = [
            ConsumableRepository(url='/tmp', name=reponame)
        ]

        repo_args = ['-chardev',
                     f'socket,id={reponame},path=/tmp/.virtio_fs_{reponame}',
                     '-device',
                     f'vhost-user-fs-pci,queue-size=1024,chardev={reponame},'
                     f'tag={reponame}']
        args, helper_args = vm._make_drive_cmd()
        self.assertEqual(args, virtiofs_diff_arch + repo_args)
        # Content of helper_args is not tested here see test_gen_virtiofs_args
        self.assertNotEqual(helper_args, [])

    def test_make_drive_cmd_unexisting_repo(self):
        """
        Check drive command line generation raise error when file repository does not exist
        """
        vm = VM(self.config, None)
        vm._repos = [ConsumableRepository("file:///fail")]
        # test for all supported shared FS types
        for shared_fs_type in ['9p', 'virtiofs']:
            vm.shared_fs_type = shared_fs_type
            with self.assertRaisesRegex(
                RiftError,
                '^Repository /fail does not exist, unable to start VM$'
            ):
                vm._make_drive_cmd()


    def test_gen_qemu_args(self):
        """
        Check qemu args generator
        """
        vm = VM(self.config, platform.machine())
        vm.consolesock = '/console'
        image_path = '/my_image'
        # Test without seed iso path
        args = vm._gen_qemu_args(image_path, None)
        expected_args = [ vm.qemu, '-enable-kvm', '-cpu', vm.cpu_type,
                          '-name', 'rift', '-display', 'none',
                          '-m', str(vm.memory), '-smp', str(vm.cpus),
                          '-drive',
                          f"file={image_path},if=virtio,format=qcow2,cache=unsafe",
                          '-chardev', f"socket,id=charserial0,path={vm.consolesock},"
                          'server=on,wait=off',
                          '-device', 'isa-serial,chardev=charserial0,id=serial0',
                          '-netdev', f"user,id=hostnet0,hostname={vm.NAME},"
                          f"hostfwd=tcp::{vm.port}-:22",
                          '-device',
                          'virtio-net-pci,netdev=hostnet0,bus=pci.0,addr=0x3']
        self.assertEqual(args, expected_args)
        # Test with seed iso path
        args = vm._gen_qemu_args(image_path, "/path/to/seed/iso")
        self.assertEqual(
            args,
            expected_args
            + ['-drive', f"driver=raw,file=/path/to/seed/iso,if=virtio"]
        )
        # Test with another arch
        vm.arch = 'aarch64'
        args = vm._gen_qemu_args(image_path, None)
        expected_args_aarch64 = [ vm.qemu, '-machine', 'virt', '-cpu', vm.cpu_type,
                          '-name', 'rift', '-display', 'none',
                          '-m', str(vm.memory), '-smp', str(vm.cpus),
                          '-bios', vm.arch_efi_bios,
                          '-drive',
                          f"file={image_path},if=virtio,format=qcow2,cache=unsafe",
                          '-chardev', f"socket,id=charserial0,path={vm.consolesock},"
                          'server=on,wait=off',
                          '-device', 'virtio-serial,id=ser0,max_ports=8',
                          '-serial', 'chardev:charserial0',
                          '-netdev', f"user,id=hostnet0,hostname={vm.NAME},"
                          f"hostfwd=tcp::{vm.port}-:22",
                          '-device',
                          'virtio-net-device,netdev=hostnet0']
        self.assertEqual(args, expected_args_aarch64)

    @patch('rift.VM.message')
    def test_start(self, mock_message):
        """Test VM start not running"""
        vm = VM(self.config, platform.machine())
        vm.running = Mock(return_value=False)
        vm.spawn = Mock()
        vm.ready = Mock()
        vm.prepare = Mock()
        self.assertTrue(vm.start())
        mock_message.assert_called_once_with("Launching VM ...")
        vm.spawn.assert_called_once()
        vm.ready.assert_called_once()
        vm.prepare.assert_called_once()

    @patch('rift.VM.message')
    def test_start_running(self, mock_message):
        """Test VM start already running"""
        vm = VM(self.config, platform.machine())
        vm.running = Mock(return_value=True)
        vm.spawn = Mock()
        vm.ready = Mock()
        vm.prepare = Mock()
        self.assertFalse(vm.start())
        mock_message.assert_called_once_with("VM is already running")
        vm.spawn.assert_not_called()
        vm.ready.assert_not_called()
        vm.prepare.assert_not_called()

class VMBuildTest(RiftProjectTestCase):
    """
    Test case for VM build() method
    """

    def setUp(self):
        super().setUp()
        # Override some configuration parameters defined in dummy config from
        # RiftProjectTestCase.
        self.config.options['vm']['images_cache'] = GLOBAL_CACHE
        self.config.options['proxy'] = PROXY
        self.wrong_url = 'https://127.0.0.1/fail'
        self.valid_url = VALID_IMAGE_URL['x86_64']
        self.copy_cloud_init_tpl()
        self.ensure_vm_images_cache_dir()

    def _check_qemuimg(self):
        """Check presence of qemu-img executable or skip current test."""
        if not os.path.exists("/usr/bin/qemu-img"):
            self.skipTest("qemu-img is not available")

    def test_build_missing_cache_dir(self):
        """Test VM build with missing cache directory"""
        vm = VM(self.config, 'x86_64')
        vm.images_cache = 'non-existent-directory'
        self.assertFalse(os.path.exists(vm.images_cache))
        with self.assertRaisesRegex(
            RiftError,
            f"^Cloud images cache directory {vm.images_cache} does not "
            "exist$",
        ):
            vm.build(self.valid_url, False, False, vm._image)

    def test_build_wrong_url(self):
        """Test VM build with URL error"""
        vm = VM(self.config, 'x86_64')
        with self.assertRaisesRegex(
            RiftError,
            f"^URL error while downloading {self.wrong_url}: .*$",
        ):
            vm.build(self.wrong_url, False, False, vm._image)
        with self.assertRaisesRegex(
            RiftError,
            f"^HTTP error while downloading {self.valid_url}.unfound: HTTP "
            "Error 404: Not Found$",
        ):
            vm.build(
                self.valid_url + '.unfound', False, False, vm._image
            )

    def test_build_missing_cloudinit_tpl(self):
        """Test VM build with missing cloud-init template"""
        vm = VM(self.config, 'x86_64')
        os.unlink(vm.cloud_init_tpl)
        with self.assertRaisesRegex(
            RiftError,
            "^Unable to find cloud-init template file "
            f"{vm.cloud_init_tpl}$",
        ):
            vm.build(self.valid_url, False, False, vm._image)

    def test_build_ok(self):
        """Test VM basic build"""
        self._check_qemuimg()
        vm = VM(self.config, 'x86_64')
        vm.build(self.valid_url, False, False, vm._image)
        self.assertEqual(os.path.exists(vm._image), True)

    def test_build_ok_copymode(self):
        """Test VM build OK with copymode enabled"""
        vm = VM(self.config, 'x86_64')
        vm.copymode = 1
        vm.build(self.valid_url, False, False, vm._image)
        self.assertEqual(os.path.exists(vm._image), True)

    @patch('rift.VM.input')
    def test_build_overwrite(self, mock_input):
        """Test VM build overwrite"""
        self._check_qemuimg()
        vm = VM(self.config, 'x86_64')
        # create empty output image
        open(vm._image, 'w').close()
        mock_input.side_effect = 'yes'
        vm.build(self.valid_url, False, False, vm._image)
        self.assertEqual(os.path.exists(vm._image), True)
        mock_input.assert_called_once()

    def test_build_with_build_script(self):
        """Test VM build with build script"""
        self._check_qemuimg()
        vm = VM(self.config, 'x86_64')
        with open(vm.build_post_script, 'w') as fh:
            fh.write("#!/bin/bash\n/bin/true\n")
        vm.build(self.valid_url, False, False, vm._image)
        self.assertEqual(os.path.exists(vm._image), True)

    def test_build_with_build_script_error(self):
        """Test VM build with build script error"""
        self._check_qemuimg()
        vm = VM(self.config, 'x86_64')
        with open(vm.build_post_script, 'w') as fh:
            fh.write("#!/bin/bash\n/bin/false\n")
        with self.assertRaisesRegex(
            RiftError, f"^Error while running build post script$"
        ):
            vm.build(self.valid_url, False, False, vm._image)
        vm.stop()

    def test_build_aarch64(self):
        """Test VM build aarch64"""
        self._check_qemuimg()
        self.config.set('arch', ['aarch64'])
        vm = VM(self.config, 'aarch64')
        vm.arch_efi_bios = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            '..', 'vendor', 'QEMU_EFI.silent.fd'
        )
        self.valid_url = VALID_IMAGE_URL[vm.arch]
        vm.build(self.valid_url, False, False, vm._image)
