"""Build a reproducible, synthetic SIR analysis workspace for the Qt client."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

try:
    from .scientific_core import (
        ObservationDataset,
        SirModelDefinition,
        analyze_sir_parameters,
        solve_sir_model,
    )
except ImportError:  # Support direct execution: python scripts/build_sir_analysis_demo.py
    from scientific_core import (
        ObservationDataset,
        SirModelDefinition,
        analyze_sir_parameters,
        solve_sir_model,
    )


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


def build_demo(output_dir: str | Path) -> dict[str, object]:
    """Calculate and write stable model/data/results/manifests for the demo."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    definition = SirModelDefinition.from_dict(_SIR_FIXTURE)
    source_solution = solve_sir_model(definition)
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
            "source": "synthetic exact observations generated from the SIR fixture",
            "fixture": "SSEC P3.17 constant-rate SIR v1",
            "data_status": "SYNTHETIC_FIXTURE",
        },
    })
    analysis = analyze_sir_parameters(
        definition,
        dataset,
        initial_parameters={"beta": 0.25, "gamma": 0.08},
        bounds={"beta": (0.05, 0.8), "gamma": (0.02, 0.4)},
        perturbations={"beta": 0.001, "gamma": 0.001},
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
    source_content = source_path.read_bytes()
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
                     "config": {"parameter_names": ["beta", "gamma"],
                                "context_refs": ["model", "observations"]}},
                    {"id": "sensitivity-view", "type": "sensitivity_plot", "title": "Sensibilidad local",
                     "resource_refs": ["sensitivity"],
                     "config": {"state_names": ["S", "I", "R"],
                                "parameter_names": ["beta", "gamma"],
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
        default=repository / "examples" / "sir_analysis_workspace_demo",
    )
    arguments = parser.parse_args(argv)
    result = build_demo(arguments.output_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
