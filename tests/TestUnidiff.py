from unidiff import parse_unidiff
from .TestUtils import make_temp_file, make_temp_dir, RiftTestCase

class UnidiffTest(RiftTestCase):
    """
    Test class for unidiff
    """

    def testMultiFilePatch(self):
        """ Test if unidiff parse correctly a patch with mutliple files """
        unifiedpatch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: add 'foo'

diff --git a/file1 b/file1
new file mode 100644
index 0000000..32ac08e
--- /dev/null
+++ b/file1
@@ -0,0 +1 @@
+foo
diff --git a/file2 b/file2
new file mode 100644
index 0000000..257cc56
--- /dev/null
+++ b/file2
@@ -0,0 +1 @@
+bar
diff --git a/file3 b/file3
new file mode 100644
index 0000000..257cc56
--- /dev/null
+++ b/file3
@@ -0,0 +1 @@
+pub
""")
        with open(unifiedpatch.name, 'r') as f:
            patchedfiles = parse_unidiff(f)
        self.assertEqual(len(patchedfiles), 3)
        filenames = []
        for patchedfile in patchedfiles:
            filenames.append(patchedfile.path)
        self.assertTrue("file1" in filenames)
        self.assertTrue("file2" in filenames)
        self.assertTrue("file3" in filenames)

    def testRenamedPatch(self):
        """ Test if unidiff parse correctly a patch with renamed files """
        unifiedpatch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: rename 'foo' to 'bar'

diff --git a/foo b/bar
similarity index 100%
rename from foo
rename to bar
""")
        with open(unifiedpatch.name, 'r') as f:
            patchedfiles = parse_unidiff(f)
        for patchedfile in patchedfiles:
            self.assertTrue(patchedfile.renamed)

    def testDeletedPatch(self):
        """ Test if unidiff parse correctly a patch with deleted files """
        unifiedpatch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: delete 'foo'

diff --git a/foo b/foo
deleted file mode 100644
index 6a7d848..0000000
--- a/MANIFEST.in
+++ /dev/null
@@ -1,1 +0,0 @@
-include scripts/rift

diff --git a/foo.bin b/foo.bin
deleted file mode 100644
index c2e4672..0000000
Binary files a/packages/slurm/sources/slurm-18.08.6.tar.bz2 and /dev/null differ
""")
        with open(unifiedpatch.name, 'r') as f:
            patchedfiles = parse_unidiff(f)
        for patchedfile in patchedfiles:
            self.assertTrue(patchedfile.is_deleted_file)

    def testBinaryPatch(self):
        unifiedpatch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: add 'foo'

diff --git /dev/null b/foo
index 6cd0ff6ec591f7f51a3479d7b66c6951a2b4afa9..91ef2076b67f3158ec1670fa7b88d88b2816aa91 100644
GIT binary patch
literal 8
PcmZQ%;Sf+z_{{#tQ1BL-x

literal 4
LcmZQ%;Sc}}-05kv|

diff --git /dev/null b/bar
index fcd49dd..91ef207 100644
Binary files a/sources/a.tar.gz and b/sources/a.tar.gz differ
""")
        with open(unifiedpatch.name, 'r') as f:
            patchedfiles = parse_unidiff(f)
        for patchedfile in patchedfiles:
            self.assertTrue(patchedfile.binary)
