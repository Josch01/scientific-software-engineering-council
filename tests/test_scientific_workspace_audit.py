"""Selected verified workspace resources are the only audit snapshot inputs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.configuration import DEFAULT_CONFIG
from scripts.scientific_workspace_audit import (
    build_workspace_audit_plan,
    run_workspace_audit,
)
from scripts.scientific_workspace_loader import load_scientific_workspace


def make_workspace(root: Path) -> tuple[object, bytes, bytes, bytes]:
    model = b'{"model":"SIR-modificado","equations":"inert"}'
    observations = b"time,I\n0,2\n1,3\n"
    unused = b"not selected for this audit"
    (root / "models").mkdir()
    (root / "data").mkdir()
    (root / "models" / "sir.json").write_bytes(model)
    (root / "data" / "observations.csv").write_bytes(observations)
    (root / "data" / "unused.csv").write_bytes(unused)
    manifest = {
        "schema_version": 1,
        "workspace_id": "sir-study",
        "title": "SIR workspace",
        "resources": [
            {"id": "model", "kind": "model_spec", "path": "models/sir.json",
             "sha256": hashlib.sha256(model).hexdigest()},
            {"id": "observations", "kind": "observations", "path": "data/observations.csv",
             "sha256": hashlib.sha256(observations).hexdigest()},
            {"id": "unused", "kind": "observations", "path": "data/unused.csv",
             "sha256": hashlib.sha256(unused).hexdigest()},
        ],
        "sections": [
            {"id": "model", "title": "Model", "components": [
                {"id": "equations", "type": "equation_view", "title": "Equations",
                 "resource_refs": ["model"], "config": {}}
            ]},
            {"id": "data", "title": "Data", "components": [
                {"id": "table", "type": "observation_table", "title": "Observed I",
                 "resource_refs": ["observations"], "config": {}}
            ]},
            {"id": "unused", "title": "Unused", "components": [
                {"id": "table2", "type": "observation_table", "title": "Unused data",
                 "resource_refs": ["unused"], "config": {}}
            ]},
        ],
    }
    (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
    return load_scientific_workspace(root, "workspace.json"), model, observations, unused


class FakeProcess:
    next_pid = 3000
    snapshots: list[tuple[str, ...]] = []
    exit_code = 0

    def __init__(self, argv, *, cwd, stdout, stderr, **kwargs):
        type(self).next_pid += 1
        self.pid = type(self).next_pid
        self.returncode = type(self).exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.snapshots.append(tuple(sorted(
            path.relative_to(cwd).as_posix() for path in Path(cwd).rglob("*")
            if path.is_file()
        )))
        stdout.write(b"fake CLI completed")
        stderr.write(b"")

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class ScientificWorkspaceAuditTests(unittest.TestCase):
    def test_plan_binds_only_selected_ids_to_workspace_and_digests(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace, _, _, _ = make_workspace(Path(folder))
            plan = build_workspace_audit_plan(workspace, ("model", "observations"))

        self.assertEqual(plan.workspace_id, "sir-study")
        self.assertEqual(tuple(item.resource_id for item in plan.resources),
                         ("model", "observations"))
        self.assertEqual(len(plan.manifest_sha256), 64)
        self.assertIn(plan.manifest_sha256, plan.task["request"])
        self.assertIn("SOFTWARE_VALIDITY", plan.task["request"])
        self.assertIn("NUMERICAL_VALIDITY", plan.task["request"])
        self.assertIn("SCIENTIFIC_VALIDITY", plan.task["request"])
        with self.assertRaises(TypeError):
            plan.task["risk"] = "R0"
        with self.assertRaises(AttributeError):
            plan.task["domains"].append("general")

    def test_unknown_or_duplicate_resource_selection_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace, _, _, _ = make_workspace(Path(folder))
            with self.assertRaisesRegex(ValueError, "unknown resource"):
                build_workspace_audit_plan(workspace, ("model", "secret"))
            with self.assertRaisesRegex(ValueError, "unique"):
                build_workspace_audit_plan(workspace, ("model", "model"))

    def test_audit_snapshots_only_selected_verified_resources_and_persists_provenance(self):
        FakeProcess.next_pid = 3000
        FakeProcess.snapshots = []
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            workspace, model, observations, unused = make_workspace(project)
            (project / "private-project-note.txt").write_text("not part of the workspace")
            config = dict(DEFAULT_CONFIG, provider_mode="gemini", audit_level="basic",
                          max_parallel_agents=1,
                          budget=dict(DEFAULT_CONFIG["budget"], max_runtime_minutes=1))

            with patch("scripts.run_agents.shutil.which", return_value="fake-gemini"), \
                    patch("scripts.run_agents.subprocess.Popen", side_effect=FakeProcess):
                report = run_workspace_audit(
                    project, workspace, ("model", "observations"), config,
                    accept_unmetered_cost=True,
                )

            self.assertEqual(report["execution"], "PROCESSES_COMPLETED_NOT_AUDITED")
            self.assertEqual(report["release_status"], "NOT_APPROVED")
            self.assertTrue(report["workspace_audit"]["manifest_sha256"])
            self.assertEqual(
                [item["id"] for item in report["workspace_audit"]["resources"]],
                ["model", "observations"],
            )
            self.assertTrue(FakeProcess.snapshots)
            for snapshot in FakeProcess.snapshots:
                self.assertIn("models/sir.json", snapshot)
                self.assertIn("data/observations.csv", snapshot)
                self.assertIn("ssec-workspace-context.json", snapshot)
                self.assertNotIn("data/unused.csv", snapshot)
                self.assertNotIn("private-project-note.txt", snapshot)
            saved = Path(report["log_dir"]) / "run_summary.json"
            persisted = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(persisted["execution"], "PROCESSES_COMPLETED_NOT_AUDITED")
            self.assertEqual(persisted["workspace_audit"]["workspace_id"], "sir-study")

    def test_resource_excluded_by_runner_policy_blocks_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            secret = b"explicitly selected input, but runner excludes .env files"
            (project / ".env").write_bytes(secret)
            manifest = {
                "schema_version": 1,
                "workspace_id": "excluded-input",
                "title": "Excluded input",
                "resources": [{
                    "id": "excluded", "kind": "model_spec", "path": ".env",
                    "sha256": hashlib.sha256(secret).hexdigest(),
                }],
                "sections": [{"id": "section", "title": "Section", "components": [{
                    "id": "component", "type": "equation_view", "title": "Input",
                    "resource_refs": ["excluded"], "config": {},
                }]}],
            }
            (project / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
            workspace = load_scientific_workspace(project, "workspace.json")
            with patch("scripts.run_agents.execute") as execute:
                with self.assertRaisesRegex(ValueError, "does not match runner snapshot policy"):
                    run_workspace_audit(
                        project, workspace, ("excluded",), DEFAULT_CONFIG,
                        accept_unmetered_cost=True,
                    )
            execute.assert_not_called()

    def test_resource_cannot_overwrite_reserved_workspace_context(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            workspace, _, _, _ = make_workspace(project)
            manifest = json.loads((project / "workspace.json").read_text(encoding="utf-8"))
            content = b"selected resource must not collide with generated context"
            context_name = "ssec-workspace-context.json"
            (project / context_name).write_bytes(content)
            manifest["resources"][0]["path"] = context_name
            manifest["resources"][0]["sha256"] = hashlib.sha256(content).hexdigest()
            (project / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
            workspace = load_scientific_workspace(project, "workspace.json")
            with patch("scripts.run_agents.execute") as execute:
                with self.assertRaisesRegex(ValueError, "reserved staging path"):
                    run_workspace_audit(
                        project, workspace, ("model",), DEFAULT_CONFIG,
                        accept_unmetered_cost=True,
                    )
            execute.assert_not_called()

    def test_cost_ack_is_required_before_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            workspace, _, _, _ = make_workspace(project)
            with patch("scripts.run_agents.execute") as execute:
                with self.assertRaisesRegex(ValueError, "cost|coste|ACK"):
                    run_workspace_audit(
                        project, workspace, ("model",), DEFAULT_CONFIG,
                        accept_unmetered_cost=False,
                    )
            execute.assert_not_called()

    def test_worker_failure_is_persisted_without_approval(self):
        FakeProcess.exit_code = 1
        try:
            with tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                workspace, _, _, _ = make_workspace(project)
                config = dict(DEFAULT_CONFIG, provider_mode="gemini", audit_level="basic",
                              max_parallel_agents=1,
                              budget=dict(DEFAULT_CONFIG["budget"], max_runtime_minutes=1))
                with patch("scripts.run_agents.shutil.which", return_value="fake-gemini"), \
                        patch("scripts.run_agents.subprocess.Popen", side_effect=FakeProcess):
                    report = run_workspace_audit(
                        project, workspace, ("model",), config,
                        accept_unmetered_cost=True,
                    )
                self.assertEqual(report["execution"], "PARTIAL_OR_FAILED")
                self.assertEqual(report["release_status"], "NOT_APPROVED")
                persisted = json.loads(
                    (Path(report["log_dir"]) / "run_summary.json").read_text(encoding="utf-8")
                )
                self.assertEqual(persisted["execution"], "PARTIAL_OR_FAILED")
                self.assertEqual(persisted["release_status"], "NOT_APPROVED")
        finally:
            FakeProcess.exit_code = 0

    def test_cancel_before_launch_stops_workers_and_persists_cancelled_state(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            workspace, _, _, _ = make_workspace(project)
            cancel_file = project / "cancel.requested"
            cancel_file.write_text("cancel", encoding="utf-8")
            config = dict(DEFAULT_CONFIG, provider_mode="gemini", audit_level="basic",
                          max_parallel_agents=1,
                          budget=dict(DEFAULT_CONFIG["budget"], max_runtime_minutes=1))
            with patch("scripts.run_agents.subprocess.Popen") as popen:
                report = run_workspace_audit(
                    project, workspace, ("model",), config,
                    accept_unmetered_cost=True,
                    cancel_file=cancel_file,
                )
            self.assertEqual(report["execution"], "CANCELLED")
            self.assertEqual(report["release_status"], "NOT_APPROVED")
            self.assertTrue(report["workspace_audit"]["cancellation_requested"])
            self.assertEqual(report["results"], [])
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
