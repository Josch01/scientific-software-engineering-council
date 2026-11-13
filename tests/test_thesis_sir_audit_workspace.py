from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.thesis_sir_model import (
    HarmonicTerm,
    ThesisSIRParameters,
    WeeklyCountObservations,
    evaluate_thesis_sir_weekly_counts,
)
from scripts.scientific_workspace_loader import load_scientific_workspace
from scripts.scientific_workspace_view import build_workspace_view_model


def _fixture():
    source_bytes = json.dumps({
        "week_by_week_comparison": [
            {"week": f"2022-SE{week:02d}", "DGE_monday_sunday_candidate": count,
             "DGE_sunday_saturday": 9000}
            for week, count in enumerate((100, 120, 140, 160), start=1)
        ]
    }, sort_keys=True).encode("utf-8")
    observations = WeeklyCountObservations(
        tuple(f"2022-SE{week:02d}" for week in range(1, 5)),
        (100, 120, 140, 160),
        "DGE_monday_sunday_candidate",
        hashlib.sha256(source_bytes).hexdigest(),
    )
    parameters = ThesisSIRParameters(
        d0=0.0,
        harmonics=(HarmonicTerm(0.1, 0.0, 0.5),),
        gamma=0.1,
        log10_initial_infectious=3.0,
        susceptible_fraction=0.999,
        ascertainment_fraction=0.1,
        delay_days=4.3,
    )
    result = evaluate_thesis_sir_weekly_counts(
        parameters, observations, max_step=0.1, max_steps_per_interval=20
    ).to_dict()
    return source_bytes, observations, parameters, result


class ThesisSirAuditWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)

    def test_bundle_is_digest_verified_renderable_and_contains_only_selected_data(self):
        from scripts.thesis_sir_audit_workspace import write_thesis_sir_audit_workspace

        source_bytes, observations, parameters, result = _fixture()
        source_before = bytes(source_bytes)
        root = write_thesis_sir_audit_workspace(
            self.parent, observations, parameters, result
        )

        loaded = load_scientific_workspace(root, "workspace.json")
        view = build_workspace_view_model(loaded)
        by_id = {resource.resource_id: resource for resource in loaded.resources}
        observation_doc = json.loads(by_id["sir_observations"].content)
        result_doc = json.loads(by_id["sir_result"].content)

        self.assertEqual(len(loaded.resources), 5)
        components = tuple(
            item for section in view.sections for item in section.components
        )
        self.assertEqual({item.status for item in components}, {"ok"})
        self.assertEqual(observation_doc["counts"], [100, 120, 140, 160])
        self.assertEqual(observation_doc["series_id"], "DGE_monday_sunday_candidate")
        self.assertNotIn(b"DGE_sunday_saturday", by_id["sir_observations"].content)
        self.assertNotIn(source_bytes, [resource.content for resource in loaded.resources])
        self.assertEqual(result_doc["result"], result)
        self.assertEqual(by_id["sir_model"].sha256,
                         loaded.to_dict()["resources"][0]["sha256"])
        root_dir = Path(__file__).resolve().parents[1] / "scripts"
        self.assertEqual(by_id["sir_engine"].content,
                         (root_dir / "thesis_sir_model.py").read_bytes())
        self.assertEqual(by_id["sir_data_adapter"].content,
                         (root_dir / "thesis_sir_data.py").read_bytes())
        self.assertEqual(source_bytes, source_before)
        self.assertFalse((root / "original_reconstruction.json").exists())

    def test_rejects_result_that_does_not_match_declared_parameters_or_observations(self):
        from scripts.thesis_sir_audit_workspace import write_thesis_sir_audit_workspace

        _source, observations, parameters, result = _fixture()
        stale = dict(result)
        stale["model"] = {"schema_version": 1, "model_type": "sir"}

        with self.assertRaisesRegex(ValueError, "model does not match"):
            write_thesis_sir_audit_workspace(self.parent, observations, parameters, stale)
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_existing_destination_is_never_overwritten(self):
        from scripts.thesis_sir_audit_workspace import write_thesis_sir_audit_workspace

        _source, observations, parameters, result = _fixture()
        fixed = uuid.UUID("12345678123456781234567812345678")
        destination = self.parent / "ssec-thesis-sir-audit-123456781234"
        destination.mkdir()
        sentinel = destination / "keep.txt"
        sentinel.write_text("existing", encoding="utf-8")

        with patch("scripts.thesis_sir_audit_workspace.uuid.uuid4", side_effect=(fixed, fixed)):
            with self.assertRaisesRegex(FileExistsError, "no files were overwritten"):
                write_thesis_sir_audit_workspace(
                    self.parent, observations, parameters, result
                )

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing")
        self.assertEqual(sorted(path.name for path in self.parent.iterdir()), [destination.name])

    def test_rejects_uncomputed_results_without_creating_a_workspace(self):
        from scripts.thesis_sir_audit_workspace import write_thesis_sir_audit_workspace

        _source, observations, parameters, result = _fixture()
        result["analysis_execution"] = "NOT_APPROVED"

        with self.assertRaisesRegex(ValueError, "computed result"):
            write_thesis_sir_audit_workspace(self.parent, observations, parameters, result)
        self.assertEqual(list(self.parent.iterdir()), [])

