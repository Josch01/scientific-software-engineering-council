"""Native provider modes preparation: no external AI needed."""
import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from scripts.prepare_agents import make_files, prepare

TASK = json.loads(
    (Path(__file__).resolve().parents[1] / "examples/seir_desktop_audit.json")
    .read_text(encoding="utf-8")
)

class TestProviderModes(unittest.TestCase):
    def test_gemini_only(self):
        data, files = make_files(TASK, "gemini")
        self.assertTrue(all(x["provider"] == "gemini" for x in data["assignments"]))
        self.assertFalse(any(x.startswith(".codex/agents/") for x in files))
        self.assertTrue(any(x.startswith(".gemini/agents/") for x in files))

    def test_codex_only_valid_toml(self):
        data, files = make_files(TASK, "codex")
        self.assertTrue(all(x["provider"] == "codex" for x in data["assignments"]))
        for path, content in files.items():
            if path.endswith(".toml"):
                self.assertIn("developer_instructions", tomllib.loads(content))

    def test_both_separate_reviewers(self):
        data, _ = make_files(TASK, "both")
        self.assertEqual({x["provider"] for x in data["assignments"]}, {"codex", "gemini"})
        self.assertTrue(all(x["provider"] == "gemini" for x in data["assignments"] if x["reviewer"]))

    def test_preview_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            x = prepare(TASK, "both", Path(d))
            self.assertFalse(x["applied"])
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_apply_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            x = prepare(TASK, "both", root, apply=True)
            self.assertTrue(x["applied"])
            self.assertTrue((root / ".gemini/agents").is_dir())
            self.assertTrue((root / ".codex/agents").is_dir())
            self.assertTrue((root / ".ssec/tasks" / TASK["task_id"] / "dispatch.json").exists())
            prepare(TASK, "both", root, apply=True)

    def test_refuses_existing_file_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, files = make_files(TASK, "codex")
            path = root / next(x for x in files if x.endswith(".toml"))
            path.parent.mkdir(parents=True)
            path.write_text("DO NOT TOUCH", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                prepare(TASK, "codex", root, apply=True)
            self.assertEqual(path.read_text(encoding="utf-8"), "DO NOT TOUCH")

    def test_rejects_unsafe_ids(self):
        with self.assertRaises(ValueError):
            make_files(dict(TASK, task_id="../other"), "gemini")

    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "other").mkdir()
            (root / ".gemini").symlink_to(root / "other", target_is_directory=True)
            with self.assertRaises(ValueError):
                prepare(TASK, "gemini", root, apply=True)

if __name__ == "__main__":
    unittest.main()
