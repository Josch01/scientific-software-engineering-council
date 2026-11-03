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

SUPPORTED_COMPONENT_TYPES = frozenset(
    {
        "equation_view",
        "parameter_table",
        "observation_table",
        "simulation_plot",
        "fit_summary",
        "sensitivity_plot",
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

    try:
        if component_type == "artifact_browser":
            selected = set(refs)
            content = tuple(resource for resource in all_resources if resource.resource_id in selected)
            return ComponentView(component_id, component_type, title, "ok", "Loaded resource metadata", content)

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
            )
        if component_type == "code_view":
            preview_bytes = resource.content[:MAX_TEXT_PREVIEW_BYTES]
            text = sanitize_display_text(preview_bytes.decode("utf-8", errors="replace"))
            truncated = len(resource.content) > MAX_TEXT_PREVIEW_BYTES
            message = "Texto plano; no se ejecuta." if not truncated else "Vista truncada; el artefacto completo no se ejecuta."
            component_cache[cache_key] = ("ok", text, message, truncated, text)
            return ComponentView(component_id, component_type, title, "ok", message, text, truncated)

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
        else:
            content = _freeze(payload)
        if not (is_sir_contract and component_type in {"equation_view", "parameter_table"}):
            message = "Artefacto leído como datos inertes; no implica validación científica."
            if component_type in {"uncertainty_summary", "sensitivity_plot"}:
                message = "Se muestra el artefacto disponible; no se calcula ni valida incertidumbre o sensibilidad."
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
            component_id, component_type, title, "ok", message, content, truncated, preview_text
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
