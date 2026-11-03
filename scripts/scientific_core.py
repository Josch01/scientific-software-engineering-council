"""Small dependency-free numerical primitives for SSEC scientific projects.

The RK4 implementation is fixed-step and intended for transparent, bounded
initial-value simulations. It does not estimate error or certify a model.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import math
from types import MappingProxyType


State = tuple[float, ...]
RightHandSide = Callable[[float, State, Mapping[str, float]], Sequence[float]]
_DEFAULT_MAX_STEPS = 1_000_000
_DEFAULT_MAX_TOTAL_SENSITIVITY_STEPS = 1_000_000
_MAX_SENSITIVITY_PARAMETERS = 100
_MAX_SENSITIVITY_VALUES = 1_000_000
_DEFAULT_MAX_FIT_ITERATIONS = 100
_DEFAULT_MAX_FIT_EVALUATIONS = 10_000
_MAX_FIT_PARAMETERS = 100
_MAX_FIT_JACOBIAN_VALUES = 1_000_000
_DEFAULT_MAX_TOTAL_OBSERVATION_STEPS = 1_000_000
_MAX_OBSERVATION_ROWS = 100_000
_MAX_OBSERVATION_VARIABLES = 100
_MAX_OBSERVATION_VALUES = 1_000_000
_MAX_OBSERVATION_PROVENANCE_FIELDS = 100
_MAX_OBSERVATION_TEXT_LENGTH = 4096
_SIR_STATE_NAMES = ("S", "I", "R")
_SIR_EQUATION_SET = "sir_frequency_dependent_v1"
_SIR_EQUATIONS = {
    "dS/dt": "-beta(t) * S * I / N",
    "dI/dt": "beta(t) * S * I / N - gamma(t) * I",
    "dR/dt": "gamma(t) * I",
}
_MAX_SIR_CONTRACT_BYTES = 1_048_576
_MAX_SIR_PROFILE_POINTS = 128
_MAX_SIR_STEPS = 99_999


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, (str, bytes, bytearray, bool)):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _observation_text(
    value: object, label: str, *, max_length: int = _MAX_OBSERVATION_TEXT_LENGTH
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > max_length:
        raise ValueError(f"{label} exceeds the {max_length}-character limit")
    return value


def _observation_payload(
    time_unit: str,
    variable_units: Mapping[str, str],
    times: Sequence[float],
    values: Sequence[Mapping[str, float]],
    provenance: Mapping[str, str],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "time_unit": time_unit,
        "variables": [
            {"name": name, "unit": unit}
            for name, unit in variable_units.items()
        ],
        "observations": [
            {"time": time, "values": dict(row)}
            for time, row in zip(times, values)
        ],
        "provenance": dict(provenance),
    }


def _observation_digest(payload: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"observation dataset cannot be canonically encoded: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()


def _finite_vector(
    values: Sequence[float], label: str, expected_length: int | None = None
) -> State:
    if isinstance(values, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a numeric sequence, not text")
    try:
        raw_values = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{label} must be a finite numeric sequence") from exc
    if expected_length is not None and len(raw_values) != expected_length:
        raise ValueError(
            f"{label} dimension mismatch: expected {expected_length}, got {len(raw_values)}"
        )
    return tuple(_finite_float(value, f"{label}[{index}]") for index, value in enumerate(raw_values))


def _sir_text(value: object, label: str, *, maximum: int = 64) -> str:
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or len(value) > maximum):
        raise ValueError(f"{label} must be a non-empty trimmed string of at most {maximum} characters")
    return value


def _sir_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_sir_json_constant(token: str) -> object:
    raise ValueError(f"non-standard JSON constant {token!r} is not allowed")


@dataclass(frozen=True, slots=True)
class TimeFunction:
    """An explicitly admitted nonnegative coefficient profile."""

    kind: str
    value: float | None = None
    points: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        if self.kind == "constant":
            if self.points:
                raise ValueError("constant time function cannot contain points")
            if self.value is None:
                raise ValueError("constant time function requires a value")
            value = _finite_float(self.value, "constant coefficient")
            if value < 0.0:
                raise ValueError("coefficient values must be nonnegative")
            object.__setattr__(self, "value", value)
            return
        if self.kind != "piecewise_linear":
            raise ValueError("time function kind must be 'constant' or 'piecewise_linear'")
        if self.value is not None:
            raise ValueError("piecewise_linear time function cannot contain a constant value")
        if not isinstance(self.points, (tuple, list)) or not 2 <= len(self.points) <= _MAX_SIR_PROFILE_POINTS:
            raise ValueError(
                f"piecewise_linear points must contain 2 to {_MAX_SIR_PROFILE_POINTS} entries"
            )
        normalized: list[tuple[float, float]] = []
        previous_time: float | None = None
        for index, point in enumerate(self.points):
            if not isinstance(point, (tuple, list)) or len(point) != 2:
                raise ValueError(f"points[{index}] must contain exactly time and value")
            time = _finite_float(point[0], f"points[{index}].time")
            value = _finite_float(point[1], f"points[{index}].value")
            if value < 0.0:
                raise ValueError("coefficient values must be nonnegative")
            if previous_time is not None and time <= previous_time:
                raise ValueError("piecewise_linear point times must be strictly increasing")
            previous_time = time
            normalized.append((time, value))
        object.__setattr__(self, "points", tuple(normalized))

    @classmethod
    def from_dict(
        cls, payload: object, *, t_span: tuple[float, float]
    ) -> "TimeFunction":
        if not isinstance(payload, Mapping) or "kind" not in payload:
            raise ValueError("time function must be an object with a declared kind")
        kind = payload["kind"]
        if kind == "constant":
            if set(payload) != {"kind", "value"}:
                raise ValueError("constant time function requires exactly kind and value")
            return cls(kind="constant", value=payload["value"])
        if kind != "piecewise_linear":
            raise ValueError("time function kind must be 'constant' or 'piecewise_linear'")
        if set(payload) != {"kind", "points"}:
            raise ValueError("piecewise_linear time function requires exactly kind and points")
        raw_points = payload["points"]
        if (not isinstance(raw_points, Sequence)
                or isinstance(raw_points, (str, bytes, bytearray))):
            raise ValueError("piecewise_linear points must be a sequence")
        if not 2 <= len(raw_points) <= _MAX_SIR_PROFILE_POINTS:
            raise ValueError(
                f"piecewise_linear points must contain 2 to {_MAX_SIR_PROFILE_POINTS} entries"
            )
        profile = cls(kind="piecewise_linear", points=tuple(raw_points))
        if profile.points[0][0] != t_span[0] or profile.points[-1][0] != t_span[1]:
            raise ValueError("piecewise_linear points must cover both t_span endpoints")
        return profile

    def evaluate(self, time: float) -> float:
        time_value = _finite_float(time, "time function evaluation time")
        if self.kind == "constant":
            assert self.value is not None
            return self.value
        if time_value < self.points[0][0] or time_value > self.points[-1][0]:
            raise ValueError("piecewise_linear evaluation time is outside its declared interval")
        for (left_time, left_value), (right_time, right_value) in zip(
            self.points, self.points[1:]
        ):
            if time_value <= right_time:
                fraction = (time_value - left_time) / (right_time - left_time)
                return left_value + fraction * (right_value - left_value)
        return self.points[-1][1]

    def to_dict(self) -> dict[str, object]:
        if self.kind == "constant":
            return {"kind": self.kind, "value": self.value}
        return {"kind": self.kind, "points": [list(point) for point in self.points]}


@dataclass(frozen=True, slots=True)
class SirModelDefinition:
    """Closed, versioned frequency-dependent SIR contract; no user expressions."""

    t_span: tuple[float, float]
    initial_state: tuple[float, float, float]
    parameters: Mapping[str, TimeFunction]
    time_unit: str
    population_unit: str
    rate_unit: str
    max_step: float
    max_steps: int
    equation_set: str = _SIR_EQUATION_SET

    def __post_init__(self) -> None:
        if self.equation_set != _SIR_EQUATION_SET:
            raise ValueError(f"unsupported SIR equation_set {self.equation_set!r}")
        interval = _finite_vector(self.t_span, "t_span", expected_length=2)
        if interval[1] <= interval[0]:
            raise ValueError("t_span must be a finite forward interval with t1 > t0")
        object.__setattr__(self, "t_span", (interval[0], interval[1]))

        initial = _finite_vector(self.initial_state, "initial_conditions", expected_length=3)
        if any(value < 0.0 for value in initial):
            raise ValueError("SIR initial conditions must be nonnegative")
        try:
            population = math.fsum(initial)
        except (OverflowError, ValueError) as exc:
            raise ValueError("SIR initial population must be finite and positive") from exc
        if not math.isfinite(population) or population <= 0.0:
            raise ValueError("SIR initial population must be finite and positive")
        object.__setattr__(self, "initial_state", initial)

        if not isinstance(self.parameters, Mapping) or set(self.parameters) != {"beta", "gamma"}:
            raise ValueError("SIR parameters must contain exactly beta and gamma")
        profiles: dict[str, TimeFunction] = {}
        for name in ("beta", "gamma"):
            profile = self.parameters[name]
            if not isinstance(profile, TimeFunction):
                raise ValueError(f"SIR parameter {name!r} must be a TimeFunction")
            if profile.kind == "piecewise_linear" and (
                profile.points[0][0] != interval[0] or profile.points[-1][0] != interval[1]
            ):
                raise ValueError(f"SIR parameter {name!r} must cover both t_span endpoints")
            profiles[name] = profile
        object.__setattr__(self, "parameters", MappingProxyType(profiles))

        time_unit = _sir_text(self.time_unit, "units.time")
        population_unit = _sir_text(self.population_unit, "units.population")
        rate_unit = _sir_text(self.rate_unit, "units.rate")
        if rate_unit != f"1/{time_unit}":
            raise ValueError("units.rate must equal 1/<units.time>")
        object.__setattr__(self, "time_unit", time_unit)
        object.__setattr__(self, "population_unit", population_unit)
        object.__setattr__(self, "rate_unit", rate_unit)

        max_step = _finite_float(self.max_step, "integrator.max_step")
        if max_step <= 0.0:
            raise ValueError("integrator.max_step must be positive")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= _MAX_SIR_STEPS:
            raise ValueError(f"integrator.max_steps must be from 1 to {_MAX_SIR_STEPS}")
        needed = (interval[1] - interval[0]) / max_step
        if not math.isfinite(needed) or math.ceil(needed) > self.max_steps:
            raise ValueError("SIR integration exceeds the declared step budget")
        step_count = max(1, math.ceil(needed))
        actual_step = (interval[1] - interval[0]) / step_count
        for profile in profiles.values():
            if profile.kind != "piecewise_linear":
                continue
            for knot_time, _knot_value in profile.points:
                grid_index = round((knot_time - interval[0]) / actual_step)
                if not 0 <= grid_index <= step_count:
                    raise ValueError("piecewise_linear knot must align with the RK4 time grid")
                grid_time = interval[0] + grid_index * actual_step
                tolerance = max(
                    math.ulp(knot_time), math.ulp(grid_time), abs(actual_step) * 1e-12
                )
                if abs(knot_time - grid_time) > tolerance:
                    raise ValueError("piecewise_linear knot must align with the RK4 time grid")
        object.__setattr__(self, "max_step", max_step)

    @property
    def state_names(self) -> tuple[str, str, str]:
        return _SIR_STATE_NAMES

    @property
    def initial_population(self) -> float:
        return math.fsum(self.initial_state)

    @classmethod
    def from_json(cls, payload: bytes | str) -> "SirModelDefinition":
        """Parse a bounded UTF-8 JSON contract with duplicate keys rejected."""
        if isinstance(payload, bytes):
            raw_bytes = payload
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("SIR model JSON must be valid UTF-8") from exc
        elif isinstance(payload, str):
            text = payload
            try:
                raw_bytes = text.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("SIR model JSON must be valid UTF-8") from exc
        else:
            raise ValueError("SIR model JSON must be bytes or text")
        if len(raw_bytes) > _MAX_SIR_CONTRACT_BYTES:
            raise ValueError(
                f"SIR model JSON exceeds the {_MAX_SIR_CONTRACT_BYTES}-byte limit"
            )
        try:
            parsed = json.loads(
                text,
                object_pairs_hook=_sir_json_object,
                parse_constant=_reject_sir_json_constant,
            )
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValueError(f"invalid SIR model JSON: {exc}") from exc
        return cls.from_dict(parsed)

    @classmethod
    def from_dict(cls, payload: object) -> "SirModelDefinition":
        required = {
            "schema_version", "model_type", "equation_set", "equations", "states",
            "initial_conditions", "parameters", "t_span", "units", "integrator",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("SIR model contract has missing or unknown fields")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("unsupported SIR model schema_version; expected 1")
        if payload["model_type"] != "sir":
            raise ValueError("model_type must be 'sir'")
        if payload["equation_set"] != _SIR_EQUATION_SET:
            raise ValueError(f"unsupported SIR equation_set; expected {_SIR_EQUATION_SET!r}")
        equations = payload["equations"]
        if not isinstance(equations, Mapping) or dict(equations) != _SIR_EQUATIONS:
            raise ValueError("equations must exactly match the declared SIR equation_set")
        states = payload["states"]
        if (not isinstance(states, Sequence) or isinstance(states, (str, bytes, bytearray))
                or len(states) != len(_SIR_STATE_NAMES)
                or tuple(states) != _SIR_STATE_NAMES):
            raise ValueError("states must be exactly ['S', 'I', 'R'] in that order")

        initial = payload["initial_conditions"]
        if not isinstance(initial, Mapping) or set(initial) != set(_SIR_STATE_NAMES):
            raise ValueError("initial_conditions must contain exactly S, I, and R")
        initial_state = tuple(
            _finite_float(initial[name], f"initial_conditions.{name}")
            for name in _SIR_STATE_NAMES
        )
        raw_interval = payload["t_span"]
        if (not isinstance(raw_interval, Sequence)
                or isinstance(raw_interval, (str, bytes, bytearray))
                or len(raw_interval) != 2):
            raise ValueError("t_span dimension mismatch: expected 2 values")
        interval = _finite_vector(raw_interval, "t_span", expected_length=2)
        if interval[1] <= interval[0]:
            raise ValueError("t_span must be a finite forward interval with t1 > t0")

        parameters = payload["parameters"]
        if not isinstance(parameters, Mapping) or set(parameters) != {"beta", "gamma"}:
            raise ValueError("SIR parameters must contain exactly beta and gamma")
        profiles = {
            name: TimeFunction.from_dict(parameters[name], t_span=interval)
            for name in ("beta", "gamma")
        }
        units = payload["units"]
        if not isinstance(units, Mapping) or set(units) != {"time", "population", "rate"}:
            raise ValueError("units must contain exactly time, population, and rate")
        integrator = payload["integrator"]
        if (not isinstance(integrator, Mapping)
                or set(integrator) != {"method", "max_step", "max_steps"}):
            raise ValueError("integrator must contain exactly method, max_step, and max_steps")
        if integrator["method"] != "RK4_FIXED_STEP":
            raise ValueError("integrator.method must be 'RK4_FIXED_STEP'")
        return cls(
            t_span=interval,
            initial_state=initial_state,
            parameters=profiles,
            time_unit=units["time"],
            population_unit=units["population"],
            rate_unit=units["rate"],
            max_step=integrator["max_step"],
            max_steps=integrator["max_steps"],
            equation_set=payload["equation_set"],
        )

    def rhs(
        self, time: float, state: State, _parameters: Mapping[str, float]
    ) -> State:
        time_value = _finite_float(time, "SIR evaluation time")
        if time_value < self.t_span[0] or time_value > self.t_span[1]:
            raise ValueError("SIR evaluation time is outside t_span")
        state_values = _finite_vector(state, "SIR state", expected_length=3)
        susceptible, infectious, recovered = state_values
        beta = self.parameters["beta"].evaluate(time_value)
        gamma = self.parameters["gamma"].evaluate(time_value)
        incidence = beta * susceptible * infectious / self.initial_population
        removal = gamma * infectious
        derivative = (-incidence, incidence - removal, removal)
        return _finite_vector(derivative, "SIR derivative", expected_length=3)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "model_type": "sir",
            "equation_set": self.equation_set,
            "equations": dict(_SIR_EQUATIONS),
            "states": list(_SIR_STATE_NAMES),
            "initial_conditions": dict(zip(_SIR_STATE_NAMES, self.initial_state)),
            "parameters": {name: profile.to_dict() for name, profile in self.parameters.items()},
            "t_span": list(self.t_span),
            "units": {
                "time": self.time_unit,
                "population": self.population_unit,
                "rate": self.rate_unit,
            },
            "integrator": {
                "method": "RK4_FIXED_STEP",
                "max_step": self.max_step,
                "max_steps": self.max_steps,
            },
        }


@dataclass(frozen=True, slots=True)
class OdeProblem:
    """A first-order ODE initial-value problem with explicit numeric inputs."""

    rhs: RightHandSide
    t_span: tuple[float, float]
    initial_state: State
    parameters: Mapping[str, float] = field(default_factory=dict)
    state_names: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not callable(self.rhs):
            raise ValueError("rhs must be callable")

        interval = _finite_vector(self.t_span, "t_span", expected_length=2)
        if interval[1] <= interval[0]:
            raise ValueError("t_span must be a finite forward interval with t1 > t0")
        object.__setattr__(self, "t_span", (interval[0], interval[1]))

        state = _finite_vector(self.initial_state, "initial_state")
        if not state:
            raise ValueError("initial_state must contain at least one value")
        object.__setattr__(self, "initial_state", state)

        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters must be a mapping of names to finite numbers")
        parameters: dict[str, float] = {}
        for name, value in self.parameters.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("parameter names must be non-empty strings")
            parameters[name] = _finite_float(value, f"parameters[{name!r}]")
        object.__setattr__(self, "parameters", MappingProxyType(parameters))

        if self.state_names is None:
            names = tuple(f"state_{index}" for index in range(len(state)))
        else:
            if isinstance(self.state_names, (str, bytes, bytearray)):
                raise ValueError("state_names must be a sequence of labels, not text")
            try:
                names = tuple(self.state_names)
            except TypeError as exc:
                raise ValueError("state_names must be a sequence of labels") from exc
            if len(names) != len(state):
                raise ValueError("state_names dimension must match initial_state")
            if any(not isinstance(name, str) or not name.strip() for name in names):
                raise ValueError("state names must be non-empty strings")
            if len(set(names)) != len(names):
                raise ValueError("state names must be unique")
        object.__setattr__(self, "state_names", names)


@dataclass(frozen=True, slots=True)
class OdeSolution:
    """Uniform time/state series and solver inputs for reproducible consumers."""

    times: tuple[float, ...]
    states: tuple[State, ...]
    state_names: tuple[str, ...]
    parameters: Mapping[str, float]
    method: str
    requested_max_step: float
    step_size: float
    step_count: int

    def to_dict(self) -> dict[str, object]:
        """Return a versioned JSON-safe result contract for workspace tools."""
        return {
            "schema_version": 1,
            "method": self.method,
            "times": list(self.times),
            "state_names": list(self.state_names),
            "values": [list(state) for state in self.states],
            "parameters": dict(self.parameters),
            "requested_max_step": self.requested_max_step,
            "actual_step_size": self.step_size,
            "step_count": self.step_count,
        }


@dataclass(frozen=True, slots=True, init=False)
class ObservationDataset:
    """Immutable sparse observations with explicit units and source metadata.

    Construct through ``from_dict`` so schema, bounds, and content digest are
    validated. The digest identifies normalized contract content; it does not
    authenticate the declared source.
    """

    time_unit: str
    variable_units: Mapping[str, str]
    times: tuple[float, ...]
    values: tuple[Mapping[str, float], ...]
    provenance: Mapping[str, str]
    content_sha256: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("construct ObservationDataset with from_dict()")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ObservationDataset":
        if not isinstance(payload, Mapping):
            raise ValueError("observation dataset must be a mapping")
        required = {
            "schema_version", "time_unit", "variables", "observations", "provenance"
        }
        if set(payload) not in (required, required | {"content_sha256"}):
            raise ValueError("observation dataset has missing or unknown fields")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("unsupported observation schema_version; expected 1")

        time_unit = _observation_text(payload["time_unit"], "time_unit")
        raw_variables = payload["variables"]
        if not isinstance(raw_variables, Sequence) or isinstance(
            raw_variables, (str, bytes, bytearray)
        ) or not raw_variables:
            raise ValueError("variables must be a non-empty ordered sequence of name/unit records")
        if len(raw_variables) > _MAX_OBSERVATION_VARIABLES:
            raise ValueError(
                f"variables exceed the {_MAX_OBSERVATION_VARIABLES}-variable limit"
            )
        variable_units: dict[str, str] = {}
        for variable_index, raw_variable in enumerate(raw_variables):
            if not isinstance(raw_variable, Mapping) or set(raw_variable) != {"name", "unit"}:
                raise ValueError(
                    f"variables[{variable_index}] must contain exactly name and unit"
                )
            name = _observation_text(
                raw_variable["name"], "variable name", max_length=256
            )
            if name != name.strip():
                raise ValueError("variable names cannot have surrounding whitespace")
            if name in variable_units:
                raise ValueError(f"duplicate variable name {name!r}")
            variable_units[name] = _observation_text(
                raw_variable["unit"], f"unit for variable {name!r}", max_length=256
            )

        raw_rows = payload["observations"]
        if not isinstance(raw_rows, Sequence) or isinstance(
            raw_rows, (str, bytes, bytearray)
        ) or not raw_rows:
            raise ValueError("observations must be a non-empty sequence")
        if len(raw_rows) > _MAX_OBSERVATION_ROWS:
            raise ValueError(
                f"observations exceed the {_MAX_OBSERVATION_ROWS}-row limit"
            )
        times: list[float] = []
        value_rows: list[Mapping[str, float]] = []
        value_count = 0
        previous_time: float | None = None
        for row_index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, Mapping) or set(raw_row) != {"time", "values"}:
                raise ValueError(
                    f"observations[{row_index}] must contain exactly time and values"
                )
            time = _finite_float(raw_row["time"], f"observations[{row_index}].time")
            if previous_time is not None and time <= previous_time:
                raise ValueError("observation times must be strictly increasing")
            previous_time = time
            raw_values = raw_row["values"]
            if not isinstance(raw_values, Mapping) or not raw_values:
                raise ValueError(
                    f"observations[{row_index}] must contain at least one measured variable"
                )
            unknown = set(raw_values) - set(variable_units)
            if unknown:
                raise ValueError(
                    f"observations[{row_index}] contains unknown variable(s): "
                    f"{sorted(map(str, unknown))}"
                )
            row_values: dict[str, float] = {}
            for name in variable_units:
                if name in raw_values:
                    row_values[name] = _finite_float(
                        raw_values[name],
                        f"observations[{row_index}].values[{name!r}]",
                    )
            value_count += len(row_values)
            if value_count > _MAX_OBSERVATION_VALUES:
                raise ValueError(
                    "observations exceed the "
                    f"{_MAX_OBSERVATION_VALUES}-value limit"
                )
            times.append(time)
            value_rows.append(MappingProxyType(row_values))

        raw_provenance = payload["provenance"]
        if not isinstance(raw_provenance, Mapping) or not raw_provenance:
            raise ValueError("provenance must be a non-empty mapping containing source")
        if len(raw_provenance) > _MAX_OBSERVATION_PROVENANCE_FIELDS:
            raise ValueError(
                "provenance exceeds the "
                f"{_MAX_OBSERVATION_PROVENANCE_FIELDS}-field limit"
            )
        provenance: dict[str, str] = {}
        for raw_key, raw_value in raw_provenance.items():
            key = _observation_text(raw_key, "provenance key", max_length=256)
            if key != key.strip():
                raise ValueError("provenance keys cannot have surrounding whitespace")
            provenance[key] = _observation_text(
                raw_value, f"provenance[{key!r}]"
            )
        if "source" not in provenance:
            raise ValueError("provenance must contain a non-empty source")

        canonical_payload = _observation_payload(
            time_unit, variable_units, times, value_rows, provenance
        )
        digest = _observation_digest(canonical_payload)
        if "content_sha256" in payload:
            supplied_digest = payload["content_sha256"]
            if (
                not isinstance(supplied_digest, str)
                or len(supplied_digest) != 64
                or any(character not in "0123456789abcdef" for character in supplied_digest)
            ):
                raise ValueError("content_sha256 must be a lowercase SHA-256 hex digest")
            if supplied_digest != digest:
                raise ValueError("content_sha256 does not match observation content")

        dataset = object.__new__(cls)
        object.__setattr__(dataset, "time_unit", time_unit)
        object.__setattr__(dataset, "variable_units", MappingProxyType(variable_units))
        object.__setattr__(dataset, "times", tuple(times))
        object.__setattr__(dataset, "values", tuple(value_rows))
        object.__setattr__(dataset, "provenance", MappingProxyType(provenance))
        object.__setattr__(dataset, "content_sha256", digest)
        return dataset

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(self.variable_units)

    def to_dict(self) -> dict[str, object]:
        payload = _observation_payload(
            self.time_unit,
            self.variable_units,
            self.times,
            self.values,
            self.provenance,
        )
        payload["content_sha256"] = self.content_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ObservationEvaluation:
    """RK4 model values and ordered residuals at observation times."""

    observation_sha256: str
    provenance: Mapping[str, str]
    time_unit: str
    variable_units: Mapping[str, str]
    times: tuple[float, ...]
    observed_values: tuple[Mapping[str, float], ...]
    simulated_values: tuple[Mapping[str, float], ...]
    residual_order: tuple[tuple[float, str], ...]
    residuals: tuple[float, ...]
    model_time_unit: str
    model_variable_units: Mapping[str, str]
    model_parameters: Mapping[str, float]
    model_state_names: tuple[str, ...]
    model_initial_state: State
    requested_max_step: float
    segment_step_sizes: tuple[float | None, ...]
    segment_step_counts: tuple[int, ...]
    total_step_count: int
    max_steps_per_interval: int
    max_total_steps: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe, provenance-linked evaluation record."""
        return {
            "schema_version": 1,
            "method": "SEGMENTED_FIXED_STEP_RK4_AT_OBSERVATION_TIMES",
            "observation_sha256": self.observation_sha256,
            "provenance": dict(self.provenance),
            "time_unit": self.time_unit,
            "variable_units": dict(self.variable_units),
            "times": list(self.times),
            "observed_values": [dict(row) for row in self.observed_values],
            "simulated_values": [dict(row) for row in self.simulated_values],
            "residual_order": [
                {"time": time, "variable": name}
                for time, name in self.residual_order
            ],
            "residuals": list(self.residuals),
            "model": {
                "time_unit": self.model_time_unit,
                "variable_units": dict(self.model_variable_units),
                "parameters": dict(self.model_parameters),
                "state_names": list(self.model_state_names),
                "initial_state": list(self.model_initial_state),
            },
            "solver": {
                "requested_max_step": self.requested_max_step,
                "segment_step_sizes": list(self.segment_step_sizes),
                "segment_step_counts": list(self.segment_step_counts),
                "total_step_count": self.total_step_count,
                "rhs_evaluation_count": 4 * self.total_step_count,
                "max_steps_per_interval": self.max_steps_per_interval,
                "max_total_steps": self.max_total_steps,
            },
        }


@dataclass(frozen=True, slots=True)
class OdeSensitivity:
    """Central finite-difference sensitivities of an RK4 trajectory.

    ``values`` is indexed as [time][state][parameter]. Sensitivities hold the
    initial state fixed and correspond to the discretized RK4 trajectories.
    """

    base_solution: OdeSolution
    parameter_names: tuple[str, ...]
    perturbations: Mapping[str, float]
    parameter_bounds: Mapping[str, tuple[float, float]]
    values: tuple[tuple[tuple[float, ...], ...], ...]
    total_step_count: int

    @property
    def times(self) -> tuple[float, ...]:
        return self.base_solution.times

    @property
    def state_names(self) -> tuple[str, ...]:
        return self.base_solution.state_names

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe result with explicit axes, perturbations, and work."""
        return {
            "schema_version": 1,
            "method": "CENTRAL_FINITE_DIFFERENCE",
            "solver_method": self.base_solution.method,
            "times": list(self.times),
            "state_names": list(self.state_names),
            "parameter_names": list(self.parameter_names),
            "base_parameters": dict(self.base_solution.parameters),
            "base_values": [list(state) for state in self.base_solution.states],
            "perturbations": dict(self.perturbations),
            "parameter_bounds": {
                name: {"lower": bounds[0], "upper": bounds[1]}
                for name, bounds in self.parameter_bounds.items()
            },
            "values": [
                [list(state_sensitivities) for state_sensitivities in time_sensitivities]
                for time_sensitivities in self.values
            ],
            "requested_max_step": self.base_solution.requested_max_step,
            "actual_step_size": self.base_solution.step_size,
            "step_count_per_trajectory": self.base_solution.step_count,
            "trajectory_count": 1 + 2 * len(self.parameter_names),
            "total_step_count": self.total_step_count,
            "rhs_evaluation_count": 4 * self.total_step_count,
        }


@dataclass(frozen=True, slots=True)
class LeastSquaresFit:
    """Bounded local least-squares result; convergence is not identifiability."""

    parameter_names: tuple[str, ...]
    initial_parameters: Mapping[str, float]
    parameters: Mapping[str, float]
    bounds: Mapping[str, tuple[float, float]]
    residuals: tuple[float, ...]
    cost: float
    cost_underflowed: bool
    status: str
    iterations: int
    accepted_steps: int
    function_evaluations: int
    max_iterations: int
    max_function_evaluations: int
    finite_difference_fraction: float
    final_damping: float

    def to_dict(self) -> dict[str, object]:
        """Return a versioned JSON-safe fit record with explicit work/status."""
        return {
            "schema_version": 1,
            "method": "BOUNDED_LEVENBERG_MARQUARDT",
            "parameter_names": list(self.parameter_names),
            "initial_parameters": dict(self.initial_parameters),
            "parameters": dict(self.parameters),
            "bounds": {
                name: {"lower": lower, "upper": upper}
                for name, (lower, upper) in self.bounds.items()
            },
            "residuals": list(self.residuals),
            "cost": self.cost,
            "cost_underflowed": self.cost_underflowed,
            "status": self.status,
            "iterations": self.iterations,
            "accepted_steps": self.accepted_steps,
            "function_evaluations": self.function_evaluations,
            "max_iterations": self.max_iterations,
            "max_function_evaluations": self.max_function_evaluations,
            "finite_difference_fraction": self.finite_difference_fraction,
            "final_damping": self.final_damping,
        }


def _evaluate(problem: OdeProblem, time: float, state: State) -> State:
    derivative = problem.rhs(time, state, problem.parameters)
    return _finite_vector(
        derivative, f"rhs result at t={time!r}", expected_length=len(state)
    )


def _shift_state(state: State, derivative: State, scale: float) -> State:
    return _finite_vector(
        tuple(value + scale * rate for value, rate in zip(state, derivative)),
        "intermediate state",
        expected_length=len(state),
    )


def _scaled_product(first: float, second: float, third: float) -> float:
    """Multiply finite factors without avoidable intermediate range loss."""
    if first == 0.0 or second == 0.0 or third == 0.0:
        return 0.0
    first_mantissa, first_exponent = math.frexp(first)
    second_mantissa, second_exponent = math.frexp(second)
    third_mantissa, third_exponent = math.frexp(third)
    mantissa = first_mantissa * second_mantissa * third_mantissa
    try:
        return math.ldexp(
            mantissa, first_exponent + second_exponent + third_exponent
        )
    except OverflowError:
        return math.copysign(math.inf, mantissa)


def _rk4_increment(
    step_size: float, derivatives: tuple[State, ...], index: int
) -> float:
    rates = tuple(derivative[index] for derivative in derivatives)
    scale = max(abs(rate) for rate in rates)
    if scale == 0.0:
        return 0.0
    normalized_rate = math.fsum(
        (
            rates[0] / scale / 6.0,
            rates[1] / scale / 3.0,
            rates[2] / scale / 3.0,
            rates[3] / scale / 6.0,
        )
    )
    return _scaled_product(step_size, scale, normalized_rate)


def solve_rk4(
    problem: OdeProblem,
    max_step: float,
    *,
    max_steps: int = _DEFAULT_MAX_STEPS,
) -> OdeSolution:
    """Integrate ``problem`` with classical fixed-step fourth-order Runge–Kutta.

    The requested maximum step is honored by choosing an integer number of
    equal substeps. No interpolation, local-error estimate, or model-specific
    invariant/positivity check is performed.
    """
    if not isinstance(problem, OdeProblem):
        raise ValueError("problem must be an OdeProblem")
    requested_step = _finite_float(max_step, "max_step")
    if requested_step <= 0.0:
        raise ValueError("max_step must be positive and finite")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")

    start, end = problem.t_span
    span = end - start
    required_steps = span / requested_step
    if not math.isfinite(required_steps) or required_steps > max_steps:
        raise ValueError(f"required step count exceeds max_steps={max_steps}")
    step_count = max(1, math.ceil(required_steps))
    if step_count > max_steps:
        raise ValueError(f"required step count exceeds max_steps={max_steps}")
    step_size = span / step_count
    if not math.isfinite(step_size) or step_size <= 0.0:
        raise ValueError("time interval is too small for a representable step")

    times = [start]
    states = [problem.initial_state]
    state = problem.initial_state

    for index in range(step_count):
        time = start + index * step_size
        next_time = end if index + 1 == step_count else start + (index + 1) * step_size
        midpoint = time + 0.5 * step_size

        k1 = _evaluate(problem, time, state)
        k2 = _evaluate(problem, midpoint, _shift_state(state, k1, 0.5 * step_size))
        k3 = _evaluate(problem, midpoint, _shift_state(state, k2, 0.5 * step_size))
        k4 = _evaluate(problem, next_time, _shift_state(state, k3, step_size))

        state = _finite_vector(
            tuple(
                value + _rk4_increment(step_size, (k1, k2, k3, k4), component)
                for component, value in enumerate(state)
            ),
            f"state after step {index + 1}",
            expected_length=len(problem.initial_state),
        )
        if next_time <= times[-1]:
            raise ValueError("time interval is too small to represent a strictly increasing grid")
        times.append(next_time)
        states.append(state)

    return OdeSolution(
        times=tuple(times),
        states=tuple(states),
        state_names=problem.state_names or (),
        parameters=MappingProxyType(dict(problem.parameters)),
        method="RK4_FIXED_STEP",
        requested_max_step=requested_step,
        step_size=step_size,
        step_count=step_count,
    )


def solve_sir_model(definition: SirModelDefinition) -> OdeSolution:
    """Run the validated SIR contract with the existing RK4 solver.

    The exact SIR invariants are checked after integration. Invalid numerical
    output is rejected; compartments are never clipped or projected.
    """
    if not isinstance(definition, SirModelDefinition):
        raise ValueError("definition must be a validated SirModelDefinition")
    problem = OdeProblem(
        rhs=definition.rhs,
        t_span=definition.t_span,
        initial_state=definition.initial_state,
        parameters={},
        state_names=definition.state_names,
    )
    solution = solve_rk4(
        problem,
        max_step=definition.max_step,
        max_steps=definition.max_steps,
    )
    population = definition.initial_population
    population_tolerance = max(1e-12, population * 1e-9)
    for index, state in enumerate(solution.states):
        if any(value < 0.0 for value in state):
            raise ValueError(
                f"RK4 produced a negative compartment at step {index}; reduce max_step"
            )
        try:
            state_population = math.fsum(state)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"SIR population invariant failed at step {index}") from exc
        if (not math.isfinite(state_population)
                or abs(state_population - population) > population_tolerance):
            raise ValueError(f"SIR population invariant drift exceeded tolerance at step {index}")
    return solution


def evaluate_observations(
    problem: OdeProblem,
    dataset: ObservationDataset,
    *,
    model_time_unit: str,
    model_variable_units: Mapping[str, str],
    max_step: float,
    max_steps_per_interval: int = _DEFAULT_MAX_STEPS,
    max_total_steps: int = _DEFAULT_MAX_TOTAL_OBSERVATION_STEPS,
) -> ObservationEvaluation:
    """Integrate to exact observation times and build ordered residuals.

    Each interval between observations is integrated with fixed-step RK4. No
    interpolation, unit conversion, or missing-value imputation is performed.
    Work budgets and unit/name compatibility are checked before any RHS call.
    Residuals are raw, unweighted ``simulated - observed`` differences in time
    order, then dataset variable order. The tuple can be passed to
    :func:`fit_least_squares`, but callers must scale or weight variables with
    unlike units before interpreting their joint squared-error objective.
    """
    if not isinstance(problem, OdeProblem):
        raise ValueError("problem must be an OdeProblem")
    if not isinstance(dataset, ObservationDataset):
        raise ValueError("dataset must be an ObservationDataset")
    time_unit = _observation_text(model_time_unit, "model_time_unit")
    if time_unit != dataset.time_unit:
        raise ValueError(
            f"model time unit {time_unit!r} does not match observation time unit "
            f"{dataset.time_unit!r}"
        )
    if not isinstance(model_variable_units, Mapping):
        raise ValueError("model_variable_units must map state names to units")
    normalized_model_units: dict[str, str] = {}
    for raw_name, raw_unit in model_variable_units.items():
        name = _observation_text(raw_name, "model state name", max_length=256)
        normalized_model_units[name] = _observation_text(
            raw_unit, f"model unit for {name!r}", max_length=256
        )

    state_indices = {
        name: index for index, name in enumerate(problem.state_names or ())
    }
    for name, unit in dataset.variable_units.items():
        if name not in state_indices or name not in normalized_model_units:
            raise ValueError(f"observation variable {name!r} is not a problem state with a declared model unit")
        if normalized_model_units[name] != unit:
            raise ValueError(
                f"unit mismatch for variable {name!r}: model has "
                f"{normalized_model_units[name]!r}, observations have {unit!r}"
            )

    requested_step = _finite_float(max_step, "max_step")
    if requested_step <= 0.0:
        raise ValueError("max_step must be positive and finite")
    if (
        isinstance(max_steps_per_interval, bool)
        or not isinstance(max_steps_per_interval, int)
        or max_steps_per_interval < 1
    ):
        raise ValueError("max_steps_per_interval must be a positive integer")
    if (
        isinstance(max_total_steps, bool)
        or not isinstance(max_total_steps, int)
        or max_total_steps < 1
    ):
        raise ValueError("max_total_steps must be a positive integer")

    start, end = problem.t_span
    current_time = start
    segment_step_counts: list[int] = []
    total_step_count = 0
    for observation_time in dataset.times:
        if observation_time < start or observation_time > end:
            raise ValueError(
                f"observation time {observation_time!r} is outside problem.t_span"
            )
        if observation_time == current_time:
            step_count = 0
        else:
            span = observation_time - current_time
            required_steps = span / requested_step
            if not math.isfinite(required_steps):
                raise ValueError("observation interval requires a non-finite step count")
            step_count = max(1, math.ceil(required_steps))
            if step_count > max_steps_per_interval:
                raise ValueError(
                    "observation interval exceeds "
                    f"max_steps_per_interval={max_steps_per_interval}"
                )
            total_step_count += step_count
            if total_step_count > max_total_steps:
                raise ValueError(
                    f"observation simulation exceeds max_total_steps={max_total_steps}"
                )
        segment_step_counts.append(step_count)
        current_time = observation_time

    current_time = start
    current_state = problem.initial_state
    segment_step_sizes: list[float | None] = []
    observed_rows: list[Mapping[str, float]] = []
    simulated_rows: list[Mapping[str, float]] = []
    residual_order: list[tuple[float, str]] = []
    residual_values: list[float] = []
    for observation_time, step_count, observed_row in zip(
        dataset.times, segment_step_counts, dataset.values
    ):
        if step_count:
            segment_problem = OdeProblem(
                rhs=problem.rhs,
                t_span=(current_time, observation_time),
                initial_state=current_state,
                parameters=problem.parameters,
                state_names=problem.state_names,
            )
            try:
                segment = solve_rk4(
                    segment_problem,
                    requested_step,
                    max_steps=max_steps_per_interval,
                )
            except Exception as exc:
                raise ValueError(
                    f"RK4 evaluation failed before observation time "
                    f"{observation_time!r}: {exc}"
                ) from exc
            current_state = segment.states[-1]
            segment_step_sizes.append(segment.step_size)
        else:
            segment_step_sizes.append(None)

        current_time = observation_time
        simulated_row = MappingProxyType(
            {
                name: current_state[state_indices[name]]
                for name in dataset.variable_units
            }
        )
        observed_rows.append(MappingProxyType(dict(observed_row)))
        simulated_rows.append(simulated_row)
        for name in dataset.variable_units:
            if name not in observed_row:
                continue
            residual = simulated_row[name] - observed_row[name]
            if not math.isfinite(residual):
                raise ValueError(
                    f"residual is not finite at time {observation_time!r} "
                    f"for variable {name!r}"
                )
            residual_order.append((observation_time, name))
            residual_values.append(residual)

    return ObservationEvaluation(
        observation_sha256=dataset.content_sha256,
        provenance=dataset.provenance,
        time_unit=dataset.time_unit,
        variable_units=dataset.variable_units,
        times=dataset.times,
        observed_values=tuple(observed_rows),
        simulated_values=tuple(simulated_rows),
        residual_order=tuple(residual_order),
        residuals=tuple(residual_values),
        model_time_unit=time_unit,
        model_variable_units=MappingProxyType(
            {name: normalized_model_units[name] for name in dataset.variable_units}
        ),
        model_parameters=problem.parameters,
        model_state_names=problem.state_names or (),
        model_initial_state=problem.initial_state,
        requested_max_step=requested_step,
        segment_step_sizes=tuple(segment_step_sizes),
        segment_step_counts=tuple(segment_step_counts),
        total_step_count=total_step_count,
        max_steps_per_interval=max_steps_per_interval,
        max_total_steps=max_total_steps,
    )


def parameter_sensitivities(
    problem: OdeProblem,
    perturbations: Mapping[str, float],
    max_step: float,
    *,
    max_steps: int = _DEFAULT_MAX_STEPS,
    max_total_steps: int = _DEFAULT_MAX_TOTAL_SENSITIVITY_STEPS,
) -> OdeSensitivity:
    """Estimate local parameter sensitivities with explicit central steps.

    Each selected parameter is perturbed by its supplied absolute amount in
    both directions. The function solves one baseline plus two trajectories
    per parameter on a shared fixed-step grid. It does not select perturbation
    sizes, check physical parameter domains, estimate derivative error, or
    establish identifiability.
    """
    if not isinstance(problem, OdeProblem):
        raise ValueError("problem must be an OdeProblem")
    if not isinstance(perturbations, Mapping) or not perturbations:
        raise ValueError("perturbations must be a non-empty mapping")
    if len(perturbations) > _MAX_SENSITIVITY_PARAMETERS:
        raise ValueError(
            f"perturbations exceed the {_MAX_SENSITIVITY_PARAMETERS}-parameter limit"
        )
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if (
        isinstance(max_total_steps, bool)
        or not isinstance(max_total_steps, int)
        or max_total_steps < 1
    ):
        raise ValueError("max_total_steps must be a positive integer")

    requested_step = _finite_float(max_step, "max_step")
    if requested_step <= 0.0:
        raise ValueError("max_step must be positive and finite")

    parameter_names: list[str] = []
    steps: dict[str, float] = {}
    bounds: dict[str, tuple[float, float]] = {}
    for name, raw_step in perturbations.items():
        if not isinstance(name, str) or not name:
            raise ValueError("perturbation parameter names must be non-empty strings")
        if name not in problem.parameters:
            raise ValueError(f"unknown sensitivity parameter {name!r}")
        step = _finite_float(raw_step, f"perturbations[{name!r}]")
        if step <= 0.0:
            raise ValueError(f"perturbation for parameter {name!r} must be positive")

        center = problem.parameters[name]
        lower = center - step
        upper = center + step
        if (
            not math.isfinite(lower)
            or not math.isfinite(upper)
            or not lower < center < upper
        ):
            raise ValueError(
                f"perturbation bounds for parameter {name!r} are not finite and distinct"
            )
        denominator = upper - lower
        if not math.isfinite(denominator) or denominator <= 0.0:
            raise ValueError(
                f"perturbation span for parameter {name!r} is not finite and positive"
            )
        parameter_names.append(name)
        steps[name] = step
        bounds[name] = (lower, upper)

    start, end = problem.t_span
    span = end - start
    required_steps = span / requested_step
    if not math.isfinite(required_steps) or required_steps > max_steps:
        raise ValueError(f"required step count exceeds max_steps={max_steps}")
    step_count = max(1, math.ceil(required_steps))
    trajectory_count = 1 + 2 * len(parameter_names)
    total_step_count = trajectory_count * step_count
    if total_step_count > max_total_steps:
        raise ValueError(
            f"sensitivity requires {total_step_count} steps, exceeds "
            f"max_total_steps={max_total_steps}"
        )
    value_slots = (
        (step_count + 1)
        * len(problem.initial_state)
        * (2 * len(parameter_names) + 3)
    )
    if value_slots > _MAX_SENSITIVITY_VALUES:
        raise ValueError(
            f"sensitivity output/intermediates exceed {_MAX_SENSITIVITY_VALUES} values"
        )

    base_solution = solve_rk4(problem, requested_step, max_steps=max_steps)
    values = [
        [[0.0 for _ in parameter_names] for _ in problem.initial_state]
        for _ in base_solution.times
    ]

    for parameter_index, name in enumerate(parameter_names):
        lower, upper = bounds[name]
        solutions: dict[str, OdeSolution] = {}
        for side, perturbed_value in (("lower", lower), ("upper", upper)):
            perturbed_parameters = dict(problem.parameters)
            perturbed_parameters[name] = perturbed_value
            try:
                perturbed_problem = OdeProblem(
                    rhs=problem.rhs,
                    t_span=problem.t_span,
                    initial_state=problem.initial_state,
                    parameters=perturbed_parameters,
                    state_names=problem.state_names,
                )
                solutions[side] = solve_rk4(
                    perturbed_problem, requested_step, max_steps=max_steps
                )
            except Exception as exc:
                raise ValueError(
                    f"sensitivity trajectory failed for parameter {name!r} "
                    f"{side} perturbation: {exc}"
                ) from exc

        denominator = upper - lower
        lower_solution = solutions["lower"]
        upper_solution = solutions["upper"]
        if (
            lower_solution.times != base_solution.times
            or upper_solution.times != base_solution.times
        ):
            raise ValueError("sensitivity trajectories produced inconsistent time grids")
        for time_index, (lower_state, upper_state) in enumerate(
            zip(lower_solution.states, upper_solution.states)
        ):
            for state_index, (lower_value, upper_value) in enumerate(
                zip(lower_state, upper_state)
            ):
                sensitivity = (upper_value - lower_value) / denominator
                if not math.isfinite(sensitivity):
                    raise ValueError(
                        f"sensitivity is not finite for parameter {name!r} "
                        f"at time index {time_index}, state {state_index}"
                    )
                values[time_index][state_index][parameter_index] = sensitivity

    frozen_values = tuple(
        tuple(tuple(state_values) for state_values in time_values)
        for time_values in values
    )
    return OdeSensitivity(
        base_solution=base_solution,
        parameter_names=tuple(parameter_names),
        perturbations=MappingProxyType(steps),
        parameter_bounds=MappingProxyType(bounds),
        values=frozen_values,
        total_step_count=total_step_count,
    )


class _FitEvaluationLimit(Exception):
    pass


def _least_squares_measure(residuals: tuple[float, ...]) -> tuple[float, float]:
    norm = 0.0
    for residual in residuals:
        norm = math.hypot(norm, residual)
    cost = 0.5 * norm * norm
    if not math.isfinite(cost):
        raise ValueError("least-squares cost is not finite")
    return norm, cost


def _solve_dense_system(
    matrix: list[list[float]], right_hand_side: list[float]
) -> list[float]:
    """Solve a small dense system by Gaussian elimination with pivoting."""
    size = len(right_hand_side)
    rows = [list(matrix_row) + [right_hand_side[index]]
            for index, matrix_row in enumerate(matrix)]
    for column in range(size):
        pivot_row = max(range(column, size), key=lambda row: abs(rows[row][column]))
        pivot = rows[pivot_row][column]
        if not math.isfinite(pivot) or pivot == 0.0:
            raise ValueError("least-squares damped system is singular")
        if pivot_row != column:
            rows[column], rows[pivot_row] = rows[pivot_row], rows[column]
        for row in range(column + 1, size):
            factor = rows[row][column] / rows[column][column]
            rows[row][column] = 0.0
            for index in range(column + 1, size + 1):
                rows[row][index] -= factor * rows[column][index]

    solution = [0.0 for _ in range(size)]
    for row in range(size - 1, -1, -1):
        tail = math.fsum(rows[row][column] * solution[column]
                         for column in range(row + 1, size))
        solution[row] = (rows[row][size] - tail) / rows[row][row]
        if not math.isfinite(solution[row]):
            raise ValueError("least-squares step is not finite")
    return solution


def fit_least_squares(
    residual_function: Callable[[Mapping[str, float]], Sequence[float]],
    initial_parameters: Mapping[str, float],
    bounds: Mapping[str, Sequence[float]],
    *,
    max_iterations: int = _DEFAULT_MAX_FIT_ITERATIONS,
    max_function_evaluations: int = _DEFAULT_MAX_FIT_EVALUATIONS,
    finite_difference_fraction: float = 1e-4,
    gradient_tolerance: float = 1e-8,
    cost_tolerance: float = 1e-10,
    step_tolerance: float = 1e-8,
) -> LeastSquaresFit:
    """Fit a bounded parameter mapping to a caller-provided residual vector.

    The local optimizer uses damped Gauss-Newton/Levenberg-Marquardt in
    locally scaled coordinates centered exactly on the supplied initial values.
    It uses central finite differences in the interior and feasible one-sided
    differences at active bounds. The callback must be deterministic; status
    ``CONVERGED`` is not an identifiability or scientific-validity result.
    """
    if not callable(residual_function):
        raise ValueError("residual_function must be callable")
    if not isinstance(initial_parameters, Mapping) or not initial_parameters:
        raise ValueError("initial_parameters must be a non-empty mapping")
    if len(initial_parameters) > _MAX_FIT_PARAMETERS:
        raise ValueError(
            f"initial_parameters exceed the {_MAX_FIT_PARAMETERS}-parameter limit"
        )
    if not isinstance(bounds, Mapping):
        raise ValueError("bounds must map every parameter name to a finite (lower, upper) pair")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations < 1
    ):
        raise ValueError("max_iterations must be a positive integer")
    if (
        isinstance(max_function_evaluations, bool)
        or not isinstance(max_function_evaluations, int)
        or max_function_evaluations < 1
    ):
        raise ValueError("max_function_evaluations must be a positive integer")

    fd_fraction = _finite_float(
        finite_difference_fraction, "finite_difference_fraction"
    )
    if not 0.0 < fd_fraction <= 0.5:
        raise ValueError("finite_difference_fraction must be in (0, 0.5]")
    grad_tol = _finite_float(gradient_tolerance, "gradient_tolerance")
    cost_tol = _finite_float(cost_tolerance, "cost_tolerance")
    step_tol = _finite_float(step_tolerance, "step_tolerance")
    if min(grad_tol, cost_tol, step_tol) <= 0.0:
        raise ValueError("gradient, cost, and step tolerances must be positive")

    names: list[str] = []
    initial: dict[str, float] = {}
    box: dict[str, tuple[float, float]] = {}
    coordinate_scales: list[float] = []
    coordinate_lowers: list[float] = []
    coordinate_uppers: list[float] = []
    coordinate_fd_steps: list[float] = []
    if set(bounds) != set(initial_parameters):
        raise ValueError("bounds must contain exactly the initial parameter names")
    for name, raw_value in initial_parameters.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("parameter names must be non-empty strings")
        value = _finite_float(raw_value, f"initial_parameters[{name!r}]")
        pair = _finite_vector(bounds[name], f"bounds[{name!r}]", expected_length=2)
        lower, upper = pair
        width = upper - lower
        if not math.isfinite(width) or width <= 0.0:
            raise ValueError(f"bounds for parameter {name!r} must have finite lower < upper")
        if value < lower or value > upper:
            raise ValueError(f"initial parameter {name!r} must lie within its bounds")
        names.append(name)
        initial[name] = value
        box[name] = (lower, upper)
        coordinate_scale = max(abs(value), min(width, 1.0))
        coordinate_lower = (lower - value) / coordinate_scale
        coordinate_upper = (upper - value) / coordinate_scale
        if not math.isfinite(coordinate_lower) or not math.isfinite(coordinate_upper):
            raise ValueError(f"bounds for parameter {name!r} exceed the supported coordinate range")
        coordinate_scales.append(coordinate_scale)
        coordinate_lowers.append(coordinate_lower)
        coordinate_uppers.append(coordinate_upper)
        coordinate_fd_steps.append(fd_fraction * (width / coordinate_scale))

    parameter_names = tuple(names)
    parameter_count = len(parameter_names)
    evaluation_count = 0
    expected_residual_count: int | None = None

    def parameter_values(point: Sequence[float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for index, name in enumerate(parameter_names):
            lower, upper = box[name]
            coordinate = point[index]
            if coordinate <= coordinate_lowers[index]:
                value = lower
            elif coordinate >= coordinate_uppers[index]:
                value = upper
            else:
                value = initial[name] + coordinate * coordinate_scales[index]
                value = min(upper, max(lower, value))
            if not math.isfinite(value):
                raise ValueError(f"parameter value is not finite for {name!r}")
            result[name] = value
        return result

    def evaluate(point: Sequence[float], context: str) -> tuple[float, ...]:
        nonlocal evaluation_count, expected_residual_count
        if evaluation_count >= max_function_evaluations:
            raise _FitEvaluationLimit
        values = parameter_values(point)
        evaluation_count += 1
        try:
            residuals = _finite_vector(
                residual_function(MappingProxyType(values)), "least-squares residuals"
            )
        except Exception as exc:
            raise ValueError(f"residual evaluation failed during {context}: {exc}") from exc
        if not residuals:
            raise ValueError("residual_function must return at least one residual")
        if expected_residual_count is None:
            expected_residual_count = len(residuals)
        elif len(residuals) != expected_residual_count:
            raise ValueError("residual_function changed its residual dimension")
        if len(residuals) * parameter_count > _MAX_FIT_JACOBIAN_VALUES:
            raise ValueError(
                f"least-squares Jacobian exceeds {_MAX_FIT_JACOBIAN_VALUES} values"
            )
        return residuals

    current = [0.0 for _ in range(parameter_count)]
    residual_values = evaluate(current, "initial evaluation")
    residual_norm, cost = _least_squares_measure(residual_values)
    initial_residual_scale = max(abs(value) for value in residual_values)
    cost_underflowed = cost == 0.0 and residual_norm > 0.0
    iterations = 0
    accepted_steps = 0
    damping = 1e-3
    status = "MAX_ITERATIONS"

    if residual_norm == 0.0:
        status = "CONVERGED"
    else:
        for iteration in range(1, max_iterations + 1):
            iterations = iteration
            columns: list[list[float]] = []
            try:
                for parameter_index, name in enumerate(parameter_names):
                    center = current[parameter_index]
                    lower_coordinate = coordinate_lowers[parameter_index]
                    upper_coordinate = coordinate_uppers[parameter_index]
                    delta = min(
                        coordinate_fd_steps[parameter_index],
                        center - lower_coordinate,
                        upper_coordinate - center,
                    )
                    if delta > 0.0:
                        lower_point = list(current)
                        upper_point = list(current)
                        lower_point[parameter_index] = center - delta
                        upper_point[parameter_index] = center + delta
                        lower_parameters = parameter_values(lower_point)[name]
                        upper_parameters = parameter_values(upper_point)[name]
                        if lower_parameters == upper_parameters:
                            raise ValueError(
                                f"finite-difference values are not representable for parameter {name!r}"
                            )
                        lower_residuals = evaluate(
                            lower_point, f"parameter {name!r} lower difference"
                        )
                        upper_residuals = evaluate(
                            upper_point, f"parameter {name!r} upper difference"
                        )
                        denominator = (
                            upper_point[parameter_index]
                            - lower_point[parameter_index]
                        )
                        column = [
                            (upper_value - lower_value) / denominator
                            for lower_value, upper_value in zip(
                                lower_residuals, upper_residuals
                            )
                        ]
                    elif center <= lower_coordinate:
                        upper_point = list(current)
                        upper_point[parameter_index] = min(
                            center + coordinate_fd_steps[parameter_index],
                            upper_coordinate,
                        )
                        upper_parameters = parameter_values(upper_point)[name]
                        if upper_parameters == parameter_values(current)[name]:
                            raise ValueError(
                                f"finite-difference value is not representable for parameter {name!r}"
                            )
                        upper_residuals = evaluate(
                            upper_point, f"parameter {name!r} upper difference"
                        )
                        denominator = upper_point[parameter_index] - center
                        column = [
                            (upper_value - value) / denominator
                            for value, upper_value in zip(residual_values, upper_residuals)
                        ]
                    else:
                        lower_point = list(current)
                        lower_point[parameter_index] = max(
                            center - coordinate_fd_steps[parameter_index],
                            lower_coordinate,
                        )
                        lower_parameters = parameter_values(lower_point)[name]
                        if lower_parameters == parameter_values(current)[name]:
                            raise ValueError(
                                f"finite-difference value is not representable for parameter {name!r}"
                            )
                        lower_residuals = evaluate(
                            lower_point, f"parameter {name!r} lower difference"
                        )
                        denominator = center - lower_point[parameter_index]
                        column = [
                            (value - lower_value) / denominator
                            for value, lower_value in zip(residual_values, lower_residuals)
                        ]
                    if any(not math.isfinite(value) for value in column):
                        raise ValueError(f"Jacobian is not finite for parameter {name!r}")
                    columns.append(column)
            except _FitEvaluationLimit:
                status = "MAX_FUNCTION_EVALUATIONS"
                break

            residual_scale = max(
                initial_residual_scale,
                max(abs(value) for value in residual_values),
            )
            scaled_residuals = [value / residual_scale for value in residual_values]
            column_scales = [
                max((abs(value) for value in column), default=0.0) or 1.0
                for column in columns
            ]
            scaled_columns = [
                [value / column_scales[index] for value in column]
                for index, column in enumerate(columns)
            ]
            gradient = [
                math.fsum(
                    value * residual
                    for value, residual in zip(column, scaled_residuals)
                )
                for column in scaled_columns
            ]
            projected_gradient = [
                0.0 if current[index] <= coordinate_lowers[index] and value > 0.0
                else 0.0 if current[index] >= coordinate_uppers[index] and value < 0.0
                else value
                for index, value in enumerate(gradient)
            ]
            if max(abs(value) for value in projected_gradient) <= grad_tol:
                status = "CONVERGED"
                break

            normal = [
                [0.0 for _ in range(parameter_count)]
                for _ in range(parameter_count)
            ]
            for left in range(parameter_count):
                for right in range(left, parameter_count):
                    value = math.fsum(
                        row_left * row_right
                        for row_left, row_right in zip(
                            scaled_columns[left], scaled_columns[right]
                        )
                    )
                    normal[left][right] = normal[right][left] = value
            maximum_diagonal = max(normal[index][index] for index in range(parameter_count))
            if maximum_diagonal == 0.0:
                status = "STALLED"
                break
            damped = [row[:] for row in normal]
            for index in range(parameter_count):
                diagonal = max(normal[index][index], maximum_diagonal * 1e-12)
                damped[index][index] += damping * diagonal
            scaled_direction = _solve_dense_system(
                damped, [-value for value in gradient]
            )
            direction = [
                scaled_direction[index]
                * (residual_scale / column_scales[index])
                for index in range(parameter_count)
            ]
            if any(not math.isfinite(value) for value in direction):
                status = "STALLED"
                break
            candidate = []
            for index in range(parameter_count):
                proposed = current[index] + direction[index]
                if not math.isfinite(proposed):
                    proposed = (
                        coordinate_uppers[index]
                        if direction[index] > 0.0
                        else coordinate_lowers[index]
                    )
                candidate.append(
                    min(
                        coordinate_uppers[index],
                        max(coordinate_lowers[index], proposed),
                    )
                )
            step_size = max(
                abs(candidate[index] - current[index])
                for index in range(parameter_count)
            )
            if step_size <= step_tol:
                status = "STALLED"
                break

            try:
                candidate_residuals = evaluate(candidate, "trial point")
            except _FitEvaluationLimit:
                status = "MAX_FUNCTION_EVALUATIONS"
                break
            candidate_norm, candidate_cost = _least_squares_measure(candidate_residuals)
            if candidate_norm < residual_norm:
                relative_improvement = 1.0 - (candidate_norm / residual_norm) ** 2
                current = candidate
                residual_values = candidate_residuals
                residual_norm = candidate_norm
                cost = candidate_cost
                cost_underflowed = cost == 0.0 and residual_norm > 0.0
                accepted_steps += 1
                damping = max(damping / 3.0, 1e-12)
                if relative_improvement <= cost_tol or step_size <= step_tol:
                    status = "CONVERGED"
                    break
            else:
                damping *= 10.0
                if not math.isfinite(damping) or damping > 1e12:
                    status = "STALLED"
                    break

    final_parameters = parameter_values(current)
    return LeastSquaresFit(
        parameter_names=parameter_names,
        initial_parameters=MappingProxyType(dict(initial)),
        parameters=MappingProxyType(final_parameters),
        bounds=MappingProxyType(dict(box)),
        residuals=residual_values,
        cost=cost,
        cost_underflowed=cost_underflowed,
        status=status,
        iterations=iterations,
        accepted_steps=accepted_steps,
        function_evaluations=evaluation_count,
        max_iterations=max_iterations,
        max_function_evaluations=max_function_evaluations,
        finite_difference_fraction=fd_fraction,
        final_damping=damping,
    )
