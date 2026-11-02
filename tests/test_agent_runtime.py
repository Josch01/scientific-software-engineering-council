import unittest
from pathlib import Path

from scripts.agent_runtime import (
    FakeRuntime,
    RuntimeRequest,
    RuntimeStatus,
)


class FakeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.request = RuntimeRequest(
            run_id="run-1", task_id="task-1", role="implementer", prompt="do work",
            cwd=Path("/workspace"), stdout_path=Path("/tmp/out.log"),
            stderr_path=Path("/tmp/err.log"), timeout_seconds=30.0,
            writable=True, cost_acknowledged=True,
        )

    def test_fake_runtime_records_provider_request(self):
        runtime = FakeRuntime()
        handle = runtime.launch(self.request)
        self.assertEqual(runtime.invocations, [("launch", self.request)])
        self.assertEqual(handle.run_id, "run-1")
        self.assertEqual(handle.provider, "fake")
        self.assertIsNone(handle.process_id)
        self.assertEqual(runtime.discover_capabilities().provider, "fake")

    def test_fake_runtime_terminal_results_are_schema_versioned(self):
        runtime = FakeRuntime()
        handle = runtime.launch(self.request)
        result = runtime.stream_or_collect(handle)
        self.assertEqual(result.schema_version, 1)
        self.assertEqual(result.run_id, "run-1")
        self.assertEqual(result.provider, "fake")
        self.assertEqual(result.status, RuntimeStatus.SUCCEEDED)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.provider_session_id)
        self.assertEqual(result.stdout_path, Path("/tmp/out.log"))
        self.assertEqual(result.stderr_path, Path("/tmp/err.log"))
        self.assertEqual(result.stdout_sha256, "")
        self.assertEqual(result.stderr_sha256, "")
        self.assertEqual(result.observed_child_agent_ids, ())
        self.assertIsNone(result.error)

    def test_timeout_and_cancel_statuses_are_distinct(self):
        for method, expected in (("timeout", RuntimeStatus.TIMED_OUT),
                                 ("cancel", RuntimeStatus.CANCELLED)):
            runtime = FakeRuntime()
            handle = runtime.launch(self.request)
            result = getattr(runtime, method)(handle)
            self.assertEqual(result.status, expected)
            self.assertEqual(runtime.status(handle), expected)

    def test_cleanup_is_idempotent(self):
        runtime = FakeRuntime()
        handle = runtime.launch(self.request)
        runtime.cleanup(handle)
        runtime.cleanup(handle)
        self.assertEqual(runtime.invocations.count(("cleanup", handle)), 1)
        self.assertEqual(runtime.status(handle), RuntimeStatus.RUNNING)

    def test_runtime_request_rejects_invalid_timeout_and_nul_prompt(self):
        with self.assertRaises(ValueError):
            RuntimeRequest(**{**self.request.__dict__, "timeout_seconds": 0})
        with self.assertRaises(ValueError):
            RuntimeRequest(**{**self.request.__dict__, "prompt": "bad\0prompt"})


if __name__ == "__main__":
    unittest.main()
