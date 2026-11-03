import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts.check_runner import capture_snapshot, read_check_manifest, run_checks
from scripts.execution_evidence import (
    ALLOWED_ENVIRONMENT_KEYS,
    canonical_task_sha256,
    candidate_tree_sha256,
    decode_evidence_record,
)


def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        input=input_bytes,
    ).stdout


def make_repo(parent: Path, *, unittest_source: str | None = None) -> Path:
    repo = parent / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Check Runner Test")
    git(repo, "config", "user.email", "check-runner@example.invalid")
    (repo / ".gitignore").write_text("ignored.txt\n__pycache__/\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("candidate bytes\n", encoding="utf-8")
    (repo / "run.sh").write_text("#!/bin/sh\necho candidate\n", encoding="utf-8")
    git(repo, "add", ".gitignore", "tracked.txt", "run.sh")
    git(repo, "commit", "-q", "-m", "base")
    if os.name == "nt":
        git(repo, "update-index", "--chmod=+x", "run.sh")
    else:
        (repo / "run.sh").chmod((repo / "run.sh").stat().st_mode | 0o100)
    if unittest_source is not None:
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_real.py").write_text(unittest_source, encoding="utf-8")
    (repo / "untracked.txt").write_text("included candidate\n", encoding="utf-8")
    (repo / "ignored.txt").write_text("excluded candidate\n", encoding="utf-8")
    return repo


def task_for(repo: Path, specs: list[dict] | None = None) -> dict:
    if specs is None:
        specs = [{
            "check_id": "unit_tests",
            "argv": [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            "cwd": ".",
            "timeout_seconds": 20,
            "protocol": "unittest",
        }]
    return {
        "task_id": "TASK-CHECK-RUNNER",
        "request": "Run the original typed check specs against a candidate snapshot.",
        "kind": "build",
        "domains": ["general"],
        "interfaces": ["cli"],
        "targets": ["windows"],
        "languages": ["python"],
        "risk": "R1",
        "runtime": {"real_subagents": False, "separate_contexts": False},
        "check_specs": specs,
    }


def context_for(repo: Path, task: dict, metadata: Path) -> tuple[dict, dict]:
    state = {
        "task_id": task["task_id"],
        "project_root": str(repo),
        "base_commit": git(repo, "rev-parse", "HEAD").decode().strip(),
        "task_revision": "revision-1",
        "task_sha256": canonical_task_sha256(task),
    }
    worker = {
        "role": "implementation_engineer",
        "branch": git(repo, "branch", "--show-current").decode().strip(),
        "path": str(repo),
        # This worker-supplied text is deliberately not a check specification.
        "mailbox_command": f'{sys.executable} -c "open("mailbox-ran", "w").write("bad")"',
    }
    metadata.mkdir(parents=True)
    return state, worker


PASSING_TEST = """import unittest

class PassingCandidateTests(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(2 + 2, 4)
"""


FAILING_TEST = """import unittest

class FailingCandidateTests(unittest.TestCase):
    def test_failure(self):
        self.assertEqual(2 + 2, 5)
"""


MUTATING_TEST = """import pathlib
import unittest

class MutatingCandidateTests(unittest.TestCase):
    def test_mutates_snapshot(self):
        pathlib.Path('tracked.txt').write_text('changed by test')
        self.assertTrue(True)
"""


class SnapshotCaptureTests(unittest.TestCase):
    def test_capture_copies_git_visible_files_and_preserves_candidate_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            destination = parent / "evidence" / "snapshot"
            reference = capture_snapshot(repo, destination)

            self.assertEqual(reference.source_tree_sha256, candidate_tree_sha256(repo))
            self.assertEqual(reference.snapshot_tree_sha256, reference.source_tree_sha256)
            self.assertEqual(reference.file_count, 4)
            self.assertGreater(reference.total_bytes, 0)
            self.assertEqual((destination / "tracked.txt").read_text(encoding="utf-8"), "candidate bytes\n")
            self.assertTrue((destination / "untracked.txt").is_file())
            self.assertFalse((destination / "ignored.txt").exists())
            self.assertFalse((destination / ".git").exists())
            if os.name != "nt":
                self.assertTrue((destination / "run.sh").stat().st_mode & 0o100)

    def test_capture_rejects_indexed_symlink_and_special_file(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            target = git(repo, "hash-object", "-w", "--stdin", input_bytes=b"target").decode().strip()
            git(repo, "update-index", "--add", "--cacheinfo", f"120000,{target},indexed-link")
            with self.assertRaisesRegex(ValueError, "symlink"):
                capture_snapshot(repo, Path(temp) / "snapshot")

        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            tracked = repo / "tracked.txt"
            tracked.unlink()
            tracked.mkdir()
            with self.assertRaisesRegex(ValueError, "regular|special|directory"):
                capture_snapshot(repo, Path(temp) / "snapshot")

    def test_capture_detects_source_change_during_copy_and_removes_partial_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            destination = parent / "evidence" / "snapshot"
            from scripts.check_runner import _copy_candidate_file

            def copy_then_change(entry, destination_file):
                copied = _copy_candidate_file(entry, destination_file)
                if entry.path.name == "tracked.txt":
                    (repo / "tracked.txt").write_text("changed during capture", encoding="utf-8")
                return copied

            with mock.patch("scripts.check_runner._copy_candidate_file", side_effect=copy_then_change):
                with self.assertRaisesRegex(ValueError, "drift|changed"):
                    capture_snapshot(repo, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(list(destination.parent.glob("*.partial")) if destination.parent.exists() else [], [])


class CheckExecutionTests(unittest.TestCase):
    def run_task(self, parent: Path, task: dict, repo: Path, *, stop_event=None):
        metadata = parent / "metadata"
        state, worker = context_for(repo, task, metadata)
        result = run_checks(
            task, state, worker, metadata,
            stop_event=stop_event or threading.Event(),
            deadline=time.monotonic() + 30,
        )
        return result, metadata, worker

    def test_initialized_task_digest_is_required_and_must_match(self):
        for mutation in ("missing", "mismatch"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                repo = make_repo(parent)
                task = task_for(repo)
                metadata = parent / "metadata"
                state, worker = context_for(repo, task, metadata)
                if mutation == "missing":
                    del state["task_sha256"]
                else:
                    state["task_sha256"] = "0" * 64
                with self.assertRaisesRegex(ValueError, "task digest"):
                    run_checks(task, state, worker, metadata,
                               stop_event=threading.Event(), deadline=time.monotonic() + 5)

    def test_source_branch_and_initialized_worker_binding_are_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            task = task_for(repo)
            metadata = parent / "metadata"
            state, worker = context_for(repo, task, metadata)
            worker["branch"] = "worker-claimed-a-different-branch"
            with self.assertRaisesRegex(ValueError, "checked-out branch"):
                run_checks(task, state, worker, metadata,
                           stop_event=threading.Event(), deadline=time.monotonic() + 5)

        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            task = task_for(repo)
            metadata = parent / "metadata"
            state, worker = context_for(repo, task, metadata)
            state["workers"] = [{"role": worker["role"], "branch": worker["branch"], "path": str(repo.parent)}]
            with self.assertRaisesRegex(ValueError, "worker path"):
                run_checks(task, state, worker, metadata,
                           stop_event=threading.Event(), deadline=time.monotonic() + 5)

    def test_process_spawn_error_is_recorded_failed_with_logs_and_no_pass(self):
        spec = {"check_id": "static_analysis", "argv": [f".{os.sep}invalid.txt"],
                "cwd": ".", "timeout_seconds": 5, "protocol": "exit_code"}
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            (repo / "invalid.txt").write_bytes(b"not an executable")
            result, metadata, _worker = self.run_task(parent, task_for(repo, [spec]), repo)

            self.assertEqual(result.status, "FAILED")
            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertEqual(record.process_status, "spawn_error")
            self.assertFalse(record.passed)
            self.assertEqual(record.containment_status, "not_started")
            manifest = read_check_manifest(result.manifest_path, metadata)
            self.assertEqual(manifest["checks"][0]["result_status"], "FAILED")

    def test_real_unittest_pass_publishes_terminal_manifest_and_verified_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent, unittest_source=PASSING_TEST)
            task = task_for(repo)
            result, metadata, worker = self.run_task(parent, task, repo)

            self.assertEqual(result.status, "PASSED")
            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertTrue(record.passed)
            self.assertEqual(record.argv, tuple(task["check_specs"][0]["argv"]))
            self.assertEqual(record.cwd, ".")
            self.assertEqual(record.unittest_count, 1)
            self.assertEqual(record.process_status, "exited")
            self.assertEqual(record.exit_code, 0)
            self.assertEqual(record.containment_status, "confirmed")
            self.assertTrue(Path(record.executable).is_absolute())
            self.assertEqual(len(record.executable_sha256), 64)
            self.assertTrue(set(record.environment).issubset(ALLOWED_ENVIRONMENT_KEYS))

            manifest_path = result.manifest_path
            self.assertIsNotNone(manifest_path)
            self.assertTrue(manifest_path.resolve().is_relative_to(metadata.resolve()))
            manifest = read_check_manifest(manifest_path, metadata)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertIs(manifest["terminal"], True)
            self.assertEqual(manifest["status"], "PASSED")
            self.assertEqual(manifest["worker_role"], worker["role"])
            self.assertEqual(manifest["worker_branch"], worker["branch"])
            self.assertEqual(len(manifest["checks"]), 1)
            logged_record = decode_evidence_record(json.dumps(manifest["checks"][0]["record"]))
            for path_value, hash_value in (
                (logged_record.stdout_path, logged_record.stdout_sha256),
                (logged_record.stderr_path, logged_record.stderr_sha256),
            ):
                log = metadata / Path(path_value)
                self.assertTrue(log.is_file())
                self.assertEqual(hashlib.sha256(log.read_bytes()).hexdigest(), hash_value)
            self.assertFalse((repo / "mailbox-ran").exists())

            snapshot = metadata / Path(manifest["snapshot"]["path"])
            self.assertEqual(snapshot, manifest_path.parent / "snapshot")
            self.assertEqual((snapshot / "tests" / "test_real.py").read_text(encoding="utf-8"), PASSING_TEST)

    def test_real_unittest_failure_and_pass_print_or_zero_discovery_never_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent, unittest_source=FAILING_TEST)
            result, _metadata, _worker = self.run_task(parent, task_for(repo), repo)
            self.assertEqual(result.status, "FAILED")
            self.assertFalse(result.records[0].passed)
            self.assertEqual(result.records[0].process_status, "exited")
            self.assertNotEqual(result.records[0].exit_code, 0)
            self.assertEqual(result.records[0].unittest_count, 1)

        for argv, setup in (
            ([sys.executable, "-c", "print('PASS')"], None),
            ([sys.executable, "-m", "unittest", "discover", "-s", "empty_tests"], "empty"),
        ):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                repo = make_repo(parent)
                if setup == "empty":
                    (repo / "empty_tests").mkdir()
                    (repo / "empty_tests" / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
                spec = {"check_id": "unit_tests", "argv": argv, "cwd": ".",
                        "timeout_seconds": 10, "protocol": "unittest"}
                result, _metadata, _worker = self.run_task(parent, task_for(repo, [spec]), repo)
                self.assertEqual(result.status, "FAILED")
                self.assertFalse(result.records[0].passed)
                self.assertIn(result.records[0].unittest_count, (None, 0))

    def test_timeout_quiesces_parent_and_child_and_is_recorded_failed(self):
        child_code = "import pathlib,time; time.sleep(1); pathlib.Path('survived.txt').write_text('alive')"
        parent_code = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child_code!r}]); time.sleep(30)"
        spec = {"check_id": "static_analysis", "argv": [sys.executable, "-c", parent_code],
                "cwd": ".", "timeout_seconds": 0.4, "protocol": "exit_code"}
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            result, metadata, _worker = self.run_task(parent, task_for(repo, [spec]), repo)
            self.assertEqual(result.status, "FAILED")
            record = result.records[0]
            self.assertEqual(record.process_status, "timed_out")
            self.assertFalse(record.passed)
            self.assertEqual(record.containment_status, "confirmed")
            time.sleep(1.1)
            snapshot = metadata / Path(read_check_manifest(result.manifest_path, metadata)["snapshot"]["path"])
            self.assertFalse((snapshot / "survived.txt").exists())

    def test_cancellation_quiesces_parent_and_child_and_is_recorded_failed(self):
        child_code = "import pathlib,time; time.sleep(2); pathlib.Path('survived.txt').write_text('alive')"
        parent_code = f"import pathlib,subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child_code!r}]); pathlib.Path('started.txt').write_text('started'); time.sleep(30)"
        spec = {"check_id": "static_analysis", "argv": [sys.executable, "-c", parent_code],
                "cwd": ".", "timeout_seconds": 20, "protocol": "exit_code"}
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            stop = threading.Event()
            metadata = parent / "metadata"
            state, worker = context_for(repo, task_for(repo, [spec]), metadata)

            def cancel_after_launch():
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    matches = list(metadata.glob("check-runs/*/implementation_engineer/snapshot/started.txt"))
                    if matches:
                        stop.set()
                        return
                    time.sleep(0.01)

            cancel_thread = threading.Thread(target=cancel_after_launch)
            cancel_thread.start()
            try:
                result = run_checks(
                    task_for(repo, [spec]), state, worker, metadata,
                    stop_event=stop, deadline=time.monotonic() + 30,
                )
            finally:
                cancel_thread.join(timeout=2)
            self.assertEqual(result.status, "FAILED")
            record = result.records[0]
            self.assertEqual(record.process_status, "cancelled")
            self.assertFalse(record.passed)
            self.assertEqual(record.containment_status, "confirmed")
            time.sleep(1.1)
            snapshot = metadata / Path(read_check_manifest(result.manifest_path, metadata)["snapshot"]["path"])
            self.assertFalse((snapshot / "survived.txt").exists())

    def test_check_that_mutates_snapshot_fails_and_later_check_does_not_run(self):
        mutating_argv = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        later_argv = [sys.executable, "-c", "open('later-ran.txt','w').write('bad')"]
        specs = [
            {"check_id": "unit_tests", "argv": mutating_argv, "cwd": ".", "timeout_seconds": 10, "protocol": "unittest"},
            {"check_id": "static_analysis", "argv": later_argv, "cwd": ".", "timeout_seconds": 10, "protocol": "exit_code"},
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent, unittest_source=MUTATING_TEST)
            result, metadata, _worker = self.run_task(parent, task_for(repo, specs), repo)
            self.assertEqual(result.status, "FAILED")
            self.assertEqual(len(result.records), 1)
            self.assertFalse(result.records[0].passed)
            self.assertNotEqual(
                result.records[0].candidate_tree_sha256_before,
                result.records[0].candidate_tree_sha256_after,
            )
            manifest = read_check_manifest(result.manifest_path, metadata)
            self.assertEqual(manifest["checks"][1]["result_status"], "NOT_RUN")
            snapshot = metadata / Path(manifest["snapshot"]["path"])
            self.assertFalse((snapshot / "later-ran.txt").exists())

    def test_tampered_log_and_partial_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent, unittest_source=PASSING_TEST)
            result, metadata, _worker = self.run_task(parent, task_for(repo), repo)
            record = result.records[0]
            log = metadata / Path(record.stdout_path)
            with log.open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash|tamper|stdout"):
                read_check_manifest(result.manifest_path, metadata)

            partial = result.manifest_path.parent / "partial.json"
            partial.write_text('{"schema_version":1', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest|JSON|invalid"):
                read_check_manifest(partial, metadata)

    def test_legacy_task_without_specs_is_explicit_not_run(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo = make_repo(parent)
            task = task_for(repo)
            del task["check_specs"]
            metadata = parent / "metadata"
            state, worker = context_for(repo, task, metadata)
            result = run_checks(
                task, state, worker, metadata,
                stop_event=threading.Event(), deadline=time.monotonic() + 5,
            )
            self.assertEqual(result.status, "NOT_RUN")
            self.assertIsNone(result.manifest_path)
            self.assertEqual(result.records, ())


if __name__ == "__main__":
    unittest.main()
