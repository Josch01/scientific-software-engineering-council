"""Native profiles for single and dual providers remain backward-compatible."""
import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from scripts.prepare_agents import make_files, prepare

TASK = json.loads((Path(__file__).resolve().parents[1] / "examples/seir_desktop_audit.json").read_text(encoding="utf-8"))

class TestModes(unittest.TestCase):
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
