#
# Copyright (C) 2026 CEA
#

from rift.repository._base import ArchRepositoriesBase
from ..TestUtils import RiftProjectTestCase


class ArchRepositoriesTestingConcrete(ArchRepositoriesBase):
    """Dummy ArchRepositories concrete child for testing purpose."""
    def __init__(self, working_dir, arch):
        super().__init__(working_dir, arch)

    def delete_matching(self):
        pass


class ArchRepositoriesBaseTest(RiftProjectTestCase):
    """
    Tests class for ArchRepositoriesBase
    """

    def test_init_abstract(self):
        with self.assertRaisesRegex(
            TypeError,
            "^Can't instantiate abstract class ArchRepositoriesBase .*"
        ):
            ArchRepositoriesBase(None, 'x86_64')

    def test_init_concrete(self):
        """ Test Package initialisation """
        repo = ArchRepositoriesTestingConcrete('/path/to/working', 'x86_64')
        self.assertEqual(repo.working_dir, '/path/to/working')
        self.assertEqual(repo.arch, 'x86_64')
