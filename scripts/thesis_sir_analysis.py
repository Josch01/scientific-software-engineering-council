"""Analysis bridge for the exact harmonic thesis SIR observation model."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
from types import MappingProxyType

try:
    from .scientific_core import (
        OdeProblem,
        LeastSquaresFit,
        OdeSensitivity,
        OdeSolution,
        fit_least_squares,
        parameter_sensitivities,
    )
    from .thesis_sir_model import (
        ThesisSIRParameters,
        WeeklyCountObservations,
        WeeklyIncidenceResult,
        evaluate_thesis_sir_weekly_counts,
    )
except ImportError:  # Support direct execution/import from the scripts directory.
    from scientific_core import (
        OdeProblem,
        LeastSquaresFit,
        OdeSensitivity,
        OdeSolution,
        fit_least_squares,
        parameter_sensitivities,
    )
    from thesis_sir_model import (
        ThesisSIRParameters,
        WeeklyCountObservations,
        WeeklyIncidenceResult,
        evaluate_thesis_sir_weekly_counts,
    )


_MAX_TOTAL_ANALYSIS_STEPS = 1_000_000
_MAX_SENSITIVITY_VALUES = 1_000_000
_HARMONIC_PARAMETER = re.compile(
    r"^harmonic_(?P<index>\d+)_(?P<field>cosine|sine|angular_frequency)$"
)
_FIXED_OR_UNSUPPORTED = frozenset(
    {"log10_initial_infectious", "susceptible_fraction", "ascertainment_fraction", "delay_days"}
)


def _number(value: object, label: str) -> float:
    if isinstance(value, (str, bytes, bytearray, bool)):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _domain(parameters: ThesisSIRParameters, name: str) -> tuple[float, float]:
    if name == "d0":
        return -2.0, 2.0
    if name == "gamma":
        return 0.05, 0.70
    match = _HARMONIC_PARAMETER.fullmatch(name)
    if match is None:
        if name in _FIXED_OR_UNSUPPORTED:
            raise ValueError(f"parameter {name!r} is not supported for fitting in P3.31")
        raise ValueError(f"unknown thesis SIR fit parameter {name!r}")
    index = int(match.group("index"))
    if index >= len(parameters.harmonics):
        raise ValueError(f"fit parameter {name!r} is outside the declared harmonics")
    if match.group("field") == "angular_frequency":
        return 0.05, 2.20
    return -2.0, 2.0


def _parameter_value(parameters: ThesisSIRParameters, name: str) -> float:
    if name == "d0":
        return parameters.d0
    if name == "gamma":
        return parameters.gamma
    match = _HARMONIC_PARAMETER.fullmatch(name)
    if match is not None:
        index = int(match.group("index"))
        if index >= len(parameters.harmonics):
            raise ValueError(f"fit parameter {name!r} is outside the declared harmonics")
        return float(getattr(parameters.harmonics[index], match.group("field")))
    _domain(parameters, name)
    raise AssertionError("unreachable")


def _with_values(
    parameters: ThesisSIRParameters, values: Mapping[str, float]
) -> ThesisSIRParameters:
    d0 = parameters.d0
    gamma = parameters.gamma
    harmonics = list(parameters.harmonics)
    for name, raw_value in values.items():
        value = _number(raw_value, f"candidate parameter {name!r}")
        _domain(parameters, name)
        if name == "d0":
            d0 = value
        elif name == "gamma":
            gamma = value
        else:
            match = _HARMONIC_PARAMETER.fullmatch(name)
            assert match is not None
            index = int(match.group("index"))
            harmonics[index] = replace(
                harmonics[index], **{match.group("field"): value}
            )
    return replace(parameters, d0=d0, gamma=gamma, harmonics=tuple(harmonics))


def _observation_digest(observations: WeeklyCountObservations) -> tuple[str, str]:
    if observations.source_sha256 is not None:
        return observations.source_sha256, "source_sha256"
    canonical = json.dumps(
        {
            "series_id": observations.series_id,
            "week_labels": list(observations.week_labels),
            "counts": list(observations.counts),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), "canonical_observations_sha256"


def _evaluation_record(
    observations: WeeklyCountObservations,
    result: WeeklyIncidenceResult,
    *,
    model_parameters: Mapping[str, float],
    max_steps_per_interval: int,
    max_total_steps: int,
) -> dict[str, object]:
    digest, digest_kind = _observation_digest(observations)
    times = result.interval_ends
    residuals = tuple(
        predicted - observed
        for predicted, observed in zip(result.predicted_means, result.observed_counts)
    )
    variable = "weekly_cases"
    unit = "cases per 7-day interval"
    steps_per_interval = math.ceil(1.0 / result.max_step)
    return {
        "schema_version": 1,
        "method": "THESIS_SIR_WEEKLY_COUNT_INTERVAL_RK4",
        "observation_sha256": digest,
        "provenance": {
            "source": observations.series_id,
            "series_id": observations.series_id,
            "digest_kind": digest_kind,
        },
        "time_unit": "week",
        "variable_units": {variable: unit},
        "times": list(times),
        "observed_values": [
            {variable: float(value)} for value in result.observed_counts
        ],
        "simulated_values": [
            {variable: value} for value in result.predicted_means
        ],
        "residual_order": [
            {"time": time, "variable": variable} for time in times
        ],
        "residuals": list(residuals),
        "model": {
            "time_unit": "week",
            "variable_units": {variable: unit},
            "parameters": dict(model_parameters),
            "state_names": ["S", "I", "R", "cumulative_incidence"],
            "initial_state": [*result.parameters.initial_state(), 0.0],
        },
        "solver": {
            "requested_max_step": result.max_step,
            "segment_step_sizes": [1.0 / steps_per_interval] * len(times),
            "segment_step_counts": [steps_per_interval] * len(times),
            "total_step_count": steps_per_interval * len(times),
            "rhs_evaluation_count": 4 * steps_per_interval * len(times),
            "max_steps_per_interval": max_steps_per_interval,
            "max_total_steps": max_total_steps,
        },
    }


@dataclass(frozen=True)
class ThesisSIRParameterAnalysis:
    """Fit, state sensitivity, weekly residuals, and simulation for thesis SIR."""

    fit: LeastSquaresFit
    sensitivity: OdeSensitivity
    evaluation: Mapping[str, object]
    solution: OdeSolution
    parameters: ThesisSIRParameters
    observations: WeeklyCountObservations
    total_work_steps: int
    max_total_steps: int
    requested_max_function_evaluations: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "result_type": "thesis_sir_parameter_analysis",
            "analysis_execution": "COMPUTED_FROM_DECLARED_INPUTS",
            "fit": self.fit.to_dict(),
            "sensitivity": self.sensitivity.to_dict(),
            "evaluation": dict(self.evaluation),
            "simulation": self.solution.to_dict(),
            "model": self.parameters.to_dict(),
            "observations": {
                "series_id": self.observations.series_id,
                "source_sha256": self.observations.source_sha256,
                "week_labels": list(self.observations.week_labels),
                "counts": list(self.observations.counts),
            },
            "work": {
                "total_rk4_steps": self.total_work_steps,
                "max_total_rk4_steps": self.max_total_steps,
                "requested_max_function_evaluations": self.requested_max_function_evaluations,
                "effective_max_function_evaluations": self.fit.max_function_evaluations,
            },
            "scientific_validity": "NOT_ASSESSED",
            "identifiability": "NOT_ASSESSED",
            "uncertainty": "NOT_CALCULATED",
        }


def analyze_thesis_sir_parameters(
    parameters: ThesisSIRParameters,
    observations: WeeklyCountObservations,
    *,
    initial_parameters: Mapping[str, float],
    bounds: Mapping[str, Sequence[float]],
    perturbations: Mapping[str, float],
    max_step: float,
    max_steps_per_interval: int,
    max_iterations: int = 100,
    max_function_evaluations: int = 250,
    max_total_steps: int = _MAX_TOTAL_ANALYSIS_STEPS,
) -> ThesisSIRParameterAnalysis:
    """Fit selected dynamic parameters without changing the thesis observer.

    Initial conditions, ascertainment fraction, and discrete delay remain fixed
    to the supplied baseline. Sensitivity is local finite-difference sensitivity
    of the S/I/R/incidence trajectory, not an identifiability assessment.
    """
    if not isinstance(parameters, ThesisSIRParameters):
        raise ValueError("parameters must be a ThesisSIRParameters value")
    if not isinstance(observations, WeeklyCountObservations):
        raise ValueError("observations must be a WeeklyCountObservations value")
    if not isinstance(initial_parameters, Mapping) or not initial_parameters:
        raise ValueError("initial_parameters must be a non-empty mapping")
    if (isinstance(max_iterations, bool) or not isinstance(max_iterations, int)
            or max_iterations < 1):
        raise ValueError("max_iterations must be a positive integer")
    if (isinstance(max_function_evaluations, bool)
            or not isinstance(max_function_evaluations, int)
            or max_function_evaluations < 1):
        raise ValueError("max_function_evaluations must be a positive integer")
    names = tuple(initial_parameters)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("fit parameter names must be non-empty strings")
    if len(names) > 11:
        raise ValueError("thesis SIR analysis supports at most 11 dynamic parameters")
    if any(not isinstance(mapping, Mapping) or set(mapping) != set(names)
           for mapping in (bounds, perturbations)):
        raise ValueError("bounds and perturbations must match the selected fit parameters")

    initial: dict[str, float] = {}
    normalized_bounds: dict[str, tuple[float, float]] = {}
    normalized_perturbations: dict[str, float] = {}
    for name in names:
        lower_domain, upper_domain = _domain(parameters, name)
        value = _number(initial_parameters[name], f"initial_parameters[{name!r}]")
        raw_pair = bounds[name]
        if (not isinstance(raw_pair, Sequence)
                or isinstance(raw_pair, (str, bytes, bytearray))
                or len(raw_pair) != 2):
            raise ValueError(f"bounds[{name!r}] must be a finite lower/upper pair")
        lower = _number(raw_pair[0], f"bounds[{name!r}].lower")
        upper = _number(raw_pair[1], f"bounds[{name!r}].upper")
        if (lower >= upper or lower < lower_domain or upper > upper_domain):
            raise ValueError(
                f"bounds for {name!r} are outside the thesis parameter domain "
                f"[{lower_domain}, {upper_domain}]"
            )
        if not lower <= value <= upper:
            raise ValueError(f"initial parameter {name!r} must lie within its bounds")
        step = _number(perturbations[name], f"perturbations[{name!r}]")
        if step <= 0.0:
            raise ValueError(f"perturbation for {name!r} must be positive")
        if value - step < lower or value + step > upper:
            raise ValueError("sensitivity perturbation must stay inside fit bounds")
        initial[name] = value
        normalized_bounds[name] = (lower, upper)
        normalized_perturbations[name] = step

    requested_step = _number(max_step, "max_step")
    if requested_step <= 0.0:
        raise ValueError("max_step must be positive")
    steps_per_week = round(1.0 / requested_step)
    if (steps_per_week < 1 or not math.isclose(
            1.0 / requested_step, steps_per_week, rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError("max_step must divide one week evenly for thesis SIR analysis")
    if (isinstance(max_steps_per_interval, bool)
            or not isinstance(max_steps_per_interval, int)
            or max_steps_per_interval < steps_per_week):
        raise ValueError("max_steps_per_interval must cover the selected weekly RK4 grid")
    if (isinstance(max_total_steps, bool) or not isinstance(max_total_steps, int)
            or not 1 <= max_total_steps <= _MAX_TOTAL_ANALYSIS_STEPS):
        raise ValueError(
            f"max_total_steps must be between 1 and {_MAX_TOTAL_ANALYSIS_STEPS}"
        )

    selected_baseline = _with_values(parameters, initial)
    steps_per_evaluation = len(observations.counts) * steps_per_week
    # Keep the preflight aligned with parameter_sensitivities' resident arrays:
    # base values + lower/upper trajectories + output tensor.
    estimated_sensitivity_values = (
        (steps_per_evaluation + 1) * 4 * (2 * len(names) + 3)
    )
    if estimated_sensitivity_values > _MAX_SENSITIVITY_VALUES:
        raise ValueError("thesis SIR sensitivity output exceeds the supported value limit")
    sensitivity_trajectories = 1 + 2 * len(names)
    reserved_steps = steps_per_evaluation * (sensitivity_trajectories + 1)
    available_fit_evaluations = (max_total_steps - reserved_steps) // steps_per_evaluation
    if available_fit_evaluations < 1:
        raise ValueError(
            "work budget is insufficient for final evaluation and sensitivity"
        )
    effective_max_evaluations = min(max_function_evaluations, available_fit_evaluations)

    def residual_function(candidate: Mapping[str, float]) -> tuple[float, ...]:
        fitted = _with_values(selected_baseline, candidate)
        result = evaluate_thesis_sir_weekly_counts(
            fitted,
            observations,
            max_step=requested_step,
            max_steps_per_interval=max_steps_per_interval,
        )
        return tuple(
            predicted - observed
            for predicted, observed in zip(result.predicted_means, result.observed_counts)
        )

    fit = fit_least_squares(
        residual_function,
        initial,
        normalized_bounds,
        max_iterations=max_iterations,
        max_function_evaluations=effective_max_evaluations,
    )
    fitted_parameters = _with_values(selected_baseline, fit.parameters)
    final_evaluation = evaluate_thesis_sir_weekly_counts(
        fitted_parameters,
        observations,
        max_step=requested_step,
        max_steps_per_interval=max_steps_per_interval,
    )
    evaluation = _evaluation_record(
        observations,
        final_evaluation,
        model_parameters=fit.parameters,
        max_steps_per_interval=max_steps_per_interval,
        max_total_steps=max_total_steps,
    )
    if tuple(evaluation["residuals"]) != fit.residuals:
        raise ValueError("final thesis SIR residuals do not match fitted values")
    for name, step in normalized_perturbations.items():
        center = fit.parameters[name]
        lower, upper = normalized_bounds[name]
        if center - step < lower or center + step > upper:
            raise ValueError("sensitivity perturbation must stay inside fit bounds")

    sensitivity_problem_cache: tuple[tuple[tuple[str, float], ...], ThesisSIRParameters] | None = None

    def thesis_rhs(
        time: float, state: tuple[float, ...], candidate: Mapping[str, float]
    ) -> tuple[float, ...]:
        nonlocal sensitivity_problem_cache
        if len(state) != 4:
            raise ValueError("thesis SIR sensitivity state must contain S, I, R, and incidence")
        signature = tuple((name, float(candidate[name])) for name in names)
        if sensitivity_problem_cache is None or sensitivity_problem_cache[0] != signature:
            sensitivity_problem_cache = (signature, _with_values(selected_baseline, candidate))
        model = sensitivity_problem_cache[1]
        if state[3] < 0.0:
            raise ValueError("thesis SIR cumulative incidence must remain nonnegative")
        derivatives = model.derivative(time, state[:3])
        return (*derivatives, -derivatives[0])

    delay_weeks = fitted_parameters.delay_days / 7.0
    problem = OdeProblem(
        rhs=thesis_rhs,
        t_span=(-delay_weeks, len(observations.counts) - delay_weeks),
        initial_state=(*fitted_parameters.initial_state(), 0.0),
        parameters=fit.parameters,
        state_names=("S", "I", "R", "cumulative_incidence"),
    )
    fit_work = fit.function_evaluations * steps_per_evaluation
    final_evaluation_steps = len(final_evaluation.observed_counts) * steps_per_week
    remaining_steps = max_total_steps - fit_work - final_evaluation_steps
    sensitivity = parameter_sensitivities(
        problem,
        normalized_perturbations,
        requested_step,
        max_steps=max_steps_per_interval * len(observations.counts),
        max_total_steps=remaining_steps,
    )
    total_work = fit_work + final_evaluation_steps + sensitivity.total_step_count
    if total_work > max_total_steps:
        raise ValueError("thesis SIR analysis exceeded its shared RK4 work budget")
    if (len(sensitivity.times) * len(sensitivity.state_names) * len(names)
            > _MAX_SENSITIVITY_VALUES):
        raise ValueError("thesis SIR sensitivity output exceeds the supported value limit")
    return ThesisSIRParameterAnalysis(
        fit=fit,
        sensitivity=sensitivity,
        evaluation=MappingProxyType(evaluation),
        solution=sensitivity.base_solution,
        parameters=fitted_parameters,
        observations=observations,
        total_work_steps=total_work,
        max_total_steps=max_total_steps,
        requested_max_function_evaluations=max_function_evaluations,
    )
