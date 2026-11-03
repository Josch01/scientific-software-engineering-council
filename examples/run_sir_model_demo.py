"""Run the synthetic, software-only SIR contract example."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.scientific_core import SirModelDefinition, solve_sir_model


def main() -> int:
    model_path = Path(__file__).with_name("sir_model_demo.json")
    model_bytes = model_path.read_bytes()
    definition = SirModelDefinition.from_json(model_bytes)
    solution = solve_sir_model(definition)
    report = {
        "status": "SIMULATED_FIXTURE",
        "scientific_validity": "NOT_ASSESSED",
        "equation_set": definition.equation_set,
        "method": solution.method,
        "step_count": solution.step_count,
        "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "initial_population": definition.initial_population,
        "final_state": dict(zip(solution.state_names, solution.states[-1])),
    }
    print(json.dumps(report, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
