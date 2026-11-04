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
        if (type(event) is not dict or
                ("type" in event and "event" in event) or
                type(event.get("type", event.get("event"))) is not str):
            raise ValueError(f"reviewer JSONL line {line_number} must be an unambiguous event object")
        if "event" in event:
            event = {**event, "type": event["event"]}
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


def _extract_agy(events: list[dict[str, object]]) -> str:
    response: str | None = None
    conversation_id: str | None = None
    initialized = False
    terminal = False

    def bind(value: object) -> None:
        nonlocal conversation_id
        if type(value) is not str or not value:
            raise ValueError("AGY reviewer conversation ID is invalid")
        if conversation_id is not None and conversation_id != value:
            raise ValueError("AGY reviewer conversation IDs do not match")
        conversation_id = value

    for event in events:
        if terminal:
            raise ValueError("AGY reviewer emitted events after its terminal event")
        if "event" not in event:
            raise ValueError("AGY reviewer output does not use the AGY event protocol")
        kind = event["event"]
        if kind == "init":
            if initialized:
                raise ValueError("AGY reviewer emitted multiple init events")
            if type(event.get("init")) is not dict:
                raise ValueError("AGY reviewer init event is malformed")
            bind(event.get("conversation_id"))
            initialized = True
        elif kind == "step_update":
            update = event.get("step_update")
            if not initialized or type(update) is not dict:
                raise ValueError("AGY reviewer step_update event is malformed or out of order")
            update_id = update.get("conversation_id")
            if update_id is not None:
                bind(update_id)
        elif kind == "result":
            result = event.get("result")
            if not initialized or type(result) is not dict:
                raise ValueError("AGY reviewer result event is malformed or out of order")
            event_id = event.get("conversation_id")
            result_id = result.get("conversation_id")
            if event_id is not None:
                bind(event_id)
            if result_id is not None:
                bind(result_id)
            if conversation_id is None:
                raise ValueError("AGY reviewer terminal event has no conversation ID")
            if result.get("status") != "SUCCESS" or result.get("error"):
                raise ValueError("AGY reviewer result was not successful")
            candidate = result.get("response")
            if type(candidate) is not str or not candidate.strip():
                raise ValueError("AGY reviewer assistant response is empty or malformed")
            if type(result.get("usage")) is not dict:
                raise ValueError("AGY reviewer terminal event is malformed")
            if response is not None:
                raise ValueError("AGY reviewer response is ambiguous")
            response = candidate
            terminal = True
        else:
            raise ValueError("AGY reviewer emitted an unsupported event")
    if not initialized or not terminal or response is None:
        raise ValueError("AGY reviewer output has no bound successful terminal event")
    _validate_response_size(response)
    return response


def _validate_response_size(response: str) -> None:
    if len(response.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        raise ValueError("reviewer response is too large")


def extract_final_response(provider: str, stdout_path: Path, *,
                           runtime_adapter_type: str | None = None) -> str:
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
        if runtime_adapter_type not in (None, "scripts.provider_runtimes.CodexRuntime"):
            raise ValueError("unsupported Codex reviewer runtime adapter")
        return _extract_codex(events)
    if runtime_adapter_type in (None, "scripts.provider_runtimes.GeminiRuntime"):
        return _extract_gemini(events)
    if runtime_adapter_type == "scripts.provider_runtimes.AgyGeminiRuntime":
        return _extract_agy(events)
    raise ValueError("unsupported Gemini reviewer runtime adapter")
