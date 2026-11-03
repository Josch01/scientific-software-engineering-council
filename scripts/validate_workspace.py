#!/usr/bin/env python3
"""Validate an inert scientific workspace manifest and emit normalized JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    from .scientific_workspace import validate_workspace
except ImportError:  # Support direct execution from the scripts directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scientific_workspace import validate_workspace


_MAX_MANIFEST_BYTES = 2 * 1024 * 1024


def _read_bounded(source: str) -> str:
    stream = sys.stdin.buffer if source == "-" else Path(source).open("rb")
    should_close = source != "-"
    try:
        raw = stream.read(_MAX_MANIFEST_BYTES + 1)
    finally:
        if should_close:
            stream.close()
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ValueError(f"manifest exceeds {_MAX_MANIFEST_BYTES} bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("manifest must be UTF-8 encoded") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        help="UTF-8 JSON manifest path, or '-' to read from standard input",
    )
    args = parser.parse_args(argv)
    try:
        text = _read_bounded(args.manifest)
        data = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        workspace = validate_workspace(data)
    except json.JSONDecodeError as exc:
        parser.error(f"invalid JSON: {exc.msg}")
    except (OSError, RecursionError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.write(
        json.dumps(workspace.to_dict(), ensure_ascii=True, indent=2, allow_nan=False)
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
