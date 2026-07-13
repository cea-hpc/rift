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

"""Module to get list or individual project packages."""

import os

from rift import RiftError
from rift.package._virtual import PackageVirtual
from rift.package.rpm import PackageRPM
from rift.package.oci import PackageOCI

class ProjectPackages:
    """
    Factory to get list of projects packages objects with their supported
    formats.
    """

    @staticmethod
    def list(config, staff, modules, names=None):
        """
        Iterate over PackageBase concrete children instances from 'names' list
        or all packages if list is not provided.
        """
        pkgs_dir = config.project_path(config.get('packages_dir'))
        if not names:
            names = [path for path in os.listdir(pkgs_dir)
                     if os.path.isdir(os.path.join(pkgs_dir, path))]

        for name in names:
            yield from ProjectPackages._get(name, config, staff, modules)

    @staticmethod
    def _get(name, config, staff, modules):
        """
        Generate PackageBase children objects corresponding to the given package
        name. If package directory does not exist, return PackageVirtual object,
        else generate concrete PackageBase child objects for which build file is
        present. Raise RiftError if package directory is present without
        supported package buildfile.
        """
        pkgdir = os.path.join(config.project_path(config.get('packages_dir')), name)
        if not os.path.isdir(pkgdir):
            yield PackageVirtual(name, config, staff, modules)
            return  # stop here when directory does not exist
        package_format_found = False
        for package_class in [PackageRPM, PackageOCI]:
            pkg = package_class(name, config, staff, modules)
            if os.path.exists(os.path.join(pkgdir, pkg.buildfile)):
                package_format_found = True
                yield pkg
        if not package_format_found:
            raise RiftError(f"Unable to determine format of package {name} due "
                    f"to missing build file in {pkgdir}")

    @staticmethod
    def get(name, config, staff, modules):
        """
        Return list of PackageBase concrete children objects corresponding to
        the given package name.
        """
        return list(ProjectPackages._get(name, config, staff, modules))
