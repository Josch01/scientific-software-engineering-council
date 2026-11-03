"""Compose an evidence-bound, disposable Git tree; no acceptance authority.

``execution_id`` selects a persisted development launch (``run_id``), never a
check-run ID. This stage intentionally stops before combined candidate checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .check_runner import (_ensure_no_symlink_path, _git, _is_filesystem_link,
                           _resolve_evidence_path, _write_atomic_manifest,
                           _duplicate_rejecting_object, read_check_manifest)
from .execution_evidence import (_candidate_tree_entries, candidate_tree_sha256,
                                 validate_check_specs)
from .prepare_agents import provider_for
from .review_evidence import validate_review_manifest
from .work_items import _covers, _path, validate_work_items
from .worktree_coordinator import check_requirements, load


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


def _source_identity(state):
    root = Path(state["project_root"])
    _ensure_no_symlink_path(root)
    if _git(root, "rev-parse", "HEAD").decode().strip() != state["base_commit"]:
        raise ValueError("source base commit changed")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("source checkout changed")
    return root


def _worker_identity(worker, state):
    root = Path(worker["path"])
    _ensure_no_symlink_path(root)
    if _git(root, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip() != worker["branch"]:
        raise ValueError("worker branch mismatch: " + worker["role"])
    if _git(root, "merge-base", "HEAD", state["base_commit"]).decode().strip() != state["base_commit"]:
        raise ValueError("worker base mismatch: " + worker["role"])
    # The tree hasher rejects POSIX symlinks, but on Windows a junction can be
    # reported as a directory. Inspect every Git-visible path before hashing.
    for raw in _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\x00"):
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
    for raw in _git(root, "ls-tree", "-r", "-z", base).split(b"\x00"):
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
        changed = _git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                       "--name-only", "-z", state["base_commit"], "--")
        additions = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
        # Let Git determine visibility and normalization. A clean CRLF checkout
        # can differ from its LF blobs without constituting a worker change.
        paths = {raw.decode("utf-8") for raw in (changed + additions).split(b"\x00") if raw}
        for path in sorted(paths):
            _path(path, "worker output path")
            entry = entries.get(path)
            content = _read_regular(entry.path) if entry else None
            mode = b"100755" if entry and entry.executable else b"100644"
            if entry:
                oid = _git(root, "hash-object", "--no-filters", "--stdin", input_bytes=content).strip()
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


def build_integration_candidate(project, task_id, execution_id) -> IntegrationResult:
    """Validate all inputs before allocating a fresh uncommitted candidate tree."""
    integration_id = uuid.uuid4().hex
    candidate = None
    manifest_path = None
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
        manifest = dict(schema_version=1, terminal=True, status="BUILT_AWAITING_CHECKS",
                        integration_id=integration_id, execution_id=execution_id,
                        **{key: state[key] for key in ("task_id", "task_revision", "task_sha256", "base_commit")},
                        candidate_worktree_path=str(candidate), candidate_branch=branch,
                        candidate_tree_sha256=candidate_hash, input_manifests=inputs,
                        worker_tree_hashes=workers, operations=operations, check_manifest_path=None)
        manifest_path = attempt / "manifest.json"
        _write_atomic_manifest(manifest_path, manifest)
        if _json_file(manifest_path) != manifest or candidate_tree_sha256(candidate) != candidate_hash:
            raise ValueError("integration manifest or candidate changed during publication")
        return IntegrationResult(integration_id, "BUILT_AWAITING_CHECKS", candidate,
                                 manifest_path, None, ())
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        return IntegrationResult(integration_id, "BLOCKED", candidate, None, None, (str(exc),))
