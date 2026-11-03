"""Canonical task, candidate-tree, and coordinator-written evidence contracts.

Hashes in this module identify byte content; they do not establish who wrote a
record or whether a check result is trustworthy or scientifically valid.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, Mapping


ALLOWED_ENVIRONMENT_KEYS = frozenset({
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "PYTHONHASHSEED",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "VIRTUAL_ENV",
    "WINDIR",
})
_CHECK_SPEC_FIELDS = frozenset({"check_id", "argv", "cwd", "timeout_seconds", "protocol"})
_PROTOCOLS = frozenset({"exit_code", "unittest"})
_EVIDENCE_PROCESS_STATUSES = frozenset({"exited", "timed_out", "cancelled", "spawn_error"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_UTC_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)
_EVIDENCE_FIELDS = (
    "task_id",
    "task_revision",
    "task_sha256",
    "execution_id",
    "check_id",
    "worker_role",
    "worker_branch",
    "base_commit",
    "candidate_tree_sha256_before",
    "candidate_tree_sha256_after",
    "executable",
    "executable_sha256",
    "protocol",
    "argv",
    "cwd",
    "operating_system",
    "python_version",
    "environment",
    "started_at_utc",
    "finished_at_utc",
    "timeout_seconds",
    "process_status",
    "exit_code",
    "unittest_count",
    "stdout_path",
    "stdout_sha256",
    "stderr_path",
    "stderr_sha256",
    "passed",
)


def _require_nonempty_string(value: Any, label: str, *, allow_nul: bool = False) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    if not allow_nul and "\x00" in value:
        raise ValueError(f"{label} must not contain NUL")
    return value


def _validate_relative_path(value: Any, label: str, *, allow_dot: bool = False) -> str:
    text = _require_nonempty_string(value, label)
    posix = PurePosixPath(text.replace("\\", "/"))
    windows = PureWindowsPath(text)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"{label} must be a relative contained path")
    parts = text.replace("\\", "/").split("/")
    if any(PureWindowsPath(part).drive for part in parts):
        raise ValueError(f"{label} must not contain a drive-qualified path component")
    if any(part == ".." for part in parts):
        raise ValueError(f"{label} must not traverse outside its root")
    if any(part == "" for part in parts):
        raise ValueError(f"{label} must not contain an empty path component")
    if not allow_dot and any(part == "." for part in parts):
        raise ValueError(f"{label} must name a file below its root")
    if not allow_dot and text.endswith(("/", "\\")):
        raise ValueError(f"{label} must name a file, not a directory")
    return text


def _validate_sha256(value: Any, label: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase 64-character SHA-256 hex digest")
    return value


def _validate_timeout(value: Any, label: str = "timeout_seconds") -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite positive number (bool is invalid)")
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{label} must be a finite positive number") from None
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return numeric


def _json_native(value: Any, label: str, active: set[int]) -> Any:
    """Validate native JSON shapes while preserving their values for encoding."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{label} contains NaN or an infinite number, which is not valid JSON")
        return value
    if type(value) is list:
        identity = id(value)
        if identity in active:
            raise ValueError(f"{label} contains a cyclic value, which is not valid JSON")
        active.add(identity)
        try:
            return [_json_native(item, label, active) for item in value]
        finally:
            active.remove(identity)
    if type(value) is dict:
        identity = id(value)
        if identity in active:
            raise ValueError(f"{label} contains a cyclic value, which is not valid JSON")
        active.add(identity)
        try:
            if any(type(key) is not str for key in value):
                raise ValueError(f"{label} object keys must be strings for JSON")
            return {key: _json_native(item, label, active) for key, item in value.items()}
        finally:
            active.remove(identity)
    raise ValueError(f"{label} contains a non-JSON value of type {type(value).__name__}")


def canonical_task_sha256(task: Mapping[str, Any]) -> str:
    """Return SHA-256 of a stable, compact JSON encoding of the complete task."""
    if not isinstance(task, Mapping):
        raise ValueError("task must be a JSON-compatible mapping")
    try:
        top_level = dict(task)
        normalized = _json_native(top_level, "task", set())
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("task"):
            raise
        raise ValueError(f"task cannot be encoded as canonical JSON: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    argv: tuple[str, ...]
    cwd: str
    timeout_seconds: float
    protocol: str

    def __post_init__(self) -> None:
        _require_nonempty_string(self.check_id, "check_id")
        if type(self.argv) is not tuple or not self.argv:
            raise ValueError("argv must be a nonempty tuple of strings")
        for index, arg in enumerate(self.argv):
            if type(arg) is not str or not arg or "\x00" in arg:
                raise ValueError(f"argv[{index}] must be a nonempty NUL-free string")
        _validate_relative_path(self.cwd, "cwd", allow_dot=True)
        object.__setattr__(self, "timeout_seconds", _validate_timeout(self.timeout_seconds))
        if type(self.protocol) is not str or self.protocol not in _PROTOCOLS:
            raise ValueError("protocol must be 'exit_code' or 'unittest'")


def validate_check_specs(task: Mapping[str, Any]) -> tuple[CheckSpec, ...]:
    """Validate optional typed check specs; legacy tasks without the field remain valid."""
    if not isinstance(task, Mapping):
        raise ValueError("task must be a JSON object")
    if "check_specs" not in task:
        return ()
    raw_specs = task["check_specs"]
    if type(raw_specs) is not list:
        raise ValueError("check_specs must be a list")

    # Import the router helpers only when validating, so module initialization stays acyclic.
    try:
        from .route_task import _required_checks_for_valid_task, _validate_task_fields
    except ImportError:  # Support direct execution/import from scripts directory.
        from route_task import _required_checks_for_valid_task, _validate_task_fields
    task_data = dict(task)
    _validate_task_fields(task_data)
    allowed_ids = set(_required_checks_for_valid_task(task_data))

    result: list[CheckSpec] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_specs):
        if type(raw) is not dict:
            raise ValueError(f"check_specs[{index}] must be an object")
        if set(raw) != _CHECK_SPEC_FIELDS:
            missing = sorted(_CHECK_SPEC_FIELDS - set(raw))
            extra = sorted(set(raw) - _CHECK_SPEC_FIELDS)
            raise ValueError(f"check_specs[{index}] has wrong fields (missing={missing}, extra={extra})")
        check_id = raw["check_id"]
        if type(check_id) is not str or not check_id.strip():
            raise ValueError(f"check_specs[{index}].check_id must be a nonempty string")
        if check_id in seen:
            raise ValueError(f"check_specs contains duplicate check_id {check_id!r}")
        if check_id not in allowed_ids:
            raise ValueError(f"check_id {check_id!r} is not required for this task")
        argv = raw["argv"]
        if type(argv) is not list:
            raise ValueError(f"check_specs[{index}].argv must be a list")
        spec = CheckSpec(
            check_id=check_id,
            argv=tuple(argv),
            cwd=raw["cwd"],
            timeout_seconds=raw["timeout_seconds"],
            protocol=raw["protocol"],
        )
        if check_id == "unit_tests" and spec.protocol != "unittest":
            raise ValueError("unit_tests requires the unittest protocol")
        seen.add(check_id)
        result.append(spec)
    return tuple(result)


@dataclass(frozen=True)
class SnapshotReference:
    source_tree_sha256: str
    snapshot_tree_sha256: str
    file_count: int
    total_bytes: int
    snapshot_path: Path

    def __post_init__(self) -> None:
        _validate_sha256(self.source_tree_sha256, "source_tree_sha256")
        _validate_sha256(self.snapshot_tree_sha256, "snapshot_tree_sha256")
        for name, value in (("file_count", self.file_count), ("total_bytes", self.total_bytes)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not isinstance(self.snapshot_path, Path):
            raise ValueError("snapshot_path must be a pathlib.Path")


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ValueError(f"could not run git while hashing candidate tree: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed while hashing candidate tree: {detail}")
    return result.stdout


def _git_index_entries(data: bytes) -> dict[bytes, bytes]:
    entries: dict[bytes, bytes] = {}
    if not data:
        return entries
    for record in data.split(b"\x00"):
        if not record:
            continue
        try:
            metadata, path = record.split(b"\t", 1)
            mode, _object_id, stage = metadata.split(b" ", 2)
        except ValueError as exc:
            raise ValueError("git returned malformed index data while hashing candidate tree") from exc
        if stage != b"0":
            raise ValueError(f"candidate index contains an unmerged path: {os.fsdecode(path)!r}")
        if path in entries:
            raise ValueError(f"candidate index contains duplicate path: {os.fsdecode(path)!r}")
        if mode == b"120000":
            raise ValueError(f"candidate contains an indexed symlink: {os.fsdecode(path)!r}")
        if mode == b"160000":
            raise ValueError(f"candidate contains an indexed submodule: {os.fsdecode(path)!r}")
        if mode not in (b"100644", b"100755"):
            raise ValueError(f"candidate contains unsupported Git mode {mode!r}")
        entries[path] = mode
    return entries


def _validate_git_path(raw_path: bytes) -> tuple[str, ...] | None:
    if not raw_path or b"\x00" in raw_path or raw_path.startswith((b"/", b"\\")):
        raise ValueError("git returned an absolute or empty candidate path")
    if os.name == "nt" and b"\\" in raw_path:
        raise ValueError(f"candidate path contains a platform-ambiguous separator: {os.fsdecode(raw_path)!r}")
    raw_parts = raw_path.split(b"/")
    if any(part in (b"", b".", b"..") for part in raw_parts):
        raise ValueError(f"candidate path escapes or is not normalized: {os.fsdecode(raw_path)!r}")
    if any(part == b".git" for part in raw_parts):
        return None
    decoded = tuple(os.fsdecode(part) for part in raw_parts)
    if not decoded or (os.name == "nt" and any(PureWindowsPath(part).drive for part in decoded)):
        raise ValueError(f"candidate path is not relative: {os.fsdecode(raw_path)!r}")
    return decoded


def _lstat_candidate(path: Path, root: Path, components: tuple[str, ...], raw_path: bytes):
    cursor = root
    try:
        for index, component in enumerate(components):
            cursor = cursor / component
            item_stat = cursor.lstat()
            if stat.S_ISLNK(item_stat.st_mode):
                raise ValueError(f"candidate contains a filesystem symlink: {os.fsdecode(raw_path)!r}")
            if index < len(components) - 1 and not stat.S_ISDIR(item_stat.st_mode):
                raise ValueError(f"candidate path has a non-directory parent: {os.fsdecode(raw_path)!r}")
            if index == len(components) - 1 and not stat.S_ISREG(item_stat.st_mode):
                raise ValueError(f"candidate contains a non-regular or special file: {os.fsdecode(raw_path)!r}")
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise ValueError(f"could not inspect candidate path {os.fsdecode(raw_path)!r}: {exc}") from exc
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"candidate path escapes repository root: {os.fsdecode(raw_path)!r}")
    except OSError as exc:
        raise ValueError(f"could not resolve candidate path {os.fsdecode(raw_path)!r}: {exc}") from exc
    return item_stat


def _hash_file_into(digest, path: Path, initial_stat, label: str) -> int:
    expected_size = initial_stat.st_size
    if expected_size < 0:
        raise ValueError(f"candidate file has invalid size: {label!r}")
    digest.update(expected_size.to_bytes(8, "big", signed=False))
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(path, flags)
        with os.fdopen(file_descriptor, "rb") as stream:
            opened_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened_stat.st_mode):
                raise ValueError(f"candidate contains a non-regular or special file: {label!r}")
            if (opened_stat.st_dev, opened_stat.st_ino) != (initial_stat.st_dev, initial_stat.st_ino):
                raise ValueError(f"candidate path changed while hashing: {label!r}")
            count = 0
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                digest.update(chunk)
            final_opened_stat = os.fstat(stream.fileno())
        final_path_stat = path.lstat()
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"could not read candidate file {label!r}: {exc}") from exc
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")
    if count != expected_size or any(
        getattr(initial_stat, field, None) != getattr(final_opened_stat, field, None)
        for field in stable_fields
    ):
        raise ValueError(f"candidate file changed while hashing: {label!r}")
    if stat.S_ISLNK(final_path_stat.st_mode):
        raise ValueError(f"candidate contains a filesystem symlink: {label!r}")
    if (not stat.S_ISREG(final_path_stat.st_mode) or
            (final_path_stat.st_dev, final_path_stat.st_ino) != (initial_stat.st_dev, initial_stat.st_ino)):
        raise ValueError(f"candidate path changed while hashing: {label!r}")
    return count


def candidate_tree_sha256(root: Path) -> str:
    """Hash tracked and non-ignored untracked regular files in a Git root.

    Each sorted record uses length-prefixed path bytes, an executable-bit byte,
    a length-prefixed file size, and the exact file bytes. Git metadata and
    ignored files are excluded. Symlinks, submodules, special files, and read
    errors fail closed.
    """
    original_root = Path(root)
    try:
        original_stat = original_root.lstat()
    except OSError as exc:
        raise ValueError(f"candidate root cannot be inspected: {exc}") from exc
    if stat.S_ISLNK(original_stat.st_mode):
        raise ValueError("candidate root must not be a symlink")
    try:
        root_path = original_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"candidate root does not exist: {exc}") from exc
    if not root_path.is_dir():
        raise ValueError("candidate root must be a directory")

    top_text = os.fsdecode(_git(root_path, "rev-parse", "--show-toplevel").rstrip(b"\r\n"))
    try:
        git_root = Path(top_text).resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"git repository root cannot be resolved: {exc}") from exc
    if git_root != root_path:
        raise ValueError("candidate root must be the Git repository top-level directory")

    tracked = _git_index_entries(_git(root_path, "ls-files", "--stage", "-z"))
    untracked_raw = _git(root_path, "ls-files", "--others", "--exclude-standard", "-z")
    untracked = {entry for entry in untracked_raw.split(b"\x00") if entry}
    paths = sorted(set(tracked) | untracked)

    digest = hashlib.sha256()
    digest.update(b"ssec-candidate-tree-v1\x00")
    for raw_path in paths:
        components = _validate_git_path(raw_path)
        if components is None:
            continue
        file_path = root_path.joinpath(*components)
        file_stat = _lstat_candidate(file_path, root_path, components, raw_path)
        if file_stat is None:
            if raw_path in tracked:
                # A missing tracked path is a deletion in the current candidate tree.
                continue
            raise ValueError(f"untracked candidate path disappeared while hashing: {os.fsdecode(raw_path)!r}")

        if os.name == "nt" and raw_path in tracked:
            executable = tracked[raw_path] == b"100755"
        else:
            executable = bool(file_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        path_bytes = raw_path
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(b"\x01" if executable else b"\x00")
        _hash_file_into(digest, file_path, file_stat, os.fsdecode(raw_path))
    return digest.hexdigest()


def _parse_utc_timestamp(value: Any, label: str) -> datetime:
    if type(value) is not str or not _UTC_TIMESTAMP_RE.fullmatch(value):
        raise ValueError(f"{label} must be an ISO-8601 UTC timestamp ending in Z or +00:00")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return parsed


def _is_absolute_executable(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


@dataclass(frozen=True)
class EvidenceRecord:
    task_id: str
    task_revision: str
    task_sha256: str
    execution_id: str
    check_id: str
    worker_role: str
    worker_branch: str
    base_commit: str
    candidate_tree_sha256_before: str
    candidate_tree_sha256_after: str
    executable: str
    executable_sha256: str
    protocol: str
    argv: tuple[str, ...]
    cwd: str
    operating_system: str
    python_version: str
    environment: Mapping[str, str]
    started_at_utc: str
    finished_at_utc: str
    timeout_seconds: float
    process_status: str
    exit_code: int | None
    unittest_count: int | None
    stdout_path: str
    stdout_sha256: str
    stderr_path: str
    stderr_sha256: str
    passed: bool

    def __post_init__(self) -> None:
        for name in (
            "task_id", "task_revision", "execution_id", "check_id", "worker_role",
            "worker_branch", "operating_system", "python_version",
        ):
            _require_nonempty_string(getattr(self, name), name)
        _validate_sha256(self.task_sha256, "task_sha256")
        if type(self.base_commit) is not str or not _GIT_OID_RE.fullmatch(self.base_commit):
            raise ValueError("base_commit must be a 40- or 64-character lowercase Git object ID")
        _validate_sha256(self.candidate_tree_sha256_before, "candidate_tree_sha256_before")
        _validate_sha256(self.candidate_tree_sha256_after, "candidate_tree_sha256_after")
        _validate_sha256(self.executable_sha256, "executable_sha256")
        _validate_sha256(self.stdout_sha256, "stdout_sha256")
        _validate_sha256(self.stderr_sha256, "stderr_sha256")

        executable = _require_nonempty_string(self.executable, "executable")
        if not _is_absolute_executable(executable):
            raise ValueError("executable must be an absolute resolved path")
        if type(self.protocol) is not str or self.protocol not in _PROTOCOLS:
            raise ValueError("protocol must be 'exit_code' or 'unittest'")
        if type(self.argv) is not tuple or not self.argv:
            raise ValueError("argv must be a nonempty tuple of strings")
        for index, arg in enumerate(self.argv):
            if type(arg) is not str or not arg or "\x00" in arg:
                raise ValueError(f"argv[{index}] must be a nonempty NUL-free string")
        _validate_relative_path(self.cwd, "cwd", allow_dot=True)
        _require_nonempty_string(self.operating_system, "operating_system")
        _require_nonempty_string(self.python_version, "python_version")

        if not isinstance(self.environment, Mapping):
            raise ValueError("environment must be an object of allowlisted string values")
        normalized_environment: dict[str, str] = {}
        for key, value in self.environment.items():
            if type(key) is not str or key not in ALLOWED_ENVIRONMENT_KEYS:
                raise ValueError(f"environment key {key!r} is not allowlisted")
            if type(value) is not str or "\x00" in value:
                raise ValueError(f"environment[{key!r}] must be a NUL-free string")
            normalized_environment[key] = value
        object.__setattr__(self, "environment", MappingProxyType(dict(sorted(normalized_environment.items()))))

        started = _parse_utc_timestamp(self.started_at_utc, "started_at_utc")
        finished = _parse_utc_timestamp(self.finished_at_utc, "finished_at_utc")
        if finished < started:
            raise ValueError("finished_at_utc must not precede started_at_utc")
        object.__setattr__(self, "timeout_seconds", _validate_timeout(self.timeout_seconds))

        if type(self.process_status) is not str or self.process_status not in _EVIDENCE_PROCESS_STATUSES:
            raise ValueError(f"process_status must be one of {sorted(_EVIDENCE_PROCESS_STATUSES)}")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ValueError("exit_code must be an integer or null")
        if self.unittest_count is not None and (type(self.unittest_count) is not int or self.unittest_count < 0):
            raise ValueError("unittest_count must be a nonnegative integer or null")
        if self.protocol == "exit_code" and self.unittest_count is not None:
            raise ValueError("exit_code protocol must not include unittest_count")
        if self.check_id == "unit_tests" and self.protocol != "unittest":
            raise ValueError("unit_tests requires the unittest protocol")
        if self.process_status == "exited" and self.exit_code is None:
            raise ValueError("an exited process must include exit_code")
        if type(self.passed) is not bool:
            raise ValueError("passed must be a boolean")
        _validate_relative_path(self.stdout_path, "stdout_path")
        _validate_relative_path(self.stderr_path, "stderr_path")
        if self.stdout_path == self.stderr_path:
            raise ValueError("stdout_path and stderr_path must be distinct")
        if self.passed:
            if self.process_status != "exited" or self.exit_code != 0:
                raise ValueError("passed evidence requires an exited process with exit_code 0")
            if self.candidate_tree_sha256_before != self.candidate_tree_sha256_after:
                raise ValueError("passed evidence requires an unchanged candidate tree")
            if self.protocol == "unittest" and (self.unittest_count is None or self.unittest_count < 1):
                raise ValueError("passed unittest evidence requires at least one executed test")

    def to_dict(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in _EVIDENCE_FIELDS}
        result["argv"] = list(self.argv)
        result["environment"] = dict(self.environment)
        result["schema_version"] = 1
        return {"schema_version": result.pop("schema_version"), **result}


def encode_evidence_record(record: EvidenceRecord) -> str:
    """Encode a schema-v1 record as deterministic JSON without trust metadata."""
    if not isinstance(record, EvidenceRecord):
        raise ValueError("record must be an EvidenceRecord")
    return json.dumps(
        record.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str):
    raise ValueError(f"non-JSON numeric constant {value!r} is not allowed")


def decode_evidence_record(payload: str | bytes) -> EvidenceRecord:
    """Decode and strictly validate a schema-v1 JSON evidence record."""
    if type(payload) is bytes:
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("evidence JSON must be UTF-8") from exc
    if type(payload) is not str:
        raise ValueError("evidence payload must be a JSON string or UTF-8 bytes")
    try:
        data = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise ValueError(f"invalid evidence JSON: {exc}") from exc
    if type(data) is not dict:
        raise ValueError("evidence JSON must be an object")
    expected = set(_EVIDENCE_FIELDS) | {"schema_version"}
    if set(data) != expected:
        missing = sorted(expected - set(data))
        extra = sorted(set(data) - expected)
        raise ValueError(f"evidence object has wrong fields (missing={missing}, extra={extra})")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if type(data["argv"]) is not list:
        raise ValueError("argv must be a JSON array")
    if type(data["environment"]) is not dict:
        raise ValueError("environment must be a JSON object")
    values = {name: data[name] for name in _EVIDENCE_FIELDS}
    values["argv"] = tuple(values["argv"])
    try:
        return EvidenceRecord(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid evidence record: {exc}") from exc
