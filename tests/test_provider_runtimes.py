"""Offline parser/contract tests; JSONL fixtures are not provider E2E evidence."""

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.agent_runtime import RuntimeCapabilityStatus, RuntimeRequest, RuntimeStatus


class ProviderRuntimeTests(unittest.TestCase):
    def setUp(self):
        # Missing implementation is an explicit RED assertion, not an import error.
        self.assertIsNotNone(importlib.util.find_spec("scripts.provider_runtimes"),
                             "provider runtime adapters are not implemented")
        from scripts import provider_runtimes
        self.module = provider_runtimes
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.request = RuntimeRequest(
            "run-1", "task-1", "reviewer", "--prompt ; $(echo unsafe) 日本語",
            root, root / "stdout.jsonl", root / "stderr.log", 30, False, True,
        )

    def help_text(self, provider):
        return ("--json --sandbox read-only workspace-write" if provider == "codex"
                else "--prompt --output-format stream-json --sandbox --approval-mode default")

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

    def launch_fixture(self, provider, events, exit_code=0, wait_error=None):
        runtime = self.module.create_runtime(provider)
        payload = events if isinstance(events, bytes) else (
            "\n".join(json.dumps(event) for event in events) + "\n").encode()
        process = Mock(pid=1234, returncode=exit_code)
        process.wait.side_effect = wait_error
        process.wait.return_value = exit_code
        process.poll.return_value = None

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


if __name__ == "__main__":
    unittest.main()
