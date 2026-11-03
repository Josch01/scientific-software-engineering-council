"""Strict extraction of one terminal provider response from reviewer JSONL.

This module only extracts text. It does not validate a review report, establish
reviewer independence, or turn a provider transcript into acceptance evidence.
"""

from __future__ import annotations

import json
from pathlib import Path


_MAX_LOG_BYTES = 16 * 1024 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _read_log(path: Path) -> list[dict[str, object]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("reviewer output must be a regular non-symlink file")
    try:
        with path.open("rb") as stream:
            raw = stream.read(_MAX_LOG_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"reviewer output could not be read: {exc}") from exc
    if len(raw) > _MAX_LOG_BYTES:
        raise ValueError("reviewer output is too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("reviewer output is not valid UTF-8") from exc

    events: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line, object_pairs_hook=_unique_object,
                               parse_constant=_invalid_constant)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid reviewer JSONL at line {line_number}: {exc}") from exc
        if type(event) is not dict or type(event.get("type")) is not str:
            raise ValueError(f"reviewer JSONL line {line_number} must be an event object")
        events.append(event)
    if not events:
        raise ValueError("reviewer output is empty")
    return events


def _extract_codex(events: list[dict[str, object]]) -> str:
    response: str | None = None
    terminal = False
    for event in events:
        kind = event["type"]
        if kind == "error" or kind == "turn.failed":
            raise ValueError("Codex reviewer emitted a failed event")
        if kind == "turn.started":
            if terminal:
                raise ValueError("Codex reviewer emitted events after its terminal event")
        elif kind == "turn.completed":
            if terminal:
                raise ValueError("Codex reviewer emitted multiple terminal events")
            if type(event.get("usage")) is not dict:
                raise ValueError("Codex reviewer terminal event is malformed")
            if response is None:
                raise ValueError("Codex reviewer completed without an assistant response")
            terminal = True
        elif kind in ("item.started", "item.updated", "item.completed"):
            if terminal:
                raise ValueError("Codex reviewer emitted events after its terminal event")
            item = event.get("item")
            if type(item) is not dict:
                raise ValueError("Codex reviewer item event is malformed")
            if kind == "item.completed" and item.get("type") == "agent_message":
                text = item.get("text")
                if type(text) is not str or not text.strip():
                    raise ValueError("Codex reviewer assistant response is empty or malformed")
                if response is not None:
                    raise ValueError("Codex reviewer response is ambiguous")
                response = text
    if not terminal:
        raise ValueError("Codex reviewer output has no successful terminal event")
    if response is None:  # Defensive: terminal validation above requires a response.
        raise ValueError("Codex reviewer completed without an assistant response")
    _validate_response_size(response)
    return response


def _extract_gemini(events: list[dict[str, object]]) -> str:
    response: str | None = None
    terminal = False
    for event in events:
        kind = event["type"]
        if kind == "error":
            raise ValueError("Gemini reviewer emitted an error event")
        if kind == "message":
            if terminal:
                raise ValueError("Gemini reviewer emitted events after its terminal event")
            role, content = event.get("role"), event.get("content")
            if role not in ("user", "assistant") or type(content) is not str:
                raise ValueError("Gemini reviewer message event is malformed")
            if role == "assistant":
                if not content.strip():
                    raise ValueError("Gemini reviewer assistant response is empty")
                if response is not None:
                    raise ValueError("Gemini reviewer response is ambiguous")
                response = content
        elif kind == "result":
            if terminal:
                raise ValueError("Gemini reviewer emitted multiple terminal events")
            if event.get("status") != "success" or event.get("error"):
                raise ValueError("Gemini reviewer result was not successful")
            if type(event.get("stats")) is not dict:
                raise ValueError("Gemini reviewer terminal event is malformed")
            if response is None:
                raise ValueError("Gemini reviewer completed without an assistant response")
            terminal = True
    if not terminal:
        raise ValueError("Gemini reviewer output has no successful terminal event")
    if response is None:  # Defensive: terminal validation above requires a response.
        raise ValueError("Gemini reviewer completed without an assistant response")
    _validate_response_size(response)
    return response


def _validate_response_size(response: str) -> None:
    if len(response.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        raise ValueError("reviewer response is too large")


def extract_final_response(provider: str, stdout_path: Path) -> str:
    """Extract exactly one assistant response followed by provider success.

    The strict single-response rule fails closed when the provider transcript
    contains multiple candidate final answers. A returned string is still only
    untrusted provider output; callers must validate its report schema and bind
    it to independently observed runtime evidence.
    """
    if provider not in {"codex", "gemini"}:
        raise ValueError(f"unsupported reviewer provider: {provider}")
    events = _read_log(Path(stdout_path))
    if provider == "codex":
        return _extract_codex(events)
    return _extract_gemini(events)
