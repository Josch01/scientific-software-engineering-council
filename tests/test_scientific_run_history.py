from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.scientific_run_history import (
    list_sir_analysis_runs,
    read_sir_analysis_run,
)


class SirAnalysisRunHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "project"
        self.root.mkdir()

    def _write_record(self, status="FAILED", *, run_id=None, started_at=None, result=None):
        run_id = run_id or uuid.uuid4().hex
        record = {
            "schema_version": 1,
            "run_id": run_id,
            "started_at_utc": started_at or datetime.now(timezone.utc).isoformat(),
            "source_workspace_manifest": "workspace.json",
            "source_workspace_manifest_sha256": "a" * 64,
            "output_directory": f"generated/sir-analysis/{run_id}",
            "status": status,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 0.01,
        }
        if result:
            record["result_workspace_manifest"] = result[0]
            record["result_workspace_manifest_sha256"] = result[1]
        log_directory = self.root / "generated" / "sir-analysis-runs"
        log_directory.mkdir(parents=True, exist_ok=True)
        log_path = log_directory / f"run-{run_id}.json"
        log_path.write_text(json.dumps(record), encoding="utf-8")
        return run_id, log_path

    def test_lists_latest_records_first_and_caps_history_at_100(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        run_ids = []
        for index in range(101):
            run_id, log_path = self._write_record(
                started_at=(start + timedelta(seconds=index)).isoformat()
            )
            run_ids.append(run_id)
            stamp = time.time_ns() + index * 100_000_000
            os.utime(log_path, ns=(stamp, stamp))

        records = list_sir_analysis_runs(self.root)

        self.assertEqual(len(records), 100)
        self.assertEqual(records[0].run_id, run_ids[-1])
        self.assertNotIn(run_ids[0], [record.run_id for record in records])

    def test_reports_malformed_and_oversized_logs_as_invalid(self):
        log_directory = self.root / "generated" / "sir-analysis-runs"
        log_directory.mkdir(parents=True)
        malformed_id = uuid.uuid4().hex
        (log_directory / f"run-{malformed_id}.json").write_text("{bad", encoding="utf-8")
        oversized_id = uuid.uuid4().hex
        (log_directory / f"run-{oversized_id}.json").write_bytes(b" " * 65537)
        bad_status_id, _ = self._write_record(status=[])

        records = list_sir_analysis_runs(self.root)

        by_id = {record.run_id: record for record in records}
        self.assertEqual(by_id[malformed_id].status, "INVALID")
        self.assertEqual(by_id[oversized_id].status, "INVALID")
        self.assertEqual(by_id[bad_status_id].status, "INVALID")
        self.assertFalse(by_id[oversized_id].can_open)

    def test_symlinked_log_is_not_followed(self):
        log_directory = self.root / "generated" / "sir-analysis-runs"
        log_directory.mkdir(parents=True)
        run_id = uuid.uuid4().hex
        outside_log = Path(self.temporary_directory.name) / "outside.json"
        outside_log.write_text(
            json.dumps({
                "schema_version": 1,
                "run_id": run_id,
                "started_at_utc": "2026-11-13T12:00:00Z",
                "status": "SUCCEEDED",
                "result_workspace_manifest": "generated/sir-analysis/run/workspace.json",
                "result_workspace_manifest_sha256": "e" * 64,
            }),
            encoding="utf-8",
        )
        link = log_directory / f"run-{run_id}.json"
        try:
            link.symlink_to(outside_log)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable in this environment: {exc}")

        records = list_sir_analysis_runs(self.root)

        self.assertEqual(records[0].status, "INVALID")
        self.assertFalse(records[0].can_open)

    def test_read_only_returns_successful_records_with_safe_relative_result_and_digest(self):
        run_id = uuid.uuid4().hex
        self._write_record(
            "SUCCEEDED",
            run_id=run_id,
            result=(f"generated/sir-analysis/{run_id}/workspace.json", "b" * 64),
        )

        record = read_sir_analysis_run(self.root, run_id)

        self.assertEqual(record.status, "SUCCEEDED")
        self.assertTrue(record.can_open)
        failed_id, _ = self._write_record("FAILED")
        with self.assertRaises(ValueError):
            read_sir_analysis_run(self.root, failed_id)
        unsafe_id, _ = self._write_record(
            "SUCCEEDED",
            result=("../../outside/workspace.json", "c" * 64),
        )
        with self.assertRaises(ValueError):
            read_sir_analysis_run(self.root, unsafe_id)
        windows_id, _ = self._write_record(
            "SUCCEEDED",
            result=("C:/outside/workspace.json", "d" * 64),
        )
        with self.assertRaises(ValueError):
            read_sir_analysis_run(self.root, windows_id)
        wrong_destination_id, _ = self._write_record(
            "SUCCEEDED",
            result=("workspace.json", "e" * 64),
        )
        with self.assertRaises(ValueError):
            read_sir_analysis_run(self.root, wrong_destination_id)


if __name__ == "__main__":
    unittest.main()
