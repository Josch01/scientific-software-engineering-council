"""Run user-declared checks on isolated Git-visible candidate snapshots."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

try:
    from .execution_evidence import (
        ALLOWED_ENVIRONMENT_KEYS,
        _CandidateTreeEntry,
        CheckSpec,
        EvidenceRecord,
        SnapshotReference,
        _candidate_tree_entries,
        _hash_candidate_entries,
        _hash_file_into,
        _lstat_candidate,
        candidate_tree_sha256,
        canonical_task_sha256,
        decode_evidence_record,
        validate_check_specs,
    )
    from .process_containment import new_containment
except ImportError:  # Support direct imports from the scripts directory.
    from execution_evidence import (
        ALLOWED_ENVIRONMENT_KEYS,
        _CandidateTreeEntry,
        CheckSpec,
        EvidenceRecord,
        SnapshotReference,
        _candidate_tree_entries,
        _hash_candidate_entries,
        _hash_file_into,
        _lstat_candidate,
        candidate_tree_sha256,
        canonical_task_sha256,
        decode_evidence_record,
        validate_check_specs,
    )
    from process_containment import new_containment


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_ROLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_UNITTEST_RAN_RE = re.compile(rb"(?m)^Ran ([0-9]+) tests? in [0-9.]+s\r?$")
_UNITTEST_OK_RE = re.compile(rb"(?m)^OK(?:\s|$)")
_PROTOCOLS = frozenset({"exit_code", "unittest"})
_MANIFEST_SCHEMA_VERSION = 2
_MANIFEST_FIELDS = frozenset({
    "schema_version",
    "terminal",
    "status",
    "task_id",
    "task_revision",
    "task_sha256",
    "execution_id",
    "worker_role",
    "worker_branch",
    "base_commit",
    "candidate_tree_sha256",
    "snapshot",
    "started_at_utc",
    "finished_at_utc",
    "checks",
    "errors",
})
_CHECK_RESULT_FIELDS = frozenset({
    "check_id",
    "argv",
    "cwd",
    "timeout_seconds",
    "protocol",
    "result_status",
    "error",
    "stdout_path",
    "stdout_sha256",
    "stderr_path",
    "stderr_sha256",
    "record",
})


@dataclass(frozen=True)
class CheckRunResult:
    status: str
    execution_id: str | None
    manifest_path: Path | None
    records: tuple[EvidenceRecord, ...]
    errors: tuple[str, ...]
    snapshot: SnapshotReference | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ValueError(f"could not run git for candidate snapshot: {exc}") from exc
    if result.returncode != 0 and not (args[:1] == ("check-ignore",) and result.returncode == 1):
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed for candidate snapshot: {detail}")
    return result.stdout


def _copy_candidate_file(entry: _CandidateTreeEntry, destination_file: Path) -> int:
    source_file = entry.path
    initial = _lstat_candidate(source_file, entry.root,
                               tuple(entry.relative_path.split("/")), entry.raw_path)
    if initial is None:
        raise ValueError(f"candidate file disappeared before copy: {entry.relative_path!r}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source_file, flags)
        with os.fdopen(descriptor, "rb") as src, destination_file.open("xb") as dst:
            opened = os.fstat(src.fileno())
            if (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino):
                raise ValueError(f"candidate file changed before copy: {source_file}")
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError(f"candidate contains a non-regular or special file: {source_file}")
            copied = 0
            while True:
                block = src.read(1024 * 1024)
                if not block:
                    break
                dst.write(block)
                copied += len(block)
            dst.flush()
            os.fsync(dst.fileno())
            final_opened = os.fstat(src.fileno())
        final_path = _lstat_candidate(source_file, entry.root,
                                      tuple(entry.relative_path.split("/")), entry.raw_path)
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"candidate file copy failed for {source_file}: {exc}") from exc
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")
    if copied != initial.st_size or any(
        getattr(initial, field, None) != getattr(final_opened, field, None)
        for field in stable_fields
    ) or final_path is None or (final_path.st_dev, final_path.st_ino) != (initial.st_dev, initial.st_ino):
        raise ValueError(f"candidate file changed while being copied: {source_file}")
    try:
        mode = destination_file.stat().st_mode
        if entry.executable:
            destination_file.chmod(mode | stat.S_IXUSR)
        else:
            destination_file.chmod(mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError as exc:
        raise ValueError(f"snapshot executable mode could not be preserved: {destination_file}: {exc}") from exc
    return copied


def _ensure_no_symlink_path(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError(f"path cannot be inspected: {cursor}: {exc}") from exc
        if _is_filesystem_link(cursor, info):
            raise ValueError(f"symlinked or reparse path component is forbidden: {cursor}")


def _safe_relative_parts(value: Any, label: str, *, allow_dot: bool = False) -> tuple[str, ...]:
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError(f"{label} must be a nonempty relative path")
    text = value.replace("\\", "/")
    posix = PurePosixPath(text)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"{label} must be a relative path contained under metadata")
    raw_parts = tuple(text.split("/"))
    if any(part in ("", "..") for part in raw_parts) or (not allow_dot and any(part == "." for part in raw_parts)):
        raise ValueError(f"{label} must not traverse outside metadata")
    parts = tuple(part for part in raw_parts if part != ".")
    if any(PureWindowsPath(part).drive for part in parts):
        raise ValueError(f"{label} must not contain a drive-qualified component")
    if not parts and not allow_dot:
        raise ValueError(f"{label} must name a path below its root")
    return parts
def _resolve_evidence_path(root: Path, relative: str, *, directory: bool) -> Path:
    parts = _safe_relative_parts(relative, "evidence path")
    path = root.joinpath(*parts)
    cursor = root
    try:
        for index, part in enumerate(parts):
            cursor = cursor / part
            info = cursor.lstat()
            if _is_filesystem_link(cursor, info):
                raise ValueError(f"evidence path contains a symlink or junction: {relative!r}")
            if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
                raise ValueError(f"evidence path parent is not a directory: {relative!r}")
        if directory and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"evidence path is not a directory: {relative!r}")
        if not directory and not stat.S_ISREG(info.st_mode):
            raise ValueError(f"evidence path is not a regular file: {relative!r}")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"evidence path escapes metadata: {relative!r}")
    except OSError as exc:
        raise ValueError(f"evidence path cannot be resolved: {relative!r}: {exc}") from exc
    return path


def _git_ignored_paths(source: Path, paths: list[bytes]) -> set[bytes]:
    if not paths:
        return set()
    raw = _git(source, "check-ignore", "--no-index", "-z", "--stdin",
               input_bytes=b"\x00".join(paths) + b"\x00")
    return {path for path in raw.split(b"\x00") if path}


def _is_filesystem_link(path: Path, info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400 if os.name == "nt" else 0)
    if getattr(info, "st_file_attributes", 0) & reparse_flag:
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _walk_snapshot(snapshot: Path, original: tuple[_CandidateTreeEntry, ...]) -> tuple[_CandidateTreeEntry, ...]:
    snapshot = Path(os.path.abspath(snapshot))
    _ensure_no_symlink_path(snapshot)
    try:
        snapshot_root = snapshot.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"snapshot root cannot be resolved: {exc}") from exc
    if not snapshot_root.is_dir():
        raise ValueError("snapshot root must be a directory")
    initial = {entry.raw_path: entry for entry in original}
    files: list[_CandidateTreeEntry] = []

    def visit(folder: Path, relative: tuple[str, ...]) -> None:
        try:
            with os.scandir(folder) as iterator:
                children = sorted(iterator, key=lambda item: os.fsencode(item.name))
        except OSError as exc:
            raise ValueError(f"snapshot directory cannot be read: {folder}: {exc}") from exc
        for child in children:
            name = child.name
            child_path = folder / name
            try:
                info = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError(f"snapshot path cannot be inspected: {child_path}: {exc}") from exc
            if _is_filesystem_link(child_path, info):
                raise ValueError(f"snapshot contains a filesystem symlink or junction: {child_path}")
            if name == ".git":
                raise ValueError(f"snapshot contains unexpected Git metadata: {child_path}")
            next_relative = relative + (name,)
            if stat.S_ISDIR(info.st_mode):
                visit(child_path, next_relative)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"snapshot contains a non-regular or special file: {child_path}")
            try:
                resolved = child_path.resolve(strict=True)
                if not resolved.is_relative_to(snapshot_root):
                    raise ValueError(f"snapshot path escapes snapshot root: {child_path}")
            except OSError as exc:
                raise ValueError(f"snapshot path cannot be resolved: {child_path}: {exc}") from exc
            relative_path = "/".join(next_relative)
            raw_path = os.fsencode(relative_path)
            old = initial.get(raw_path)
            executable = (
                old.executable if os.name == "nt" and old is not None
                else bool(info.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
            )
            files.append(_CandidateTreeEntry(relative_path, raw_path, child_path, executable, snapshot_root))

    visit(snapshot_root, ())
    files.sort(key=lambda item: item.raw_path)
    return tuple(files)


def _snapshot_artifact_sha256(snapshot: Path) -> str:
    """Hash every regular file in the archived snapshot, including ignored outputs."""
    entries = _walk_snapshot(Path(snapshot), ())
    digest = hashlib.sha256(b"ssec-snapshot-artifact-v1\x00")
    for entry in entries:
        path_bytes = entry.raw_path
        digest.update(len(path_bytes).to_bytes(8, "big", signed=False))
        digest.update(path_bytes)
        digest.update(b"\x01" if entry.executable else b"\x00")
        initial_stat = entry.path.lstat()
        _hash_file_into(digest, entry.path, initial_stat, entry.relative_path)
    return digest.hexdigest()


def snapshot_artifact_sha256(snapshot: Path) -> str:
    """Public integrity check for a standalone archived candidate snapshot."""
    return _snapshot_artifact_sha256(Path(snapshot))


def _snapshot_tree_sha256(
    snapshot: Path,
    original: tuple[_CandidateTreeEntry, ...],
    source: Path,
    source_tree_sha256: str,
) -> str:
    if candidate_tree_sha256(source) != source_tree_sha256:
        raise ValueError("source candidate changed after snapshot capture")
    current = _walk_snapshot(snapshot, original)
    initial_paths = {entry.raw_path for entry in original}
    new_paths = [entry.raw_path for entry in current if entry.raw_path not in initial_paths]
    ignored = _git_ignored_paths(source, new_paths)
    visible = tuple(entry for entry in current if entry.raw_path not in ignored)
    return _hash_candidate_entries(visible)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
    except OSError as exc:
        raise ValueError(f"evidence log cannot be read: {path}: {exc}") from exc
    return digest.hexdigest()


def capture_snapshot(source: Path, destination: Path) -> SnapshotReference:
    """Copy tracked plus non-ignored untracked regular files into a stable snapshot."""
    entries = _candidate_tree_entries(Path(source))
    source_root = Path(source).resolve(strict=True)
    destination_path = Path(os.path.abspath(destination))
    _ensure_no_symlink_path(destination_path.parent)
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(f"snapshot destination already exists: {destination_path}")
    try:
        if destination_path.resolve(strict=False).is_relative_to(source_root):
            raise ValueError("snapshot destination must be outside the source worktree")
    except OSError as exc:
        raise ValueError(f"snapshot destination cannot be resolved: {exc}") from exc
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_no_symlink_path(destination_path.parent)

    partial = destination_path.parent / f".{destination_path.name}.{uuid.uuid4().hex}.partial"
    source_before = _hash_candidate_entries(entries)
    copied_entries: list[_CandidateTreeEntry] = []
    total_bytes = 0
    try:
        partial.mkdir(mode=0o700, exist_ok=False)
        for entry in entries:
            components = entry.relative_path.split("/")
            source_file = entry.path
            target_file = partial.joinpath(*components)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            total_bytes += _copy_candidate_file(entry, target_file)
            copied_entries.append(_CandidateTreeEntry(
                entry.relative_path, entry.raw_path, target_file, entry.executable, partial
            ))
        source_after = candidate_tree_sha256(source_root)
        if source_after != source_before:
            raise ValueError("source candidate drifted while snapshot was copied")
        snapshot_hash = _hash_candidate_entries(tuple(copied_entries))
        if snapshot_hash != source_before:
            raise ValueError("copied snapshot tree does not match the source candidate")
        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(f"snapshot destination appeared during capture: {destination_path}")
        os.replace(partial, destination_path)
        return SnapshotReference(
            source_tree_sha256=source_before,
            snapshot_tree_sha256=snapshot_hash,
            file_count=len(copied_entries),
            total_bytes=total_bytes,
            snapshot_path=destination_path,
        )
    except Exception:
        if partial.exists() and not partial.is_symlink():
            shutil.rmtree(partial, ignore_errors=True)
        raise


def _environment() -> dict[str, str]:
    selected: dict[str, str] = {}
    for key, value in os.environ.items():
        normalized = key.upper()
        if normalized in ALLOWED_ENVIRONMENT_KEYS:
            selected[normalized] = value
    selected["PYTHONDONTWRITEBYTECODE"] = "1"
    return dict(sorted(selected.items()))


def _resolve_executable(command: str, cwd: Path, environment: Mapping[str, str]) -> tuple[str, str]:
    if type(command) is not str or not command or "\x00" in command:
        raise ValueError("argv[0] is not a valid executable name")
    windows = PureWindowsPath(command)
    if Path(command).is_absolute() or windows.is_absolute():
        candidate = Path(command)
    elif "/" in command or "\\" in command:
        candidate = cwd / command
    else:
        found = shutil.which(command, path=environment.get("PATH"))
        if found is None:
            raise ValueError(f"executable could not be resolved: {command!r}")
        candidate = Path(found)
    try:
        resolved = candidate.resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise ValueError(f"executable could not be resolved: {command!r}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"resolved executable is not a regular file: {resolved}")
    return str(resolved), _hash_file(resolved)


def _safe_cwd(snapshot: Path, cwd: str) -> Path:
    parts = _safe_relative_parts(cwd.replace("\\", "/"), "cwd", allow_dot=True)
    path = snapshot.joinpath(*parts)
    cursor = snapshot
    try:
        for part in parts:
            cursor = cursor / part
            info = cursor.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ValueError(f"check cwd is not a contained directory: {cwd!r}")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(snapshot):
            raise ValueError(f"check cwd escapes snapshot: {cwd!r}")
    except OSError as exc:
        raise ValueError(f"check cwd is unavailable: {cwd!r}: {exc}") from exc
    return path


def _unittest_count(output: bytes) -> tuple[int | None, bool]:
    matches = _UNITTEST_RAN_RE.findall(output)
    if len(matches) != 1:
        return None, False
    count = int(matches[0])
    return count, bool(_UNITTEST_OK_RE.search(output))


def _check_log_paths(
    metadata: Path,
    worker_folder: Path,
    spec: CheckSpec,
) -> tuple[Path, Path, str, str]:
    stem = spec.check_id
    stdout = worker_folder / f"{stem}.stdout"
    stderr = worker_folder / f"{stem}.stderr"
    for path in (stdout, stderr):
        _ensure_no_symlink_path(path.parent)
        with path.open("xb"):
            pass
    return (
        stdout,
        stderr,
        stdout.relative_to(metadata).as_posix(),
        stderr.relative_to(metadata).as_posix(),
    )


def _run_process(
    spec: CheckSpec,
    executable: str,
    cwd: Path,
    stdout_stream,
    stderr_stream,
    environment: Mapping[str, str],
    stop_event: threading.Event,
    deadline: float,
) -> tuple[str, str, int | None, str | None]:
    process = None
    containment = None
    process_status = "spawn_error"
    containment_status = "not_started"
    error = None
    exit_code = None
    try:
        containment = new_containment()
    except OSError as exc:
        return process_status, containment_status, None, f"containment setup failed: {exc}"

    try:
        # Evidence retains the declared argv; launch the hash-bound resolved executable.
        process = subprocess.Popen(
            [executable, *spec.argv[1:]],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout_stream,
            stderr=stderr_stream,
            shell=False,
            env=dict(environment),
            creationflags=containment.creationflags,
            start_new_session=os.name != "nt",
        )
        try:
            containment.attach(process)
        except OSError as exc:
            process_status = "containment_error"
            error = f"process containment attach failed: {exc}"
            try:
                process.kill()
                process.wait(timeout=5)
            except OSError as kill_error:
                error += f"; process termination failed: {kill_error}"
            except subprocess.TimeoutExpired:
                error += "; process termination did not finish"
        else:
            check_deadline = time.monotonic() + spec.timeout_seconds
            while True:
                if stop_event.is_set():
                    process_status = "cancelled"
                    break
                now = time.monotonic()
                if now >= deadline or now >= check_deadline:
                    process_status = "timed_out"
                    break
                try:
                    if containment.root_exited(process):
                        process_status = "exited"
                        break
                except OSError as exc:
                    process_status = "containment_error"
                    error = f"process root observation failed: {exc}"
                    break
                wait_for = min(0.025, max(0.001, deadline - now), max(0.001, check_deadline - now))
                stop_event.wait(wait_for)
    except OSError as exc:
        process_status = "spawn_error"
        error = f"check process could not be started: {exc}"

    if process is not None:
        try:
            observation_error = containment.quiesce(process)
            if observation_error:
                containment_status = "unverified"
                error = error or str(observation_error)
            else:
                containment_status = "confirmed"
            exit_code = process.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            containment_status = "unverified"
            error = error or f"process quiescence could not be confirmed: {exc}"
            if process_status == "exited":
                exit_code = process.returncode
            elif process_status not in ("timed_out", "cancelled", "spawn_error"):
                process_status = "containment_error"
        finally:
            try:
                containment.close()
            except OSError as exc:
                containment_status = "unverified"
                error = error or f"containment close failed: {exc}"
    else:
        try:
            containment.close()
        except OSError as exc:
            error = error or f"containment close failed: {exc}"
    return process_status, containment_status, exit_code, error


def _record_check(
    spec: CheckSpec,
    *,
    task_id: str,
    task_revision: str,
    task_sha256: str,
    execution_id: str,
    worker_role: str,
    worker_branch: str,
    base_commit: str,
    executable: str,
    executable_sha256: str,
    environment: Mapping[str, str],
    started_at_utc: str,
    finished_at_utc: str,
    process_status: str,
    containment_status: str,
    exit_code: int | None,
    unittest_count: int | None,
    candidate_before: str,
    candidate_after: str,
    stdout_path: str,
    stdout_sha256: str,
    stderr_path: str,
    stderr_sha256: str,
    extra_error: str | None,
) -> EvidenceRecord:
    passed = (
        process_status == "exited"
        and containment_status == "confirmed"
        and exit_code == 0
        and candidate_before == candidate_after
        and (spec.protocol != "unittest" or (unittest_count is not None and unittest_count > 0))
        and extra_error is None
    )
    return EvidenceRecord(
        task_id=task_id,
        task_revision=task_revision,
        task_sha256=task_sha256,
        execution_id=execution_id,
        check_id=spec.check_id,
        worker_role=worker_role,
        worker_branch=worker_branch,
        base_commit=base_commit,
        candidate_tree_sha256_before=candidate_before,
        candidate_tree_sha256_after=candidate_after,
        executable=executable,
        executable_sha256=executable_sha256,
        protocol=spec.protocol,
        argv=spec.argv,
        cwd=spec.cwd,
        operating_system=sys.platform,
        python_version=sys.version.split()[0],
        environment=environment,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        timeout_seconds=spec.timeout_seconds,
        process_status=process_status,
        containment_status=containment_status,
        exit_code=exit_code,
        unittest_count=unittest_count,
        stdout_path=stdout_path,
        stdout_sha256=stdout_sha256,
        stderr_path=stderr_path,
        stderr_sha256=stderr_sha256,
        passed=passed,
    )


def _check_result(
    spec: CheckSpec,
    worker_folder: Path,
    metadata: Path,
    snapshot: Path,
    source: Path,
    initial_entries: tuple[_CandidateTreeEntry, ...],
    snapshot_reference: SnapshotReference,
    state: Mapping[str, Any],
    worker: Mapping[str, Any],
    task: Mapping[str, Any],
    execution_id: str,
    task_revision: str,
    task_sha256: str,
    stop_event: threading.Event,
    deadline: float,
) -> tuple[dict[str, Any], EvidenceRecord | None, bool]:
    item: dict[str, Any] = {
        "check_id": spec.check_id,
        "argv": list(spec.argv),
        "cwd": spec.cwd,
        "timeout_seconds": spec.timeout_seconds,
        "protocol": spec.protocol,
        "result_status": "FAILED",
        "error": None,
        "stdout_path": None,
        "stdout_sha256": None,
        "stderr_path": None,
        "stderr_sha256": None,
        "record": None,
    }
    if stop_event.is_set() or time.monotonic() >= deadline:
        item["result_status"] = "NOT_RUN"
        item["error"] = "cancelled before check launch" if stop_event.is_set() else "deadline expired before check launch"
        return item, None, True

    try:
        candidate_before = _snapshot_tree_sha256(
            snapshot, initial_entries, source, snapshot_reference.source_tree_sha256
        )
        artifact_before = _snapshot_artifact_sha256(snapshot)
        cwd = _safe_cwd(snapshot, spec.cwd)
    except ValueError as exc:
        item["error"] = f"snapshot verification failed before check: {exc}"
        return item, None, True

    environment = _environment()
    try:
        executable, executable_sha256 = _resolve_executable(spec.argv[0], cwd, environment)
    except ValueError as exc:
        item["error"] = str(exc)
        return item, None, False

    try:
        stdout_file, stderr_file, stdout_relative, stderr_relative = _check_log_paths(
            metadata, worker_folder, spec
        )
    except OSError as exc:
        item["error"] = f"exclusive check logs could not be created: {exc}"
        return item, None, False
    item["stdout_path"] = stdout_relative
    item["stderr_path"] = stderr_relative
    started_at_utc = _utc_now()
    process_status = "spawn_error"
    containment_status = "not_started"
    exit_code = None
    process_error = None
    try:
        with stdout_file.open("ab") as stdout_stream, stderr_file.open("ab") as stderr_stream:
            process_status, containment_status, exit_code, process_error = _run_process(
                spec, executable, cwd, stdout_stream, stderr_stream, environment,
                stop_event, deadline
            )
    except OSError as exc:
        process_error = f"check log stream failed: {exc}"
    finished_at_utc = _utc_now()

    try:
        stdout_sha256 = _hash_file(stdout_file)
        stderr_sha256 = _hash_file(stderr_file)
        item["stdout_sha256"] = stdout_sha256
        item["stderr_sha256"] = stderr_sha256
    except ValueError as exc:
        item["error"] = str(exc)
        return item, None, True

    unittest_count = None
    unittest_success_summary = True
    if spec.protocol == "unittest":
        try:
            output = stdout_file.read_bytes() + b"\n" + stderr_file.read_bytes()
        except OSError as exc:
            item["error"] = f"unittest output cannot be read: {exc}"
            return item, None, True
        unittest_count, unittest_success_summary = _unittest_count(output)

    try:
        candidate_after = _snapshot_tree_sha256(
            snapshot, initial_entries, source, snapshot_reference.source_tree_sha256
        )
        artifact_after = _snapshot_artifact_sha256(snapshot)
    except ValueError as exc:
        item["error"] = f"snapshot verification failed after check: {exc}"
        return item, None, True
    snapshot_changed = candidate_before != candidate_after or artifact_before != artifact_after
    if snapshot_changed:
        process_error = process_error or "check changed the candidate snapshot or its archived files"

    if spec.protocol == "unittest" and not unittest_success_summary:
        process_error = process_error or "unittest success summary was absent or not successful"

    try:
        record = _record_check(
            spec,
            task_id=str(task["task_id"]),
            task_revision=task_revision,
            task_sha256=task_sha256,
            execution_id=execution_id,
            worker_role=str(worker["role"]),
            worker_branch=str(worker["branch"]),
            base_commit=str(state["base_commit"]),
            executable=executable,
            executable_sha256=executable_sha256,
            environment=environment,
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            process_status=process_status,
            containment_status=containment_status,
            exit_code=exit_code,
            unittest_count=unittest_count,
            candidate_before=candidate_before,
            candidate_after=candidate_after,
            stdout_path=stdout_relative,
            stdout_sha256=stdout_sha256,
            stderr_path=stderr_relative,
            stderr_sha256=stderr_sha256,
            extra_error=process_error,
        )
    except ValueError as exc:
        item["error"] = f"evidence record could not be validated: {exc}"
        return item, None, snapshot_changed
    item["record"] = record.to_dict()
    item["result_status"] = "PASSED" if record.passed else "FAILED"
    item["error"] = process_error
    return item, record, snapshot_changed or process_status in ("cancelled", "timed_out", "containment_error")


def _manifest_snapshot(reference: SnapshotReference | None, metadata: Path):
    if reference is None:
        return None
    return {
        "path": reference.snapshot_path.relative_to(metadata).as_posix(),
        "source_tree_sha256": reference.source_tree_sha256,
        "snapshot_tree_sha256": reference.snapshot_tree_sha256,
        "artifact_sha256": _snapshot_artifact_sha256(reference.snapshot_path),
        "file_count": reference.file_count,
        "total_bytes": reference.total_bytes,
    }


def _write_atomic_manifest(path: Path, data: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
        raise ValueError(f"terminal check manifest could not be published atomically: {exc}") from exc


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manifest field {key!r}")
        result[key] = value
    return result


def _manifest_error(message: str) -> ValueError:
    return ValueError(f"invalid check manifest: {message}")


def _validate_log(root: Path, path_value: Any, hash_value: Any, label: str) -> None:
    if type(path_value) is not str or type(hash_value) is not str or not _SHA256_RE.fullmatch(hash_value):
        raise _manifest_error(f"{label} path/hash is missing or invalid")
    path = _resolve_evidence_path(root, path_value, directory=False)
    if _hash_file(path) != hash_value:
        raise _manifest_error(f"{label} hash mismatch or tampering detected")


def _validate_manifest_data(data: Any, metadata_root: Path) -> dict[str, Any]:
    if type(data) is not dict or set(data) != _MANIFEST_FIELDS:
        raise _manifest_error("fields are missing or extra")
    if type(data["schema_version"]) is not int or data["schema_version"] != _MANIFEST_SCHEMA_VERSION:
        raise _manifest_error(f"unsupported schema_version; expected {_MANIFEST_SCHEMA_VERSION}")
    if type(data["terminal"]) is not bool or data["terminal"] is not True:
        raise _manifest_error("manifest is not terminal")
    if data["status"] not in ("PASSED", "FAILED"):
        raise _manifest_error("status must be PASSED or FAILED")
    for name in ("task_id", "task_revision", "execution_id", "worker_role", "worker_branch"):
        if type(data[name]) is not str or not data[name] or "\x00" in data[name]:
            raise _manifest_error(f"{name} must be a nonempty string")
    if type(data["task_sha256"]) is not str or not _SHA256_RE.fullmatch(data["task_sha256"]):
        raise _manifest_error("task_sha256 is invalid")
    if type(data["base_commit"]) is not str or not _GIT_OID_RE.fullmatch(data["base_commit"]):
        raise _manifest_error("base_commit is invalid")
    if type(data["candidate_tree_sha256"]) is not str or not _SHA256_RE.fullmatch(data["candidate_tree_sha256"]):
        raise _manifest_error("candidate_tree_sha256 is invalid")
    if type(data["started_at_utc"]) is not str or type(data["finished_at_utc"]) is not str:
        raise _manifest_error("timestamps must be strings")
    if type(data["errors"]) is not list or any(type(error) is not str for error in data["errors"]):
        raise _manifest_error("errors must be a string array")
    snapshot = data["snapshot"]
    if snapshot is not None:
        required = {"path", "source_tree_sha256", "snapshot_tree_sha256", "artifact_sha256",
                    "file_count", "total_bytes"}
        if type(snapshot) is not dict or set(snapshot) != required:
            raise _manifest_error("snapshot fields are invalid")
        _resolve_evidence_path(metadata_root, snapshot["path"], directory=True)
        for name in ("source_tree_sha256", "snapshot_tree_sha256"):
            if type(snapshot[name]) is not str or not _SHA256_RE.fullmatch(snapshot[name]):
                raise _manifest_error(f"snapshot {name} is invalid")
        for name in ("file_count", "total_bytes"):
            if type(snapshot[name]) is not int or snapshot[name] < 0:
                raise _manifest_error(f"snapshot {name} is invalid")
        if type(snapshot["artifact_sha256"]) is not str or not _SHA256_RE.fullmatch(snapshot["artifact_sha256"]):
            raise _manifest_error("snapshot artifact_sha256 is invalid")
        if snapshot["source_tree_sha256"] != data["candidate_tree_sha256"]:
            raise _manifest_error("snapshot source digest does not match candidate digest")
        snapshot_path = _resolve_evidence_path(metadata_root, snapshot["path"], directory=True)
        if _snapshot_artifact_sha256(snapshot_path) != snapshot["artifact_sha256"]:
            raise _manifest_error("snapshot artifact hash mismatch or tampering detected")
    checks = data["checks"]
    if type(checks) is not list:
        raise _manifest_error("checks must be an array")
    seen: set[str] = set()
    records: list[EvidenceRecord] = []
    for item in checks:
        if type(item) is not dict or set(item) != _CHECK_RESULT_FIELDS:
            raise _manifest_error("check result fields are missing or extra")
        check_id = item["check_id"]
        if type(check_id) is not str or not check_id or check_id in seen:
            raise _manifest_error("check_id is empty or duplicated")
        seen.add(check_id)
        if type(item["argv"]) is not list or not item["argv"] or any(
            type(arg) is not str or not arg or "\x00" in arg for arg in item["argv"]
        ):
            raise _manifest_error(f"{check_id} argv is invalid")
        if type(item["cwd"]) is not str:
            raise _manifest_error(f"{check_id} cwd is invalid")
        _safe_relative_parts(item["cwd"].replace("\\", "/"), "cwd", allow_dot=True)
        timeout = item["timeout_seconds"]
        if type(timeout) not in (int, float) or not math.isfinite(float(timeout)) or timeout <= 0:
            raise _manifest_error(f"{check_id} timeout is invalid")
        if type(item["protocol"]) is not str or item["protocol"] not in _PROTOCOLS:
            raise _manifest_error(f"{check_id} protocol is invalid")
        if item["result_status"] not in ("PASSED", "FAILED", "NOT_RUN"):
            raise _manifest_error(f"{check_id} result_status is invalid")
        if item["error"] is not None and type(item["error"]) is not str:
            raise _manifest_error(f"{check_id} error must be string or null")
        record_data = item["record"]
        if record_data is None:
            if item["result_status"] == "PASSED":
                raise _manifest_error(f"{check_id} has no evidence record for PASS")
        else:
            try:
                record = decode_evidence_record(json.dumps(record_data, ensure_ascii=False, allow_nan=False))
            except (TypeError, ValueError) as exc:
                raise _manifest_error(f"{check_id} record is invalid: {exc}") from exc
            if (
                record.check_id != check_id
                or record.argv != tuple(item["argv"])
                or record.cwd != item["cwd"]
                or record.protocol != item["protocol"]
                or record.timeout_seconds != float(timeout)
                or record.task_id != data["task_id"]
                or record.task_revision != data["task_revision"]
                or record.task_sha256 != data["task_sha256"]
                or record.execution_id != data["execution_id"]
                or record.worker_role != data["worker_role"]
                or record.worker_branch != data["worker_branch"]
                or record.base_commit != data["base_commit"]
                or record.candidate_tree_sha256_before != data["candidate_tree_sha256"]
                or record.stdout_path != item["stdout_path"]
                or record.stdout_sha256 != item["stdout_sha256"]
                or record.stderr_path != item["stderr_path"]
                or record.stderr_sha256 != item["stderr_sha256"]
            ):
                raise _manifest_error(f"{check_id} record does not match its manifest")
            if item["result_status"] != ("PASSED" if record.passed else "FAILED"):
                raise _manifest_error(f"{check_id} result_status disagrees with record")
            records.append(record)
        for label in ("stdout", "stderr"):
            path_value, hash_value = item[f"{label}_path"], item[f"{label}_sha256"]
            if path_value is None and hash_value is None:
                continue
            _validate_log(metadata_root, path_value, hash_value, f"{check_id} {label}")
    all_passed = bool(checks) and all(item["result_status"] == "PASSED" for item in checks)
    if data["status"] == "PASSED":
        if not all_passed or len(records) != len(checks) or data["errors"]:
            raise _manifest_error("PASSED requires every check to have passing evidence")
        if snapshot is None or snapshot["snapshot_tree_sha256"] != data["candidate_tree_sha256"]:
            raise _manifest_error("PASSED requires a stable captured snapshot")
        if any(record.containment_status != "confirmed" for record in records):
            raise _manifest_error("PASSED requires confirmed containment for all checks")
    return data


def read_check_manifest(manifest_path: Path, metadata_root: Path) -> dict[str, Any]:
    """Read a terminal manifest and verify its schema, containment, and current log hashes."""
    root_argument = Path(metadata_root)
    if root_argument.is_symlink():
        raise ValueError("metadata root must not be a symlink")
    try:
        root = root_argument.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("metadata root must be a directory")
        path_argument = Path(manifest_path)
        if path_argument.is_symlink():
            raise ValueError("manifest path must not be a symlink")
        path = path_argument.resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("manifest path escapes metadata root")
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"manifest path cannot be read: {exc}") from exc
    try:
        data = json.loads(
            raw,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON number {value}")),
        )
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise ValueError(f"invalid check manifest JSON: {exc}") from exc
    return _validate_manifest_data(data, root)


def _not_run_check(spec: CheckSpec, reason: str) -> dict[str, Any]:
    return {
        "check_id": spec.check_id,
        "argv": list(spec.argv),
        "cwd": spec.cwd,
        "timeout_seconds": spec.timeout_seconds,
        "protocol": spec.protocol,
        "result_status": "NOT_RUN",
        "error": reason,
        "stdout_path": None,
        "stdout_sha256": None,
        "stderr_path": None,
        "stderr_sha256": None,
        "record": None,
    }


def _publish_run(
    *,
    metadata: Path,
    worker_folder: Path,
    manifest_path: Path,
    status: str,
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    worker: Mapping[str, Any],
    task_revision: str,
    task_sha256: str,
    execution_id: str,
    candidate_tree: str,
    snapshot: SnapshotReference | None,
    checks: list[dict[str, Any]],
    started_at_utc: str,
    errors: list[str],
) -> dict[str, Any]:
    published_status = status
    published_errors = list(errors)
    try:
        snapshot_data = _manifest_snapshot(snapshot, metadata)
    except (OSError, ValueError) as exc:
        snapshot_data = None
        published_status = "FAILED"
        published_errors.append(f"snapshot artifact could not be verified: {exc}")
    data = {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "terminal": True,
        "status": published_status,
        "task_id": str(task["task_id"]),
        "task_revision": task_revision,
        "task_sha256": task_sha256,
        "execution_id": execution_id,
        "worker_role": str(worker["role"]),
        "worker_branch": str(worker["branch"]),
        "base_commit": str(state["base_commit"]),
        "candidate_tree_sha256": candidate_tree,
        "snapshot": snapshot_data,
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "checks": checks,
        "errors": published_errors,
    }
    try:
        _validate_manifest_data(data, metadata)
        _write_atomic_manifest(manifest_path, data)
        return read_check_manifest(manifest_path, metadata)
    except (OSError, TypeError, ValueError) as exc:
        if published_status == "PASSED":
            data["status"] = "FAILED"
            data["errors"] = [*published_errors, f"manifest verification/publication failed: {exc}"]
            data["finished_at_utc"] = _utc_now()
            try:
                _validate_manifest_data(data, metadata)
                _write_atomic_manifest(manifest_path, data)
                return read_check_manifest(manifest_path, metadata)
            except (OSError, TypeError, ValueError):
                pass
        raise ValueError(f"check manifest could not be published as terminal evidence: {exc}") from exc


def run_checks(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    worker: Mapping[str, Any],
    metadata: Path,
    *,
    stop_event: threading.Event,
    deadline: float,
) -> CheckRunResult:
    """Run only validated task check specs in one worker's private snapshot."""
    specs = validate_check_specs(task)
    if not specs:
        return CheckRunResult("NOT_RUN", None, None, (), (), None)
    if not isinstance(state, Mapping) or not isinstance(worker, Mapping):
        raise ValueError("state and worker must be mappings")
    if type(stop_event) is not threading.Event:
        raise ValueError("stop_event must be a threading.Event")
    if type(deadline) not in (int, float) or not math.isfinite(float(deadline)):
        raise ValueError("deadline must be a finite monotonic timestamp")
    task_id = task.get("task_id")
    if type(task_id) is not str or not task_id:
        raise ValueError("task_id must be a nonempty string")
    if state.get("task_id") != task_id:
        raise ValueError("task and initialized state task_id differ")
    task_sha256 = canonical_task_sha256(task)
    initialized_digest = state.get("task_sha256")
    if type(initialized_digest) is not str or initialized_digest != task_sha256:
        raise ValueError("task digest differs from initialized task")
    base_commit = state.get("base_commit")
    if type(base_commit) is not str or not _GIT_OID_RE.fullmatch(base_commit):
        raise ValueError("state base_commit must be a Git object ID")
    role = worker.get("role")
    branch = worker.get("branch")
    source_value = worker.get("path")
    if type(role) is not str or not _ROLE_RE.fullmatch(role):
        raise ValueError("worker role is not a safe path component")
    if type(branch) is not str or not branch or "\x00" in branch:
        raise ValueError("worker branch must be a nonempty string")
    if not isinstance(source_value, (str, Path)):
        raise ValueError("worker path must name its candidate worktree")
    task_revision_value = state.get("task_revision", task.get("task_revision", task.get("revision", "revision-1")))
    task_revision = str(task_revision_value)
    if not task_revision or "\x00" in task_revision:
        raise ValueError("task revision must be a nonempty string")

    source_tree = _candidate_tree_entries(Path(source_value))
    source_root = Path(source_value).resolve(strict=True)
    try:
        actual_branch = _git(source_root, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8").strip()
        merge_base = _git(source_root, "merge-base", "HEAD", base_commit).decode("ascii").strip()
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"worker Git identity could not be verified: {exc}") from exc
    if actual_branch != branch:
        raise ValueError("worker branch does not match the source worktree's checked-out branch")
    if merge_base != base_commit:
        raise ValueError("worker branch is not based on the initialized base commit")
    state_workers = state.get("workers")
    if state_workers is not None:
        if type(state_workers) not in (list, tuple):
            raise ValueError("initialized workers must be a sequence")
        matching = [item for item in state_workers if isinstance(item, Mapping) and item.get("role") == role]
        if len(matching) != 1 or matching[0].get("branch") != branch:
            raise ValueError("worker role/branch does not match initialized state")
        initialized_path = matching[0].get("path")
        if initialized_path is not None and Path(initialized_path).resolve(strict=True) != source_root:
            raise ValueError("worker path does not match initialized state")

    metadata_argument = Path(metadata)
    _ensure_no_symlink_path(metadata_argument)
    metadata_argument.mkdir(parents=True, exist_ok=True)
    metadata_root = metadata_argument.resolve(strict=True)
    if not metadata_root.is_dir():
        raise ValueError("metadata must be a directory")
    execution_id = uuid.uuid4().hex
    check_runs = metadata_root / "check-runs"
    _ensure_no_symlink_path(check_runs)
    check_runs.mkdir(exist_ok=True)
    execution_root = check_runs / execution_id
    execution_root.mkdir(exist_ok=False)
    worker_folder = execution_root / role
    worker_folder.mkdir(exist_ok=False)
    _ensure_no_symlink_path(worker_folder)
    manifest_path = worker_folder / "manifest.json"
    started_at_utc = _utc_now()
    snapshot_reference: SnapshotReference | None = None
    original_entries = source_tree
    checks: list[dict[str, Any]] = []
    records: list[EvidenceRecord] = []
    errors: list[str] = []
    try:
        snapshot_destination = worker_folder / "snapshot"
        snapshot_reference = capture_snapshot(Path(source_value), snapshot_destination)
    except (OSError, ValueError) as exc:
        errors.append(f"snapshot capture failed: {exc}")
        checks = [_not_run_check(spec, str(exc)) for spec in specs]
        data = _publish_run(
            metadata=metadata_root, worker_folder=worker_folder, manifest_path=manifest_path,
            status="FAILED", task=task, state=state, worker=worker,
            task_revision=task_revision, task_sha256=task_sha256, execution_id=execution_id,
            candidate_tree="0" * 64, snapshot=None, checks=checks,
            started_at_utc=started_at_utc, errors=errors,
        )
        return CheckRunResult("FAILED", execution_id, manifest_path, (), tuple(errors), None)

    interrupted = False
    for index, spec in enumerate(specs):
        if interrupted:
            checks.append(_not_run_check(spec, "not run after cancellation, timeout, or candidate drift"))
            continue
        item, record, should_stop = _check_result(
            spec,
            worker_folder,
            metadata_root,
            snapshot_reference.snapshot_path,
            source_root,
            original_entries,
            snapshot_reference,
            state,
            worker,
            task,
            execution_id,
            task_revision,
            task_sha256,
            stop_event,
            float(deadline),
        )
        checks.append(item)
        if record is not None:
            records.append(record)
        if item["error"]:
            errors.append(f"{spec.check_id}: {item['error']}")
        interrupted = should_stop

    all_passed = bool(checks) and len(checks) == len(specs) and all(
        item["result_status"] == "PASSED" for item in checks
    )
    status = "PASSED" if all_passed and not errors else "FAILED"
    data = _publish_run(
        metadata=metadata_root, worker_folder=worker_folder, manifest_path=manifest_path,
        status=status, task=task, state=state, worker=worker,
        task_revision=task_revision, task_sha256=task_sha256, execution_id=execution_id,
        candidate_tree=snapshot_reference.source_tree_sha256,
        snapshot=snapshot_reference, checks=checks,
        started_at_utc=started_at_utc, errors=errors,
    )
    final_status = data["status"]
    return CheckRunResult(
        final_status,
        execution_id,
        manifest_path,
        tuple(records),
        tuple(errors),
        snapshot_reference,
    )
