import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.execution_evidence import (
    ALLOWED_ENVIRONMENT_KEYS,
    CheckSpec,
    EvidenceRecord,
    SnapshotReference,
    _lstat_candidate,
    candidate_tree_sha256,
    canonical_task_sha256,
    decode_evidence_record,
    encode_evidence_record,
    validate_check_specs,
)
from scripts.route_task import required_checks

ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        input=input_bytes,
    ).stdout


def make_repo(parent: Path) -> Path:
    repo = parent / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Evidence Test")
    git(repo, "config", "user.email", "evidence-test@example.invalid")
    (repo / "tracked.txt").write_bytes(b"original\n")
    (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    git(repo, "add", "tracked.txt", ".gitignore")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def sample_record(**changes) -> EvidenceRecord:
    values = {
        "task_id": "task-17",
        "task_revision": "revision-3",
        "task_sha256": "a" * 64,
        "execution_id": "exec-22",
        "check_id": "unit_tests",
        "worker_role": "implementation_engineer",
        "worker_branch": "codex/worker-1",
        "base_commit": "b" * 40,
        "candidate_tree_sha256_before": "c" * 64,
        "candidate_tree_sha256_after": "c" * 64,
        "executable": str(Path(os.__file__).resolve()),
        "executable_sha256": "d" * 64,
        "protocol": "unittest",
        "argv": ("python", "-m", "unittest", "discover"),
        "cwd": ".",
        "operating_system": "Windows-11",
        "python_version": "3.11.9",
        "environment": {"PYTHONUTF8": "1"},
        "started_at_utc": "2026-11-02T18:00:00Z",
        "finished_at_utc": "2026-11-02T18:00:03.250000Z",
        "timeout_seconds": 120.0,
        "process_status": "exited",
        "containment_status": "confirmed",
        "exit_code": 0,
        "unittest_count": 4,
        "stdout_path": "check-runs/exec-22/unit_tests.stdout",
        "stdout_sha256": "e" * 64,
        "stderr_path": "check-runs/exec-22/unit_tests.stderr",
        "stderr_sha256": "f" * 64,
        "passed": True,
    }
    values.update(changes)
    return EvidenceRecord(**values)


class CanonicalTaskHashTests(unittest.TestCase):
    def test_hash_is_canonical_and_changes_when_request_or_check_spec_changes(self):
        left = {"request": "build", "task_id": "t-1", "check_specs": [{"argv": ["python", "-m", "unittest"]}]}
        reordered = {"check_specs": [{"argv": ["python", "-m", "unittest"]}], "task_id": "t-1", "request": "build"}
        self.assertEqual(canonical_task_sha256(left), canonical_task_sha256(reordered))
        self.assertEqual(canonical_task_sha256(left), hashlib.sha256(
            b'{"check_specs":[{"argv":["python","-m","unittest"]}],"request":"build","task_id":"t-1"}'
        ).hexdigest())

        changed_request = copy.deepcopy(left)
        changed_request["request"] = "build something else"
        self.assertNotEqual(canonical_task_sha256(left), canonical_task_sha256(changed_request))

        changed_check = copy.deepcopy(left)
        changed_check["check_specs"][0]["argv"].append("tests")
        self.assertNotEqual(canonical_task_sha256(left), canonical_task_sha256(changed_check))

    def test_hash_rejects_nan_and_non_json_values_clearly(self):
        with self.assertRaisesRegex(ValueError, "JSON|NaN|finite"):
            canonical_task_sha256({"request": float("nan")})
        with self.assertRaisesRegex(ValueError, "JSON|serializable"):
            canonical_task_sha256({"request": object()})


    def test_hash_rejects_tuple_values_as_non_json(self):
        with self.assertRaisesRegex(ValueError, "JSON"):
            canonical_task_sha256({"argv": ("python", "-m", "unittest")})

class CheckSpecValidationTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / "examples/seir_desktop_audit.json").read_text(encoding="utf-8"))
        self.task["check_specs"] = [
            {"check_id": "unit_tests", "argv": ["python", "-P", "-m", "unittest"], "cwd": ".",
             "timeout_seconds": 30, "protocol": "unittest"},
            {"check_id": "static_analysis", "argv": ["python", "-m", "compileall", "scripts"],
             "cwd": "scripts", "timeout_seconds": 15.5, "protocol": "exit_code"},
        ]

    def test_accepts_typed_specs_for_required_checks(self):
        specs = validate_check_specs(self.task)
        self.assertEqual(specs, (
            CheckSpec("unit_tests", ("python", "-P", "-m", "unittest"), ".", 30.0, "unittest"),
            CheckSpec("static_analysis", ("python", "-m", "compileall", "scripts"), "scripts", 15.5, "exit_code"),
        ))

    def test_check_spec_is_frozen(self):
        spec = validate_check_specs(self.task)[0]
        with self.assertRaises(AttributeError):
            spec.check_id = "changed"

    def test_legacy_task_without_check_specs_still_routes(self):
        task = copy.deepcopy(self.task)
        del task["check_specs"]
        self.assertEqual(validate_check_specs(task), ())
        self.assertEqual(required_checks(task)[:2], ["unit_tests", "static_analysis"])

    def test_rejects_wrong_schema_unknown_or_duplicate_check_ids(self):
        for invalid in (
            {"check_id": "unit_tests", "argv": ["python"], "cwd": ".", "timeout_seconds": 1, "protocol": "unittest", "extra": 1},
            {"check_id": "unknown", "argv": ["python"], "cwd": ".", "timeout_seconds": 1, "protocol": "exit_code"},
        ):
            with self.subTest(invalid=invalid):
                task = copy.deepcopy(self.task)
                task["check_specs"] = [invalid]
                with self.assertRaises(ValueError):
                    validate_check_specs(task)

        task = copy.deepcopy(self.task)
        task["check_specs"] = [copy.deepcopy(task["check_specs"][0]), copy.deepcopy(task["check_specs"][0])]
        with self.assertRaisesRegex(ValueError, "unique|duplicate"):
            validate_check_specs(task)

    def test_rejects_invalid_argv_cwd_timeout_and_protocol(self):
        cases = (
            ("argv", []),
            ("argv", ["python", ""]),
            ("argv", ["python\x00bad"]),
            ("cwd", "C:\\outside"),
            ("cwd", "C:relative"),
            ("cwd", "../outside"),
            ("cwd", "nested/../../outside"),
            ("cwd", "nested/C:relative"),
            ("cwd", "/outside"),
            ("timeout_seconds", True),
            ("timeout_seconds", 0),
            ("timeout_seconds", float("inf")),
            ("timeout_seconds", float("nan")),
            ("protocol", "shell"),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                task = copy.deepcopy(self.task)
                task["check_specs"] = [copy.deepcopy(task["check_specs"][0])]
                task["check_specs"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_check_specs(task)

    def test_unit_tests_requires_unittest_protocol(self):
        task = copy.deepcopy(self.task)
        task["check_specs"] = [copy.deepcopy(task["check_specs"][0])]
        task["check_specs"][0]["protocol"] = "exit_code"
        with self.assertRaisesRegex(ValueError, "unit_tests.*unittest|unittest.*unit_tests"):
            validate_check_specs(task)

    def test_unit_tests_requires_direct_python_unittest_module_cli(self):
        for command in ("python", "python3", "python3.14", "pypy", "pypy3", "py", sys.executable):
            with self.subTest(command=command):
                task = copy.deepcopy(self.task)
                task["check_specs"][0]["argv"] = [command, "-P", "-m", "unittest", "discover"]
                self.assertEqual(validate_check_specs(task)[0].argv[:4], (command, "-P", "-m", "unittest"))

        forged_commands = (
            [sys.executable, "-m", "unittest", "discover"],
            [sys.executable, "-c", "print('Ran 1 test in 0.01s\\n\\nOK')"],
            [sys.executable, "-P", "-c", "print('Ran 1 test in 0.01s\\n\\nOK')"],
            [sys.executable, "-"],
            [sys.executable, "test_runner.py"],
            ["pytest", "tests"],
            [sys.executable, "-m", "unittest.mock"],
        )
        for argv in forged_commands:
            with self.subTest(argv=argv):
                task = copy.deepcopy(self.task)
                task["check_specs"][0]["argv"] = argv
                with self.assertRaisesRegex(ValueError, "Python.*-m unittest|unit_tests.*unittest"):
                    validate_check_specs(task)

    def test_non_list_check_specs_is_invalid(self):
        task = copy.deepcopy(self.task)
        task["check_specs"] = {"check_id": "unit_tests"}
        with self.assertRaises(ValueError):
            validate_check_specs(task)


class CandidateTreeHashTests(unittest.TestCase):
    def test_lstat_accepts_equivalent_root_with_lexical_parent_segment(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            candidate = repo / "candidate.txt"
            candidate.write_text("candidate\n", encoding="utf-8")
            aliased_root = repo.parent / repo.name / ".." / repo.name

            item_stat = _lstat_candidate(candidate, aliased_root, ("candidate.txt",),
                                         b"candidate.txt")

            self.assertTrue(stat.S_ISREG(item_stat.st_mode))

    def test_hash_tracks_tracked_and_nonignored_untracked_bytes_but_ignores_ignored_files(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            initial = candidate_tree_sha256(repo)
            (repo / "ignored.txt").write_text("hidden one", encoding="utf-8")
            self.assertEqual(candidate_tree_sha256(repo), initial)

            (repo / "tracked.txt").write_bytes(b"edited\n")
            tracked_edit = candidate_tree_sha256(repo)
            self.assertNotEqual(tracked_edit, initial)

            (repo / "new.txt").write_bytes(b"untracked one")
            first_untracked = candidate_tree_sha256(repo)
            self.assertNotEqual(first_untracked, tracked_edit)
            (repo / "new.txt").write_bytes(b"untracked two")
            self.assertNotEqual(candidate_tree_sha256(repo), first_untracked)

    def test_hash_changes_when_executable_bit_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            path = repo / "tracked.txt"
            before = candidate_tree_sha256(repo)
            if os.name == "nt":
                git(repo, "update-index", "--chmod=+x", "tracked.txt")
            else:
                path.chmod(path.stat().st_mode | stat.S_IXUSR)
            self.assertNotEqual(candidate_tree_sha256(repo), before)

    def test_rejects_indexed_symlink_mode_without_requiring_os_symlink_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            target_blob = git(repo, "hash-object", "-w", "--stdin", input_bytes=b"target\n").decode().strip()
            git(repo, "update-index", "--add", "--cacheinfo", f"120000,{target_blob},indexed-link")
            with self.assertRaisesRegex(ValueError, "symlink"):
                candidate_tree_sha256(repo)

    def test_rejects_indexed_submodule_and_nonregular_worktree_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            head = git(repo, "rev-parse", "HEAD").decode().strip()
            git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},nested-module")
            with self.assertRaisesRegex(ValueError, "submodule"):
                candidate_tree_sha256(repo)

        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            tracked = repo / "tracked.txt"
            tracked.unlink()
            tracked.mkdir()
            with self.assertRaisesRegex(ValueError, "regular|special|directory"):
                candidate_tree_sha256(repo)

    def test_rejects_root_that_is_not_repository_top_level(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = make_repo(Path(temp))
            (repo / "subdir").mkdir()
            with self.assertRaisesRegex(ValueError, "root|repository"):
                candidate_tree_sha256(repo / "subdir")


class SnapshotReferenceTests(unittest.TestCase):
    def test_snapshot_reference_is_frozen_and_validates_hashes_and_counts(self):
        reference = SnapshotReference("a" * 64, "b" * 64, 3, 12, Path("snapshot"))
        self.assertEqual(reference.file_count, 3)
        with self.assertRaises((AttributeError, TypeError)):
            reference.file_count = 4
        with self.assertRaises(ValueError):
            SnapshotReference("bad", "b" * 64, 0, 0, Path("snapshot"))


class EvidenceRecordTests(unittest.TestCase):
    def test_schema_v1_round_trips_as_strict_json(self):
        record = sample_record()
        encoded = encode_evidence_record(record)
        decoded = decode_evidence_record(encoded)
        self.assertEqual(decoded, record)
        self.assertEqual(json.loads(encoded)["schema_version"], 1)
        self.assertTrue(set(decoded.environment).issubset(ALLOWED_ENVIRONMENT_KEYS))

    def test_evidence_record_and_environment_are_frozen(self):
        record = sample_record()
        with self.assertRaises(AttributeError):
            record.task_id = "changed"
        with self.assertRaises(TypeError):
            record.environment["PYTHONUTF8"] = "0"

    def test_rejects_extra_missing_and_duplicate_json_fields(self):
        data = json.loads(encode_evidence_record(sample_record()))
        data["untrusted_source"] = "worker"
        with self.assertRaisesRegex(ValueError, "field|schema|untrusted_source"):
            decode_evidence_record(json.dumps(data))

        data = json.loads(encode_evidence_record(sample_record()))
        del data["task_sha256"]
        with self.assertRaisesRegex(ValueError, "field|schema|task_sha256"):
            decode_evidence_record(json.dumps(data))

        with self.assertRaisesRegex(ValueError, "duplicate"):
            decode_evidence_record('{"schema_version":1,"schema_version":1}')

    def test_rejects_wrong_types_hashes_paths_environment_and_pass_status(self):
        base = json.loads(encode_evidence_record(sample_record()))
        mutations = (
            ("schema_version", True),
            ("passed", 1),
            ("timeout_seconds", True),
            ("unittest_count", True),
            ("exit_code", True),
            ("task_sha256", "not-a-sha"),
            ("stdout_sha256", "A" * 64),
            ("stdout_path", "../outside.log"),
            ("stderr_path", "C:\\outside.log"),
            ("cwd", "../../outside"),
            ("environment", {"API_TOKEN": "secret"}),
            ("environment", {"PYTHONUTF8": 1}),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(base)
                data[field] = value
                with self.assertRaises(ValueError):
                    decode_evidence_record(json.dumps(data))

    def test_pass_requires_zero_exit_stable_candidate_and_positive_unittest_count(self):
        for changes in (
            {"exit_code": 1},
            {"process_status": "timed_out"},
            {"candidate_tree_sha256_after": "9" * 64},
            {"unittest_count": 0},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                sample_record(**changes)

    def test_rejects_non_utc_or_reversed_timestamps_and_invalid_process_status(self):
        for changes in (
            {"started_at_utc": "2026-11-02T10:00:00-08:00"},
            {"finished_at_utc": "2026-11-02T17:00:00Z"},
            {"process_status": "passed"},
            {"process_status": "timed_out", "passed": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                sample_record(**changes)

    def test_pass_requires_confirmed_process_containment(self):
        for status in ("not_started", "unverified"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                sample_record(containment_status=status)

    def test_failed_exit_code_record_is_representable(self):
        record = sample_record(process_status="exited", exit_code=1, passed=False)
        self.assertEqual(decode_evidence_record(encode_evidence_record(record)), record)


if __name__ == "__main__":
    unittest.main()
