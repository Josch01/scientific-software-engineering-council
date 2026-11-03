import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def _make_workspace(
    root: Path,
    *,
    digest: str | None = None,
    content: bytes = b'{"name":"generic model specification"}',
    component_count: int = 1,
) -> None:
    resource_path = root / "model.json"
    resource_path.write_bytes(content)
    manifest = {
        "schema_version": 1,
        "workspace_id": "app-test",
        "title": "Application test",
        "resources": [
            {
                "id": "model",
                "kind": "model_spec",
                "path": "model.json",
                "sha256": digest or hashlib.sha256(content).hexdigest(),
            }
        ],
        "sections": [
            {
                "id": "model-section",
                "title": "Model",
                "components": [
                    {
                        "id": f"equations-{index}",
                        "type": "equation_view",
                        "title": "Model payload",
                        "resource_refs": ["model"],
                        "config": {},
                    }
                    for index in range(component_count)
                ],
            }
        ],
    }
    (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")


class ScientificWorkspaceAppTests(unittest.TestCase):
    def _run_check(self, root: Path) -> subprocess.CompletedProcess[str]:
        app_path = Path(__file__).resolve().parents[1] / "scripts" / "scientific_workspace_app.py"
        code = (
            "import runpy,sys; "
            f"ns=runpy.run_path({str(app_path)!r}, run_name='ssec_workspace_app'); "
            f"status=ns['main'](['--check','--project-root',{str(root)!r},'workspace.json']); "
            "print('TK_IMPORTED='+str('tkinter' in sys.modules)); "
            "raise SystemExit(status)"
        )
        return subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )

    def test_headless_check_prepares_views_without_importing_tkinter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root)
            completed = self._run_check(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output, marker = completed.stdout.strip().splitlines()
        report = json.loads(output)
        self.assertEqual(report["status"], "VIEW_PREPARED")
        self.assertEqual(report["artifact_status"], "ARTIFACT_DIGESTS_MATCHED")
        self.assertEqual(report["component_count"], 1)
        self.assertEqual(marker, "TK_IMPORTED=False")

    def test_digest_failure_is_not_reported_as_prepared_view(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root, digest="0" * 64)
            completed = self._run_check(root)

        self.assertEqual(completed.returncode, 2)
        self.assertIn("INVALID", completed.stderr)
        self.assertNotIn("VIEW_PREPARED", completed.stdout)

    def test_component_decode_failure_is_not_reported_as_prepared_view(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root, content=b'{"duplicate":1,"duplicate":2}')
            completed = self._run_check(root)

        self.assertEqual(completed.returncode, 2)
        report = json.loads(completed.stdout.splitlines()[0])
        self.assertEqual(report["status"], "VIEW_ERRORS")
        self.assertIn("duplicate", report["errors"][0]["message"])

    def test_renderer_registry_covers_exact_manifest_component_types(self):
        from scripts import scientific_workspace_app, scientific_workspace_view

        self.assertEqual(
            set(scientific_workspace_app.COMPONENT_RENDERERS),
            set(scientific_workspace_view.SUPPORTED_COMPONENT_TYPES),
        )

    def test_json_view_kind_cannot_dispatch_an_untrusted_component_to_sir_renderer(self):
        from scripts import scientific_workspace_app
        from scripts.scientific_workspace_view import ComponentView

        cases = (
            (
                "equation_view",
                "sir_equations_v1",
                scientific_workspace_app._render_equations,
            ),
            (
                "parameter_table",
                "sir_parameters_v1",
                scientific_workspace_app._render_parameters,
            ),
        )
        for component_type, marker, renderer in cases:
            with self.subTest(component_type=component_type):
                component = ComponentView(
                    component_id="untrusted",
                    component_type=component_type,
                    title="Untrusted model",
                    status="ok",
                    message="",
                    content={"view_kind": marker},
                )
                with patch.object(scientific_workspace_app, "_render_json") as render_json:
                    renderer(object(), component, object(), object())

                render_json.assert_called_once()

    def test_json_text_renderer_neutralizes_directional_format_controls(self):
        from scripts.scientific_workspace_app import _format_json

        rendered = _format_json({"label": "visible\u202ehidden"})
        surrogate_rendered = _format_json({"label": "isolated\ud800surrogate"})

        self.assertNotIn("\u202e", rendered)
        self.assertIn("\uFFFD", rendered)
        self.assertNotIn("\ud800", surrogate_rendered)
        self.assertIn("\uFFFD", surrogate_rendered)

    def test_headless_check_reports_ui_component_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root, component_count=101)
            completed = self._run_check(root)

        self.assertEqual(completed.returncode, 2)
        report = json.loads(completed.stdout.splitlines()[0])
        self.assertEqual(report["status"], "VIEW_LIMITED")
        self.assertEqual(report["rendered_component_count"], 100)
        self.assertEqual(report["omitted_component_count"], 1)

    def test_plot_range_mapping_stays_finite_for_extreme_finite_values(self):
        from scripts.scientific_workspace_app import _range_fraction, _range_interpolate

        fraction = _range_fraction(1e308, -1e308, 1e308)
        middle = _range_interpolate(-1e308, 1e308, 0.5)

        self.assertEqual(fraction, 1.0)
        self.assertEqual(middle, 0.0)

    def test_window_root_uses_child_toplevel_when_parent_is_supplied(self):
        from scripts.scientific_workspace_app import _create_window_root

        class TkFactory:
            def __init__(self):
                self.calls = []

            def Tk(self):
                value = object()
                self.calls.append(("root", None, value))
                return value

            def Toplevel(self, parent):
                value = object()
                self.calls.append(("child", parent, value))
                return value

        toolkit = TkFactory()
        parent = object()
        child = _create_window_root(toolkit, parent)
        root = _create_window_root(toolkit, None)

        self.assertEqual(toolkit.calls[0][0], "child")
        self.assertIs(toolkit.calls[0][1], parent)
        self.assertIs(child, toolkit.calls[0][2])
        self.assertEqual(toolkit.calls[1][0], "root")
        self.assertIsNone(toolkit.calls[1][1])
        self.assertIs(root, toolkit.calls[1][2])

    def test_project_root_hint_accepts_only_an_existing_directory(self):
        from scripts.scientific_workspace_app import _project_root_hint

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hint = _project_root_hint(root)
            self.assertIsNotNone(hint)
            self.assertTrue(hint.samefile(root))
            self.assertIsNone(_project_root_hint(root / "missing"))
            self.assertIsNone(_project_root_hint(None))
            self.assertIsNone(_project_root_hint(""))


if __name__ == "__main__":
    unittest.main()
