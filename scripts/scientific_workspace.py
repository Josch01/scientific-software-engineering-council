"""Validate versioned, model-agnostic scientific workspace manifests.

This module validates layout metadata only. It never loads or executes a
resource named by the manifest; a future renderer must verify file containment
and hashes before reading any artifact.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path, PureWindowsPath
import re
import sys
import unicodedata


_MAX_MANIFEST_BYTES = 1_048_576
_MAX_JSON_DEPTH = 32
_MAX_RESOURCES = 500
_MAX_SECTIONS = 100
_MAX_COMPONENTS = 1_000
_MAX_REFERENCES = 100
_MAX_CONFIG_NAMES = 50
_MAX_PATH_LENGTH = 512
_MAX_PATH_SEGMENTS = 32
_MAX_SEGMENT_LENGTH = 128
_MAX_TEXT_LENGTH = 4_096

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_DEVICE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|"
    r"COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$",
    re.IGNORECASE,
)
_SHORT_ALIAS_SUFFIX = re.compile(r"~[0-9]+$")
_WIN32_FORBIDDEN = frozenset('<>:"|?*')

_RESOURCE_KINDS = frozenset(
    {
        "model_spec",
        "observations",
        "simulation_result",
        "fit_result",
        "sensitivity_result",
        "observation_evaluation",
        "uncertainty_result",
        "audit_report",
        "source_code",
        "generic",
    }
)

_COMPONENT_REQUIRED_KIND: dict[str, str | None] = {
    "equation_view": "model_spec",
    "parameter_table": "model_spec",
    "observation_table": "observations",
    "simulation_plot": "simulation_result",
    "fit_summary": "fit_result",
    "sensitivity_plot": "sensitivity_result",
    "residual_plot": "observation_evaluation",
    "uncertainty_summary": "uncertainty_result",
    "audit_summary": "audit_report",
    "artifact_browser": None,
    "code_view": "source_code",
}
_COMPONENT_CONFIG_FIELDS: dict[str, frozenset[str]] = {
    "equation_view": frozenset(),
    "parameter_table": frozenset(),
    "observation_table": frozenset(),
    "simulation_plot": frozenset({"x_axis", "series", "context_refs"}),
    "fit_summary": frozenset({"parameter_names", "context_refs"}),
    "sensitivity_plot": frozenset({"state_names", "parameter_names", "context_refs"}),
    "residual_plot": frozenset(),
    "uncertainty_summary": frozenset({"quantities"}),
    "audit_summary": frozenset(),
    "artifact_browser": frozenset(),
    "code_view": frozenset({"language"}),
}


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    """Small validation result suitable for a CLI or a future desktop core."""

    workspace_id: str
    title: str
    resource_count: int
    section_count: int
    component_count: int
    component_types: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "VALID",
            "schema_version": 1,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "resource_count": self.resource_count,
            "section_count": self.section_count,
            "component_count": self.component_count,
            "component_types": list(self.component_types),
        }


def _fail(message: str) -> None:
    raise ValueError(message)


def _text(value: object, label: str, *, maximum: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a non-empty string")
    if len(value) > maximum:
        _fail(f"{label} exceeds the {maximum}-character limit")
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in value):
        _fail(f"{label} contains a control or surrogate character")
    return value


def _identifier(value: object, label: str) -> str:
    identifier = _text(value, label, maximum=64)
    if not _IDENTIFIER.fullmatch(identifier):
        _fail(f"{label} must match the portable identifier pattern")
    return identifier


def _sequence(value: object, label: str, *, minimum: int, maximum: int) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail(f"{label} must be a sequence")
    if not minimum <= len(value) <= maximum:
        _fail(f"{label} must contain between {minimum} and {maximum} items")
    return value


def _mapping(value: object, label: str, fields: set[str], optional: set[str] | None = None) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    allowed = fields | (optional or set())
    if not fields <= set(value) or not set(value) <= allowed:
        _fail(f"{label} has unknown or missing fields")
    return value


def _portable_path(value: object, label: str) -> tuple[str, str]:
    path = _text(value, label, maximum=_MAX_PATH_LENGTH)
    windows_path = PureWindowsPath(path)
    if (
        "\\" in path
        or ":" in path
        or path.startswith("/")
        or windows_path.is_absolute()
        or windows_path.drive
    ):
        _fail(f"{label} must be a portable relative path using '/' separators")

    segments = path.split("/")
    if len(segments) > _MAX_PATH_SEGMENTS:
        _fail(f"{label} exceeds the {_MAX_PATH_SEGMENTS}-segment limit")
    for segment in segments:
        if not segment or segment in {".", ".."}:
            _fail(f"{label} contains an empty, dot, or traversal segment")
        if len(segment) > _MAX_SEGMENT_LENGTH:
            _fail(f"{label} contains a segment longer than {_MAX_SEGMENT_LENGTH} characters")
        if segment.endswith((" ", ".")):
            _fail(f"{label} contains a segment ending in a space or period")
        if any(
            character in _WIN32_FORBIDDEN
            or unicodedata.category(character) in {"Cc", "Cs"}
            for character in segment
        ):
            _fail(f"{label} contains a Windows-forbidden or control character")
        if _WINDOWS_DEVICE.fullmatch(segment):
            _fail(f"{label} contains a reserved Windows device name")
        stem = segment.rsplit(".", 1)[0]
        if _SHORT_ALIAS_SUFFIX.search(stem):
            _fail(f"{label} contains a short 8.3-alias-looking segment")

    normalized_key = unicodedata.normalize(
        "NFKC", unicodedata.normalize("NFKC", path).casefold()
    )
    return path, normalized_key


def _name_list(value: object, label: str) -> tuple[str, ...]:
    entries = _sequence(value, label, minimum=1, maximum=_MAX_CONFIG_NAMES)
    names = tuple(_text(entry, f"{label} item", maximum=256) for entry in entries)
    if len(set(names)) != len(names):
        _fail(f"{label} names must be unique")
    return names


def _validate_component_config(component_type: str, config: object, label: str) -> None:
    fields = _COMPONENT_CONFIG_FIELDS[component_type]
    optional_fields = {"context_refs"} if component_type in {
        "simulation_plot", "fit_summary", "sensitivity_plot",
    } else set()
    required_fields = set(fields) - optional_fields
    config_mapping = _mapping(
        config, f"{label}.config", required_fields, optional_fields
    )
    if component_type == "simulation_plot":
        if config_mapping["x_axis"] != "time":
            _fail(f"{label}.config.x_axis must be 'time'")
        _name_list(config_mapping["series"], f"{label}.config.series")
    elif component_type == "fit_summary":
        _name_list(config_mapping["parameter_names"], f"{label}.config.parameter_names")
    elif component_type == "sensitivity_plot":
        _name_list(config_mapping["state_names"], f"{label}.config.state_names")
        _name_list(config_mapping["parameter_names"], f"{label}.config.parameter_names")
    if component_type in {"simulation_plot", "fit_summary", "sensitivity_plot"} and "context_refs" in config_mapping:
        maximum = {"simulation_plot": 1, "fit_summary": 3, "sensitivity_plot": 2}[
            component_type
        ]
        raw_context_refs = _sequence(
            config_mapping["context_refs"],
            f"{label}.config.context_refs",
            minimum=0,
            maximum=maximum,
        )
        for index, resource_id in enumerate(raw_context_refs):
            _identifier(resource_id, f"{label}.config.context_refs[{index}]")
    elif component_type == "uncertainty_summary":
        _name_list(config_mapping["quantities"], f"{label}.config.quantities")
    elif component_type == "code_view":
        if config_mapping["language"] not in {"python", "json", "markdown", "text"}:
            _fail(f"{label}.config.language is not a supported view format")


def validate_workspace_manifest(payload: Mapping[str, object]) -> WorkspaceSummary:
    """Validate a workspace layout without touching referenced resource paths."""
    root = _mapping(
        payload,
        "workspace manifest",
        {"schema_version", "workspace_id", "title", "resources", "sections"},
        {"description"},
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        _fail("schema_version must be the integer 1")
    workspace_id = _identifier(root["workspace_id"], "workspace_id")
    title = _text(root["title"], "title", maximum=200)
    if "description" in root:
        _text(root["description"], "description")

    raw_resources = _sequence(root["resources"], "resources", minimum=1, maximum=_MAX_RESOURCES)
    resources: dict[str, str] = {}
    resource_paths: set[str] = set()
    for index, raw_resource in enumerate(raw_resources):
        label = f"resources[{index}]"
        resource = _mapping(raw_resource, label, {"id", "kind", "path"}, {"sha256"})
        resource_id = _identifier(resource["id"], f"{label}.id")
        if resource_id in resources:
            _fail(f"duplicate resource id {resource_id!r}")
        kind = _text(resource["kind"], f"{label}.kind", maximum=64)
        if kind not in _RESOURCE_KINDS:
            _fail(f"{label}.kind is not a registered resource kind")
        path, path_key = _portable_path(resource["path"], f"{label}.path")
        if path_key in resource_paths:
            _fail(f"duplicate resource path {path!r} after portable normalization")
        resource_paths.add(path_key)
        if "sha256" in resource:
            sha256 = _text(resource["sha256"], f"{label}.sha256", maximum=64)
            if not _SHA256.fullmatch(sha256):
                _fail(f"{label}.sha256 must be a lowercase SHA-256 digest")
        resources[resource_id] = kind

    raw_sections = _sequence(root["sections"], "sections", minimum=1, maximum=_MAX_SECTIONS)
    section_ids: set[str] = set()
    component_ids: set[str] = set()
    component_types: list[str] = []
    component_count = 0
    for section_index, raw_section in enumerate(raw_sections):
        section_label = f"sections[{section_index}]"
        section = _mapping(raw_section, section_label, {"id", "title", "components"})
        section_id = _identifier(section["id"], f"{section_label}.id")
        if section_id in section_ids:
            _fail(f"duplicate section id {section_id!r}")
        section_ids.add(section_id)
        _text(section["title"], f"{section_label}.title", maximum=200)
        components = _sequence(
            section["components"],
            f"{section_label}.components",
            minimum=1,
            maximum=_MAX_COMPONENTS,
        )
        component_count += len(components)
        if component_count > _MAX_COMPONENTS:
            _fail(f"components exceed the {_MAX_COMPONENTS}-component limit")
        for component_index, raw_component in enumerate(components):
            component_label = f"{section_label}.components[{component_index}]"
            component = _mapping(
                raw_component,
                component_label,
                {"id", "type", "title", "resource_refs", "config"},
            )
            component_id = _identifier(component["id"], f"{component_label}.id")
            if component_id in component_ids:
                _fail(f"duplicate component id {component_id!r}")
            component_ids.add(component_id)
            _text(component["title"], f"{component_label}.title", maximum=200)
            component_type = _text(component["type"], f"{component_label}.type", maximum=64)
            if component_type not in _COMPONENT_REQUIRED_KIND:
                _fail(f"{component_label}.type is not a registered component type")
            refs = _sequence(
                component["resource_refs"],
                f"{component_label}.resource_refs",
                minimum=1,
                maximum=_MAX_REFERENCES,
            )
            if any(not isinstance(reference, str) for reference in refs):
                _fail(f"{component_label}.resource_refs must contain string IDs")
            if len(set(refs)) != len(refs):
                _fail(f"{component_label}.resource_refs must be unique")
            for reference in refs:
                if reference not in resources:
                    _fail(f"{component_label} contains unknown resource reference {reference!r}")
            required_kind = _COMPONENT_REQUIRED_KIND[component_type]
            if component_type == "artifact_browser":
                pass
            else:
                if len(refs) != 1:
                    _fail(f"{component_label} requires exactly one resource reference")
                if resources[refs[0]] != required_kind:
                    _fail(
                        f"{component_label} requires resource kind {required_kind!r}"
                    )
            _validate_component_config(component_type, component["config"], component_label)
            if component_type in {"simulation_plot", "fit_summary", "sensitivity_plot"}:
                config = component["config"]
                context_refs = tuple(config.get("context_refs", ()))
                if len(set(context_refs)) != len(context_refs):
                    _fail(f"{component_label}.config.context_refs must be unique")
                if set(context_refs) & set(refs):
                    _fail(f"{component_label}.config.context_refs must be distinct from resource_refs")
                for context_ref in context_refs:
                    if context_ref not in resources:
                        _fail(
                            f"{component_label} contains unknown context resource reference "
                            f"{context_ref!r}"
                        )
                context_kinds = tuple(resources[context_ref] for context_ref in context_refs)
                if component_type == "simulation_plot":
                    if any(kind != "model_spec" for kind in context_kinds):
                        _fail("simulation_plot context_refs only allow model_spec")
                elif component_type == "fit_summary":
                    if any(kind not in {"model_spec", "observations"} for kind in context_kinds):
                        _fail(
                            "fit_summary context_refs only allow model_spec and observations"
                        )
                    if (context_kinds.count("model_spec") > 1
                            or context_kinds.count("observations") > 1):
                        _fail(
                            "fit_summary context_refs allow at most one model_spec and one observations"
                        )
                else:
                    if any(kind != "model_spec" for kind in context_kinds):
                        _fail("sensitivity_plot context_refs only allow model_spec")
                    if context_kinds.count("model_spec") > 1:
                        _fail(
                            "sensitivity_plot context_refs allow at most one model_spec"
                        )
            component_types.append(component_type)

    return WorkspaceSummary(
        workspace_id=workspace_id,
        title=title,
        resource_count=len(resources),
        section_count=len(raw_sections),
        component_count=component_count,
        component_types=tuple(component_types),
    )


def _reject_duplicate_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        _fail("JSON number must be finite")
    return value


def _reject_json_constant(token: str) -> object:
    _fail(f"non-standard JSON constant {token!r} is not allowed")


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
            if depth > _MAX_JSON_DEPTH:
                _fail(f"JSON nesting exceeds the {_MAX_JSON_DEPTH}-container limit")
        elif byte in (ord("}"), ord("]")):
            depth -= 1


def parse_workspace_manifest_bytes(raw: bytes) -> Mapping[str, object]:
    """Parse already-read bytes using the manifest CLI's strict JSON policy."""
    if not isinstance(raw, bytes):
        raise TypeError("manifest bytes must be bytes")
    if len(raw) > _MAX_MANIFEST_BYTES:
        _fail(f"manifest exceeds the {_MAX_MANIFEST_BYTES}-byte limit")
    _check_json_depth(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("manifest must be valid UTF-8") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_float=_parse_finite_float,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ValueError(f"manifest JSON is invalid: {exc}") from exc
    if not isinstance(payload, Mapping):
        _fail("workspace manifest root must be an object")
    return payload


def load_workspace_manifest(path: str | Path) -> Mapping[str, object]:
    """Read and parse only the selected manifest, with bounded memory use."""
    manifest_path = Path(path)
    try:
        with manifest_path.open("rb") as stream:
            raw = stream.read(_MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"cannot read workspace manifest: {exc}") from exc
    return parse_workspace_manifest_bytes(raw)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="path to a workspace manifest JSON file")
    arguments = parser.parse_args(argv)
    try:
        payload = load_workspace_manifest(arguments.manifest)
        summary = validate_workspace_manifest(payload)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(summary.to_dict(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
