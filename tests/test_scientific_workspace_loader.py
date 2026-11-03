import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def minimal_manifest(content: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "workspace_id": "sir-study",
        "title": "Model workspace",
        "resources": [
            {
                "id": "observations",
                "kind": "observations",
                "path": "data/observations.bin",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
        "sections": [
            {
                "id": "data",
                "title": "Data",
                "components": [
                    {
                        "id": "table",
                        "type": "observation_table",
                        "title": "Observations",
                        "resource_refs": ["observations"],
                        "config": {},
                    }
                ],
            }
        ],
    }


class ScientificWorkspaceLoaderTests(unittest.TestCase):
    def _loader(self):
        spec = importlib.util.find_spec("scripts.scientific_workspace_loader")
        self.assertIsNotNone(spec, "safe workspace loader module has not been implemented")
        return importlib.import_module("scripts.scientific_workspace_loader")

    def test_loads_bytes_only_after_digest_verification(self):
        loader = self._loader()
        content = b"observations are inert bytes"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            (root / "data" / "observations.bin").write_bytes(content)
            (root / "workspace.json").write_text(
                json.dumps(minimal_manifest(content)), encoding="utf-8"
            )

            loaded = loader.load_scientific_workspace(root, "workspace.json")

        resource = loaded.resources[0]
        self.assertEqual(resource.resource_id, "observations")
        self.assertEqual(resource.content, content)
        self.assertEqual(resource.sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(loaded.summary.workspace_id, "sir-study")

    def test_missing_digest_is_rejected_before_resource_open(self):
        loader = self._loader()
        manifest = minimal_manifest(b"missing resource")
        del manifest["resources"][0]["sha256"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "requires a SHA-256 digest"):
                loader.load_scientific_workspace(root, "workspace.json")

    def test_digest_mismatch_aborts_without_returning_partial_workspace(self):
        loader = self._loader()
        manifest = minimal_manifest(b"expected")
        manifest["resources"].append(
            {
                "id": "second",
                "kind": "generic",
                "path": "data/second.bin",
                "sha256": hashlib.sha256(b"declared").hexdigest(),
            }
        )
        manifest["sections"][0]["components"][0]["type"] = "artifact_browser"
        manifest["sections"][0]["components"][0]["resource_refs"] = [
            "observations",
            "second",
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            (root / "data" / "observations.bin").write_bytes(b"expected")
            (root / "data" / "second.bin").write_bytes(b"actual")
            (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
                loader.load_scientific_workspace(root, "workspace.json")

    def test_per_resource_and_total_byte_budgets_fail_closed(self):
        loader = self._loader()
        content = b"1234"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            (root / "data" / "observations.bin").write_bytes(content)
            (root / "workspace.json").write_text(
                json.dumps(minimal_manifest(content)), encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "read limit"):
                loader.load_scientific_workspace(
                    root, "workspace.json", max_resource_bytes=3
                )
            with self.assertRaisesRegex(ValueError, "read limit"):
                loader.load_scientific_workspace(
                    root, "workspace.json", max_total_bytes=3
                )
            with self.assertRaisesRegex(ValueError, "max_resource_bytes"):
                loader.load_scientific_workspace(
                    root,
                    "workspace.json",
                    max_resource_bytes=loader.MAX_RESOURCE_BYTES + 1,
                )

    def test_read_limit_consumes_at_most_budget_plus_one(self):
        loader = self._loader()

        class CountingReader:
            def __init__(self):
                self.bytes_returned = 0

            def read(self, size):
                self.bytes_returned += size
                return b"x" * size

        reader = CountingReader()
        with self.assertRaisesRegex(ValueError, "exceeds the 5-byte"):
            loader._read_limited(reader, 5, "test resource")
        self.assertEqual(reader.bytes_returned, 6)

    def test_manifest_path_cannot_escape_project_root(self):
        loader = self._loader()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            root.mkdir()
            outside = Path(temp) / "workspace.json"
            outside.write_text(json.dumps(minimal_manifest(b"x")), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "traversal segment|portable relative path"):
                loader.load_scientific_workspace(root, "../workspace.json")

    def test_symlink_or_junction_escape_is_rejected(self):
        loader = self._loader()
        content = b"external data"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            outside = Path(temp) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "observations.bin").write_bytes(content)
            try:
                os.symlink(outside, root / "linked", target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows host does not grant symlink creation privilege")
                raise
            manifest = minimal_manifest(content)
            manifest["resources"][0]["path"] = "linked/observations.bin"
            (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "safely open|symlink|reparse|outside"):
                loader.load_scientific_workspace(root, "workspace.json")

    def test_non_regular_resource_is_rejected_without_blocking(self):
        loader = self._loader()
        content = b"placeholder"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            resource_path = root / "data" / "observations.bin"
            if hasattr(os, "mkfifo"):
                os.mkfifo(resource_path)
            else:
                resource_path.mkdir()
            (root / "workspace.json").write_text(
                json.dumps(minimal_manifest(content)), encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "regular file|safely open|cannot open project resource"):
                loader.load_scientific_workspace(root, "workspace.json")

    def test_cli_outputs_only_verified_metadata(self):
        content = b"SECRET_RESOURCE_CONTENT_SENTINEL"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            (root / "data" / "observations.bin").write_bytes(content)
            (root / "workspace.json").write_text(
                json.dumps(minimal_manifest(content)), encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "scripts" / "scientific_workspace_loader.py"),
                    "--project-root",
                    str(root),
                    "workspace.json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "ARTIFACT_DIGESTS_MATCHED")
        self.assertEqual(result["resources"][0]["byte_count"], len(content))
        self.assertNotIn(content.decode(), completed.stdout)

    def test_cli_invalid_digest_exits_two_without_printing_resource_bytes(self):
        content = b"CLI_SECRET_SENTINEL"
        manifest = minimal_manifest(b"different")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            (root / "data" / "observations.bin").write_bytes(content)
            (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "scripts" / "scientific_workspace_loader.py"),
                    "--project-root",
                    str(root),
                    "workspace.json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertNotIn(content.decode(), completed.stdout + completed.stderr)


class LimitedReadTests(unittest.TestCase):
    def test_file_growing_past_the_limit_is_still_bounded(self):
        module = importlib.import_module("scripts.scientific_workspace_loader")
        # The public integration test uses real files; this small stream probe
        # specifically checks the helper's requested read sizes.
        class GrowingReader:
            def __init__(self):
                self.requested = 0

            def read(self, size):
                self.requested += size
                return b"x" * size

        reader = GrowingReader()
        with self.assertRaises(ValueError):
            module._read_limited(reader, 7, "growing file")
        self.assertEqual(reader.requested, 8)

    def test_windows_containment_uses_component_boundary_and_normalizes_unc(self):
        module = importlib.import_module("scripts.scientific_workspace_loader")
        contained = getattr(module, "_windows_paths_contained", None)
        self.assertTrue(callable(contained), "component-aware Windows path check is missing")
        self.assertTrue(
            contained(
                r"C:\Projects\SIR", r"\\?\C:\Projects\SIR\data.csv"
            )
        )
        self.assertFalse(
            contained(
                r"C:\Projects\SIR", r"C:\Projects\SIR-escape\secret.csv"
            )
        )
        self.assertTrue(
            contained(
                r"\\server\share\SIR",
                r"\\?\UNC\server\share\SIR\data.csv",
            )
        )

    def test_verified_resource_records_cannot_be_created_without_loader(self):
        module = importlib.import_module("scripts.scientific_workspace_loader")
        with self.assertRaisesRegex(TypeError, "loader"):
            module.LoadedResource("id", "generic", "data.bin", "0" * 64, b"content")


if __name__ == "__main__":
    unittest.main()
