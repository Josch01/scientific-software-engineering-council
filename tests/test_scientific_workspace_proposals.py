"""Fail-closed proposal review and persistence for scientific workspace manifests."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.scientific_workspace_loader import load_scientific_workspace


def _write_manifest(root: Path, filename: str, *, title: str, resource: bytes,
                    resource_sha256: str | None = None, include_resource_digest: bool = True) -> Path:
    (root / "model.json").write_bytes(resource)
    manifest = {
        "schema_version": 1,
        "workspace_id": "sir-workspace",
        "title": title,
        "resources": [{
            "id": "model",
            "kind": "model_spec",
            "path": "model.json",
        }],
        "sections": [{
            "id": "model-section",
            "title": "Model",
            "components": [{
                "id": "equations",
                "type": "equation_view",
                "title": title,
                "resource_refs": ["model"],
                "config": {},
            }],
        }],
    }
    if include_resource_digest or resource_sha256:
        manifest["resources"][0]["sha256"] = (
            resource_sha256 or hashlib.sha256(resource).hexdigest()
        )
    path = root / filename
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_large_manifest(root: Path, filename: str, *, title: str) -> bytes:
    resource_ids = []
    resources = []
    resource_bytes = b"{}\n"
    for index in range(100):
        resource_id = "r" * 60 + str(index)
        resource_path = f"resource-{index}.json"
        (root / resource_path).write_bytes(resource_bytes)
        resource_ids.append(resource_id)
        resources.append({
            "id": resource_id,
            "kind": "generic",
            "path": resource_path,
            "sha256": hashlib.sha256(resource_bytes).hexdigest(),
        })
    components = [
        {
            "id": f"artifacts-{index:03d}",
            "type": "artifact_browser",
            "title": "Resources",
            "resource_refs": resource_ids,
            "config": {},
        }
        for index in range(140)
    ]
    manifest = {
        "schema_version": 1,
        "workspace_id": "large-workspace",
        "title": title,
        "resources": resources,
        "sections": [{"id": "all", "title": "Artifacts", "components": components}],
    }
    compact = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    pretty = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(compact) >= 1_048_576 or len(pretty) <= 1_048_576:
        raise AssertionError("large manifest fixture must be compact-valid and pretty-oversized")
    (root / filename).write_bytes(compact)
    return compact


class ScientificWorkspaceProposalTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("scripts.scientific_workspace_proposals"),
            "workspace proposal preview and approval are not implemented",
        )
        from scripts import scientific_workspace_proposals
        self.proposals = scientific_workspace_proposals
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resource = b'{"model_type":"sir","status":"synthetic"}\n'
        self.source_path = _write_manifest(
            self.root, "workspace.json", title="Current workspace", resource=self.resource
        )
        self.proposal_path = _write_manifest(
            self.root, "proposal.json", title="Proposed workspace", resource=self.resource
        )
        self.active = load_scientific_workspace(self.root, "workspace.json")
        self._source_bytes = self.source_path.read_bytes()
        self._proposal_bytes = self.proposal_path.read_bytes()

    def _preview(self):
        return self.proposals.preview_workspace_proposal(
            self.root, self.active, "proposal.json"
        )

    def test_preview_shows_complete_diff_and_does_not_write(self):
        preview = self._preview()

        self.assertTrue(preview.changed)
        self.assertEqual(preview.proposal_relative_path, "proposal.json")
        self.assertRegex(preview.active_manifest_sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(preview.proposal_manifest_sha256, r"^[0-9a-f]{64}$")
        self.assertIn("Current workspace", preview.diff)
        self.assertIn("Proposed workspace", preview.diff)
        self.assertEqual(self.source_path.read_bytes(), self._source_bytes)
        self.assertEqual(self.proposal_path.read_bytes(), self._proposal_bytes)
        self.assertEqual(list(self.root.glob(".ssec-workspace-*.json")), [])

    def test_approval_persists_exact_proposal_without_overwriting_sources(self):
        preview = self._preview()

        approved = self.proposals.approve_workspace_proposal(self.root, self.active, preview)

        self.assertTrue(approved.created)
        self.assertEqual(approved.sha256, preview.proposal_manifest_sha256)
        self.assertEqual(approved.workspace.summary.title, "Proposed workspace")
        self.assertTrue(approved.manifest_relative_path.startswith(".ssec-workspace-"))
        self.assertEqual(approved.workspace.manifest["title"], "Proposed workspace")
        self.assertEqual(self.source_path.read_bytes(), self._source_bytes)
        self.assertEqual(self.proposal_path.read_bytes(), self._proposal_bytes)

        again = self.proposals.approve_workspace_proposal(self.root, self.active, preview)

        self.assertFalse(again.created)
        self.assertEqual(again.manifest_relative_path, approved.manifest_relative_path)
        self.assertEqual(again.workspace.summary.title, approved.workspace.summary.title)

    def test_missing_resource_digest_blocks_preview_before_any_copy(self):
        _write_manifest(
            self.root, "proposal.json", title="Proposed workspace", resource=self.resource,
            include_resource_digest=False,
        )
        self._proposal_bytes = self.proposal_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "requires a SHA-256 digest before loading"):
            self._preview()
        self.assertEqual(list(self.root.glob(".ssec-workspace-*.json")), [])

    def test_changed_proposal_after_preview_blocks_approval(self):
        preview = self._preview()
        _write_manifest(self.root, "proposal.json", title="Changed after review", resource=self.resource)

        with self.assertRaisesRegex(ValueError, "proposal changed after preview"):
            self.proposals.approve_workspace_proposal(self.root, self.active, preview)

        self.assertEqual(list(self.root.glob(".ssec-workspace-*.json")), [])

    def test_changed_active_workspace_blocks_approval(self):
        preview = self._preview()
        other_path = _write_manifest(
            self.root, "other.json", title="Other active workspace", resource=self.resource
        )
        changed_active = load_scientific_workspace(self.root, "other.json")

        with self.assertRaisesRegex(ValueError, "active workspace changed after preview"):
            self.proposals.approve_workspace_proposal(self.root, changed_active, preview)

        self.assertTrue(other_path.exists())
        self.assertEqual(list(self.root.glob(".ssec-workspace-*.json")), [])

    def test_invalid_resource_digest_blocks_preview(self):
        _write_manifest(
            self.root, "proposal.json", title="Invalid proposal", resource=self.resource,
            resource_sha256="0" * 64,
        )

        with self.assertRaisesRegex(ValueError, "SHA-256 does not match the manifest"):
            self._preview()

        self.assertEqual(list(self.root.glob(".ssec-workspace-*.json")), [])

    def test_diff_limit_refuses_partial_review(self):
        with patch.object(self.proposals, "MAX_PROPOSAL_DIFF_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "diff exceeds"):
                self._preview()

        self.assertEqual(list(self.root.glob(".ssec-workspace-*.json")), [])

    def test_existing_digest_target_is_never_overwritten(self):
        preview = self._preview()
        target = self.root / f".ssec-workspace-{preview.proposal_manifest_sha256}.json"
        target.write_bytes(b"pre-existing content\n")

        with self.assertRaisesRegex(ValueError, "existing proposal target"):
            self.proposals.approve_workspace_proposal(self.root, self.active, preview)

        self.assertEqual(target.read_bytes(), b"pre-existing content\n")

    def test_existing_semantic_digest_target_must_have_canonical_file_bytes(self):
        preview = self._preview()
        target = self.root / f".ssec-workspace-{preview.approved_manifest_sha256}.json"
        target.write_text(
            json.dumps(json.loads(self._proposal_bytes), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        original = target.read_bytes()

        with self.assertRaisesRegex(ValueError, "existing proposal target is not canonical"):
            self.proposals.approve_workspace_proposal(self.root, self.active, preview)

        self.assertEqual(target.read_bytes(), original)

    def test_checked_in_sir_proposal_loads_with_registered_audit_component(self):
        project = Path(__file__).resolve().parents[1] / "examples"

        workspace = load_scientific_workspace(project, "sir_workspace_proposal.json")

        self.assertEqual(workspace.summary.workspace_id, "sir-demo")
        self.assertIn("audit_summary", workspace.summary.component_types)
        self.assertEqual(
            next(item for item in workspace.resources if item.resource_id == "audit-fixture").sha256,
            hashlib.sha256((project / "sir_demo_audit.json").read_bytes()).hexdigest(),
        )

    def test_approval_keeps_large_valid_manifest_under_loader_limit(self):
        active_bytes = _write_large_manifest(self.root, "large-active.json", title="Active")
        proposal_bytes = _write_large_manifest(self.root, "large-proposal.json", title="Proposed")
        self.assertLess(len(active_bytes), 1_048_576)
        self.assertLess(len(proposal_bytes), 1_048_576)
        active = load_scientific_workspace(self.root, "large-active.json")
        preview = self.proposals.preview_workspace_proposal(
            self.root, active, "large-proposal.json"
        )
        self.assertLess(len(preview.diff.encode("utf-8")), 1_000)

        approved = self.proposals.approve_workspace_proposal(self.root, active, preview)

        approved_path = self.root / approved.manifest_relative_path
        approved_bytes = approved_path.read_bytes()
        self.assertLessEqual(len(approved_bytes), 1_048_576)
        self.assertEqual(hashlib.sha256(approved_bytes).hexdigest(), approved.sha256)
        self.assertEqual(approved.workspace.summary.component_count, 140)
        self.assertEqual((self.root / "large-active.json").read_bytes(), active_bytes)
        self.assertEqual((self.root / "large-proposal.json").read_bytes(), proposal_bytes)

    def test_diff_escapes_unicode_format_controls_losslessly(self):
        active_path = _write_manifest(
            self.root, "unicode-active.json", title="Model A\u200bB", resource=self.resource
        )
        proposal_path = _write_manifest(
            self.root, "unicode-proposal.json", title="Model A\u200cB", resource=self.resource
        )
        active = load_scientific_workspace(self.root, active_path.name)
        preview = self.proposals.preview_workspace_proposal(
            self.root, active, proposal_path.name
        )

        self.assertIn(r"Model A\u200bB", preview.diff)
        self.assertIn(r"Model A\u200cB", preview.diff)
        self.assertNotIn("\uFFFD", preview.diff)

if __name__ == "__main__":
    unittest.main()
