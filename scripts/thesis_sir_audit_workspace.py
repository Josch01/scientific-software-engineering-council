"""Create a digest-verified workspace for human-approved thesis SIR audits."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid
from collections.abc import Mapping
from typing import Any

try:
    from . import scientific_workspace
    from .scientific_workspace_loader import (
        MAX_RESOURCE_BYTES,
        load_scientific_workspace,
    )
    from .scientific_workspace_view import build_workspace_view_model
    from .thesis_sir_model import (
        THESIS_PDF_SHA256,
        THESIS_SOURCE_REFERENCE,
        THESIS_SIR_EQUATION_SET,
        ThesisSIRParameters,
        WeeklyCountObservations,
    )
except ImportError:  # Support direct script-directory imports.
    import scientific_workspace
    from scientific_workspace_loader import MAX_RESOURCE_BYTES, load_scientific_workspace
    from scientific_workspace_view import build_workspace_view_model
    from thesis_sir_model import (
        THESIS_PDF_SHA256,
        THESIS_SOURCE_REFERENCE,
        THESIS_SIR_EQUATION_SET,
        ThesisSIRParameters,
        WeeklyCountObservations,
    )


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_OBSERVATION_SERIES = "DGE_monday_sunday_candidate"
_EQUATIONS = {
    "beta(t)": "exp(d0 + sum_k(a_k*cos(omega_k*t) + b_k*sin(omega_k*t)))",
    "dS/dt": "-beta(t)*S*I/N",
    "dI/dt": "beta(t)*S*I/N - gamma*I",
    "dR/dt": "gamma*I",
}


def _json_bytes(payload: object, label: str) -> bytes:
    try:
        content = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be finite JSON data") from exc
    if len(content) > MAX_RESOURCE_BYTES:
        raise ValueError(f"{label} exceeds the workspace resource size limit")
    return content


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validate_inputs(
    observations: WeeklyCountObservations,
    parameters: ThesisSIRParameters,
    result_payload: Mapping[str, Any],
) -> None:
    if not isinstance(observations, WeeklyCountObservations):
        raise TypeError("observations must be a validated WeeklyCountObservations value")
    if not isinstance(parameters, ThesisSIRParameters):
        raise TypeError("parameters must be a validated ThesisSIRParameters value")
    if not isinstance(result_payload, Mapping):
        raise TypeError("result_payload must be a result mapping")
    if observations.series_id != _OBSERVATION_SERIES:
        raise ValueError("only the selected DGE Monday-Sunday observation series can be audited")
    if not isinstance(observations.source_sha256, str):
        raise ValueError("observations require the source JSON SHA-256 digest")
    if result_payload.get("analysis_execution") != "COMPUTED_FROM_DECLARED_INPUTS":
        raise ValueError("a computed result is required to prepare an audit workspace")
    if result_payload.get("model") != parameters.to_dict():
        raise ValueError("result model does not match the declared parameters")
    result_observations = result_payload.get("observations")
    if not isinstance(result_observations, Mapping):
        raise ValueError("result observations are missing")
    expected_observations = {
        "series_id": observations.series_id,
        "source_sha256": observations.source_sha256,
        "week_labels": list(observations.week_labels),
        "counts": list(observations.counts),
    }
    if any(result_observations.get(key) != value for key, value in expected_observations.items()):
        raise ValueError("result observations do not match the selected input series")
    prediction = result_payload.get("prediction")
    if not isinstance(prediction, Mapping):
        raise ValueError("result predictions are missing")
    predicted = prediction.get("mean_cases")
    states = prediction.get("states_at_boundaries_person")
    boundaries = prediction.get("state_boundary_times_week")
    if (not isinstance(predicted, list) or len(predicted) != len(observations.counts)
            or not isinstance(states, list) or len(states) != len(observations.counts) + 1
            or not isinstance(boundaries, list) or len(boundaries) != len(states)):
        raise ValueError("result predictions do not match the declared observation intervals")
    for key in ("scientific_validity", "identifiability", "uncertainty"):
        if result_payload.get(key) != "NOT_ASSESSED":
            raise ValueError(f"result {key} must remain NOT_ASSESSED in the audit bundle")
    _json_bytes(dict(result_payload), "result payload")


def _safe_output_parent(value: str | os.PathLike[str]) -> Path:
    raw = Path(value).expanduser()
    try:
        info = raw.lstat()
    except OSError as exc:
        raise ValueError("audit workspace parent must be an existing directory") from exc
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
            or not stat.S_ISDIR(info.st_mode)):
        raise ValueError("audit workspace parent must be a regular non-symlink directory")
    return raw.resolve(strict=True)


def write_thesis_sir_audit_workspace(
    parent: str | os.PathLike[str],
    observations: WeeklyCountObservations,
    parameters: ThesisSIRParameters,
    result_payload: Mapping[str, Any],
) -> Path:
    """Write a new bundle, then re-load and render-validate it before returning.

    The source reconstruction is never copied: only the selected observation
    series and its original source digest are included. A unique directory is
    used and existing output files are never overwritten.
    """
    _validate_inputs(observations, parameters, result_payload)
    output_parent = _safe_output_parent(parent)
    model_content = _json_bytes({
        "schema_version": 1,
        "equation_set": THESIS_SIR_EQUATION_SET,
        "model_contract": parameters.to_dict(),
        "equations": _EQUATIONS,
        "source": {
            "reference": THESIS_SOURCE_REFERENCE,
            "pdf_sha256": THESIS_PDF_SHA256,
        },
        "scientific_validity": "NOT_ASSESSED",
        "identifiability": "NOT_ASSESSED",
        "uncertainty": "NOT_ASSESSED",
    }, "model specification")
    observation_content = _json_bytes({
        "schema_version": 1,
        "series_id": observations.series_id,
        "week_labels": list(observations.week_labels),
        "counts": list(observations.counts),
        "units": "cases per 7-day interval",
        "source_sha256": observations.source_sha256,
        "selection": "DGE_monday_sunday_candidate only",
    }, "observation resource")
    model_source = Path(__file__).with_name("thesis_sir_model.py")
    data_source = Path(__file__).with_name("thesis_sir_data.py")
    if model_source.is_symlink() or data_source.is_symlink():
        raise ValueError("SIR engine and data adapter sources must not be symlinks")
    model_source_content = model_source.read_bytes()
    data_source_content = data_source.read_bytes()
    if (not model_source_content or len(model_source_content) > MAX_RESOURCE_BYTES
            or not data_source_content or len(data_source_content) > MAX_RESOURCE_BYTES):
        raise ValueError("SIR engine source files are missing or exceed the resource limit")
    result_content = _json_bytes({
        "schema_version": 1,
        "result_contract": "thesis_sir_weekly_incidence",
        "result": dict(result_payload),
        "linked_resources": {
            "model_sha256": _sha256(model_content),
            "observations_sha256": _sha256(observation_content),
            "model_source_sha256": _sha256(model_source_content),
            "data_adapter_sha256": _sha256(data_source_content),
        },
    }, "simulation result")
    files = (
        ("sir_model", "model_spec", "resources/model.json", model_content),
        ("sir_observations", "observations", "resources/observations.json", observation_content),
        ("sir_result", "simulation_result", "results/forward-run.json", result_content),
        ("sir_engine", "source_code", "source/thesis_sir_model.py", model_source_content),
        ("sir_data_adapter", "source_code", "source/thesis_sir_data.py", data_source_content),
    )
    workspace_id = f"thesis-sir-audit-{uuid.uuid4().hex[:12]}"
    manifest = {
        "schema_version": 1,
        "workspace_id": workspace_id,
        "title": "SIR de tesis · ejecución declarada",
        "description": (
            "Bundle de auditoría generado localmente. Los artefactos están ligados por SHA-256; "
            "la ejecución no acredita validez científica ni identificabilidad."
        ),
        "resources": [
            {"id": resource_id, "kind": kind, "path": relative_path,
             "sha256": _sha256(content)}
            for resource_id, kind, relative_path, content in files
        ],
        "sections": [
            {
                "id": "sir_run_artifacts",
                "title": "Modelo, datos y resultado",
                "components": [{
                    "id": "audit_artifact_index",
                    "type": "artifact_browser",
                    "title": "Artefactos SIR verificados",
                    "resource_refs": [resource_id for resource_id, *_ in files],
                    "config": {},
                }],
            },
            {
                "id": "sir_implementation_source",
                "title": "Implementación exacta",
                "components": [
                    {
                        "id": "sir_engine_source_view",
                        "type": "code_view",
                        "title": "Motor SIR P2.5",
                        "resource_refs": ["sir_engine"],
                        "config": {"language": "python"},
                    },
                    {
                        "id": "sir_data_adapter_source_view",
                        "type": "code_view",
                        "title": "Adaptador de observaciones P2.5",
                        "resource_refs": ["sir_data_adapter"],
                        "config": {"language": "python"},
                    },
                ],
            },
        ],
    }
    scientific_workspace.validate_workspace_manifest(manifest)
    manifest_content = _json_bytes(manifest, "workspace manifest")

    staging = Path(tempfile.mkdtemp(prefix=".ssec-thesis-sir-audit-", dir=output_parent))
    final_path = output_parent / f"ssec-thesis-sir-audit-{uuid.uuid4().hex[:12]}"
    try:
        for _resource_id, _kind, relative_path, content in files:
            destination = staging.joinpath(*relative_path.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(content)
        with (staging / "workspace.json").open("xb") as stream:
            stream.write(manifest_content)
        loaded = load_scientific_workspace(staging, "workspace.json")
        view = build_workspace_view_model(loaded)
        components = tuple(
            component for section in view.sections for component in section.components
        )
        if not components or any(component.status != "ok" for component in components):
            raise ValueError("generated workspace did not pass the existing Qt view contract")
        if final_path.exists() or final_path.is_symlink():
            raise FileExistsError("audit workspace output already exists; no files were overwritten")
        os.rename(staging, final_path)
        staging = None  # type: ignore[assignment]
        return final_path
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
