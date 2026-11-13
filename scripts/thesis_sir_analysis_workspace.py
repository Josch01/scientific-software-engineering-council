"""Create a new digest-verified workspace from a computed thesis SIR analysis."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import uuid
from datetime import datetime

try:
    from . import scientific_workspace
    from .scientific_workspace_loader import MAX_RESOURCE_BYTES, load_scientific_workspace
    from .scientific_workspace_view import build_workspace_view_model
    from .thesis_sir_analysis import ThesisSIRParameterAnalysis
    from .thesis_sir_model import THESIS_PDF_SHA256, THESIS_SOURCE_REFERENCE, THESIS_SIR_EQUATION_SET
except ImportError:  # Support direct script-directory imports.
    import scientific_workspace
    from scientific_workspace_loader import MAX_RESOURCE_BYTES, load_scientific_workspace
    from scientific_workspace_view import build_workspace_view_model
    from thesis_sir_analysis import ThesisSIRParameterAnalysis
    from thesis_sir_model import THESIS_PDF_SHA256, THESIS_SOURCE_REFERENCE, THESIS_SIR_EQUATION_SET


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
def _json_bytes(payload: object, label: str) -> bytes:
    try:
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be finite JSON data") from exc
    if not content or len(content) > MAX_RESOURCE_BYTES:
        raise ValueError(f"{label} is empty or exceeds the workspace resource size limit")
    return content


def _safe_parent(value: str | os.PathLike[str]) -> Path:
    raw = Path(value).expanduser()
    try:
        info = raw.lstat()
    except OSError as exc:
        raise ValueError("existing output directory is required for an analysis workspace") from exc
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
            or not stat.S_ISDIR(info.st_mode)):
        raise ValueError("analysis workspace parent must be a regular non-symlink directory")
    return raw.resolve(strict=True)


def write_thesis_sir_analysis_workspace(
    output_parent: str | os.PathLike[str], analysis: ThesisSIRParameterAnalysis,
    *, started_at_utc: str | None = None, completed_at_utc: str | None = None,
) -> Path:
    """Write, digest-check, and render-check a create-only analysis workspace."""
    if not isinstance(analysis, ThesisSIRParameterAnalysis):
        raise TypeError("analysis must be a computed ThesisSIRParameterAnalysis")
    if not analysis.observations.week_labels or not analysis.fit.parameter_names:
        raise ValueError("analysis must contain observations and selected fit parameters")
    parent = _safe_parent(output_parent)
    model = _json_bytes(analysis.parameters.to_dict(), "thesis SIR model")
    observations = _json_bytes({
        "schema_version": 1,
        "series_id": analysis.observations.series_id,
        "week_labels": list(analysis.observations.week_labels),
        "counts": list(analysis.observations.counts),
        "units": "cases per 7-day interval",
        "source_sha256": analysis.observations.source_sha256,
        "selection": "selected observation series only; source file is not copied",
    }, "selected observations")
    source_files = []
    for resource_id, filename in (
        ("analysis_engine", "thesis_sir_analysis.py"),
        ("scientific_core", "scientific_core.py"),
        ("model_adapter", "thesis_sir_model.py"),
        ("workspace_writer", "thesis_sir_analysis_workspace.py"),
    ):
        source_path = Path(__file__).with_name(filename)
        info = source_path.lstat()
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
                or not stat.S_ISREG(info.st_mode)):
            raise ValueError(f"analysis engine source {filename} must be a regular file")
        source_content = source_path.read_bytes()
        if not source_content or len(source_content) > MAX_RESOURCE_BYTES:
            raise ValueError(f"analysis engine source {filename} is empty or too large")
        source_files.append((resource_id, "source_code", f"code/{filename}", source_content))
    source_hashes = {resource_id: hashlib.sha256(content).hexdigest()
                     for resource_id, _kind, _path, content in source_files}
    parsed_timestamps = {}
    for label, value in (("started_at_utc", started_at_utc),
                         ("completed_at_utc", completed_at_utc)):
        if value is None:
            continue
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{label} must include a timezone")
        parsed_timestamps[label] = parsed
    if ((started_at_utc is None) != (completed_at_utc is None)
            or (started_at_utc is not None and completed_at_utc is not None
                and parsed_timestamps["completed_at_utc"]
                < parsed_timestamps["started_at_utc"])):
        raise ValueError("analysis execution timestamps must be provided in chronological pairs")
    run_id = f"thesis-sir-fit-{uuid.uuid4().hex[:12]}"
    payloads = (
        ("model", "model_spec", "model/model.json", model),
        ("observations", "observations", "data/observations.json", observations),
        ("simulation", "simulation_result", "results/simulation.json",
         _json_bytes(analysis.solution.to_dict(), "simulation result")),
        ("fit", "fit_result", "results/fit.json", _json_bytes(analysis.fit.to_dict(), "fit result")),
        ("sensitivity", "sensitivity_result", "results/sensitivity.json",
         _json_bytes(analysis.sensitivity.to_dict(), "sensitivity result")),
        ("evaluation", "observation_evaluation", "results/evaluation.json",
         _json_bytes(dict(analysis.evaluation), "observation evaluation")),
        ("uncertainty", "uncertainty_result", "results/uncertainty.json", _json_bytes({
            "schema_version": 1,
            "status": "NOT_CALCULATED",
            "scientific_validity": "NOT_ASSESSED",
            "identifiability": "NOT_ASSESSED",
            "reason": "This workflow defines no validated uncertainty estimator.",
        }, "uncertainty status")),
        ("analysis", "generic", "results/analysis.json", _json_bytes({
            "schema_version": 1,
            "analysis_execution": "COMPUTED_FROM_DECLARED_INPUTS",
            "equation_set": THESIS_SIR_EQUATION_SET,
            "python_version": sys.version.split()[0],
            "input_source_sha256": analysis.observations.source_sha256,
            "fit_configuration": {
                "initial_parameters": dict(analysis.fit.initial_parameters),
                "bounds": {name: {"lower": value[0], "upper": value[1]}
                           for name, value in analysis.fit.bounds.items()},
                "sensitivity_perturbations": dict(analysis.sensitivity.perturbations),
            },
            "integrator": {
                "method": "RK4_FIXED_STEP",
                "requested_max_step_week": analysis.solution.requested_max_step,
                "max_steps_per_interval": analysis.evaluation["solver"]["max_steps_per_interval"],
                "max_total_steps": analysis.max_total_steps,
            },
            "engine_source_sha256": source_hashes,
            "work": {
                "total_rk4_steps": analysis.total_work_steps,
                "max_total_rk4_steps": analysis.max_total_steps,
                "requested_max_function_evaluations": analysis.requested_max_function_evaluations,
            },
            "scientific_validity": "NOT_ASSESSED",
            "identifiability": "NOT_ASSESSED",
            "uncertainty": "NOT_CALCULATED",
        }, "analysis provenance")),
        ("run-log", "generic", "results/run-log.json", _json_bytes({
            "schema_version": 1,
            "run_id": run_id,
            "status": "COMPUTED_FROM_DECLARED_INPUTS",
            "started_at_utc": started_at_utc,
            "completed_at_utc": completed_at_utc,
            "timing_status": "RECORDED" if started_at_utc is not None else "NOT_RECORDED",
            "fit_status": analysis.fit.status,
            "function_evaluations": analysis.fit.function_evaluations,
            "total_rk4_steps": analysis.total_work_steps,
            "input_source_sha256": analysis.observations.source_sha256,
            "engine_source_sha256": source_hashes,
            "human_review": "PENDING",
        }, "analysis run log")),
        *source_files,
    )
    digest = lambda content: hashlib.sha256(content).hexdigest()
    names = list(analysis.fit.parameter_names)
    resources = [{"id": rid, "kind": kind, "path": path, "sha256": digest(content)}
                 for rid, kind, path, content in payloads]
    manifest = {
        "schema_version": 1,
        "workspace_id": run_id,
        "title": "Ajuste SIR de tesis · análisis calculado",
        "description": (
            f"Fuente: {THESIS_SOURCE_REFERENCE} · PDF SHA-256 {THESIS_PDF_SHA256}. "
            "Análisis ligado por SHA-256 al modelo, observaciones y resultados. "
            "Validez e identificabilidad: NOT_ASSESSED; incertidumbre: NOT_CALCULATED."
        ),
        "resources": resources,
        "sections": [
            {"id": "analysis", "title": "Análisis científico", "components": [
                {"id": "trajectory", "type": "simulation_plot", "title": "Trayectorias RK4",
                 "resource_refs": ["simulation"],
                 "config": {"x_axis": "time", "series": ["S", "I", "R"], "context_refs": ["model"]}},
                {"id": "fit", "type": "fit_summary", "title": "Ajuste local",
                 "resource_refs": ["fit"],
                 "config": {"parameter_names": names, "context_refs": ["model", "observations"]}},
                {"id": "sensitivity", "type": "sensitivity_plot", "title": "Sensibilidad local",
                 "resource_refs": ["sensitivity"],
                 "config": {"state_names": ["S", "I", "R"], "parameter_names": names,
                            "context_refs": ["model"]}},
                {"id": "residuals", "type": "residual_plot", "title": "Residuales semanales",
                 "resource_refs": ["evaluation"], "config": {}},
                {"id": "uncertainty", "type": "uncertainty_summary", "title": "Incertidumbre",
                 "resource_refs": ["uncertainty"], "config": {"quantities": ["S", "I", "R"]}},
                {"id": "artifacts", "type": "artifact_browser", "title": "Recursos y procedencia",
                 "resource_refs": [item[0] for item in payloads], "config": {}},
            ]},
            {"id": "code", "title": "Código exacto del motor", "components": [
                {"id": resource_id, "type": "code_view", "title": filename,
                 "resource_refs": [resource_id], "config": {"language": "python"}}
                for resource_id, filename in (
                    ("analysis_engine", "Puente de ajuste P3.31"),
                    ("scientific_core", "Motor numérico SSEC"),
                    ("model_adapter", "Adaptador SIR de tesis"),
                    ("workspace_writer", "Generador de workspace P3.32"),
                )
            ]},
        ],
    }
    scientific_workspace.validate_workspace_manifest(manifest)
    manifest_bytes = _json_bytes(manifest, "workspace manifest")
    staging = Path(tempfile.mkdtemp(prefix=".ssec-thesis-sir-fit-", dir=parent))
    final = parent / f"ssec-thesis-sir-fit-{uuid.uuid4().hex[:12]}"
    try:
        for _rid, _kind, relative, content in payloads:
            target = staging.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(content)
        with (staging / "workspace.json").open("xb") as stream:
            stream.write(manifest_bytes)
        loaded = load_scientific_workspace(staging, "workspace.json")
        components = [component for section in build_workspace_view_model(loaded).sections
                      for component in section.components]
        if not components or any(component.status != "ok" for component in components):
            raise ValueError("generated analysis workspace failed the existing view contracts")
        if final.exists() or final.is_symlink():
            raise FileExistsError("analysis workspace output already exists; no files were overwritten")
        os.rename(staging, final)
        return final
    finally:
        if staging.exists():
            shutil.rmtree(staging)
