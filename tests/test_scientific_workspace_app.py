import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_proposal_diff_can_be_rejected_without_project_writes(self):
        self._exercise_proposal_dialog(decision="reject")

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_approved_proposal_is_persisted_and_becomes_active_workspace(self):
        self._exercise_proposal_dialog(decision="approve")

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_changed_proposal_after_preview_is_not_persisted(self):
        self._exercise_proposal_dialog(decision="stale")

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_proposal_review_displays_unicode_format_controls_as_json_escapes(self):
        output = self._exercise_proposal_dialog(
            decision="reject", proposal_title="Proposed\u200b SIR"
        )

        self.assertIn(r"\u200b", output["diff"])
        self.assertNotIn("\uFFFD", output["diff"])
        self.assertIn(r'"Proposed\u200b SIR"', output["summary"])

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_workspace_audit_requires_explicit_confirmation(self):
        output = self._exercise_workspace_audit_dialog(confirmed=False)

        self.assertEqual(output["audit_calls"], 0)
        self.assertEqual(output["confirm_calls"], 1)
        self.assertIn("no dispone de medidor", output["confirmation_text"])

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_workspace_window_exposes_ai_proposal_action(self):
        import tkinter as tk
        from tkinter import ttk

        from scripts.scientific_workspace_app import create_workspace_window
        from scripts.scientific_workspace_loader import load_scientific_workspace
        from scripts.scientific_workspace_view import build_workspace_view_model

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root)
            workspace = load_scientific_workspace(root, "workspace.json")
            window = create_workspace_window(
                build_workspace_view_model(workspace), project_root=root,
                loaded_workspace=workspace,
            )
            window.withdraw()
            try:
                buttons = [
                    child for container in window.winfo_children()
                    for child in container.winfo_children()
                    if isinstance(child, ttk.Button)
                    and child.cget("text") == "Proponer cambios con IA"
                ]
                self.assertEqual(len(buttons), 1)
                self.assertTrue(buttons[0].instate(["!disabled"]))
            finally:
                window.destroy()
                gc.collect()

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_codex_proposal_action_explains_safe_fallback_without_model_confirmation(self):
        import tkinter as tk
        from tkinter import ttk

        from scripts.configuration import DEFAULT_CONFIG, save_config
        from scripts.scientific_workspace_app import create_workspace_window
        from scripts.scientific_workspace_loader import load_scientific_workspace
        from scripts.scientific_workspace_view import build_workspace_view_model

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root)
            save_config(root, dict(DEFAULT_CONFIG, provider_mode="codex"))
            workspace = load_scientific_workspace(root, "workspace.json")
            window = create_workspace_window(
                build_workspace_view_model(workspace), project_root=root,
                loaded_workspace=workspace,
            )
            window.withdraw()
            try:
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)

                button = next(
                    widget for widget in descendants(window)
                    if isinstance(widget, ttk.Button)
                    and widget.cget("text") == "Proponer cambios con IA"
                )
                with patch("tkinter.messagebox.showinfo") as info, \
                        patch("tkinter.messagebox.askyesno") as confirm, \
                        patch("scripts.scientific_workspace_app.generate_workspace_proposal") as generate:
                    button.invoke()
                info.assert_called_once()
                self.assertIn("manifiesto JSON", info.call_args.args[1])
                confirm.assert_not_called()
                generate.assert_not_called()
            finally:
                window.destroy()
                gc.collect()

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_ai_proposal_requires_confirmation_then_uses_existing_diff_approval(self):
        import tkinter as tk
        from tkinter import ttk

        from scripts.scientific_workspace_app import create_workspace_window
        from scripts.scientific_workspace_loader import load_scientific_workspace
        from scripts.scientific_workspace_view import build_workspace_view_model

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root)
            source_manifest = root / "workspace.json"
            source_bytes = source_manifest.read_bytes()
            active = load_scientific_workspace(root, "workspace.json")
            proposal = json.loads(source_bytes)
            proposal["title"] = "Agent configured SIR workspace"
            proposal["sections"][0]["title"] = "Proposed equation view"
            generated_path = root / ".ssec" / "runs" / "synthetic" / "workspace-proposal.json"
            generated_path.parent.mkdir(parents=True)
            generated_path.write_text(json.dumps(proposal), encoding="utf-8")
            relative_generated = generated_path.relative_to(root).as_posix()
            window = create_workspace_window(
                build_workspace_view_model(active), project_root=root, loaded_workspace=active
            )
            window.withdraw()
            output: dict[str, object] = {}

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            buttons = [
                widget for widget in descendants(window)
                if isinstance(widget, ttk.Button)
                and widget.cget("text") == "Proponer cambios con IA"
            ]
            self.assertEqual(len(buttons), 1)

            def fake_generation(*args, **kwargs):
                output["confirmation_seen_before_provider"] = confirm.call_count
                output["selected_ids"] = args[2]
                output["objective"] = args[3]
                output["cost_acknowledged"] = kwargs.get("accept_unmetered_cost")
                return {
                    "status": "PROPOSAL_READY_NOT_APPROVED",
                    "release_status": "NOT_APPROVED",
                    "scientific_validity": "NOT_ASSESSED",
                    "proposal_relative_path": relative_generated,
                }

            def open_generation_dialog(attempt=0):
                dialogs = [
                    child for child in window.winfo_children()
                    if isinstance(child, tk.Toplevel)
                    and child.title() == "Proponer cambios con IA"
                ]
                if not dialogs:
                    if attempt >= 40:
                        output["error"] = "proposal generation dialog did not open"
                        return
                    window.after(25, lambda: open_generation_dialog(attempt + 1))
                    return
                dialog = dialogs[0]
                objective_widgets = [child for child in descendants(dialog) if isinstance(child, tk.Text)]
                objective_widgets[0].delete("1.0", "end")
                objective_widgets[0].insert("1.0", "Add model and observation views")
                request_buttons = [
                    child for child in descendants(dialog)
                    if isinstance(child, ttk.Button)
                    and child.cget("text") == "Solicitar propuesta…"
                ]
                self.assertEqual(len(request_buttons), 1)
                request_buttons[0].invoke()
                window.after(25, open_review_dialog)

            def open_review_dialog(attempt=0):
                dialogs = [
                    child for child in window.winfo_children()
                    if isinstance(child, tk.Toplevel)
                    and child.title() == "Revisar propuesta de workspace"
                ]
                if not dialogs:
                    if attempt >= 80:
                        output["error"] = "generated proposal did not reach diff review"
                        return
                    window.after(25, lambda: open_review_dialog(attempt + 1))
                    return
                dialog = dialogs[0]
                text_widgets = [child for child in descendants(dialog) if isinstance(child, tk.Text)]
                output["diff"] = text_widgets[0].get("1.0", "end-1c")
                approve_buttons = [
                    child for child in descendants(dialog)
                    if isinstance(child, ttk.Button) and child.cget("text") == "Aprobar y guardar"
                ]
                self.assertEqual(len(approve_buttons), 1)
                approve_buttons[0].invoke()
                output["approved_files"] = list(root.glob(".ssec-workspace-*.json"))

            error_messages: list[str] = []
            try:
                with patch(
                    "scripts.scientific_workspace_app.generate_workspace_proposal",
                    side_effect=fake_generation,
                ) as generate, patch(
                    "tkinter.messagebox.askyesno", return_value=True
                ) as confirm, patch(
                    "tkinter.messagebox.showerror",
                    side_effect=lambda _title, message, **_kw: error_messages.append(str(message)),
                ):
                    window.after(25, open_generation_dialog)
                    buttons[0].invoke()
                    deadline = time.monotonic() + 5
                    while "approved_files" not in output and time.monotonic() < deadline:
                        window.update()
                        time.sleep(0.01)
                    output["generation_calls"] = generate.call_count
                    output["confirm_calls"] = confirm.call_count
                    output["confirmation_text"] = "\n".join(
                        str(call.args[1]) for call in confirm.call_args_list
                    )
                self.assertNotIn("error", output, output.get("error"))
                self.assertEqual(output["generation_calls"], 1)
                self.assertEqual(output["confirm_calls"], 2)
                self.assertEqual(output["confirmation_seen_before_provider"], 1)
                self.assertEqual(output["selected_ids"], ("model",))
                self.assertEqual(output["objective"], "Add model and observation views")
                self.assertTrue(output["cost_acknowledged"])
                self.assertIn("puede consumir cuota", output["confirmation_text"])
                self.assertIn("Agent configured SIR workspace", output["diff"])
                self.assertEqual(source_manifest.read_bytes(), source_bytes)
                self.assertEqual(len(output["approved_files"]), 1)
                self.assertEqual(error_messages, [])
            finally:
                if window.winfo_exists():
                    window.destroy()
                gc.collect()

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_confirmed_workspace_audit_runs_async_and_displays_unapproved_result(self):
        output = self._exercise_workspace_audit_dialog(confirmed=True)

        self.assertEqual(output["audit_calls"], 1)
        self.assertEqual(output["confirm_calls"], 1)
        self.assertEqual(output["selected_ids"], ("model",))
        self.assertEqual(output["dispatched_ids"], ("model",))
        self.assertTrue(output["cost_acknowledged"])
        self.assertEqual(output["release_status"], "NOT_APPROVED")
        self.assertIn("Resultado · Auditoría", output["tabs"])

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_workspace_audit_cancel_button_signals_worker_and_displays_cancelled(self):
        output = self._exercise_workspace_audit_dialog(confirmed=True, request_cancel=True)

        self.assertEqual(output["audit_calls"], 1)
        self.assertTrue(output["cancel_marker_observed"])
        self.assertEqual(output["execution"], "CANCELLED")
        self.assertEqual(output["release_status"], "NOT_APPROVED")

    @unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "Tk display is unavailable")
    def test_closing_workspace_during_audit_cancels_before_destroy(self):
        output = self._exercise_workspace_audit_dialog(
            confirmed=True, request_cancel=True, close_window=True
        )

        self.assertTrue(output["window_closed"])
        self.assertTrue(output["cancel_marker_observed"])
        self.assertEqual(output["execution"], "CANCELLED")
        self.assertEqual(output["release_status"], "NOT_APPROVED")

    def _exercise_workspace_audit_dialog(
        self, *, confirmed: bool, request_cancel: bool = False, close_window: bool = False
    ):
        import tkinter as tk
        from tkinter import ttk

        from scripts.scientific_workspace_app import create_workspace_window
        from scripts.scientific_workspace_loader import load_scientific_workspace
        from scripts.scientific_workspace_view import build_workspace_view_model

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root)
            workspace = load_scientific_workspace(root, "workspace.json")
            window = create_workspace_window(
                build_workspace_view_model(workspace), project_root=root, loaded_workspace=workspace
            )
            window.withdraw()
            output: dict[str, object] = {}

            def window_exists() -> bool:
                try:
                    return bool(window.winfo_exists())
                except tk.TclError:
                    return False

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            buttons = [
                widget for widget in descendants(window)
                if isinstance(widget, ttk.Button)
                and widget.cget("text") == "Solicitar auditoría…"
            ]
            self.assertEqual(len(buttons), 1)

            def fake_audit(*_args, **kwargs):
                output["cost_acknowledged"] = kwargs.get("accept_unmetered_cost")
                output["dispatched_ids"] = _args[2]
                if request_cancel:
                    cancel_file = kwargs["cancel_file"]
                    deadline = time.monotonic() + 2
                    while not cancel_file.exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    output["cancel_marker_observed"] = cancel_file.exists()
                report = {
                    "execution": "CANCELLED" if request_cancel else "PROCESSES_COMPLETED_NOT_AUDITED",
                    "release_status": "NOT_APPROVED",
                    "workspace_audit": {
                        "workspace_id": "app-test",
                        "cancellation_requested": request_cancel,
                    },
                }
                output["worker_result"] = report
                return report

            def interact(attempt: int = 0) -> None:
                dialogs = [
                    child for child in window.winfo_children()
                    if isinstance(child, tk.Toplevel)
                    and child.title() == "Solicitar auditoría del workspace"
                ]
                if not dialogs:
                    if attempt >= 40:
                        output["error"] = "workspace audit dialog did not open"
                        return
                    window.after(25, lambda: interact(attempt + 1))
                    return
                dialog = dialogs[0]
                tables = [child for child in descendants(dialog) if isinstance(child, ttk.Treeview)]
                output["selected_ids"] = tables[0].selection() if tables else ()
                send_buttons = [
                    child for child in descendants(dialog)
                    if isinstance(child, ttk.Button) and child.cget("text") == "Enviar a especialistas…"
                ]
                if not send_buttons:
                    output["error"] = "workspace audit dispatch button is missing"
                    return
                send_buttons[0].invoke()
                if confirmed and request_cancel:
                    if close_window:
                        window.tk.call(window.protocol("WM_DELETE_WINDOW"))
                    else:
                        cancel_buttons = [
                            child for child in descendants(window)
                            if isinstance(child, ttk.Button)
                            and child.cget("text") == "Cancelar auditoría"
                        ]
                        if cancel_buttons:
                            cancel_buttons[0].invoke()
                if not confirmed:
                    cancel_buttons = [
                        child for child in descendants(dialog)
                        if isinstance(child, ttk.Button) and child.cget("text") == "Cancelar"
                    ]
                    if cancel_buttons:
                        cancel_buttons[0].invoke()

            try:
                with patch(
                    "tkinter.messagebox.askyesno", return_value=confirmed
                ) as confirm, patch(
                    "scripts.scientific_workspace_app.run_workspace_audit",
                    side_effect=fake_audit,
                ) as audit:
                    window.after(50, interact)
                    buttons[0].invoke()
                    deadline = time.monotonic() + 3
                    while confirmed and time.monotonic() < deadline:
                        if not window_exists():
                            break
                        window.update()
                        if not window_exists():
                            break
                        if any(
                            isinstance(child, ttk.Notebook)
                            and any(child.tab(tab, "text") == "Resultado · Auditoría" for tab in child.tabs())
                            for child in descendants(window)
                        ):
                            break
                        time.sleep(0.01)
                    output["audit_calls"] = audit.call_count
                    output["confirm_calls"] = confirm.call_count
                    output["confirmation_text"] = confirm.call_args.args[1] if confirm.call_args else ""
                    if window_exists():
                        output["tabs"] = [
                            child.tab(tab, "text")
                            for child in descendants(window) if isinstance(child, ttk.Notebook)
                            for tab in child.tabs()
                        ]
                        result_texts = [
                            child.get("1.0", "end-1c")
                            for child in descendants(window)
                            if isinstance(child, tk.Text)
                            and "workspace_audit" in child.get("1.0", "end-1c")
                        ]
                        displayed = json.loads(result_texts[-1]) if result_texts else {}
                    else:
                        output["tabs"] = []
                        displayed = output.get("worker_result", {})
                    output["release_status"] = displayed.get("release_status")
                    output["execution"] = displayed.get("execution")
                    output["window_closed"] = not window_exists()
                self.assertNotIn("error", output, output.get("error"))
            finally:
                if window_exists():
                    window.destroy()
                gc.collect()
            return output

    def _exercise_proposal_dialog(self, *, decision: str, proposal_title: str | None = None):
        import tkinter as tk
        from tkinter import ttk

        from scripts.scientific_workspace_app import create_workspace_window
        from scripts.scientific_workspace_loader import load_scientific_workspace
        from scripts.scientific_workspace_view import build_workspace_view_model

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_workspace(root)
            source_manifest = root / "workspace.json"
            source_bytes = source_manifest.read_bytes()
            resource = b'{"model_type":"sir","status":"proposal fixture"}\n'
            (root / "proposal-model.json").write_bytes(resource)
            proposal = json.loads(source_bytes)
            proposal["title"] = proposal_title or "Agent proposal fixture"
            proposal["resources"][0]["path"] = "proposal-model.json"
            proposal["resources"][0]["sha256"] = hashlib.sha256(resource).hexdigest()
            proposal["sections"][0]["title"] = "Proposed SIR section"
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
            proposal_bytes = proposal_path.read_bytes()
            active = load_scientific_workspace(root, "workspace.json")
            window = create_workspace_window(
                build_workspace_view_model(active), project_root=root, loaded_workspace=active
            )
            window.withdraw()
            output: dict[str, object] = {}

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            buttons = [
                widget for widget in descendants(window)
                if isinstance(widget, ttk.Button)
                and widget.cget("text") == "Revisar propuesta…"
            ]
            self.assertEqual(len(buttons), 1, "proposal review button should be available for an active workspace")

            def act_on_dialog(attempt: int = 0) -> None:
                dialogs = [
                    child for child in window.winfo_children()
                    if isinstance(child, tk.Toplevel)
                    and child.title() == "Revisar propuesta de workspace"
                ]
                if not dialogs:
                    if attempt >= 40:
                        output["error"] = "proposal diff dialog did not open"
                        return
                    window.after(25, lambda: act_on_dialog(attempt + 1))
                    return
                dialog = dialogs[0]
                text_widgets = [child for child in descendants(dialog) if isinstance(child, tk.Text)]
                output["diff"] = text_widgets[0].get("1.0", "end-1c") if text_widgets else ""
                summary_widgets = [
                    child for child in descendants(dialog)
                    if isinstance(child, ttk.Label) and "SHA-256 semántico:" in child.cget("text")
                ]
                output["summary"] = summary_widgets[0].cget("text") if summary_widgets else ""
                if decision == "stale":
                    changed = json.loads(proposal_path.read_text(encoding="utf-8"))
                    changed["title"] = "Changed after preview"
                    proposal_path.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
                button_text = "Rechazar" if decision == "reject" else "Aprobar y guardar"
                action_buttons = [
                    widget for widget in descendants(dialog)
                    if isinstance(widget, ttk.Button) and widget.cget("text") == button_text
                ]
                if not action_buttons:
                    output["error"] = f"missing dialog action {button_text!r}"
                    return
                action_buttons[0].invoke()
                if decision == "stale":
                    output["errors_shown"] = list(error_messages)
                    reject_buttons = [
                        widget for widget in descendants(dialog)
                        if isinstance(widget, ttk.Button) and widget.cget("text") == "Rechazar"
                    ]
                    if reject_buttons:
                        reject_buttons[0].invoke()

            error_messages: list[str] = []
            try:
                with patch(
                    "tkinter.filedialog.askopenfilename", return_value=str(proposal_path)
                ), patch("tkinter.messagebox.askyesno", return_value=True) as confirm, patch(
                    "tkinter.messagebox.showerror",
                    side_effect=lambda title, message, **_kw: error_messages.append(str(message)),
                ):
                    window.after(50, act_on_dialog)
                    buttons[0].invoke()
                    output["confirm_calls"] = confirm.call_count
                self.assertNotIn("error", output, output.get("error"))
                self.assertIn("Proposed SIR section", output["diff"])
                approved_files = list(root.glob(".ssec-workspace-*.json"))
                if decision == "reject":
                    self.assertEqual(approved_files, [])
                    self.assertEqual(source_manifest.read_bytes(), source_bytes)
                    self.assertEqual(proposal_path.read_bytes(), proposal_bytes)
                    self.assertEqual(output["confirm_calls"], 0)
                elif decision == "approve":
                    self.assertEqual(len(approved_files), 1)
                    self.assertEqual(source_manifest.read_bytes(), source_bytes)
                    approved = load_scientific_workspace(
                        root, approved_files[0].relative_to(root).as_posix()
                    )
                    self.assertEqual(approved.summary.title, "Agent proposal fixture")
                    notebooks = [widget for widget in descendants(window) if isinstance(widget, ttk.Notebook)]
                    self.assertEqual(len(notebooks), 1)
                    tab_names = [notebooks[0].tab(tab, "text") for tab in notebooks[0].tabs()]
                    self.assertIn("Proposed SIR section", tab_names)
                    self.assertEqual(output["confirm_calls"], 1)
                else:
                    self.assertEqual(approved_files, [])
                    self.assertTrue(any("proposal changed after preview" in item for item in error_messages))
                    self.assertEqual(source_manifest.read_bytes(), source_bytes)
            finally:
                window.destroy()
                gc.collect()
            return output


if __name__ == "__main__":
    unittest.main()
