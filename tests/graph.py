#
# Copyright (C) 2025 CEA
#
import os
import shutil
import io
from unittest.mock import patch

from rift.graph import PackagesDependencyGraph
from rift.package.rpm import PackageRPM
from .TestUtils import RiftProjectTestCase, SubPackage

class GraphTest(RiftProjectTestCase):
    """
    Tests class for PackageDependencyGraph
    """
    def test_one_package(self):
        """ Test graph with one package """
        pkg_name = 'fake'
        self.make_pkg(name=pkg_name)
        package = PackageRPM(pkg_name, self.config, self.staff, self.modules)
        graph = PackagesDependencyGraph.from_project(
            self.config,
            self.staff,
            self.modules
        )
        self.assertEqual(len(graph.nodes), 1)
        build_requirements = graph.solve(package)
        self.assertEqual(len(build_requirements), 1)
        self.assertEqual(build_requirements[0].package.name, package.name)
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
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        # Check warning message has been emitted
        self.assertEqual(
            cm.output,
            [
                "WARNING:root:Skipping package 'failed' unable to load: [Errno 2]"
                " No such file or directory: "
                f"'{self.projdir}/packages/failed/info.yaml'"
            ]
        )
        # Check success package is successfully loaded anyway.
        self.assertEqual(len(graph.nodes), 1)
        self.assertEqual(graph.nodes[0].package.name, 'success')

    def test_packages_spec_error(self):
        """ Test graph build with package with spec error """
        pkgs_names = ['success', 'failed']
        packages = {}
        for pkg_name in pkgs_names:
            self.make_pkg(name=pkg_name)
            packages[pkg_name] = PackageRPM(
                pkg_name, self.config, self.staff, self.modules
            )
        # Insert invalid content in failed package specfile
        with open(packages['failed'].buildfile, 'w') as fh:
            fh.write("invalid content")
        # Build packages graph
        with self.assertLogs(level='WARNING') as cm:
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
        # Check warning message has been emitted
        self.assertEqual(
            cm.output,
            [
                "WARNING:root:Skipping package 'failed' unable to load: "
                f"{self.projdir}/packages/failed/failed.spec: can't parse specfile"
            ]
        )
        # Check success package is successfully loaded anyway.
        self.assertEqual(len(graph.nodes), 1)
        self.assertEqual(graph.nodes[0].package.name, 'success')

    def test_dump(self):
        """ Test graph dump """
        pkg_name = 'fake'
        self.make_pkg(name=pkg_name)
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
                'INFO:root:  is required by: []'
            ]
        )

    def test_empty_solve(self):
        """ Test solve with package not in graph """
        pkg_name = 'one'
        self.make_pkg(name=pkg_name)
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
        graph = PackagesDependencyGraph.from_project(
            self.config,
            self.staff,
            self.modules
        )
        self.assertEqual(len(graph.nodes), 3)

        # Rebuild of my-software does not trigger rebuild of other packages.
        build_requirements = graph.solve(
            PackageRPM('my-software', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 1)
        self.assertEqual(build_requirements[0].package.name, 'my-software')
        self.assertEqual(build_requirements[0].reasons, ["User request"])

        # Rebuild of libone triggers rebuild of my-software because it depends
        # on libone.
        build_requirements = graph.solve(
            PackageRPM('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 2)
        self.assertEqual(build_requirements[0].package.name, 'libone')
        self.assertEqual(build_requirements[0].reasons, ["User request"])
        self.assertEqual(build_requirements[1].package.name, 'my-software')
        self.assertEqual(
            build_requirements[1].reasons,
            ["depends on rpm:libone"],
        )

        # Rebuild of libtwo triggers rebuild of:
        # - libone because it depends on libtwo
        # - my-software because it depends on libone
        build_requirements = graph.solve(
            PackageRPM('libtwo', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 3)
        self.assertEqual(build_requirements[0].package.name, 'libtwo')
        self.assertEqual(build_requirements[0].reasons, ["User request"])
        self.assertEqual(build_requirements[1].package.name, 'libone')
        self.assertEqual(
            build_requirements[1].reasons,
            ["depends on rpm:libtwo"],
        )
        self.assertEqual(build_requirements[2].package.name, 'my-software')
        self.assertEqual(
            build_requirements[2].reasons,
            ["depends on rpm:libone"],
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
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
            self.assertEqual(len(graph.nodes), 3)
            return graph

        graph = load_graph()

        # Rebuild of my-software does not trigger rebuild of other packages.
        build_requirements = graph.solve(
            PackageRPM('my-software', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 1)
        self.assertEqual(build_requirements[0].package.name, 'my-software')
        self.assertEqual(build_requirements[0].reasons, ["User request"])


        # Rebuild of libone triggers rebuild of my-software because my-software
        # build requires on one of libone subpackage.
        build_requirements = graph.solve(
            PackageRPM('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 2)
        self.assertEqual(build_requirements[0].package.name, 'libone')
        self.assertEqual(build_requirements[0].reasons, ["User request"])
        self.assertEqual(build_requirements[1].package.name, 'my-software')
        self.assertEqual(
            build_requirements[1].reasons,
            ["build depends on rpm:libone-devel"]
        )

        # Rebuild of libtwo triggers rebuild of libone and my-software because
        # - libone build requires on one of libtwo subpackage
        # - my-software build requires on one of libtwo subpackage and on one
        #   of libone subpackage.
        build_requirements = graph.solve(
            PackageRPM('libtwo', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 3)
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
        self.assertEqual(
            len(
                graph.solve(
                    PackageRPM('libone', self.config, self.staff, self.modules)
                )
            ),
            1
        )

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
            graph = PackagesDependencyGraph.from_project(
                self.config,
                self.staff,
                self.modules
            )
            self.assertEqual(len(graph.nodes), 2)
            return graph

        graph = load_graph()

        # Rebuild of libone triggers rebuild of my-software because my-software
        # build requires on one of libone subpackage provides.
        build_requirements = graph.solve(
            PackageRPM('libone', self.config, self.staff, self.modules)
        )
        self.assertEqual(len(build_requirements), 2)
        self.assertEqual(build_requirements[0].package.name, 'libone')
        self.assertEqual(build_requirements[0].reasons, ["User request"])
        self.assertEqual(build_requirements[1].package.name, 'my-software')
        self.assertEqual(
            build_requirements[1].reasons,
            ["build depends on rpm:libone-provide"]
        )

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
        graph = PackagesDependencyGraph.from_project(
            self.config,
            self.staff,
            self.modules
        )
        self.assertEqual(len(graph.nodes), 3)

        # For all three package, the resolution should return all three
        # build requirements.
        for package in ['libone', 'libtwo', 'libthree']:
            self.assertEqual(
                len(
                    graph.solve(
                        PackageRPM(package, self.config, self.staff, self.modules)
                    )
                ),
                3
            )

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
        # Check depedencies are represented in graph.
        self.assertTrue('"rpm:my-software" -> "rpm:libone"' in output)
        self.assertTrue('"rpm:libone" -> "rpm:libtwo"' in output)
        self.assertFalse('"rpm:libtwo" -> "rpm:my-software"' in output)

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
        # Check depedencies are represented in graph.
        self.assertTrue('"rpm:libone" -> "rpm:libtwo"' in output)
        # Check my-software is not mentionned in graph.
        self.assertFalse('rpm:my-software' in output)

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
        graph = PackagesDependencyGraph.from_project(
            self.config,
            self.staff,
            self.modules
        )
        graph.draw(True, [])  # w/ external deps
        output = mock_stdout.getvalue()

        # Check all packages are declared as nodes (with their labels) in graph.
        self.assertTrue(
                '"rpm:external-devel" [fillcolor=orange]' in output
        )
        # Check depedencies are represented in graph.
        self.assertTrue('"rpm:my-software" -> "rpm:external-devel"' in output)
        self.assertTrue('"rpm:libone" -> "rpm:external-devel"' in output)
        self.assertFalse('"rpm:libtwo" -> "rpm:external-devel"' in output)
