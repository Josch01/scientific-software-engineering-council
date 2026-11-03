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


def _workspace(
    root: Path,
    *,
    model_content: bytes | None = None,
    additional_model_content: bytes | None = None,
    series: tuple[str, ...] = ("I",),
):
    model_bytes = model_content or b'{"equations":"SIR test fixture"}'
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
    resources = [
        {"id": "model", "kind": "model_spec", "path": "model.json",
         "sha256": hashlib.sha256(model_bytes).hexdigest()},
        {"id": "simulation", "kind": "simulation_result", "path": "simulation.json",
         "sha256": hashlib.sha256(result_bytes).hexdigest()},
    ]
    if additional_model_content is not None:
        (root / "model-additional.json").write_bytes(additional_model_content)
        resources.append({
            "id": "model-additional", "kind": "model_spec", "path": "model-additional.json",
            "sha256": hashlib.sha256(additional_model_content).hexdigest(),
        })
    manifest = {
        "schema_version": 1,
        "workspace_id": "approved-action-test",
        "title": "Approved action test",
        "resources": resources,
        "sections": [{
            "id": "results", "title": "Results", "components": [{
                "id": "trajectory", "type": "simulation_plot", "title": "Trajectory",
                "resource_refs": ["simulation"],
                "config": {"x_axis": "time", "series": list(series)},
            }],
        }],
    }
    (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
    loaded = load_scientific_workspace(root, "workspace.json")
    component = build_workspace_view_model(loaded).sections[0].components[0]
    return loaded, component


def _sir_model_bytes() -> bytes:
    model = {
        "schema_version": 1,
        "model_type": "sir",
        "equation_set": "sir_frequency_dependent_v1",
        "equations": {
            "dS/dt": "-beta(t) * S * I / N",
            "dI/dt": "beta(t) * S * I / N - gamma(t) * I",
            "dR/dt": "gamma(t) * I",
        },
        "states": ["S", "I", "R"],
        "initial_conditions": {"S": 90.0, "I": 10.0, "R": 0.0},
        "parameters": {
            "beta": {"kind": "constant", "value": 0.3},
            "gamma": {"kind": "constant", "value": 0.1},
        },
        "t_span": [0.0, 1.0],
        "units": {"time": "day", "population": "person", "rate": "1/day"},
        "integrator": {
            "method": "RK4_FIXED_STEP", "max_step": 0.1, "max_steps": 10
        },
    }
    return json.dumps(model).encode("utf-8")


class ApprovedSimulationActionTests(unittest.TestCase):
    def test_builtin_sir_action_runs_only_the_verified_model_spec(self):
        from scripts import scientific_workspace_actions as actions_api
        from scripts.scientific_workspace_actions import (
            request_approved_simulation,
            run_approved_simulation,
        )
        build_actions = getattr(actions_api, "sir_simulation_actions_for_workspace", None)
        self.assertIsNotNone(build_actions, "SSEC must bind declarative SIR models to approved actions")

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(
                Path(temp), model_content=_sir_model_bytes()
            )
            actions = build_actions(workspace)
            action = actions[component.component_id]
            model_sha256 = next(
                resource.sha256 for resource in workspace.resources
                if resource.kind == "model_spec"
            )
            ticket = request_approved_simulation(
                action, workspace, component, confirm=lambda _prompt: True
            )
            result = run_approved_simulation(ticket)

        self.assertIn(model_sha256, action.label)
        self.assertEqual(result.content["series_names"], ("I",))
        self.assertGreater(result.content["values"][-1][1], 10.0)

    def test_builtin_sir_action_refuses_ambiguous_model_specs(self):
        from scripts.scientific_workspace_actions import sir_simulation_actions_for_workspace

        with tempfile.TemporaryDirectory() as temp:
            workspace, _component = _workspace(
                Path(temp),
                model_content=_sir_model_bytes(),
                additional_model_content=_sir_model_bytes(),
            )

            with self.assertRaisesRegex(ValueError, "exactly one model_spec"):
                sir_simulation_actions_for_workspace(workspace)

    def test_builtin_sir_action_rejects_plot_series_outside_contract_states(self):
        from scripts.scientific_workspace_actions import sir_simulation_actions_for_workspace

        with tempfile.TemporaryDirectory() as temp:
            workspace, _component = _workspace(
                Path(temp), model_content=_sir_model_bytes(), series=("X",)
            )

            with self.assertRaisesRegex(ValueError, "outside the SIR model"):
                sir_simulation_actions_for_workspace(workspace)

    def test_builtin_sir_action_refuses_same_workspace_id_with_changed_model_digest(self):
        from scripts.scientific_workspace_actions import (
            request_approved_simulation,
            run_approved_simulation,
            sir_simulation_actions_for_workspace,
        )

        changed_model = json.loads(_sir_model_bytes())
        changed_model["parameters"]["beta"]["value"] = 0.25
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            original, component = _workspace(Path(first_temp), model_content=_sir_model_bytes())
            changed, changed_component = _workspace(
                Path(second_temp), model_content=json.dumps(changed_model).encode("utf-8")
            )
            action = sir_simulation_actions_for_workspace(original)[component.component_id]
            ticket = request_approved_simulation(
                action, changed, changed_component, confirm=lambda _prompt: True
            )

            with self.assertRaisesRegex(ValueError, "digest changed"):
                run_approved_simulation(ticket)

    def test_workspace_window_actions_include_builtin_sir_and_host_override(self):
        from scripts.scientific_workspace_actions import ApprovedSimulationAction
        from scripts import scientific_workspace_app as app
        prepare_actions = getattr(app, "_simulation_actions_for_workspace", None)
        self.assertIsNotNone(prepare_actions, "workspace display must prepare SIR actions")

        with tempfile.TemporaryDirectory() as temp:
            workspace, component = _workspace(Path(temp), model_content=_sir_model_bytes())
            builtin_actions, error = prepare_actions(workspace, {})
            host_action = ApprovedSimulationAction(
                workspace_id=workspace.summary.workspace_id,
                label="Host approved",
                callback=lambda _loaded, _view: None,
            )
            effective_actions, override_error = prepare_actions(
                workspace, {component.component_id: host_action}
            )

        self.assertIsNone(error)
        self.assertIn(component.component_id, builtin_actions)
        self.assertIsNone(override_error)
        self.assertIs(effective_actions[component.component_id], host_action)

    def test_workspace_window_exposes_invalid_sir_contract_error_and_no_action(self):
        from scripts import scientific_workspace_app as app

        with tempfile.TemporaryDirectory() as temp:
            workspace, _component = _workspace(
                Path(temp), model_content=b'{"schema_version":1,"model_type":"sir"}'
            )
            actions, error = app._simulation_actions_for_workspace(workspace, {})

        self.assertEqual(actions, {})
        self.assertIn("missing or unknown fields", error)

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
