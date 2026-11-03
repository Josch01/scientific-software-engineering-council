"""Compose and check an evidence-bound disposable Git tree; no acceptance authority.

``execution_id`` selects a persisted development launch (``run_id``), never a
check-run ID. Integrated checks use their own ephemeral ``integration_candidate``
identity and cannot approve or release the composed candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid
from datetime import datetime, timezone

from .check_runner import (_ensure_no_symlink_path, _git, _is_filesystem_link,
                           _resolve_evidence_path, _write_atomic_manifest,
                           _duplicate_rejecting_object, read_check_manifest, run_checks)
from .execution_evidence import (_candidate_tree_entries, candidate_tree_sha256,
                                 validate_check_specs)
from .prepare_agents import provider_for
from .review_evidence import validate_review_manifest
from .work_items import _covers, _path, validate_work_items
from .worktree_coordinator import check_requirements, load


_INTEGRATION_ID_RE = re.compile(r"^v2-[0-9]{20}-[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INTEGRATION_STATUSES = frozenset({"BUILT_AWAITING_CHECKS", "CHECKED_AWAITING_INTEGRATED_REVIEW",
                                   "FAILED", "BLOCKED"})
_INTEGRATION_FIELDS = frozenset({
    "schema_version", "terminal", "status", "integration_id", "execution_id",
    "task_id", "task_revision", "task_sha256", "base_commit",
    "candidate_worktree_path", "candidate_branch", "integration_role",
    "candidate_tree_sha256", "started_at_utc", "input_manifests",
    "worker_tree_hashes", "operations", "check_manifest_path",
    "check_manifest_sha256", "check_status", "check_specs", "errors",
})


@dataclass(frozen=True)
class IntegrationResult:
    integration_id: str
    status: str
    candidate_worktree_path: Path | None
    integration_manifest_path: Path | None
    check_manifest_path: Path | None
    blockers: tuple[str, ...]


def _json_file(path: Path) -> dict:
    def reject_constant(value):
        raise ValueError("invalid JSON constant: " + value)
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_duplicate_rejecting_object, parse_constant=reject_constant)


def _read_regular(path: Path) -> bytes:
    """Read stable bytes without following links, including Windows reparse paths."""
    _ensure_no_symlink_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("non-regular or special file: " + str(path))
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("file changed while opening: " + str(path))
        data = stream.read()
        after_open = os.fstat(stream.fileno())
    after = path.lstat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")
    identity = lambda info: tuple(getattr(info, field) for field in fields)
    if (identity(before) != identity(after_open) or identity(before) != identity(after) or
            len(data) != before.st_size or _is_filesystem_link(path, after)):
        raise ValueError("file changed while reading: " + str(path))
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(_read_regular(path)).hexdigest()


def _read_git(root, *args, **kwargs):
    """Inspect source/worker Git state without refreshing their index files."""
    return _git(root, "--no-optional-locks", "-c", "diff.autoRefreshIndex=false", *args, **kwargs)


def _source_identity(state):
    root = Path(state["project_root"])
    _ensure_no_symlink_path(root)
    if _read_git(root, "rev-parse", "HEAD").decode().strip() != state["base_commit"]:
        raise ValueError("source base commit changed")
    if _read_git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("source checkout changed")
    return root


def _worker_identity(worker, state):
    root = Path(worker["path"])
    _ensure_no_symlink_path(root)
    if _read_git(root, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip() != worker["branch"]:
        raise ValueError("worker branch mismatch: " + worker["role"])
    if _read_git(root, "merge-base", "HEAD", state["base_commit"]).decode().strip() != state["base_commit"]:
        raise ValueError("worker base mismatch: " + worker["role"])
    # The tree hasher rejects POSIX symlinks, but on Windows a junction can be
    # reported as a directory. Inspect every Git-visible path before hashing.
    for raw in _read_git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\x00"):
        if raw:
            relative = raw.decode("utf-8")
            _path(relative, "worker path")
            _ensure_no_symlink_path(root.joinpath(*relative.rstrip("/").split("/")))
    return candidate_tree_sha256(root)


def _evidence(state, metadata, execution_id, contracts, specs):
    """Select exact persisted reviewer paths and their bound check manifests."""
    if not state["review_roles"]:
        raise ValueError("integration requires configured reviewers")
    required, _, unsupported = check_requirements(state["task_packet"], state["required_evidence"])
    if not specs or unsupported or not required <= {spec.check_id for spec in specs}:
        raise ValueError("missing or unsupported declared process checks")
    workers, inputs = {}, {}
    for worker in sorted(state["workers"], key=lambda item: item["role"]):
        role = worker["role"]
        tree = _worker_identity(worker, state)
        workers[role] = tree
        expected = {field: state[field] for field in ("task_id", "task_revision", "task_sha256", "base_commit")}
        expected.update(worker_role=role, candidate_tree_sha256=tree)
        selected_check = None
        for reviewer in sorted(contracts[role].required_reviewers):
            relative = f"dev-logs/{execution_id}/reviews/{role}/{reviewer}/manifest.json"
            path = _resolve_evidence_path(metadata, relative, directory=False)
            before = _sha256(path)
            review = validate_review_manifest(_json_file(path), metadata)
            if (review["status"] != "PASSED" or review["verdict"] != "PASS" or
                    any(review[field] != value for field, value in expected.items()) or
                    review["reviewer_role"] != reviewer or
                    review["reviewer_provider"] != provider_for(reviewer, state["mode"])):
                raise ValueError("review evidence identity/status mismatch: " + role + "/" + reviewer)
            if _sha256(path) != before:
                raise ValueError("review manifest changed during validation")
            inputs[relative] = dict(path=relative, sha256=before, kind="review", role=role,
                                    reviewer_role=reviewer)
            check_relative = review["check_manifest_path"]
            check_path = _resolve_evidence_path(metadata, check_relative, directory=False)
            checked = read_check_manifest(check_path, metadata)
            check_hash = _sha256(check_path)
            binding = check_relative, check_hash
            if selected_check is not None and binding != selected_check:
                raise ValueError("reviewers must reference the same check manifest: " + role)
            selected_check = binding
            if (check_hash != review["check_manifest_sha256"] or checked["status"] != "PASSED" or
                    checked["worker_branch"] != worker["branch"] or
                    any(checked[field] != value for field, value in expected.items())):
                raise ValueError("check evidence identity/status mismatch: " + role)
            actual = {item["check_id"]: item for item in checked["checks"]}
            if set(actual) != {spec.check_id for spec in specs}:
                raise ValueError("check evidence does not contain the complete declared check set: " + role)
            for spec in specs:
                check = actual[spec.check_id]
                if (check["result_status"] != "PASSED" or check["argv"] != list(spec.argv) or
                        check["cwd"] != spec.cwd or check["protocol"] != spec.protocol or
                        check["timeout_seconds"] != spec.timeout_seconds):
                    raise ValueError("check command/spec mismatch: " + role + "/" + spec.check_id)
            inputs[check_relative] = dict(path=check_relative, sha256=check_hash, kind="check", role=role)
    return workers, sorted(inputs.values(), key=lambda item: item["path"])


def _base_entries(root, base):
    entries = {}
    for raw in _read_git(root, "ls-tree", "-r", "-z", base).split(b"\x00"):
        if not raw:
            continue
        header, name = raw.split(b"\t", 1)
        mode, kind, oid = header.split(b" ")
        path = name.decode("utf-8")
        _path(path, "base path")
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("base contains a link, submodule, or special entry: " + path)
        entries[path] = mode, oid
    return entries


def _reject_collisions(paths):
    """Reject aliases and file/ancestor conflicts without relying on host casing."""
    files, components = set(), {}
    for path in sorted(paths):
        folded = path.casefold()
        if folded in files:
            raise ValueError("exact or casefold path collision: " + path)
        files.add(folded)
        parts = path.split("/")
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            key = prefix.casefold()
            if key in components and components[key] != prefix:
                raise ValueError("casefold path component collision: " + path)
            components[key] = prefix
    for path in files:
        parts = path.split("/")
        if any("/".join(parts[:length]) in files for length in range(1, len(parts))):
            raise ValueError("file/ancestor path collision: " + path)


def _operations(state, contracts, base):
    operations, contents = [], {}
    for worker in sorted(state["workers"], key=lambda item: item["role"]):
        role = worker["role"]
        root = Path(worker["path"])
        entries = {entry.relative_path: entry for entry in _candidate_tree_entries(root)}
        changed = _read_git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                            "--numstat", "-z", state["base_commit"], "--")
        additions = _read_git(root, "ls-files", "--others", "--exclude-standard", "-z")
        # Let Git determine visibility and normalization. A clean CRLF checkout
        # can differ from its LF blobs without constituting a worker change.
        # Numstat compares content without refreshing the index; name-only can
        # report stale-stat differences when diff.autoRefreshIndex is disabled.
        paths = {raw.split(b"\t", 2)[2].decode("utf-8") for raw in changed.split(b"\x00") if raw}
        paths.update(raw.decode("utf-8") for raw in additions.split(b"\x00") if raw)
        for path in sorted(paths):
            _path(path, "worker output path")
            entry = entries.get(path)
            content = _read_regular(entry.path) if entry else None
            mode = b"100755" if entry and entry.executable else b"100644"
            if entry:
                oid = _read_git(root, "hash-object", "--no-filters", "--stdin", input_bytes=content).strip()
                if base.get(path) == (mode, oid):
                    continue
            elif path not in base:
                continue
            item = contracts[role]
            if not any(_covers(scope, path) for scope in item.file_ownership):
                raise ValueError("worker change violates file ownership: " + role + "/" + path)
            if not any(_covers(scope, path) for scope in item.outputs):
                raise ValueError("worker change violates declared output scope: " + role + "/" + path)
            if content is not None:
                try:
                    content.decode("utf-8")
                except UnicodeError as exc:
                    raise ValueError("binary/non-UTF-8 output: " + path) from exc
                if b"\x00" in content:
                    raise ValueError("binary output: " + path)
                contents[(role, path)] = content
            operations.append(dict(role=role, path=path, operation="write" if entry else "delete",
                                   sha256=hashlib.sha256(content).hexdigest() if entry else None,
                                   executable=entry.executable if entry else None))
    _reject_collisions([item["path"] for item in operations])
    # Include untouched base paths: a newly added case alias must not shadow one.
    final_paths = set(base)
    for item in operations:
        final_paths.discard(item["path"])
        if item["operation"] == "write":
            final_paths.add(item["path"])
    _reject_collisions(final_paths)
    return operations, contents


def _overlay(candidate, operations, contents):
    for item in operations:
        relative = item["path"]
        path = candidate.joinpath(*relative.split("/"))
        _ensure_no_symlink_path(path)
        if item["operation"] == "delete":
            path.unlink()
            _git(candidate, "update-index", "--force-remove", "--", relative)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_no_symlink_path(path.parent)
        content = contents[(item["role"], relative)]
        with path.open("wb") as stream:
            stream.write(content)
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR if item["executable"] else mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        # Stage exact bytes, avoiding source Git filters and newline conversion.
        oid = _git(candidate, "hash-object", "-w", "--no-filters", "--stdin", input_bytes=content).decode().strip()
        _git(candidate, "update-index", "--add", "--cacheinfo",
             "100755" if item["executable"] else "100644", oid, relative)


def _materialize_base(candidate, base, base_commit):
    """Populate exact base blobs without checkout hooks, filters, or EOL rules."""
    _git(candidate, "read-tree", base_commit)
    for relative, (mode, oid) in sorted(base.items()):
        path = candidate.joinpath(*relative.split("/"))
        _ensure_no_symlink_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _git(candidate, "cat-file", "blob", oid.decode("ascii"))
        with path.open("xb") as stream:
            stream.write(content)
        if mode == b"100755":
            path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _new_integration_id():
    # The fixed-width time prefix gives the gate a stable latest-attempt order;
    # the random suffix keeps retries independent even within one clock tick.
    return f"v2-{time.time_ns():020d}-{uuid.uuid4().hex}"


def _check_spec_data(specs):
    return [dict(check_id=spec.check_id, argv=list(spec.argv), cwd=spec.cwd,
                 timeout_seconds=spec.timeout_seconds, protocol=spec.protocol)
            for spec in specs]


def _integration_manifest_data(state, execution_id, integration_id, candidate, branch,
                               candidate_hash, inputs, workers, operations, specs,
                               *, status="BUILT_AWAITING_CHECKS", check_manifest_path=None,
                               check_manifest_sha256=None, check_status=None, errors=(),
                               started_at_utc=None):
    return dict(
        schema_version=2,
        terminal=True,
        status=status,
        integration_id=integration_id,
        execution_id=execution_id,
        **{key: state[key] for key in ("task_id", "task_revision", "task_sha256", "base_commit")},
        candidate_worktree_path=str(candidate),
        candidate_branch=branch,
        integration_role="integration_candidate",
        candidate_tree_sha256=candidate_hash,
        started_at_utc=started_at_utc or _utc_now(),
        input_manifests=inputs,
        worker_tree_hashes=workers,
        operations=operations,
        check_manifest_path=check_manifest_path,
        check_manifest_sha256=check_manifest_sha256,
        check_status=check_status,
        check_specs=_check_spec_data(specs),
        errors=list(errors),
    )


def validate_integration_manifest(manifest_path, metadata, state, specs):
    """Validate the latest integration record and its exact persisted check evidence."""
    metadata = Path(metadata)
    _ensure_no_symlink_path(metadata)
    metadata = metadata.resolve(strict=True)
    path = Path(manifest_path)
    _ensure_no_symlink_path(path)
    path = path.resolve(strict=True)
    if not path.is_relative_to(metadata):
        raise ValueError("integration manifest path escapes metadata root")
    relative = path.relative_to(metadata).as_posix()
    parts = path.relative_to(metadata).parts
    if len(parts) != 3 or parts[0] != "integrations" or parts[2] != "manifest.json":
        raise ValueError("integration manifest is outside the canonical integration layout")
    integration_id = parts[1]
    if not _INTEGRATION_ID_RE.fullmatch(integration_id):
        raise ValueError("integration attempt ID is invalid")

    data = _json_file(path)
    if type(data) is not dict or set(data) != _INTEGRATION_FIELDS:
        raise ValueError("integration manifest fields are missing or extra")
    if type(data["schema_version"]) is not int or data["schema_version"] != 2:
        raise ValueError("unsupported integration manifest schema version")
    if type(data["terminal"]) is not bool or data["terminal"] is not True:
        raise ValueError("integration manifest is not terminal")
    if data["status"] not in _INTEGRATION_STATUSES:
        raise ValueError("integration status is invalid")
    if data["integration_id"] != integration_id:
        raise ValueError("integration ID does not match its metadata path")
    if type(data["execution_id"]) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", data["execution_id"]):
        raise ValueError("integration execution ID is invalid")
    for field in ("task_id", "task_revision", "task_sha256", "base_commit"):
        if data[field] != state[field]:
            raise ValueError("integration manifest " + field + " does not match initialized task")
    if type(data["task_sha256"]) is not str or not _SHA256_RE.fullmatch(data["task_sha256"]):
        raise ValueError("integration task digest is invalid")
    if type(data["base_commit"]) is not str or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", data["base_commit"]):
        raise ValueError("integration base commit is invalid")
    if type(data["started_at_utc"]) is not str or not data["started_at_utc"]:
        raise ValueError("integration start time is invalid")
    if data["integration_role"] != "integration_candidate":
        raise ValueError("integration role is not integration_candidate")

    attempt = metadata / "integrations" / integration_id
    _ensure_no_symlink_path(attempt)
    expected_candidate = attempt / "worktree"
    if type(data["candidate_worktree_path"]) is not str:
        raise ValueError("integration candidate path is invalid")
    candidate = Path(data["candidate_worktree_path"])
    _ensure_no_symlink_path(candidate)
    candidate = candidate.resolve(strict=True)
    if candidate != expected_candidate.resolve(strict=True):
        raise ValueError("integration candidate path does not match its attempt directory")
    expected_branch = "ssec/integration/" + state["task_id"] + "/" + integration_id
    if data["candidate_branch"] != expected_branch:
        raise ValueError("integration candidate branch identity is invalid")
    actual_branch = _read_git(candidate, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip()
    actual_head = _read_git(candidate, "rev-parse", "HEAD").decode().strip()
    if actual_branch != expected_branch or actual_head != state["base_commit"]:
        raise ValueError("integration candidate branch or base has changed")
    candidate_hash = data["candidate_tree_sha256"]
    if type(candidate_hash) is not str or not _SHA256_RE.fullmatch(candidate_hash):
        raise ValueError("integration candidate tree hash is invalid")
    if candidate_tree_sha256(candidate) != candidate_hash:
        raise ValueError("integration candidate tree changed after checks")

    expected_specs = _check_spec_data(specs)
    if data["check_specs"] != expected_specs:
        raise ValueError("integration check specs do not exactly match the task")
    worker_roles = {worker["role"] for worker in state["workers"]}
    worker_hashes = data["worker_tree_hashes"]
    if type(worker_hashes) is not dict or set(worker_hashes) != worker_roles or any(
            type(value) is not str or not _SHA256_RE.fullmatch(value) for value in worker_hashes.values()):
        raise ValueError("integration worker tree hashes are invalid")
    if type(data["input_manifests"]) is not list:
        raise ValueError("integration input manifests are invalid")
    seen_inputs = set()
    for item in data["input_manifests"]:
        if type(item) is not dict or set(item) not in (
                {"path", "sha256", "kind", "role"},
                {"path", "sha256", "kind", "role", "reviewer_role"}):
            raise ValueError("integration input manifest record is invalid")
        if (type(item["path"]) is not str or item["path"] in seen_inputs or
                type(item["sha256"]) is not str or not _SHA256_RE.fullmatch(item["sha256"]) or
                item["kind"] not in ("check", "review") or item["role"] not in worker_roles):
            raise ValueError("integration input manifest identity is invalid")
        seen_inputs.add(item["path"])
        input_path = _resolve_evidence_path(metadata, item["path"], directory=False)
        if _sha256(input_path) != item["sha256"]:
            raise ValueError("integration input manifest hash mismatch")
    if type(data["operations"]) is not list:
        raise ValueError("integration operations are invalid")
    if any(type(item) is not dict for item in data["operations"]):
        raise ValueError("integration operation record is invalid")
    if data["operations"] != sorted(data["operations"], key=lambda item: (item.get("role", ""), item.get("path", ""))):
        raise ValueError("integration operations are not in canonical order")
    contracts = validate_work_items(state["task_packet"], [worker["role"] for worker in state["workers"]],
                                    state["review_roles"], [spec.check_id for spec in specs])
    operation_paths = []
    candidate_entries = {entry.relative_path: entry for entry in _candidate_tree_entries(candidate)}
    for item in data["operations"]:
        if set(item) != {"role", "path", "operation", "sha256", "executable"}:
            raise ValueError("integration operation record is invalid")
        if item["role"] not in worker_roles or item["operation"] not in ("write", "delete"):
            raise ValueError("integration operation identity is invalid")
        _path(item["path"], "integration operation path")
        operation_paths.append(item["path"])
        contract = contracts[item["role"]]
        if (not any(_covers(scope, item["path"]) for scope in contract.file_ownership) or
                not any(_covers(scope, item["path"]) for scope in contract.outputs)):
            raise ValueError("integration operation is outside declared ownership/output scope")
        if item["operation"] == "write":
            if (type(item["sha256"]) is not str or not _SHA256_RE.fullmatch(item["sha256"]) or
                    type(item["executable"]) is not bool):
                raise ValueError("integration write operation is invalid")
            entry = candidate_entries.get(item["path"])
            if entry is None or _sha256(entry.path) != item["sha256"] or entry.executable != item["executable"]:
                raise ValueError("integration write operation does not match candidate content")
        elif item["sha256"] is not None or item["executable"] is not None:
            raise ValueError("integration delete operation is invalid")
        elif item["path"] in candidate_entries:
            raise ValueError("integration delete operation still exists in candidate")
    if len(operation_paths) != len(set(operation_paths)):
        raise ValueError("integration operation paths are duplicated")
    _reject_collisions(operation_paths)
    base_entries = _base_entries(Path(state["project_root"]), state["base_commit"])
    current_entries = {}
    for relative_path, entry in candidate_entries.items():
        content = _read_regular(entry.path)
        mode = b"100755" if entry.executable else b"100644"
        oid = _read_git(candidate, "hash-object", "--no-filters", "--stdin", input_bytes=content).strip()
        current_entries[relative_path] = (mode, oid)
    all_paths = set(base_entries) | set(current_entries)
    changed_paths = {relative_path for relative_path in all_paths
                     if base_entries.get(relative_path) != current_entries.get(relative_path)}
    if changed_paths != set(operation_paths):
        raise ValueError("integration operations do not exactly match candidate changes")
    if type(data["errors"]) is not list or any(type(error) is not str for error in data["errors"]):
        raise ValueError("integration errors are invalid")

    check_path_value = data["check_manifest_path"]
    check_hash = data["check_manifest_sha256"]
    check_status = data["check_status"]
    if data["status"] == "BUILT_AWAITING_CHECKS":
        if check_path_value is not None or check_hash is not None or check_status is not None:
            raise ValueError("built integration attempt unexpectedly claims terminal checks")
        return data, None
    if check_path_value is None:
        if data["status"] in ("CHECKED_AWAITING_INTEGRATED_REVIEW", "FAILED"):
            raise ValueError("terminal integration attempt is missing its check manifest")
        if check_hash is not None or check_status is not None:
            raise ValueError("integration check identity is incomplete")
        return data, None
    if (type(check_path_value) is not str or type(check_hash) is not str or
            not _SHA256_RE.fullmatch(check_hash) or check_status not in ("PASSED", "FAILED")):
        raise ValueError("integration check manifest path, hash, or status is invalid")
    check_path = _resolve_evidence_path(metadata, check_path_value, directory=False)
    if _sha256(check_path) != check_hash:
        raise ValueError("integrated check manifest hash mismatch or tampering detected")
    check_data = read_check_manifest(check_path, metadata)
    check_relative = check_path.relative_to(metadata).parts
    if (len(check_relative) != 4 or check_relative[0] != "check-runs" or
            check_relative[2:] != ("integration_candidate", "manifest.json") or
            check_data["execution_id"] != check_relative[1]):
        raise ValueError("integrated check manifest path does not match its execution identity")
    if check_data["status"] != check_status:
        raise ValueError("integrated check status does not match its manifest")
    check_prefix = f"check-runs/{check_relative[1]}/integration_candidate/"
    for field, expected in (
        ("task_id", state["task_id"]), ("task_revision", state["task_revision"]),
        ("task_sha256", state["task_sha256"]), ("base_commit", state["base_commit"]),
        ("candidate_tree_sha256", candidate_hash), ("worker_role", "integration_candidate"),
        ("worker_branch", expected_branch),
    ):
        if check_data[field] != expected:
            raise ValueError("integrated check manifest " + field + " does not match integration evidence")
    if check_data["snapshot"] is not None and check_data["snapshot"]["path"] != check_prefix + "snapshot":
        raise ValueError("integrated check snapshot is outside its canonical run directory")
    actual_checks = {item["check_id"]: item for item in check_data["checks"]}
    if set(actual_checks) != {spec.check_id for spec in specs}:
        raise ValueError("integrated check manifest does not contain the exact task check set")
    for spec in specs:
        item = actual_checks[spec.check_id]
        if (item["argv"] != list(spec.argv) or item["cwd"] != spec.cwd or
                float(item["timeout_seconds"]) != spec.timeout_seconds or item["protocol"] != spec.protocol):
            raise ValueError("integrated check command differs from task spec: " + spec.check_id)
        for label in ("stdout", "stderr"):
            value = item[label + "_path"]
            if value is not None and value != check_prefix + spec.check_id + "." + label:
                raise ValueError("integrated check log path is outside its run directory")
    if data["status"] == "CHECKED_AWAITING_INTEGRATED_REVIEW" and check_data["status"] != "PASSED":
        raise ValueError("checked integration does not have passing integrated checks")
    if data["status"] == "FAILED" and check_data["status"] != "FAILED":
        raise ValueError("failed integration does not have a failed terminal check manifest")
    return data, check_data


def _check_run_identity(result, metadata, state, branch, candidate_hash, specs):
    if result.status not in ("PASSED", "FAILED") or result.manifest_path is None:
        raise ValueError("integrated check run did not publish a terminal manifest")
    path = Path(result.manifest_path)
    _ensure_no_symlink_path(path)
    path = path.resolve(strict=True)
    if not path.is_relative_to(metadata):
        raise ValueError("integrated check manifest escapes metadata root")
    before_hash = _sha256(path)
    data = read_check_manifest(path, metadata)
    if _sha256(path) != before_hash:
        raise ValueError("integrated check manifest changed during validation")
    relative = path.relative_to(metadata).parts
    if (len(relative) != 4 or relative[0] != "check-runs" or
            relative[2:] != ("integration_candidate", "manifest.json") or
            data["execution_id"] != relative[1]):
        raise ValueError("integrated check manifest path does not match its run identity")
    expected = {
        "task_id": state["task_id"],
        "task_revision": state["task_revision"],
        "task_sha256": state["task_sha256"],
        "base_commit": state["base_commit"],
        "candidate_tree_sha256": candidate_hash,
        "worker_role": "integration_candidate",
        "worker_branch": branch,
    }
    for field, value in expected.items():
        if data[field] != value:
            raise ValueError("integrated check manifest " + field + " does not match the candidate")
    actual = {item["check_id"]: item for item in data["checks"]}
    if set(actual) != {spec.check_id for spec in specs}:
        raise ValueError("integrated check manifest does not contain the exact task check set")
    for spec in specs:
        item = actual[spec.check_id]
        if (item["argv"] != list(spec.argv) or item["cwd"] != spec.cwd or
                float(item["timeout_seconds"]) != spec.timeout_seconds or item["protocol"] != spec.protocol):
            raise ValueError("integrated check command differs from task spec: " + spec.check_id)
    if data["status"] != result.status:
        raise ValueError("integrated check result status does not match persisted manifest")
    if data["snapshot"] is not None:
        expected_snapshot = f"check-runs/{relative[1]}/integration_candidate/snapshot"
        if data["snapshot"]["path"] != expected_snapshot:
            raise ValueError("integrated check snapshot is outside its canonical run directory")
    return path, before_hash, data


def _publish_integration_manifest(pending_path, manifest_path, data, candidate,
                                  candidate_hash, *, check_path=None, check_hash=None,
                                  metadata=None, state=None, branch=None, specs=()):
    _write_atomic_manifest(pending_path, data)
    if _json_file(pending_path) != data:
        raise ValueError("integration manifest readback changed before publication")
    if data["status"] == "BUILT_AWAITING_CHECKS" and candidate_tree_sha256(candidate) != candidate_hash:
        raise ValueError("candidate changed before built integration publication")
    if data["status"] == "CHECKED_AWAITING_INTEGRATED_REVIEW":
        if candidate_tree_sha256(candidate) != candidate_hash:
            raise ValueError("candidate changed before checked integration publication")
        if check_path is None or _sha256(check_path) != check_hash:
            raise ValueError("integrated check manifest changed before publication")
        check_data = read_check_manifest(check_path, metadata)
        if (check_data["status"] != "PASSED" or check_data["worker_role"] != "integration_candidate" or
                check_data["worker_branch"] != branch or
                check_data["candidate_tree_sha256"] != candidate_hash):
            raise ValueError("integrated check evidence changed before publication")
        actual = {item["check_id"]: item for item in check_data["checks"]}
        if set(actual) != {spec.check_id for spec in specs}:
            raise ValueError("integrated check set changed before publication")
        for spec in specs:
            item = actual[spec.check_id]
            if (item["argv"] != list(spec.argv) or item["cwd"] != spec.cwd or
                    float(item["timeout_seconds"]) != spec.timeout_seconds or item["protocol"] != spec.protocol):
                raise ValueError("integrated check spec changed before publication")
    # The final rename is the only operation after publication validation.
    os.replace(pending_path, manifest_path)


def build_integration_candidate(project, task_id, execution_id, *, stop_event=None) -> IntegrationResult:
    """Compose a fresh candidate, run its checks, and leave review/release blocked."""
    integration_id = _new_integration_id()
    candidate = None
    manifest_path = None
    manifest_published = False
    check_path = None
    blockers = ()
    try:
        if stop_event is None:
            stop_event = threading.Event()
        if type(stop_event) is not threading.Event:
            raise ValueError("stop_event must be a threading.Event")
    except ValueError as exc:
        return IntegrationResult(integration_id, "BLOCKED", None, None, None, (str(exc),))
    try:
        if type(execution_id) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", execution_id):
            raise ValueError("execution_id must identify a safe persisted launch run_id")
        _path(execution_id, "execution_id")
        state, metadata = load(Path(project), task_id)
        _ensure_no_symlink_path(metadata)
        metadata = metadata.resolve(strict=True)
        if state["status"] != "WORKTREES_READY_UNREVIEWED":
            raise ValueError("initialized workflow is not ready")
        task = state["task_packet"]
        specs = validate_check_specs(task)
        contracts = validate_work_items(task, [w["role"] for w in state["workers"]],
                                        state["review_roles"], [spec.check_id for spec in specs])
        root = _source_identity(state)
        source_tree = candidate_tree_sha256(root)
        workers, inputs = _evidence(state, metadata, execution_id, contracts, specs)
        base = _base_entries(root, state["base_commit"])
        operations, contents = _operations(state, contracts, base)
        # Detect worker/evidence drift during preflight before candidate allocation.
        if _evidence(state, metadata, execution_id, contracts, specs) != (workers, inputs):
            raise ValueError("worker evidence changed during integration preflight")
        _source_identity(state)
        integration_root = metadata / "integrations"
        _ensure_no_symlink_path(integration_root)
        integration_root.mkdir(exist_ok=True)
        attempt = integration_root / integration_id
        attempt.mkdir(exist_ok=False)
        started_at_utc = _utc_now()
        candidate = attempt / "worktree"
        branch = "ssec/integration/" + task_id + "/" + integration_id
        _git(root, "worktree", "add", "--no-checkout", "-b", branch, str(candidate), state["base_commit"])
        _materialize_base(candidate, base, state["base_commit"])
        _overlay(candidate, operations, contents)
        candidate_hash = candidate_tree_sha256(candidate)
        if _evidence(state, metadata, execution_id, contracts, specs) != (workers, inputs):
            raise ValueError("worker evidence changed during candidate composition")
        _source_identity(state)
        if candidate_tree_sha256(root) != source_tree:
            raise ValueError("source checkout changed during composition")
        manifest = _integration_manifest_data(state, execution_id, integration_id, candidate, branch,
                                              candidate_hash, inputs, workers, operations, specs,
                                              started_at_utc=started_at_utc)
        manifest_path = attempt / "manifest.json"
        pending_path = attempt / "manifest.pending.json"
        _publish_integration_manifest(pending_path, manifest_path, manifest, candidate, candidate_hash)
        manifest_published = True

        # Keep the canonical worker roster untouched. The checker sees one
        # ephemeral identity bound to this composed Git worktree and its branch.
        integration_worker = dict(role="integration_candidate", branch=branch, path=str(candidate))
        integration_state = dict(state)
        integration_state["workers"] = [integration_worker]
        deadline = time.monotonic() + min(300.0, sum(spec.timeout_seconds for spec in specs) + 5.0)
        try:
            checked_result = run_checks(task, integration_state, integration_worker, metadata,
                                        stop_event=stop_event, deadline=deadline)
            check_path, check_hash, checked_manifest = _check_run_identity(
                checked_result, metadata, state, branch, candidate_hash, specs)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            blockers = ("integrated checks could not be validated: " + str(exc),)
            blocked = _integration_manifest_data(
                state, execution_id, integration_id, candidate, branch, candidate_hash, inputs,
                workers, operations, specs, status="BLOCKED", errors=blockers,
                started_at_utc=started_at_utc)
            try:
                _publish_integration_manifest(pending_path, manifest_path, blocked, candidate,
                                              candidate_hash)
            except (OSError, ValueError, TypeError):
                pass
            return IntegrationResult(integration_id, "BLOCKED", candidate, manifest_path, None, blockers)

        current_candidate_hash = candidate_tree_sha256(candidate)
        if checked_result.status == "FAILED" or checked_manifest["status"] == "FAILED":
            final_status = "FAILED"
            blockers = tuple(checked_result.errors) or ("one or more integrated checks failed",)
        elif stop_event.is_set():
            final_status = "BLOCKED"
            blockers = ("integrated checks were cancelled before checked publication",)
        elif current_candidate_hash != candidate_hash:
            final_status = "BLOCKED"
            blockers = ("candidate changed after integrated checks",)
        else:
            final_status = "CHECKED_AWAITING_INTEGRATED_REVIEW"
            blockers = ()
        check_relative = check_path.relative_to(metadata).as_posix()
        terminal = _integration_manifest_data(
            state, execution_id, integration_id, candidate, branch, candidate_hash, inputs,
            workers, operations, specs, status=final_status,
            check_manifest_path=check_relative, check_manifest_sha256=check_hash,
            check_status=checked_manifest["status"], errors=blockers,
            started_at_utc=started_at_utc)
        try:
            _publish_integration_manifest(pending_path, manifest_path, terminal, candidate,
                                          candidate_hash,
                                          check_path=check_path if final_status == "CHECKED_AWAITING_INTEGRATED_REVIEW" else None,
                                          check_hash=check_hash if final_status == "CHECKED_AWAITING_INTEGRATED_REVIEW" else None,
                                          metadata=metadata, state=state, branch=branch, specs=specs)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            blockers = ("integrated result publication failed: " + str(exc),)
            return IntegrationResult(integration_id, "BLOCKED", candidate, manifest_path,
                                     check_path, blockers)
        return IntegrationResult(integration_id, final_status, candidate, manifest_path,
                                 check_path, blockers)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        return IntegrationResult(integration_id, "BLOCKED", candidate,
                                 manifest_path if manifest_published else None,
                                 check_path, (str(exc),))
