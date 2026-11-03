"""Versioned, inert contracts for agent-configured scientific workspaces.

This module validates metadata only. It never parses scientific expressions,
imports artifacts, renders HTML, or executes project code.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import re
import unicodedata


_SCHEMA_VERSION = 1
_MAX_ARTIFACTS = 1000
_MAX_PAGES = 100
_MAX_COMPONENTS = 500
_MAX_COMPONENTS_PER_PAGE = 100
_MAX_TITLE_LENGTH = 1000
_MAX_SUMMARY_LENGTH = 4000
_MAX_ID_LENGTH = 64
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_RESERVED_DEVICE = re.compile(r"(?:COM|LPT)(?:[1-9]|[¹²³])\Z", re.IGNORECASE)
_SHORT_NAME_SUFFIX = re.compile(r"~[0-9]+\Z")
_RESERVED_NAMES = {"con", "prn", "aux", "nul", "conin$", "conout$"}
_WINDOWS_FORBIDDEN = set('<>:"/\\|?*')

_ARTIFACT_KINDS = frozenset(
    {
        "model_definition",
        "dataset",
        "simulation_result",
        "plot",
        "optimization_result",
        "sensitivity_result",
        "uncertainty_result",
        "audit_report",
        "test_report",
        "source_code",
    }
)
_COMPONENT_ARTIFACTS: dict[str, frozenset[str] | None] = {
    "model_overview": frozenset({"model_definition"}),
    "equations": frozenset({"model_definition"}),
    "parameters": frozenset({"model_definition", "optimization_result"}),
    "simulation_plot": frozenset({"simulation_result", "plot"}),
    "optimization": frozenset({"optimization_result"}),
    "sensitivity": frozenset({"sensitivity_result"}),
    "uncertainty": frozenset({"uncertainty_result"}),
    "results": frozenset(
        {
            "simulation_result",
            "plot",
            "optimization_result",
            "sensitivity_result",
            "uncertainty_result",
        }
    ),
    "audit": frozenset({"audit_report", "test_report"}),
    "project_files": None,
}


@dataclass(frozen=True, slots=True)
class ModelCard:
    id: str
    title: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "summary": self.summary}


@dataclass(frozen=True, slots=True)
class Artifact:
    id: str
    kind: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "kind": self.kind, "path": self.path}


@dataclass(frozen=True, slots=True)
class Component:
    id: str
    kind: str
    title: str
    artifact_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "artifact_ids": list(self.artifact_ids),
        }


@dataclass(frozen=True, slots=True)
class WorkspacePage:
    id: str
    title: str
    components: tuple[Component, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "components": [component.to_dict() for component in self.components],
        }


@dataclass(frozen=True, slots=True)
class ScientificWorkspace:
    schema_version: int
    model: ModelCard
    artifacts: tuple[Artifact, ...]
    pages: tuple[WorkspacePage, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize to the stable, versioned JSON data contract."""
        return {
            "schema_version": self.schema_version,
            "model": self.model.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "pages": [page.to_dict() for page in self.pages],
        }


def _object(value: object, label: str, fields: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} field names must be strings")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {sorted(unknown)!r}")
    if missing:
        raise ValueError(f"{label} is missing fields: {sorted(missing)!r}")
    return value


def _text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be non-empty text of at most {maximum} characters")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_ID_LENGTH
        or not _IDENTIFIER.fullmatch(value)
    ):
        raise ValueError(
            f"{label} must be a portable identifier of at most {_MAX_ID_LENGTH} characters"
        )
    return value


def _string_list(value: object, label: str, *, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} must be a list with at most {maximum} entries")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} entries must be strings")
    return tuple(value)


def _portable_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("artifact path must be non-empty portable relative text")
    if value.startswith("/") or "\\" in value:
        raise ValueError("artifact path must use relative POSIX separators")

    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("artifact path must not contain empty, dot, or parent segments")
    for segment in segments:
        if segment.startswith(" ") or segment.endswith((".", " ")):
            raise ValueError(
                "artifact path segments must not start with a space or end in a dot or space"
            )
        if any(character in _WINDOWS_FORBIDDEN for character in segment):
            raise ValueError("artifact path contains a Windows-forbidden character")
        if any(ord(character) < 32 or ord(character) == 127 for character in segment):
            raise ValueError("artifact path must not contain control characters")
        device_base = segment.split(".", 1)[0].rstrip(" .").casefold()
        if device_base in _RESERVED_NAMES or _RESERVED_DEVICE.fullmatch(device_base):
            raise ValueError("artifact path must not use a reserved Windows device name")
        if _SHORT_NAME_SUFFIX.search(segment.split(".", 1)[0]):
            raise ValueError("artifact path must not use a Windows short-name alias")
    return value


def _artifact_path_key(path: str) -> str:
    # NFKC + casefold conservatively catches aliases across common Windows and
    # macOS filesystems before a workspace is moved between operating systems.
    return unicodedata.normalize("NFKC", path).casefold()


def validate_workspace(data: object) -> ScientificWorkspace:
    """Validate and detach a schema-v1 scientific workspace manifest."""
    root = _object(data, "workspace", {"schema_version", "model", "artifacts", "pages"})
    version = root["schema_version"]
    if type(version) is not int or version != _SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {_SCHEMA_VERSION}")

    raw_model = _object(root["model"], "model", {"id", "title", "summary"})
    model = ModelCard(
        id=_identifier(raw_model["id"], "model.id"),
        title=_text(raw_model["title"], "model.title", maximum=_MAX_TITLE_LENGTH),
        summary=_text(raw_model["summary"], "model.summary", maximum=_MAX_SUMMARY_LENGTH),
    )
    artifact_ids_seen: set[str] = set()

    raw_artifacts = root["artifacts"]
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) > _MAX_ARTIFACTS:
        raise ValueError(f"artifacts must be a list with at most {_MAX_ARTIFACTS} entries")
    artifacts: list[Artifact] = []
    artifacts_by_id: dict[str, Artifact] = {}
    path_keys: set[str] = set()
    for index, raw in enumerate(raw_artifacts):
        label = f"artifacts[{index}]"
        item = _object(raw, label, {"id", "kind", "path"})
        artifact_id = _identifier(item["id"], f"{label}.id")
        if artifact_id in artifact_ids_seen:
            raise ValueError(f"duplicate identifier: {artifact_id!r}")
        artifact_ids_seen.add(artifact_id)
        kind = item["kind"]
        if not isinstance(kind, str) or kind not in _ARTIFACT_KINDS:
            raise ValueError(f"{label}.kind is not a supported artifact kind")
        path = _portable_relative_path(item["path"])
        path_key = _artifact_path_key(path)
        if path_key in path_keys:
            raise ValueError(f"duplicate artifact path: {path!r}")
        path_keys.add(path_key)
        artifact = Artifact(artifact_id, kind, path)
        artifacts.append(artifact)
        artifacts_by_id[artifact_id] = artifact

    raw_pages = root["pages"]
    if not isinstance(raw_pages, list) or not raw_pages or len(raw_pages) > _MAX_PAGES:
        raise ValueError(f"pages must be a non-empty list with at most {_MAX_PAGES} entries")
    pages: list[WorkspacePage] = []
    page_ids_seen: set[str] = set()
    component_ids_seen: set[str] = set()
    total_components = 0
    for page_index, raw_page in enumerate(raw_pages):
        page_label = f"pages[{page_index}]"
        page_data = _object(raw_page, page_label, {"id", "title", "components"})
        page_id = _identifier(page_data["id"], f"{page_label}.id")
        if page_id in page_ids_seen:
            raise ValueError(f"duplicate identifier: {page_id!r}")
        page_ids_seen.add(page_id)
        page_title = _text(page_data["title"], f"{page_label}.title", maximum=_MAX_TITLE_LENGTH)
        raw_components = page_data["components"]
        if (
            not isinstance(raw_components, list)
            or not raw_components
            or len(raw_components) > _MAX_COMPONENTS_PER_PAGE
        ):
            raise ValueError(
                f"{page_label}.components must be a non-empty list with at most "
                f"{_MAX_COMPONENTS_PER_PAGE} entries"
            )
        components: list[Component] = []
        for component_index, raw_component in enumerate(raw_components):
            label = f"{page_label}.components[{component_index}]"
            item = _object(
                raw_component,
                label,
                {"id", "kind", "title", "artifact_ids"},
            )
            component_id = _identifier(item["id"], f"{label}.id")
            if component_id in component_ids_seen:
                raise ValueError(f"duplicate identifier: {component_id!r}")
            component_ids_seen.add(component_id)
            kind = item["kind"]
            if not isinstance(kind, str) or kind not in _COMPONENT_ARTIFACTS:
                raise ValueError(f"{label} has an unsupported component kind")
            title = _text(item["title"], f"{label}.title", maximum=_MAX_TITLE_LENGTH)
            artifact_ids = _string_list(
                item["artifact_ids"], f"{label}.artifact_ids", maximum=_MAX_ARTIFACTS
            )
            if len(set(artifact_ids)) != len(artifact_ids):
                raise ValueError(f"{label}.artifact_ids contains a duplicate reference")
            compatible_kinds = _COMPONENT_ARTIFACTS[kind]
            if compatible_kinds is not None and not artifact_ids:
                raise ValueError(f"{label} requires at least one compatible artifact")
            for artifact_id in artifact_ids:
                artifact = artifacts_by_id.get(artifact_id)
                if artifact is None:
                    raise ValueError(f"{label} references an undeclared artifact {artifact_id!r}")
                if compatible_kinds is not None and artifact.kind not in compatible_kinds:
                    raise ValueError(
                        f"{label} binds incompatible artifact kind {artifact.kind!r}"
                    )
            components.append(Component(component_id, kind, title, artifact_ids))
            total_components += 1
            if total_components > _MAX_COMPONENTS:
                raise ValueError(f"workspace components exceed {_MAX_COMPONENTS}")
        pages.append(WorkspacePage(page_id, page_title, tuple(components)))

    return ScientificWorkspace(_SCHEMA_VERSION, model, tuple(artifacts), tuple(pages))


def resolve_artifact_path(project_root: str | os.PathLike[str], relative_path: str) -> Path:
    """Resolve a safe manifest path and reject existing symlink/junction escapes.

    The return value is a path, not a secure file handle. Callers that read
    concurrently mutable, untrusted project trees need an OS-level open policy
    that prevents symlink replacement between this check and the file open.
    """
    safe_path = _portable_relative_path(relative_path)
    try:
        root = Path(project_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("project root must be an existing directory")
        candidate = root.joinpath(*safe_path.split("/")).resolve(strict=False)
        candidate.relative_to(root)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("artifact path does not resolve within the project root") from exc
    return candidate
