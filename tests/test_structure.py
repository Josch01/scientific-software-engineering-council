import unittest
from scripts.validate_skill import MANDATORY, validate


class StructureTests(unittest.TestCase):
    def test_valid_structure(self):
        self.assertEqual(validate(), [])

    def test_release_governance_documents_are_mandatory(self):
        self.assertIn("docs/security/THREAT_MODEL.md", MANDATORY)
        self.assertIn("docs/release/RELEASE_CANDIDATE_CHECKLIST.md", MANDATORY)
