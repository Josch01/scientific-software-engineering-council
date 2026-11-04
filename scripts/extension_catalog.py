#!/usr/bin/env python3
"""Validate metadata for pinned, reviewed extensions without loading code."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_CATALOG_BYTES = 1_048_576
MAX_EXTENSION_COUNT = 1000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STABLE_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PERMISSIONS = frozenset(
    {"read_project", "write_project", "run_process", "network", "secrets_access"}
)


class CatalogValidationError(ValueError):
    """Raised when bounded local catalog metadata is invalid."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


class _DuplicateJsonKeyError(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _object(value: Any, path: str, required: set[str], errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return None
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required)
    for key in missing:
        errors.append(f"{path}.{key} is required")
    for key in extra:
        errors.append(f"{path}.{key} is not allowed")
    return value


def _text(value: Any, path: str, errors: list[str], *, maximum: int = 256) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        errors.append(f"{path} must be non-empty text of at most {maximum} characters")
        return None
    if any(ord(char) < 32 for char in value):
        errors.append(f"{path} must not contain control characters")
        return None
    return value.strip()


def _digest(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        errors.append(f"{path} must be a lowercase SHA-256 digest")


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _STABLE_VERSION.fullmatch(value)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _commit(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        errors.append(f"{path} must be a full lowercase 40-character commit hash")


def _text_list(value: Any, path: str, errors: list[str], *, minimum: int = 0) -> list[str] | None:
    if not isinstance(value, list) or len(value) < minimum or len(value) > 64:
        errors.append(f"{path} must be a list with {minimum} to 64 entries")
        return None
    normalized: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, f"{path}[{index}]", errors, maximum=64)
        if text is None:
            continue
        if _TOKEN.fullmatch(text) is None:
            errors.append(f"{path}[{index}] must be a lowercase identifier")
        if text in normalized:
            errors.append(f"{path} contains duplicate value {text!r}")
        normalized.append(text)
    return normalized


def _validate_source(value: Any, path: str, errors: list[str]) -> None:
    source = _object(value, path, {"url", "commit", "sha256"}, errors)
    if source is None:
        return
    url = _text(source.get("url"), f"{path}.url", errors, maximum=2048)
    if url is not None:
        try:
            parsed = urlsplit(url)
            port = parsed.port
            valid = (
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and (port is None or 1 <= port <= 65535)
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            errors.append(f"{path}.url must be an HTTPS source URL without credentials, query, or fragment")
    _commit(source.get("commit"), f"{path}.commit", errors)
    _digest(source.get("sha256"), f"{path}.sha256", errors)


def _validate_rollback(value: Any, path: str, current_version: str | None, current_commit: Any,
                       current_digest: Any, errors: list[str]) -> None:
    rollback = _object(value, path, {"version", "commit", "sha256"}, errors)
    if rollback is None:
        return
    version = _text(rollback.get("version"), f"{path}.version", errors, maximum=64)
    rollback_version = _version_tuple(version) if version is not None else None
    if version is not None and rollback_version is None:
        errors.append(f"{path}.version must be a stable MAJOR.MINOR.PATCH version")
    commit = rollback.get("commit")
    _commit(commit, f"{path}.commit", errors)
    digest = rollback.get("sha256")
    _digest(digest, f"{path}.sha256", errors)
    current_tuple = _version_tuple(current_version) if current_version is not None else None
    if rollback_version is not None and current_tuple is not None and rollback_version >= current_tuple:
        errors.append(f"{path}.version must identify an earlier release")
    if isinstance(current_commit, str) and commit == current_commit:
        errors.append(f"{path}.commit must differ from the current source pin")
    if isinstance(current_digest, str) and digest == current_digest:
        errors.append(f"{path}.sha256 must differ from the current artifact digest")


def _validate_review(value: Any, path: str, maintainer: str | None, errors: list[str]) -> None:
    review = _object(value, path, {"status", "reviewer", "reviewed_at", "report_sha256"}, errors)
    if review is None:
        return
    if review.get("status") != "approved":
        errors.append(f"{path}.status must be 'approved' for catalog inclusion")
    reviewer = _text(review.get("reviewer"), f"{path}.reviewer", errors, maximum=120)
    if reviewer is not None and maintainer is not None and reviewer.casefold() == maintainer.casefold():
        errors.append(f"{path}.reviewer must be independent of the maintainer")
    reviewed_at = _text(review.get("reviewed_at"), f"{path}.reviewed_at", errors, maximum=32)
    if reviewed_at is not None:
        raw_timestamp = review.get("reviewed_at")
        if raw_timestamp != reviewed_at or _UTC_TIMESTAMP.fullmatch(reviewed_at) is None:
            errors.append(f"{path}.reviewed_at must be an RFC 3339 UTC timestamp ending in Z")
        else:
            try:
                datetime.strptime(reviewed_at, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                errors.append(f"{path}.reviewed_at must be an RFC 3339 UTC timestamp ending in Z")
    _digest(review.get("report_sha256"), f"{path}.report_sha256", errors)


def _validate_extension(value: Any, index: int, errors: list[str]) -> str | None:
    path = f"extensions[{index}]"
    required = {
        "id", "name", "version", "source", "maintainer", "license",
        "capabilities", "permissions", "review", "rollback",
    }
    entry = _object(value, path, required, errors)
    if entry is None:
        return None

    identifier = _text(entry.get("id"), f"{path}.id", errors, maximum=64)
    if identifier is not None and _IDENTIFIER.fullmatch(identifier) is None:
        errors.append(f"{path}.id must be a lowercase kebab-case identifier")
    _text(entry.get("name"), f"{path}.name", errors, maximum=160)
    version = _text(entry.get("version"), f"{path}.version", errors, maximum=64)
    if version is not None and _version_tuple(version) is None:
        errors.append(f"{path}.version must be a stable MAJOR.MINOR.PATCH version")
    _validate_source(entry.get("source"), f"{path}.source", errors)
    maintainer = _text(entry.get("maintainer"), f"{path}.maintainer", errors, maximum=120)
    _text(entry.get("license"), f"{path}.license", errors, maximum=128)

    capabilities = _text_list(entry.get("capabilities"), f"{path}.capabilities", errors, minimum=1)
    if capabilities is not None and any(_TOKEN.fullmatch(item) is None for item in capabilities):
        errors.append(f"{path}.capabilities entries must be lowercase identifiers")
    permissions = _text_list(entry.get("permissions"), f"{path}.permissions", errors)
    if permissions is not None:
        for permission in permissions:
            if permission not in _PERMISSIONS:
                errors.append(f"{path}.permissions contains unsupported value {permission!r}")

    _validate_review(entry.get("review"), f"{path}.review", maintainer, errors)
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    _validate_rollback(
        entry.get("rollback"), f"{path}.rollback", version,
        source.get("commit"), source.get("sha256"), errors,
    )
    return identifier


def validate_catalog(value: Any) -> list[str]:
    """Return bounded structural errors; never loads or executes catalog entries."""
    errors: list[str] = []
    catalog = _object(value, "catalog", {"schema_version", "extensions"}, errors)
    if catalog is None:
        return errors
    if type(catalog.get("schema_version")) is not int or catalog.get("schema_version") != 1:
        errors.append("catalog.schema_version must be integer 1")
    extensions = catalog.get("extensions")
    if not isinstance(extensions, list) or len(extensions) > MAX_EXTENSION_COUNT:
        errors.append(f"catalog.extensions must be a list of at most {MAX_EXTENSION_COUNT} entries")
        return errors
    identifiers: set[str] = set()
    for index, extension in enumerate(extensions):
        identifier = _validate_extension(extension, index, errors)
        if identifier is not None:
            if identifier in identifiers:
                errors.append(f"extensions contains duplicate id {identifier!r}")
            identifiers.add(identifier)
    return errors


def load_catalog(path: Path) -> dict[str, Any]:
    """Read and validate a bounded UTF-8 JSON catalog from a local path."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CATALOG_BYTES + 1)
    except OSError as exc:
        raise CatalogValidationError([f"cannot read catalog: {exc}"]) from exc
    if len(raw) > MAX_CATALOG_BYTES:
        raise CatalogValidationError([f"catalog exceeds {MAX_CATALOG_BYTES} bytes"])
    try:
        decoded = raw.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKeyError, RecursionError) as exc:
        raise CatalogValidationError([f"catalog must be valid UTF-8 JSON: {exc}"]) from exc
    errors = validate_catalog(value)
    if errors:
        raise CatalogValidationError(errors)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate SSEC extension catalog metadata only.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate a local JSON catalog")
    validate.add_argument("catalog", type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
    except CatalogValidationError as exc:
        print("INVALID_METADATA")
        for error in exc.errors[:64]:
            print(f"- {error}")
        return 2
    print(
        f"VALID_METADATA_ONLY: {len(catalog['extensions'])} extension(s); "
        "no download, installation, or execution performed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
