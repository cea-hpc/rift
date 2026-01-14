#
# Copyright (C) 2025 CEA
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
Module to track dependencies between packages in Rift projects in a graph and
solve recursive build requirements.
"""
import time
from collections import namedtuple
import textwrap
import logging

from rift.package import ProjectPackages
from rift import RiftError

BuildRequirement = namedtuple("BuildRequirement", ["package", "reasons"])


class PackageDependencyNode:
    """Node in PackagesDependencyGraph."""
    def __init__(self, package):
        self.package = package
        self.subpackages = package.subpackages()
        self.build_requires = package.build_requires()
        self.rdeps = []

    def depends_on(self, node):
        """
        Return True if the package of the current node depends on the package of
        the given node, ie. when current node source package has build
        requirement on any of the subpackages produced by the given node.
        """
        # Check depends in info.yaml
        if self.package.depends is not None:
            return node.package.name in self.package.depends
        # If dependencies are not defined in info.yaml, look at build requires
        # and produced subpackages found in spec file.
        return any(
            build_require in node.subpackages
            for build_require in self.build_requires
        )

    def required_subpackages(self, rdep):
        """
        Return the list of current node subpackages that are build requirements
        of the given reverse dependency.
        """
        return [
            subpkg
            for subpkg in self.subpackages
            if subpkg in rdep.build_requires
        ]

    def rdep_reason(self, rdep):
        """
        Return a string to describe the reason to justify the build requirement
        on the reverse dependency. If depends are defined in info.yaml, just
        indicate this dependency. Otherwise, resolve build requirements to
        indicate the subpackages that explain the dependency.
        """
        if rdep.package.depends is not None:
            return f"depends on {self.package.name}"
        return 'build depends on ' + ', '.join(
            self.required_subpackages(rdep)
        )

    def draw_label(self):
        """
        Return a string to represent node label in graphviz representation.
        """
        return (
            '<<table border="0" cellborder="0" cellpadding="1"><tr>'
            '<td bgcolor="#555555" align="center">'
            f"<font color=\"white\">{self.package.name}</font>"
            '</td></tr>'
            + ''.join(
                [
                    f"<tr><td align=\"center\">{subpackage}</td></tr>"
                    for subpackage in self.subpackages
                ]
            )
            + '</table>>'
        )

class PackagesDependencyGraph:
    """Graph of dependencies between packages in Rift project."""
    def __init__(self):
        self.nodes = []
        self.path = None
        self.represented_nodes = None  # used and initialized in _draw_nodes()
        self.external_deps = None  # initialized in draw()

    def dump(self):
        """Dump graph in its current state with logging message."""
        for node in self.nodes:
            logging.info("→ %s", node.package.name)
            logging.info("  provides: %s", str(node.subpackages))
            logging.info("  requires: %s", node.build_requires)
            logging.info(
                "  is required by: %s",
                str([rdep.package.name for rdep in node.rdeps])
            )

    def draw(self, external, packages):
        """
        Generate graphviz representation of packages dependencies graph on
        standard output, with or without project external dependencies.
        """
        # circo layout is used when all project packages are represented
        # without external dependencies because there are generally many nodes
        # without relations and this results in a more dense layout. In other
        # cases, there are generally more relations and default dot layout is
        # preferred.
        print(
            'digraph rift {\n'
            f"  layout={'dot' if external or packages else 'circo'} \n"
            '  fontname="Helvetica,Arial,sans-serif"\n'
            '  node [fontname="Helvetica,Arial,sans-serif", style=filled, '
            'fillcolor=white, penwidth=1, fontsize=8, shape=Mrecord, '
            'height=0.25]\n'
            '  edge [fontname="Helvetica,Arial,sans-serif", fontsize=6, '
            'fontcolor="#444444"]\n'
        )
        # Track external dependencies and represented nodes in list to avoid
        # duplicates.
        self.external_deps = []
        self.represented_nodes = []
        self._draw_nodes(external, packages)
        self._draw_relations(external)

    def _search_deps(self, node):
        """Generator for a given node dependencies."""
        for _node in self.nodes:
            if node in _node.rdeps:
                yield _node

    def _draw_node(self, node):
        """Draw a node and its dependencies recursively."""
        # Skip node if it has already been represented.
        if node in self.represented_nodes:
            return
        print(
            f"  \"{node.package.name}\" [ label = {node.draw_label()} ];"
        )
        self.represented_nodes.append(node)
        # Fill external_deps list with additional build requirements.
        for build_require in node.build_requires:
            if build_require not in self.external_deps:
                self.external_deps.append(build_require)
        # Draw node dependencies recusively.
        for dep in self._search_deps(node):
            self._draw_node(dep)

    def _draw_nodes(self, external, packages):
        """
        Generate graphviz packages nodes on standard output, either a subset of
        project packages or all nodes, with or without project external
        dependencies.
        """
        if packages:
            logging.debug(
                "Dependency graph represented with this list of packages: %s",
                str(packages)
            )
        else:
            logging.debug(
                "Dependency graph represented with all project packages"
            )
        for node in self.nodes:
            # If a subset of packages is specified and node's package is not in
            # this list, skip this node.
            if packages and node.package.name not in packages:
                continue
            self._draw_node(node)
        # Filter out from external_deps all dependencies that are actually
        # satisfied by project packages.
        for node in self.nodes:
            for subpackage in node.subpackages:
                if subpackage in self.external_deps:
                    self.external_deps.remove(subpackage)
        # If external dependencies have to be represented, draw these nodes with
        # distinctive color.
        if external:
            for external_dep in self.external_deps:
                print(
                    f"  \"{external_dep}\" [fillcolor=orange];"
                )

    def _draw_relations(self, external):
        """
        Generate graphviz relations between represented nodes on standard
        output, with or without project external dependencies.
        """
        for node in self.represented_nodes:
            # Draw relations between project packages and their reverse
            # dependencies.
            for rdep in node.rdeps:
                # Skip reverse dependency if its node is not represented.
                if rdep not in self.represented_nodes:
                    continue
                print(
                    f"  \"{rdep.package.name}\" -> \"{node.package.name}\" "
                    '[ label = "',
                    textwrap.fill(node.rdep_reason(rdep), 20),
                    '" ];'
                )
            # If external dependencies have to be represented, draw relations
            # between project packages and these external dependencies.
            if external:
                for build_require in node.build_requires:
                    if build_require in self.external_deps:
                        print(
                            f"  \"{node.package.name}\" -> \"{build_require}\";"
                        )
        print('}')

    def _dep_index(self, new, result):
        """
        The new and results arguments are list of build requirements. The result
        contains the current list of build requirements. The first item of the
        new list is the build requirement to insert in result list followed by
        all its own build requirements.

        If the first item in new is already present in result, return True and
        the index of this item in result. Else, it returns False and the first
        index of its build requirements in result. If none of its build
        requirements is found in result, return index -1.
        """
        # Search first item of new in result. If found, return True and its
        # index.
        for index, build_requirement in enumerate(result):
            if build_requirement.package == new[0].package:
                return True, index

        # First item not found in result, Return false and the first index of
        # of its build requirement.
        for index, build_requirement in enumerate(result):
            for new_build_requirement in new[1:]:
                if new_build_requirement.package == build_requirement.package:
                    return False, index

        # No build requirement found in result, return false and -1.
        return False, -1

    def _solve(self, node, reason, depth=0):
        """
        Return list of recursive build requirements for the provided package
        dependency node. The "reason" argument is a string to textually justify
        the build requirement of the given node. The depth argument is used to
        track the depth of recursive path in the dependency graph.
        """

        result = []
        logging.debug(
            "%s→ Source package %s must be rebuilt",
            '  '*depth,
            node.package.name
        )
        result.append(
            BuildRequirement(node.package, [reason])
        )

        # Remove the end of the processing path after the current node
        del self.path[max(0, depth-1):-1]
        # Add current node to the processing path
        self.path.append(node)

        for rdep in node.rdeps:
            reason = node.rdep_reason(rdep)
            # If reverse dependency has already been processed in the processing
            # path to the current node, add it to resulting list and stop
            # processing to avoid endless loop.
            if rdep in self.path[0:depth]:
                logging.debug(
                    "%s   ⥀ Loop detected on node %s at depth %d: %s",
                    '  '*depth,
                    rdep.package.name,
                    depth,
                    '→'.join(node.package.name for node in self.path + [rdep]),
                )
                result.append(BuildRequirement(rdep.package, [reason]))
                continue
            logging.debug(
                "%s  Exploring reverse dependency %s",
                '  '*depth,
                rdep.package.name
            )
            # Iterate over all recursively solved build requirements for this
            # reverse dependency.
            build_requirements = self._solve(rdep, reason, depth+1)
            for idx, build_requirement in enumerate(build_requirements):
                found, position = self._dep_index(build_requirements[idx:], result)
                if found:
                    # Build requirement already present in result, just extend
                    # the build reasons.
                    result[position].reasons.extend(
                        build_requirement.reasons
                    )
                elif position == -1:
                    # The recursive build requirements of the new build
                    # requirement are not present in the list, just append the
                    # new build requirement in result.
                    result.append(build_requirement)
                else:
                    # Insert the new build requirement before its first
                    # recursive build requirements in result.
                    result.insert(position, build_requirement)
        return result

    def solve(self, package):
        """
        Return list of recursive build requirements for the provided package.
        """
        self.path = []  # Start with empty path
        for node in self.nodes:
            if node.package.name == package.name:
                return self._solve(node, "User request")

        # Package not found in graph, return empty list.
        return []

    def _insert(self, package):
        """Insert package in the graph."""
        node = PackageDependencyNode(package)
        for _node in self.nodes:
            if _node.depends_on(node):
                node.rdeps.append(_node)
            if node.depends_on(_node):
                _node.rdeps.append(node)
        self.nodes.append(node)

    def build(self, packages):
        """Build graph with the provided packages."""
        tic = time.perf_counter()
        for package in packages:
            # Load info.yaml to check for potential explicit dependencies. Skip
            # package with warning if unable to load.
            try:
                package.load()
            except (RiftError, FileNotFoundError) as err:
                logging.warning("Skipping package '%s' unable to load: %s",
                                package.name, err)
                continue
            self._insert(package)
        toc = time.perf_counter()
        logging.debug("Graph built in %0.4f seconds", toc - tic)
        logging.debug("Graph size: %d", len(self.nodes))

    @classmethod
    def from_project(cls, config, staff, modules):
        """Build graph with all project's packages."""
        graph = cls()
        graph.build(ProjectPackages.list(config, staff, modules))
        return graph
