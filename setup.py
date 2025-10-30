#!/usr/bin/env python
#
# Copyright (C) 2014-2019 CEA
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

from lib.rift import __version__
from setuptools import setup

setup(name='rift',
      version=__version__,
      license='CeCILL-C (French equivalent to LGPLv2+)',
      description='RPM repository management',
      author='Aurelien Cedeyn',
      author_email='aurelien.cedeyn@cea.fr',
      package_dir={'': 'lib'},
      packages=['rift'],
      install_requires=['boto3>=1.18.65', 'xmltodict'],
      py_modules = ['unidiff'],
      data_files = [
                  ('/usr/share/rift/template', ['template/project.conf', 'template/local.conf', 'template/mock.tpl']),
                  ('/usr/share/rift/template/packages', ['template/packages/modules.yaml', 'template/packages/staff.yaml']),
                  ('/usr/share/rift/vendor', ['vendor/QEMU_EFI.fd', 'vendor/QEMU_EFI.silent.fd']),
                  ('/usr/share/doc/rift', ['Changelog', 'AUTHORS']),
              ],
      entry_points = {
        'console_scripts': [
            'rift = rift.Controller:main',
        ],
      }
     )

