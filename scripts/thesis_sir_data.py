"""Strict adapter for the selected 56-week series in the DGE reconstruction JSON."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

try:
    from .thesis_sir_model import WeeklyCountObservations
except ImportError:  # Support direct import from the scripts directory.
    from thesis_sir_model import WeeklyCountObservations


_MAX_SOURCE_BYTES = 1_048_576
_EXPECTED_ROWS = 56
_SERIES_ID = "DGE_monday_sunday_candidate"
_WEEK_LABEL = re.compile(r"^(?P<year>\d{4})-SE(?P<week>\d{1,2})$")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_json_constant(token: str) -> object:
    raise ValueError(f"non-finite JSON number {token!r} is not allowed")


def _week_order(label: object, index: int) -> tuple[int, int]:
    if not isinstance(label, str):
        raise ValueError(f"week_by_week_comparison[{index}].week must be a string")
    match = _WEEK_LABEL.fullmatch(label)
    if match is None:
        raise ValueError(f"week_by_week_comparison[{index}].week has invalid format")
    year, week = int(match.group("year")), int(match.group("week"))
    if not 1 <= week <= 53:
        raise ValueError(f"week_by_week_comparison[{index}].week number is out of range")
    return year, week


def parse_dge_reconstruction_json(payload: bytes | str) -> WeeklyCountObservations:
    """Load only the thesis-aligned candidate series; never substitute a sibling column."""
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        try:
            raw = payload.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("reconstruction JSON must be valid UTF-8") from exc
    else:
        raise ValueError("reconstruction JSON must be bytes or text")
    if not raw or len(raw) > _MAX_SOURCE_BYTES:
        raise ValueError("reconstruction JSON must be nonempty and at most 1 MiB")
    try:
        text = raw.decode("utf-8-sig")
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid reconstruction JSON: {exc}") from exc
    if not isinstance(document, Mapping):
        raise ValueError("reconstruction JSON root must be an object")
    window = document.get("target_window")
    if not isinstance(window, Mapping):
        raise ValueError("reconstruction JSON target_window must be an object")
    if type(window.get("n_weeks")) is not int or window["n_weeks"] != _EXPECTED_ROWS:
        raise ValueError("reconstruction target_window must declare exactly 56 weeks")
    rows = document.get("week_by_week_comparison")
    if not isinstance(rows, list) or len(rows) != _EXPECTED_ROWS:
        raise ValueError("week_by_week_comparison must contain exactly 56 rows")

    labels: list[str] = []
    counts: list[int] = []
    previous: tuple[int, int] | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"week_by_week_comparison[{index}] must be an object")
        label = row.get("week")
        order = _week_order(label, index)
        if previous is not None:
            year, week = order
            previous_year, previous_week = previous
            contiguous = (
                (year == previous_year and week == previous_week + 1)
                or (
                    year == previous_year + 1
                    and previous_week in (52, 53)
                    and week == 1
                )
            )
            if not contiguous:
                raise ValueError("weekly labels must be contiguous and chronological")
        previous = order
        count = row.get(_SERIES_ID)
        if type(count) is not int or count < 0:
            raise ValueError(
                f"week_by_week_comparison[{index}].{_SERIES_ID} must be a nonnegative integer"
            )
        labels.append(label)
        counts.append(count)

    if window.get("first_week") != labels[0] or window.get("last_week") != labels[-1]:
        raise ValueError("target_window endpoints must match the selected series labels")
    return WeeklyCountObservations(
        week_labels=tuple(labels),
        counts=tuple(counts),
        series_id=_SERIES_ID,
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )
