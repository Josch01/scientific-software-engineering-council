"""Run a small synthetic forward-model example for the thesis SIR contract."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.thesis_sir_model import (
    HarmonicTerm,
    ThesisSIRParameters,
    WeeklyCountObservations,
    evaluate_thesis_sir_weekly_counts,
)


def main() -> int:
    parameters = ThesisSIRParameters(
        d0=-1.0,
        harmonics=(HarmonicTerm(cosine=0.25, sine=-0.10, angular_frequency=0.8),),
        gamma=0.3,
        log10_initial_infectious=3.0,
        susceptible_fraction=0.99999,
        ascertainment_fraction=0.5,
        delay_days=4.3,
    )
    observations = WeeklyCountObservations(
        week_labels=("SYNTHETIC-W01", "SYNTHETIC-W02", "SYNTHETIC-W03", "SYNTHETIC-W04"),
        counts=(10, 15, 20, 18),
        series_id="SYNTHETIC_FIXTURE",
    )
    result = evaluate_thesis_sir_weekly_counts(
        parameters,
        observations,
        max_step=0.02,
        max_steps_per_interval=50,
    )
    print(json.dumps({
        "fixture_status": "SYNTHETIC_FIXTURE",
        "method": result.method,
        "weeks": len(result.week_labels),
        "predicted_means": list(result.predicted_means),
        "scientific_validity": "NOT_ASSESSED",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
