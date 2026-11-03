"""Strict parsing and binding for untrusted provider-produced review reports.

Parsing a report never authorizes acceptance. The caller must separately bind
it to an observed runtime invocation, candidate, check manifest, and logs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

try:
    from .check_runner import _snapshot_artifact_sha256, _walk_snapshot, read_check_manifest
    from .execution_evidence import _CandidateTreeEntry, _hash_candidate_entries
    from .reviewer_output import extract_final_response
except ImportError:  # Support direct imports from the scripts directory.
    from check_runner import _snapshot_artifact_sha256, _walk_snapshot, read_check_manifest
    from execution_evidence import _CandidateTreeEntry, _hash_candidate_entries
    from reviewer_output import extract_final_response


_MAX_REPORT_BYTES = 128 * 1024
_IDENTITY_FIELDS = frozenset({
    "task_id", "task_revision", "task_sha256", "base_commit", "worker_role",
    "candidate_tree_sha256", "diff_sha256", "check_manifest_sha256",
})
_REPORT_FIELDS = _IDENTITY_FIELDS | {"schema_version", "verdict", "summary", "findings"}
_FINDING_FIELDS = {"id", "severity", "path", "line", "evidence", "recommendation"}
_SEVERITIES = {"BLOCKER", "HIGH", "MEDIUM", "LOW", "INFO"}
_VERDICTS = {"PASS", "REQUEST_CHANGES", "BLOCKED"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FINDING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_REVIEW_STATUS = frozenset({
    "PASSED", "REQUEST_CHANGES", "BLOCKED", "NOT_RUN", "FAILED", "CANCELLED", "TIMED_OUT",
})
_REVIEW_MANIFEST_FIELDS = frozenset({
    "schema_version", "status", "task_id", "task_revision", "task_sha256", "base_commit",
    "worker_role", "candidate_tree_sha256", "diff_sha256", "check_manifest_path",
    "check_manifest_sha256", "reviewer_role", "reviewer_provider", "runtime_run_id",
    "runtime_adapter_type", "review_independence", "observed_provider",
    "provider_session_id", "verdict", "review_report",
    "review_report_sha256", "input_path", "input_sha256", "stdout_path", "stdout_sha256",
    "stderr_path", "stderr_sha256", "snapshot_path", "review_snapshot_tree_sha256",
    "snapshot_artifact_sha256_before",
    "snapshot_artifact_sha256_after", "started_at_utc", "finished_at_utc", "exit_code",
    "sandbox_effective", "error",
})
_REVIEW_MANIFEST_FIELDS_V2 = _REVIEW_MANIFEST_FIELDS | {"snapshot_logical_modes"}
_MAX_EVIDENCE_FILE_BYTES = 32 * 1024 * 1024
_PROVIDER_ADAPTER_TYPES = {
    "codex": "scripts.provider_runtimes.CodexRuntime",
    "gemini": "scripts.provider_runtimes.GeminiRuntime",
}
_REVIEW_INDEPENDENCE_LIMITATION = "UNVERIFIED_WITHOUT_PROVIDER_E2E"
_REVIEW_ATTEMPT_FIELDS = frozenset({
    "schema_version", "task_id", "task_revision", "task_sha256", "base_commit",
    "worker_role", "reviewer_role", "requested_provider", "runtime_run_id",
    "runtime_adapter_type", "identity", "status", "review_independence",
    "started_at_utc", "finished_at_utc", "error",
})
_REVIEW_ATTEMPT_STATUSES = frozenset({
    "NOT_RUN", "UNAVAILABLE", "FAILED", "CANCELLED", "TIMED_OUT",
    "RESPONSE_INVALID", "SNAPSHOT_MUTATED", "UNVERIFIED_FAKE_RUNTIME",
    "UNVERIFIED_PROVIDER_MISMATCH", "UNVERIFIED_SESSION_ID",
    "UNVERIFIED_SESSION_REUSE", "UNVERIFIED_RUNTIME_ADAPTER",
    "REVIEW_REPORT_VALID", "REVIEW_FINDINGS_RECORDED", "REVIEW_BLOCKED",
})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _require_text(value: Any, label: str, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{label} must be nonempty text within {maximum} UTF-8 bytes")
    if "\x00" in value:
        raise ValueError(f"{label} contains NUL")
    return value


def _validate_identity(identity: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(identity, Mapping) or set(identity) != _IDENTITY_FIELDS:
        raise ValueError("expected review identity fields are incomplete or extra")
    result: dict[str, str] = {}
    for field in _IDENTITY_FIELDS:
        value = identity[field]
        if type(value) is not str or not value or "\x00" in value:
            raise ValueError(f"expected {field} must be a nonempty string")
        result[field] = value
    if not _TASK_ID_RE.fullmatch(result["task_id"]):
        raise ValueError("expected task_id is invalid")
    if len(result["task_revision"]) > 128:
        raise ValueError("expected task_revision is too long")
    if not _SHA256_RE.fullmatch(result["task_sha256"]):
        raise ValueError("expected task_sha256 is invalid")
    if not _GIT_OID_RE.fullmatch(result["base_commit"]):
        raise ValueError("expected base_commit is invalid")
    if not _ROLE_RE.fullmatch(result["worker_role"]):
        raise ValueError("expected worker_role is invalid")
    for field in ("candidate_tree_sha256", "diff_sha256", "check_manifest_sha256"):
        if not _SHA256_RE.fullmatch(result[field]):
            raise ValueError(f"expected {field} is invalid")
    return result


def _validate_finding(value: Any, index: int) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _FINDING_FIELDS:
        raise ValueError(f"finding {index} has missing or extra fields")
    finding_id = value["id"]
    if type(finding_id) is not str or not _FINDING_ID_RE.fullmatch(finding_id):
        raise ValueError(f"finding {index} id is invalid")
    severity = value["severity"]
    if type(severity) is not str or severity not in _SEVERITIES:
        raise ValueError(f"finding {index} severity is invalid")
    path = value["path"]
    line = value["line"]
    if path is not None:
        if type(path) is not str or not path or "\\" in path or "\x00" in path:
            raise ValueError(f"finding {index} path is invalid")
        parsed = PurePosixPath(path)
        windows = PureWindowsPath(path)
        if (parsed.is_absolute() or windows.is_absolute() or windows.drive or
                path in {".", ".."} or
                any(part in {"", ".", ".."} for part in path.split("/")) or
                parsed.as_posix() != path):
            raise ValueError(f"finding {index} path must be a normalized project-relative path")
    if line is not None and (type(line) is not int or line < 1):
        raise ValueError(f"finding {index} line must be null or a positive integer")
    if path is None and line is not None:
        raise ValueError(f"finding {index} line requires a path")
    return {
        "id": finding_id,
        "severity": severity,
        "path": path,
        "line": line,
        "evidence": _require_text(value["evidence"], f"finding {index} evidence", 4000),
        "recommendation": _require_text(value["recommendation"],
                                         f"finding {index} recommendation", 4000),
    }


def parse_review_report(response: str, expected_identity: Mapping[str, Any]) -> dict[str, Any]:
    """Parse one bounded report and require its declared candidate bindings.

    The report is still untrusted. Matching these fields detects accidental or
    stale-candidate mixups; it does not prove that a provider actually read the
    candidate or that a same-user editor did not alter the evidence store.
    """
    identity = _validate_identity(expected_identity)
    if type(response) is not str or not response.strip():
        raise ValueError("review response must be nonempty JSON text")
    encoded = response.encode("utf-8")
    if len(encoded) > _MAX_REPORT_BYTES:
        raise ValueError("review response is too large")
    try:
        report = json.loads(response, object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant)
    except (json.JSONDecodeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"review report is invalid JSON: {exc}") from exc
    if type(report) is not dict or set(report) != _REPORT_FIELDS:
        raise ValueError("review report fields are missing or extra")
    if type(report["schema_version"]) is not int or report["schema_version"] != 1:
        raise ValueError("review report schema_version is unsupported")
    for field, expected in identity.items():
        if type(report[field]) is not str or report[field] != expected:
            raise ValueError(f"review report {field} does not match expected candidate")
    verdict = report["verdict"]
    if type(verdict) is not str or verdict not in _VERDICTS:
        raise ValueError("review report verdict is invalid")
    summary = _require_text(report["summary"], "review summary", 4000)
    findings = report["findings"]
    if type(findings) is not list:
        raise ValueError("review report findings must be an array")
    if len(findings) > 100:
        raise ValueError("review report has too many findings")
    normalized = [_validate_finding(item, index) for index, item in enumerate(findings)]
    ids = [item["id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("review report contains duplicate finding IDs")
    if verdict == "REQUEST_CHANGES" and not normalized:
        raise ValueError("REQUEST_CHANGES requires at least one finding")
    if verdict == "PASS" and any(item["severity"] in {"BLOCKER", "HIGH"} for item in normalized):
        raise ValueError("PASS is inconsistent with blocker/high findings")
    return {"schema_version": 1, **identity, "verdict": verdict,
            "summary": summary, "findings": normalized}


def report_sha256(report: Mapping[str, Any]) -> str:
    """Hash canonical UTF-8 JSON for a validated review report."""
    if type(report) is not dict or set(report) != _REPORT_FIELDS:
        raise ValueError("report must be a validated review report object")
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_identity(data: Mapping[str, Any]) -> dict[str, str]:
    fields = (
        "task_id", "task_revision", "task_sha256", "base_commit", "worker_role",
        "candidate_tree_sha256", "diff_sha256",
    )
    result: dict[str, str] = {}
    for field in fields:
        value = data[field]
        if type(value) is not str or not value or "\x00" in value:
            raise ValueError(f"review manifest {field} must be a nonempty string")
        result[field] = value
    if not _TASK_ID_RE.fullmatch(result["task_id"]):
        raise ValueError("review manifest task_id is invalid")
    if len(result["task_revision"]) > 128:
        raise ValueError("review manifest task_revision is too long")
    if not _SHA256_RE.fullmatch(result["task_sha256"]):
        raise ValueError("review manifest task_sha256 is invalid")
    if not _GIT_OID_RE.fullmatch(result["base_commit"]):
        raise ValueError("review manifest base_commit is invalid")
    if not _ROLE_RE.fullmatch(result["worker_role"]):
        raise ValueError("review manifest worker_role is invalid")
    for field in ("candidate_tree_sha256", "diff_sha256"):
        if not _SHA256_RE.fullmatch(result[field]):
            raise ValueError(f"review manifest {field} is invalid")
    return result


def validate_review_attempt(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a durable attempt record, including failures without full identity."""
    if not isinstance(data, Mapping) or set(data) != _REVIEW_ATTEMPT_FIELDS:
        raise ValueError("review attempt fields are missing or extra")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("review attempt schema_version is unsupported")
    for field, pattern, label in (
        ("task_id", _TASK_ID_RE, "task_id"),
        ("worker_role", _ROLE_RE, "worker_role"),
        ("reviewer_role", _ROLE_RE, "reviewer_role"),
    ):
        value = data[field]
        if type(value) is not str or not pattern.fullmatch(value):
            raise ValueError(f"review attempt {label} is invalid")
    if type(data["task_revision"]) is not str or not data["task_revision"] or len(data["task_revision"])>128:
        raise ValueError("review attempt task_revision is invalid")
    if not _SHA256_RE.fullmatch(data["task_sha256"] if type(data["task_sha256"]) is str else ""):
        raise ValueError("review attempt task_sha256 is invalid")
    if not _GIT_OID_RE.fullmatch(data["base_commit"] if type(data["base_commit"]) is str else ""):
        raise ValueError("review attempt base_commit is invalid")
    if data["requested_provider"] not in {"codex", "gemini"}:
        raise ValueError("review attempt requested_provider is invalid")
    if type(data["runtime_run_id"]) is not str or not data["runtime_run_id"]:
        raise ValueError("review attempt runtime_run_id is invalid")
    adapter_type = data["runtime_adapter_type"]
    if adapter_type is not None and (type(adapter_type) is not str or not adapter_type or
                                     "\x00" in adapter_type or len(adapter_type)>512):
        raise ValueError("review attempt runtime_adapter_type is invalid")
    status = data["status"]
    if type(status) is not str or status not in _REVIEW_ATTEMPT_STATUSES:
        raise ValueError("review attempt status is invalid")
    if data["review_independence"] != _REVIEW_INDEPENDENCE_LIMITATION:
        raise ValueError("review attempt must preserve the unverified independence limitation")
    identity = data["identity"]
    if identity is not None:
        identity = _validate_identity(identity)
        expected = {field: data[field] for field in (
            "task_id", "task_revision", "task_sha256", "base_commit", "worker_role")}
        if any(identity[field] != value for field, value in expected.items()):
            raise ValueError("review attempt identity does not match its task/worker fields")
    error = data["error"]
    if error is not None and (type(error) is not str or not error.strip() or "\x00" in error):
        raise ValueError("review attempt error must be null or nonempty text")
    started = _parse_utc(data["started_at_utc"], "started_at_utc")
    finished = _parse_utc(data["finished_at_utc"], "finished_at_utc")
    if finished < started:
        raise ValueError("review attempt finished_at_utc precedes started_at_utc")
    return {**dict(data), "identity": identity}


def _metadata_root(metadata_root: Path) -> Path:
    argument = Path(metadata_root)
    absolute = argument.absolute()
    cursor = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            cursor = cursor / part
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise ValueError("review metadata root must not contain symlink components")
    except OSError as exc:
        raise ValueError(f"review metadata root cannot be inspected: {exc}") from exc
    try:
        root = argument.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"review metadata root cannot be resolved: {exc}") from exc
    if not root.is_dir():
        raise ValueError("review metadata root must be a directory")
    return root


def _metadata_relative_path(root: Path, value: Any, *, directory: bool) -> Path:
    if type(value) is not str or not value or "\x00" in value or "\\" in value:
        raise ValueError("review artifact path must be normalized metadata-relative POSIX text")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    parts = value.split("/")
    if (posix.is_absolute() or windows.is_absolute() or windows.drive or
            posix.as_posix() != value or any(part in {"", ".", ".."} for part in parts)):
        raise ValueError("review artifact path must be normalized and contained under metadata")
    path = root.joinpath(*parts)
    cursor = root
    try:
        for index, part in enumerate(parts):
            cursor = cursor / part
            info = cursor.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(f"review artifact path contains a symlink: {value!r}")
            if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
                raise ValueError(f"review artifact parent is not a directory: {value!r}")
        if directory and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"review artifact path is not a directory: {value!r}")
        if not directory and not stat.S_ISREG(info.st_mode):
            raise ValueError(f"review artifact path is not a regular file: {value!r}")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"review artifact path escapes metadata: {value!r}")
    except OSError as exc:
        raise ValueError(f"review artifact path cannot be resolved: {value!r}: {exc}") from exc
    return path


def _hash_evidence_file(path: Path) -> str:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("review evidence file is not regular")
        if before.st_size > _MAX_EVIDENCE_FILE_BYTES:
            raise ValueError("review evidence file is too large")
        digest = hashlib.sha256()
        count = 0
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or
                    (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                raise ValueError("review evidence file changed while opening")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                count += len(chunk)
                if count > _MAX_EVIDENCE_FILE_BYTES:
                    raise ValueError("review evidence file is too large")
                digest.update(chunk)
            after_open = os.fstat(stream.fileno())
        after_path = path.lstat()
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns)
        identity_open = (after_open.st_dev, after_open.st_ino, after_open.st_size, after_open.st_mtime_ns)
        if identity_before != identity_after or identity_before != identity_open:
            raise ValueError("review evidence file changed while hashing")
    except OSError as exc:
        raise ValueError(f"review evidence file cannot be hashed: {exc}") from exc
    return digest.hexdigest()


def _validate_optional_file(root: Path, data: Mapping[str, Any], path_field: str,
                            hash_field: str) -> Path | None:
    relative, expected = data[path_field], data[hash_field]
    if relative is None and expected is None:
        return None
    if relative is None or expected is None:
        raise ValueError(f"review manifest {path_field}/{hash_field} must be both null or present")
    if type(expected) is not str or not _SHA256_RE.fullmatch(expected):
        raise ValueError(f"review manifest {hash_field} is invalid")
    path = _metadata_relative_path(root, relative, directory=False)
    if _hash_evidence_file(path) != expected:
        raise ValueError(f"review manifest {hash_field} mismatch or tampering detected")
    return path


def _logical_mode_inventory(value: Any, *, snapshot_present: bool) -> dict[str, bool] | None:
    """Parse canonical source modes without coercing bools or repairing paths."""
    if value is None and not snapshot_present:
        return None
    if type(value) is not list or not snapshot_present:
        raise ValueError("review snapshot logical mode inventory requires a snapshot and a list")
    result: dict[str, bool] = {}
    previous: bytes | None = None
    for item in value:
        if type(item) is not dict or set(item) != {"path", "executable"}:
            raise ValueError("review snapshot logical mode inventory entry fields are missing or extra")
        path = item["path"]
        if type(path) is not str or not path or any(ord(char) < 32 for char in path):
            raise ValueError("review snapshot logical mode inventory path is invalid")
        posix, windows = PurePosixPath(path), PureWindowsPath(path)
        if (posix.is_absolute() or windows.is_absolute() or windows.drive or
                posix.as_posix() != path or any(char in path for char in '\\:*?<>|"') or
                any(part in {"", ".", ".."} or part.casefold() == ".git" or part.endswith((".", " "))
                    for part in path.split("/"))):
            raise ValueError("review snapshot logical mode inventory path must be normalized repository-relative text")
        try:
            raw = path.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("review snapshot logical mode inventory path must be UTF-8") from exc
        if previous is not None and raw <= previous:
            raise ValueError("review snapshot logical mode inventory paths must be unique and canonically ordered")
        if type(item["executable"]) is not bool:
            raise ValueError("review snapshot logical mode inventory executable must be a JSON boolean")
        result[path] = item["executable"]
        previous = raw
    return result


def _review_snapshot_tree_sha256(snapshot: Path, logical_modes: Mapping[str, bool] | None = None,
                                 *, require_mode_match: bool = True) -> str:
    """Hash a fresh Git-visible copy; ignored outputs are not candidate files.

    This tree digest is separate from the artifact digest, which also detects
    later ignored files or other mutations inside the review copy.
    """
    entries = _walk_snapshot(Path(snapshot), ())
    if logical_modes is None:
        return _hash_candidate_entries(entries)  # Legacy schema-1 semantics.
    if require_mode_match and set(logical_modes) != {entry.relative_path for entry in entries}:
        raise ValueError("review snapshot logical mode inventory path set does not match snapshot files")
    bound = []
    for entry in entries:
        executable = logical_modes.get(entry.relative_path, entry.executable)
        if require_mode_match and os.name != "nt" and executable != entry.executable:
            raise ValueError("review snapshot physical executable mode does not match logical mode inventory")
        bound.append(_CandidateTreeEntry(entry.relative_path, entry.raw_path, entry.path,
                                         executable, entry.root))
    return _hash_candidate_entries(tuple(bound))


def _validate_optional_snapshot(root: Path, data: Mapping[str, Any], *, require_stable: bool,
                                logical_modes: Mapping[str, bool] | None = None) -> Path | None:
    path_value = data["snapshot_path"]
    tree_hash = data["review_snapshot_tree_sha256"]
    before = data["snapshot_artifact_sha256_before"]
    after = data["snapshot_artifact_sha256_after"]
    if path_value is None and tree_hash is None and before is None and after is None:
        return None
    if path_value is None or tree_hash is None or before is None or after is None:
        raise ValueError("review snapshot path, tree hash, and artifact hashes must be all null or present")
    if any(type(value) is not str or not _SHA256_RE.fullmatch(value)
           for value in (tree_hash, before, after)):
        raise ValueError("review snapshot tree/artifact hash is invalid")
    if require_stable and before != after:
        raise ValueError("review snapshot changed during reviewer execution")
    path = _metadata_relative_path(root, path_value, directory=True)
    if _snapshot_artifact_sha256(path) != after:
        raise ValueError("review snapshot artifact after hash mismatch or tampering detected")
    actual_tree = _review_snapshot_tree_sha256(path, logical_modes, require_mode_match=require_stable)
    if require_stable and actual_tree != tree_hash:
        raise ValueError("review snapshot tree hash mismatch or tampering detected")
    return path


def _parse_utc(value: Any, label: str) -> datetime:
    if type(value) is not str or not value:
        raise ValueError(f"review manifest {label} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise ValueError(f"review manifest {label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"review manifest {label} must have a UTC offset")
    return parsed.astimezone(timezone.utc)


def _validate_review_input(path: Path, data: Mapping[str, Any],
                           expected_identity: Mapping[str, Any]) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > _MAX_EVIDENCE_FILE_BYTES:
            raise ValueError("review input is too large")
        if hashlib.sha256(raw).hexdigest() != data["input_sha256"]:
            raise ValueError("review input changed while it was being validated")
        source = raw.decode("utf-8")
        input_data = json.loads(source, object_pairs_hook=_unique_object,
                                parse_constant=_invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"review input is invalid: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"review input is invalid: {exc}") from exc
    fields = {"schema_version", "identity", "reviewer_role", "requested_provider", "prompt", "diff"}
    if type(input_data) is not dict or set(input_data) != fields:
        raise ValueError("review input fields are missing or extra")
    if type(input_data["schema_version"]) is not int or input_data["schema_version"] != 1:
        raise ValueError("review input schema_version is unsupported")
    input_identity = input_data["identity"]
    if type(input_identity) is not dict or set(input_identity) != _IDENTITY_FIELDS:
        raise ValueError("review input identity fields are missing or extra")
    if input_identity != dict(expected_identity):
        raise ValueError("review input identity does not match the review manifest")
    if input_data["reviewer_role"] != data["reviewer_role"]:
        raise ValueError("review input reviewer_role does not match the review manifest")
    if input_data["requested_provider"] != data["reviewer_provider"]:
        raise ValueError("review input requested_provider does not match the review manifest")
    prompt = input_data["prompt"]
    diff = input_data["diff"]
    if (type(prompt) is not str or not prompt or "\x00" in prompt or
            len(prompt.encode("utf-8")) > _MAX_EVIDENCE_FILE_BYTES):
        raise ValueError("review input prompt is invalid or too large")
    if type(diff) is not str or "\x00" in diff or len(diff.encode("utf-8")) > _MAX_EVIDENCE_FILE_BYTES:
        raise ValueError("review input diff is invalid or too large")
    begin = "<<<SSEC_DIFF_BEGIN>>>\n"
    end = "<<<SSEC_DIFF_END>>>"
    if prompt.count(begin) != 1 or prompt.count(end) != 1:
        raise ValueError("review prompt must contain exactly one bounded diff block")
    start_index = prompt.index(begin) + len(begin)
    end_index = prompt.index(end)
    if end_index < start_index or prompt[start_index:end_index] != diff:
        raise ValueError("review prompt diff block does not match the input diff")
    actual_diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    if actual_diff_hash != data["diff_sha256"]:
        raise ValueError("review input diff_sha256 does not match the review manifest")
    return input_data


def validate_review_manifest(data: Mapping[str, Any], metadata_root: Path) -> dict[str, Any]:
    """Validate a durable review record against its persisted inputs and outputs.

    Hashes bind bytes and snapshot contents but do not authenticate the CLI,
    provider account, reviewer identity, scientific claims, or same-user edits.
    Any malformed or inconsistent record raises ``ValueError`` and must block
    downstream acceptance decisions.
    """
    if not isinstance(data, Mapping):
        raise ValueError("review manifest fields are missing or extra")
    version = data.get("schema_version")
    if type(version) is not int or version not in {1, 2}:
        raise ValueError("review manifest schema_version is unsupported")
    fields = _REVIEW_MANIFEST_FIELDS if version == 1 else _REVIEW_MANIFEST_FIELDS_V2
    if set(data) != fields:
        raise ValueError("review manifest fields are missing or extra")
    logical_modes = (_logical_mode_inventory(data["snapshot_logical_modes"],
                       snapshot_present=data["snapshot_path"] is not None) if version == 2 else None)
    status = data["status"]
    if type(status) is not str or status not in _REVIEW_STATUS:
        raise ValueError("review manifest status is invalid")
    identity = _manifest_identity(data)
    reviewer_role = data["reviewer_role"]
    if type(reviewer_role) is not str or not _ROLE_RE.fullmatch(reviewer_role):
        raise ValueError("review manifest reviewer_role is invalid")
    reviewer_provider = data["reviewer_provider"]
    if type(reviewer_provider) is not str or reviewer_provider not in {"codex", "gemini"}:
        raise ValueError("review manifest reviewer_provider is invalid")
    for field in ("runtime_run_id", "runtime_adapter_type", "observed_provider",
                  "provider_session_id"):
        value = data[field]
        if value is not None and (type(value) is not str or not value or "\x00" in value):
            raise ValueError(f"review manifest {field} must be null or nonempty text")
    if data["review_independence"] != _REVIEW_INDEPENDENCE_LIMITATION:
        raise ValueError("review manifest must preserve the unverified independence limitation")
    if data["observed_provider"] is not None and data["observed_provider"] != reviewer_provider:
        if status in {"PASSED", "REQUEST_CHANGES", "BLOCKED"}:
            raise ValueError("observed provider does not match the configured reviewer provider")
    exit_code = data["exit_code"]
    if exit_code is not None and type(exit_code) is not int:
        raise ValueError("review manifest exit_code must be an integer or null")
    if data["sandbox_effective"] is not None and type(data["sandbox_effective"]) is not bool:
        raise ValueError("review manifest sandbox_effective must be boolean or null")
    error = data["error"]
    if error is not None and (type(error) is not str or not error.strip() or "\x00" in error):
        raise ValueError("review manifest error must be null or nonempty text")
    started = _parse_utc(data["started_at_utc"], "started_at_utc")
    finished = _parse_utc(data["finished_at_utc"], "finished_at_utc")
    if finished < started:
        raise ValueError("review manifest finished_at_utc precedes started_at_utc")

    verdict = data["verdict"]
    review_report = data["review_report"]
    review_report_digest = data["review_report_sha256"]
    if review_report is None:
        if verdict is not None or review_report_digest is not None:
            raise ValueError("review verdict/hash cannot exist without a review report")
    else:
        if type(review_report) is not dict:
            raise ValueError("review manifest review_report must be an object or null")
        if type(verdict) is not str or verdict not in _VERDICTS:
            raise ValueError("review manifest verdict is invalid")
        if type(review_report_digest) is not str or not _SHA256_RE.fullmatch(review_report_digest):
            raise ValueError("review manifest review_report_sha256 is invalid")

    root = _metadata_root(metadata_root)
    check_manifest_path = _validate_optional_file(
        root, data, "check_manifest_path", "check_manifest_sha256"
    )
    input_path = _validate_optional_file(root, data, "input_path", "input_sha256")
    stdout_path = _validate_optional_file(root, data, "stdout_path", "stdout_sha256")
    stderr_path = _validate_optional_file(root, data, "stderr_path", "stderr_sha256")

    has_report = review_report is not None
    requires_report = status in {"PASSED", "REQUEST_CHANGES"}
    if requires_report and not has_report:
        raise ValueError(f"review status {status} requires a validated report")
    successful_report = status in {"PASSED", "REQUEST_CHANGES"} or (status == "BLOCKED" and has_report)
    snapshot_path = _validate_optional_snapshot(root, data, require_stable=successful_report,
                                                logical_modes=logical_modes)
    if (data["review_snapshot_tree_sha256"] is not None and
            data["review_snapshot_tree_sha256"] != identity["candidate_tree_sha256"]):
        raise ValueError("review snapshot tree does not match candidate_tree_sha256")
    if successful_report:
        if (check_manifest_path is None or input_path is None or stdout_path is None or
                stderr_path is None or snapshot_path is None):
            raise ValueError(f"review status {status} requires complete file evidence")
        if (data["runtime_run_id"] is None or data["observed_provider"] != reviewer_provider or
                data["provider_session_id"] is None):
            raise ValueError(f"review status {status} requires observed provider/session identity")
        if data["runtime_adapter_type"] != _PROVIDER_ADAPTER_TYPES[reviewer_provider]:
            raise ValueError(f"review status {status} requires the concrete provider runtime adapter")
        if exit_code != 0 or error is not None:
            raise ValueError(f"review status {status} requires successful exit without an error")
        expected_verdict = {
            "PASSED": "PASS", "REQUEST_CHANGES": "REQUEST_CHANGES", "BLOCKED": "BLOCKED",
        }[status]
        if verdict != expected_verdict:
            raise ValueError(f"review status {status} disagrees with the report verdict")
    elif status in {"NOT_RUN", "FAILED", "CANCELLED", "TIMED_OUT"}:
        if has_report:
            raise ValueError(f"review status {status} cannot carry a validated report")
        if error is None:
            raise ValueError(f"review status {status} requires an explanatory error")
    elif status == "BLOCKED":
        if error is None:
            raise ValueError("BLOCKED review without a report requires an explanatory error")

    normalized_report: dict[str, Any] | None = None
    if check_manifest_path is not None:
        if _hash_evidence_file(check_manifest_path) != data["check_manifest_sha256"]:
            raise ValueError("check manifest changed during review-manifest validation")
        try:
            checked = read_check_manifest(check_manifest_path, root)
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise ValueError(f"review check manifest is invalid: {exc}") from exc
        expected_check_identity = {
            "task_id": identity["task_id"], "task_revision": identity["task_revision"],
            "task_sha256": identity["task_sha256"], "base_commit": identity["base_commit"],
            "worker_role": identity["worker_role"],
            "candidate_tree_sha256": identity["candidate_tree_sha256"],
        }
        for field, expected in expected_check_identity.items():
            actual_field = "candidate_tree_sha256" if field == "candidate_tree_sha256" else field
            if checked.get(actual_field) != expected:
                raise ValueError(f"review check manifest {field} does not match review candidate")
        if checked.get("status") != "PASSED":
            raise ValueError("review check manifest is not PASSED")
        check_snapshot = checked.get("snapshot")
        if check_snapshot is None:
            if status in {"PASSED", "REQUEST_CHANGES"}:
                raise ValueError("review candidate has no archived check snapshot")
        elif check_snapshot.get("snapshot_tree_sha256") != identity["candidate_tree_sha256"]:
            raise ValueError("check manifest snapshot tree does not match candidate_tree_sha256")
        if successful_report and snapshot_path is None:
            raise ValueError("review candidate has no independent review snapshot")

    expected_identity = {
        **identity,
        "check_manifest_sha256": data["check_manifest_sha256"],
    }
    if input_path is not None:
        _validate_review_input(input_path, data, expected_identity)
    if has_report:
        if stdout_path is None:
            raise ValueError("review report is not linked to a persisted provider output")
        try:
            response = extract_final_response(str(data["observed_provider"]), stdout_path)
            if _hash_evidence_file(stdout_path) != data["stdout_sha256"]:
                raise ValueError("reviewer stdout changed while it was being validated")
            normalized_report = parse_review_report(response, expected_identity)
            if normalized_report != review_report:
                raise ValueError("stored review report differs from the report in provider output")
            if normalized_report["verdict"] != verdict:
                raise ValueError("review manifest verdict differs from parsed report")
            if report_sha256(normalized_report) != review_report_digest:
                raise ValueError("review report hash mismatch or tampering detected")
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise ValueError(f"review report evidence is invalid: {exc}") from exc

    normalized = dict(data)
    if normalized_report is not None:
        normalized["review_report"] = normalized_report
    return normalized
