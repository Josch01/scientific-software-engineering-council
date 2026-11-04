from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.extension_catalog import (
    MAX_CATALOG_BYTES,
    CatalogValidationError,
    load_catalog,
    validate_catalog,
)


def valid_catalog() -> dict[str, object]:
    return {
        "schema_version": 1,
        "extensions": [
            {
                "id": "sir-rate-audit",
                "name": "SIR rate audit",
                "version": "1.2.3",
                "source": {
                    "url": "https://github.com/example/sir-rate-audit",
                    "commit": "a" * 40,
                    "sha256": "b" * 64,
                },
                "maintainer": "example-team",
                "license": "MIT",
                "capabilities": ["scientific_audit", "workspace_proposal"],
                "permissions": ["read_project"],
                "review": {
                    "status": "approved",
                    "reviewer": "independent-reviewer",
                    "reviewed_at": "2026-11-04T09:00:00Z",
                    "report_sha256": "c" * 64,
                },
                "rollback": {
                    "version": "1.2.2",
                    "commit": "d" * 40,
                    "sha256": "e" * 64,
                },
            }
        ],
    }


class ExtensionCatalogTests(unittest.TestCase):
    def test_accepts_metadata_with_immutable_source_review_and_rollback(self) -> None:
        self.assertEqual(validate_catalog(valid_catalog()), [])

    def test_rejects_mutable_or_non_https_sources(self) -> None:
        for url, commit in (
            ("https://github.com/example/sir-rate-audit", "main"),
            ("http://github.com/example/sir-rate-audit", "a" * 40),
            ("https://user:pass@example.org/package", "a" * 40),
            ("https://example.org:invalid/package", "a" * 40),
        ):
            with self.subTest(url=url, commit=commit):
                catalog = valid_catalog()
                entry = catalog["extensions"][0]
                entry["source"]["url"] = url
                entry["source"]["commit"] = commit
                self.assertTrue(validate_catalog(catalog))

    def test_requires_review_record_and_distinct_rollback_pin(self) -> None:
        catalog = valid_catalog()
        entry = catalog["extensions"][0]
        entry["review"]["status"] = "pending"
        entry["rollback"]["version"] = entry["version"]
        errors = validate_catalog(catalog)
        self.assertTrue(any("review.status" in error for error in errors))
        self.assertTrue(any("rollback" in error for error in errors))

    def test_rejects_noncanonical_utc_timestamp(self) -> None:
        catalog = valid_catalog()
        catalog["extensions"][0]["review"]["reviewed_at"] = "2026-1-4T9:0:0Z"
        self.assertTrue(any("RFC 3339 UTC" in error for error in validate_catalog(catalog)))

    def test_rejects_rollback_that_is_newer_than_current_release(self) -> None:
        catalog = valid_catalog()
        catalog["extensions"][0]["rollback"]["version"] = "1.3.0"
        self.assertTrue(any("earlier release" in error for error in validate_catalog(catalog)))

    def test_versioned_example_is_an_empty_opt_in_catalog(self) -> None:
        catalog = load_catalog(Path("examples/extension_catalog.json"))
        self.assertEqual(catalog, {"schema_version": 1, "extensions": []})

    def test_rejects_unknown_fields_without_evaluating_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executed.txt"
            payload = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')"
            catalog = valid_catalog()
            catalog["extensions"][0]["python"] = payload
            self.assertTrue(validate_catalog(catalog))
            self.assertFalse(marker.exists())

    def test_rejects_duplicate_extension_ids(self) -> None:
        catalog = valid_catalog()
        catalog["extensions"].append(copy.deepcopy(catalog["extensions"][0]))
        self.assertTrue(any("duplicate" in error for error in validate_catalog(catalog)))

    def test_loader_rejects_catalog_over_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_bytes(b" " * (MAX_CATALOG_BYTES + 1))
            with self.assertRaises(CatalogValidationError):
                load_catalog(path)

    def test_loader_rejects_duplicate_json_keys_in_nested_objects(self) -> None:
        raw = json.dumps(valid_catalog())
        raw = raw.replace(
            '"commit": "' + "a" * 40 + '"',
            '"commit": "NOT_A_COMMIT", "commit": "' + "a" * 40 + '"',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(path)

    def test_loader_reports_deep_json_as_invalid_catalog_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep.json"
            path.write_bytes(b"[" * 100_000 + b"]" * 100_000)
            with self.assertRaises(CatalogValidationError):
                load_catalog(path)

    def test_cli_labels_success_as_metadata_only_and_never_runs_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps(valid_catalog()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "scripts/extension_catalog.py", "validate", str(catalog_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("VALID_METADATA_ONLY", result.stdout)
            self.assertIn("no download, installation, or execution", result.stdout)

    def test_cli_reports_deep_json_as_invalid_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "deep.json"
            catalog_path.write_bytes(b"[" * 100_000 + b"]" * 100_000)
            result = subprocess.run(
                [sys.executable, "scripts/extension_catalog.py", "validate", str(catalog_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("INVALID_METADATA", result.stdout)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
