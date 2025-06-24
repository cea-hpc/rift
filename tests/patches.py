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

import os

from .TestUtils import make_temp_file, RiftProjectTestCase

from rift import RiftError
from rift.patches import get_packages_from_patch

class PatchTest(RiftProjectTestCase):

    def test_package_removed(self):
        """ Test detect removed package in patch"""
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        pkgsrc = os.path.join('packages', 'pkgname', 'sources',
                              '{0}-{1}.tar.gz'.format(pkgname, pkgvers))
        patch = make_temp_file("""
diff --git a/packages/pkg/info.yaml b/packages/pkg/info.yaml
deleted file mode 100644
index 32ac08e..0000000
--- a/packages/pkg/info.yaml
+++ /dev/null
@@ -1,6 +0,0 @@
-package:
-    maintainers:
-        - Myself
-    module: Great module
-    origin: Vendor
-    reason: Missing feature
diff --git a/packages/pkg/pkg.spec b/packages/pkg/pkg.spec
deleted file mode 100644
index b92c49d..0000000
--- a/packages/pkg/pkg.spec
+++ /dev/null
@@ -1,24 +0,0 @@
-Name:    pkg
-Version:        1.0
-Release:        1
-Summary:        A package
-Group:          System Environment/Base
-License:        GPL
-URL:            http://nowhere.com/projects/%{{name}}/
-Source0:        %{{name}}-%{{version}}.tar.gz
-BuildArch:      noarch
-BuildRequires:  br-package
-Requires:       another-package
-Provides:       pkg-provide
-%description
-A package
-%prep
-%build
-# Nothing to build
-%install
-# Nothing to install
-%files
-# No files
-%changelog
-* Tue Feb 26 2019 Myself <buddy@somewhere.org> - 1.0-1
-- Update to 1.0 release
diff --git a/{0} b/{0}
deleted file mode 100644
index 43bf48d..0000000
--- a/{0}
+++ /dev/null
@@ -1 +0,0 @@
-ACACACACACACACAC
\ No newline at end of file
""".format(pkgsrc))

        with open(patch.name) as p:
            (updated, removed) = get_packages_from_patch(
                p, self.config, self.modules, self.staff
            )
            self.assertEqual(len(updated), 0)
            self.assertEqual(len(removed), 1)
            self.assertTrue('pkg' in removed.keys())

    def test_tests_directory(self):
        """ Test if package tests directory structure is fine """
        patch = make_temp_file("""
diff --git a/packages/pkg/tests/sources/deep/source.c b/packages/pkg/tests/sources/deep/source.c
new file mode 100644
index 0000000..68344bf
--- /dev/null
+++ b/packages/pkg/tests/sources/deep/source.c
@@ -0,0 +1,4 @@
+#include <stdlib.h>
+int main(int argc, char **argv){
+    exit(0);
+}
\ No newline at end of file
""")
        # Ensure package exists
        self.make_pkg('pkg')
        with open(patch.name, 'r') as f:
            (updated, removed) = get_packages_from_patch(
                f, self.config, self.modules, self.staff
            )
            self.assertEqual(len(updated), 1)
            self.assertEqual(len(removed), 0)
            self.assertTrue('pkg' in updated.keys())

    def test_invalid_file(self):
        """Test invalid project file is detected in patch"""
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    project wrong file

diff --git a/wrong b/wrong
new file mode 100644
index 0000000..68344bf
--- a/wrong
+++ b/wrong
@@ -0,0 +1 @@
+README
""")
        with open(patch.name, 'r') as f:
            with self.assertRaisesRegex(RiftError,
                                        "Unknown file pattern: wrong"):
                get_packages_from_patch(
                    f, self.config, self.modules, self.staff
                )

    def test_invalid_pkg_file(self):
        """Test invalid package file is detected in patch"""
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: Wrong file

diff --git a/packages/pkg/wrong b/packages/pkg/wrong
new file mode 100644
index 0000000..68344bf
--- a/packages/pkg/wrong
+++ b/packages/pkg/wrong
@@ -0,0 +1 @@
+README
""")
        with open(patch.name, 'r') as f:
            with self.assertRaisesRegex(
                RiftError,
                "Unknown file pattern in 'pkg' directory: packages/pkg/wrong"):
                get_packages_from_patch(
                    f, self.config, self.modules, self.staff
                )

    def test_info(self):
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: update 'pkg' infos

diff --git a/packages/pkg/info.yaml b/packages/pkg/info.yaml
new file mode 100644
index 0000000..68344bf
--- a/packages/pkg/info.yaml
+++ b/packages/pkg/info.yaml
@@ -2,5 +2,5 @@ package:
   maintainers:
   - Myself
   module: Great module
-  origin: Somewhere
+  origin: Elsewhere
   reason: Missing feature
""")
        self.make_pkg()
        # For this patch, get_packages_from_patch() must not return updated nor
        # removed packages.
        with open(patch.name, 'r') as p:
            (updated, removed) = get_packages_from_patch(
                p, config=self.config, modules=self.modules, staff=self.staff
            )
        self.assertEqual(len(updated), 0)
        self.assertEqual(len(removed), 0)

    def test_modules(self):
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    modules: add 'Section'

diff --git a/packages/modules.yaml b/packages/modules.yaml
new file mode 100644
index 0000000..68344bf
--- a/packages/modules.yaml
+++ b/packages/modules.yaml
@@ -0,0 +3 @@
+modules:
+  User Tools:
+    manager: John Doe
""")
        # For this patch, get_packages_from_patch() must not return updated nor
        # removed packages.
        with open(patch.name, 'r') as p:
            (updated, removed) = get_packages_from_patch(
                p, config=self.config, modules=self.modules, staff=self.staff
            )
        self.assertEqual(len(updated), 0)
        self.assertEqual(len(removed), 0)

    def test_readme(self):
        """ Should allow README files """
        self.make_pkg()
        patch_template = """
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: document 'pkg'

diff --git a/packages/pkg/{0} b/packages/pkg/{0}
new file mode 100644
index 0000000..e845566
--- /dev/null
+++ b/packages/pkg/{0}
@@ -0,0 +1 @@
+README
"""

        for fmt in '', 'rst', 'md', 'txt':
            filename = 'README'
            if fmt:
                filename = "{0}.{1}".format(filename, fmt)
            patch = make_temp_file(patch_template.format(filename))
            with open(patch.name, 'r') as f:
                (updated, removed) = get_packages_from_patch(
                    f, self.config, self.modules, self.staff
                )
                self.assertEqual(len(updated), 0)
                self.assertEqual(len(removed), 0)

    def test_binary(self):
        """ Should fail if source file is a binary file """
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        pkgsrc = os.path.join('packages', 'pkgname', 'sources',
                              '{0}-{1}.tar.gz'.format(pkgname, pkgvers))
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: update 'pkg' sources

diff --git /dev/null b/{0}
index fcd49dd..91ef207 100644
Binary files a/sources/a.tar.gz and b/sources/a.tar.gz differ
""".format(pkgsrc))
        with open(patch.name, 'r') as f:
            with self.assertRaisesRegex(
                RiftError,
                "Binary file detected: {0}".format(pkgsrc)):
                get_packages_from_patch(
                    f, self.config, self.modules, self.staff
                )

    def test_binary_with_content(self):
        """ Should fail if source file is a binary file (diff --binary) """
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        pkgsrc = os.path.join('packages', 'pkgname', 'sources',
                              '{0}-{1}.tar.gz'.format(pkgname, pkgvers))
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: update 'pkg' sources

diff --git /dev/null b/{0}
index 6cd0ff6ec591f7f51a3479d7b66c6951a2b4afa9..91ef2076b67f3158ec1670fa7b88d88b2816aa91 100644
GIT binary patch
literal 8
PcmZQ%;Sf+z_{{#tQ1BL-x

literal 4
LcmZQ%;Sc}}-05kv|
""".format(pkgsrc))
        with open(patch.name, 'r') as f:
            with self.assertRaisesRegex(RiftError, "Binary file detected: {0}".format(pkgsrc)):
                get_packages_from_patch(
                    f, self.config, self.modules, self.staff
                )

    def test_rename_package(self):
        """ Test if renaming a package trigger a build """
        pkgname = 'pkgnew'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        patch = make_temp_file("""
diff --git a/packages/pkg/pkg.spec b/packages/pkgnew/pkgnew.spec
similarity index 100%
rename from packages/pkg/pkg.spec
rename to packages/pkgnew/pkgnew.spec
diff --git a/packages/pkg/info.yaml b/packages/pkgnew/info.yaml
similarity index 100%
rename from packages/pkg/info.yaml
rename to packages/pkgnew/info.yaml
diff --git a/packages/pkg/sources/pkg-1.0.tar.gz b/packages/pkgnew/sources/pkgnew-1.0.tar.gz
similarity index 100%
rename from packages/pkg/sources/pkg-1.0.tar.gz
rename to packages/pkgnew/sources/pkgnew-1.0.tar.gz
""")
        # For this patch, get_packages_from_patch() must return an updated
        # package named pkgnew.
        with open(patch.name, 'r') as p:
            (updated, removed) = get_packages_from_patch(
                p, config=self.config, modules=self.modules, staff=self.staff
            )
        self.assertEqual(len(updated), 1)
        self.assertEqual(len(removed), 0)
        self.assertTrue('pkgnew' in updated.keys())

    def test_rename_and_update_package(self):
        """ Test if renaming and updating a package trigger a build """
        pkgname = 'pkgnew'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        patch = make_temp_file("""
commit f8c1a88ea96adfccddab0bf43c0a90f05ab26dc5 (HEAD -> playground)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: rename 'pkg' to 'pkgnew'

diff --git a/packages/pkg/info.yaml b/packages/pkgnew/info.yaml
similarity index 100%
rename from packages/pkg/info.yaml
rename to packages/pkgnew/info.yaml
diff --git a/packages/pkg/pkg.spec b/packages/pkgnew/pkgnew.spec
similarity index 93%
rename from packages/pkg/pkg.spec
rename to packages/pkgnew/pkgnew.spec
index b92c49d..0fa690c 100644
--- a/packages/pkg/pkg.spec
+++ b/packages/pkgnew/pkgnew.spec
@@ -1,6 +1,6 @@
-Name:    pkg
+Name:    pkgnew
 Version:        1.0
-Release:        1
+Release:        2
 Summary:        A package
 Group:          System Environment/Base
 License:        GPL
diff --git a/packages/pkg/sources/pkg-1.0.tar.gz b/packages/pkgnew/sources/pkgnew-1.0.tar.gz
similarity index 100%
rename from packages/pkg/sources/pkg-1.0.tar.gz
rename to packages/pkgnew/sources/pkgnew-1.0.tar.gz
""")
        # For this patch, get_packages_from_patch() must return an updated
        # package named pkgnew.
        with open(patch.name, 'r') as p:
            (updated, removed) = get_packages_from_patch(
                p, config=self.config, modules=self.modules, staff=self.staff
            )
        self.assertEqual(len(updated), 1)
        self.assertEqual(len(removed), 0)
        self.assertTrue('pkgnew' in updated.keys())
