"""Small dependency-free numerical primitives for SSEC scientific projects.

The RK4 implementation is fixed-step and intended for transparent, bounded
initial-value simulations. It does not estimate error or certify a model.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType


State = tuple[float, ...]
RightHandSide = Callable[[float, State, Mapping[str, float]], Sequence[float]]
_DEFAULT_MAX_STEPS = 1_000_000


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
                value
                + step_size
                * math.fsum(
                    (first / 6.0, second / 3.0, third / 3.0, fourth / 6.0)
                )
                for value, first, second, third, fourth in zip(state, k1, k2, k3, k4)
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
