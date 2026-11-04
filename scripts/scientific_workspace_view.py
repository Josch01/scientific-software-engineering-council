"""Bounded, inert presentation models for verified scientific workspaces."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from types import MappingProxyType
import unicodedata

try:
    from .scientific_core import OdeSolution, ObservationDataset, SirModelDefinition
    from .scientific_workspace_loader import LoadedResource, LoadedWorkspace
except ImportError:  # Support direct script execution/import by the desktop shell.
    from scientific_core import OdeSolution, ObservationDataset, SirModelDefinition
    from scientific_workspace_loader import LoadedResource, LoadedWorkspace


MAX_JSON_VIEW_BYTES = 1 * 1024 * 1024
MAX_TOTAL_JSON_VIEW_BYTES = 2 * 1024 * 1024
MAX_JSON_TEXT_PREVIEW_BYTES = 32 * 1024
MAX_TEXT_PREVIEW_BYTES = 256 * 1024
MAX_UI_COMPONENTS = 100
MAX_JSON_DEPTH = 32
MAX_SIMULATION_ROWS = 100_000
MAX_SIMULATION_VIEW_VALUES = 1_000_000
MAX_SIMULATION_VIEW_PARAMETERS = 100
MAX_SIMULATION_VIEW_STATES = 100
MAX_SCIENTIFIC_VIEW_SERIES = 100
MAX_SCIENTIFIC_VIEW_POINTS = 100_000
_SHA256 = frozenset("0123456789abcdef")

SUPPORTED_COMPONENT_TYPES = frozenset(
    {
        "equation_view",
        "parameter_table",
        "observation_table",
        "simulation_plot",
        "fit_summary",
        "sensitivity_plot",
        "residual_plot",
        "uncertainty_summary",
        "audit_summary",
        "artifact_browser",
        "code_view",
    }
)


@dataclass(frozen=True, slots=True)
class ComponentView:
    component_id: str
    component_type: str
    title: str
    status: str
    message: str
    content: object = None
    truncated: bool = False
    preview_text: str = ""
    source_resources: tuple["ResourceView", ...] = ()


@dataclass(frozen=True, slots=True)
class FitParameterView:
    name: str
    initial_value: float
    fitted_value: float
    lower_bound: float
    upper_bound: float
    unit: str


@dataclass(frozen=True, slots=True)
class FitSummaryView:
    method: str
    status: str
    cost: float
    cost_underflowed: bool
    iterations: int
    accepted_steps: int
    function_evaluations: int
    max_iterations: int
    max_function_evaluations: int
    parameters: tuple[FitParameterView, ...]
    residuals: tuple[float, ...]
    finite_difference_fraction: float
    final_damping: float


@dataclass(frozen=True, slots=True)
class ScientificSeriesView:
    label: str
    values: tuple[float, ...]
    unit: str


@dataclass(frozen=True, slots=True)
class SensitivityPlotView:
    method: str
    solver_method: str
    times: tuple[float, ...]
    time_unit: str
    series: tuple[ScientificSeriesView, ...]


@dataclass(frozen=True, slots=True)
class ResidualSeriesView:
    variable: str
    unit: str
    times: tuple[float, ...]
    observed: tuple[float, ...]
    simulated: tuple[float, ...]
    residuals: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ObservationEvaluationView:
    observation_sha256: str
    provenance: Mapping[str, str]
    time_unit: str
    series: tuple[ResidualSeriesView, ...]
    residual_order: tuple[tuple[float, str], ...]


@dataclass(frozen=True, slots=True)
class SirEquationView:
    equation_set: str
    population_balance: str
    equations: tuple[tuple[str, str], ...]
    states: tuple[str, str, str]
    time_unit: str
    population_unit: str
    rate_unit: str


@dataclass(frozen=True, slots=True)
class SirRateProfileView:
    name: str
    kind: str
    value: float | None
    points: tuple[tuple[float, float], ...]
    unit: str


@dataclass(frozen=True, slots=True)
class SirParameterView:
    initial_conditions: tuple[tuple[str, float], ...]
    initial_population: float
    population_unit: str
    time_span: tuple[float, float]
    time_unit: str
    profiles: tuple[SirRateProfileView, ...]
    integrator_method: str
    max_step: float
    max_steps: int


@dataclass(frozen=True, slots=True)
class SectionView:
    section_id: str
    title: str
    components: tuple[ComponentView, ...]
    omitted_component_count: int = 0


@dataclass(frozen=True, slots=True)
class ResourceView:
    resource_id: str
    kind: str
    path: str
    sha256: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceViewModel:
    workspace_id: str
    title: str
    sections: tuple[SectionView, ...]
    resources: tuple[ResourceView, ...]
    omitted_component_count: int = 0
    verification_status: str = "ARTIFACT_DIGESTS_MATCHED"
    scientific_notice: str = (
        "La visualización de artefactos no valida el modelo ni establece "
        "precisión, identificabilidad o validez científica."
    )


@dataclass(frozen=True, slots=True)
class _CachedFailure:
    message: str


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    return value


def _reject_constant(token: str) -> object:
    raise ValueError(f"non-standard JSON constant {token!r} is not allowed")


def _check_json_depth(raw: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
        elif byte == ord('"'):
            in_string = True
        elif byte in (ord("{"), ord("[")):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError(f"JSON nesting exceeds the {MAX_JSON_DEPTH}-container limit")
        elif byte in (ord("}"), ord("]")):
            depth -= 1


def _parse_json(content: bytes) -> object:
    if len(content) > MAX_JSON_VIEW_BYTES:
        raise ValueError(f"JSON preview exceeds the {MAX_JSON_VIEW_BYTES}-byte UI limit")
    _check_json_depth(content)
    try:
        text = content.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_parse_finite_float,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("JSON artifact must be UTF-8") from exc
    except (json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ValueError(f"invalid JSON artifact: {exc}") from exc


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def sanitize_display_text(value: str) -> str:
    return "".join(
        character
        if character in "\t\n\r" or unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
        else "\uFFFD"
        for character in value
    )


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _simulation_base_content(payload: object) -> Mapping[str, object]:
    result = _object(payload, "simulation result")
    required = {
        "schema_version", "method", "times", "state_names", "values",
        "parameters", "requested_max_step", "actual_step_size", "step_count",
    }
    if set(result) != required or type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ValueError("simulation result does not match scientific_core schema v1")
    if not isinstance(result["method"], str) or not result["method"] or len(result["method"]) > 64:
        raise ValueError("simulation method must be a non-empty string of at most 64 characters")
    if type(result["step_count"]) is not int or result["step_count"] < 1:
        raise ValueError("simulation step_count must be a positive integer")
    requested_step = _number(result["requested_max_step"], "requested_max_step")
    actual_step = _number(result["actual_step_size"], "actual_step_size")
    if requested_step <= 0.0 or actual_step <= 0.0:
        raise ValueError("simulation step sizes must be positive")
    requested_tolerance = max(
        math.ulp(requested_step), math.ulp(actual_step), abs(requested_step) * 1e-12
    )
    if actual_step > requested_step + requested_tolerance:
        raise ValueError("actual_step_size exceeds the requested maximum")
    parameters = _object(result["parameters"], "simulation parameters")
    if any(not isinstance(name, str) for name in parameters):
        raise ValueError("simulation parameter names must be strings")
    for name, value in parameters.items():
        if not name or len(name) > 128:
            raise ValueError("simulation parameter names must contain at most 128 characters")
        _number(value, f"simulation parameter {name!r}")
    times = result["times"]
    names = result["state_names"]
    rows = result["values"]
    if not isinstance(times, (list, tuple)) or not times:
        raise ValueError("simulation times must be a non-empty sequence")
    if len(times) != result["step_count"] + 1:
        raise ValueError("simulation step_count must match the time grid")
    if len(times) > MAX_SIMULATION_ROWS:
        raise ValueError(f"simulation exceeds the {MAX_SIMULATION_ROWS}-row UI limit")
    if (
        not isinstance(names, (list, tuple))
        or not names
        or any(not isinstance(name, str) or not name or len(name) > 128 for name in names)
    ):
        raise ValueError("simulation state_names must be non-empty strings of at most 128 characters")
    if len(set(names)) != len(names):
        raise ValueError("simulation state_names must be unique")
    if not isinstance(rows, (list, tuple)) or len(rows) != len(times):
        raise ValueError("simulation values must contain one row per time")
    numeric_times = tuple(_number(value, "simulation time") for value in times)
    if any(right <= left for left, right in zip(numeric_times, numeric_times[1:])):
        raise ValueError("simulation times must be strictly increasing")
    for left, right in zip(numeric_times, numeric_times[1:]):
        interval = right - left
        tolerance = max(
            math.ulp(left), math.ulp(right), math.ulp(actual_step), abs(actual_step) * 1e-12
        )
        if not math.isfinite(interval) or abs(interval - actual_step) > tolerance:
            raise ValueError("actual_step_size does not match the time grid")
    numeric_rows: list[tuple[float, ...]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != len(names):
            raise ValueError(f"simulation values row {index} must match state_names")
        numeric_rows.append(
            tuple(_number(value, f"simulation values row {index}") for value in row)
        )
    return MappingProxyType(
        {
            "method": sanitize_display_text(result["method"]),
            "times": numeric_times,
            "state_names": tuple(names),
            "values": tuple(numeric_rows),
            "row_count": len(numeric_times),
        }
    )


def _simulation_content(
    base: Mapping[str, object], config: Mapping[str, object]
) -> Mapping[str, object]:
    configured_names = config["series"]
    if not isinstance(configured_names, (list, tuple)):
        raise ValueError("configured simulation series must be a sequence")
    by_name = {name: index for index, name in enumerate(base["state_names"])}
    if any(name not in by_name for name in configured_names):
        raise ValueError("configured simulation series are absent from state_names")
    series_names = tuple(configured_names)
    series_indices = tuple(by_name[name] for name in series_names)
    return MappingProxyType(
        {
            "method": base["method"],
            "times": base["times"],
            "values": base["values"],
            "series_names": series_names,
            "series_indices": series_indices,
            "row_count": base["row_count"],
        }
    )


def build_simulation_result_view(
    component: ComponentView,
    solution: OdeSolution,
    *,
    series: Sequence[str],
    action_label: str,
) -> ComponentView:
    """Validate a trusted callback's in-memory solver result for the existing plot renderer."""
    if component.component_type != "simulation_plot":
        raise ValueError("approved simulation output requires a simulation_plot component")
    if not isinstance(solution, OdeSolution):
        raise ValueError("approved simulation callback must return an OdeSolution")
    if type(solution.step_count) is not int or solution.step_count < 1:
        raise ValueError("simulation step_count must be a positive integer")
    if (not isinstance(solution.method, str) or not solution.method
            or len(solution.method) > 64):
        raise ValueError("simulation method must be a non-empty string of at most 64 characters")
    row_count = solution.step_count + 1
    if row_count > MAX_SIMULATION_ROWS:
        raise ValueError(f"simulation exceeds the {MAX_SIMULATION_ROWS}-row UI limit")
    if (not isinstance(solution.times, (tuple, list))
            or len(solution.times) != row_count):
        raise ValueError("simulation step_count must match the time grid before serialization")
    if (not isinstance(solution.states, (tuple, list))
            or len(solution.states) != row_count):
        raise ValueError("simulation states must match the time grid before serialization")
    if not isinstance(solution.state_names, (tuple, list)) or not solution.state_names:
        raise ValueError("simulation state_names must be a non-empty sequence")
    state_count = len(solution.state_names)
    if state_count > MAX_SIMULATION_VIEW_STATES:
        raise ValueError(
            f"simulation exceeds the {MAX_SIMULATION_VIEW_STATES}-state UI limit"
        )
    if row_count * (state_count + 1) > MAX_SIMULATION_VIEW_VALUES:
        raise ValueError(
            f"simulation exceeds the {MAX_SIMULATION_VIEW_VALUES}-value UI limit"
        )
    if any(not isinstance(name, str) or not name or len(name) > 128
           for name in solution.state_names):
        raise ValueError("simulation state_names must be bounded non-empty strings")
    if (not isinstance(solution.parameters, Mapping)
            or len(solution.parameters) > MAX_SIMULATION_VIEW_PARAMETERS):
        raise ValueError(
            f"simulation exceeds the {MAX_SIMULATION_VIEW_PARAMETERS}-parameter UI limit"
        )
    if any(not isinstance(row, (tuple, list)) or len(row) != state_count
           for row in solution.states):
        raise ValueError("simulation states must match state_names before serialization")
    base = _simulation_base_content(solution.to_dict())
    content = _simulation_content(base, {"series": series})
    safe_label = sanitize_display_text(action_label)
    message = (
        f"Salida en memoria de la acción aprobada «{safe_label}». "
        "Esto no valida el modelo ni su validez científica."
    )
    return ComponentView(
        component_id=component.component_id,
        component_type="simulation_plot",
        title=component.title,
        status="ok",
        message=message,
        content=content,
        source_resources=component.source_resources,
    )


def _result_object(value: object, label: str, required: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    if set(value) != required:
        raise ValueError(f"{label} must match the versioned scientific_core schema")
    return value


def _result_sequence(value: object, label: str, *, minimum: int = 1,
                     maximum: int = MAX_SCIENTIFIC_VIEW_POINTS) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} must contain between {minimum} and {maximum} entries")
    return tuple(value)


def _result_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty string of at most 128 characters")
    safe_value = sanitize_display_text(value)
    if safe_value != value:
        raise ValueError(f"{label} contains unsupported display characters")
    return value


def _result_names(value: object, label: str, *, maximum: int = MAX_SIMULATION_VIEW_STATES
                  ) -> tuple[str, ...]:
    names = tuple(_result_name(item, label) for item in _result_sequence(
        value, label, maximum=maximum
    ))
    if len(set(names)) != len(names):
        raise ValueError(f"{label} must contain unique names")
    return names


def _result_number(value: object, label: str) -> float:
    return _number(value, label)


def _unit_map(context: Mapping[str, object] | None, field: str) -> Mapping[str, str]:
    if context is None:
        return MappingProxyType({})
    if not isinstance(context, Mapping):
        raise ValueError("unit_context must be an object")
    values = context.get(field, {})
    if not isinstance(values, Mapping) or any(not isinstance(name, str) for name in values):
        raise ValueError(f"unit_context.{field} must be an object")
    units: dict[str, str] = {}
    for name, unit in values.items():
        if not isinstance(unit, str) or not unit or len(unit) > 256:
            raise ValueError(f"unit_context.{field}[{name!r}] must be a non-empty unit string")
        units[name] = sanitize_display_text(unit)
    return MappingProxyType(units)


def build_fit_summary_view(
    payload: object,
    config: Mapping[str, object],
    unit_context: Mapping[str, object] | None = None,
) -> FitSummaryView:
    """Validate and select existing LeastSquaresFit schema v1 values for display."""
    required = {
        "schema_version", "method", "parameter_names", "initial_parameters", "parameters",
        "bounds", "residuals", "cost", "cost_underflowed", "status", "iterations",
        "accepted_steps", "function_evaluations", "max_iterations",
        "max_function_evaluations", "finite_difference_fraction", "final_damping",
    }
    result = _result_object(payload, "fit result", required)
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ValueError("unsupported fit schema_version; expected 1")
    if result["method"] != "BOUNDED_LEVENBERG_MARQUARDT":
        raise ValueError("fit method does not match scientific_core schema v1")
    names = _result_names(result["parameter_names"], "fit parameter_names",
                          maximum=MAX_SIMULATION_VIEW_PARAMETERS)
    configured = _result_names(config.get("parameter_names"), "configured parameter_names",
                               maximum=MAX_SIMULATION_VIEW_PARAMETERS)
    if any(name not in names for name in configured):
        raise ValueError("configured parameters are absent from fit parameter_names")
    initial = result["initial_parameters"]
    fitted = result["parameters"]
    raw_bounds = result["bounds"]
    for label, mapping in (("initial_parameters", initial), ("parameters", fitted),
                           ("bounds", raw_bounds)):
        if not isinstance(mapping, Mapping) or set(mapping) != set(names):
            raise ValueError(f"fit {label} must match parameter_names")
    unit_context = unit_context or {}
    parameter_units = _unit_map(unit_context, "parameter_units")
    parameter_views: list[FitParameterView] = []
    for name in configured:
        initial_value = _result_number(initial[name], f"initial_parameters[{name!r}]")
        fitted_value = _result_number(fitted[name], f"parameters[{name!r}]")
        bound = _result_object(raw_bounds[name], f"bounds[{name!r}]", {"lower", "upper"})
        lower = _result_number(bound["lower"], f"bounds[{name!r}].lower")
        upper = _result_number(bound["upper"], f"bounds[{name!r}].upper")
        if lower > upper or not lower <= fitted_value <= upper:
            raise ValueError(f"fit parameter {name!r} is outside its declared bounds")
        parameter_views.append(FitParameterView(
            name=name, initial_value=initial_value, fitted_value=fitted_value,
            lower_bound=lower, upper_bound=upper,
            unit=parameter_units.get(name, "unidad no indicada"),
        ))
    if type(result["cost_underflowed"]) is not bool:
        raise ValueError("fit cost_underflowed must be a boolean")
    cost = _result_number(result["cost"], "fit cost")
    if cost < 0.0:
        raise ValueError("fit cost must be non-negative")
    status = result["status"]
    if not isinstance(status, str) or not status or len(status) > 128:
        raise ValueError("fit status must be a non-empty string of at most 128 characters")
    counts: dict[str, int] = {}
    for name in ("iterations", "accepted_steps", "function_evaluations",
                 "max_iterations", "max_function_evaluations"):
        value = result[name]
        if type(value) is not int or value < 0:
            raise ValueError(f"fit {name} must be a non-negative integer")
        counts[name] = value
    if (counts["iterations"] > counts["max_iterations"]
            or counts["function_evaluations"] > counts["max_function_evaluations"]
            or counts["accepted_steps"] > counts["iterations"]):
        raise ValueError("fit work counts exceed their declared bounds")
    residual_values = _result_sequence(
        result["residuals"], "fit residuals", minimum=0, maximum=MAX_SIMULATION_VIEW_VALUES
    )
    residuals = tuple(_result_number(value, "fit residual") for value in residual_values)
    fraction = _result_number(result["finite_difference_fraction"],
                              "finite_difference_fraction")
    damping = _result_number(result["final_damping"], "final_damping")
    if not 0.0 < fraction < 1.0 or damping < 0.0:
        raise ValueError("fit finite-difference fraction or final damping is outside its domain")
    return FitSummaryView(
        method=str(result["method"]), status=sanitize_display_text(status),
        cost=cost,
        cost_underflowed=result["cost_underflowed"], iterations=counts["iterations"],
        accepted_steps=counts["accepted_steps"],
        function_evaluations=counts["function_evaluations"],
        max_iterations=counts["max_iterations"],
        max_function_evaluations=counts["max_function_evaluations"],
        parameters=tuple(parameter_views), residuals=residuals,
        finite_difference_fraction=fraction, final_damping=damping,
    )


def build_sensitivity_plot_view(
    payload: object,
    config: Mapping[str, object],
    unit_context: Mapping[str, object] | None = None,
) -> SensitivityPlotView:
    """Validate the [time][state][parameter] OdeSensitivity schema v1 tensor."""
    required = {
        "schema_version", "method", "solver_method", "times", "state_names",
        "parameter_names", "base_parameters", "base_values", "perturbations",
        "parameter_bounds", "values", "requested_max_step", "actual_step_size",
        "step_count_per_trajectory", "trajectory_count", "total_step_count",
        "rhs_evaluation_count",
    }
    result = _result_object(payload, "sensitivity result", required)
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ValueError("unsupported sensitivity schema_version; expected 1")
    if result["method"] != "CENTRAL_FINITE_DIFFERENCE":
        raise ValueError("sensitivity method does not match scientific_core schema v1")
    state_names = _result_names(result["state_names"], "sensitivity state_names")
    parameter_names = _result_names(result["parameter_names"], "sensitivity parameter_names",
                                    maximum=MAX_SIMULATION_VIEW_PARAMETERS)
    configured_states = _result_names(config.get("state_names"), "configured state_names")
    configured_parameters = _result_names(config.get("parameter_names"),
                                          "configured parameter_names",
                                          maximum=MAX_SIMULATION_VIEW_PARAMETERS)
    if any(name not in state_names for name in configured_states):
        raise ValueError("configured states are absent from sensitivity state_names")
    if any(name not in parameter_names for name in configured_parameters):
        raise ValueError("configured parameters are absent from sensitivity parameter_names")
    times = tuple(_result_number(value, "sensitivity time") for value in _result_sequence(
        result["times"], "sensitivity times"
    ))
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("sensitivity times must be strictly increasing")
    maps: dict[str, Mapping[str, object]] = {}
    for field in ("base_parameters", "perturbations", "parameter_bounds"):
        value = result[field]
        if not isinstance(value, Mapping) or set(value) != set(parameter_names):
            raise ValueError(f"sensitivity {field} must match parameter_names")
        maps[field] = value
    for name in parameter_names:
        base_parameter = _result_number(maps["base_parameters"][name],
                                         f"base_parameters[{name!r}]")
        perturbation = _result_number(maps["perturbations"][name],
                                       f"perturbations[{name!r}]")
        bounds = _result_object(maps["parameter_bounds"][name],
                                f"parameter_bounds[{name!r}]", {"lower", "upper"})
        lower = _result_number(bounds["lower"], f"parameter_bounds[{name!r}].lower")
        upper = _result_number(bounds["upper"], f"parameter_bounds[{name!r}].upper")
        if perturbation <= 0.0 or lower > upper or not lower <= base_parameter <= upper:
            raise ValueError(f"sensitivity parameter {name!r} has invalid perturbation or bounds")
    base_rows = _result_sequence(result["base_values"], "sensitivity base_values")
    tensor = _result_sequence(result["values"], "sensitivity values")
    if len(base_rows) != len(times) or len(tensor) != len(times):
        raise ValueError("sensitivity tensor time dimension does not match times")
    parameter_indices = {name: index for index, name in enumerate(parameter_names)}
    selected_values: dict[tuple[str, str], list[float]] = {
        (state, parameter): []
        for state in configured_states for parameter in configured_parameters
    }
    for time_index, (base_row, time_row) in enumerate(zip(base_rows, tensor)):
        base_values = _result_sequence(base_row, f"sensitivity base_values[{time_index}]",
                                       maximum=MAX_SIMULATION_VIEW_STATES)
        sensitivities_by_state = _result_sequence(
            time_row, f"sensitivity values[{time_index}]", maximum=MAX_SIMULATION_VIEW_STATES
        )
        if len(base_values) != len(state_names) or len(sensitivities_by_state) != len(state_names):
            raise ValueError("sensitivity tensor state dimension does not match state_names")
        for state_index, sensitivities in enumerate(sensitivities_by_state):
            parameter_values = _result_sequence(
                sensitivities, f"sensitivity tensor[{time_index}][{state_index}]",
                maximum=MAX_SIMULATION_VIEW_PARAMETERS,
            )
            if len(parameter_values) != len(parameter_names):
                raise ValueError("sensitivity tensor parameter dimension does not match parameter_names")
            _result_number(base_values[state_index], "sensitivity base value")
            state = state_names[state_index]
            if state in configured_states:
                for parameter in configured_parameters:
                    selected_values[(state, parameter)].append(
                        _result_number(parameter_values[parameter_indices[parameter]],
                                       "sensitivity value")
                    )
    if len(times) * (len(state_names) * len(parameter_names) + len(state_names)) > MAX_SIMULATION_VIEW_VALUES:
        raise ValueError("sensitivity result exceeds the bounded chart value limit")
    counts: dict[str, int] = {}
    for name in ("step_count_per_trajectory", "trajectory_count", "total_step_count",
                 "rhs_evaluation_count"):
        value = result[name]
        if type(value) is not int or value < 0:
            raise ValueError(f"sensitivity {name} must be a non-negative integer")
        counts[name] = value
    if (counts["trajectory_count"] != 1 + 2 * len(parameter_names)
            or counts["total_step_count"] != counts["step_count_per_trajectory"] * counts["trajectory_count"]
            or counts["rhs_evaluation_count"] != 4 * counts["total_step_count"]):
        raise ValueError("sensitivity work counts do not match the declared trajectories")
    step_requested = _result_number(result["requested_max_step"], "requested_max_step")
    step_actual = _result_number(result["actual_step_size"], "actual_step_size")
    if step_requested <= 0.0 or step_actual <= 0.0 or step_actual > step_requested + max(
        math.ulp(step_requested), abs(step_requested) * 1e-12
    ):
        raise ValueError("sensitivity solver step sizes are invalid")
    solver_method = _result_name(result["solver_method"], "sensitivity solver_method")
    unit_context = unit_context or {}
    state_units = _unit_map(unit_context, "state_units")
    parameter_units = _unit_map(unit_context, "parameter_units")
    time_unit = unit_context.get("time_unit", "unidad no indicada") if isinstance(unit_context, Mapping) else "unidad no indicada"
    if not isinstance(time_unit, str) or not time_unit or len(time_unit) > 256:
        raise ValueError("unit_context.time_unit must be a non-empty unit string")
    series: list[ScientificSeriesView] = []
    for state in configured_states:
        for parameter in configured_parameters:
            state_unit = state_units.get(state)
            parameter_unit = parameter_units.get(parameter)
            unit = (f"{state_unit} / {parameter_unit}"
                    if state_unit is not None and parameter_unit is not None
                    else "unidad no indicada")
            series.append(ScientificSeriesView(
                label=f"{state} ∂/∂{parameter}",
                values=tuple(selected_values[(state, parameter)]), unit=unit,
            ))
    return SensitivityPlotView(
        method="CENTRAL_FINITE_DIFFERENCE", solver_method=solver_method,
        times=times, time_unit=sanitize_display_text(time_unit), series=tuple(series),
    )


def build_observation_evaluation_view(payload: object) -> ObservationEvaluationView:
    """Validate ObservationEvaluation schema v1 and retain sparse residual coordinates."""
    required = {
        "schema_version", "method", "observation_sha256", "provenance", "time_unit",
        "variable_units", "times", "observed_values", "simulated_values", "residual_order",
        "residuals", "model", "solver",
    }
    result = _result_object(payload, "observation evaluation", required)
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ValueError("unsupported observation evaluation schema_version; expected 1")
    if result["method"] != "SEGMENTED_FIXED_STEP_RK4_AT_OBSERVATION_TIMES":
        raise ValueError("observation evaluation method does not match scientific_core schema v1")
    digest = result["observation_sha256"]
    if (not isinstance(digest, str) or len(digest) != 64
            or any(character not in _SHA256 for character in digest)):
        raise ValueError("observation_sha256 must be a lowercase SHA-256 digest")
    raw_provenance = result["provenance"]
    if (not isinstance(raw_provenance, Mapping) or not raw_provenance
            or len(raw_provenance) > 32):
        raise ValueError("observation evaluation provenance must be a bounded object")
    provenance: dict[str, str] = {}
    for key, value in raw_provenance.items():
        if not isinstance(key, str) or not key or len(key) > 256:
            raise ValueError("observation provenance keys must be non-empty strings")
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise ValueError("observation provenance values must be non-empty strings")
        provenance[sanitize_display_text(key)] = sanitize_display_text(value)
    if "source" not in provenance:
        raise ValueError("observation evaluation provenance must include source")
    time_unit = result["time_unit"]
    if not isinstance(time_unit, str) or not time_unit or len(time_unit) > 256:
        raise ValueError("observation evaluation time_unit must be a non-empty string")
    units = result["variable_units"]
    if (not isinstance(units, Mapping) or not units
            or len(units) > MAX_SCIENTIFIC_VIEW_SERIES):
        raise ValueError("observation evaluation variable_units must be a bounded object")
    variable_names = tuple(_result_name(name, "observation variable") for name in units)
    variable_units: dict[str, str] = {}
    for name, unit in units.items():
        if not isinstance(unit, str) or not unit or len(unit) > 256:
            raise ValueError(f"observation unit for {name!r} must be a non-empty string")
        variable_units[name] = sanitize_display_text(unit)
    times = tuple(_result_number(value, "observation evaluation time")
                  for value in _result_sequence(result["times"], "observation evaluation times"))
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("observation evaluation times must be strictly increasing")
    observed = _result_sequence(result["observed_values"], "observed_values")
    simulated = _result_sequence(result["simulated_values"], "simulated_values")
    if len(observed) != len(times) or len(simulated) != len(times):
        raise ValueError("observation evaluation rows must match times")
    observed_coordinates: set[tuple[float, str]] = set()
    observed_rows: list[Mapping[str, float]] = []
    simulated_rows: list[Mapping[str, float]] = []
    for row_index, (raw_observed, raw_simulated) in enumerate(zip(observed, simulated)):
        if (not isinstance(raw_observed, Mapping) or not raw_observed
                or not set(raw_observed).issubset(variable_units)):
            raise ValueError(f"observed_values[{row_index}] contains invalid variables")
        if (not isinstance(raw_simulated, Mapping)
                or set(raw_simulated) != set(variable_units)):
            raise ValueError(f"simulated_values[{row_index}] must match variable_units")
        observed_row = {
            name: _result_number(value, f"observed_values[{row_index}][{name!r}]")
            for name, value in raw_observed.items()
        }
        simulated_row = {
            name: _result_number(raw_simulated[name], f"simulated_values[{row_index}][{name!r}]")
            for name in variable_names
        }
        for name in observed_row:
            observed_coordinates.add((times[row_index], name))
        observed_rows.append(MappingProxyType(observed_row))
        simulated_rows.append(MappingProxyType(simulated_row))
    raw_order = _result_sequence(result["residual_order"], "residual_order",
                                 minimum=0, maximum=MAX_SIMULATION_VIEW_VALUES)
    raw_residuals = _result_sequence(result["residuals"], "residuals",
                                     minimum=0, maximum=MAX_SIMULATION_VIEW_VALUES)
    if len(raw_order) != len(raw_residuals) or len(raw_order) != len(observed_coordinates):
        raise ValueError("residual coordinates and residual values must match observations")
    time_index_by_value = {time: index for index, time in enumerate(times)}
    residual_order: list[tuple[float, str]] = []
    residual_by_coordinate: dict[tuple[float, str], float] = {}
    for coordinate, residual in zip(raw_order, raw_residuals):
        entry = _result_object(coordinate, "residual coordinate", {"time", "variable"})
        time = _result_number(entry["time"], "residual coordinate time")
        variable = _result_name(entry["variable"], "residual coordinate variable")
        key = (time, variable)
        if key not in observed_coordinates or key in residual_by_coordinate:
            raise ValueError("residual coordinates must uniquely match observed values")
        value = _result_number(residual, "residual value")
        row_index = time_index_by_value.get(time)
        if row_index is None:
            raise ValueError("residual coordinates must match observation times")
        expected_residual = simulated_rows[row_index][variable] - observed_rows[row_index][variable]
        if not math.isfinite(expected_residual) or not math.isclose(
            value, expected_residual, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("residual value does not match simulated minus observed data")
        residual_by_coordinate[key] = value
        residual_order.append(key)
    model = _result_object(result["model"], "observation evaluation model", {
        "time_unit", "variable_units", "parameters", "state_names", "initial_state",
    })
    model_state_names = _result_names(model["state_names"], "model state_names")
    if not set(variable_names).issubset(model_state_names):
        raise ValueError("model state_names must contain each observed variable")
    if not isinstance(model["time_unit"], str) or not model["time_unit"] or len(model["time_unit"]) > 256:
        raise ValueError("model time_unit must be a non-empty string")
    model_initial_state = _result_sequence(model["initial_state"], "model initial_state",
                                          maximum=MAX_SIMULATION_VIEW_STATES)
    if len(model_initial_state) != len(model_state_names):
        raise ValueError("model initial_state must match state_names")
    for index, value in enumerate(model_initial_state):
        _result_number(value, f"model initial_state[{index}]")
    model_units = model["variable_units"]
    if not isinstance(model_units, Mapping) or set(model_units) != set(variable_names):
        raise ValueError("model variable_units must match observation variables")
    for unit in model_units.values():
        if not isinstance(unit, str) or not unit or len(unit) > 256:
            raise ValueError("model variable units must be non-empty strings")
    parameters = model["parameters"]
    if not isinstance(parameters, Mapping) or len(parameters) > MAX_SIMULATION_VIEW_PARAMETERS:
        raise ValueError("model parameters must be a bounded object")
    for name, value in parameters.items():
        _result_name(name, "model parameter name")
        _result_number(value, f"model parameter {name!r}")
    solver = _result_object(result["solver"], "observation evaluation solver", {
        "requested_max_step", "segment_step_sizes", "segment_step_counts", "total_step_count",
        "rhs_evaluation_count", "max_steps_per_interval", "max_total_steps",
    })
    requested_step = _result_number(solver["requested_max_step"], "requested_max_step")
    if requested_step <= 0.0:
        raise ValueError("requested_max_step must be positive")
    step_sizes = _result_sequence(solver["segment_step_sizes"], "segment_step_sizes")
    step_counts = _result_sequence(solver["segment_step_counts"], "segment_step_counts")
    if len(step_sizes) != len(times) or len(step_counts) != len(times):
        raise ValueError("solver segment metadata must match observation times")
    normalized_step_counts: list[int] = []
    for index, (step_size, step_count) in enumerate(zip(step_sizes, step_counts)):
        if type(step_count) is not int or step_count < 0:
            raise ValueError(f"segment_step_counts[{index}] must be non-negative")
        normalized_step_counts.append(step_count)
        if step_count == 0:
            if step_size is not None:
                raise ValueError("zero-step segments must not declare a step size")
        elif (_result_number(step_size, f"segment_step_sizes[{index}]") <= 0.0):
            raise ValueError("positive-step segments must declare a positive step size")
    for name in ("total_step_count", "rhs_evaluation_count", "max_steps_per_interval", "max_total_steps"):
        if type(solver[name]) is not int or solver[name] < 0:
            raise ValueError(f"solver {name} must be a non-negative integer")
    if (sum(normalized_step_counts) != solver["total_step_count"]
            or solver["rhs_evaluation_count"] != 4 * solver["total_step_count"]
            or solver["total_step_count"] > solver["max_total_steps"]
            or any(count > solver["max_steps_per_interval"] for count in normalized_step_counts)):
        raise ValueError("observation solver work counts are inconsistent")
    if solver["max_steps_per_interval"] < 1 or solver["max_total_steps"] < 1:
        raise ValueError("observation solver step limits must be positive")
    series: list[ResidualSeriesView] = []
    for variable in variable_names:
        coordinates = tuple((time, variable) for time in times
                            if (time, variable) in observed_coordinates)
        if not coordinates:
            continue
        series.append(ResidualSeriesView(
            variable=variable, unit=variable_units[variable],
            times=tuple(time for time, _ in coordinates),
            observed=tuple(observed_rows[time_index_by_value[time]][variable]
                           for time, _ in coordinates),
            simulated=tuple(simulated_rows[time_index_by_value[time]][variable]
                            for time, _ in coordinates),
            residuals=tuple(residual_by_coordinate[key] for key in coordinates),
        ))
    return ObservationEvaluationView(
        observation_sha256=digest,
        provenance=MappingProxyType(provenance),
        time_unit=sanitize_display_text(time_unit),
        series=tuple(series),
        residual_order=tuple(residual_order),
    )


def _observation_content(payload: object) -> Mapping[str, object]:
    dataset = ObservationDataset.from_dict(_object(payload, "observation dataset"))
    rows = tuple(
        MappingProxyType({key: float(value) for key, value in row.items()})
        for row in dataset.values
    )
    return MappingProxyType(
        {
            "time_unit": dataset.time_unit,
            "variable_units": dataset.variable_units,
            "times": dataset.times,
            "observations": rows,
            "provenance": dataset.provenance,
            "content_sha256": dataset.content_sha256,
        }
    )


def _resource_view(resource: LoadedResource) -> ResourceView:
    return ResourceView(
        resource_id=sanitize_display_text(resource.resource_id),
        kind=sanitize_display_text(resource.kind),
        path=sanitize_display_text(resource.path),
        sha256=resource.sha256,
        byte_count=len(resource.content),
    )


def _cached_json_payload(
    resource: LoadedResource,
    cache: dict[str, object | _CachedFailure],
    total_byte_count: list[int],
) -> object:
    if resource.resource_id in cache:
        cached = cache[resource.resource_id]
        if isinstance(cached, _CachedFailure):
            raise ValueError(cached.message)
        return cached
    try:
        if len(resource.content) > MAX_JSON_VIEW_BYTES:
            raise ValueError(f"JSON preview exceeds the {MAX_JSON_VIEW_BYTES}-byte UI limit")
        if total_byte_count[0] + len(resource.content) > MAX_TOTAL_JSON_VIEW_BYTES:
            raise ValueError(
                f"workspace JSON views exceed the {MAX_TOTAL_JSON_VIEW_BYTES}-byte UI budget"
            )
        payload = _freeze(_parse_json(resource.content))
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        message = sanitize_display_text(str(exc))[:300]
        cache[resource.resource_id] = _CachedFailure(message)
        raise ValueError(message) from exc
    cache[resource.resource_id] = payload
    total_byte_count[0] += len(resource.content)
    return payload


def _sir_equation_view(definition: SirModelDefinition) -> SirEquationView:
    equations = definition.to_dict()["equations"]
    return SirEquationView(
        equation_set=definition.equation_set,
        population_balance="N = S(0) + I(0) + R(0)",
        equations=tuple(equations.items()),
        states=definition.state_names,
        time_unit=definition.time_unit,
        population_unit=definition.population_unit,
        rate_unit=definition.rate_unit,
    )


def _sir_parameter_view(definition: SirModelDefinition) -> SirParameterView:
    profiles = tuple(
        SirRateProfileView(
            name=name,
            kind=profile.kind,
            value=profile.value,
            points=profile.points,
            unit=definition.rate_unit,
        )
        for name, profile in definition.parameters.items()
    )
    return SirParameterView(
        initial_conditions=tuple(zip(definition.state_names, definition.initial_state)),
        initial_population=definition.initial_population,
        population_unit=definition.population_unit,
        time_span=definition.t_span,
        time_unit=definition.time_unit,
        profiles=profiles,
        integrator_method="RK4_FIXED_STEP",
        max_step=definition.max_step,
        max_steps=definition.max_steps,
    )


def _render_component(
    component: Mapping[str, object],
    resource_by_id: Mapping[str, LoadedResource],
    all_resources: tuple[ResourceView, ...],
    json_cache: dict[str, object | _CachedFailure],
    json_byte_count: list[int],
    simulation_cache: dict[str, Mapping[str, object] | _CachedFailure],
    component_cache: dict[tuple[object, ...], tuple[str, object, str, bool, str]],
) -> ComponentView:
    component_id = str(component["id"])
    component_type = str(component["type"])
    title = sanitize_display_text(str(component["title"]))
    refs = component["resource_refs"]
    config = _object(component["config"], f"component {component_id} config")
    if component_type not in SUPPORTED_COMPONENT_TYPES:
        return ComponentView(component_id, component_type, title, "error", "Unregistered renderer")
    source_resources = tuple(
        _resource_view(resource_by_id[str(resource_id)]) for resource_id in refs
    )

    try:
        if component_type == "artifact_browser":
            selected = set(refs)
            content = tuple(resource for resource in all_resources if resource.resource_id in selected)
            return ComponentView(
                component_id, component_type, title, "ok", "Loaded resource metadata", content,
                source_resources=source_resources,
            )

        resource = resource_by_id[str(refs[0])]
        config_signature = tuple(
            sorted(
                (
                    key,
                    tuple(value) if isinstance(value, (list, tuple)) else value,
                )
                for key, value in config.items()
            )
        )
        cache_key = (resource.resource_id, component_type, config_signature)
        if cache_key in component_cache:
            status, content, message, truncated, preview_text = component_cache[cache_key]
            return ComponentView(
                component_id,
                component_type,
                title,
                status,
                message,
                content,
                truncated,
                preview_text,
                source_resources,
            )
        if component_type == "code_view":
            preview_bytes = resource.content[:MAX_TEXT_PREVIEW_BYTES]
            text = sanitize_display_text(preview_bytes.decode("utf-8", errors="replace"))
            truncated = len(resource.content) > MAX_TEXT_PREVIEW_BYTES
            message = "Texto plano; no se ejecuta." if not truncated else "Vista truncada; el artefacto completo no se ejecuta."
            component_cache[cache_key] = ("ok", text, message, truncated, text)
            return ComponentView(
                component_id, component_type, title, "ok", message, text, truncated,
                source_resources=source_resources,
            )

        payload = _cached_json_payload(resource, json_cache, json_byte_count)
        is_sir_contract = (
            isinstance(payload, Mapping) and payload.get("model_type") == "sir"
        )
        if is_sir_contract and component_type in {"equation_view", "parameter_table"}:
            definition = SirModelDefinition.from_dict(payload)
            if component_type == "equation_view":
                content = _sir_equation_view(definition)
            else:
                content = _sir_parameter_view(definition)
            message = (
                "Contrato SIR v1 validado para su visualización; no acredita validez científica."
            )
            preview_text = ""
            truncated = False
        elif component_type == "observation_table":
            content = _observation_content(payload)
        elif component_type == "simulation_plot":
            if resource.resource_id not in simulation_cache:
                try:
                    simulation_cache[resource.resource_id] = _simulation_base_content(payload)
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    simulation_cache[resource.resource_id] = _CachedFailure(str(exc))
                    raise
            simulation_base = simulation_cache[resource.resource_id]
            if isinstance(simulation_base, _CachedFailure):
                raise ValueError(simulation_base.message)
            content = _simulation_content(simulation_base, config)
        elif component_type == "fit_summary":
            content = build_fit_summary_view(payload, config)
        elif component_type == "sensitivity_plot":
            content = build_sensitivity_plot_view(payload, config)
        elif component_type == "residual_plot":
            content = build_observation_evaluation_view(payload)
        else:
            content = _freeze(payload)
        if not (is_sir_contract and component_type in {"equation_view", "parameter_table"}):
            message = "Artefacto leído como datos inertes; no implica validación científica."
            if component_type == "uncertainty_summary":
                message = (
                    "NOT_ASSESSED / NOT_CALCULATED: no hay una estimación de incertidumbre "
                    "validada; no se generan intervalos ni bandas."
                )
            elif component_type == "fit_summary":
                message = (
                    "Se presenta el resultado del ajuste declarado; la convergencia no "
                    "demuestra identificabilidad práctica ni incertidumbre estadística."
                )
            elif component_type == "sensitivity_plot":
                message = (
                    "Sensibilidad local del resultado suministrado; no establece "
                    "identificabilidad práctica ni incertidumbre estadística."
                )
            elif component_type == "residual_plot":
                message = (
                    "Residuales calculados por el contrato de evaluación; representan "
                    "simulación menos observación, no incertidumbre estadística."
                )
            preview_text = ""
            truncated = False
            if component_type not in {"observation_table", "simulation_plot"}:
                preview_text = sanitize_display_text(
                    resource.content[:MAX_JSON_TEXT_PREVIEW_BYTES].decode("utf-8", errors="replace")
                )
                truncated = len(resource.content) > MAX_JSON_TEXT_PREVIEW_BYTES
                if truncated:
                    message += " Vista JSON limitada a 32 KiB."
        component_cache[cache_key] = ("ok", content, message, truncated, preview_text)
        return ComponentView(
            component_id, component_type, title, "ok", message, content, truncated, preview_text,
            source_resources,
        )
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError) as exc:
        error_message = sanitize_display_text(f"No se pudo representar este componente: {exc}")[:300]
        if "cache_key" in locals():
            component_cache[cache_key] = ("error", None, error_message, False, "")
        return ComponentView(
            component_id,
            component_type,
            title,
            "error",
            error_message,
            source_resources=source_resources,
        )


def build_workspace_view_model(workspace: LoadedWorkspace) -> WorkspaceViewModel:
    """Build display data from the loader's captured bytes without file access."""
    manifest = workspace.manifest
    raw_sections = manifest["sections"]
    resources = tuple(_resource_view(resource) for resource in workspace.resources)
    resource_by_id = {resource.resource_id: resource for resource in workspace.resources}
    json_cache: dict[str, object | _CachedFailure] = {}
    json_byte_count = [0]
    simulation_cache: dict[str, Mapping[str, object] | _CachedFailure] = {}
    component_cache: dict[tuple[object, ...], tuple[str, object, str, bool, str]] = {}
    sections_list: list[SectionView] = []
    remaining_components = MAX_UI_COMPONENTS
    omitted_total = 0
    for section in raw_sections:
        raw_components = section["components"]
        selected_components = tuple(raw_components[:remaining_components])
        omitted = len(raw_components) - len(selected_components)
        remaining_components -= len(selected_components)
        omitted_total += omitted
        sections_list.append(
            SectionView(
                section_id=str(section["id"]),
                title=sanitize_display_text(str(section["title"])),
                components=tuple(
                    _render_component(
                        component,
                        resource_by_id,
                        resources,
                        json_cache,
                        json_byte_count,
                        simulation_cache,
                        component_cache,
                    )
                    for component in selected_components
                ),
                omitted_component_count=omitted,
            )
        )
    sections = tuple(sections_list)
    return WorkspaceViewModel(
        workspace_id=workspace.summary.workspace_id,
        title=sanitize_display_text(workspace.summary.title),
        sections=sections,
        resources=resources,
        omitted_component_count=omitted_total,
    )
