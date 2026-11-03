import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "validate_workspace.py"
EXAMPLE = ROOT / "examples" / "scientific_workspace_minimal.json"


class WorkspaceCliTests(unittest.TestCase):
    def run_cli(self, argument, *, input_text=None):
        return subprocess.run(
            [sys.executable, "-P", str(CLI), argument],
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )

    def test_cli_emits_normalized_json_for_valid_manifest(self):
        result = self.run_cli(str(EXAMPLE))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), json.loads(EXAMPLE.read_text(encoding="utf-8")))
        self.assertEqual(result.stderr, "")

    def test_cli_accepts_manifest_from_stdin(self):
        manifest_text = EXAMPLE.read_text(encoding="utf-8")

        result = self.run_cli("-", input_text=manifest_text)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), json.loads(manifest_text))

    def test_cli_emits_portable_ascii_json_for_unicode_text(self):
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["model"]["title"] = "Modelo científico β — 🧪"
        manifest_text = json.dumps(manifest, ensure_ascii=False)

        result = self.run_cli("-", input_text=manifest_text)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.isascii())
        self.assertEqual(json.loads(result.stdout), manifest)

    def test_cli_reports_invalid_manifest_and_nonzero_exit(self):
        result = self.run_cli("-", input_text='{"schema_version": 1}')

        self.assertEqual(result.returncode, 2)
        self.assertIn("workspace is missing fields", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_cli_rejects_duplicate_json_keys_and_nonstandard_numbers(self):
        example_text = EXAMPLE.read_text(encoding="utf-8")
        duplicate_key = example_text.replace(
            '"schema_version": 1,',
            '"schema_version": 2, "schema_version": 1,',
            1,
        )
        for text, message in (
            (duplicate_key, "duplicate JSON key"),
            ('{"schema_version": NaN}', "non-finite JSON number"),
        ):
            with self.subTest(message=message):
                result = self.run_cli("-", input_text=text)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_cli_rejects_oversized_manifest_without_reading_unbounded_input(self):
        too_large = " " * (2 * 1024 * 1024 + 1)

        result = self.run_cli("-", input_text=too_large)

        self.assertEqual(result.returncode, 2)
        self.assertIn("exceeds 2097152 bytes", result.stderr)

    def test_cli_reports_filesystem_and_json_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid_json = Path(directory) / "invalid.json"
            invalid_json.write_text("{", encoding="utf-8")
            result = self.run_cli(str(invalid_json))
            missing_json = self.run_cli(str(Path(directory) / "missing.json"))

        self.assertEqual(result.returncode, 2)
        self.assertIn("JSON", result.stderr)
        self.assertEqual(missing_json.returncode, 2)
        self.assertNotEqual(missing_json.stderr, "")


if __name__ == "__main__":
    unittest.main()
