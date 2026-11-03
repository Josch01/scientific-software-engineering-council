import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from scripts.check_runner import _snapshot_artifact_sha256, capture_snapshot, read_check_manifest, run_checks
from scripts.execution_evidence import canonical_task_sha256
from scripts.review_evidence import (parse_review_report, report_sha256,
                                     validate_review_attempt, validate_review_manifest)
from scripts.reviewer_output import extract_final_response


IDENTITY = {
    "task_id": "task-1",
    "task_revision": "rev-2",
    "task_sha256": "a" * 64,
    "base_commit": "b" * 40,
    "worker_role": "numerical_analyst",
    "candidate_tree_sha256": "c" * 64,
    "diff_sha256": "d" * 64,
    "check_manifest_sha256": "e" * 64,
}


def report(**overrides):
    data = {
        "schema_version": 1,
        **IDENTITY,
        "verdict": "PASS",
        "summary": "Reviewed the exact candidate and check evidence.",
        "findings": [],
    }
    data.update(overrides)
    return json.dumps(data)


class ReviewEvidenceTests(unittest.TestCase):
    def test_parses_report_bound_to_exact_candidate_and_check_manifest(self):
        parsed = parse_review_report(report(), IDENTITY)

        self.assertEqual(parsed["verdict"], "PASS")
        self.assertEqual(parsed["candidate_tree_sha256"], IDENTITY["candidate_tree_sha256"])
        self.assertEqual(parsed["check_manifest_sha256"], IDENTITY["check_manifest_sha256"])

    def test_rejects_identity_mismatch_and_missing_or_extra_identity_fields(self):
        mismatched = {**IDENTITY, "candidate_tree_sha256": "f" * 64}
        with self.assertRaisesRegex(ValueError, "candidate_tree_sha256"):
            parse_review_report(report(), mismatched)

        with self.assertRaises(ValueError):
            parse_review_report(report(task_id="other-task"), IDENTITY)
        with self.assertRaises(ValueError):
            parse_review_report(report(unexpected="extra"), IDENTITY)

    def test_rejects_unknown_verdict_or_inconsistent_change_request(self):
        with self.assertRaisesRegex(ValueError, "verdict"):
            parse_review_report(report(verdict="ACCEPTED"), IDENTITY)
        with self.assertRaisesRegex(ValueError, "finding"):
            parse_review_report(report(verdict="REQUEST_CHANGES"), IDENTITY)

    def test_validates_finding_schema_severity_path_and_line(self):
        finding = {
            "id": "F-1", "severity": "HIGH", "path": "src/solver.py", "line": 12,
            "evidence": "The branch omits the zero-input case.",
            "recommendation": "Add a test and handle the boundary explicitly.",
        }
        parsed = parse_review_report(report(verdict="REQUEST_CHANGES", findings=[finding]), IDENTITY)
        self.assertEqual(parsed["findings"][0]["path"], "src/solver.py")

        for changes in ({"path": "../secret"}, {"path": "C:\\secret"},
                        {"path": "C:/x.py"}, {"path": "C:relative.py"},
                        {"path": "//server/share/x.py"},
                        {"severity": "CRITICAL"}, {"line": True}, {"line": 0},
                        {"extra": "field"}):
            bad = dict(finding, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                parse_review_report(report(verdict="REQUEST_CHANGES", findings=[bad]), IDENTITY)

    def test_rejects_duplicate_finding_ids_and_too_many_findings(self):
        finding = {"id": "F-1", "severity": "LOW", "path": "src/a.py", "line": None,
                   "evidence": "Observation.", "recommendation": "Consider a test."}
        duplicate = [finding, dict(finding, severity="INFO")]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_review_report(report(findings=duplicate), IDENTITY)
        too_many = [dict(finding, id=f"F-{i}") for i in range(101)]
        with self.assertRaisesRegex(ValueError, "too many"):
            parse_review_report(report(verdict="REQUEST_CHANGES", findings=too_many), IDENTITY)

    def test_rejects_ambiguous_malformed_and_oversized_json(self):
        duplicate_key = '{"schema_version":1,"schema_version":1}'
        for content in ("{broken", duplicate_key, " " * (128 * 1024 + 1)):
            with self.subTest(size=len(content)), self.assertRaises(ValueError):
                parse_review_report(content, IDENTITY)

    def test_rejects_invalid_identity_contract(self):
        invalid = {**IDENTITY, "worker_role": "../reviewer"}
        with self.assertRaises(ValueError):
            parse_review_report(report(), invalid)


class ReviewAttemptTests(unittest.TestCase):
    def attempt(self, **changes):
        result = {
            "schema_version": 1, "task_id": "task-1", "task_revision": "rev-2",
            "task_sha256": "a" * 64, "base_commit": "b" * 40,
            "worker_role": "numerical_analyst", "reviewer_role": "independent_reviewer",
            "requested_provider": "gemini", "runtime_run_id": "run-1",
            "runtime_adapter_type": None, "identity": None, "status": "CANCELLED",
            "review_independence": "UNVERIFIED_WITHOUT_PROVIDER_E2E",
            "started_at_utc": "2026-11-02T00:00:00Z",
            "finished_at_utc": "2026-11-02T00:00:01Z",
            "error": "review was cancelled before candidate identity was captured",
        }
        result.update(changes)
        return result

    def test_persists_valid_preparation_failure_without_complete_candidate_identity(self):
        attempt = validate_review_attempt(self.attempt())
        self.assertEqual(attempt["status"], "CANCELLED")
        self.assertIsNone(attempt["identity"])

    def test_binds_complete_candidate_identity_to_task_and_worker(self):
        attempt = self.attempt(status="FAILED", identity=IDENTITY)
        attempt.update(task_revision=IDENTITY["task_revision"],
                       task_sha256=IDENTITY["task_sha256"], base_commit=IDENTITY["base_commit"],
                       worker_role=IDENTITY["worker_role"])
        self.assertEqual(validate_review_attempt(attempt)["identity"], IDENTITY)

    def test_rejects_attempt_identity_drift_and_unknown_fields(self):
        changed = self.attempt(identity=dict(IDENTITY, worker_role="other_role"))
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_review_attempt(changed)
        with self.assertRaises(ValueError):
            validate_review_attempt(dict(self.attempt(), untrusted="extra"))


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()


class ReviewManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.name", "Review Evidence Test")
        _git(self.repo, "config", "user.email", "review@example.invalid")
        (self.repo / "candidate.txt").write_text("candidate bytes\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "base")

        self.metadata = root / "metadata"
        self.metadata.mkdir()
        self.task = {
            "task_id": "task-review-manifest",
            "request": "Run a local check and preserve its candidate evidence.",
            "kind": "build",
            "domains": ["general"],
            "interfaces": ["cli"],
            "targets": ["windows"],
            "languages": ["python"],
            "risk": "R1",
            "runtime": {"real_subagents": False, "separate_contexts": False},
            "check_specs": [{
                "check_id": "static_analysis",
                "argv": [sys.executable, "-P", "-c", "print('PASS')"],
                "cwd": ".", "timeout_seconds": 20, "protocol": "exit_code",
            }],
        }
        self.state = {
            "task_id": self.task["task_id"],
            "project_root": str(self.repo),
            "base_commit": _git(self.repo, "rev-parse", "HEAD"),
            "task_revision": "rev-1",
            "task_sha256": canonical_task_sha256(self.task),
        }
        self.worker = {
            "role": "implementation_engineer",
            "branch": _git(self.repo, "branch", "--show-current"),
            "path": str(self.repo),
        }
        result = run_checks(self.task, self.state, self.worker, self.metadata,
                            stop_event=threading.Event(), deadline=time.monotonic() + 30)
        self.assertEqual(result.status, "PASSED")
        self.check_manifest_path = result.manifest_path
        self.check_manifest = read_check_manifest(self.check_manifest_path, self.metadata)
        self.check_manifest_raw = self.check_manifest_path.read_bytes()
        self.check_manifest_hash = hashlib.sha256(self.check_manifest_raw).hexdigest()
        self.snapshot = self.metadata / self.check_manifest["snapshot"]["path"]
        self.review_snapshot = self.metadata / "review-runs" / "run-1" / "review-snapshot"
        self.review_snapshot_ref = capture_snapshot(self.repo, self.review_snapshot)
        self.snapshot_hash = _snapshot_artifact_sha256(self.review_snapshot)
        self.manifest = self._make_manifest()

    def _relative(self, path):
        path = Path(path)
        try:
            # Preserve lexical links so negative tests can encode a hostile reference.
            return path.relative_to(self.metadata).as_posix()
        except ValueError:
            # Production helpers may return resolved long paths for a short-name root.
            return path.resolve(strict=True).relative_to(
                self.metadata.resolve(strict=True)
            ).as_posix()

    def test_relative_fixture_path_accepts_windows_short_metadata_alias(self):
        if sys.platform != "win32":
            self.skipTest("Windows short paths are specific to Windows")
        import ctypes

        metadata = self.metadata.resolve(strict=True)
        short_path = ctypes.create_unicode_buffer(32768)
        get_short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
        get_short_path.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        get_short_path.restype = ctypes.c_uint32
        length = get_short_path(str(metadata), short_path, len(short_path))
        if not length or length >= len(short_path):
            self.skipTest("Windows short path lookup is unavailable")
        alias = Path(short_path.value)
        if str(alias).casefold() == str(metadata).casefold():
            self.skipTest("this volume does not expose a distinct short path")

        original = self.metadata
        self.metadata = alias
        try:
            expected = self.check_manifest_path.resolve(strict=True).relative_to(metadata).as_posix()
            self.assertEqual(self._relative(self.check_manifest_path), expected)
        finally:
            self.metadata = original

    def _write(self, relative, content):
        path = self.metadata / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _make_manifest(self, *, verdict="PASS"):
        diff = "diff --git a/candidate.txt b/candidate.txt\n+candidate update\n"
        report_identity = {
            "task_id": self.state["task_id"],
            "task_revision": self.check_manifest["task_revision"],
            "task_sha256": self.check_manifest["task_sha256"],
            "base_commit": self.check_manifest["base_commit"],
            "worker_role": self.check_manifest["worker_role"],
            "candidate_tree_sha256": self.check_manifest["candidate_tree_sha256"],
            "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            "check_manifest_sha256": self.check_manifest_hash,
        }
        report_data = {
            "schema_version": 1, **report_identity,
            "verdict": verdict,
            "summary": "Reviewed the candidate and its deterministic check evidence.",
            "findings": [],
        }
        if verdict == "REQUEST_CHANGES":
            report_data["findings"] = [{
                "id": "F-1", "severity": "HIGH", "path": "candidate.txt", "line": 1,
                "evidence": "The candidate does not meet the task requirement.",
                "recommendation": "Revise the candidate and rerun the check.",
            }]
        report_text = json.dumps(report_data, ensure_ascii=False, separators=(",", ":"))
        parsed_report = parse_review_report(report_text, report_identity)
        prompt = ("Review the candidate and checks.\n<<<SSEC_DIFF_BEGIN>>>\n" + diff +
                  "<<<SSEC_DIFF_END>>>\nReturn a structured report.")
        input_data = {
            "schema_version": 1, "identity": report_identity,
            "reviewer_role": "independent_reviewer", "requested_provider": "gemini",
            "prompt": prompt, "diff": diff,
        }
        input_path = self._write("review-runs/run-1/input.json",
                                 json.dumps(input_data, ensure_ascii=False,
                                            separators=(",", ":")).encode())
        stdout_path = self._write("review-runs/run-1/stdout.jsonl", json.dumps({
            "type": "message", "role": "assistant", "content": report_text,
        }).encode() + b"\n" + json.dumps({
            "type": "result", "status": "success", "stats": {},
        }).encode() + b"\n")
        stderr_path = self._write("review-runs/run-1/stderr.log", b"")
        digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        now = "2026-11-02T00:00:00+00:00"
        return {
            "schema_version": 1, "status": "PASSED" if verdict == "PASS" else verdict,
            **{key: report_identity[key] for key in (
                "task_id", "task_revision", "task_sha256", "base_commit", "worker_role",
                "candidate_tree_sha256", "diff_sha256", "check_manifest_sha256",
            )},
            "check_manifest_path": self._relative(self.check_manifest_path),
            "reviewer_role": "independent_reviewer", "reviewer_provider": "gemini",
            "runtime_run_id": "run-1",
            "runtime_adapter_type": "scripts.provider_runtimes.GeminiRuntime",
            "review_independence": "UNVERIFIED_WITHOUT_PROVIDER_E2E",
            "observed_provider": "gemini",
            "provider_session_id": "session-1", "verdict": verdict,
            "review_report": parsed_report,
            "review_report_sha256": report_sha256(parsed_report),
            "input_path": self._relative(input_path), "input_sha256": digest(input_path),
            "stdout_path": self._relative(stdout_path), "stdout_sha256": digest(stdout_path),
            "stderr_path": self._relative(stderr_path), "stderr_sha256": digest(stderr_path),
            "snapshot_path": self._relative(self.review_snapshot),
            "review_snapshot_tree_sha256": self.review_snapshot_ref.snapshot_tree_sha256,
            "snapshot_artifact_sha256_before": self.snapshot_hash,
            "snapshot_artifact_sha256_after": self.snapshot_hash,
            "started_at_utc": now, "finished_at_utc": now, "exit_code": 0,
            "sandbox_effective": None, "error": None,
        }

    def test_valid_pass_manifest_is_bound_to_check_report_logs_and_snapshot(self):
        parsed = validate_review_manifest(self.manifest, self.metadata)

        self.assertEqual(parsed["status"], "PASSED")
        self.assertEqual(parsed["verdict"], "PASS")
        self.assertEqual(parsed["review_report_sha256"], self.manifest["review_report_sha256"])
        self.assertNotEqual(self.review_snapshot.resolve(), self.snapshot.resolve())
        self.assertEqual(self.manifest["review_snapshot_tree_sha256"],
                         self.manifest["candidate_tree_sha256"])

    def test_rejects_adulterated_log_hash_and_check_manifest_hash(self):
        for field, path_field in (("stdout_sha256", "stdout_path"),
                                  ("input_sha256", "input_path"),
                                  ("stderr_sha256", "stderr_path")):
            changed = dict(self.manifest)
            changed[field] = "f" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_review_manifest(changed, self.metadata)

        changed = dict(self.manifest, check_manifest_sha256="f" * 64)
        with self.assertRaises(ValueError):
            validate_review_manifest(changed, self.metadata)

    def test_rejects_check_manifest_content_tampering(self):
        self.check_manifest_path.write_bytes(self.check_manifest_raw + b" ")

        with self.assertRaises(ValueError):
            validate_review_manifest(self.manifest, self.metadata)

    def test_rejects_metadata_escape_references(self):
        changed = dict(self.manifest, stdout_path="../outside.log")
        with self.assertRaises(ValueError):
            validate_review_manifest(changed, self.metadata)

    def test_rejects_symlink_references(self):
        outside = Path(self.temp.name) / "outside.log"
        outside.write_text("secret", encoding="utf-8")
        link = self.metadata / "review-runs" / "run-1" / "linked.log"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is not available on this platform")
        changed = dict(self.manifest, stdout_path=self._relative(link))
        with self.assertRaises(ValueError):
            validate_review_manifest(changed, self.metadata)

    def test_rejects_snapshot_mutation_and_before_after_mismatch(self):
        (self.review_snapshot / "candidate.txt").write_text("altered\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_review_manifest(self.manifest, self.metadata)

        (self.review_snapshot / "candidate.txt").write_text("candidate bytes\n", encoding="utf-8")
        changed = dict(self.manifest, snapshot_artifact_sha256_after="f" * 64)
        with self.assertRaises(ValueError):
            validate_review_manifest(changed, self.metadata)

    def test_failed_review_can_record_mutation_when_after_hash_matches_current_copy(self):
        original_hash = self.manifest["snapshot_artifact_sha256_before"]
        (self.review_snapshot / "candidate.txt").write_text("reviewer mutation\n", encoding="utf-8")
        current_hash = _snapshot_artifact_sha256(self.review_snapshot)
        changed = dict(self.manifest,
                       status="FAILED", verdict=None, review_report=None,
                       review_report_sha256=None, error="review snapshot was modified",
                       snapshot_artifact_sha256_before=original_hash,
                       snapshot_artifact_sha256_after=current_hash)

        parsed = validate_review_manifest(changed, self.metadata)

        self.assertEqual(parsed["status"], "FAILED")
        self.assertNotEqual(parsed["snapshot_artifact_sha256_before"],
                            parsed["snapshot_artifact_sha256_after"])

    def test_rejects_review_snapshot_with_changed_git_visible_tree_even_if_rehashed(self):
        (self.review_snapshot / "candidate.txt").write_text("altered\n", encoding="utf-8")
        changed_artifact = _snapshot_artifact_sha256(self.review_snapshot)
        changed = dict(self.manifest,
                       snapshot_artifact_sha256_before=changed_artifact,
                       snapshot_artifact_sha256_after=changed_artifact)

        with self.assertRaisesRegex(ValueError, "tree"):
            validate_review_manifest(changed, self.metadata)

    def test_rejects_report_not_bound_to_actual_output_or_candidate(self):
        changed_report = dict(self.manifest["review_report"], candidate_tree_sha256="f" * 64)
        changed = dict(self.manifest, review_report=changed_report)
        with self.assertRaises(ValueError):
            validate_review_manifest(changed, self.metadata)

        changed = dict(self.manifest, review_report_sha256="f" * 64)
        with self.assertRaises(ValueError):
            validate_review_manifest(changed, self.metadata)

    def test_rejects_input_diff_identity_role_or_provider_mismatch(self):
        original = (self.metadata / self.manifest["input_path"]).read_bytes()
        input_data = json.loads(original)
        for changes in (
            {"diff": "different patch"},
            {"identity": dict(input_data["identity"], task_id="other-task")},
            {"reviewer_role": "software_auditor"},
            {"requested_provider": "codex"},
            {"prompt": "missing diff delimiters"},
        ):
            with self.subTest(changes=changes):
                changed_input = dict(input_data, **changes)
                path = self.metadata / self.manifest["input_path"]
                path.write_text(json.dumps(changed_input, ensure_ascii=False,
                                           separators=(",", ":")), encoding="utf-8")
                changed_manifest = dict(self.manifest,
                                        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                with self.assertRaises(ValueError):
                    validate_review_manifest(changed_manifest, self.metadata)
        (self.metadata / self.manifest["input_path"]).write_bytes(original)

    def test_not_run_and_failed_without_artifacts_are_valid_non_acceptance_records(self):
        artifact_fields = (
            "check_manifest_path", "check_manifest_sha256", "runtime_run_id",
            "observed_provider", "provider_session_id", "verdict", "review_report",
            "review_report_sha256", "input_path", "input_sha256", "stdout_path",
            "stdout_sha256", "stderr_path", "stderr_sha256", "snapshot_path",
            "review_snapshot_tree_sha256", "snapshot_artifact_sha256_before",
            "snapshot_artifact_sha256_after",
        )
        for status in ("NOT_RUN", "FAILED"):
            with self.subTest(status=status):
                changed = dict(self.manifest, status=status, exit_code=None,
                               sandbox_effective=None, error="review was not completed")
                for field in artifact_fields:
                    changed[field] = None
                parsed = validate_review_manifest(changed, self.metadata)
                self.assertEqual(parsed["status"], status)
                self.assertIsNone(parsed["review_report"])

    def test_rejects_extra_fields_and_status_verdict_mismatch(self):
        with self.assertRaises(ValueError):
            validate_review_manifest(dict(self.manifest, extra="not allowed"), self.metadata)
        changed = dict(self.manifest, status="REQUEST_CHANGES")
        with self.assertRaises(ValueError):
            validate_review_manifest(changed, self.metadata)
        changed = dict(self.manifest, runtime_adapter_type="tests.FixtureGeminiRuntime")
        with self.assertRaisesRegex(ValueError, "concrete provider runtime adapter"):
            validate_review_manifest(changed, self.metadata)
        changed = dict(self.manifest, review_independence="VERIFIED")
        with self.assertRaisesRegex(ValueError, "unverified independence"):
            validate_review_manifest(changed, self.metadata)


if __name__ == "__main__":
    unittest.main()
