"""Human-reviewed, digest-bound proposals for inert workspace manifests.

This module stores validated JSON layouts only. It never evaluates code or
invokes providers. Resource bytes are read through the scientific workspace
loader and pinned in the accepted copy.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path
import tempfile

try:
    from . import scientific_workspace as manifest_api
    from .scientific_workspace_loader import LoadedWorkspace, load_scientific_workspace
except ImportError:  # Support direct script imports by the desktop app.
    import scientific_workspace as manifest_api
    from scientific_workspace_loader import LoadedWorkspace, load_scientific_workspace


MAX_PROPOSAL_DIFF_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class WorkspaceProposalPreview:
    """Immutable review snapshot; approval revalidates its source and bindings."""

    project_root: Path
    proposal_relative_path: str
    active_manifest_sha256: str
    proposal_manifest_sha256: str
    approved_manifest_sha256: str
    resource_digests: tuple[tuple[str, str, str, int], ...]
    workspace_title: str
    diff: str
    changed: bool


@dataclass(frozen=True, slots=True)
class ApprovedWorkspaceProposal:
    """Validated workspace loaded from a create-only persisted manifest."""

    workspace: LoadedWorkspace
    manifest_relative_path: str
    sha256: str
    created: bool


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    return value


def _canonical_bytes(manifest: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            _plain_json(manifest), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("workspace manifest is not canonical JSON") from exc


def _review_bytes(manifest: Mapping[str, object]) -> bytes:
    """Render a lossless, human-readable JSON form with invisible Unicode escaped."""
    try:
        return (json.dumps(
            _plain_json(manifest), ensure_ascii=True, sort_keys=True,
            indent=2, allow_nan=False,
        ) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("workspace manifest is not serializable as JSON") from exc


def _manifest_sha256(manifest: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(manifest)).hexdigest()


def _resource_snapshot(workspace: LoadedWorkspace) -> tuple[tuple[str, str, str, int], ...]:
    return tuple(
        (item.resource_id, item.path, item.sha256, len(item.content))
        for item in workspace.resources
    )


def _approved_manifest(workspace: LoadedWorkspace) -> dict[str, object]:
    manifest = _plain_json(workspace.manifest)
    if type(manifest) is not dict:
        raise ValueError("loaded workspace manifest must be an object")
    resources = manifest.get("resources")
    if type(resources) is not list:
        raise ValueError("loaded workspace resources are malformed")
    observed = {item.resource_id: item.sha256 for item in workspace.resources}
    for resource in resources:
        if type(resource) is not dict:
            raise ValueError("loaded workspace resource entry is malformed")
        resource_id = resource.get("id")
        digest = observed.get(resource_id)
        if not isinstance(resource_id, str) or not isinstance(digest, str):
            raise ValueError("loaded workspace resource digest is unavailable")
        declared = resource.get("sha256")
        if declared != digest:
            raise ValueError("loaded workspace resource digest changed")
    return manifest


def _resolve_root(project_root: str | os.PathLike[str]) -> Path:
    try:
        root = Path(project_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("project root must be an existing directory") from exc
    if not root.is_dir():
        raise ValueError("project root must be an existing directory")
    return root


def preview_workspace_proposal(
    project_root: str | os.PathLike[str],
    active_workspace: LoadedWorkspace,
    proposal_relative_path: str,
) -> WorkspaceProposalPreview:
    """Validate resources, pin observed hashes, and produce the complete diff."""
    if not isinstance(active_workspace, LoadedWorkspace):
        raise ValueError("an active validated workspace is required for comparison")
    if type(proposal_relative_path) is not str or not proposal_relative_path:
        raise ValueError("proposal manifest path must be a non-empty project-relative string")
    root = _resolve_root(project_root)
    proposed = load_scientific_workspace(root, proposal_relative_path)
    active_manifest = _plain_json(active_workspace.manifest)
    if type(active_manifest) is not dict:
        raise ValueError("active workspace manifest is malformed")
    approved = _approved_manifest(proposed)
    active_digest = _manifest_sha256(active_manifest)
    proposal_digest = _manifest_sha256(proposed.manifest)
    approved_digest = _manifest_sha256(approved)
    before = _review_bytes(active_manifest).decode("utf-8").splitlines(keepends=True)
    after = _review_bytes(approved).decode("utf-8").splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(
        before, after, fromfile="active workspace", tofile="approved proposal"
    ))
    if len(diff.encode("utf-8")) > MAX_PROPOSAL_DIFF_BYTES:
        raise ValueError(f"workspace proposal diff exceeds {MAX_PROPOSAL_DIFF_BYTES} bytes")
    return WorkspaceProposalPreview(
        project_root=root,
        proposal_relative_path=proposal_relative_path,
        active_manifest_sha256=active_digest,
        proposal_manifest_sha256=proposal_digest,
        approved_manifest_sha256=approved_digest,
        resource_digests=_resource_snapshot(proposed),
        workspace_title=approved["title"],
        diff=diff,
        changed=active_digest != approved_digest,
    )


def _load_persisted(root: Path, relative_path: str, expected_sha256: str) -> LoadedWorkspace:
    target = root / relative_path
    if target.is_symlink():
        raise ValueError("existing proposal target is a symlink")
    try:
        workspace = load_scientific_workspace(root, relative_path)
    except (OSError, ValueError) as exc:
        raise ValueError("existing proposal target is invalid and was not overwritten") from exc
    if (workspace.manifest_bytes != _canonical_bytes(workspace.manifest)
            or hashlib.sha256(workspace.manifest_bytes).hexdigest() != expected_sha256):
        raise ValueError("existing proposal target is not canonical and was not overwritten")
    if _manifest_sha256(workspace.manifest) != expected_sha256:
        raise ValueError("existing proposal target has a different digest and was not overwritten")
    return workspace


def approve_workspace_proposal(
    project_root: str | os.PathLike[str],
    active_workspace: LoadedWorkspace,
    preview: WorkspaceProposalPreview,
) -> ApprovedWorkspaceProposal:
    """Revalidate the preview and create/reuse a digest-named pinned manifest.

    The caller is responsible for invoking this function only after an explicit
    human approval action. This API itself has no authority to infer consent.
    """
    if not isinstance(active_workspace, LoadedWorkspace):
        raise ValueError("an active validated workspace is required for approval")
    if not isinstance(preview, WorkspaceProposalPreview):
        raise ValueError("a validated proposal preview is required")
    root = _resolve_root(project_root)
    if root != preview.project_root:
        raise ValueError("proposal preview belongs to a different project root")
    active_manifest = _plain_json(active_workspace.manifest)
    if (type(active_manifest) is not dict or
            _manifest_sha256(active_manifest) != preview.active_manifest_sha256):
        raise ValueError("active workspace changed after preview")
    proposed = load_scientific_workspace(root, preview.proposal_relative_path)
    if _manifest_sha256(proposed.manifest) != preview.proposal_manifest_sha256:
        raise ValueError("proposal changed after preview")
    if _resource_snapshot(proposed) != preview.resource_digests:
        raise ValueError("proposal resources changed after preview")
    approved = _approved_manifest(proposed)
    digest = _manifest_sha256(approved)
    if digest != preview.approved_manifest_sha256:
        raise ValueError("approved proposal changed after preview")
    if not preview.changed:
        raise ValueError("proposal contains no workspace changes")
    persisted_bytes = _canonical_bytes(approved)
    manifest_api.validate_workspace_manifest(
        manifest_api.parse_workspace_manifest_bytes(persisted_bytes)
    )

    relative_path = f".ssec-workspace-{digest}.json"
    target = root / relative_path
    if target.exists() or target.is_symlink():
        workspace = _load_persisted(root, relative_path, digest)
        if _resource_snapshot(workspace) != preview.resource_digests:
            raise ValueError("existing proposal target resources do not match the reviewed proposal")
        return ApprovedWorkspaceProposal(workspace, relative_path, digest, False)

    temporary_name: str | None = None
    created = False
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".ssec-proposal-", suffix=".tmp", dir=root)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(persisted_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Hard-link creation is atomic and fails if another file already owns the name.
            os.link(temporary_name, target)
            created = True
        except FileExistsError:
            workspace = _load_persisted(root, relative_path, digest)
            if _resource_snapshot(workspace) != preview.resource_digests:
                raise ValueError("existing proposal target resources do not match the reviewed proposal")
            return ApprovedWorkspaceProposal(workspace, relative_path, digest, False)
        workspace = load_scientific_workspace(root, relative_path)
        if _manifest_sha256(workspace.manifest) != digest:
            raise ValueError("saved proposal manifest failed digest verification")
        if _resource_snapshot(workspace) != preview.resource_digests:
            raise ValueError("saved proposal resources changed during approval")
        return ApprovedWorkspaceProposal(workspace, relative_path, digest, True)
    except Exception:
        if created and temporary_name is not None:
            try:
                if os.path.samefile(temporary_name, target):
                    target.unlink()
            except OSError:
                pass
        raise
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
