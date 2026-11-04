"""Native profiles for single and dual providers remain backward-compatible."""
import json
import tempfile
import threading
import time
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import run_agents
from scripts.agent_runtime import RuntimeHandle, RuntimeLaunchControl, RuntimeStatus
from scripts.config_panel import build_policy
from scripts.prepare_agents import make_files, prepare

TASK = json.loads((Path(__file__).resolve().parents[1] / "examples/seir_desktop_audit.json").read_text(encoding="utf-8"))


class FakeAgyRuntime:
    def __init__(self, status=RuntimeStatus.SUCCEEDED, *, fail_cleanup=False):
        self.current_status = status
        self.fail_cleanup = fail_cleanup
        self.request = None
        self.handle = None
        self.cleaned = 0
        self.cancelled = 0
        self.timed_out = 0
        self.snapshot_files = ()
        self.packet_text = ""
        self.cancel_file_after_launch = None

    def launch(self, request):
        self.request = request
        self.snapshot_files = tuple(sorted(
            path.relative_to(request.cwd).as_posix() for path in request.cwd.rglob("*")
            if path.is_file()
        ))
        agent_name = "ssec-" + request.role.replace("_", "-")
        packet = request.cwd / ".ssec/tasks" / request.task_id / f"{agent_name}.md"
        self.packet_text = packet.read_text()
        request.stdout_path.write_bytes(b'{"status":"SUCCESS"}')
        request.stderr_path.write_bytes(b"")
        self.handle = RuntimeHandle("fake-agy", request.run_id, "agy", 321)
        if self.cancel_file_after_launch is not None:
            self.cancel_file_after_launch.write_text("cancel", encoding="utf-8")
        return self.handle

    def status(self, handle):
        return self.current_status

    def stream_or_collect(self, handle):
        return self.result()

    def cancel(self, handle):
        self.cancelled += 1
        self.current_status = RuntimeStatus.CANCELLED
        return self.result()

    def timeout(self, handle):
        self.timed_out += 1
        self.current_status = RuntimeStatus.TIMED_OUT
        return self.result()

    def cleanup(self, handle):
        self.cleaned += 1
        if self.fail_cleanup:
            raise OSError("fake cleanup failure")

    def result(self):
        return SimpleNamespace(
            provider="agy", status=self.current_status,
            exit_code=0 if self.current_status is RuntimeStatus.SUCCEEDED else 1,
            provider_session_id=("agy-session-1" if self.current_status is RuntimeStatus.SUCCEEDED
                                 else None),
            stdout_sha256="a" * 64, stderr_sha256="b" * 64,
            error=None if self.current_status is RuntimeStatus.SUCCEEDED else "provider failed",
        )


class TrackingLaunchControl(RuntimeLaunchControl):
    def __post_init__(self):
        super().__post_init__()
        self.set_calls = 0

    def set(self):
        self.set_calls += 1
        super().set()


class TestModes(unittest.TestCase):
    def test_agy_only_uses_explicit_runtime_without_native_profile(self):
        config = build_policy("agy", "2", "read_only", "60", "10", "standard")
        manifest, files = make_files(TASK, "agy", config)

        self.assertEqual({entry["provider"] for entry in manifest["assignments"]}, {"agy"})
        self.assertTrue(all(entry["profile"] is None for entry in manifest["assignments"]))
        self.assertTrue(all(entry["packet"] in files for entry in manifest["assignments"]))
        self.assertFalse(any(path.startswith((".codex/agents/", ".gemini/agents/"))
                             for path in files))
        self.assertTrue(all("Provider: agy" in files[entry["packet"]]
                            for entry in manifest["assignments"]))

    def test_gemini_only(self):
        m, files = make_files(TASK, "gemini")
        self.assertTrue(all(a["provider"] == "gemini" for a in m["assignments"]))
        self.assertFalse(any(k.startswith(".codex/agents/") for k in files))

    def test_codex_only_toml(self):
        m, files = make_files(TASK, "codex")
        self.assertTrue(all(a["provider"] == "codex" for a in m["assignments"]))
        for path, content in files.items():
            if path.endswith(".toml"):
                self.assertIn("developer_instructions", tomllib.loads(content))

    def test_both(self):
        m, _ = make_files(TASK, "both")
        self.assertEqual({a["provider"] for a in m["assignments"]}, {"gemini", "codex"})
        self.assertTrue(all(a["provider"] == "gemini" for a in m["assignments"] if a["reviewer"]))

    def _run_agy_worker(self, runtime, *, cancel=False, timeout=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "model.json"
            source.write_text('{"equations":"data only"}', encoding="utf-8")
            run_dir = root / "run"
            run_dir.mkdir()
            packet = ".ssec/tasks/test-task/ssec-numerical-analyst.md"
            cancel_file = root / "cancel"
            if cancel:
                runtime.cancel_file_after_launch = cancel_file
            agent = {"agent": "ssec-numerical-analyst", "role": "numerical_analyst",
                     "provider": "agy", "profile": None, "packet": packet}
            deadline = time.monotonic() + (0.02 if timeout else 10)
            stop = threading.Event()
            launch_control = TrackingLaunchControl(stop, deadline, cancel_file=cancel_file)
            result = run_agents.run_one(
                agent, "test-task", [(source, Path("model.json"))], {packet: "role packet"},
                run_dir, deadline, stop, cancel_file if cancel else None,
                runtime_factory=lambda provider: runtime, run_id="run-123",
                cost_acknowledged=True, launch_control=launch_control,
            )
            return result, launch_control

    def test_agy_worker_uses_runtime_and_keeps_success_unreviewed_with_evidence(self):
        runtime = FakeAgyRuntime()
        with patch.object(run_agents, "command_for",
                          side_effect=AssertionError("AGY must not use raw CLI dispatch")):
            result, launch_control = self._run_agy_worker(runtime)

        self.assertEqual(result["status"], "EXIT_ZERO_UNREVIEWED")
        self.assertEqual(result["provider_session_id"], "agy-session-1")
        self.assertEqual(result["runtime_run_id"], "run-123")
        self.assertEqual(result["stdout_sha256"], "a" * 64)
        self.assertEqual(result["stderr_sha256"], "b" * 64)
        self.assertFalse(runtime.request.writable)
        self.assertTrue(runtime.request.cost_acknowledged)
        self.assertIs(runtime.request.launch_control, launch_control)
        self.assertEqual(runtime.request.run_id, "run-123")
        self.assertEqual(runtime.snapshot_files, (
            ".ssec/tasks/test-task/ssec-numerical-analyst.md", "model.json"))
        self.assertEqual(runtime.packet_text, "role packet")
        self.assertIn("ssec-numerical-analyst", runtime.request.prompt)
        self.assertEqual(runtime.cleaned, 1)

    def test_agy_worker_propagates_cancel_and_timeout_and_cleans_up(self):
        cancelled = FakeAgyRuntime(RuntimeStatus.RUNNING)
        cancel_result, cancel_control = self._run_agy_worker(cancelled, cancel=True)
        self.assertEqual(cancel_result["status"], "CANCELLED")
        self.assertEqual(cancelled.cancelled, 1)
        self.assertEqual(cancelled.cleaned, 1)
        self.assertEqual(cancel_control.set_calls, 1)

        timed_out = FakeAgyRuntime(RuntimeStatus.RUNNING)
        with patch.object(run_agents.time, "sleep", return_value=None):
            timeout_result, timeout_control = self._run_agy_worker(timed_out, timeout=True)
        self.assertEqual(timeout_result["status"], "TIMED_OUT")
        self.assertEqual(timed_out.timed_out, 1)
        self.assertEqual(timed_out.cleaned, 1)
        self.assertEqual(timeout_control.set_calls, 1)

    def test_agy_worker_maps_provider_failure_without_session(self):
        runtime = FakeAgyRuntime(RuntimeStatus.FAILED)
        result, _ = self._run_agy_worker(runtime)
        self.assertEqual(result["status"], "CLI_FAILED")
        self.assertIsNone(result["provider_session_id"])
        self.assertEqual(runtime.cleaned, 1)

    def test_cancel_file_created_during_runtime_factory_blocks_agy_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "model.json"
            source.write_text("{}", encoding="utf-8")
            run_dir = root / "run"
            run_dir.mkdir()
            cancel_file = root / "cancel"
            packet = ".ssec/tasks/test-task/ssec-numerical-analyst.md"
            stop = threading.Event()
            control = TrackingLaunchControl(stop, time.monotonic() + 10,
                                            cancel_file=cancel_file)
            runtime = FakeAgyRuntime()

            def factory(provider):
                cancel_file.write_text("cancel", encoding="utf-8")
                return runtime

            result = run_agents.run_one(
                {"agent": "ssec-numerical-analyst", "role": "numerical_analyst",
                 "provider": "agy", "profile": None, "packet": packet},
                "test-task", [(source, Path("model.json"))], {packet: "role packet"},
                run_dir, control.deadline, stop, cancel_file,
                runtime_factory=factory, run_id="run-123", cost_acknowledged=True,
                launch_control=control,
            )

        self.assertEqual(result["status"], "CANCELLED")
        self.assertIsNone(runtime.request)
        self.assertEqual(runtime.cleaned, 0)
        self.assertTrue(stop.is_set())

    def test_cleanup_failure_downgrades_success_and_cannot_approve(self):
        runtime = FakeAgyRuntime(fail_cleanup=True)
        result, _ = self._run_agy_worker(runtime)
        self.assertEqual(result["status"], "LAUNCH_FAILED")
        self.assertIn("fake cleanup failure", result["error"])
        self.assertEqual(runtime.cleaned, 1)

    def test_unmetered_cost_gate_prevents_agy_runtime_creation(self):
        config = build_policy("agy", "2", "read_only", "60", "10", "standard")
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / "model.json").write_text("{}", encoding="utf-8")
            created = []
            with self.assertRaisesRegex(ValueError, "billing is NOT metered"):
                run_agents.execute(
                    TASK, config, project, execute_clis=True,
                    accept_unmetered_cost=False,
                    runtime_factory=lambda provider: created.append(provider),
                )
            self.assertEqual(created, [])

    def test_agy_execute_dispatches_all_roles_without_claiming_audit_approval(self):
        config = build_policy("agy", "1", "read_only", "1", "10", "basic")
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / "model.json").write_text("{}", encoding="utf-8")
            runtimes = []

            def factory(provider):
                self.assertEqual(provider, "agy")
                runtime = FakeAgyRuntime()
                runtimes.append(runtime)
                return runtime

            report = run_agents.execute(
                TASK, config, project, execute_clis=True,
                accept_unmetered_cost=True, runtime_factory=factory,
            )

        self.assertEqual(report["execution"], "PROCESSES_COMPLETED_NOT_AUDITED")
        self.assertEqual(report["release_status"], "NOT_APPROVED")
        self.assertEqual(len(report["results"]), report["agent_count"])
        self.assertTrue(all(item["status"] == "EXIT_ZERO_UNREVIEWED"
                            for item in report["results"]))
        self.assertEqual(len({item["runtime_run_id"] for item in report["results"]}),
                         report["agent_count"])
        self.assertEqual(len(runtimes), report["agent_count"])
        self.assertEqual(len({id(runtime.request.launch_control) for runtime in runtimes}), 1)

    def test_execute_records_pre_wave_cancel_through_launch_control(self):
        config = build_policy("agy", "1", "read_only", "1", "10", "basic")
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / "model.json").write_text("{}", encoding="utf-8")
            cancel_file = project / "cancel"
            cancel_file.write_text("cancel", encoding="utf-8")
            controls = []
            factories = []

            def make_control(stop_event, deadline, *, cancel_file=None):
                control = TrackingLaunchControl(stop_event, deadline,
                                                cancel_file=cancel_file)
                controls.append(control)
                return control

            with patch.object(run_agents, "RuntimeLaunchControl", side_effect=make_control):
                report = run_agents.execute(
                    TASK, config, project, execute_clis=True,
                    accept_unmetered_cost=True, cancel_file=cancel_file,
                    runtime_factory=lambda provider: factories.append(provider),
                )

        self.assertEqual(report["execution"], "PARTIAL_OR_FAILED")
        self.assertEqual(report["release_status"], "NOT_APPROVED")
        self.assertEqual(factories, [])
        self.assertEqual(controls[0].set_calls, 1)

    def test_preview(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.assertFalse(prepare(TASK, "both", p)["applied"])
            self.assertFalse(list(p.iterdir()))

    def test_apply_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.assertTrue(prepare(TASK, "both", p, apply=True)["applied"])
            self.assertTrue((p / ".gemini/agents").is_dir())
            self.assertTrue((p / ".codex/agents").is_dir())
            prepare(TASK, "both", p, apply=True)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            _, files = make_files(TASK, "codex")
            conflict = p / next(k for k in files if k.endswith(".toml"))
            conflict.parent.mkdir(parents=True)
            conflict.write_text("USER DATA")
            with self.assertRaises(FileExistsError):
                prepare(TASK, "codex", p, apply=True)
            self.assertEqual(conflict.read_text(), "USER DATA")

    def test_bad_id(self):
        with self.assertRaises(ValueError):
            make_files(dict(TASK, task_id="../bad"), "gemini")

    def test_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "elsewhere").mkdir()
            (p / ".gemini").symlink_to(p / "elsewhere", target_is_directory=True)
            with self.assertRaises(ValueError):
                prepare(TASK, "gemini", p, apply=True)
