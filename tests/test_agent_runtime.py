import math
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

    def test_collection_preserves_cancelled_and_timed_out_terminal_status(self):
        for method, expected in (("cancel", RuntimeStatus.CANCELLED),
                                 ("timeout", RuntimeStatus.TIMED_OUT)):
            with self.subTest(method=method):
                runtime = FakeRuntime()
                handle = runtime.launch(self.request)
                getattr(runtime, method)(handle)
                result = runtime.stream_or_collect(handle)
                self.assertEqual(result.status, expected)
                self.assertEqual(runtime.status(handle), expected)

    def test_cleanup_is_idempotent(self):
        runtime = FakeRuntime()
        handle = runtime.launch(self.request)
        runtime.cleanup(handle)
        runtime.cleanup(handle)
        self.assertEqual(runtime.invocations.count(("cleanup", handle)), 1)
        self.assertEqual(runtime.status(handle), RuntimeStatus.RUNNING)

    def test_first_terminal_result_survives_every_later_lifecycle_call(self):
        for first_status in (RuntimeStatus.SUCCEEDED, RuntimeStatus.FAILED,
                             RuntimeStatus.UNAVAILABLE, RuntimeStatus.CANCELLED,
                             RuntimeStatus.TIMED_OUT):
            with self.subTest(first_status=first_status):
                runtime=FakeRuntime((first_status,))
                handle=runtime.launch(self.request)
                first=runtime.stream_or_collect(handle)
                self.assertIs(runtime.cancel(handle),first)
                self.assertIs(runtime.timeout(handle),first)
                self.assertIs(runtime.stream_or_collect(handle),first)
                runtime.cleanup(handle)
                self.assertEqual(runtime.status(handle),first_status)
                self.assertIs(runtime.stream_or_collect(handle),first)

    def test_running_stop_result_is_cached_across_opposite_stop(self):
        for stop, expected in (("cancel",RuntimeStatus.CANCELLED),
                               ("timeout",RuntimeStatus.TIMED_OUT)):
            with self.subTest(stop=stop):
                runtime=FakeRuntime()
                handle=runtime.launch(self.request)
                first=getattr(runtime,stop)(handle)
                self.assertEqual(first.status,expected)
                self.assertIs(runtime.cancel(handle),first)
                self.assertIs(runtime.timeout(handle),first)
                self.assertIs(runtime.stream_or_collect(handle),first)

    def test_runtime_request_rejects_nonfinite_timeout_and_nul_prompt(self):
        for timeout in (0, -1, math.nan, math.inf, -math.inf):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                RuntimeRequest(**{**self.request.__dict__, "timeout_seconds": timeout})
        with self.assertRaises(ValueError):
            RuntimeRequest(**{**self.request.__dict__, "prompt": "bad\0prompt"})


if __name__ == "__main__":
    unittest.main()
