"""Run a deterministic synthetic fit through the exact thesis SIR bridge."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.thesis_sir_analysis import analyze_thesis_sir_parameters
from scripts.thesis_sir_model import (
    HarmonicTerm,
    ThesisSIRParameters,
    WeeklyCountObservations,
    evaluate_thesis_sir_weekly_counts,
)


def build_synthetic_result() -> dict[str, object]:
    truth = ThesisSIRParameters(
        d0=-0.45,
        harmonics=(HarmonicTerm(0.15, 0.04, 0.3),),
        gamma=0.18,
        log10_initial_infectious=6.0,
        susceptible_fraction=0.985,
        ascertainment_fraction=0.3,
        delay_days=0.0,
    )
    labels = tuple(f"synthetic-week-{index + 1:02d}" for index in range(8))
    empty = WeeklyCountObservations(labels, (0,) * len(labels), "SSEC_P3_31_SYNTHETIC")
    generated = evaluate_thesis_sir_weekly_counts(
        truth, empty, max_step=0.1, max_steps_per_interval=10
    )
    observations = WeeklyCountObservations(
        labels,
        tuple(int(round(value)) for value in generated.predicted_means),
        empty.series_id,
    )
    start = replace(truth, d0=-0.75)
    analysis = analyze_thesis_sir_parameters(
        start,
        observations,
        initial_parameters={"d0": -0.75},
        bounds={"d0": (-1.0, 0.0)},
        perturbations={"d0": 0.02},
        max_step=0.1,
        max_steps_per_interval=10,
    )
    return analysis.to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional full result JSON path; must not already exist",
    )
    arguments = parser.parse_args(argv)
    result = build_synthetic_result()
    if arguments.output is not None:
        with arguments.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    fit = result["fit"]
    assert isinstance(fit, dict)
    print(json.dumps({
        "status": "COMPUTED",
        "fixture": "SYNTHETIC_ONLY",
        "fit_status": fit["status"],
        "fitted_parameters": fit["parameters"],
        "max_abs_residual_cases": max(abs(value) for value in fit["residuals"]),
        "scientific_validity": result["scientific_validity"],
        "identifiability": result["identifiability"],
        "uncertainty": result["uncertainty"],
        "full_result_written": arguments.output is not None,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
