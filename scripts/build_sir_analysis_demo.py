"""Build a reproducible, synthetic SIR analysis workspace for the Qt client."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

try:
    from .scientific_core import (
        ObservationDataset,
        SirModelDefinition,
        SirParameterAnalysis,
        analyze_sir_parameters,
        solve_sir_model,
    )
    from .scientific_workspace_loader import load_scientific_workspace
    from .scientific_workspace import validate_workspace_manifest
except ImportError:  # Support direct execution: python scripts/build_sir_analysis_demo.py
    from scientific_core import (
        ObservationDataset,
        SirModelDefinition,
        SirParameterAnalysis,
        analyze_sir_parameters,
        solve_sir_model,
    )
    from scientific_workspace_loader import load_scientific_workspace
    from scientific_workspace import validate_workspace_manifest


_SIR_FIXTURE: dict[str, object] = {
    "schema_version": 1,
    "model_type": "sir",
    "equation_set": "sir_frequency_dependent_v1",
    "equations": {
        "dS/dt": "-beta(t) * S * I / N",
        "dI/dt": "beta(t) * S * I / N - gamma(t) * I",
        "dR/dt": "gamma(t) * I",
    },
    "states": ["S", "I", "R"],
    "initial_conditions": {"S": 90.0, "I": 10.0, "R": 0.0},
    "parameters": {
        "beta": {"kind": "constant", "value": 0.3},
        "gamma": {"kind": "constant", "value": 0.1},
    },
    "t_span": [0.0, 10.0],
    "units": {"time": "day", "population": "person", "rate": "1/day"},
    "integrator": {"method": "RK4_FIXED_STEP", "max_step": 0.1, "max_steps": 100},
}


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(token: str) -> object:
    raise ValueError(f"non-finite JSON value {token!r} is not allowed")


def _strict_json_resource(content: bytes, label: str) -> object:
    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label} JSON is invalid: {exc}") from exc


def _analysis_config(content: bytes) -> dict[str, object]:
    payload = _strict_json_resource(content, "analysis configuration")
    required = {
        "schema_version", "initial_parameters", "bounds", "perturbations",
        "fit_knots", "max_iterations", "max_function_evaluations",
    }
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise ValueError("analysis configuration has missing or unknown fields")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("analysis configuration schema_version must be 1")
    for name in ("initial_parameters", "bounds", "perturbations"):
        if not isinstance(payload[name], Mapping):
            raise ValueError(f"analysis configuration {name} must be an object")
    fit_knots = payload["fit_knots"]
    if fit_knots is not None and not isinstance(fit_knots, Mapping):
        raise ValueError("analysis configuration fit_knots must be an object or null")
    for name in ("max_iterations", "max_function_evaluations"):
        if type(payload[name]) is not int or payload[name] < 1:
            raise ValueError(f"analysis configuration {name} must be a positive integer")
    return dict(payload)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _output_location(
    output_dir: str | Path,
    source_root: Path,
    *,
    source_root_path: str | Path | None = None,
) -> tuple[Path, str]:
    requested = Path(os.path.abspath(Path(output_dir).expanduser()))
    source = source_root.resolve(strict=True)
    source_path = source_root if source_root_path is None else source_root_path
    lexical_source = Path(os.path.abspath(Path(source_path).expanduser()))
    requested_inside = False
    for containment_root in (lexical_source, source):
        if not _is_relative_to(requested, containment_root):
            continue
        requested_inside = True
        current = containment_root
        for part in requested.relative_to(containment_root).parts:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise ValueError("analysis output cannot traverse symlinks or reparse points")
    root = requested.resolve(strict=False)
    if not requested_inside and _is_relative_to(root, source):
        raise ValueError("analysis output cannot alias the source project through a symlink")
    if root == source or _is_relative_to(source, root):
        raise ValueError("analysis output must be outside the source project")
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise ValueError("output directory must be empty")
    prefix = root.relative_to(source).as_posix() if _is_relative_to(root, source) else ""
    return root, prefix


def _create_analysis_output(
    output_dir: str | Path,
    *,
    source_root: Path,
    model_content: bytes,
    observations_content: bytes,
    analysis_config_content: bytes,
    dataset: ObservationDataset,
    analysis: SirParameterAnalysis,
    source_manifest_sha256: str,
    input_resource_sha256: Mapping[str, str],
) -> str:
    """Write a complete, digest-linked workspace into a new or empty directory."""
    root, prefix = _output_location(output_dir, source_root)

    source_content = Path(__file__).resolve().read_bytes().replace(b"\r\n", b"\n")
    core_content = (
        Path(__file__).resolve().with_name("scientific_core.py")
        .read_bytes()
        .replace(b"\r\n", b"\n")
    )
    provenance = {
        "schema_version": 1,
        "status": "CALCULATED_FROM_DIGEST_MATCHED_INPUTS",
        "source_workspace_manifest_sha256": source_manifest_sha256,
        "input_resource_sha256": dict(input_resource_sha256),
        "scientific_core_sha256": hashlib.sha256(core_content).hexdigest(),
        "python_version": sys.version.split()[0],
        "data_status": dataset.provenance.get("data_status", "NOT_DECLARED"),
        "input_source_authentication": "NOT_ASSESSED",
        "scientific_validity": "NOT_ASSESSED",
        "identifiability": "NOT_ASSESSED",
        "uncertainty": "NOT_CALCULATED",
    }
    uncertainty = {
        "schema_version": 1,
        "status": "NOT_CALCULATED",
        "scientific_validity": "NOT_ASSESSED",
        "identifiability": "NOT_ASSESSED",
        "reason": "No uncertainty estimator is defined in this analysis workflow.",
    }
    payloads: tuple[tuple[str, str, str, bytes], ...] = (
        ("model", "model_spec", "model/model.json", model_content),
        ("observations", "observations", "data/observations.json", observations_content),
        ("analysis-config", "generic", "config/sir-analysis.json", analysis_config_content),
        ("simulation", "simulation_result", "results/simulation.json",
         _json_bytes(analysis.solution.to_dict())),
        ("fit", "fit_result", "results/fit.json", _json_bytes(analysis.fit.to_dict())),
        ("sensitivity", "sensitivity_result", "results/sensitivity.json",
         _json_bytes(analysis.sensitivity.to_dict())),
        ("evaluation", "observation_evaluation", "results/evaluation.json",
         _json_bytes(analysis.evaluation.to_dict())),
        ("uncertainty", "uncertainty_result", "results/uncertainty.json",
         _json_bytes(uncertainty)),
        ("analysis-provenance", "generic", "results/provenance.json",
         _json_bytes(provenance)),
        ("scientific-core", "source_code", "code/scientific_core.py", core_content),
        ("analysis-builder", "source_code", "code/build_sir_analysis_demo.py", source_content),
    )
    resources = [
        {"id": resource_id, "kind": kind,
         "path": f"{prefix}/{path}" if prefix else path,
         "sha256": hashlib.sha256(content).hexdigest()}
        for resource_id, kind, path, content in payloads
    ]
    manifest = {
        "schema_version": 1,
        "workspace_id": f"sir-analysis-{source_manifest_sha256[:16]}",
        "title": "Análisis SIR a partir de recursos con digest coincidente",
        "description": (
            "Análisis calculado con recursos cuyas huellas coinciden con el manifiesto fuente. "
            "Esto no autentica procedencia; validez e identificabilidad: NOT_ASSESSED; "
            "incertidumbre: NOT_CALCULATED."
        ),
        "resources": resources,
        "sections": [
            {
                "id": "model-data",
                "title": "Modelo y observaciones de entrada",
                "components": [
                    {"id": "equations", "type": "equation_view", "title": "Ecuaciones",
                     "resource_refs": ["model"], "config": {}},
                    {"id": "parameters", "type": "parameter_table", "title": "Parámetros declarados",
                     "resource_refs": ["model"], "config": {}},
                    {"id": "observations-view", "type": "observation_table", "title": "Observaciones declaradas",
                     "resource_refs": ["observations"], "config": {}},
                ],
            },
            {
                "id": "analysis-results",
                "title": "Resultados calculados",
                "components": [
                    {"id": "trajectory", "type": "simulation_plot", "title": "Trayectorias RK4",
                     "resource_refs": ["simulation"],
                     "config": {"x_axis": "time", "series": ["S", "I", "R"],
                                "context_refs": ["model"]}},
                    {"id": "fit-view", "type": "fit_summary", "title": "Ajuste local calculado",
                     "resource_refs": ["fit"],
                     "config": {"parameter_names": list(analysis.fit.parameters),
                                "context_refs": ["model", "observations"]}},
                    {"id": "sensitivity-view", "type": "sensitivity_plot", "title": "Sensibilidad local",
                     "resource_refs": ["sensitivity"],
                     "config": {"state_names": ["S", "I", "R"],
                                "parameter_names": list(analysis.sensitivity.parameter_names),
                                "context_refs": ["model"]}},
                    {"id": "residual-view", "type": "residual_plot", "title": "Residuales calculados",
                     "resource_refs": ["evaluation"], "config": {}},
                    {"id": "uncertainty-view", "type": "uncertainty_summary", "title": "Incertidumbre",
                     "resource_refs": ["uncertainty"], "config": {"quantities": ["S", "I", "R"]}},
                ],
            },
        ],
    }
    manifest_content = _json_bytes(manifest)
    validate_workspace_manifest(manifest)
    if not root.exists():
        root.mkdir(parents=True)
    if any(root.iterdir()):
        raise ValueError("output directory must be empty")
    for _resource_id, _kind, relative_path, content in payloads:
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
    with (root / "workspace.json").open("xb") as stream:
        stream.write(manifest_content)
    return f"{prefix}/workspace.json" if prefix else "workspace.json"


def build_analysis_workspace(
    source_project_root: str | Path,
    source_manifest: str,
    output_dir: str | Path,
    *,
    model_resource_id: str = "model",
    observations_resource_id: str = "observations",
    config_resource_id: str = "analysis-config",
    expected_source_manifest_sha256: str | None = None,
) -> dict[str, object]:
    """Analyze validated SIR resources and write a digest-linked workspace.

    The source manifest loader verifies resource containment and SHA-256 before
    this function parses model, observations, or bounded analysis settings.
    """
    source_path = Path(source_project_root).expanduser()
    root = source_path.resolve(strict=True)
    output, _prefix = _output_location(
        output_dir, root, source_root_path=source_path
    )

    loaded = load_scientific_workspace(root, source_manifest)
    source_manifest_sha256 = hashlib.sha256(loaded.manifest_bytes).hexdigest()
    if (expected_source_manifest_sha256 is not None
            and source_manifest_sha256 != expected_source_manifest_sha256):
        raise ValueError("source workspace changed after analysis confirmation")
    by_id = {resource.resource_id: resource for resource in loaded.resources}
    requested = (
        (model_resource_id, "model_spec", "model"),
        (observations_resource_id, "observations", "observations"),
        (config_resource_id, "generic", "analysis configuration"),
    )
    selected = {}
    for resource_id, expected_kind, label in requested:
        resource = by_id.get(resource_id)
        if resource is None or resource.kind != expected_kind:
            raise ValueError(f"input workspace requires {label} resource {resource_id!r} of kind {expected_kind!r}")
        selected[label] = resource

    model_resource = selected["model"]
    observations_resource = selected["observations"]
    config_resource = selected["analysis configuration"]
    definition = SirModelDefinition.from_json(model_resource.content)
    observation_payload = _strict_json_resource(observations_resource.content, "observations")
    if not isinstance(observation_payload, Mapping):
        raise ValueError("observations JSON must be an object")
    dataset = ObservationDataset.from_dict(observation_payload)
    config = _analysis_config(config_resource.content)
    analysis = analyze_sir_parameters(
        definition,
        dataset,
        initial_parameters=config["initial_parameters"],
        bounds=config["bounds"],
        perturbations=config["perturbations"],
        fit_knots=config["fit_knots"],
        max_iterations=config["max_iterations"],
        max_function_evaluations=config["max_function_evaluations"],
    )
    workspace_path = _create_analysis_output(
        output,
        source_root=root,
        model_content=model_resource.content,
        observations_content=observations_resource.content,
        analysis_config_content=config_resource.content,
        dataset=dataset,
        analysis=analysis,
        source_manifest_sha256=source_manifest_sha256,
        input_resource_sha256={
            "model": model_resource.sha256,
            "observations": observations_resource.sha256,
            "analysis_config": config_resource.sha256,
        },
    )
    return {
        "status": "BUILT_ANALYSIS_WORKSPACE",
        "workspace_path": workspace_path,
        "resource_count": 11,
        "fit_status": analysis.fit.status,
        "parameters": dict(analysis.fit.parameters),
        "data_status": dataset.provenance.get("data_status", "NOT_DECLARED"),
        "analysis_execution": "COMPUTED_FROM_DECLARED_INPUTS",
        "scientific_validity": "NOT_ASSESSED",
        "identifiability": "NOT_ASSESSED",
        "uncertainty": "NOT_CALCULATED",
    }


def _profiled_fixture(beta_middle: float) -> dict[str, object]:
    fixture = json.loads(json.dumps(_SIR_FIXTURE))
    fixture["parameters"]["beta"] = {
        "kind": "piecewise_linear",
        "points": [[0.0, 0.3], [5.0, beta_middle], [10.0, 0.3]],
    }
    return fixture


def build_demo(output_dir: str | Path, *, scenario: str = "constant") -> dict[str, object]:
    """Calculate and write stable synthetic SIR workspaces for a declared scenario."""
    if scenario not in {"constant", "profiled"}:
        raise ValueError("scenario must be 'constant' or 'profiled'")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    if scenario == "profiled":
        fixture = _profiled_fixture(0.3)
        source_fixture = _profiled_fixture(0.45)
        fit_knots = {"beta": [1]}
        initial_parameters = {"beta_knot_1": 0.3, "gamma": 0.08}
        bounds = {"beta_knot_1": (0.05, 0.8), "gamma": (0.02, 0.4)}
        perturbations = {"beta_knot_1": 0.001, "gamma": 0.001}
    else:
        fixture = _SIR_FIXTURE
        source_fixture = _SIR_FIXTURE
        fit_knots = None
        initial_parameters = {"beta": 0.25, "gamma": 0.08}
        bounds = {"beta": (0.05, 0.8), "gamma": (0.02, 0.4)}
        perturbations = {"beta": 0.001, "gamma": 0.001}
    definition = SirModelDefinition.from_dict(fixture)
    source_definition = SirModelDefinition.from_dict(source_fixture)
    source_solution = solve_sir_model(source_definition)
    observation_rows = [
        {
            "time": source_solution.times[index],
            "values": dict(zip(source_solution.state_names, source_solution.states[index])),
        }
        for index in range(0, len(source_solution.times), 10)
    ]
    dataset = ObservationDataset.from_dict({
        "schema_version": 1,
        "time_unit": definition.time_unit,
        "variables": [
            {"name": state, "unit": definition.population_unit}
            for state in definition.state_names
        ],
        "observations": observation_rows,
        "provenance": {
            "source": (
                "synthetic exact observations generated by SSEC solve_sir_model; "
                + ("source beta knot 1=0.45 1/day at day 5, gamma=0.1 1/day"
                   if scenario == "profiled"
                   else "source beta=0.3 1/day, gamma=0.1 1/day")
            ),
            "fixture": f"SSEC P3.19 {scenario} SIR v1",
            "data_status": "SYNTHETIC_FIXTURE",
        },
    })
    analysis = analyze_sir_parameters(
        definition,
        dataset,
        initial_parameters=initial_parameters,
        bounds=bounds,
        perturbations=perturbations,
        fit_knots=fit_knots,
        max_iterations=100,
        max_function_evaluations=500,
    )

    model_payload = definition.to_dict()
    payloads: tuple[tuple[str, str, object], ...] = (
        ("model", "model_spec", model_payload),
        ("observations", "observations", dataset.to_dict()),
        ("simulation", "simulation_result", analysis.solution.to_dict()),
        ("fit", "fit_result", analysis.fit.to_dict()),
        ("sensitivity", "sensitivity_result", analysis.sensitivity.to_dict()),
        ("evaluation", "observation_evaluation", analysis.evaluation.to_dict()),
        (
            "uncertainty",
            "uncertainty_result",
            {
                "schema_version": 1,
                "status": "NOT_CALCULATED",
                "scientific_validity": "NOT_ASSESSED",
                "identifiability": "NOT_ASSESSED",
                "reason": "No uncertainty estimator is defined for this demo.",
            },
        ),
    )
    resource_records: list[dict[str, str]] = []
    for resource_id, kind, payload in payloads:
        folder = "model" if resource_id == "model" else (
            "data" if resource_id == "observations" else "results"
        )
        relative_path = f"{folder}/{resource_id}.json"
        content = _json_bytes(payload)
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        resource_records.append({
            "id": resource_id,
            "kind": kind,
            "path": relative_path,
            "sha256": hashlib.sha256(content).hexdigest(),
        })

    source_path = Path(__file__).resolve()
    # Make the embedded source artifact identical across Windows/Linux checkouts.
    source_content = source_path.read_bytes().replace(b"\r\n", b"\n")
    (root / "code").mkdir(parents=True, exist_ok=True)
    (root / "code" / "build_sir_analysis_demo.py").write_bytes(source_content)
    resource_records.append({
        "id": "analysis-builder",
        "kind": "source_code",
        "path": "code/build_sir_analysis_demo.py",
        "sha256": hashlib.sha256(source_content).hexdigest(),
    })

    manifest = {
        "schema_version": 1,
        "workspace_id": "synthetic-sir-analysis",
        "title": "SIR · análisis sintético reproducible",
        "description": (
            "Demostración de software con observaciones sintéticas generadas del modelo. "
            "Validez científica, identificabilidad e incertidumbre: NOT_ASSESSED."
        ),
        "resources": resource_records,
        "sections": [
            {
                "id": "model-data",
                "title": "Modelo y datos sintéticos",
                "components": [
                    {"id": "equations", "type": "equation_view", "title": "Ecuaciones",
                     "resource_refs": ["model"], "config": {}},
                    {"id": "parameters", "type": "parameter_table", "title": "Parámetros declarados",
                     "resource_refs": ["model"], "config": {}},
                    {"id": "observations-view", "type": "observation_table", "title": "Observaciones sintéticas",
                     "resource_refs": ["observations"], "config": {}},
                ],
            },
            {
                "id": "analysis-results",
                "title": "Simulación y análisis calculados",
                "components": [
                    {"id": "trajectory", "type": "simulation_plot", "title": "Trayectorias RK4",
                     "resource_refs": ["simulation"],
                     "config": {"x_axis": "time", "series": ["S", "I", "R"],
                                "context_refs": ["model"]}},
                    {"id": "fit-view", "type": "fit_summary", "title": "Ajuste local a fixture sintético",
                     "resource_refs": ["fit"],
                     "config": {"parameter_names": list(analysis.fit.parameters),
                                "context_refs": ["model", "observations"]}},
                    {"id": "sensitivity-view", "type": "sensitivity_plot", "title": "Sensibilidad local",
                     "resource_refs": ["sensitivity"],
                     "config": {"state_names": ["S", "I", "R"],
                                "parameter_names": list(analysis.sensitivity.parameter_names),
                                "context_refs": ["model"]}},
                    {"id": "residual-view", "type": "residual_plot", "title": "Residuales simulados",
                     "resource_refs": ["evaluation"], "config": {}},
                    {"id": "uncertainty-view", "type": "uncertainty_summary", "title": "Incertidumbre",
                     "resource_refs": ["uncertainty"], "config": {"quantities": ["S", "I", "R"]}},
                    {"id": "builder-code", "type": "code_view", "title": "Código del constructor",
                     "resource_refs": ["analysis-builder"], "config": {"language": "python"}},
                ],
            },
        ],
    }
    manifest_content = _json_bytes(manifest)
    (root / "workspace.json").write_bytes(manifest_content)
    return {
        "status": "BUILT_SYNTHETIC_DEMO",
        "scenario": scenario,
        "workspace_path": "workspace.json",
        "resource_count": len(resource_records),
        "fit_status": analysis.fit.status,
        "parameters": dict(analysis.fit.parameters),
        "scientific_validity": "NOT_ASSESSED",
        "identifiability": "NOT_ASSESSED",
        "uncertainty": "NOT_CALCULATED",
        "real_user_sir": "NOT_RUN",
    }


def main(argv: Sequence[str] | None = None) -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="output directory; required when --source-root is used",
    )
    parser.add_argument(
        "--scenario", choices=("constant", "profiled"), default="constant",
        help="synthetic scenario to calculate (default: constant)",
    )
    parser.add_argument("--source-root", type=Path,
                        help="project directory with a securely loadable workspace")
    parser.add_argument("--source-manifest",
                        help="project-relative source manifest path")
    parser.add_argument("--model-id", default="model",
                        help="model_spec resource id (default: model)")
    parser.add_argument("--observations-id", default="observations",
                        help="observations resource id (default: observations)")
    parser.add_argument("--analysis-config-id", default="analysis-config",
                        help="generic analysis settings resource id (default: analysis-config)")
    arguments = parser.parse_args(argv)
    if arguments.source_root is not None or arguments.source_manifest is not None:
        if arguments.source_root is None or arguments.source_manifest is None:
            parser.error("--source-root and --source-manifest must be supplied together")
        if arguments.output_dir is None:
            parser.error("--output-dir is required with --source-root")
        try:
            result = build_analysis_workspace(
                arguments.source_root,
                arguments.source_manifest,
                arguments.output_dir,
                model_resource_id=arguments.model_id,
                observations_resource_id=arguments.observations_id,
                config_resource_id=arguments.analysis_config_id,
            )
        except (OSError, TypeError, ValueError, RecursionError) as exc:
            print(json.dumps({"status": "INVALID", "error": str(exc)}), file=sys.stderr)
            return 2
    else:
        if arguments.model_id != "model" or arguments.observations_id != "observations" or arguments.analysis_config_id != "analysis-config":
            parser.error("resource id options require --source-root")
        output_dir = arguments.output_dir or (
            repository / "examples" / "sir_analysis_workspace_demo"
        )
        result = build_demo(output_dir, scenario=arguments.scenario)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
