"""Provider-neutral contracts and a deterministic runtime test double."""

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RuntimeRequest:
    run_id: str
    task_id: str
    role: str
    prompt: str
    cwd: Path
    stdout_path: Path
    stderr_path: Path
    timeout_seconds: float
    writable: bool
    cost_acknowledged: bool

    def __post_init__(self) -> None:
        if not self.run_id or not self.task_id or not self.role:
            raise ValueError("run_id, task_id, and role must be non-empty")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if "\0" in self.prompt:
            raise ValueError("prompt must not contain NUL")


class RuntimeCapabilityStatus(Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RuntimeCapabilities:
    provider: str
    available: bool
    version: str | None
    features: tuple[str, ...]
    sandbox_effective: bool | None
    native_subagents: RuntimeCapabilityStatus


class RuntimeStatus(Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class RuntimeHandle:
    token: str
    run_id: str
    provider: str
    process_id: int | None


@dataclass(frozen=True)
class RuntimeResult:
    schema_version: int
    run_id: str
    provider: str
    status: RuntimeStatus
    exit_code: int | None
    provider_session_id: str | None
    stdout_path: Path
    stderr_path: Path
    stdout_sha256: str
    stderr_sha256: str
    started_at_utc: str
    finished_at_utc: str
    observed_child_agent_ids: tuple[str, ...]
    error: str | None


class AgentRuntime(Protocol):
    def discover_capabilities(self) -> RuntimeCapabilities: ...

    def launch(self, request: RuntimeRequest) -> RuntimeHandle: ...

    def stream_or_collect(self, handle: RuntimeHandle) -> RuntimeResult: ...

    def cancel(self, handle: RuntimeHandle) -> RuntimeResult: ...

    def timeout(self, handle: RuntimeHandle) -> RuntimeResult: ...

    def status(self, handle: RuntimeHandle) -> RuntimeStatus: ...

    def cleanup(self, handle: RuntimeHandle) -> None: ...


class FakeRuntime:
    """Deterministic in-memory runtime; it never represents a provider session."""

    _STARTED_AT = "2000-01-01T00:00:00+00:00"
    _FINISHED_AT = "2000-01-01T00:00:01+00:00"

    def __init__(self, status_transitions: tuple[RuntimeStatus, ...] = ()) -> None:
        self.invocations: list[tuple[str, object]] = []
        self._requests: dict[str, RuntimeRequest] = {}
        self._statuses: dict[str, RuntimeStatus] = {}
        self._terminal_results: dict[str, RuntimeResult] = {}
        self._cleaned: set[str] = set()
        self._transitions = list(status_transitions)
        self._transition_index = 0

    def discover_capabilities(self) -> RuntimeCapabilities:
        self.invocations.append(("discover_capabilities", None))
        return RuntimeCapabilities(
            provider="fake", available=True, version=None, features=(),
            sandbox_effective=None,
            native_subagents=RuntimeCapabilityStatus.UNKNOWN,
        )

    def launch(self, request: RuntimeRequest) -> RuntimeHandle:
        self.invocations.append(("launch", request))
        token = f"fake:{request.run_id}"
        handle = RuntimeHandle(token, request.run_id, "fake", None)
        self._requests[token] = request
        initial = (self._transitions[0] if self._transitions else RuntimeStatus.RUNNING)
        self._statuses[token] = initial
        if self._transitions:
            self._transition_index = 1
        return handle

    def stream_or_collect(self, handle: RuntimeHandle) -> RuntimeResult:
        self.invocations.append(("stream_or_collect", handle))
        status = self._next_status(handle, RuntimeStatus.SUCCEEDED)
        return self._result(handle, status)

    def cancel(self, handle: RuntimeHandle) -> RuntimeResult:
        self.invocations.append(("cancel", handle))
        if self._statuses[handle.token] is RuntimeStatus.RUNNING:
            self._statuses[handle.token] = RuntimeStatus.CANCELLED
        return self._result(handle, self._statuses[handle.token])

    def timeout(self, handle: RuntimeHandle) -> RuntimeResult:
        self.invocations.append(("timeout", handle))
        if self._statuses[handle.token] is RuntimeStatus.RUNNING:
            self._statuses[handle.token] = RuntimeStatus.TIMED_OUT
        return self._result(handle, self._statuses[handle.token])

    def status(self, handle: RuntimeHandle) -> RuntimeStatus:
        self.invocations.append(("status", handle))
        return self._statuses[handle.token]

    def cleanup(self, handle: RuntimeHandle) -> None:
        if handle.token not in self._cleaned:
            self.invocations.append(("cleanup", handle))
            self._cleaned.add(handle.token)

    def _next_status(self, handle: RuntimeHandle, default: RuntimeStatus) -> RuntimeStatus:
        current = self._statuses[handle.token]
        if current is not RuntimeStatus.RUNNING:
            return current
        if self._transition_index < len(self._transitions):
            status = self._transitions[self._transition_index]
            self._transition_index += 1
        else:
            status = default
        self._statuses[handle.token] = status
        return status

    def _result(self, handle: RuntimeHandle, status: RuntimeStatus) -> RuntimeResult:
        if handle.token in self._terminal_results:
            return self._terminal_results[handle.token]
        request = self._requests[handle.token]
        result = RuntimeResult(
            schema_version=1, run_id=handle.run_id, provider="fake", status=status,
            exit_code=0 if status is RuntimeStatus.SUCCEEDED else None,
            provider_session_id=None, stdout_path=request.stdout_path,
            stderr_path=request.stderr_path, stdout_sha256="", stderr_sha256="",
            started_at_utc=self._STARTED_AT, finished_at_utc=self._FINISHED_AT,
            observed_child_agent_ids=(), error=None,
        )
        if status is not RuntimeStatus.RUNNING:
            self._terminal_results[handle.token] = result
        return result
