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
import stat
import subprocess
import sys
import threading
import time
import uuid

from scripts.agent_runtime import (
    AgentRuntime, RuntimeCapabilities, RuntimeCapabilityStatus, RuntimeHandle,
    RuntimeLaunchControl, RuntimeRequest, RuntimeResult, RuntimeStatus,
)
from scripts.run_agents import _terminate_tree
from scripts.process_containment import new_containment as _new_containment


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
    containment: object | None = None
    containment_quiesced: bool = False
    cleanup_error: str | None = None
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
                if self.provider == "agy":
                    # agy.EXE 1.5.0 writes its help table to stderr with exit 0.
                    help_text += "\n" + (help_result.stderr or "")
                available = (version_result.returncode == help_result.returncode == 0
                             and all(re.search(r"(?<![\w-])" + re.escape(flag)
                                               + r"(?![\w-])", help_text)
                                     for flag in self._required_help))
                if available:
                    features = (*self._required_help, *self._additional_features(help_text))
            except (OSError, subprocess.TimeoutExpired):
                pass
        return RuntimeCapabilities(
            provider=self.provider, available=available, version=version,
            features=features, sandbox_effective=None,
            native_subagents=RuntimeCapabilityStatus.UNKNOWN,
        )

    def _additional_features(self, _help_text: str) -> tuple[str, ...]:
        return ()

    def build_argv(self, request: RuntimeRequest) -> tuple[str, ...]:
        raise NotImplementedError

    def launch(self, request: RuntimeRequest) -> RuntimeHandle:
        if not request.cost_acknowledged:
            raise ValueError("Provider launch requires cost_acknowledged")
        started_clock = time.monotonic()
        started_at = _utc_now()
        control = request.launch_control or RuntimeLaunchControl(
            threading.Event(), started_clock + request.timeout_seconds)
        available = self.discover_capabilities().available
        if available:
            self._reserve_outputs(request)
        handle = RuntimeHandle(uuid.uuid4().hex, request.run_id, self.provider, None)
        run = _Run(request, started_at, started_clock)
        self._runs[handle.token] = run
        if not available:
            self._finish(run, RuntimeStatus.UNAVAILABLE, "Selected CLI or required flags unavailable")
            return handle
        argv = (*self._command, *self.build_argv(request)[1:])
        try:
            run.containment = _new_containment()
            # File-backed output avoids pipe deadlocks and unbounded in-memory logs.
            with request.stdout_path.open("xb") as stdout, request.stderr_path.open("xb") as stderr:
                # Preparation I/O stays outside the gate so stop can be recorded
                # while it blocks. Only final authorization and creation are atomic.
                with control.gate:
                    blocked = control.blocked_status()
                    if blocked is None and time.monotonic() >= started_clock + request.timeout_seconds:
                        blocked = RuntimeStatus.TIMED_OUT
                    if blocked is not None:
                        self._finish(run, blocked, blocked.value)
                        return handle
                    run.process = subprocess.Popen(
                        argv, cwd=request.cwd, stdin=subprocess.DEVNULL,
                        stdout=stdout, stderr=stderr, shell=False,
                        creationflags=run.containment.creationflags,
                        start_new_session=os.name != "nt",
                    )
                    run.containment.attach(run.process)
        except OSError as exc:
            if run.process is not None:
                if run.containment.requires_unreaped_root is not True:
                    try:
                        run.process.kill()
                        run.process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                self._finish(run, RuntimeStatus.FAILED,
                             f"Containment setup UNVERIFIED: {exc}", evidence_stable=False)
            else:
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
            run.containment.wait_for_root(run.process, remaining)
        except subprocess.TimeoutExpired:
            return self.timeout(handle)
        except OSError as exc:
            return self._finish(run, RuntimeStatus.FAILED,
                                f"Root observation UNVERIFIED: {exc}", evidence_stable=False)
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
            try:
                if run.containment.root_exited(run.process):
                    return self._finish(run)
            except OSError as exc:
                return self._finish(run, RuntimeStatus.FAILED,
                                    f"Root observation UNVERIFIED: {exc}", evidence_stable=False)
            if run.containment.requires_unreaped_root is True:
                # POSIX quiescence owns signalling and the sole final reap.
                # The legacy helper/poll/wait path could release the PGID early.
                return self._finish(run, status, status.value)
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
            try:
                if run.containment.root_exited(run.process):
                    return self._finish(run).status
            except OSError as exc:
                return self._finish(run, RuntimeStatus.FAILED,
                                    f"Root observation UNVERIFIED: {exc}", evidence_stable=False).status
            if time.monotonic() - run.started_clock >= run.request.timeout_seconds:
                return self.timeout(handle).status
            return RuntimeStatus.RUNNING

    def cleanup(self, handle: RuntimeHandle) -> None:
        run = self._lookup(handle)
        with run.lock:
            if run.result is None:
                self.cancel(handle)
            if run.containment is not None:
                try:
                    if not run.containment_quiesced and run.process is not None:
                        run.containment.quiesce(run.process)
                        run.containment_quiesced = True
                    run.containment.close()
                except (OSError, subprocess.TimeoutExpired) as exc:
                    run.cleanup_error = f"Containment cleanup UNVERIFIED: {exc}"
                    raise OSError(run.cleanup_error) from exc
                run.cleanup_error = None

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
                    if self.provider == "agy":
                        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                            raise ValueError("AGY JSONL event must contain an event name")
                        kind = event["event"]
                        if terminal:
                            raise ValueError("AGY emitted events after its terminal result")
                        if kind == "init":
                            value = event.get("conversation_id")
                            if (not isinstance(value, str) or not value
                                    or not isinstance(event.get("init"), dict)
                                    or session_id is not None):
                                raise ValueError("Malformed or duplicate AGY init event")
                            session_id = value
                        elif kind == "step_update":
                            step = event.get("step_update")
                            if (session_id is None or not isinstance(step, dict)
                                    or step.get("conversation_id") != session_id
                                    or type(step.get("step_index")) is not int
                                    or step.get("state") not in ("ACTIVE", "DONE")
                                    or not isinstance(step.get("step_type"), str)):
                                raise ValueError("Malformed AGY step_update event")
                            subagent_info = step.get("subagent_info")
                            if subagent_info is not None:
                                agents = subagent_info.get("subagents") if isinstance(subagent_info, dict) else None
                                if not isinstance(agents, list):
                                    raise ValueError("Malformed AGY subagent information")
                                for agent in agents:
                                    child = agent.get("conversation_id") if isinstance(agent, dict) else None
                                    if not isinstance(child, str) or not child:
                                        raise ValueError("Malformed AGY subagent conversation ID")
                                    if child not in children:
                                        children.append(child)
                        elif kind == "result":
                            result = event.get("result")
                            if (session_id is None or not isinstance(result, dict)
                                    or result.get("conversation_id") != session_id
                                    or not isinstance(result.get("response"), str)):
                                raise ValueError("Malformed AGY result event")
                            if result.get("status") != "SUCCESS" or result.get("error"):
                                error = "AGY result was not successful"
                            elif not result["response"].strip():
                                error = "AGY result contained no response"
                            terminal = True
                        else:
                            raise ValueError("Unsupported AGY stream event")
                        continue
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
            # Every terminal path, including natural root exit, must stop and
            # confirm residual members before parsing or hashing inherited logs.
            if run.containment is not None:
                try:
                    if run.process is not None:
                        warning = run.containment.quiesce(run.process)
                        if isinstance(warning, str) and warning:
                            status, evidence_stable = RuntimeStatus.FAILED, False
                            error = f"{error}; {warning}" if error else warning
                    run.containment_quiesced = True
                except (OSError, subprocess.TimeoutExpired) as exc:
                    status, evidence_stable = RuntimeStatus.FAILED, False
                    detail = f"Containment termination UNVERIFIED ({type(exc).__name__}): {exc}"
                    error = f"{error}; {detail}" if error else detail
                finally:
                    try:
                        run.containment.close()
                    except OSError as exc:
                        status, evidence_stable = RuntimeStatus.FAILED, False
                        error = f"Containment closure UNVERIFIED: {exc}"
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
        if request.tool_policy_path is not None:
            raise RuntimeError(
                "Codex CLI cannot enforce the workspace proposal no-execution tool policy"
            )
        return ("codex", "exec", "--json", "--sandbox",
                "workspace-write" if request.writable else "read-only", "--", request.prompt)


class GeminiRuntime(_CliRuntime):
    """Requests CLI sandboxing; this does not guarantee a read-only workspace."""

    provider = "gemini"
    _help_args = ("--help",)
    _required_help = ("--prompt", "--output-format", "stream-json", "--sandbox", "--approval-mode", "default")

    def _additional_features(self, help_text: str) -> tuple[str, ...]:
        required = ("--admin-policy", "plan")
        return (("proposal_read_only_tool_policy",)
                if all(re.search(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])", help_text)
                       for flag in required)
                else ())

    def build_argv(self, request: RuntimeRequest) -> tuple[str, ...]:
        if request.tool_policy_path is not None:
            return (
                "gemini", "--sandbox", "--approval-mode", "plan",
                "--admin-policy", str(request.tool_policy_path),
                "--output-format", "stream-json", "--prompt=" + request.prompt,
            )
        return ("gemini", "--sandbox", "--approval-mode", "default",
                "--output-format", "stream-json", "--prompt=" + request.prompt)


class AgyRuntime(_CliRuntime):
    """Antigravity CLI adapter for its documented headless NDJSON contract."""

    provider = "agy"
    _help_args = ("--help",)
    _required_help = ("--prompt", "--output-format", "stream-json", "--sandbox",
                      "--agent", "--mode", "accept-edits", "plan")

    _worker_tools = ("view_file", "grep_search", "replace_file_content", "write_to_file")

    def _validate_local_filesystem_settings(self) -> None:
        """Fail closed if AGY is configured to read or write outside workspaces."""
        directory = Path.home()
        for part in (".gemini", "antigravity-cli"):
            directory = directory / part
            try:
                metadata = directory.lstat()
            except FileNotFoundError:
                return  # AGY's documented default is workspace-only access.
            except OSError as exc:
                raise ValueError("AGY local filesystem settings cannot be checked safely") from exc
            if (stat.S_ISLNK(metadata.st_mode)
                    or getattr(metadata, "st_file_attributes", 0) & 0x400
                    or not stat.S_ISDIR(metadata.st_mode)):
                raise ValueError("AGY local filesystem settings path must be a real directory")

        path = directory / "settings.json"
        try:
            before = path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ValueError("AGY local filesystem settings cannot be checked safely") from exc
        if (stat.S_ISLNK(before.st_mode)
                or getattr(before, "st_file_attributes", 0) & 0x400
                or not stat.S_ISREG(before.st_mode) or before.st_size > 1024 * 1024):
            raise ValueError("AGY local filesystem settings must be a bounded regular file")
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                raw = stream.read(1024 * 1024 + 1)
                after_open = os.fstat(stream.fileno())
            after = path.lstat()
            identity = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                     info.st_mtime_ns, info.st_mode)
            if (identity(before) != identity(opened) or identity(before) != identity(after_open)
                    or identity(before) != identity(after) or len(raw) != before.st_size
                    or getattr(after, "st_file_attributes", 0) & 0x400):
                raise ValueError("settings changed while reading")
            settings = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object,
                                  parse_constant=_invalid_constant)
            if not isinstance(settings, dict):
                raise ValueError("settings root must be an object")
            outside_access = settings.get("allowNonWorkspaceAccess", False)
            if type(outside_access) is not bool:
                raise ValueError("allowNonWorkspaceAccess must be a boolean")
            if outside_access:
                raise ValueError("allowNonWorkspaceAccess must be disabled")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("AGY local filesystem settings are unsafe or invalid") from exc

    def _validate_profile(self, request: RuntimeRequest) -> None:
        role = request.role
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", role):
            raise ValueError("AGY role cannot map to a safe workspace agent name")
        cursor = request.cwd
        for part in (".agents", "agents", "ssec-" + role.replace("_", "-") + ".md"):
            cursor = cursor / part
            try:
                metadata = cursor.lstat()
            except OSError as exc:
                raise ValueError("AGY SSEC profile is missing from the worker worktree") from exc
            if (stat.S_ISLNK(metadata.st_mode)
                    or getattr(metadata, "st_file_attributes", 0) & 0x400):
                raise ValueError("AGY SSEC profile path cannot contain a symlink or reparse point")
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65536:
            raise ValueError("AGY SSEC profile must be a bounded regular file")
        try:
            content = cursor.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError("AGY SSEC profile cannot be read safely") from exc
        if not content.startswith("---\n"):
            raise ValueError("AGY SSEC profile has malformed frontmatter")
        frontmatter, separator, _body = content[4:].partition("\n---\n")
        if not separator:
            raise ValueError("AGY SSEC profile has malformed frontmatter")
        fields: dict[str, str] = {}
        tools: list[str] = []
        in_tools = False
        for line in frontmatter.splitlines():
            if line.startswith("  - ") and in_tools:
                tools.append(line[4:])
            elif line and not line[0].isspace() and ":" in line:
                key, value = line.split(":", 1)
                if key in fields:
                    raise ValueError("AGY SSEC profile frontmatter has duplicate fields")
                fields[key] = value.strip()
                in_tools = key == "tools"
        expected_name = "ssec-" + role.replace("_", "-")
        if (set(fields) != {"name", "description", "mainAgent", "subagent",
                            "tools", "commandExecutionPolicy"}
                or fields["name"] != expected_name or fields["mainAgent"] != "true"
                or fields["subagent"] != "false"
                or fields["commandExecutionPolicy"] != "off"
                or tuple(tools) != self._worker_tools):
            raise ValueError("AGY SSEC profile must restrict the worker to file tools without commands")

    def launch(self, request: RuntimeRequest) -> RuntimeHandle:
        if not request.cost_acknowledged:
            raise ValueError("Provider launch requires cost_acknowledged")
        if not request.writable:
            raise ValueError("AGY adapter is enabled only for scoped implementation workers")
        if request.tool_policy_path is not None:
            raise RuntimeError("AGY cannot enforce the SSEC external no-execution policy")
        self._validate_profile(request)
        self._validate_local_filesystem_settings()
        return super().launch(request)

    def build_argv(self, request: RuntimeRequest) -> tuple[str, ...]:
        if request.tool_policy_path is not None:
            raise RuntimeError("AGY cannot enforce the SSEC external no-execution policy")
        if not request.writable:
            raise ValueError("AGY adapter is enabled only for scoped implementation workers")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", request.role):
            raise ValueError("AGY role cannot map to a safe workspace agent name")
        mode = "accept-edits" if request.writable else "plan"
        return (
            "agy", "--agent", "ssec-" + request.role.replace("_", "-"),
            "--mode", mode, "--sandbox", "--output-format", "stream-json",
            "--prompt=" + request.prompt,
        )


def create_runtime(provider: str) -> AgentRuntime:
    """Provider selection is explicit and never substitutes another runtime."""
    if provider == "codex":
        return CodexRuntime()
    if provider == "gemini":
        return GeminiRuntime()
    if provider == "agy":
        return AgyRuntime()
    raise ValueError(f"Unsupported runtime provider: {provider!r}")
