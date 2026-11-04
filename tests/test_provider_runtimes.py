"""Offline parser/contract tests; JSONL fixtures are not provider E2E evidence."""

from dataclasses import replace
import hashlib
import errno
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.agent_runtime import RuntimeCapabilities, RuntimeCapabilityStatus, RuntimeRequest, RuntimeStatus


class OfflineContainment:
    """No OS handles: parser/contract process doubles have no actual descendants."""
    creationflags = 0
    requires_unreaped_root = False

    def root_exited(self, process):
        return process.poll() is not None

    def wait_for_root(self, process, timeout):
        return process.wait(timeout=timeout)

    def attach(self, process):
        pass

    def quiesce(self, process):
        pass

    def close(self):
        pass


class ProviderRuntimeTests(unittest.TestCase):
    def setUp(self):
        # Missing implementation is an explicit RED assertion, not an import error.
        self.assertIsNotNone(importlib.util.find_spec("scripts.provider_runtimes"),
                             "provider runtime adapters are not implemented")
        from scripts import provider_runtimes
        self.module = provider_runtimes
        self.real_containment_factory = getattr(self.module, "_new_containment", None)
        containment = patch.object(self.module, "_new_containment", side_effect=OfflineContainment, create=True)
        containment.start()
        self.addCleanup(containment.stop)
        # Offline process doubles must never reach OS tree-termination commands.
        termination = patch.object(self.module, "_terminate_tree", side_effect=lambda process: process.kill(), create=True)
        termination.start()
        self.addCleanup(termination.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.request = RuntimeRequest(
            "run-1", "task-1", "reviewer", "--prompt ; $(echo unsafe) 日本語",
            root, root / "stdout.jsonl", root / "stderr.log", 30, False, True,
        )

    def help_text(self, provider):
        return ("--json --sandbox read-only workspace-write" if provider == "codex"
                else "--prompt --output-format stream-json --sandbox "
                     "--approval-mode default plan --admin-policy")

    def discovery(self, provider, help_text=None):
        def run(argv, **kwargs):
            self.assertFalse(kwargs["shell"])
            self.assertGreater(kwargs["timeout"], 0)
            self.assertLessEqual(kwargs["timeout"], 5)
            self.assertEqual(argv[0], f"/selected/{provider}")
            self.assertIn(tuple(argv[1:]), (("--version",), ("--help",), ("exec", "--help")))
            return subprocess.CompletedProcess(argv, 0, "1.2.3" if argv[-1] == "--version"
                                               else (help_text if help_text is not None
                                                     else self.help_text(provider)), "")
        return patch.object(self.module.subprocess, "run", side_effect=run)

    def launch_fixture(self, provider, events, exit_code=0, wait_error=None, process_setup=None):
        # Every parser fixture represents a separate run with fresh evidence paths.
        root = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.request = replace(self.request, stdout_path=root / "stdout.jsonl",
                               stderr_path=root / "stderr.log")
        runtime = self.module.create_runtime(provider)
        payload = events if isinstance(events, bytes) else (
            "\n".join(json.dumps(event) for event in events) + "\n").encode()
        process = Mock(pid=1234, returncode=exit_code)
        process.wait.side_effect = wait_error
        process.wait.return_value = exit_code
        process.poll.return_value = None
        if process_setup is not None:
            process_setup(process)

        def spawn(argv, **kwargs):
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["cwd"], self.request.cwd)
            kwargs["stdout"].write(payload)
            kwargs["stdout"].flush()
            kwargs["stderr"].write(b"diagnostic")
            kwargs["stderr"].flush()
            return process

        with patch.object(self.module.shutil, "which", return_value=f"/selected/{provider}"), \
                self.discovery(provider), patch.object(self.module.subprocess, "Popen", side_effect=spawn):
            handle = runtime.launch(self.request)
        self.assertEqual(handle.provider, provider)
        return runtime, handle, process

    def collect_fixture(self, provider, events, exit_code=0, wait_error=None):
        runtime, handle, process = self.launch_fixture(provider, events, exit_code, wait_error)
        return runtime, handle, runtime.stream_or_collect(handle), process

    def test_explicit_provider_factory_rejects_unknown_instead_of_falling_back(self):
        self.assertIsInstance(self.module.create_runtime("codex"), self.module.CodexRuntime)
        self.assertIsInstance(self.module.create_runtime("gemini"), self.module.GeminiRuntime)
        for value in ("", "auto", "CODEX", "fake", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.module.create_runtime(value)

    def test_build_argv_is_pure_and_keeps_prompt_one_argument(self):
        with patch.object(self.module.subprocess, "run", side_effect=AssertionError("impure")), \
                patch.object(self.module.subprocess, "Popen", side_effect=AssertionError("impure")), \
                patch.object(self.module.shutil, "which", side_effect=AssertionError("impure")):
            runtime = self.module.CodexRuntime()
            readonly = runtime.build_argv(self.request)
            writable = runtime.build_argv(replace(self.request, writable=True))
            self.assertIsInstance(readonly, tuple)
            self.assertEqual(readonly[readonly.index("--sandbox") + 1], "read-only")
            self.assertEqual(writable[writable.index("--sandbox") + 1], "workspace-write")
            self.assertEqual(readonly[-2:], ("--", self.request.prompt))
            self.assertIn("--json", readonly)
            gemini = self.module.GeminiRuntime().build_argv(self.request)
            self.assertIn("--sandbox", gemini)
            self.assertEqual(gemini[gemini.index("--approval-mode") + 1], "default")
            self.assertEqual(gemini[gemini.index("--output-format") + 1], "stream-json")
            self.assertEqual(gemini[-1], "--prompt=" + self.request.prompt)
            self.assertNotIn("yolo", " ".join(gemini))
            # A prompt starting with a flag must stay a value in yargs.
            hostile = self.module.GeminiRuntime().build_argv(replace(self.request, prompt="--yolo"))
            self.assertNotIn("--yolo", hostile)
            self.assertIn("--prompt=--yolo", hostile)

    def test_proposal_runtime_enforces_gemini_plan_policy_and_rejects_codex(self):
        policy_path = Path(self.temp.name) / "proposal-policy.toml"
        policy_path.write_text("deny all tools", encoding="utf-8")
        proposal_request = replace(self.request, tool_policy_path=policy_path)

        argv = self.module.GeminiRuntime().build_argv(proposal_request)
        self.assertEqual(argv[argv.index("--approval-mode") + 1], "plan")
        self.assertIn("--sandbox", argv)
        self.assertEqual(argv[argv.index("--admin-policy") + 1], str(policy_path))
        self.assertEqual(argv[-1], "--prompt=" + proposal_request.prompt)
        with self.assertRaisesRegex(RuntimeError, "no-execution"):
            self.module.CodexRuntime().build_argv(proposal_request)

    def test_gemini_read_only_proposal_capability_requires_plan_and_admin_policy_flags(self):
        runtime = self.module.GeminiRuntime()
        self.assertIn("proposal_read_only_tool_policy",
                      runtime._additional_features(self.help_text("gemini")))
        self.assertNotIn("proposal_read_only_tool_policy",
                         runtime._additional_features("--approval-mode default --sandbox"))

    def test_cost_acknowledgement_is_required_before_discovery_or_spawn(self):
        for provider in ("codex", "gemini"):
            with self.subTest(provider=provider), \
                    patch.object(self.module.subprocess, "Popen") as spawn, \
                    patch.object(self.module.subprocess, "run") as discover:
                with self.assertRaises(ValueError):
                    self.module.create_runtime(provider).launch(
                        replace(self.request, cost_acknowledged=False))
                spawn.assert_not_called()
                discover.assert_not_called()
        self.assertFalse(self.request.stdout_path.exists())

    def test_discovery_is_bounded_and_does_not_prove_sandbox_or_subagents(self):
        for provider in ("codex", "gemini"):
            with self.subTest(provider=provider), \
                    patch.object(self.module.shutil, "which", return_value=f"/selected/{provider}"), \
                    self.discovery(provider) as probe, patch.object(self.module.subprocess, "Popen") as spawn:
                caps = self.module.create_runtime(provider).discover_capabilities()
                self.assertTrue(caps.available)
                self.assertEqual(caps.provider, provider)
                self.assertEqual(caps.version, "1.2.3")
                self.assertIsNone(caps.sandbox_effective)
                self.assertEqual(caps.native_subagents, RuntimeCapabilityStatus.UNKNOWN)
                self.assertNotIn("read-only", caps.features if provider == "gemini" else ())
                self.assertEqual(probe.call_count, 2)
                spawn.assert_not_called()

    def test_launch_reuses_cached_discovery_without_repeating_probes(self):
        with patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                self.discovery("codex") as probe, \
                patch.object(self.module.subprocess, "Popen", return_value=Mock(pid=123)):
            runtime = self.module.CodexRuntime()
            first = runtime.discover_capabilities()
            runtime.launch(self.request)
            self.assertIs(runtime.discover_capabilities(), first)
            self.assertEqual(probe.call_count, 2)

    def test_stop_or_deadline_during_output_reservation_prevents_spawn(self):
        from scripts import agent_runtime
        control_type = getattr(agent_runtime, "RuntimeLaunchControl", None)
        self.assertIsNotNone(control_type, "Shared runtime launch control is missing")
        for reason, expected in (("stop", RuntimeStatus.CANCELLED),
                                 ("deadline", RuntimeStatus.TIMED_OUT)):
            with self.subTest(reason=reason):
                root = Path(tempfile.mkdtemp(dir=self.temp.name))
                clock = [0]
                entered = threading.Event()
                release = threading.Event()
                control = control_type(threading.Event(), 10)
                request = replace(self.request, launch_control=control,
                                  stdout_path=root / "out", stderr_path=root / "err")
                runtime = self.module.CodexRuntime()
                original_reserve = runtime._reserve_outputs
                results, errors = [], []
                def reserve(value):
                    entered.set()
                    if not release.wait(5):
                        raise AssertionError("Reservation barrier not released")
                    return original_reserve(value)
                def launch():
                    try:
                        results.append(runtime.launch(request))
                    except BaseException as exc:
                        errors.append(exc)
                with patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                        self.discovery("codex"), patch.object(runtime, "_reserve_outputs", side_effect=reserve), \
                        patch.object(self.module.time, "monotonic", side_effect=lambda: clock[0]), \
                        patch.object(self.module.subprocess, "Popen", return_value=Mock(pid=123)) as spawn:
                    thread = threading.Thread(target=launch, daemon=True)
                    thread.start()
                    try:
                        self.assertTrue(entered.wait(5))
                        if reason == "stop":
                            control.set()
                        else:
                            clock[0] = 11
                    finally:
                        release.set()
                        thread.join(5)
                    self.assertFalse(thread.is_alive(), "Stop recording deadlocked behind reservation")
                    self.assertEqual(errors, [])
                    spawn.assert_not_called()
                    result = runtime.stream_or_collect(results[0])
                    self.assertEqual(result.status, expected)
                    self.assertIsNone(result.provider_session_id)
                    self.assertEqual(result.stdout_sha256, "")

    def test_missing_executable_or_required_help_flags_never_launches_or_falls_back(self):
        for provider in ("codex", "gemini"):
            for executable, help_text in ((None, ""), (f"/selected/{provider}", "--unrelated")):
                with self.subTest(provider=provider, executable=executable), \
                        patch.object(self.module.shutil, "which", return_value=executable) as which, \
                        self.discovery(provider, help_text), patch.object(self.module.subprocess, "Popen") as spawn:
                    runtime = self.module.create_runtime(provider)
                    handle = runtime.launch(self.request)
                    self.assertEqual(runtime.stream_or_collect(handle).status, RuntimeStatus.UNAVAILABLE)
                    self.assertEqual(handle.provider, provider)
                    self.assertTrue(all(call.args == (provider,) for call in which.call_args_list))
                    spawn.assert_not_called()

    def test_probe_timeout_nonzero_and_oserror_are_unavailable(self):
        for failure in (subprocess.TimeoutExpired("help", 5), OSError("missing"), None):
            with self.subTest(failure=failure), \
                    patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                    patch.object(self.module.subprocess, "run", side_effect=failure,
                                 return_value=subprocess.CompletedProcess([], 1, "", "error")):
                self.assertFalse(self.module.CodexRuntime().discover_capabilities().available)

    def test_codex_jsonl_parser_extracts_thread_and_hashes_logs(self):
        runtime, handle, result, _ = self.collect_fixture("codex", [
            {"type": "thread.started", "thread_id": "thread-123"},
            {"type": "item.completed", "item": {"type": "agent_message", "id": "item-0",
                                                     "text": "session_id: spoofed"}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0,
                                                        "output_tokens": 1}},
        ])
        self.assertEqual(result.status, RuntimeStatus.SUCCEEDED)
        self.assertEqual(result.provider_session_id, "thread-123")
        self.assertEqual(result.observed_child_agent_ids, ())
        self.assertEqual(result.stdout_sha256, hashlib.sha256(self.request.stdout_path.read_bytes()).hexdigest())
        self.assertEqual(result.stderr_sha256, hashlib.sha256(b"diagnostic").hexdigest())
        self.assertEqual(result.schema_version, 1)
        self.assertEqual(runtime.status(handle), RuntimeStatus.SUCCEEDED)
        self.assertEqual(runtime.stream_or_collect(handle), result)

    def test_gemini_jsonl_parser_extracts_only_init_session(self):
        _, _, result, _ = self.collect_fixture("gemini", [
            {"type": "init", "timestamp": "2026-01-01T00:00:00Z", "session_id": "gem-123", "model": "test"},
            {"type": "tool_use", "tool_id": "not-an-agent", "tool_name": "task", "parameters": {}},
            {"type": "result", "status": "success", "stats": {}},
        ])
        self.assertEqual(result.status, RuntimeStatus.SUCCEEDED)
        self.assertEqual(result.provider_session_id, "gem-123")
        self.assertEqual(result.observed_child_agent_ids, ())

    def test_codex_child_evidence_requires_successful_spawn_event(self):
        _, _, result, _ = self.collect_fixture("codex", [
            {"type": "item.completed", "item": {"id": "item-1", "type": "collab_tool_call",
                "tool": "spawn_agent", "status": "completed", "sender_thread_id": "parent",
                "receiver_thread_ids": ["child-1"], "agents_states": {}}},
            {"type": "turn.completed", "usage": {}},
        ])
        self.assertEqual(result.observed_child_agent_ids, ("child-1",))
        self.assertIsNone(result.provider_session_id)

    def test_codex_parent_session_is_never_reported_as_child_in_either_event_order(self):
        """Offline JSONL parser regression, not native-subagent E2E evidence."""
        for ids, expected in ((["parent", "child-1"], ("child-1",)), (["parent"], ())):
            spawn = {"type": "item.completed", "item": {
                "id": "item-1", "type": "collab_tool_call", "tool": "spawn_agent",
                "status": "completed", "sender_thread_id": "parent",
                "receiver_thread_ids": ids, "agents_states": {},
            }}
            session = {"type": "thread.started", "thread_id": "parent"}
            for events in ([spawn, session], [session, spawn]):
                with self.subTest(ids=ids, spawn_first=events[0] is spawn):
                    _, _, result, _ = self.collect_fixture("codex", events + [
                        {"type": "turn.completed", "usage": {}},
                    ])
                    self.assertEqual(result.status, RuntimeStatus.SUCCEEDED)
                    self.assertEqual(result.provider_session_id, "parent")
                    self.assertEqual(result.observed_child_agent_ids, expected)

    def test_parser_rejects_malformed_missing_terminal_and_failure_outputs(self):
        cases = {
            "codex": [b"not json\n", b"[]\n", b'{"type":"turn.completed"}\nBAD\n',
                      b'{"type":"turn.completed","usage":{"input_tokens":NaN}}\n',
                      b'{"type":"error","type":"turn.completed","usage":{}}\n',
                      b'{"type":"thread.started","thread_id":"x"}\n',
                      b'{"type":"turn.failed","error":{"message":"bad"}}\n',
                      b'{"type":"error","message":"bad"}\n{"type":"turn.completed","usage":{}}\n',
                      b'{"type":"turn.completed","usage":null}\n'],
            "gemini": [b"not json\n", b"null\n", b'{"type":"init","session_id":"x"}\n',
                       b'{"type":"result","status":"error","error":{"message":"bad"}}\n',
                       b'{"type":"result"}\n',
                       b'{"type":"error","severity":"error","message":"bad"}\n{"type":"result","status":"success","stats":{}}\n'],
        }
        for provider, fixtures in cases.items():
            for fixture in fixtures:
                with self.subTest(provider=provider, fixture=fixture):
                    _, _, result, _ = self.collect_fixture(provider, fixture)
                    self.assertEqual(result.status, RuntimeStatus.FAILED)
                    self.assertTrue(result.error)

    def test_nonzero_exit_cannot_succeed_even_with_success_terminal(self):
        for provider, event in (("codex", {"type": "turn.completed", "usage": {}}),
                                ("gemini", {"type": "result", "status": "success", "stats": {}})):
            with self.subTest(provider=provider):
                _, _, result, _ = self.collect_fixture(provider, [event], exit_code=1)
                self.assertEqual(result.status, RuntimeStatus.FAILED)

    def test_collect_timeout_kills_and_reaps_process(self):
        _, _, result, process = self.collect_fixture(
            "codex", [], wait_error=[subprocess.TimeoutExpired("codex", 30), -9])
        self.assertEqual(result.status, RuntimeStatus.TIMED_OUT)
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    def test_nonzero_windows_taskkill_cannot_confirm_cancellation_or_log_hashes(self):
        from scripts import run_agents
        runtime, handle, process = self.launch_fixture("codex", [
            {"type": "thread.started", "thread_id": "mutable-session"},
            {"type": "turn.completed", "usage": {}},
        ], exit_code=-9)
        with patch.object(self.module, "_terminate_tree", wraps=run_agents._terminate_tree), \
                patch.object(run_agents, "os", SimpleNamespace(name="nt")), \
                patch.object(run_agents.subprocess, "run", return_value=
                             subprocess.CompletedProcess(["taskkill"], 1)) as command:
            result = runtime.cancel(handle)
        self.assertEqual(command.call_args.args[0][0], "taskkill")
        self.assertEqual(result.status, RuntimeStatus.FAILED)
        self.assertIn("UNVERIFIED", result.error)
        self.assertEqual(result.stdout_sha256, "")
        self.assertEqual(result.stderr_sha256, "")
        self.assertIsNone(result.provider_session_id)
        process.kill.assert_called_once()
        self.assertGreater(process.wait.call_args.kwargs["timeout"], 0)
        self.assertIs(runtime.stream_or_collect(handle), result)

    def test_stop_waits_are_bounded_when_direct_process_will_not_exit(self):
        runtime, handle, process = self.launch_fixture("codex", [], exit_code=None)
        def stuck_wait(*args, **kwargs):
            self.assertIn("timeout", kwargs, "Unbounded wait after attempted tree termination")
            self.assertGreater(kwargs["timeout"], 0)
            self.assertLessEqual(kwargs["timeout"], 5)
            raise subprocess.TimeoutExpired("local-double", kwargs["timeout"])
        process.wait.side_effect = stuck_wait
        result = runtime.timeout(handle)
        self.assertEqual(result.status, RuntimeStatus.FAILED)
        self.assertIn("UNVERIFIED", result.error)
        self.assertEqual(result.stdout_sha256, "")
        self.assertEqual(result.stderr_sha256, "")
        self.assertEqual(process.wait.call_count, 2)

    def test_concurrent_stop_and_collection_share_one_terminal_result(self):
        """Offline event-controlled wait race; no subprocess or provider runs."""
        for method, expected in (("cancel", RuntimeStatus.CANCELLED),
                                 ("timeout", RuntimeStatus.TIMED_OUT)):
            with self.subTest(method=method):
                runtime, handle, process = self.launch_fixture("codex", [], exit_code=-9)
                collecting = threading.Event()
                release_collector = threading.Event()
                stopped = threading.Event()
                results = {}
                errors = []

                def controlled_wait(*args, **kwargs):
                    if threading.current_thread().name == "controlled-collector":
                        collecting.set()
                        if not release_collector.wait(5):
                            raise AssertionError("Collector was not released")
                    return -9

                process.wait.side_effect = controlled_wait

                def collect():
                    try:
                        results["collected"] = runtime.stream_or_collect(handle)
                    except BaseException as exc:
                        errors.append(exc)

                def stop():
                    try:
                        results["stopped"] = getattr(runtime, method)(handle)
                    except BaseException as exc:
                        errors.append(exc)
                    finally:
                        stopped.set()

                collector = threading.Thread(target=collect, name="controlled-collector", daemon=True)
                stopper = threading.Thread(target=stop, name="controlled-stopper", daemon=True)
                collector.start()
                try:
                    self.assertTrue(collecting.wait(5), "Collector did not reach process.wait")
                    stopper.start()
                    self.assertTrue(stopped.wait(5), "Stop blocked behind collector wait (deadlock)")
                finally:
                    release_collector.set()
                    collector.join(5)
                    if stopper.ident is not None:
                        stopper.join(5)
                self.assertFalse(collector.is_alive())
                self.assertFalse(stopper.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(results["stopped"].status, expected)
                self.assertIs(results["collected"], results["stopped"])
                self.assertEqual(runtime.status(handle), expected)
                self.assertIs(runtime.stream_or_collect(handle), results["stopped"])
                self.assertIs(runtime.cancel(handle), results["stopped"])
                self.assertIs(runtime.timeout(handle), results["stopped"])
                runtime.cleanup(handle)
                process.kill.assert_called_once()

    def test_local_python_stop_terminates_inherited_child_before_publishing_logs(self):
        """Local process-tree lifecycle only; no provider or sandbox evidence."""
        from scripts.run_agents import _terminate_tree
        root = Path(self.temp.name)
        ready = root / "child.pid"
        marker = root / "child-survived"
        child_code = ("import os,time;from pathlib import Path;"
                      f"Path({str(ready)!r}).write_text(str(os.getpid()));"
                      "print('child-started',flush=True);time.sleep(1);"
                      f"Path({str(marker)!r}).write_text('survived');time.sleep(30)")
        parent_code = ("import subprocess,sys,time;"
                       f"subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
                       "print('parent-started',flush=True);time.sleep(30)")

        class LocalRuntime(self.module.CodexRuntime):
            provider = "local-python"

            def discover_capabilities(inner):
                inner._command = (sys.executable,)
                return RuntimeCapabilities("local-python", True, None, (), None,
                                           RuntimeCapabilityStatus.UNKNOWN)

            def build_argv(inner, request):
                return (sys.executable, "-c", parent_code)

        runtime = LocalRuntime()
        child_pid = None
        with patch.object(self.module, "_terminate_tree", wraps=_terminate_tree), \
                patch.object(self.module, "_new_containment", wraps=self.real_containment_factory):
            handle = runtime.launch(self.request)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists(), "Local child did not start")
                child_pid = int(ready.read_text())
                result = runtime.cancel(handle)
                self.assertEqual(result.status, RuntimeStatus.CANCELLED)
                payload = self.request.stdout_path.read_bytes()
                time.sleep(1.2)
                self.assertFalse(marker.exists(), "Inherited child survived parent cancellation")
                self.assertEqual(self.request.stdout_path.read_bytes(), payload)
                self.assertEqual(result.stdout_sha256, hashlib.sha256(payload).hexdigest())
            finally:
                if child_pid is not None:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(child_pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                    else:
                        try:
                            os.kill(child_pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                runtime.cleanup(handle)

    def test_local_natural_parent_exit_stops_child_before_terminal_log_publication(self):
        """Local Python Codex-shaped JSONL fixture, never provider E2E."""
        for exit_code, resume_failure in ((0, False), (1, False), (0, True)):
            with self.subTest(exit_code=exit_code, resume_failure=resume_failure):
                root = Path(tempfile.mkdtemp(dir=self.temp.name))
                ready, marker = root / "child.pid", root / "late-mutation"
                request = replace(self.request, stdout_path=root / "out", stderr_path=root / "err")
                child_code = ("import os,time;from pathlib import Path;"
                    f"Path({str(ready)!r}).write_text(str(os.getpid()));time.sleep(1);"
                    f"Path({str(marker)!r}).write_text('survived');"
                    "print('LATE MUTATION',flush=True);time.sleep(30)")
                parent_code = ("import subprocess,sys,time,json;from pathlib import Path;"
                    "print(json.dumps({'type':'thread.started','thread_id':'local-parent'}),flush=True);"
                    f"subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
                    f"ready=Path({str(ready)!r});deadline=time.monotonic()+5\n"
                    "while not ready.exists() and time.monotonic()<deadline: time.sleep(.01)\n"
                    "print(json.dumps({'type':'turn.completed','usage':{}}),flush=True)\n"
                    f"sys.exit({exit_code})")
                class LocalRuntime(self.module.CodexRuntime):
                    def discover_capabilities(inner):
                        inner._command = (sys.executable,)
                        return RuntimeCapabilities("codex", True, None, (), None,
                                                   RuntimeCapabilityStatus.UNKNOWN)
                    def build_argv(inner, value):
                        return (sys.executable, "-c", parent_code)
                runtime = LocalRuntime()
                handle = None
                def containment_factory():
                    containment = self.real_containment_factory()
                    original_attach = containment.attach
                    def attach(process):
                        original_attach(process)
                        if resume_failure:
                            deadline = time.monotonic() + 5
                            while not ready.exists() and time.monotonic() < deadline:
                                time.sleep(.01)
                            raise OSError("Injected failure after resume/child startup")
                    containment.attach = attach
                    return containment
                with patch.object(self.module, "_new_containment", side_effect=containment_factory):
                    try:
                        handle = runtime.launch(request)
                        result = runtime.stream_or_collect(handle)
                        self.assertTrue(ready.exists(), "Local child did not start")
                        self.assertEqual(result.status, RuntimeStatus.SUCCEEDED
                                         if exit_code == 0 and not resume_failure else RuntimeStatus.FAILED)
                        payload = request.stdout_path.read_bytes()
                        time.sleep(1.2)
                        self.assertFalse(marker.exists(), "Child survived natural parent exit")
                        self.assertEqual(request.stdout_path.read_bytes(), payload)
                        self.assertEqual(result.stdout_sha256, "" if resume_failure
                                         else hashlib.sha256(payload).hexdigest())
                    finally:
                        if ready.exists():
                            child_pid = int(ready.read_text())
                            if os.name == "nt":
                                subprocess.run(["taskkill", "/PID", str(child_pid), "/T", "/F"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                            else:
                                try:
                                    os.kill(child_pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                        if handle is not None:
                            runtime.cleanup(handle)

    def test_containment_setup_and_quiescence_fail_closed_without_log_evidence(self):
        for failure in ("attach", "quiesce"):
            with self.subTest(failure=failure):
                containment = Mock(wraps=OfflineContainment(), creationflags=0, requires_unreaped_root=False)
                getattr(containment, failure).side_effect = OSError("unconfirmed containment")
                with patch.object(self.module, "_new_containment", return_value=containment):
                    _, _, result, process = self.collect_fixture("codex", [
                        {"type": "turn.completed", "usage": {}},
                    ])
                self.assertEqual(result.status, RuntimeStatus.FAILED)
                self.assertIn("UNVERIFIED", result.error)
                self.assertEqual(result.stdout_sha256, "")
                self.assertEqual(result.stderr_sha256, "")
                self.assertIsNone(result.provider_session_id)
                containment.quiesce.assert_called_once_with(process)
                containment.close.assert_called_once()

    def test_cancel_and_timeout_require_containment_confirmation_before_log_evidence(self):
        for method in ("cancel", "timeout"):
            with self.subTest(method=method):
                containment = Mock(wraps=OfflineContainment(), creationflags=0, requires_unreaped_root=False)
                containment.quiesce.side_effect = OSError("residual member still active")
                with patch.object(self.module, "_new_containment", return_value=containment):
                    runtime, handle, process = self.launch_fixture("codex", [
                        {"type": "turn.completed", "usage": {}},
                    ], exit_code=-9)
                    result = getattr(runtime, method)(handle)
                self.assertEqual(result.status, RuntimeStatus.FAILED)
                self.assertIn("UNVERIFIED", result.error)
                self.assertEqual(result.stdout_sha256, "")
                self.assertEqual(result.stderr_sha256, "")
                containment.quiesce.assert_called_once_with(process)
                containment.close.assert_called_once()
                self.assertIs(runtime.stream_or_collect(handle), result)

    def test_windows_job_close_retains_native_handle_until_close_succeeds(self):
        from scripts.process_containment import WindowsJob
        job = WindowsJob.__new__(WindowsJob)
        job._handle = 123
        job._api = SimpleNamespace(CloseHandle=Mock(side_effect=[OSError("close failed"), 1]))
        with self.assertRaises(OSError):
            job.close()
        self.assertEqual(job._handle, 123)
        job.close()
        self.assertIsNone(job._handle)
        self.assertEqual(job._api.CloseHandle.call_count, 2)

    def test_posix_backend_signals_group_before_reaping_on_every_terminal_path(self):
        """POSIX ordering under kernel/process doubles; safe on any test host."""
        from scripts import process_containment
        for mode in ("collect", "status", "cancel", "timeout", "setup_failure"):
            with self.subTest(mode=mode):
                order = []
                group = process_containment.PosixGroup.__new__(process_containment.PosixGroup)
                state = {"exited": mode in ("collect", "status")}
                def observe(kind, pid, options):
                    self.assertTrue(options & 0x100, "waitid must not reap the root")
                    order.append("observe")
                    return SimpleNamespace(si_pid=pid) if state["exited"] else None
                def signal_group(*args):
                    order.append("signal")
                    state["exited"] = True
                kernel = SimpleNamespace(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=0x100,
                    waitid=Mock(side_effect=observe), killpg=Mock(side_effect=signal_group))
                def process_setup(process):
                    def reap(*args, **kwargs):
                        order.append("reap")
                        return process.returncode
                    process.wait.side_effect = reap
                    process.poll.side_effect = (lambda: reap() if state["exited"] else None)
                if mode == "setup_failure":
                    attach = group.attach
                    def failed_attach(process):
                        attach(process)
                        raise OSError("POSIX setup failure")
                    group.attach = failed_attach
                with patch.object(process_containment, "os", kernel), \
                        patch.object(process_containment, "signal", SimpleNamespace(SIGKILL=9)), \
                        patch.object(group, "_has_live_members", return_value=False), \
                        patch.object(self.module, "_new_containment", return_value=group):
                    runtime, handle, process = self.launch_fixture("codex", [
                        {"type": "turn.completed", "usage": {}},
                    ], process_setup=process_setup)
                    if mode == "status":
                        runtime.status(handle)
                    elif mode in ("cancel", "timeout"):
                        getattr(runtime, mode)(handle)
                    result = runtime.stream_or_collect(handle)
                self.assertIn("signal", order)
                self.assertIn("reap", order)
                self.assertLess(order.index("signal"), order.index("reap"), order)
                self.assertEqual(order.count("signal"), 1)
                self.assertEqual(result.status, {
                    "collect": RuntimeStatus.SUCCEEDED, "status": RuntimeStatus.SUCCEEDED,
                    "cancel": RuntimeStatus.CANCELLED, "timeout": RuntimeStatus.TIMED_OUT,
                    "setup_failure": RuntimeStatus.FAILED}[mode])

    def test_posix_lost_leader_identity_never_signals_a_reused_group(self):
        from scripts import process_containment
        for outcome in (ChildProcessError("root already reaped"),
                        OSError(errno.ECHILD, "no owned child"), SimpleNamespace(si_pid=999)):
            with self.subTest(outcome=outcome):
                group = process_containment.PosixGroup.__new__(process_containment.PosixGroup)
                process = Mock(pid=123)
                group.attach(process)
                observer = Mock(side_effect=outcome) if isinstance(outcome, BaseException) else Mock(return_value=outcome)
                kernel = SimpleNamespace(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=0x100,
                    waitid=observer, killpg=Mock())
                with patch.object(process_containment, "os", kernel), \
                        patch.object(process_containment, "signal", SimpleNamespace(SIGKILL=9)), \
                        patch.object(group, "_has_live_members", return_value=False):
                    with self.assertRaises(OSError):
                        group.quiesce(process)
                kernel.killpg.assert_not_called()
                process.wait.assert_not_called()

    def test_posix_missing_live_group_inspection_blocks_before_spawn(self):
        from scripts import process_containment
        kernel = SimpleNamespace(name="posix", P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=0x100,
                                 waitid=Mock())
        with patch.object(process_containment, "os", kernel), \
                patch.object(process_containment, "Path", return_value=Mock(is_dir=Mock(return_value=False))), \
                patch.object(self.module, "_new_containment", side_effect=process_containment.new_containment), \
                patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                self.discovery("codex"), patch.object(self.module.subprocess, "Popen") as spawn:
            runtime = self.module.CodexRuntime()
            result = runtime.stream_or_collect(runtime.launch(self.request))
        self.assertEqual(result.status, RuntimeStatus.UNAVAILABLE)
        spawn.assert_not_called()

    def test_posix_live_member_scan_ignores_proc_entry_removed_during_scan(self):
        from scripts import process_containment
        group = process_containment.PosixGroup.__new__(process_containment.PosixGroup)
        group._pgid = 123

        class ProcessEntry:
            def __init__(self, name, stat_text=None, error=None):
                self.name = name
                self.stat_text = stat_text
                self.error = error

            def __truediv__(self, name):
                assert name == "stat"

                class ProcessStat:
                    def read_text(inner, **kwargs):
                        if self.error is not None:
                            raise self.error
                        return self.stat_text

                return ProcessStat()

        class ProcRoot:
            def is_dir(self):
                return True

            def iterdir(self):
                return [
                    ProcessEntry("456", error=ProcessLookupError(
                        errno.ESRCH, "No such process")),
                    ProcessEntry("789", stat_text="789 (live) S 1 123 123 0 0 0"),
                ]

        kernel = SimpleNamespace(killpg=Mock())
        with patch.object(process_containment, "os", kernel), \
                patch.object(process_containment, "Path", return_value=ProcRoot()):
            self.assertTrue(group._has_live_members())

    def test_posix_sigchld_host_precondition_blocks_ignored_custom_and_unknown_handlers(self):
        from scripts import process_containment
        for disposition in (1, lambda signum, frame: None, None):
            with self.subTest(disposition=disposition):
                root = Path(tempfile.mkdtemp(dir=self.temp.name))
                request = replace(self.request, stdout_path=root / "out", stderr_path=root / "err")
                kernel = SimpleNamespace(name="posix", P_PID=1, WEXITED=4, WNOHANG=1,
                                         WNOWAIT=0x100, waitid=Mock())
                signals = SimpleNamespace(SIGCHLD=17, SIG_DFL=0, SIG_IGN=1,
                                          getsignal=Mock(return_value=disposition))
                with patch.object(process_containment, "os", kernel), \
                        patch.object(process_containment, "signal", signals), \
                        patch.object(process_containment, "Path", return_value=Mock(is_dir=Mock(return_value=True))), \
                        patch.object(self.module, "_new_containment", side_effect=process_containment.new_containment), \
                        patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                        self.discovery("codex"), patch.object(self.module.subprocess, "Popen") as spawn:
                    runtime = self.module.CodexRuntime()
                    handle = runtime.launch(request)
                self.assertIsNone(handle.process_id)
                self.assertEqual(runtime.stream_or_collect(handle).status, RuntimeStatus.UNAVAILABLE)
                signals.getsignal.assert_called_once_with(signals.SIGCHLD)
                spawn.assert_not_called()

    def test_posix_default_sigchld_host_precondition_allows_runtime_creation(self):
        from scripts import process_containment
        kernel = SimpleNamespace(name="posix", P_PID=1, WEXITED=4, WNOHANG=1,
                                 WNOWAIT=0x100, waitid=Mock())
        signals = SimpleNamespace(SIGCHLD=17, SIG_DFL=0, SIG_IGN=1,
                                  getsignal=Mock(return_value=0))
        with patch.object(process_containment, "os", kernel), \
                patch.object(process_containment, "signal", signals), \
                patch.object(process_containment, "Path", return_value=Mock(is_dir=Mock(return_value=True))), \
                patch.object(process_containment.PosixGroup, "_require_waitable_children"), \
                patch.object(self.module, "_new_containment", side_effect=process_containment.new_containment), \
                patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                self.discovery("codex"), patch.object(self.module.subprocess, "Popen", return_value=Mock(pid=123)) as spawn:
            runtime = self.module.CodexRuntime()
            handle = runtime.launch(self.request)
        self.assertEqual(handle.process_id, 123)
        self.assertIsInstance(runtime._runs[handle.token].containment, process_containment.PosixGroup)
        spawn.assert_called_once()
        signals.getsignal.assert_called_once_with(signals.SIGCHLD)

    def test_posix_concurrent_collection_cancel_signals_before_the_only_reap(self):
        from scripts import process_containment
        group = process_containment.PosixGroup.__new__(process_containment.PosixGroup)
        collecting, release, stopped = threading.Event(), threading.Event(), threading.Event()
        order, results, errors = [], {}, []
        state = {"reaped": False}
        def observe(kind, pid, options):
            if threading.current_thread().name == "posix-collector":
                collecting.set()
                if not release.wait(5):
                    raise AssertionError("POSIX collector was not released")
            if state["reaped"]:
                raise ChildProcessError("Root was reaped by the winning stopper")
            return None
        def signal_group(*args):
            order.append("signal")
        kernel = SimpleNamespace(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=0x100,
            waitid=Mock(side_effect=observe), killpg=Mock(side_effect=signal_group))
        def process_setup(process):
            process.poll.side_effect = AssertionError("POSIX poll would reap early")
            def reap(*args, **kwargs):
                order.append("reap")
                state["reaped"] = True
                return -9
            process.wait.side_effect = reap
        with patch.object(process_containment, "os", kernel), \
                patch.object(process_containment, "signal", SimpleNamespace(SIGKILL=9)), \
                patch.object(group, "_has_live_members", return_value=False), \
                patch.object(self.module, "_new_containment", return_value=group):
            runtime, handle, process = self.launch_fixture("codex", [], exit_code=-9,
                                                          process_setup=process_setup)
            def collect():
                try:
                    results["collect"] = runtime.stream_or_collect(handle)
                except BaseException as exc:
                    errors.append(exc)
            def cancel():
                try:
                    results["cancel"] = runtime.cancel(handle)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    stopped.set()
            collector = threading.Thread(target=collect, name="posix-collector", daemon=True)
            stopper = threading.Thread(target=cancel, daemon=True)
            collector.start()
            try:
                self.assertTrue(collecting.wait(5))
                stopper.start()
                self.assertTrue(stopped.wait(5))
            finally:
                release.set()
                collector.join(5)
                if stopper.ident is not None:
                    stopper.join(5)
            self.assertFalse(collector.is_alive())
            self.assertFalse(stopper.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(order, ["signal", "reap"])
            self.assertIs(results["collect"], results["cancel"])
            self.assertEqual(results["cancel"].status, RuntimeStatus.CANCELLED)
            self.assertEqual(runtime.status(handle), RuntimeStatus.CANCELLED)
            self.assertIs(runtime.timeout(handle), results["cancel"])
            kernel.killpg.assert_called_once()

    def test_posix_waitid_observation_failure_still_stops_owned_group_without_evidence(self):
        from scripts import process_containment
        for mode in ("status", "collect", "cancel", "timeout", "cleanup", "quiesce"):
            with self.subTest(mode=mode):
                group = process_containment.PosixGroup.__new__(process_containment.PosixGroup)
                order = []
                observed = []
                def observe(kind, pid, options):
                    observed.append(pid)
                    if mode == "quiesce" and len(observed) == 1:
                        return SimpleNamespace(si_pid=pid)
                    raise PermissionError("observation denied")
                kernel = SimpleNamespace(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=0x100,
                    waitid=Mock(side_effect=observe),
                    killpg=Mock(side_effect=lambda *args: order.append("signal")))
                def process_setup(process):
                    process.poll.side_effect = AssertionError("Owned POSIX root must remain unreaped")
                    process.wait.side_effect = lambda *args, **kwargs: order.append("reap") or -9
                with patch.object(process_containment, "os", kernel), \
                        patch.object(process_containment, "signal", SimpleNamespace(SIGKILL=9)), \
                        patch.object(group, "_has_live_members", return_value=False), \
                        patch.object(self.module, "_new_containment", return_value=group):
                    runtime, handle, process = self.launch_fixture("codex", [
                        {"type": "thread.started", "thread_id": "mutable-parent"},
                        {"type": "turn.completed", "usage": {}},
                    ], process_setup=process_setup)
                    if mode not in ("collect", "quiesce"):
                        getattr(runtime, mode)(handle)
                    result = runtime.stream_or_collect(handle)
                    self.assertEqual(order, ["signal", "reap"])
                    self.assertEqual(result.status, RuntimeStatus.FAILED)
                    self.assertIn("UNVERIFIED", result.error)
                    self.assertIn("observation denied", result.error)
                    self.assertIsNone(result.provider_session_id)
                    self.assertEqual(result.observed_child_agent_ids, ())
                    self.assertEqual(result.stdout_sha256, "")
                    self.assertEqual(result.stderr_sha256, "")
                    runtime.cleanup(handle)
                    self.assertIs(runtime.stream_or_collect(handle), result)
                    self.assertEqual(order, ["signal", "reap"])
                    process.kill.assert_not_called()

    def test_posix_failed_signal_is_retried_by_cleanup_without_upgrading_cached_failure(self):
        from scripts import process_containment
        group = process_containment.PosixGroup.__new__(process_containment.PosixGroup)
        order = []
        state = {"deny_signal": True}
        def signal_group(*args):
            order.append("signal")
            if state["deny_signal"]:
                raise PermissionError("group signal denied")
        kernel = SimpleNamespace(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=0x100,
            waitid=Mock(side_effect=PermissionError("observation denied")), killpg=Mock(side_effect=signal_group))
        def process_setup(process):
            process.poll.side_effect = AssertionError("No reaping poll")
            process.wait.side_effect = lambda *args, **kwargs: order.append("reap") or -9
        with patch.object(process_containment, "os", kernel), \
                patch.object(process_containment, "signal", SimpleNamespace(SIGKILL=9)), \
                patch.object(group, "_has_live_members", return_value=False), \
                patch.object(self.module, "_new_containment", return_value=group):
            runtime, handle, process = self.launch_fixture("codex", [], process_setup=process_setup)
            self.assertEqual(runtime.status(handle), RuntimeStatus.FAILED)
            result = runtime.stream_or_collect(handle)
            self.assertEqual(order, ["signal"])
            process.wait.assert_not_called()
            with self.assertRaises(OSError):
                runtime.cleanup(handle)
            self.assertIn("UNVERIFIED", runtime._runs[handle.token].cleanup_error)
            process.wait.assert_not_called()
            state["deny_signal"] = False
            runtime.cleanup(handle)
            self.assertEqual(order, ["signal", "signal", "signal", "reap"])
            self.assertTrue(runtime._runs[handle.token].containment_quiesced)
            self.assertIsNone(runtime._runs[handle.token].cleanup_error)
            self.assertIs(runtime.stream_or_collect(handle), result)
            self.assertEqual(result.status, RuntimeStatus.FAILED)
            self.assertEqual(result.stdout_sha256, "")
            self.assertEqual(result.stderr_sha256, "")
            runtime.cleanup(handle)
            self.assertEqual(order, ["signal", "signal", "signal", "reap"])

    def test_cancel_and_cleanup_preserve_terminal_result_and_are_idempotent(self):
        runtime, handle, result, process = self.collect_fixture(
            "codex", [{"type": "turn.completed", "usage": {}}])
        self.assertEqual(runtime.cancel(handle), result)
        runtime.cleanup(handle)
        runtime.cleanup(handle)
        process.kill.assert_not_called()

    def test_running_cancel_and_cleanup_kill_reap_and_preserve_status(self):
        for method in ("cancel", "cleanup"):
            with self.subTest(method=method):
                runtime, handle, process = self.launch_fixture("codex", [], exit_code=-9)
                self.assertEqual(runtime.status(handle), RuntimeStatus.RUNNING)
                getattr(runtime, method)(handle)
                result = runtime.stream_or_collect(handle)
                self.assertEqual(result.status, RuntimeStatus.CANCELLED)
                self.assertEqual(result.exit_code, -9)
                runtime.cleanup(handle)
                process.kill.assert_called_once()
                process.wait.assert_called_once()

    def test_status_collects_completed_process(self):
        runtime, handle, process = self.launch_fixture(
            "gemini", [{"type": "result", "status": "success", "stats": {}}])
        process.poll.return_value = 0
        self.assertEqual(runtime.status(handle), RuntimeStatus.SUCCEEDED)

    def test_unavailable_runtime_never_attributes_stale_logs_to_new_session(self):
        self.request.stdout_path.write_text(
            '{"type":"thread.started","thread_id":"old-session"}\n'
            '{"type":"turn.completed","usage":{}}\n', encoding="utf-8")
        with patch.object(self.module.shutil, "which", return_value=None):
            runtime = self.module.CodexRuntime()
            result = runtime.stream_or_collect(runtime.launch(self.request))
        self.assertEqual(result.status, RuntimeStatus.UNAVAILABLE)
        self.assertIsNone(result.provider_session_id)
        self.assertEqual(result.stdout_sha256, "")

    def test_malformed_known_events_cannot_certify_success(self):
        for provider, events in (
            ("codex", [{"type": "item.started", "item": None},
                       {"type": "turn.completed", "usage": {}}]),
            ("codex", [{"type": "turn.completed", "usage": {}}, {"type": "turn.started"}]),
            ("gemini", [{"type": "message", "role": "assistant", "content": None},
                        {"type": "result", "status": "success", "stats": {}}]),
        ):
            with self.subTest(provider=provider, events=events):
                _, _, result, _ = self.collect_fixture(provider, events)
                self.assertEqual(result.status, RuntimeStatus.FAILED)

    def test_windows_gemini_shim_uses_native_node_for_probes_and_launch(self):
        root = Path(self.temp.name)
        shim = root / "gemini.CMD"
        shim.touch()
        script = root / "node_modules" / "@google" / "gemini-cli" / "bundle" / "gemini.js"
        script.parent.mkdir(parents=True)
        script.touch()
        node = root / "node.exe"
        node.touch()
        prompt = 'literal & echo PWNED | > < ^ %PATH% !value! "quoted" --yolo'
        request = replace(self.request, prompt=prompt)

        def probe(argv, **kwargs):
            self.assertEqual(argv[:2], (str(node), str(script)))
            self.assertIn(argv[2:], (("--version",), ("--help",)))
            self.assertFalse(kwargs["shell"])
            return subprocess.CompletedProcess(argv, 0, "1.0" if argv[-1] == "--version"
                                               else self.help_text("gemini"), "")

        with patch.object(sys, "platform", "win32"), \
                patch.object(self.module.shutil, "which", side_effect=lambda name: {
                    "gemini": str(shim), "node.exe": str(node)}.get(name)), \
                patch.object(self.module.subprocess, "run", side_effect=probe), \
                patch.object(self.module.subprocess, "Popen", return_value=Mock(pid=321)) as spawn:
            runtime = self.module.GeminiRuntime()
            runtime.launch(request)
        argv = spawn.call_args.args[0]
        self.assertEqual(argv[:2], (str(node), str(script)))
        self.assertEqual(argv[-1], "--prompt=" + prompt)
        self.assertFalse(spawn.call_args.kwargs["shell"])
        self.assertNotIn(str(shim), argv)

    def test_windows_shims_without_native_components_are_unavailable_without_probe(self):
        root = Path(self.temp.name)
        for provider, suffix, components in (("gemini", ".CMD", "none"),
                                              ("gemini", ".bat", "node_only"),
                                              ("codex", ".cmd", "none")):
            with self.subTest(provider=provider, components=components):
                shim = root / (provider + suffix)
                node = root / "node.exe"
                node.touch(exist_ok=True)
                with patch.object(sys, "platform", "win32"), \
                        patch.object(self.module.shutil, "which", side_effect=lambda name: (
                            str(shim) if name == provider else str(node) if components == "node_only" else None)), \
                        patch.object(self.module.subprocess, "run") as probe, \
                        patch.object(self.module.subprocess, "Popen") as spawn:
                    runtime = self.module.create_runtime(provider)
                    result = runtime.stream_or_collect(runtime.launch(self.request))
                self.assertEqual(result.status, RuntimeStatus.UNAVAILABLE)
                probe.assert_not_called()
                spawn.assert_not_called()

    def test_output_aliases_and_existing_files_are_rejected_before_spawn(self):
        root = Path(self.temp.name)
        existing = root / "existing.log"
        existing.write_bytes(b"original evidence")
        for stdout, stderr in ((root / "same.log", root / "same.log"),
                                (root / "same.log", root / "nested" / ".." / "same.log"),
                                (existing, root / "new.log"),
                                (root / "new.log", existing)):
            with self.subTest(stdout=stdout, stderr=stderr), \
                    patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                    self.discovery("codex"), patch.object(self.module.subprocess, "Popen") as spawn:
                with self.assertRaises(ValueError):
                    self.module.CodexRuntime().launch(replace(self.request, stdout_path=stdout, stderr_path=stderr))
                spawn.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"original evidence")

    def test_exclusive_creation_preserves_files_created_after_reservation(self):
        original_open = Path.open
        for stream_name in ("stdout_path", "stderr_path"):
            root = Path(tempfile.mkdtemp(dir=self.temp.name))
            request = replace(self.request, stdout_path=root / "out", stderr_path=root / "err")
            raced_path = getattr(request, stream_name)
            injected = False

            def racing_open(path, mode="r", *args, **kwargs):
                nonlocal injected
                if path == raced_path and not injected:
                    injected = True
                    with original_open(path, "wb") as stream:
                        stream.write(b"independent evidence")
                return original_open(path, mode, *args, **kwargs)

            with self.subTest(stream_name=stream_name), \
                    patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                    self.discovery("codex"), patch.object(Path, "open", new=racing_open), \
                    patch.object(self.module.subprocess, "Popen") as spawn:
                runtime = self.module.CodexRuntime()
                result = runtime.stream_or_collect(runtime.launch(request))
            self.assertEqual(result.status, RuntimeStatus.UNAVAILABLE)
            self.assertEqual(raced_path.read_bytes(), b"independent evidence")
            spawn.assert_not_called()

    def test_run_b_cannot_overwrite_or_relabel_run_a_evidence(self):
        runtime_a, handle_a, _ = self.launch_fixture("codex", [
            {"type": "thread.started", "thread_id": "session-A"},
            {"type": "turn.completed", "usage": {}},
        ])
        original = self.request.stdout_path.read_bytes()
        for completed in (False, True):
            if completed:
                runtime_a.stream_or_collect(handle_a)
            with self.subTest(completed=completed), \
                    patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                    self.discovery("codex"), patch.object(self.module.subprocess, "Popen") as spawn:
                with self.assertRaises(ValueError):
                    self.module.CodexRuntime().launch(replace(self.request, run_id="run-B"))
                spawn.assert_not_called()
            self.assertEqual(self.request.stdout_path.read_bytes(), original)
        result = runtime_a.stream_or_collect(handle_a)
        self.assertEqual(result.provider_session_id, "session-A")
        self.assertEqual(result.run_id, "run-1")
        self.request.stdout_path.unlink()
        self.request.stderr_path.unlink()
        runtime_a.cleanup(handle_a)
        with patch.object(self.module.shutil, "which", return_value="/selected/codex"), \
                self.discovery("codex"), patch.object(self.module.subprocess, "Popen") as spawn:
            with self.assertRaises(ValueError):
                self.module.CodexRuntime().launch(replace(self.request, run_id="run-B"))
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
