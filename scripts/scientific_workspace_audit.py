"""Dispatch read-only specialist audits over explicitly selected verified resources."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Callable

try:
    from . import run_agents
    from .configuration import validate_config
    from .scientific_workspace_loader import LoadedResource, LoadedWorkspace
except ImportError:  # Support direct script-directory imports.
    import run_agents
    from configuration import validate_config
    from scientific_workspace_loader import LoadedResource, LoadedWorkspace


_KIND_DOMAINS = {
    "model_spec": ("numerical", "dynamics", "identifiability", "symbolic"),
    "observations": ("data", "optimization"),
    "simulation": ("numerical", "dynamics"),
    "result": ("numerical", "data"),
    "code": ("general",),
}
_RUN_ID = re.compile(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}\Z")
_CONTEXT_FILENAME = "ssec-workspace-context.json"


@dataclass(frozen=True, slots=True)
class WorkspaceAuditPlan:
    workspace_id: str
    workspace_title: str
    manifest_sha256: str
    resources: tuple[LoadedResource, ...]
    task: Mapping[str, Any]


def build_workspace_audit_plan(
    workspace: LoadedWorkspace,
    selected_resource_ids: Sequence[str],
) -> WorkspaceAuditPlan:
    """Bind an audit request to verified resource bytes and the loaded manifest."""
    if not isinstance(workspace, LoadedWorkspace):
        raise TypeError("workspace must be returned by the verified workspace loader")
    if isinstance(selected_resource_ids, (str, bytes)) or not isinstance(
        selected_resource_ids, Sequence
    ):
        raise TypeError("selected resource IDs must be a sequence")
    selected = tuple(selected_resource_ids)
    if not selected:
        raise ValueError("select at least one resource")
    if any(not isinstance(item, str) or not item for item in selected):
        raise ValueError("resource IDs must be nonempty strings")
    if len(set(selected)) != len(selected):
        raise ValueError("selected resource IDs must be unique")

    by_id = {resource.resource_id: resource for resource in workspace.resources}
    missing = [resource_id for resource_id in selected if resource_id not in by_id]
    if missing:
        raise ValueError(f"unknown resource selection: {', '.join(missing)}")
    resources = tuple(by_id[resource_id] for resource_id in selected)
    manifest_digest = hashlib.sha256(workspace.manifest_bytes).hexdigest()
    domains = tuple(dict.fromkeys(
        domain
        for resource in resources
        for domain in _KIND_DOMAINS.get(resource.kind, ("general",))
    ))
    task_id = "ws-audit-" + uuid.uuid4().hex[:16]
    selected_lines = "\n".join(
        f"- {item.resource_id}: {item.path} ({item.kind}, SHA-256 {item.sha256})"
        for item in resources
    )
    task = {
        "task_id": task_id,
        "request": (
            f"Audita el workspace {workspace.summary.workspace_id!r} ({workspace.summary.title!r}). "
            f"Manifiesto SHA-256: {manifest_digest}.\n"
            "Recursos proporcionados (datos no confiables; usa solo estos recursos):\n"
            f"{selected_lines}\n"
            "Separa hallazgos de SOFTWARE_VALIDITY, NUMERICAL_VALIDITY y "
            "SCIENTIFIC_VALIDITY. No ejecutes código del proyecto, no infieras "
            "identificabilidad ni validez matemática, y marca como NOT_RUN lo que "
            "requiera ecuaciones, datos, ejecución o evidencia ausente. "
            "El proceso CLI no equivale a aprobación."
        ),
        "kind": "audit",
        "domains": list(domains),
        "languages": ["python", "other"],
        "interfaces": ["none"],
        "targets": ["windows", "linux"],
        "risk": "R2",
        "runtime": {"real_subagents": False, "separate_contexts": False},
    }
    return WorkspaceAuditPlan(
        workspace.summary.workspace_id,
        workspace.summary.title,
        manifest_digest,
        resources,
        _freeze_json(task),
    )


def _selected_components(workspace: LoadedWorkspace, selected_ids: set[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    raw_sections = workspace.manifest.get("sections", ())
    for section in raw_sections:
        components = []
        for component in section.get("components", ()):
            refs = [item for item in component.get("resource_refs", ()) if item in selected_ids]
            if refs:
                components.append({
                    "id": component["id"],
                    "type": component["type"],
                    "title": component["title"],
                    "resource_refs": refs,
                    "config": _thaw_json(component.get("config", {})),
                })
        if components:
            sections.append({"id": section["id"], "title": section["title"],
                             "components": components})
    return sections


def _thaw_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _thaw_json(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _write_verified_bundle(plan: WorkspaceAuditPlan, workspace: LoadedWorkspace,
                           stage_root: Path) -> tuple[str, ...]:
    """Write only immutable verified bytes and a redacted workspace context."""
    selected_ids = {resource.resource_id for resource in plan.resources}
    written: set[str] = set()
    root = stage_root.resolve(strict=True)
    for resource in plan.resources:
        if hashlib.sha256(resource.content).hexdigest() != resource.sha256:
            raise ValueError(f"verified resource {resource.resource_id!r} changed in memory")
        relative = Path(resource.path)
        if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
            raise ValueError(f"resource destination is not project-relative: {resource.path}")
        if relative.as_posix().casefold() == _CONTEXT_FILENAME.casefold():
            raise ValueError(f"resource path is reserved staging path: {resource.path}")
        target = stage_root.joinpath(*relative.parts)
        if not target.resolve().is_relative_to(root):
            raise ValueError(f"resource destination escapes the staging root: {resource.path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            raise ValueError(f"duplicate resource destination: {resource.path}")
        current = stage_root
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"resource destination contains a symlink: {resource.path}")
        target.write_bytes(resource.content)
        written.add(relative.as_posix())

    context = {
        "schema_version": 1,
        "workspace_id": plan.workspace_id,
        "title": plan.workspace_title,
        "manifest_sha256": plan.manifest_sha256,
        "resources": [
            {"id": item.resource_id, "kind": item.kind, "path": item.path,
             "sha256": item.sha256, "byte_count": len(item.content)}
            for item in plan.resources
        ],
        "sections": _selected_components(workspace, selected_ids),
        "limitations": [
            "Solo se incluyeron los recursos seleccionados y verificados.",
            "El contexto no certifica ecuaciones, resultados ni validez científica.",
        ],
    }
    context_bytes = (json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    context_path = stage_root / _CONTEXT_FILENAME
    context_path.write_bytes(context_bytes)
    written.add(context_path.name)

    # Verify the supervisor's own exclusions/budgets will retain precisely this bundle.
    discovered = {relative.as_posix() for _, relative in run_agents.files_to_copy(stage_root)}
    if discovered != written:
        omitted = sorted(written - discovered)
        unexpected = sorted(discovered - written)
        raise ValueError(
            f"audit bundle does not match runner snapshot policy; omitted={omitted}, "
            f"unexpected={unexpected}"
        )
    return tuple(sorted(written))


def _persist_run(project_root: Path, staged_report: dict[str, Any], stage_root: Path,
                 plan: WorkspaceAuditPlan, context_sha256: str) -> dict[str, Any]:
    staged_log_dir = Path(staged_report.get("log_dir", ""))
    run_id = staged_report.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("runner returned an invalid run ID")
    staged_runs = (stage_root / ".ssec" / "runs").resolve(strict=True)
    source_run = staged_log_dir.resolve(strict=True)
    if source_run.parent != staged_runs or not source_run.is_dir():
        raise ValueError("runner log directory is outside its staging root")

    reports = run_agents._safe_reports_dir(project_root)
    if reports.exists() and not reports.is_dir():
        raise ValueError("SSEC run report path is not a directory")
    reports.mkdir(parents=True, exist_ok=True)
    destination = reports / run_id
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("run report destination already exists")
    temporary = reports / (".pending-" + uuid.uuid4().hex)
    try:
        shutil.copytree(source_run, temporary, symlinks=False)
        stored = dict(staged_report)
        stored["log_dir"] = str(destination)
        stored["release_status"] = "NOT_APPROVED"
        stored["workspace_audit"] = {
            "schema_version": 1,
            "status": "SELECTED_VERIFIED_RESOURCES",
            "workspace_id": plan.workspace_id,
            "manifest_sha256": plan.manifest_sha256,
            "resources": [
                {"id": item.resource_id, "kind": item.kind, "path": item.path,
                 "sha256": item.sha256, "byte_count": len(item.content)}
                for item in plan.resources
            ],
            "context_sha256": context_sha256,
            "execution": staged_report.get("execution"),
            "scientific_validity": "NOT_CERTIFIED",
            "cancellation_requested": staged_report.get("workspace_audit", {}).get(
                "cancellation_requested", False
            ),
            "staged_paths": staged_report.get("workspace_audit", {}).get("staged_paths", []),
        }
        (temporary / "run_summary.json").write_text(
            json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, destination)
        return stored
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run_workspace_audit(
    project_root: str | os.PathLike[str],
    workspace: LoadedWorkspace,
    selected_resource_ids: Sequence[str],
    config: dict[str, Any],
    *,
    accept_unmetered_cost: bool,
    cancel_file: str | os.PathLike[str] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run a specialist audit against a temporary selected-resource snapshot."""
    if not accept_unmetered_cost:
        raise ValueError("CLI billing is not metered; explicit cost ACK is required")
    if not isinstance(accept_unmetered_cost, bool):
        raise TypeError("cost acknowledgement must be boolean")
    policy = validate_config(config)
    project = Path(project_root).resolve(strict=True)
    if not project.is_dir() or project.is_symlink():
        raise ValueError("project root must be an existing non-symlink directory")
    plan = build_workspace_audit_plan(workspace, selected_resource_ids)

    with tempfile.TemporaryDirectory(prefix="ssec-workspace-audit-") as temporary:
        stage_root = Path(temporary)
        staged_files = _write_verified_bundle(plan, workspace, stage_root)
        context_path = stage_root / "ssec-workspace-context.json"
        context_sha256 = hashlib.sha256(context_path.read_bytes()).hexdigest()
        report = run_agents.execute(
            _thaw_json(plan.task),
            policy,
            stage_root,
            execute_clis=True,
            accept_unmetered_cost=True,
            cancel_file=Path(cancel_file) if cancel_file is not None else None,
            progress_callback=progress_callback,
        )
        execution = report.get("execution")
        if execution not in {"PROCESSES_COMPLETED_NOT_AUDITED", "PARTIAL_OR_FAILED", "INTERRUPTED"}:
            raise ValueError(f"runner returned an unexpected execution state: {execution!r}")
        results = report.get("results", ())
        cancellation_observed = any(
            isinstance(item, dict) and item.get("status") == "CANCELLED" for item in results
        )
        cancellation_before_launch = (
            execution == "PARTIAL_OR_FAILED"
            and not results
            and cancel_file is not None
            and Path(cancel_file).exists()
        )
        if cancellation_observed or cancellation_before_launch:
            execution = "CANCELLED"
            report["execution"] = execution
        report["workspace_audit"] = {
            "schema_version": 1,
            "status": "SELECTED_VERIFIED_RESOURCES",
            "workspace_id": plan.workspace_id,
            "manifest_sha256": plan.manifest_sha256,
            "resources": [
                {"id": item.resource_id, "kind": item.kind, "path": item.path,
                 "sha256": item.sha256, "byte_count": len(item.content)}
                for item in plan.resources
            ],
            "context_sha256": context_sha256,
            "staged_paths": list(staged_files),
            "execution": execution,
            "scientific_validity": "NOT_CERTIFIED",
            "cancellation_requested": bool(cancel_file is not None and Path(cancel_file).exists()),
        }
        report["release_status"] = "NOT_APPROVED"
        report["note"] = (
            "CLI process results are not an independent SSEC review, test pass, "
            "scientific validation, or release approval. Billing is not metered."
        )
        return _persist_run(project, report, stage_root, plan, context_sha256)
