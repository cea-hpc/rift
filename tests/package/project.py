#
# Copyright (C) 2025 CEA
#

import os

from rift.Config import Config
from rift.package._virtual import PackageVirtual
from rift.package.rpm import PackageRPM
from rift.package.oci import PackageOCI
from rift.package import ProjectPackages
from ..TestUtils import RiftProjectTestCase


class ProjectPackagesTest(RiftProjectTestCase):
    """
    Tests class for ProjectPackages
    """
    def fill_project_dir(self, packages):
        open(os.path.join(self.projdir, Config._DEFAULT_FILES[0]), 'a').close()
        packages_dir = os.path.join(self.projdir, self.config.get('packages_dir'))
        for package, formats in packages.items():
            os.mkdir(os.path.join(packages_dir, package))
            if 'rpm' in formats:
                open(os.path.join(packages_dir, package, f"{package}.spec"), 'a').close()
            if 'oci' in formats:
                open(os.path.join(packages_dir, package, 'Containerfile'), 'a').close()

    def test_list(self):
        """ Test ProjectPackages list() """
        packages_names = {'foo': ['rpm'], 'bar': ['oci']}
        self.fill_project_dir(packages_names)
        packages = list(ProjectPackages.list(self.config, self.staff, self.modules))
        self.assertEqual(len(packages), 2)
        for package in packages:
            self.assertIn(package.name, packages_names)
            if package.name == 'foo':
                self.assertIsInstance(package, PackageRPM)
            elif package.name == 'bar':
                self.assertIsInstance(package, PackageOCI)

    def test_list_empty(self):
        """ Test ProjectPackages list() empty """
        self.fill_project_dir({})
        self.assertCountEqual(ProjectPackages.list(self.config, self.staff, self.modules), [])

    def test_list_with_names(self):
        """ Test ProjectPackages list() with names"""
        packages_names = {'foo': ['rpm'], 'bar': ['rpm'], 'baz': ['oci']}
        list_names = ['bar', 'baz', 'fail']
        self.fill_project_dir(packages_names)
        packages = list(ProjectPackages.list(self.config, self.staff, self.modules, list_names))
        self.assertEqual(len(packages), 3)
        for package in packages:
            self.assertIn(package.name, list_names)
            if package.name == 'bar':
                self.assertIsInstance(package, PackageRPM)
            elif package.name == 'baz':
                self.assertIsInstance(package, PackageOCI)
            else:
                self.assertIsInstance(package, PackageVirtual)

    def test_get_virtual(self):
        """ Test ProjectPackages get() virtual package"""
        packages = ProjectPackages.get('pkg', self.config, self.staff, self.modules)
        self.assertIsInstance(packages, list)
        self.assertEqual(len(packages), 1)
        self.assertIsInstance(packages[0], PackageVirtual)
        self.assertEqual(packages[0].name, 'pkg')

    def test_get_rpm(self):
        """ Test ProjectPackages get() RPM package"""
        self.fill_project_dir({'pkg': ['rpm']})
        packages = ProjectPackages.get('pkg', self.config, self.staff, self.modules)
        self.assertIsInstance(packages, list)
        self.assertEqual(len(packages), 1)
        self.assertIsInstance(packages[0], PackageRPM)
        self.assertEqual(packages[0].name, 'pkg')

    def test_get_oci(self):
        """ Test ProjectPackages get() OCI package"""
        self.fill_project_dir({'pkg': ['oci']})
        packages = ProjectPackages.get('pkg', self.config, self.staff, self.modules)
        self.assertIsInstance(packages, list)
        self.assertEqual(len(packages), 1)
        self.assertIsInstance(packages[0], PackageOCI)
        self.assertEqual(packages[0].name, 'pkg')

    def test_get_multiformats(self):
        """ Test ProjectPackages get() multiformats package"""
        self.fill_project_dir({'pkg': ['rpm', 'oci']})
        packages = ProjectPackages.get('pkg', self.config, self.staff, self.modules)
        self.assertIsInstance(packages, list)
        self.assertEqual(len(packages), 2)
        # Check there is one RPM and one OCI in list
        self.assertEqual([isinstance(package, PackageRPM) for package in packages].count(True), 1)
        self.assertEqual([isinstance(package, PackageOCI) for package in packages].count(True), 1)
        for package in packages:
            self.assertEqual(package.name, 'pkg')
