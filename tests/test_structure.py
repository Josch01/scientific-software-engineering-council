import unittest
from scripts.validate_skill import validate


class StructureTests(unittest.TestCase):
    def test_valid_structure(self):
        self.assertEqual(validate(), [])
