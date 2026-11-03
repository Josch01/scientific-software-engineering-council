"""Load declared workspace resources only after safe-open and digest checks."""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
import ctypes
import hashlib
import json
import ntpath
import os
from pathlib import Path
import stat
import sys
from dataclasses import dataclass
from typing import BinaryIO, Iterator

try:
    from . import scientific_workspace as manifest_api
except ImportError:  # Support direct execution: python scripts/scientific_workspace_loader.py
    import scientific_workspace as manifest_api


MAX_RESOURCE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_WINDOWS_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_LOADER_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class LoadedResource:
    """A declared artifact captured as immutable bytes after digest validation."""

    resource_id: str
    kind: str
    path: str
    sha256: str
    content: bytes

    def __init__(
        self,
        resource_id: str,
        kind: str,
        path: str,
        sha256: str,
        content: bytes,
        *,
        _loader_token: object | None = None,
    ) -> None:
        if _loader_token is not _LOADER_TOKEN:
            raise TypeError("verified resource records can only be created by the loader")
        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "sha256", sha256)
        object.__setattr__(self, "content", content)


@dataclass(frozen=True, slots=True, init=False)
class LoadedWorkspace:
    """Validated workspace metadata and all-or-nothing verified resources."""

    summary: manifest_api.WorkspaceSummary
    resources: tuple[LoadedResource, ...]

    def __init__(
        self,
        summary: manifest_api.WorkspaceSummary,
        resources: tuple[LoadedResource, ...],
        *,
        _loader_token: object | None = None,
    ) -> None:
        if _loader_token is not _LOADER_TOKEN:
            raise TypeError("verified workspaces can only be created by the loader")
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "resources", resources)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "ARTIFACT_DIGESTS_MATCHED",
            "schema_version": 1,
            "workspace_id": self.summary.workspace_id,
            "title": self.summary.title,
            "resource_count": len(self.resources),
            "total_bytes": sum(len(resource.content) for resource in self.resources),
            "resources": [
                {
                    "id": resource.resource_id,
                    "kind": resource.kind,
                    "path": resource.path,
                    "sha256": resource.sha256,
                    "byte_count": len(resource.content),
                }
                for resource in self.resources
            ],
        }


def _path_segments(value: object, label: str) -> tuple[str, ...]:
    path, _ = manifest_api._portable_path(value, label)
    return tuple(path.split("/"))


def _validate_budget(value: int, maximum: int, label: str) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{label} must be an integer between 0 and {maximum}")
    return value


def _read_limited(stream: BinaryIO, limit: int, label: str) -> bytes:
    """Read at most limit+1 bytes so oversized/growing files fail boundedly."""
    result = bytearray()
    while len(result) <= limit:
        requested = min(_READ_CHUNK_BYTES, limit + 1 - len(result))
        chunk = stream.read(requested)
        if not chunk:
            break
        result.extend(chunk)
    if len(result) > limit:
        raise ValueError(f"{label} exceeds the {limit}-byte read limit")
    return bytes(result)


def _normal_windows_path(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return ntpath.normcase(ntpath.normpath(path))


def _windows_paths_contained(root_path: str, candidate_path: str) -> bool:
    normalized_root = _normal_windows_path(root_path)
    normalized_candidate = _normal_windows_path(candidate_path)
    try:
        return ntpath.commonpath((normalized_root, normalized_candidate)) == normalized_root
    except ValueError:
        return False


def _windows_final_path(fd: int) -> str:
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_final_path.restype = wintypes.DWORD
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
    capacity = 512
    while capacity <= 32768:
        buffer = ctypes.create_unicode_buffer(capacity)
        length = get_final_path(handle, buffer, capacity, 0)
        if length == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        if length < capacity:
            return buffer.value
        capacity = length + 1
    raise OSError("final Windows path exceeds the supported buffer")


def _assert_windows_contained(root: Path, fd: int, segments: tuple[str, ...]) -> None:
    for index in range(1, len(segments) + 1):
        component = root.joinpath(*segments[:index])
        try:
            info = component.lstat()
        except FileNotFoundError:
            # The final handle check below is authoritative if the path races.
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT:
            raise ValueError("resource path contains a symlink or Windows reparse point")

    if not _windows_paths_contained(str(root), _windows_final_path(fd)):
        raise ValueError("opened resource resolves outside the project root")


@contextmanager
def _open_project_file(project_root: str | os.PathLike[str], relative_path: object) -> Iterator[BinaryIO]:
    """Open one regular file inside root; keep the checked descriptor open."""
    segments = _path_segments(relative_path, "project-relative path")
    try:
        root = Path(project_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as exc:
        raise ValueError("project root must resolve to an existing directory") from exc
    if not root.is_dir():
        raise ValueError("project root must be an existing directory")

    if os.name == "nt":
        candidate = root.joinpath(*segments)
        try:
            stream = candidate.open("rb", buffering=0)
        except OSError as exc:
            raise ValueError(f"cannot open project resource {relative_path!r}: {exc}") from exc
        try:
            _assert_windows_contained(root, stream.fileno(), segments)
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("project resources must be regular files")
            yield stream
        finally:
            stream.close()
        return

    required_flags = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if os.open not in os.supports_dir_fd or any(not hasattr(os, name) for name in required_flags):
        raise ValueError("safe descriptor-relative loading is unsupported on this platform")
    directory_flag = os.O_DIRECTORY
    common_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    root_fd: int | None = None
    parent_fd: int | None = None
    try:
        root_fd = os.open(root, os.O_RDONLY | directory_flag | os.O_CLOEXEC)
        parent_fd = root_fd
        for segment in segments[:-1]:
            next_fd = os.open(
                segment,
                common_flags | directory_flag | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            if parent_fd != root_fd:
                os.close(parent_fd)
            parent_fd = next_fd
        file_fd = os.open(
            segments[-1],
            common_flags | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
        stream = os.fdopen(file_fd, "rb", buffering=0)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ValueError("project resources must be regular files")
            yield stream
        finally:
            stream.close()
    except OSError as exc:
        raise ValueError(f"cannot safely open project resource {relative_path!r}: {exc}") from exc
    finally:
        if parent_fd is not None and parent_fd != root_fd:
            os.close(parent_fd)
        if root_fd is not None:
            os.close(root_fd)


def _parse_and_validate(raw: bytes) -> tuple[Mapping[str, object], manifest_api.WorkspaceSummary]:
    payload = manifest_api.parse_workspace_manifest_bytes(raw)
    summary = manifest_api.validate_workspace_manifest(payload)
    return payload, summary


def load_scientific_workspace(
    project_root: str | os.PathLike[str],
    manifest_relative_path: str,
    *,
    max_resource_bytes: int = MAX_RESOURCE_BYTES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> LoadedWorkspace:
    """Securely load all declared resource bytes after containment and SHA-256 checks.

    Budget arguments may reduce the defaults, never increase them. Any failure
    aborts the load and returns no partially verified workspace.
    """
    per_resource_limit = _validate_budget(max_resource_bytes, MAX_RESOURCE_BYTES, "max_resource_bytes")
    total_limit = _validate_budget(max_total_bytes, MAX_TOTAL_BYTES, "max_total_bytes")

    with _open_project_file(project_root, manifest_relative_path) as stream:
        manifest_bytes = _read_limited(stream, manifest_api._MAX_MANIFEST_BYTES, "manifest")
    payload, summary = _parse_and_validate(manifest_bytes)
    raw_resources = payload["resources"]
    if not isinstance(raw_resources, Sequence) or isinstance(raw_resources, (str, bytes)):
        raise ValueError("resources must be a sequence")
    for index, item in enumerate(raw_resources):
        if not isinstance(item, Mapping) or "sha256" not in item:
            raise ValueError(f"resources[{index}] requires a SHA-256 digest before loading")

    loaded: list[LoadedResource] = []
    total_bytes = 0
    for item in raw_resources:
        assert isinstance(item, Mapping)
        resource_id = item["id"]
        kind = item["kind"]
        path = item["path"]
        expected_digest = item["sha256"]
        remaining = total_limit - total_bytes
        effective_limit = min(per_resource_limit, remaining)
        with _open_project_file(project_root, path) as stream:
            content = _read_limited(stream, effective_limit, f"resource {resource_id!r}")
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(f"resource {resource_id!r} SHA-256 does not match the manifest")
        loaded.append(
            LoadedResource(
                resource_id,
                kind,
                path,
                actual_digest,
                content,
                _loader_token=_LOADER_TOKEN,
            )
        )
        total_bytes += len(content)

    return LoadedWorkspace(summary, tuple(loaded), _loader_token=_LOADER_TOKEN)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, help="project directory that contains all inputs")
    parser.add_argument("manifest", help="portable project-relative path to the workspace manifest")
    arguments = parser.parse_args(argv)
    try:
        loaded = load_scientific_workspace(arguments.project_root, arguments.manifest)
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(loaded.to_dict(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
