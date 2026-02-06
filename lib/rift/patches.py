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
patches.py:
    Package to parse patches files in unified diff format
"""
import os
import logging

from unidiff import parse_unidiff
from rift import RiftError
from rift.package import ProjectPackages
from rift.RPM import RPMLINT_CONFIG_V1, RPMLINT_CONFIG_V2
from rift.Config import Staff, Modules


def get_packages_from_patch(patch, config, modules, staff):
    """
    Return 2-tuple of dicts of updated and removed packages extracted from given
    patch.
    """
    updated = {}
    removed = {}
    patchedfiles = parse_unidiff(patch)
    if not patchedfiles:
        raise RiftError("Invalid patch detected (empty commit ?)")

    for patchedfile in patchedfiles:
        modifies_packages = _validate_patched_file(
            patchedfile,
            config=config,
            modules=modules,
            staff=staff
        )
        if not modifies_packages:
            continue
        pkg = _patched_file_updated_package(
            patchedfile,
            config=config,
            modules=modules,
            staff=staff
        )
        if pkg is not None and pkg not in updated:
            logging.info('Patch updates package %s', pkg.name)
            updated[pkg.name] = pkg
        pkg = _patched_file_removed_package(
            patchedfile,
            config=config,
            modules=modules,
            staff=staff
        )
        if pkg is not None and pkg not in removed:
            logging.info('Patch deletes package %s', pkg.name)
            removed[pkg.name] = pkg

    return updated, removed


def _validate_patched_file(patched_file, config, modules, staff):
    """
    Raise RiftError if patched_file is a binary file or does not match any known
    file path in Rift project tree.

    Return True if the patched_file modifies a package or False otherwise.
    """
    filepath = patched_file.path
    names = filepath.split(os.path.sep)

    if filepath == config.get('staff_file'):
        staff = Staff(config)
        staff.load(filepath)
        logging.info('Staff file is OK.')
        return False

    if filepath == config.get('modules_file'):
        modules = Modules(config, staff)
        modules.load(filepath)
        logging.info('Modules file is OK.')
        return False

    if filepath == 'mock.tpl':
        logging.debug('Ignoring mock template file: %s', filepath)
        return False

    if filepath == '.gitignore':
        logging.debug('Ignoring git file: %s', filepath)
        return False

    if filepath == 'project.conf':
        logging.debug('Ignoring project config file: %s', filepath)
        return False

    if filepath == '.gitlab-ci.yml':
        logging.debug('Ignoring gitlab ci file: %s', filepath)
        return False

    if filepath == 'CODEOWNERS':
        logging.debug('Ignoring gitlab ci file: %s', filepath)
        return False

    if names[0] == "gitlab-ci":
        logging.debug("Ignoring gitlab ci file: %s", filepath)
        return False

    if patched_file.binary:
        raise RiftError(f"Binary file detected: {filepath}")

    if names[0] != config.get('packages_dir'):
        raise RiftError(f"Unknown file pattern: {filepath}")

    return True


def _patched_file_updated_package(patched_file, config, modules, staff):
    """
    Return Package updated by patched_file, or None if either:

    - The patched_file modifies a package file that does not impact package
      build result.
    - The pached_file is removed.

    Raise RiftError if patched_file path does not match any known
    packaging code file path.
    """
    filepath = patched_file.path
    names = filepath.split(os.path.sep)
    fullpath = config.project_path(filepath)
    pkg = None

    if patched_file.is_deleted_file:
        logging.debug('Ignoring removed file: %s', filepath)
        return None

    # Drop config.get('packages_dir') from list
    names.pop(0)

    pkg = ProjectPackages.get(names.pop(0), config, staff, modules)

    # info.yaml
    if fullpath == pkg.metafile:
        logging.info('Ignoring meta file')
        return None

    # README file
    if fullpath in pkg.docfiles:
        logging.debug('Ignoring documentation file: %s', fullpath)
        return None

    # backup buildfile
    if fullpath == f"{pkg.buildfile}.orig":
        logging.debug('Ignoring backup buildfile')
        return None

    # buildfile
    if fullpath == pkg.buildfile:
        logging.info('Detected buildfile file')

    # rpmlint config file
    elif names in [RPMLINT_CONFIG_V1, RPMLINT_CONFIG_V2]:
        logging.debug('Detecting rpmlint config file')

    # sources/
    elif fullpath.startswith(pkg.sourcesdir) and len(names) == 2:
        logging.debug('Detecting source file: %s', names[1])

    # tests/
    elif fullpath.startswith(pkg.testsdir):
        logging.debug('Detecting test script: %s', filepath)

    else:
        raise RiftError(
            f"Unknown file pattern in '{pkg.name}' directory: {filepath}"
        )

    return pkg


def _patched_file_removed_package(patched_file, config, modules, staff):
    """
    Return Package removed by the patched_file or None if patched_file does not
    remove any package.
    """
    filepath = patched_file.path
    names = filepath.split(os.path.sep)
    fullpath = config.project_path(filepath)

    if not patched_file.is_deleted_file:
        logging.debug('Ignoring not removed file: %s', filepath)
        return None

    pkg = ProjectPackages.get(names[1], config, staff, modules)

    if fullpath == pkg.metafile:
        return pkg

    return None
