"""Typed forward model for the thesis SIR and its weekly count operator."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

try:
    from .scientific_core import OdeProblem, solve_rk4
except ImportError:  # Support direct execution/import from the scripts directory.
    from scientific_core import OdeProblem, solve_rk4


THESIS_SIR_POPULATION = 129_960_600.0
THESIS_SIR_EQUATION_SET = "thesis_sir_harmonic_weekly_v1"
_THESIS_DELAY_SCENARIOS = (0.0, 3.5, 4.3, 6.5)
_MAX_WEEKLY_OBSERVATIONS = 10_000
_MAX_TOTAL_RK4_STEPS = 1_000_000
_CONSERVATION_TOLERANCE = THESIS_SIR_POPULATION * 1e-12


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, (str, bytes, bytearray, bool)):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _bounded(value: object, label: str, lower: float, upper: float) -> float:
    number = _finite_number(value, label)
    if not lower <= number <= upper:
        raise ValueError(f"{label} must be in [{lower}, {upper}]")
    return number


@dataclass(frozen=True)
class HarmonicTerm:
    """One bounded cosine/sine pair in the exponential transmission rate."""

    cosine: float
    sine: float
    angular_frequency: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "cosine", _bounded(self.cosine, "cosine", -2.0, 2.0))
        object.__setattr__(self, "sine", _bounded(self.sine, "sine", -2.0, 2.0))
        object.__setattr__(
            self,
            "angular_frequency",
            _bounded(self.angular_frequency, "angular_frequency", 0.05, 2.20),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "cosine": self.cosine,
            "sine": self.sine,
            "angular_frequency": self.angular_frequency,
        }


@dataclass(frozen=True)
class ThesisSIRParameters:
    """Parameter values and fixed conventions from thesis chapter 3."""

    d0: float
    harmonics: tuple[HarmonicTerm, ...]
    gamma: float
    log10_initial_infectious: float
    susceptible_fraction: float
    ascertainment_fraction: float
    delay_days: float = 4.3

    def __post_init__(self) -> None:
        object.__setattr__(self, "d0", _bounded(self.d0, "d0", -2.0, 2.0))
        if not isinstance(self.harmonics, Sequence) or isinstance(
            self.harmonics, (str, bytes, bytearray)
        ):
            raise ValueError("harmonics must be a sequence of HarmonicTerm values")
        harmonics = tuple(self.harmonics)
        if not 1 <= len(harmonics) <= 3:
            raise ValueError("harmonics must contain 1 to 3 terms")
        if any(not isinstance(term, HarmonicTerm) for term in harmonics):
            raise ValueError("harmonics must contain only HarmonicTerm values")
        object.__setattr__(self, "harmonics", harmonics)
        object.__setattr__(self, "gamma", _bounded(self.gamma, "gamma", 0.05, 0.70))

        max_log10_infectious = math.log10(THESIS_SIR_POPULATION)
        object.__setattr__(
            self,
            "log10_initial_infectious",
            _bounded(
                self.log10_initial_infectious,
                "log10_initial_infectious",
                0.0,
                max_log10_infectious,
            ),
        )
        object.__setattr__(
            self,
            "susceptible_fraction",
            _bounded(self.susceptible_fraction, "susceptible_fraction", 0.0, 1.0),
        )
        object.__setattr__(
            self,
            "ascertainment_fraction",
            _bounded(self.ascertainment_fraction, "ascertainment_fraction", 0.0, 1.0),
        )
        delay = _finite_number(self.delay_days, "delay_days")
        if not any(math.isclose(delay, allowed, rel_tol=0.0, abs_tol=1e-12)
                   for allowed in _THESIS_DELAY_SCENARIOS):
            raise ValueError("delay_days must be one of 0, 3.5, 4.3, or 6.5")
        object.__setattr__(self, "delay_days", delay)

        susceptible, infectious, recovered = self.initial_state()
        if min(susceptible, infectious, recovered) < 0.0:
            raise ValueError("initial SIR state must be nonnegative and sum to the population")

    def beta(self, time_weeks: float) -> float:
        """Evaluate beta(t) with the explicitly supported Fourier form only."""
        time = _finite_number(time_weeks, "time_weeks")
        harmonic_values = (
            term.cosine * math.cos(term.angular_frequency * time)
            + term.sine * math.sin(term.angular_frequency * time)
            for term in self.harmonics
        )
        try:
            value = math.exp(math.fsum((self.d0, *harmonic_values)))
        except OverflowError as exc:
            raise ValueError("beta(t) is outside the finite numeric range") from exc
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("beta(t) is outside the finite positive numeric range")
        return value

    def derivative(
        self, time_weeks: float, state: Sequence[float]
    ) -> tuple[float, float, float]:
        """Evaluate the thesis SIR right-hand side for a feasible state."""
        time = _finite_number(time_weeks, "time_weeks")
        if not isinstance(state, Sequence) or isinstance(state, (str, bytes, bytearray)):
            raise ValueError("SIR state must be a numeric sequence")
        values = tuple(_finite_number(value, f"state[{index}]") for index, value in enumerate(state))
        if len(values) != 3:
            raise ValueError("SIR state must contain exactly S, I, R")
        susceptible, infectious, recovered = values
        if min(values) < 0.0:
            raise ValueError("SIR state must be nonnegative")
        if abs(math.fsum(values) - THESIS_SIR_POPULATION) > _CONSERVATION_TOLERANCE:
            raise ValueError("SIR state must sum to the fixed population")
        infection_flow = self.beta(time) * susceptible * infectious / THESIS_SIR_POPULATION
        removal_flow = self.gamma * infectious
        derivative = (-infection_flow, infection_flow - removal_flow, removal_flow)
        if not all(math.isfinite(value) for value in derivative):
            raise ValueError("SIR derivative is outside the finite numeric range")
        return derivative

    def initial_state(self) -> tuple[float, float, float]:
        infectious = 10.0 ** self.log10_initial_infectious
        if (infectious > THESIS_SIR_POPULATION
                and infectious - THESIS_SIR_POPULATION <= THESIS_SIR_POPULATION * 1e-14):
            infectious = THESIS_SIR_POPULATION
        susceptible = THESIS_SIR_POPULATION * self.susceptible_fraction
        recovered = THESIS_SIR_POPULATION - susceptible - infectious
        return susceptible, infectious, recovered

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "model_type": "sir",
            "equation_set": THESIS_SIR_EQUATION_SET,
            "population": THESIS_SIR_POPULATION,
            "states": ["S", "I", "R"],
            "units": {
                "population": "person",
                "time": "week",
                "rates": "1/week",
                "angular_frequency": "rad/week",
            },
            "parameters": {
                "d0": self.d0,
                "harmonics": [term.to_dict() for term in self.harmonics],
                "gamma": self.gamma,
                "log10_initial_infectious": self.log10_initial_infectious,
                "susceptible_fraction": self.susceptible_fraction,
                "ascertainment_fraction": self.ascertainment_fraction,
                "delay_days": self.delay_days,
            },
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ThesisSIRParameters":
        expected = {
            "schema_version", "model_type", "equation_set", "population",
            "states", "units", "parameters",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("thesis SIR model must contain exactly the versioned contract fields")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("unsupported thesis SIR schema_version; expected 1")
        if payload["model_type"] != "sir" or payload["equation_set"] != THESIS_SIR_EQUATION_SET:
            raise ValueError("unsupported thesis SIR equation_set")
        if _finite_number(payload["population"], "population") != THESIS_SIR_POPULATION:
            raise ValueError("thesis SIR population is fixed at 129960600 persons")
        if payload["states"] != ["S", "I", "R"]:
            raise ValueError("thesis SIR states must be exactly S, I, R")
        expected_units = {
            "population": "person", "time": "week", "rates": "1/week",
            "angular_frequency": "rad/week",
        }
        if payload["units"] != expected_units:
            raise ValueError("thesis SIR units do not match the versioned contract")
        values = payload["parameters"]
        expected_parameters = {
            "d0", "harmonics", "gamma", "log10_initial_infectious",
            "susceptible_fraction", "ascertainment_fraction", "delay_days",
        }
        if not isinstance(values, Mapping) or set(values) != expected_parameters:
            raise ValueError("thesis SIR parameters contain missing or unknown fields")
        raw_terms = values["harmonics"]
        if not isinstance(raw_terms, Sequence) or isinstance(
            raw_terms, (str, bytes, bytearray)
        ):
            raise ValueError("harmonics must be a sequence")
        terms: list[HarmonicTerm] = []
        for index, raw_term in enumerate(raw_terms):
            if not isinstance(raw_term, Mapping) or set(raw_term) != {
                "cosine", "sine", "angular_frequency"
            }:
                raise ValueError(f"harmonics[{index}] has missing or unknown fields")
            terms.append(HarmonicTerm(**raw_term))
        return cls(
            d0=values["d0"],
            harmonics=tuple(terms),
            gamma=values["gamma"],
            log10_initial_infectious=values["log10_initial_infectious"],
            susceptible_fraction=values["susceptible_fraction"],
            ascertainment_fraction=values["ascertainment_fraction"],
            delay_days=values["delay_days"],
        )


@dataclass(frozen=True)
class WeeklyCountObservations:
    """Ordered weekly counts; data identity is retained as provenance."""

    week_labels: tuple[str, ...]
    counts: tuple[int, ...]
    series_id: str = "SYNTHETIC_FIXTURE"
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.week_labels, Sequence) or isinstance(
            self.week_labels, (str, bytes, bytearray)
        ):
            raise ValueError("week_labels must be a sequence")
        if not isinstance(self.counts, Sequence) or isinstance(
            self.counts, (str, bytes, bytearray)
        ):
            raise ValueError("counts must be a sequence")
        labels = tuple(self.week_labels)
        counts = tuple(self.counts)
        if not 1 <= len(labels) <= _MAX_WEEKLY_OBSERVATIONS or len(labels) != len(counts):
            raise ValueError("weekly observations must contain matching nonempty labels and counts")
        if any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError("week labels must be nonempty strings")
        if len(set(labels)) != len(labels):
            raise ValueError("week labels must be unique")
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("weekly counts must be nonnegative integers")
        if not isinstance(self.series_id, str) or not self.series_id.strip() or len(self.series_id) > 128:
            raise ValueError("series_id must be a nonempty string of at most 128 characters")
        if self.source_sha256 is not None and (
            not isinstance(self.source_sha256, str)
            or len(self.source_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.source_sha256)
        ):
            raise ValueError("source_sha256 must be a lowercase SHA-256 hex digest")
        object.__setattr__(self, "week_labels", labels)
        object.__setattr__(self, "counts", counts)


@dataclass(frozen=True)
class WeeklyIncidenceResult:
    week_labels: tuple[str, ...]
    observed_counts: tuple[int, ...]
    predicted_means: tuple[float, ...]
    interval_starts: tuple[float, ...]
    interval_ends: tuple[float, ...]
    states_at_boundaries: tuple[tuple[float, float, float], ...]
    parameters: ThesisSIRParameters
    series_id: str
    source_sha256: str | None
    max_step: float
    max_steps_per_interval: int
    method: str = "RK4_FIXED_STEP"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "result_type": "thesis_sir_weekly_incidence",
            "analysis_execution": "COMPUTED_FROM_DECLARED_INPUTS",
            "method": self.method,
            "model": self.parameters.to_dict(),
            "observations": {
                "series_id": self.series_id,
                "source_sha256": self.source_sha256,
                "week_labels": list(self.week_labels),
                "counts": list(self.observed_counts),
            },
            "prediction": {
                "units": "cases per 7-day interval",
                "interval_starts_week": list(self.interval_starts),
                "interval_ends_week": list(self.interval_ends),
                "state_boundary_times_week": [
                    self.interval_starts[0], *self.interval_ends
                ],
                "mean_cases": list(self.predicted_means),
                "states_at_boundaries_person": [list(state) for state in self.states_at_boundaries],
            },
            "integrator": {
                "method": self.method,
                "max_step_week": self.max_step,
                "max_steps_per_interval": self.max_steps_per_interval,
            },
            "scientific_validity": "NOT_ASSESSED",
            "identifiability": "NOT_ASSESSED",
            "uncertainty": "NOT_ASSESSED",
        }


def evaluate_thesis_sir_weekly_counts(
    parameters: ThesisSIRParameters,
    observations: WeeklyCountObservations,
    *,
    max_step: float,
    max_steps_per_interval: int,
) -> WeeklyIncidenceResult:
    """Compute shifted weekly infection means using the existing fixed-step RK4."""
    if not isinstance(parameters, ThesisSIRParameters):
        raise ValueError("parameters must be a ThesisSIRParameters value")
    if not isinstance(observations, WeeklyCountObservations):
        raise ValueError("observations must be a WeeklyCountObservations value")
    step = _finite_number(max_step, "max_step")
    if step <= 0.0:
        raise ValueError("max_step must be positive")
    if isinstance(max_steps_per_interval, bool) or not isinstance(max_steps_per_interval, int):
        raise ValueError("max_steps_per_interval must be a positive integer")
    if max_steps_per_interval < 1:
        raise ValueError("max_steps_per_interval must be a positive integer")
    required_steps = 1.0 / step
    if not math.isfinite(required_steps) or required_steps > max_steps_per_interval:
        raise ValueError("weekly integration exceeds max_steps_per_interval")
    steps_per_week = max(1, math.ceil(required_steps))
    if steps_per_week > max_steps_per_interval:
        raise ValueError("weekly integration exceeds max_steps_per_interval")
    if len(observations.counts) * steps_per_week > _MAX_TOTAL_RK4_STEPS:
        raise ValueError("weekly integration exceeds the total RK4 step budget")

    observed_total = sum(observations.counts)
    if observed_total > THESIS_SIR_POPULATION:
        raise ValueError("observed total exceeds the no-reinfection population bound")
    q_min = observed_total / THESIS_SIR_POPULATION
    if parameters.ascertainment_fraction < q_min:
        raise ValueError("ascertainment_fraction is below sum(observed counts)/population")

    susceptible, infectious, recovered = parameters.initial_state()
    initial_state = (susceptible, infectious, recovered)
    boundary_states = [initial_state]
    shift_weeks = parameters.delay_days / 7.0
    starts: list[float] = []
    ends: list[float] = []
    means: list[float] = []

    def rhs(time: float, state: tuple[float, ...], _parameters: Mapping[str, float]):
        if len(state) != 4:
            raise ValueError("thesis SIR incidence state must have four components")
        s, i, r, cumulative_incidence = state
        if min(s, i, r, cumulative_incidence) < 0.0:
            raise ValueError("RK4 intermediate state left the nonnegative SIR region; reduce max_step")
        derivative = parameters.derivative(time, (s, i, r))
        infection_flow = -derivative[0]
        return (*derivative, infection_flow)

    state = initial_state
    for index in range(len(observations.counts)):
        start = index - shift_weeks
        end = start + 1.0
        starts.append(start)
        ends.append(end)
        problem = OdeProblem(
            rhs=rhs,
            t_span=(start, end),
            initial_state=(*state, 0.0),
            parameters={},
            state_names=("S", "I", "R", "cumulative_incidence"),
        )
        solution = solve_rk4(problem, step, max_steps=max_steps_per_interval)
        for current in solution.states:
            if min(current) < 0.0:
                raise ValueError("RK4 produced a negative SIR/incidence state; reduce max_step")
            population = math.fsum(current[:3])
            if abs(population - THESIS_SIR_POPULATION) > _CONSERVATION_TOLERANCE:
                raise ValueError("RK4 step violated fixed-population conservation")
        final = solution.states[-1]
        predicted_mean = parameters.ascertainment_fraction * final[3]
        if not math.isfinite(predicted_mean) or predicted_mean < 0.0:
            raise ValueError("weekly incidence mean is outside the finite nonnegative range")
        state = (final[0], final[1], final[2])
        boundary_states.append(state)
        means.append(predicted_mean)

    return WeeklyIncidenceResult(
        week_labels=observations.week_labels,
        observed_counts=observations.counts,
        predicted_means=tuple(means),
        interval_starts=tuple(starts),
        interval_ends=tuple(ends),
        states_at_boundaries=tuple(boundary_states),
        parameters=parameters,
        series_id=observations.series_id,
        source_sha256=observations.source_sha256,
        max_step=step,
        max_steps_per_interval=max_steps_per_interval,
    )
