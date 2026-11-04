"""Headless tests; execution limits remain expressly advisory."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.configuration import DEFAULT_CONFIG, config_path, load_config, save_config, validate_config
from scripts.config_panel import build_policy
from scripts.prepare_agents import make_files, prepare

ROOT = Path(__file__).resolve().parents[1]
TASK = json.loads((ROOT / "examples/seir_desktop_audit.json").read_text(encoding="utf-8"))

class ConfigTests(unittest.TestCase):
    def test_defaults_valid(self):
        self.assertEqual(validate_config(DEFAULT_CONFIG), DEFAULT_CONFIG)

    def test_reject_unknown_fields(self):
        with self.assertRaises(ValueError):
            validate_config(dict(DEFAULT_CONFIG, allow_shell=True))

    def test_reject_bool_as_limit_and_nan(self):
        with self.assertRaises(ValueError):
            validate_config(dict(DEFAULT_CONFIG, max_parallel_agents=True))
        with self.assertRaises(ValueError):
            validate_config(dict(DEFAULT_CONFIG, budget={"max_runtime_minutes": 3, "max_estimated_cost_usd": float("nan")}))

    def test_user_input(self):
        x = build_policy("both", "3", "read_only", "40", "0.50", "strict")
        self.assertEqual(x["max_parallel_agents"], 3)
        self.assertEqual(x["budget"]["max_estimated_cost_usd"], 0.5)
        with self.assertRaises(ValueError):
            build_policy("codex", "2.5", "read_only", "30", "3", "standard")

    def test_agy_provider_mode_is_explicitly_valid(self):
        config = build_policy("agy", "2", "read_only", "60", "10", "standard")
        self.assertEqual(validate_config(config)["provider_mode"], "agy")

    def test_save_load_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved = save_config(root, DEFAULT_CONFIG)
            self.assertEqual(saved, config_path(root))
            self.assertEqual(load_config(saved), DEFAULT_CONFIG)
            self.assertEqual(save_config(root, DEFAULT_CONFIG), saved)

    def test_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "elsewhere").mkdir()
            (root / ".ssec").symlink_to(root / "elsewhere", target_is_directory=True)
            with self.assertRaises(ValueError):
                save_config(root, DEFAULT_CONFIG)

    def test_mode_config_mismatch(self):
        with self.assertRaises(ValueError):
            make_files(TASK, "codex", DEFAULT_CONFIG)

    def test_cap_does_not_drop_reviews(self):
        config = dict(DEFAULT_CONFIG, max_parallel_agents=1, provider_mode="both")
        m, _ = make_files(TASK, "both", config)
        self.assertTrue(all(len(w["roles"]) <= 1 for w in m["waves"]))
        self.assertTrue(any(w["phase"] == "review" for w in m["waves"]))
        first_review = next(i for i, w in enumerate(m["waves"]) if w["phase"] == "review")
        self.assertTrue(all(w["phase"] == "implementation" for w in m["waves"][:first_review]))
        self.assertTrue(all(w["phase"] == "review" for w in m["waves"][first_review:]))
        self.assertEqual(m["policy"]["provider_mode"], "both")
        self.assertIn("scientific_validation", m["required_evidence"])
        self.assertIn("independent_review", m["required_evidence"])
        self.assertFalse(m["runtime_guarantees"]["max_parallel_enforced"])

    def test_audit_basic_never_removes_high_risk_reviewers(self):
        basic = dict(DEFAULT_CONFIG, audit_level="basic")
        m, _ = make_files(TASK, "gemini", basic)
        roles = [a["role"] for a in m["assignments"]]
        self.assertIn("independent_reviewer", roles)
        self.assertIn("security_reviewer", roles)

    def test_strict_adds_review_for_low_risk(self):
        task = dict(TASK, risk="R1", kind="build", domains=["general"])
        m, _ = make_files(task, "gemini", dict(DEFAULT_CONFIG, audit_level="strict"))
        self.assertIn("security_audit", m["required_evidence"])
        self.assertIn("independent_review", m["required_evidence"])

    def test_policy_propagated_into_profiles(self):
        p = dict(DEFAULT_CONFIG, provider_mode="codex", permissions="read_only")
        m, files = make_files(TASK, "codex", p)
        self.assertEqual(m["policy"]["permissions"], "read_only")
        self.assertTrue(any("SOLO LECTURA" in v for k, v in files.items() if k.endswith(".toml")))

    def test_prepare_dry_run_doesnt_write_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = prepare(TASK, "gemini", root, config=DEFAULT_CONFIG)
            self.assertFalse(result["applied"])
            self.assertEqual(list(root.iterdir()), [])

    def test_headless_gui_check(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/config_panel.py"), "--check"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GUI model valid", result.stdout)

if __name__ == "__main__":
    unittest.main()
