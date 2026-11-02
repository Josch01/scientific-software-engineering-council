"""Explicit CLI adapters. Help discovery detects flags, never sandbox enforcement.

JSONL contracts: openai/codex codex-rs/exec/src/exec_events.rs and Gemini
CLI docs/cli/headless plus packages/cli/src/__snapshots__/nonInteractiveCli.test.ts.snap.
Offline parser fixtures do not establish provider integration or paid-session evidence.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from scripts.agent_runtime import (
    AgentRuntime, RuntimeCapabilities, RuntimeCapabilityStatus, RuntimeHandle,
    RuntimeRequest, RuntimeResult, RuntimeStatus,
)
from scripts.run_agents import _terminate_tree


# A path remains owned for this process's lifetime, including after cleanup or
# deletion of its logs. Completed evidence must never be relabelled by another run.
_OWNED_OUTPUT_PATHS: set[Path] = set()
_OUTPUT_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    event: dict = {}
    for key, value in pairs:
        if key in event:
            raise ValueError("Duplicate JSON key")
        event[key] = value
    return event


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


@dataclass
class _Run:
    request: RuntimeRequest
    started_at: str
    started_clock: float
    process: subprocess.Popen | None = None
    result: RuntimeResult | None = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)


class _CliRuntime:
    provider: str
    _help_args: tuple[str, ...]
    _required_help: tuple[str, ...]

    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}
        self._command: tuple[str, ...] | None = None
        self._capabilities: RuntimeCapabilities | None = None
        self._discovery_lock = threading.Lock()

    def _resolve_command(self) -> tuple[str, ...] | None:
        executable = shutil.which(self.provider)
        if not executable:
            return None
        path = Path(executable)
        if path.suffix.lower() not in (".cmd", ".bat"):
            return (executable,)
        # Windows can invoke batch files through cmd.exe despite shell=False.
        # Never send a batch shim to any subprocess boundary.
        if sys.platform != "win32" or self.provider != "gemini":
            return None
        script = path.parent / "node_modules" / "@google" / "gemini-cli" / "bundle" / "gemini.js"
        node = shutil.which("node.exe")
        if (not node or Path(node).suffix.lower() != ".exe"
                or not Path(node).is_file() or not script.is_file()):
            return None
        return (node, str(script))

    def _reserve_outputs(self, request: RuntimeRequest) -> None:
        paths = (request.stdout_path, request.stderr_path)
        canonical = tuple(path.resolve() for path in paths)
        with _OUTPUT_LOCK:
            if canonical[0] == canonical[1]:
                raise ValueError("stdout and stderr must use distinct output paths")
            if any(path.exists() or path.is_symlink() for path in paths):
                raise ValueError("Output paths must not already exist")
            if any(path in _OWNED_OUTPUT_PATHS for path in canonical):
                raise ValueError("Output path is already owned by another run")
            _OWNED_OUTPUT_PATHS.update(canonical)

    def discover_capabilities(self) -> RuntimeCapabilities:
        """Only bounded version/help probes; no credential or model access."""
        with self._discovery_lock:
            if self._capabilities is None:
                self._capabilities = self._discover_capabilities()
            return self._capabilities

    def _discover_capabilities(self) -> RuntimeCapabilities:
        self._command = self._resolve_command()
        version = None
        features: tuple[str, ...] = ()
        available = False
        if self._command:
            try:
                version_result = subprocess.run(
                    (*self._command, "--version"), shell=False, timeout=5,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )
                help_result = subprocess.run(
                    (*self._command, *self._help_args), shell=False, timeout=5,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )
                if version_result.returncode == 0:
                    version = version_result.stdout.strip() or None
                help_text = help_result.stdout
                available = (version_result.returncode == help_result.returncode == 0
                             and all(re.search(r"(?<![\w-])" + re.escape(flag)
                                               + r"(?![\w-])", help_text)
                                     for flag in self._required_help))
                if available:
                    features = self._required_help
            except (OSError, subprocess.TimeoutExpired):
                pass
        return RuntimeCapabilities(
            provider=self.provider, available=available, version=version,
            features=features, sandbox_effective=None,
            native_subagents=RuntimeCapabilityStatus.UNKNOWN,
        )

    def build_argv(self, request: RuntimeRequest) -> tuple[str, ...]:
        raise NotImplementedError

    def launch(self, request: RuntimeRequest) -> RuntimeHandle:
        if not request.cost_acknowledged:
            raise ValueError("Provider launch requires cost_acknowledged")
        available = self.discover_capabilities().available
        if available:
            self._reserve_outputs(request)
        handle = RuntimeHandle(uuid.uuid4().hex, request.run_id, self.provider, None)
        run = _Run(request, _utc_now(), time.monotonic())
        self._runs[handle.token] = run
        if not available:
            self._finish(run, RuntimeStatus.UNAVAILABLE, "Selected CLI or required flags unavailable")
            return handle
        argv = (*self._command, *self.build_argv(request)[1:])
        try:
            # File-backed output avoids pipe deadlocks and unbounded in-memory logs.
            with request.stdout_path.open("xb") as stdout, request.stderr_path.open("xb") as stderr:
                run.process = subprocess.Popen(
                    argv, cwd=request.cwd, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, shell=False,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
        except OSError as exc:
            self._finish(run, RuntimeStatus.UNAVAILABLE, str(exc))
            return handle
        return RuntimeHandle(handle.token, request.run_id, self.provider, run.process.pid)

    def _lookup(self, handle: RuntimeHandle) -> _Run:
        run = self._runs[handle.token]
        if handle.provider != self.provider or handle.run_id != run.request.run_id:
            raise ValueError("Handle does not belong to this runtime")
        return run

    def stream_or_collect(self, handle: RuntimeHandle) -> RuntimeResult:
        run = self._lookup(handle)
        with run.lock:
            if run.result is not None:
                return run.result
            remaining = max(0, run.request.timeout_seconds - (time.monotonic() - run.started_clock))
        # A collector must not prevent another thread from stopping the process.
        try:
            run.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return self.timeout(handle)
        return self._finish(run)

    def cancel(self, handle: RuntimeHandle) -> RuntimeResult:
        return self._stop(handle, RuntimeStatus.CANCELLED)

    def timeout(self, handle: RuntimeHandle) -> RuntimeResult:
        return self._stop(handle, RuntimeStatus.TIMED_OUT)

    def _stop(self, handle: RuntimeHandle, status: RuntimeStatus) -> RuntimeResult:
        run = self._lookup(handle)
        with run.lock:
            if run.result is not None:
                return run.result
            if run.process.poll() is not None:
                return self._finish(run)
            # Serialize kill/reap and publication: a waiting collector cannot
            # publish FAILED between process death and the requested stop result.
            stop_error = None
            try:
                _terminate_tree(run.process)
            except (OSError, subprocess.TimeoutExpired) as exc:
                stop_error = f"Tree termination UNVERIFIED: {exc}"
            try:
                run.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as exc:
                stop_error = stop_error or f"Tree termination UNVERIFIED: {exc}"
                try:
                    run.process.kill()
                    run.process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired) as retry_exc:
                    stop_error += f"; direct-process reap unconfirmed: {retry_exc}"
            if stop_error is not None:
                return self._finish(run, RuntimeStatus.FAILED, stop_error,
                                    evidence_stable=False)
            return self._finish(run, status, status.value)

    def status(self, handle: RuntimeHandle) -> RuntimeStatus:
        run = self._lookup(handle)
        with run.lock:
            if run.result is not None:
                return run.result.status
            if run.process.poll() is not None:
                return self._finish(run).status
            if time.monotonic() - run.started_clock >= run.request.timeout_seconds:
                return self.timeout(handle).status
            return RuntimeStatus.RUNNING

    def cleanup(self, handle: RuntimeHandle) -> None:
        run = self._lookup(handle)
        with run.lock:
            if run.result is None:
                self.cancel(handle)

    def _parse(self, path: Path) -> tuple[str | None, tuple[str, ...], str | None]:
        session_id = None
        children: list[str] = []
        terminal = False
        error = None
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    event = json.loads(line, object_pairs_hook=_json_object,
                                       parse_constant=_invalid_constant)
                    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                        raise ValueError("JSONL event must be an object with a type")
                    kind = event["type"]
                    session_kind, session_field = (("thread.started", "thread_id")
                                                  if self.provider == "codex" else ("init", "session_id"))
                    if kind == session_kind:
                        value = event.get(session_field)
                        if not isinstance(value, str) or not value:
                            raise ValueError("Invalid provider session ID")
                        if session_id is not None and session_id != value:
                            raise ValueError("Conflicting provider session IDs")
                        session_id = value
                    if kind == "error" or (self.provider == "codex" and kind == "turn.failed"):
                        # Conservative: even a warning cannot certify a successful run.
                        error = "Provider emitted an error event"
                    if self.provider == "codex":
                        if kind == "turn.started":
                            terminal = False
                        if kind == "turn.completed":
                            if not isinstance(event.get("usage"), dict):
                                raise ValueError("Malformed turn.completed event")
                            terminal = True
                        if kind in ("item.started", "item.updated", "item.completed"):
                            item = event.get("item")
                            if not isinstance(item, dict):
                                raise ValueError("Malformed item event")
                            if (kind == "item.completed" and item.get("type") == "collab_tool_call"
                                    and item.get("tool") == "spawn_agent"
                                    and item.get("status") == "completed"):
                                ids = item.get("receiver_thread_ids")
                                if not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids):
                                    raise ValueError("Malformed child-agent IDs")
                                for child in ids:
                                    if child not in children:
                                        children.append(child)
                    else:
                        if kind == "message" and (not isinstance(event.get("content"), str)
                                                   or event.get("role") not in ("user", "assistant")):
                            raise ValueError("Malformed message event")
                        if kind == "result":
                            if event.get("status") != "success" or event.get("error"):
                                error = "Provider result was not successful"
                            elif not isinstance(event.get("stats"), dict):
                                raise ValueError("Malformed result event")
                            terminal = True
        except (OSError, UnicodeError, ValueError) as exc:
            error = f"Invalid JSONL output: {exc}"
        if not terminal and error is None:
            error = "Missing successful terminal event"
        # Reconcile only after parsing: spawn may precede the parent session event.
        return session_id, tuple(child for child in children if child != session_id), error

    def _finish(self, run: _Run, status: RuntimeStatus | None = None,
                error: str | None = None, *, evidence_stable: bool = True) -> RuntimeResult:
        with run.lock:
            if run.result is not None:
                return run.result
            return self._publish_result(run, status, error, evidence_stable)

    def _publish_result(self, run: _Run, status: RuntimeStatus | None,
                        error: str | None, evidence_stable: bool) -> RuntimeResult:
        """Called with the per-run lock held; publish exactly once."""
        # Existing paths cannot serve as evidence for a CLI that never started.
        session_id, children, parse_error = (self._parse(run.request.stdout_path)
                                              if run.process is not None and evidence_stable
                                              else (None, (), None))
        exit_code = run.process.returncode if run.process else None
        if status is None:
            error = parse_error or (f"Provider exited with code {exit_code}" if exit_code != 0 else None)
            status = RuntimeStatus.FAILED if error else RuntimeStatus.SUCCEEDED

        def digest(path: Path) -> str:
            if not evidence_stable or run.process is None or not path.exists():
                return ""
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

        run.result = RuntimeResult(
            schema_version=1, run_id=run.request.run_id, provider=self.provider,
            status=status, exit_code=exit_code, provider_session_id=session_id,
            stdout_path=run.request.stdout_path, stderr_path=run.request.stderr_path,
            stdout_sha256=digest(run.request.stdout_path), stderr_sha256=digest(run.request.stderr_path),
            started_at_utc=run.started_at, finished_at_utc=_utc_now(),
            observed_child_agent_ids=children, error=error,
        )
        return run.result


class CodexRuntime(_CliRuntime):
    provider = "codex"
    _help_args = ("exec", "--help")
    _required_help = ("--json", "--sandbox", "read-only", "workspace-write")

    def build_argv(self, request: RuntimeRequest) -> tuple[str, ...]:
        return ("codex", "exec", "--json", "--sandbox",
                "workspace-write" if request.writable else "read-only", "--", request.prompt)


class GeminiRuntime(_CliRuntime):
    """Requests CLI sandboxing; this does not guarantee a read-only workspace."""

    provider = "gemini"
    _help_args = ("--help",)
    _required_help = ("--prompt", "--output-format", "stream-json", "--sandbox", "--approval-mode", "default")

    def build_argv(self, request: RuntimeRequest) -> tuple[str, ...]:
        return ("gemini", "--sandbox", "--approval-mode", "default",
                "--output-format", "stream-json", "--prompt=" + request.prompt)


def create_runtime(provider: str) -> AgentRuntime:
    """Provider selection is explicit and never substitutes another runtime."""
    if provider == "codex":
        return CodexRuntime()
    if provider == "gemini":
        return GeminiRuntime()
    raise ValueError(f"Unsupported runtime provider: {provider!r}")
