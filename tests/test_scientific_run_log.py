from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.scientific_control_center_qt import _write_analysis_run_log


class AnalysisRunLogTests(unittest.TestCase):
    def test_concurrent_first_run_log_directory_creation_is_create_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "generated").mkdir()
            rendezvous = threading.Barrier(2)
            original_mkdir = Path.mkdir

            def synchronized_mkdir(path, *args, **kwargs):
                if path.name == "sir-analysis-runs":
                    rendezvous.wait(timeout=3)
                return original_mkdir(path, *args, **kwargs)

            with patch.object(Path, "mkdir", new=synchronized_mkdir):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(
                        _write_analysis_run_log, root, "run-one", {"status": "SUCCEEDED"}
                    )
                    second = pool.submit(
                        _write_analysis_run_log, root, "run-two", {"status": "SUCCEEDED"}
                    )
                    paths = {first.result(timeout=5), second.result(timeout=5)}

            self.assertEqual(paths, {
                "generated/sir-analysis-runs/run-run-one.json",
                "generated/sir-analysis-runs/run-run-two.json",
            })
            records = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((root / "generated" / "sir-analysis-runs").glob("*.json"))
            ]
            self.assertEqual(records, [{"status": "SUCCEEDED"}, {"status": "SUCCEEDED"}])


if __name__ == "__main__":
    unittest.main()
