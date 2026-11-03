import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from scripts.scientific_core import OdeProblem, OdeSolution, solve_rk4
from scripts.scientific_workspace_loader import load_scientific_workspace
from scripts.scientific_workspace_view import build_workspace_view_model


def _workspace(root: Path):
    model_bytes = b'{"equations":"SIR test fixture"}'
    (root / "model.json").write_bytes(model_bytes)
    initial_solution = solve_rk4(
        OdeProblem(
            rhs=lambda _time, _state, _parameters: (0.0, 0.0),
            t_span=(0.0, 1.0),
            initial_state=(90.0, 10.0),
            state_names=("S", "I"),
        ),
        1.0,
    )
    result_bytes = json.dumps(initial_solution.to_dict()).encode("utf-8")
    (root / "simulation.json").write_bytes(result_bytes)
    manifest = {
        "schema_version": 1,
        "workspace_id": "approved-action-test",
        "title": "Approved action test",
        "resources": [
            {"id": "model", "kind": "model_spec", "path": "model.json",
             "sha256": hashlib.sha256(model_bytes).hexdigest()},
            {"id": "simulation", "kind": "simulation_result", "path": "simulation.json",
             "sha256": hashlib.sha256(result_bytes).hexdigest()},
        ],
        "sections": [{
            "id": "results", "title": "Results", "components": [{
                "id": "trajectory", "type": "simulation_plot", "title": "Trajectory",
                "resource_refs": ["simulation"],
                "config": {"x_axis": "time", "series": ["I"]},
            }],
        }],
    }
    (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
    loaded = load_scientific_workspace(root, "workspace.json")
    component = build_workspace_view_model(loaded).sections[0].components[0]
    return loaded, component


class ApprovedSimulationActionTests(unittest.TestCase):
    def test_ui_action_selection_uses_only_matching_host_registered_callback(self):
        from scripts.scientific_workspace_actions import ApprovedSimulationAction
        from scripts.scientific_workspace_app import _approved_action_for

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp))
            action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Reviewed model callback",
                callback=lambda _loaded, _component: None,
            )
            wrong_workspace = ApprovedSimulationAction(
                workspace_id="another-project",
                label="Other callback",
                callback=lambda _loaded, _component: None,
            )

            self.assertIsNone(_approved_action_for(component, workspace, {}))
            self.assertIs(_approved_action_for(
                component, workspace, {component.component_id: action}
            ), action)
            self.assertIsNone(_approved_action_for(
                component, workspace, {component.component_id: wrong_workspace}
            ))
            self.assertIsNone(_approved_action_for(
                replace(component, component_type="equation_view"),
                workspace,
                {component.component_id: action},
            ))

    def test_ui_worker_publishes_terminal_error_for_base_exception(self):
        from scripts.scientific_workspace_actions import (
            ApprovedSimulationAction,
            request_approved_simulation,
        )
        from scripts.scientific_workspace_app import _run_simulation_ticket_for_ui

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp))

            def exit_callback(_loaded, _component):
                raise SystemExit("callback exited")

            action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Reviewed callback",
                callback=exit_callback,
            )
            ticket = request_approved_simulation(
                action, workspace, component, confirm=lambda _prompt: True
            )
            outcome, message = _run_simulation_ticket_for_ui(ticket)

        self.assertEqual(outcome, "error")
        self.assertIn("SystemExit", message)
        self.assertIn("callback exited", message)

    def test_declining_human_confirmation_never_invokes_callback(self):
        from scripts.scientific_workspace_actions import (
            ApprovedSimulationAction,
            request_approved_simulation,
        )

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp))
            calls = []
            action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Reviewed model callback",
                callback=lambda loaded, selected: calls.append((loaded, selected)),
            )
            prompts = []
            ticket = request_approved_simulation(
                action, workspace, component,
                confirm=lambda prompt: prompts.append(prompt) or False,
            )

        self.assertIsNone(ticket)
        self.assertEqual(calls, [])
        self.assertIn("proceso", prompts[0].lower())
        self.assertIn("no valida", prompts[0].lower())

    def test_approved_callback_receives_verified_workspace_and_renders_solution(self):
        from scripts.scientific_workspace_actions import (
            ApprovedSimulationAction,
            request_approved_simulation,
            run_approved_simulation,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace, component = _workspace(root)
            before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in root.iterdir() if path.is_file()}
            calls = []

            def callback(loaded, selected):
                calls.append((loaded, selected))
                return solve_rk4(
                    OdeProblem(
                        rhs=lambda _time, _state, _parameters: (0.0, 1.0),
                        t_span=(0.0, 2.0),
                        initial_state=(90.0, 10.0),
                        state_names=("S", "I"),
                    ),
                    1.0,
                )

            action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Reviewed model callback",
                callback=callback,
            )
            ticket = request_approved_simulation(
                action, workspace, component, confirm=lambda _prompt: True
            )
            self.assertEqual(calls, [])
            result = run_approved_simulation(ticket)
            after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in root.iterdir() if path.is_file()}

        self.assertEqual(calls, [(workspace, component)])
        self.assertEqual(result.component_type, "simulation_plot")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.content["series_names"], ("I",))
        self.assertEqual(result.content["times"], (0.0, 1.0, 2.0))
        self.assertEqual(before, after)

    def test_action_is_bound_to_exact_workspace_and_simulation_component(self):
        from scripts.scientific_workspace_actions import (
            ApprovedSimulationAction,
            request_approved_simulation,
        )

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp))
            calls = []
            action = ApprovedSimulationAction(
                workspace_id="another-project",
                label="Reviewed callback",
                callback=lambda *_args: calls.append(True),
            )
            with self.assertRaisesRegex(ValueError, "workspace_id"):
                request_approved_simulation(
                    action, workspace, component, confirm=lambda _prompt: True
                )
            matching_action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Reviewed callback",
                callback=lambda *_args: calls.append(True),
            )
            with self.assertRaisesRegex(ValueError, "simulation_plot"):
                request_approved_simulation(
                    matching_action,
                    workspace,
                    replace(component, component_type="equation_view"),
                    confirm=lambda _prompt: True,
                )

        self.assertEqual(calls, [])

    def test_approval_ticket_is_one_shot(self):
        from scripts.scientific_workspace_actions import (
            ApprovedSimulationAction,
            request_approved_simulation,
            run_approved_simulation,
        )

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp))
            action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Reviewed callback",
                callback=lambda _loaded, _component: solve_rk4(
                    OdeProblem(
                        rhs=lambda _time, _state, _parameters: (0.0, 0.0),
                        t_span=(0.0, 1.0), initial_state=(90.0, 10.0),
                        state_names=("S", "I"),
                    ),
                    1.0,
                ),
            )
            ticket = request_approved_simulation(
                action, workspace, component, confirm=lambda _prompt: True
            )
            run_approved_simulation(ticket)
            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                run_approved_simulation(ticket)

    def test_invalid_callback_result_is_not_rendered(self):
        from scripts.scientific_workspace_actions import (
            ApprovedSimulationAction,
            request_approved_simulation,
            run_approved_simulation,
        )

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp))
            action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Reviewed callback",
                callback=lambda _loaded, _component: {"status": "looks good"},
            )
            ticket = request_approved_simulation(
                action, workspace, component, confirm=lambda _prompt: True
            )
            with self.assertRaisesRegex(ValueError, "OdeSolution"):
                run_approved_simulation(ticket)

    def test_oversized_solution_is_rejected_before_serialization(self):
        from scripts.scientific_workspace_view import (
            MAX_SIMULATION_ROWS,
            build_simulation_result_view,
        )

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp))
            oversized = OdeSolution(
                times=(), states=(), state_names=("I",), parameters={}, method="rk4",
                requested_max_step=1.0, step_size=1.0,
                step_count=MAX_SIMULATION_ROWS,
            )
            with patch.object(OdeSolution, "to_dict", side_effect=AssertionError("must not copy")):
                with self.assertRaisesRegex(ValueError, "row UI limit"):
                    build_simulation_result_view(
                        component, oversized, series=("I",), action_label="approved"
                    )

    def test_malformed_dimensions_and_parameter_count_are_rejected_before_copy(self):
        from scripts.scientific_workspace_view import build_simulation_result_view

        class HugeLength(tuple):
            def __len__(self):
                return 100_001

        with tempfile.TemporaryDirectory() as temp:
            _workspace_obj, component = _workspace(Path(temp))
            mismatched = OdeSolution(
                times=HugeLength(), states=(), state_names=("I",), parameters={},
                method="rk4", requested_max_step=1.0, step_size=1.0, step_count=1,
            )
            too_many_parameters = OdeSolution(
                times=(0.0, 1.0), states=((1.0,), (2.0,)), state_names=("I",),
                parameters={f"p{index}": float(index) for index in range(101)},
                method="rk4", requested_max_step=1.0, step_size=1.0, step_count=1,
            )
            too_many_states = OdeSolution(
                times=(0.0, 1.0),
                states=(tuple(0.0 for _ in range(101)), tuple(1.0 for _ in range(101))),
                state_names=tuple(f"S{index}" for index in range(101)),
                parameters={}, method="rk4", requested_max_step=1.0, step_size=1.0,
                step_count=1,
            )
            with patch.object(OdeSolution, "to_dict", side_effect=AssertionError("must not copy")):
                with self.assertRaisesRegex(ValueError, "time grid before serialization"):
                    build_simulation_result_view(
                        component, mismatched, series=("I",), action_label="approved"
                    )
                with self.assertRaisesRegex(ValueError, "parameter UI limit"):
                    build_simulation_result_view(
                        component, too_many_parameters, series=("I",), action_label="approved"
                    )
                with self.assertRaisesRegex(ValueError, "state UI limit"):
                    build_simulation_result_view(
                        component, too_many_states, series=("I",), action_label="approved"
                    )


if __name__ == "__main__":
    unittest.main()
