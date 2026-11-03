"""Real Git/process integration contracts; synthetic reviews are schema fixtures only."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from scripts.check_runner import capture_snapshot, read_check_manifest, run_checks, snapshot_artifact_sha256
from scripts.configuration import DEFAULT_CONFIG
from scripts.execution_evidence import candidate_tree_sha256
from scripts.prepare_agents import choose_roles
from scripts.review_evidence import report_sha256, validate_review_manifest
from scripts.worktree_coordinator import gate, initialize, load
from tests.test_work_items import work_item


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True).stdout.decode().strip()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class IntegrationCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Integration Test")
        git(self.root, "config", "user.email", "integration@example.invalid")
        git(self.root, "config", "core.autocrlf", "false")
        (self.root / ".gitignore").write_text("__pycache__/\n*.ignored\n", encoding="utf-8")
        (self.root / "baseline.txt").write_bytes(b"base\n")
        (self.root / "tests").mkdir()
        (self.root / "tests/__init__.py").write_text("", encoding="utf-8")
        (self.root / "tests/test_base.py").write_text(
            "import unittest\nclass Base(unittest.TestCase):\n def test_true(self): self.assertTrue(True)\n",
            encoding="utf-8")
        self.task = dict(task_id="integration-test", kind="build", request="Implement changes",
                         domains=["general"], languages=["python"], interfaces=["cli"],
                         targets=["linux"], risk="R1", runtime={}, check_specs=[
            dict(check_id="unit_tests", argv=[sys.executable, "-P", "-m", "unittest", "discover",
                                             "-s", "tests", "-t", "."], cwd=".",
                 timeout_seconds=20, protocol="unittest"),
            dict(check_id="static_analysis", argv=[sys.executable, "-c", "print('checked')"],
                 cwd=".", timeout_seconds=20, protocol="exit_code")])
        policy = dict(DEFAULT_CONFIG, provider_mode="both", audit_level="basic")
        roles, reviewers, _ = choose_roles(self.task, policy)
        self.task["work_items"] = [work_item(role, outputs=[role + "/"],
            required_reviewers=reviewers, tests=["unit_tests", "static_analysis"]) for role in roles]
        for role in roles:
            (self.root / role).mkdir()
            (self.root / role / "old.txt").write_text("old\n", encoding="utf-8")
            (self.root / role / "edit.txt").write_text("original\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.state = initialize(self.task, policy, self.root, apply=True)
        _, self.meta = load(self.root, self.task["task_id"])
        self.meta = self.meta.resolve()
        self.run_id = "launch-run-1"
        self.reviews = []
        self.checks = []
        for worker in self.state["workers"]:
            folder = Path(worker["path"]) / worker["role"]
            (folder / "edit.txt").write_text("changed " + worker["role"] + "\n", encoding="utf-8")
            (folder / "old.txt").unlink()
            (folder / "new.txt").write_text("new\n", encoding="utf-8")
            (folder / "skip.ignored").write_text("ignored\n", encoding="utf-8")

    def evidence(self, *, check_transform=None, distinct_reviewer_checks=False):
        """Run real local checks, then create untrusted review-schema fixtures."""
        for worker in self.state["workers"]:
            checked = run_checks(self.task, self.state, worker, self.meta,
                                 stop_event=threading.Event(), deadline=time.monotonic() + 60)
            self.assertEqual(checked.status, "PASSED", checked.errors)
            self.checks.append(checked.manifest_path)
            if check_transform:
                data = json.loads(checked.manifest_path.read_text())
                check_transform(data)
                checked.manifest_path.write_text(json.dumps(data), encoding="utf-8")
            check = read_check_manifest(checked.manifest_path, self.meta)
            for index, reviewer in enumerate(self.state["review_roles"]):
                if distinct_reviewer_checks and index:
                    checked = run_checks(self.task, self.state, worker, self.meta,
                        stop_event=threading.Event(), deadline=time.monotonic() + 60)
                    self.assertEqual(checked.status, "PASSED", checked.errors)
                    check = read_check_manifest(checked.manifest_path, self.meta)
                directory = self.meta / "dev-logs" / self.run_id / "reviews" / worker["role"] / reviewer
                directory.mkdir(parents=True)
                snapshot = capture_snapshot(Path(worker["path"]), directory / "snapshot")
                diff = "fixture-only diff\n"
                identity = {key: check[key] for key in ("task_id", "task_revision", "task_sha256",
                            "base_commit", "worker_role", "candidate_tree_sha256")}
                identity.update(diff_sha256=hashlib.sha256(diff.encode()).hexdigest(),
                                check_manifest_sha256=digest(checked.manifest_path))
                report = dict(schema_version=1, **identity, verdict="PASS", summary="Schema fixture", findings=[])
                input_data = dict(schema_version=1, identity=identity, reviewer_role=reviewer,
                    requested_provider="gemini", diff=diff,
                    prompt="Review\n<<<SSEC_DIFF_BEGIN>>>\n" + diff + "<<<SSEC_DIFF_END>>>\n")
                (directory / "input.json").write_text(json.dumps(input_data), encoding="utf-8")
                (directory / "stdout.jsonl").write_text(json.dumps(dict(type="message", role="assistant",
                    content=json.dumps(report))) + "\n" + json.dumps(dict(type="result", status="success", stats={})) + "\n",
                    encoding="utf-8")
                (directory / "stderr.log").write_bytes(b"")
                manifest = dict(schema_version=1, status="PASSED", **identity,
                    check_manifest_path=checked.manifest_path.relative_to(self.meta).as_posix(),
                    reviewer_role=reviewer, reviewer_provider="gemini", runtime_run_id="fixture-run",
                    runtime_adapter_type="scripts.provider_runtimes.GeminiRuntime",
                    review_independence="UNVERIFIED_WITHOUT_PROVIDER_E2E", observed_provider="gemini",
                    provider_session_id="fixture-session", verdict="PASS", review_report=report,
                    review_report_sha256=report_sha256(report),
                    snapshot_path=snapshot.snapshot_path.relative_to(self.meta).as_posix(),
                    review_snapshot_tree_sha256=snapshot.snapshot_tree_sha256,
                    snapshot_artifact_sha256_before=snapshot_artifact_sha256(snapshot.snapshot_path),
                    snapshot_artifact_sha256_after=snapshot_artifact_sha256(snapshot.snapshot_path),
                    started_at_utc="2026-11-02T00:00:00Z", finished_at_utc="2026-11-02T00:00:00Z",
                    exit_code=0, sandbox_effective=None, error=None)
                for label, filename in (("input", "input.json"), ("stdout", "stdout.jsonl"), ("stderr", "stderr.log")):
                    manifest[label + "_path"] = (directory / filename).relative_to(self.meta).as_posix()
                    manifest[label + "_sha256"] = digest(directory / filename)
                validate_review_manifest(manifest, self.meta)
                path = directory / "manifest.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                self.reviews.append(path)

    def build(self, run_id=None):
        from scripts.integration_candidate import build_integration_candidate
        return build_integration_candidate(self.root, self.task["task_id"], run_id or self.run_id)

    def add_integration_probe(self, code, *, timeout=20):
        """Add a real Python check that is meaningful on the composed candidate."""
        from scripts.execution_evidence import canonical_task_sha256
        spec = next(item for item in self.state["task_packet"]["check_specs"]
                    if item["check_id"] == "static_analysis")
        spec["argv"] = [sys.executable, "-c", code]
        spec["timeout_seconds"] = timeout
        self.task = self.state["task_packet"]
        self.state["task_sha256"] = canonical_task_sha256(self.task)
        (self.meta / "state.json").write_text(json.dumps(self.state), encoding="utf-8")

    def combined_candidate_probe(self):
        role_paths = repr([worker["role"] + "/new.txt" for worker in self.state["workers"]])
        return ("from pathlib import Path; import sys; "
                f"paths={role_paths}; "
                "sys.exit(0 if Path.cwd().parent.name != 'integration_candidate' or "
                "all(Path(p).is_file() for p in paths) else 17)")

    def blocked(self, text=None, run_id=None):
        before = git(self.root, "worktree", "list", "--porcelain")
        result = self.build(run_id)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertTrue(result.blockers)
        if text:
            self.assertIn(text.casefold(), " ".join(result.blockers).casefold())
        self.assertIsNone(result.candidate_worktree_path)
        self.assertEqual(git(self.root, "worktree", "list", "--porcelain"), before)

    def test_missing_run_and_unsafe_run_id_block_before_worktree_creation(self):
        self.blocked()
        for run_id in ("../escape", "/absolute", "C:drive", "bad/name", "bad\\name"):
            with self.subTest(run_id=run_id):
                self.blocked(run_id=run_id)

    def test_legacy_packet_blocks_with_clear_contract_requirement(self):
        from scripts.execution_evidence import canonical_task_sha256
        self.state["task_packet"].pop("work_items")
        self.state["task_sha256"] = canonical_task_sha256(self.state["task_packet"])
        (self.meta / "state.json").write_text(json.dumps(self.state), encoding="utf-8")
        self.blocked("work_items")

    def test_disjoint_overlay_is_deterministic_uncommitted_and_does_not_mutate_inputs(self):
        self.evidence()
        source = candidate_tree_sha256(self.root), git(self.root, "status", "--porcelain=v1")
        workers = [(candidate_tree_sha256(Path(w["path"])), git(Path(w["path"]), "status", "--porcelain=v1"))
                   for w in self.state["workers"]]
        first, second = self.build(), self.build()
        for result in (first, second):
            self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)
            self.assertIsNotNone(result.check_manifest_path)
            self.assertFalse(hasattr(result, "release_status"))
            tree = Path(result.candidate_worktree_path)
            self.assertEqual(git(tree, "rev-parse", "HEAD"), self.state["base_commit"])
            self.assertTrue(git(tree, "diff", "--cached", "--name-only"))
            for w in self.state["workers"]:
                self.assertEqual((tree / w["role"] / "new.txt").read_text(), "new\n")
                self.assertFalse((tree / w["role"] / "old.txt").exists())
                self.assertFalse((tree / w["role"] / "skip.ignored").exists())
            data = json.loads(Path(result.integration_manifest_path).read_text())
            self.assertEqual(data["schema_version"], 2)
            self.assertEqual(data["status"], "CHECKED_AWAITING_INTEGRATED_REVIEW")
            self.assertIsNotNone(data["check_manifest_path"])
            self.assertEqual(data["check_manifest_sha256"], digest(result.check_manifest_path))
            self.assertEqual(data["candidate_tree_sha256"], candidate_tree_sha256(tree))
            self.assertEqual(len(data["worker_tree_hashes"]), len(self.state["workers"]))
            self.assertTrue(data["input_manifests"])
            self.assertEqual(data["operations"], sorted(data["operations"], key=lambda x: (x["role"], x["path"])))
            for item in data["input_manifests"]:
                self.assertEqual(item["sha256"], digest(self.meta / item["path"]))
        self.assertNotEqual(first.integration_id, second.integration_id)
        self.assertNotEqual(first.candidate_worktree_path, second.candidate_worktree_path)
        self.assertEqual(candidate_tree_sha256(Path(first.candidate_worktree_path)),
                         candidate_tree_sha256(Path(second.candidate_worktree_path)))
        self.assertEqual((candidate_tree_sha256(self.root), git(self.root, "status", "--porcelain=v1")), source)
        self.assertEqual([(candidate_tree_sha256(Path(w["path"])), git(Path(w["path"]), "status", "--porcelain=v1"))
                          for w in self.state["workers"]], workers)

    def test_integrated_checks_run_against_composed_candidate_and_gate_stays_blocked(self):
        self.add_integration_probe(self.combined_candidate_probe())
        self.evidence()

        result = self.build()

        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)
        self.assertIsNotNone(result.check_manifest_path)
        integration = json.loads(Path(result.integration_manifest_path).read_text(encoding="utf-8"))
        check_path = Path(result.check_manifest_path)
        checked = read_check_manifest(check_path, self.meta)
        self.assertEqual(integration["schema_version"], 2)
        self.assertEqual(integration["status"], result.status)
        self.assertEqual(integration["integration_role"], "integration_candidate")
        self.assertEqual(integration["candidate_branch"], checked["worker_branch"])
        self.assertEqual(integration["check_manifest_path"], check_path.relative_to(self.meta).as_posix())
        self.assertEqual(integration["check_manifest_sha256"], digest(check_path))
        self.assertEqual(integration["candidate_tree_sha256"], checked["candidate_tree_sha256"])
        self.assertEqual(integration["check_specs"], [
            dict(check_id=spec["check_id"], argv=spec["argv"], cwd=spec["cwd"],
                 timeout_seconds=spec["timeout_seconds"], protocol=spec["protocol"])
            for spec in self.task["check_specs"]])
        self.assertEqual(checked["worker_role"], "integration_candidate")
        self.assertTrue(all(item["result_status"] == "PASSED" for item in checked["checks"]))

        result_gate = gate(self.root, self.task["task_id"])

        self.assertEqual(result_gate["status"], "BLOCKED")
        self.assertTrue(result_gate["integrated_checks_verified"], result_gate)
        self.assertEqual(result_gate["integrated_check_status"], "PASSED")
        self.assertFalse(result_gate["evidence_verified"])
        self.assertEqual(result_gate["release_status"], "NOT_APPROVED")
        self.assertFalse(result_gate["automatic_merge"])
        self.assertTrue(any("integrated review" in item.casefold() and "human approval" in item.casefold()
                            for item in result_gate["blockers"]))

    def test_integration_only_failure_is_terminal_failed_even_when_workers_pass(self):
        failure = ("from pathlib import Path; import sys; "
                   "sys.exit(23 if Path.cwd().parent.name == 'integration_candidate' else 0)")
        self.add_integration_probe(failure)
        self.evidence()

        result = self.build()

        self.assertEqual(result.status, "FAILED", result.blockers)
        self.assertIsNotNone(result.check_manifest_path)
        integration = json.loads(Path(result.integration_manifest_path).read_text(encoding="utf-8"))
        checked = read_check_manifest(Path(result.check_manifest_path), self.meta)
        self.assertEqual(integration["status"], "FAILED")
        self.assertEqual(checked["status"], "FAILED")
        self.assertEqual(checked["worker_role"], "integration_candidate")
        self.assertEqual(checked["checks"][-1]["result_status"], "FAILED")
        self.assertFalse(gate(self.root, self.task["task_id"])["integrated_checks_verified"])

    def test_candidate_mutation_after_integrated_check_invalidates_gate_evidence(self):
        self.evidence()
        result = self.build()
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)

        (Path(result.candidate_worktree_path) / "baseline.txt").write_text("post-check mutation\n", encoding="utf-8")
        result_gate = gate(self.root, self.task["task_id"])

        self.assertFalse(result_gate["integrated_checks_verified"])
        self.assertTrue(result_gate["invalid_integration_manifests"])
        self.assertEqual(result_gate["status"], "BLOCKED")

    def test_integrated_manifest_and_check_identity_tampering_are_rejected_by_gate(self):
        self.evidence()
        result = self.build()
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)
        manifest_path = Path(result.integration_manifest_path)
        check_path = Path(result.check_manifest_path)
        good_manifest = manifest_path.read_bytes()
        good_check = check_path.read_bytes()

        mutations = (
            ("missing check path", lambda data: data.update(check_manifest_path=None)),
            ("path escape", lambda data: data.update(check_manifest_path="../escape")),
            ("wrong role", lambda data: data.update(integration_role="worker")),
            ("wrong branch", lambda data: data.update(candidate_branch="ssec/integration/wrong")),
            ("wrong base", lambda data: data.update(base_commit="f" * 40)),
            ("invented worker tree hash", lambda data: data["worker_tree_hashes"].update(
                {next(iter(data["worker_tree_hashes"])): "f" * 64})),
            ("empty required input bindings", lambda data: data.update(input_manifests=[])),
            ("missing reviewer binding", lambda data: data.update(input_manifests=[
                item for item in data["input_manifests"] if item["kind"] != "review"])),
            ("wrong execution binding", lambda data: data.update(execution_id="another-launch")),
            ("wrong worker binding", lambda data: data["input_manifests"][0].update(
                role=next(role for role in self.state["workers"]
                          if role["role"] != data["input_manifests"][0]["role"])["role"])),
            ("extra check spec", lambda data: data["check_specs"].append(
                dict(check_id="extra", argv=[sys.executable, "-c", "pass"], cwd=".",
                     timeout_seconds=1, protocol="exit_code"))),
            ("incomplete check specs", lambda data: data.update(check_specs=data["check_specs"][:-1])),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                data = json.loads(good_manifest)
                mutate(data)
                manifest_path.write_text(json.dumps(data), encoding="utf-8")
                result_gate = gate(self.root, self.task["task_id"])
                self.assertFalse(result_gate["integrated_checks_verified"])
                self.assertTrue(result_gate["invalid_integration_manifests"])
            manifest_path.write_bytes(good_manifest)

        for field, value in (("worker_role", "worker"), ("worker_branch", "wrong-branch"),
                             ("base_commit", "f" * 40)):
            with self.subTest(check_identity=field):
                data = json.loads(good_check)
                data[field] = value
                check_path.write_text(json.dumps(data), encoding="utf-8")
                integration = json.loads(good_manifest)
                integration["check_manifest_sha256"] = digest(check_path)
                manifest_path.write_text(json.dumps(integration), encoding="utf-8")
                result_gate = gate(self.root, self.task["task_id"])
                self.assertFalse(result_gate["integrated_checks_verified"])
                self.assertTrue(result_gate["invalid_integration_manifests"])
            check_path.write_bytes(good_check)
            manifest_path.write_bytes(good_manifest)

        check_path.write_bytes(good_check + b" ")
        result_gate = gate(self.root, self.task["task_id"])
        self.assertFalse(result_gate["integrated_checks_verified"])
        self.assertTrue(result_gate["invalid_integration_manifests"])
        check_path.write_bytes(good_check)

        check_path.unlink()
        result_gate = gate(self.root, self.task["task_id"])
        self.assertFalse(result_gate["integrated_checks_verified"])
        self.assertTrue(result_gate["invalid_integration_manifests"])
        check_path.write_bytes(good_check)

    def test_integrated_manifest_readback_failure_never_reports_checked(self):
        self.evidence()
        from scripts.integration_candidate import _json_file
        original_json_file = _json_file

        def fail_checked_readback(path):
            data = original_json_file(path)
            if data.get("status") == "CHECKED_AWAITING_INTEGRATED_REVIEW":
                raise OSError("injected integrated manifest readback failure")
            return data

        with patch("scripts.integration_candidate._json_file", side_effect=fail_checked_readback):
            result = self.build()

        self.assertNotEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW")
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(result.candidate_worktree_path and Path(result.candidate_worktree_path).is_dir())
        self.assertTrue(result.check_manifest_path and Path(result.check_manifest_path).is_file())
        result_gate = gate(self.root, self.task["task_id"])
        self.assertFalse(result_gate["integrated_checks_verified"])

    def test_integration_manifest_rejects_metadata_reparse_path(self):
        from scripts.integration_candidate import validate_integration_manifest
        metadata_alias = Path(self.temp.name) / "metadata-alias"
        if os.name == "nt":
            completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(metadata_alias), str(self.meta)],
                                       capture_output=True)
            if completed.returncode:
                self.skipTest("metadata junction creation unavailable")
        else:
            try:
                metadata_alias.symlink_to(self.meta, target_is_directory=True)
            except OSError as exc:
                self.skipTest("metadata symlink creation unavailable: " + str(exc))

        with self.assertRaisesRegex(ValueError, "symlinked or reparse path component"):
            validate_integration_manifest(self.meta / "integrations" / "fake" / "manifest.json",
                                           metadata_alias, {}, ())

    def test_integrated_manifest_publication_failure_never_reports_checked(self):
        self.evidence()
        from scripts.integration_candidate import _write_atomic_manifest

        def fail_checked_publication(path, data):
            if data.get("status") == "CHECKED_AWAITING_INTEGRATED_REVIEW":
                raise OSError("injected checked manifest publication failure")
            return _write_atomic_manifest(path, data)

        with patch("scripts.integration_candidate._write_atomic_manifest", side_effect=fail_checked_publication):
            result = self.build()

        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(result.blockers)
        self.assertTrue(Path(result.integration_manifest_path).is_file())
        self.assertTrue(Path(result.check_manifest_path).is_file())
        self.assertEqual(json.loads(Path(result.integration_manifest_path).read_text())["status"],
                         "BUILT_AWAITING_CHECKS")
        self.assertFalse(gate(self.root, self.task["task_id"])["integrated_checks_verified"])

    def test_cancelled_integrated_checks_remain_failed(self):
        self.evidence()
        stop_event = threading.Event()
        stop_event.set()
        from scripts.integration_candidate import build_integration_candidate

        result = build_integration_candidate(self.root, self.task["task_id"], self.run_id,
                                             stop_event=stop_event)

        self.assertEqual(result.status, "FAILED", result.blockers)
        checked = read_check_manifest(Path(result.check_manifest_path), self.meta)
        self.assertEqual(checked["status"], "FAILED")
        self.assertTrue(all(item["result_status"] == "NOT_RUN" for item in checked["checks"]))

    def test_timed_out_integrated_check_is_terminal_failed(self):
        timeout_code = ("from pathlib import Path; import time; "
                        "time.sleep(5) if Path.cwd().parent.name == 'integration_candidate' else None")
        self.add_integration_probe(timeout_code, timeout=0.15)
        self.evidence()

        result = self.build()

        self.assertEqual(result.status, "FAILED", result.blockers)
        checked = read_check_manifest(Path(result.check_manifest_path), self.meta)
        self.assertEqual(checked["status"], "FAILED")
        self.assertEqual(checked["checks"][-1]["result_status"], "FAILED")
        self.assertIn("timed_out", checked["checks"][-1]["record"]["process_status"])

    def test_crash_after_built_publication_cannot_pass_gate(self):
        self.evidence()
        previous = self.build()
        self.assertEqual(previous.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", previous.blockers)
        with patch("scripts.integration_candidate.run_checks", side_effect=SystemExit("simulated process crash")):
            with self.assertRaisesRegex(SystemExit, "simulated process crash"):
                self.build()

        attempts = sorted((self.meta / "integrations").iterdir(), key=lambda item: item.name)
        latest_manifest = attempts[-1] / "manifest.json"
        data = json.loads(latest_manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "BUILT_AWAITING_CHECKS")
        result_gate = gate(self.root, self.task["task_id"])
        self.assertFalse(result_gate["integrated_checks_verified"])
        self.assertTrue(result_gate["invalid_integration_manifests"])
        self.assertTrue(any("terminal check manifest" in item["error"]
                            for item in result_gate["invalid_integration_manifests"]))

    def test_invalid_historical_attempt_does_not_hide_latest_valid_integrated_checks(self):
        self.evidence()
        latest = self.build()
        self.assertEqual(latest.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", latest.blockers)

        historical_id = "v2-00000000000000000000-" + "0" * 32
        historical = self.meta / "integrations" / historical_id
        historical.mkdir()
        (historical / "manifest.json").write_text("{}", encoding="utf-8")

        result_gate = gate(self.root, self.task["task_id"])

        self.assertTrue(result_gate["integrated_checks_verified"], result_gate)
        self.assertTrue(result_gate["invalid_integration_manifests"])
        self.assertTrue(any(item["path"].startswith("integrations/" + historical_id)
                            for item in result_gate["invalid_integration_manifests"]))
        self.assertEqual(result_gate["status"], "BLOCKED")
        self.assertFalse(any(historical_id in blocker for blocker in result_gate["blockers"]))
        self.assertFalse(any("one or more integration manifests are invalid or tampered" in blocker
                             for blocker in result_gate["blockers"]))
        self.assertTrue(any("independent integrated review and human approval" in blocker
                            for blocker in result_gate["blockers"]))

    def test_missing_reviewer_and_missing_check_are_rejected(self):
        self.evidence()
        raw = self.reviews[0].read_bytes()
        self.reviews[0].unlink()
        self.blocked()
        self.reviews[0].write_bytes(raw)
        self.checks[0].unlink()
        self.blocked()

    def test_review_selects_exact_check_manifest_despite_newer_unrelated_checks(self):
        self.evidence()
        decoy = run_checks(self.task, self.state, self.state["workers"][0], self.meta,
                           stop_event=threading.Event(), deadline=time.monotonic() + 60)
        decoy.manifest_path.write_text("corrupted newer check run", encoding="utf-8")
        result = self.build()
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)

    def test_all_required_reviewers_must_reference_one_check_manifest(self):
        from scripts.execution_evidence import canonical_task_sha256
        reviewers = ["software_auditor", "independent_reviewer"]
        self.state["audit_level"] = "standard"
        self.state["review_roles"] = reviewers
        self.state["required_evidence"].append("independent_review")
        for item in self.state["task_packet"]["work_items"]:
            item["required_reviewers"] = reviewers
        self.task = self.state["task_packet"]
        self.state["task_sha256"] = canonical_task_sha256(self.task)
        (self.meta / "state.json").write_text(json.dumps(self.state), encoding="utf-8")
        self.evidence(distinct_reviewer_checks=True)
        self.blocked("same check manifest")

    def test_tampered_manifest_logs_snapshot_and_check_binding_are_rejected(self):
        self.evidence()
        review = json.loads(self.reviews[0].read_text())
        paths = [self.checks[0], self.meta / review["stdout_path"], self.meta / review["input_path"],
                 self.meta / review["snapshot_path"] / "baseline.txt"]
        for path in paths:
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.subTest(path=path):
                self.blocked()
            path.write_bytes(original)

    def test_failed_stale_mismatched_or_incomplete_reviews_are_rejected(self):
        self.evidence()
        original = self.reviews[0].read_bytes()
        for changes in (dict(status="FAILED"), dict(status="NOT_RUN"), dict(verdict="BLOCKED"),
                        dict(task_revision="stale"), dict(task_id="other-task"), dict(task_sha256="f" * 64),
                        dict(base_commit="f" * 40), dict(worker_role="other_worker"),
                        dict(reviewer_role="other_reviewer"), dict(candidate_tree_sha256="f" * 64),
                        dict(check_manifest_sha256="f" * 64), dict(check_manifest_path="../escape")):
            data = json.loads(original)
            data.update(changes)
            self.reviews[0].write_text(json.dumps(data), encoding="utf-8")
            with self.subTest(changes=changes):
                self.blocked()
        data = json.loads(original)
        del data["check_manifest_path"]
        self.reviews[0].write_text(json.dumps(data), encoding="utf-8")
        self.blocked()

    def test_current_worker_tree_branch_and_source_drift_block(self):
        self.evidence()
        worker = self.state["workers"][0]
        target = Path(worker["path"]) / worker["role"] / "new.txt"
        original = target.read_bytes()
        target.write_text("drift\n", encoding="utf-8")
        self.blocked()
        target.write_bytes(original)
        git(Path(worker["path"]), "checkout", "--detach")
        self.blocked()
        git(Path(worker["path"]), "checkout", worker["branch"])
        (self.root / "baseline.txt").write_text("source changed\n", encoding="utf-8")
        self.blocked()

    def test_unowned_and_undeclared_output_changes_block_even_with_current_evidence(self):
        worker = self.state["workers"][0]
        (Path(worker["path"]) / "baseline.txt").write_text("unowned\n", encoding="utf-8")
        self.evidence()
        self.blocked("ownership")

    def test_ownership_does_not_grant_undeclared_output_scope(self):
        from scripts.execution_evidence import canonical_task_sha256
        for item in self.state["task_packet"]["work_items"]:
            item["outputs"] = [item["role"] + "/new.txt"]
        self.state["task_sha256"] = canonical_task_sha256(self.state["task_packet"])
        self.task = self.state["task_packet"]
        (self.meta / "state.json").write_text(json.dumps(self.state), encoding="utf-8")
        self.evidence()
        self.blocked("output")

    def test_actual_casefold_and_ancestor_output_collisions_block(self):
        worker = self.state["workers"][0]
        folder = Path(worker["path"]) / worker["role"]
        # A removed base file plus an added descendant is an ancestor operation conflict.
        (folder / "old.txt").mkdir()
        (folder / "old.txt/child.txt").write_text("child\n", encoding="utf-8")
        # Stage the type replacement so existing tree hashing sees the valid tree.
        git(Path(worker["path"]), "add", "-A")
        self.evidence()
        self.blocked("collision")

    @unittest.skipIf(os.name == "nt", "case-distinct sibling files require a case-sensitive filesystem")
    def test_casefold_sibling_collision_blocks(self):
        worker = self.state["workers"][0]
        (Path(worker["path"]) / worker["role"] / "NEW.txt").write_text("collision\n", encoding="utf-8")
        self.evidence()
        self.blocked("collision")

    def test_exact_cross_role_ownership_collision_blocks(self):
        from scripts.execution_evidence import canonical_task_sha256
        for item in self.state["task_packet"]["work_items"]:
            item.update(outputs=["shared/"], file_ownership=["shared/"])
        self.state["task_sha256"] = canonical_task_sha256(self.state["task_packet"])
        (self.meta / "state.json").write_text(json.dumps(self.state), encoding="utf-8")
        self.blocked("overlap")

    def test_binary_output_is_rejected(self):
        worker = self.state["workers"][0]
        (Path(worker["path"]) / worker["role"] / "new.txt").write_bytes(b"binary\x00content")
        self.evidence()
        self.blocked("binary")

    def test_complete_declared_check_set_is_required(self):
        self.evidence(check_transform=lambda data: data["checks"].pop())
        self.blocked("check")

    def test_passing_check_command_must_match_declared_spec(self):
        def change_command(data):
            item = data["checks"][-1]
            item["argv"][-1] = "print('different check')"
            item["record"]["argv"] = item["argv"]
        self.evidence(check_transform=change_command)
        self.blocked("command")

    def test_failed_check_manifest_is_rejected(self):
        self.evidence()
        data = json.loads(self.checks[0].read_text())
        data.update(status="FAILED", errors=["Check failed"])
        self.checks[0].write_text(json.dumps(data), encoding="utf-8")
        self.blocked()

    def test_unsafe_git_visible_output_path_is_rejected(self):
        worker = self.state["workers"][0]
        (Path(worker["path"]) / worker["role"] / "bad[name].txt").write_text("unsafe\n", encoding="utf-8")
        self.evidence()
        self.blocked("path")

    def test_symlink_output_is_rejected_before_candidate_creation(self):
        self.evidence()
        worker = self.state["workers"][0]
        target = Path(worker["path"]) / worker["role"] / "link.txt"
        try:
            target.symlink_to(self.root / "baseline.txt")
        except OSError as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        self.blocked("symlink")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs require POSIX")
    def test_special_output_is_rejected_without_opening_it(self):
        worker = self.state["workers"][0]
        target = Path(worker["path"]) / worker["role"] / "new.txt"
        git(Path(worker["path"]), "add", worker["role"] + "/new.txt")
        self.evidence()
        target.unlink()
        os.mkfifo(target)
        self.blocked("special")

    @unittest.skipUnless(os.name == "nt", "junctions require Windows")
    def test_junction_output_parent_is_rejected(self):
        self.evidence()
        worker = self.state["workers"][0]
        link = Path(worker["path"]) / worker["role"] / "junction"
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.root / "tests")],
                                   capture_output=True)
        if completed.returncode:
            self.skipTest("junction creation unavailable")
        self.blocked("reparse")

    @unittest.skipIf(os.name == "nt", "existing review snapshot reader cannot represent Windows Git executable bits")
    def test_executable_index_mode_is_preserved(self):
        worker = self.state["workers"][0]
        folder = Path(worker["path"])
        relative = worker["role"] + "/new.txt"
        (folder / relative).chmod((folder / relative).stat().st_mode | stat.S_IXUSR)
        git(folder, "add", relative)
        git(folder, "update-index", "--chmod=+x", relative)
        self.evidence()
        result = self.build()
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)
        self.assertTrue(git(Path(result.candidate_worktree_path), "ls-files", "--stage", relative).startswith("100755"))

    def test_overlay_preserves_exact_bytes_and_executable_index_mode_on_host(self):
        from scripts.integration_candidate import _overlay
        candidate = Path(self.temp.name) / "overlay"
        git(self.root, "worktree", "add", "-b", "overlay-test", str(candidate), self.state["base_commit"])
        content = b"#!/bin/sh\nexit 0\n"
        operations = [dict(role="local", path="run.sh", operation="write", executable=True)]
        _overlay(candidate, operations, {("local", "run.sh"): content})
        self.assertEqual((candidate / "run.sh").read_bytes(), content)
        self.assertEqual(subprocess.run(["git", "-C", str(candidate), "show", ":run.sh"],
                                       check=True, capture_output=True).stdout, content)
        self.assertTrue(git(candidate, "ls-files", "--stage", "run.sh").startswith("100755"))
        self.assertEqual(git(candidate, "rev-parse", "HEAD"), self.state["base_commit"])

    def test_unchanged_crlf_checkout_files_are_not_worker_outputs(self):
        # A clean Git checkout may differ from stored blobs on Windows.
        for worker in self.state["workers"]:
            path = Path(worker["path"]) / "baseline.txt"
            path.write_bytes(b"base\r\n")
            git(Path(worker["path"]), "config", "core.autocrlf", "true")
        self.assertTrue(all(not git(Path(w["path"]), "diff", "--name-only", "--", "baseline.txt")
                            for w in self.state["workers"]))
        self.evidence()
        result = self.build()
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)

    def test_checkout_hooks_cannot_inject_undeclared_candidate_outputs(self):
        self.evidence()
        hook = self.root / ".git/hooks/post-checkout"
        hook.write_bytes(b"#!/bin/sh\nprintf 'injected' > injected.txt\n")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        result = self.build()
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)
        self.assertFalse((Path(result.candidate_worktree_path) / "injected.txt").exists())

    def test_atomic_publication_failure_does_not_report_built(self):
        self.evidence()
        with patch("scripts.integration_candidate._write_atomic_manifest", side_effect=OSError("disk full")):
            result = self.build()
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(result.blockers)
        self.assertIsNone(result.integration_manifest_path)

    def test_staging_failure_retains_failed_artifact_without_mutating_inputs(self):
        from scripts.integration_candidate import _git
        self.evidence()
        roots = [self.root] + [Path(w["path"]) for w in self.state["workers"]]
        before = [(candidate_tree_sha256(root), git(root, "status", "--porcelain=v1")) for root in roots]
        def fail_staging(root, *args, **kwargs):
            if args[0] == "update-index":
                raise ValueError("injected staging failure")
            return _git(root, *args, **kwargs)
        with patch("scripts.integration_candidate._git", side_effect=fail_staging):
            result = self.build()
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.integration_manifest_path)
        self.assertIsNone(result.check_manifest_path)
        self.assertIn("staging failure", " ".join(result.blockers))
        self.assertTrue(Path(result.candidate_worktree_path).is_dir())
        self.assertFalse((Path(result.candidate_worktree_path).parent / "manifest.json").exists())
        self.assertEqual([(candidate_tree_sha256(root), git(root, "status", "--porcelain=v1")) for root in roots], before)

    def stale_stat_indexes(self):
        """Capture exact index bytes after changing stats, without running status."""
        indexes = {}
        for root in [self.root] + [Path(worker["path"]) for worker in self.state["workers"]]:
            target = root / "tests/test_base.py"
            info = target.stat()
            os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 10_000_000_000))
            index = Path(git(root, "--no-optional-locks", "rev-parse", "--git-path", "index"))
            if not index.is_absolute():
                index = root / index
            indexes[index] = index.read_bytes()
        return indexes

    def assert_index_bytes_unchanged(self, indexes):
        for index, original in indexes.items():
            with self.subTest(index=str(index)):
                self.assertEqual(index.read_bytes(), original, "inspection changed index bytes: " + str(index))

    def test_success_preserves_source_and_worker_index_bytes_with_stale_stats(self):
        self.evidence()
        indexes = self.stale_stat_indexes()
        result = self.build()
        # Compare index bytes before any assertion or helper invokes git status.
        self.assert_index_bytes_unchanged(indexes)
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)

    def test_blocked_build_preserves_source_and_worker_index_bytes_with_stale_stats(self):
        worker = sorted(self.state["workers"], key=lambda item: item["role"])[0]
        (Path(worker["path"]) / "unowned.txt").write_bytes(b"outside output scope\n")
        self.evidence()
        indexes = self.stale_stat_indexes()
        result = self.build()
        self.assert_index_bytes_unchanged(indexes)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("ownership", " ".join(result.blockers))
        self.assertIsNone(result.candidate_worktree_path)

    def test_candidate_mutation_after_atomic_write_leaves_no_canonical_success(self):
        from scripts.integration_candidate import _write_atomic_manifest
        self.evidence()
        written = []
        def write_then_mutate(path, data):
            _write_atomic_manifest(path, data)
            written.append(path)
            (Path(data["candidate_worktree_path"]) / "baseline.txt").write_bytes(b"publication drift\n")
        with patch("scripts.integration_candidate._write_atomic_manifest", side_effect=write_then_mutate):
            result = self.build()
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.integration_manifest_path)
        self.assertTrue(Path(result.candidate_worktree_path).is_dir())
        self.assertFalse((Path(result.candidate_worktree_path).parent / "manifest.json").exists())
        self.assertTrue(written[0].is_file(), "failed pending publication should remain inspectable")

    def test_persisted_manifest_read_failure_leaves_no_canonical_success(self):
        from scripts.integration_candidate import _json_file
        self.evidence()
        written = []
        def fail_integration_read(path):
            if Path(path).parent.parent == self.meta / "integrations":
                written.append(path)
                self.assertTrue(path.is_file())
                raise OSError("injected persisted manifest read failure")
            return _json_file(path)
        with patch("scripts.integration_candidate._json_file", side_effect=fail_integration_read):
            result = self.build()
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.integration_manifest_path)
        self.assertFalse((Path(result.candidate_worktree_path).parent / "manifest.json").exists())
        self.assertTrue(written[0].is_file())

    def test_checked_manifest_is_published_after_all_fallible_validation(self):
        self.evidence()
        def refuse_validation_after_publication(root):
            manifest = Path(root).parent / "manifest.json"
            if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8"))["status"] == "CHECKED_AWAITING_INTEGRATED_REVIEW":
                raise ValueError("candidate validation happened after checked publication")
            return candidate_tree_sha256(root)
        with patch("scripts.integration_candidate.candidate_tree_sha256",
                   side_effect=refuse_validation_after_publication):
            result = self.build()
        self.assertEqual(result.status, "CHECKED_AWAITING_INTEGRATED_REVIEW", result.blockers)
        data = json.loads(Path(result.integration_manifest_path).read_text())
        self.assertEqual(data["status"], result.status)
        self.assertEqual(data["candidate_tree_sha256"], candidate_tree_sha256(Path(result.candidate_worktree_path)))

    def test_canonical_rename_failure_leaves_no_canonical_success(self):
        self.evidence()
        original_replace = os.replace
        def fail_final_rename(source, destination):
            if Path(source).name == "manifest.pending.json" and Path(destination).name == "manifest.json":
                raise OSError("injected canonical rename failure")
            return original_replace(source, destination)
        with patch("scripts.integration_candidate.os.replace", side_effect=fail_final_rename):
            result = self.build()
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.integration_manifest_path)
        self.assertIn("canonical rename failure", " ".join(result.blockers))
        self.assertFalse((Path(result.candidate_worktree_path).parent / "manifest.json").exists())
