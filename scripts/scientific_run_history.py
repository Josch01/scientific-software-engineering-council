from __future__ import annotations

import json
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


MAX_HISTORY_ENTRIES = 100
MAX_RUN_LOG_BYTES = 65_536
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UUID_HEX = re.compile(r"^[0-9a-f]{32}$")
_REPARSE_POINT = 0x400


@dataclass(frozen=True)
class SirAnalysisRun:
    run_id: str
    status: str
    started_at_utc: str
    result_workspace_manifest: str | None = None
    result_workspace_manifest_sha256: str | None = None
    log_file: str = ""
    issue: str = ""

    @property
    def can_open(self) -> bool:
        return (
            self.status == "SUCCEEDED"
            and self.result_workspace_manifest is not None
            and self.result_workspace_manifest_sha256 is not None
            and not self.issue
        )


def _is_run_id(value: str) -> bool:
    if _UUID_HEX.fullmatch(value):
        return True
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        return False
    return str(parsed) == value


def _is_link_or_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _history_directory(root: Path) -> Path | None:
    current = root
    for part in ("generated", "sir-analysis-runs"):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return None
        if _is_link_or_reparse(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("analysis history path must be a regular directory")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("analysis history directory escapes project root") from exc
    return resolved


def _invalid_record(run_id: str, file_name: str, issue: str) -> SirAnalysisRun:
    return SirAnalysisRun(
        run_id=run_id,
        status="INVALID",
        started_at_utc="",
        log_file=file_name,
        issue=issue[:240],
    )


def _record_from_file(root: Path, directory: Path, file_name: str, expected_info) -> SirAnalysisRun:
    run_id = file_name[len("run-") : -len(".json")]
    path = directory / file_name
    if not _is_run_id(run_id):
        return _invalid_record(run_id, file_name, "run ID is not a supported UUID")
    try:
        before_info = path.lstat()
    except OSError as exc:
        return _invalid_record(run_id, file_name, f"cannot inspect log: {exc}")
    if _is_link_or_reparse(before_info) or not stat.S_ISREG(before_info.st_mode):
        return _invalid_record(run_id, file_name, "log is not a regular file")
    if before_info.st_size > MAX_RUN_LOG_BYTES:
        return _invalid_record(run_id, file_name, "log exceeds 65 536 bytes")
    if before_info.st_size != expected_info.st_size:
        return _invalid_record(run_id, file_name, "log changed during history scan")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened_info = os.fstat(stream.fileno())
            after_info = path.lstat()
            if (
                _is_link_or_reparse(after_info)
                or not stat.S_ISREG(opened_info.st_mode)
                or (opened_info.st_dev, opened_info.st_ino)
                != (before_info.st_dev, before_info.st_ino)
                or (after_info.st_dev, after_info.st_ino)
                != (opened_info.st_dev, opened_info.st_ino)
            ):
                return _invalid_record(run_id, file_name, "log changed while it was opened")
            raw = stream.read(MAX_RUN_LOG_BYTES + 1)
    except OSError as exc:
        return _invalid_record(run_id, file_name, f"cannot read log: {exc}")

    if len(raw) > MAX_RUN_LOG_BYTES:
        return _invalid_record(run_id, file_name, "log exceeds 65 536 bytes")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return _invalid_record(run_id, file_name, "log is not valid UTF-8 JSON")
    if not isinstance(record, dict):
        return _invalid_record(run_id, file_name, "log root must be a JSON object")
    if type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        return _invalid_record(run_id, file_name, "unsupported log schema")
    if record.get("run_id") != run_id:
        return _invalid_record(run_id, file_name, "log run ID does not match its filename")
    started_at = record.get("started_at_utc")
    if not isinstance(started_at, str) or not started_at or len(started_at) > 64:
        return _invalid_record(run_id, file_name, "log timestamp is missing or invalid")
    status = record.get("status")
    if not isinstance(status, str) or status not in {"SUCCEEDED", "FAILED"}:
        return _invalid_record(run_id, file_name, "log status is invalid")

    result_path = record.get("result_workspace_manifest")
    result_digest = record.get("result_workspace_manifest_sha256")
    if status == "SUCCEEDED":
        if (
            not isinstance(result_path, str)
            or not result_path
            or len(result_path) > 1024
            or "\\" in result_path
        ):
            return _invalid_record(run_id, file_name, "result manifest path is invalid")
        relative = PurePosixPath(result_path)
        windows_relative = PureWindowsPath(result_path)
        if (
            relative.is_absolute()
            or windows_relative.is_absolute()
            or bool(windows_relative.drive)
            or relative.parts != ("generated", "sir-analysis", run_id, "workspace.json")
        ):
            return _invalid_record(
                run_id, file_name, "result manifest path does not match this run's output"
            )
        if not isinstance(result_digest, str) or not _SHA256.fullmatch(result_digest):
            return _invalid_record(run_id, file_name, "result manifest SHA-256 is invalid")
    else:
        result_path = None
        result_digest = None

    error = record.get("error", "")
    issue = str(error)[:240] if status == "FAILED" and error else ""
    return SirAnalysisRun(
        run_id=run_id,
        status=status,
        started_at_utc=started_at,
        result_workspace_manifest=result_path,
        result_workspace_manifest_sha256=result_digest,
        log_file=file_name,
        issue=issue,
    )


def list_sir_analysis_runs(project_root: str | os.PathLike[str]) -> list[SirAnalysisRun]:
    root = Path(project_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project root must be a directory")
    directory = _history_directory(root)
    if directory is None:
        return []

    candidates: list[tuple[str, os.stat_result]] = []
    with os.scandir(directory) as children:
        for child in children:
            if child.name.startswith("run-") and child.name.endswith(".json"):
                try:
                    info = child.stat(follow_symlinks=False)
                except OSError:
                    info = None
                if info is not None:
                    candidates.append((child.name, info))
    candidates.sort(key=lambda item: (item[1].st_mtime_ns, item[0]), reverse=True)
    records = [
        _record_from_file(root, directory, file_name, info)
        for file_name, info in candidates[:MAX_HISTORY_ENTRIES]
    ]
    records.sort(key=lambda record: (record.started_at_utc, record.run_id), reverse=True)
    return records


def read_sir_analysis_run(
    project_root: str | os.PathLike[str], run_id: str
) -> SirAnalysisRun:
    if not _is_run_id(run_id):
        raise ValueError("analysis run ID is invalid")
    record = next(
        (entry for entry in list_sir_analysis_runs(project_root) if entry.run_id == run_id),
        None,
    )
    if record is None:
        raise ValueError("analysis run is not present in the recent history")
    if not record.can_open:
        raise ValueError(record.issue or "analysis run has no verified result")
    return record
