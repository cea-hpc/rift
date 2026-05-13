#
# Copyright (C) 2025 CEA
#
import os
import shutil
import io
from unittest.mock import patch

from rift.graph import PackagesDependencyGraph
from rift.package.rpm import PackageRPM
from rift.package.oci import PackageOCI

from .TestUtils import RiftProjectTestCase, SubPackage, read_file


class GraphTest(RiftProjectTestCase):
    """
    Tests class for PackageDependencyGraph
    """
    def test_one_package(self):
        """ Test graph with one package """
        pkg_name = 'fake'
        self.make_pkg(name=pkg_name)
        package_rpm = PackageRPM(pkg_name, self.config, self.staff, self.modules)
        package_oci = PackageOCI(pkg_name, self.config, self.staff, self.modules)
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        # 1 package in 2 formats → 2 nodes expected in the graph
        self.assertEqual(len(graph.nodes), 2)

        # Solve with RPM package
        build_requirements = graph.solve(package_rpm)
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageRPM)
        self.assertEqual(build_requirements[0].package.name, package_rpm.name)
        self.assertEqual(build_requirements[0].reasons, ["User request"])

        # Solve with OCI package
        build_requirements = graph.solve(package_oci)
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageOCI)
        self.assertEqual(build_requirements[0].package.name, package_oci.name)
        self.assertEqual(build_requirements[0].reasons, ["User request"])

    def test_one_package_one_format(self):
        """ Test graph with one package in one format"""
        pkg_name = 'fake'
        self.make_pkg(name=pkg_name, formats=['rpm'])
        package_rpm = PackageRPM(pkg_name, self.config, self.staff, self.modules)
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        # 1 package in 1 format → 1 node expected in the graph
        self.assertEqual(len(graph.nodes), 1)

        # Solve with RPM package
        build_requirements = graph.solve(package_rpm)
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageRPM)
        self.assertEqual(build_requirements[0].package.name, package_rpm.name)
        self.assertEqual(build_requirements[0].reasons, ["User request"])

    def test_one_package_build_format_filter(self):
        """ Test graph with one package and format filter """
        pkg_name = 'fake'
        self.make_pkg(name=pkg_name)
        package_oci = PackageOCI(pkg_name, self.config, self.staff, self.modules)
        graph = PackagesDependencyGraph.from_project(
            self.config,
            self.staff,
            self.modules,
            formats=['oci']
        )
        # 1 package in 2 formats but format filder → 1 node expected in the graph
        self.assertEqual(len(graph.nodes), 1)

        # Solve with OCI package
        build_requirements = graph.solve(package_oci)
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageOCI)
        self.assertEqual(build_requirements[0].package.name, package_oci.name)
        self.assertEqual(build_requirements[0].reasons, ["User request"])

    def test_packages_unable_load(self):
        """ Test graph build with package unable to load """
        pkgs_names = ['success', 'failed']
        packages = {}
        for pkg_name in pkgs_names:
            self.make_pkg(name=pkg_name)
            packages[pkg_name] = PackageRPM(
                pkg_name, self.config, self.staff, self.modules
            )
        # Remove info.yaml in packages failed to generate error
        os.unlink(packages['failed'].metafile)
        # Build packages graph
        with self.assertLogs(level='WARNING') as cm:
            # mock Mock.read_spec to return spec file content directly read on host
            with patch('rift.package.rpm.Mock') as mock_mock:
                mock_mock.return_value.read_spec = read_file
                graph = PackagesDependencyGraph.from_project(
                    self.config,
                    self.staff,
                    self.modules
                )
        # Check warning message have been emitted. Error should appear twice,
        # once for each package supported format.
        self.assertCountEqual(
            cm.output,
            [
                "WARNING:root:Skipping package 'failed' unable to load: [Errno 2]"
                " No such file or directory: "
                f"'{self.projdir}/packages/failed/info.yaml'",
                "WARNING:root:Skipping package 'failed' unable to load: [Errno 2]"
                " No such file or directory: "
                f"'{self.projdir}/packages/failed/info.yaml'",
            ]
        )
        # Check success package is successfully loaded anyway.
        # (2 formats → 2 nodes expected in the graph).
        self.assertEqual(len(graph.nodes), 2)
        for node in graph.nodes:
            self.assertEqual(node.package.name, 'success')

    def test_dump(self):
        """ Test graph dump """
        pkg_name = 'fake'
        self.make_pkg(name=pkg_name)
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        with self.assertLogs(level='INFO') as cm:
            graph.dump()
        self.assertEqual(
            cm.output,
            [
                'INFO:root:→ rpm:fake',
                "INFO:root:  provides: ['fake', 'fake-provide']",
                "INFO:root:  requires: ['br-package']",
                'INFO:root:  is required by: []',
                'INFO:root:→ oci:fake',
                "INFO:root:  provides: ['fake']",
                "INFO:root:  requires: []",
                'INFO:root:  is required by: []'
            ]
        )

    def test_empty_solve(self):
        """ Test solve with package not in graph """
        pkg_name = 'one'
        self.make_pkg(name=pkg_name)
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        package = PackageRPM('another', self.config, self.staff, self.modules)
        build_requirements = graph.solve(package)
        self.assertEqual(len(build_requirements), 0)

    def test_multiple_packages(self):
        """ Test graph with multiple packages and dependencies in info.yaml """
        # Define 3 packages with depends in info.yaml, in both string and list
        # formats.
        self.make_pkg(
            name='libone',
            metadata={
                'depends': 'libtwo'
            }
        )
        self.make_pkg(
            name='libtwo',
        )
        self.make_pkg(
            name='my-software',
            metadata={
                'depends': ['libone']
            }
        )

        # Load graph
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        # 3 packages x 2 formats → 6 nodes expected in the graph
        self.assertEqual(len(graph.nodes), 6)

        # Rebuild of my-software does not trigger rebuild of other packages.
        for package_class in (PackageRPM, PackageOCI):
            build_requirements = graph.solve(
                package_class('my-software', self.config, self.staff, self.modules)
            )
            self.assertEqual(len(build_requirements), 1)
            self.assertIsInstance(build_requirements[0].package, package_class)
            self.assertEqual(build_requirements[0].package.name, 'my-software')
            self.assertEqual(build_requirements[0].reasons, ["User request"])

        # Rebuild of libone triggers rebuild of my-software because it depends
        # on libone.
        for package_class in (PackageRPM, PackageOCI):
            build_requirements = graph.solve(
                package_class('libone', self.config, self.staff, self.modules)
            )
            self.assertEqual(len(build_requirements), 2)
            for build_requirement in build_requirements:
                self.assertIsInstance(build_requirement.package, package_class)
            self.assertEqual(build_requirements[0].package.name, 'libone')
            self.assertEqual(build_requirements[0].reasons, ["User request"])
            self.assertEqual(build_requirements[1].package.name, 'my-software')
            self.assertEqual(
                build_requirements[1].reasons,
                [f"depends on {build_requirements[1].package.format}:libone"],
            )

        # Rebuild of libtwo triggers rebuild of:
        # - libone because it depends on libtwo
        # - my-software because it depends on libone
        for package_class in (PackageRPM, PackageOCI):
            build_requirements = graph.solve(
                package_class('libtwo', self.config, self.staff, self.modules)
            )
            self.assertEqual(len(build_requirements), 3)
            for build_requirement in build_requirements:
                self.assertIsInstance(build_requirement.package, package_class)
            self.assertEqual(build_requirements[0].package.name, 'libtwo')
            self.assertEqual(build_requirements[0].reasons, ["User request"])
            self.assertEqual(build_requirements[1].package.name, 'libone')
            self.assertEqual(
                build_requirements[1].reasons,
                [f"depends on {build_requirement.package.format}:libtwo"],
            )
            self.assertEqual(build_requirements[2].package.name, 'my-software')
            self.assertEqual(
                build_requirements[2].reasons,
                [f"depends on {build_requirement.package.format}:libone"],
            )

    def test_multiple_packages_spec_fallback(self):
        """ Test graph with multiple packages and dependencies in RPM spec files """
        # Define 3 packages without depends in info.yaml but with build requires
        # on others subpackages.
        self.make_pkg(
            name='libone',
            build_requires=['libtwo-devel >= 3.5'],
            subpackages=[
                SubPackage('libone-bin'),
                SubPackage('libone-devel')
            ]
        )
        self.make_pkg(
            name='libtwo',
            subpackages=[
                SubPackage('libtwo-bin'),
                SubPackage('libtwo-devel')
            ]
        )
        self.make_pkg(
            name='my-software',
            build_requires=['libone-devel = 3, libtwo-devel'],
        )

        def load_graph():
            # mock Mock.read_spec to return spec file content directly read on host
            with patch('rift.package.rpm.Mock') as mock_mock:
                mock_mock.return_value.read_spec = read_file
                graph = PackagesDependencyGraph.from_project(
                    self.config,
                    self.staff,
                    self.modules
                )
            self.assertEqual(len(graph.nodes), 6)
            return graph

        graph = load_graph()

        # Rebuild of my-software does not trigger rebuild of other packages.
        for package_class in (PackageRPM, PackageOCI):
            build_requirements = graph.solve(
                package_class('my-software', self.config, self.staff, self.modules)
            )
            self.assertEqual(len(build_requirements), 1)
            self.assertIsInstance(build_requirements[0].package, package_class)
            self.assertEqual(build_requirements[0].package.name, 'my-software')
            self.assertEqual(build_requirements[0].reasons, ["User request"])

        # Rebuild of RPM libone triggers rebuild of my-software because
        # my-software build requires on one of libone subpackage.
        build_requirements = graph.solve(
            PackageRPM('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 2)
        for build_requirement in build_requirements:
            self.assertIsInstance(build_requirement.package, PackageRPM)
        self.assertEqual(build_requirements[0].package.name, 'libone')
        self.assertEqual(build_requirements[0].reasons, ["User request"])
        self.assertEqual(build_requirements[1].package.name, 'my-software')
        self.assertEqual(
            build_requirements[1].reasons,
            ["build depends on rpm:libone-devel"]
        )

        # However, rebuild of OCI libone does not trigger rebuild other rebuild
        # because build requirements are expressed in RPM spec file only.
        build_requirements = graph.solve(
            PackageOCI('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageOCI)
        self.assertEqual(build_requirements[0].package.name, 'libone')
        self.assertEqual(build_requirements[0].reasons, ["User request"])


        # Rebuild of RPM libtwo triggers rebuild of libone and my-software
        # because:
        # - libone build requires on one of libtwo subpackage
        # - my-software build requires on one of libtwo subpackage and on one
        #   of libone subpackage.
        build_requirements = graph.solve(
            PackageRPM('libtwo', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 3)
        for build_requirement in build_requirements:
            self.assertIsInstance(build_requirement.package, PackageRPM)
        self.assertEqual(build_requirements[0].package.name, 'libtwo')
        self.assertEqual(build_requirements[0].reasons, ["User request"])
        self.assertEqual(build_requirements[1].package.name, 'libone')
        self.assertEqual(
            build_requirements[1].reasons,
            ["build depends on rpm:libtwo-devel"]
        )
        self.assertEqual(build_requirements[2].package.name, 'my-software')
        self.assertCountEqual(
            build_requirements[2].reasons,
            [
                "build depends on rpm:libone-devel",
                "build depends on rpm:libtwo-devel"
            ]
        )

        # However, rebuild of OCI libtwo does not trigger rebuild other rebuild
        # because build requirements are expressed in RPM spec file only.
        build_requirements = graph.solve(
            PackageOCI('libtwo', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageOCI)
        self.assertEqual(build_requirements[0].package.name, 'libtwo')
        self.assertEqual(build_requirements[0].reasons, ["User request"])

        # Remove my-software package directory, redefine my-software package
        # with dependencies in info.yaml and reload the graph.
        shutil.rmtree(self.pkgdirs['my-software'])
        self.make_pkg(
            name='my-software',
            build_requires=['libone-devel, libtwo-devel'],
            metadata={
                'depends': ['libtwo']
            }
        )
        graph = load_graph()

        # Rebuild of libone MUST NOT trigger rebuild of my-software anymore
        # because my-software dependencies defined in info.yaml now overrides
        # build requires in RPM spec file.
        build_requirements = graph.solve(
            PackageRPM('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageRPM)

    def test_multiple_packages_with_provides(self):
        """ Test graph with multiple packages and dependencies on provides in RPM spec files """
        # Define 2 packages without depends in info.yaml but with build requires
        # on other subpackages provides.
        self.make_pkg(
            name='libone',
            subpackages=[
                SubPackage('libone-bin'),
                SubPackage('libone-devel')
            ]
        )
        self.make_pkg(
            name='my-software',
            build_requires=['libone-provide = 3'],
        )

        def load_graph():
            # mock Mock.read_spec to return spec file content directly read on host
            with patch('rift.package.rpm.Mock') as mock_mock:
                mock_mock.return_value.read_spec = read_file
                graph = PackagesDependencyGraph.from_project(
                    self.config,
                    self.staff,
                    self.modules
                )
            # 2 packages x 2 formats → 4 nodes expected in the graph
            self.assertEqual(len(graph.nodes), 4)
            return graph

        graph = load_graph()

        # Rebuild of libone triggers rebuild of my-software because my-software
        # build requires on one of libone subpackage provides.
        build_requirements = graph.solve(
            PackageRPM('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 2)
        for build_requirement in build_requirements:
            self.assertIsInstance(build_requirement.package, PackageRPM)
        self.assertEqual(build_requirements[0].package.name, 'libone')
        self.assertEqual(build_requirements[0].reasons, ["User request"])
        self.assertEqual(build_requirements[1].package.name, 'my-software')
        self.assertEqual(
            build_requirements[1].reasons,
            ["build depends on rpm:libone-provide"]
        )

        # However, rebuild of OCI libone does not trigger rebuild other rebuild
        # because provides are expressed in RPM spec file only.
        build_requirements = graph.solve(
            PackageOCI('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 1)
        self.assertIsInstance(build_requirements[0].package, PackageOCI)
        self.assertEqual(build_requirements[0].package.name, 'libone')
        self.assertEqual(build_requirements[0].reasons, ["User request"])

    def test_loop(self):
        """ Test graph solve with dependency loop """
        # Define 3 packages with a dependency loop.
        self.make_pkg(
            name='libone',
            metadata={
                'depends': 'libtwo'
            }
        )
        self.make_pkg(
            name='libtwo',
            metadata={
                'depends': 'libthree'
            }
        )
        self.make_pkg(
            name='libthree',
            metadata={
                'depends': 'libone'
            }
        )

        # Load graph
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        # 3 packages x 2 formats → 6 nodes expected in the graph
        self.assertEqual(len(graph.nodes), 6)

        # For all three package, the resolution should return all three
        # build requirements (in RPM and OCI format).
        for package in ['libone', 'libtwo', 'libthree']:
            for package_class in (PackageRPM, PackageOCI):
                build_requirements = graph.solve(
                    package_class(package, self.config, self.staff, self.modules)
                )
                for build_requirement in build_requirements:
                    self.assertIsInstance(build_requirement.package, package_class)
                self.assertEqual(len(build_requirements), 3)

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_draw(self, mock_stdout):
        """ Test graph draw """
        # Define 3 packages with depends in info.yaml, in both string and list
        # formats.
        self.make_pkg(
            name='libone',
            metadata={
                'depends': 'libtwo'
            }
        )
        self.make_pkg(
            name='libtwo',
        )
        self.make_pkg(
            name='my-software',
            metadata={
                'depends': ['libone']
            }
        )

        # Load graph
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        graph.draw(False, [])  # w/o external deps
        output = mock_stdout.getvalue()

        # Check all packages are declared as nodes (with their labels) in graph.
        for package in ['libone', 'libtwo', 'my-software']:
            self.assertTrue(
                f"\"rpm:{package}\" [ label = " in output
            )
            self.assertTrue(
                f"\"oci:{package}\" [ label = " in output
            )
        # Check depedencies are represented in graph.
        self.assertTrue('"rpm:my-software" -> "rpm:libone"' in output)
        self.assertTrue('"rpm:libone" -> "rpm:libtwo"' in output)
        self.assertFalse('"rpm:libtwo" -> "rpm:my-software"' in output)
        self.assertTrue('"oci:my-software" -> "oci:libone"' in output)
        self.assertTrue('"oci:libone" -> "oci:libtwo"' in output)
        self.assertFalse('"oci:libtwo" -> "oci:my-software"' in output)

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_draw_packages_subset(self, mock_stdout):
        """ Test graph draw a subset of packages"""
        # Define 3 packages with depends in info.yaml, in both string and list
        # formats.
        self.make_pkg(
            name='libone',
            metadata={
                'depends': 'libtwo'
            }
        )
        self.make_pkg(
            name='libtwo',
        )
        self.make_pkg(
            name='my-software',
            metadata={
                'depends': ['libone']
            }
        )

        # Load graph
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        graph.draw(False, ['libone'])  # only libone and its deps
        output = mock_stdout.getvalue()

        # Check libone and its dependency libtwo are declared as nodes in the
        # graph.
        for package in ['libone', 'libtwo']:
            self.assertTrue(
                f"\"rpm:{package}\" [ label = " in output
            )
            self.assertTrue(
                f"\"oci:{package}\" [ label = " in output
            )
        # Check depedencies are represented in graph.
        self.assertTrue('"rpm:libone" -> "rpm:libtwo"' in output)
        self.assertTrue('"oci:libone" -> "oci:libtwo"' in output)
        # Check my-software is not mentionned in graph.
        self.assertFalse('rpm:my-software' in output)
        self.assertFalse('oci:my-software' in output)

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_draw_with_external_deps(self, mock_stdout):
        """ Test graph draw with external dependencies """
        # Define 3 packages without depends in info.yaml but with build requires
        # on others subpackages and external dep.
        self.make_pkg(
            name='libone',
            build_requires=['libtwo-devel', 'external-devel'],
            subpackages=[
                SubPackage('libone-bin'),
                SubPackage('libone-devel'),
            ]
        )
        self.make_pkg(
            name='libtwo',
            subpackages=[
                SubPackage('libtwo-bin'),
                SubPackage('libtwo-devel')
            ]
        )
        self.make_pkg(
            name='my-software',
            build_requires=['libone-devel, libtwo-devel', 'external-devel'],
        )

        # Load graph
        # mock Mock.read_spec to return spec file content directly read on host
        with patch('rift.package.rpm.Mock') as mock_mock:
            mock_mock.return_value.read_spec = read_file
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        graph.draw(True, [])  # w/ external deps
        output = mock_stdout.getvalue()

        # Check external RPM packages are declared as nodes (with their labels)
        # in graph.
        self.assertTrue(
                '"rpm:external-devel" [fillcolor=orange]' in output
        )
        # External package must not be present for OCI format as this is a
        # spec/RPM specific notion.
        self.assertFalse(
                '"oci:external-devel" [fillcolor=orange]' in output
        )

        # Check depedencies are represented in graph.
        self.assertTrue('"rpm:my-software" -> "rpm:external-devel"' in output)
        self.assertTrue('"rpm:libone" -> "rpm:external-devel"' in output)
        self.assertFalse('"rpm:libtwo" -> "rpm:external-devel"' in output)
        self.assertFalse('"oci:my-software" -> "oci:external-devel"' in output)
        self.assertFalse('"oci:libone" -> "oci:external-devel"' in output)
        self.assertFalse('"oci:libtwo" -> "oci:external-devel"' in output)
