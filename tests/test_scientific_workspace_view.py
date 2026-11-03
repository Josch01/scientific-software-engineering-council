import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.scientific_workspace_loader import load_scientific_workspace
from scripts.scientific_core import OdeProblem, solve_rk4


def _load_workspace(resources, components):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manifest_resources = []
        for resource_id, kind, relative_path, content in resources:
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            manifest_resources.append(
                {
                    "id": resource_id,
                    "kind": kind,
                    "path": relative_path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        manifest = {
            "schema_version": 1,
            "workspace_id": "test-workspace",
            "title": "Test workspace",
            "resources": manifest_resources,
            "sections": [
                {"id": "main", "title": "Main", "components": components}
            ],
        }
        (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        return load_scientific_workspace(root, "workspace.json")


def _component(component_id, component_type, resource_id, config=None):
    return {
        "id": component_id,
        "type": component_type,
        "title": component_id.replace("-", " ").title(),
        "resource_refs": [resource_id],
        "config": config or {},
    }


class ScientificWorkspaceViewTests(unittest.TestCase):
    def _view(self):
        spec = importlib.util.find_spec("scripts.scientific_workspace_view")
        self.assertIsNotNone(spec, "scientific workspace view layer has not been implemented")
        from scripts import scientific_workspace_view

        return scientific_workspace_view

    def test_manifest_configures_sections_and_components(self):
        view = self._view()
        workspace = _load_workspace(
            [("model", "model_spec", "model.json", b'{"equations":[]}')],
            [_component("equations", "equation_view", "model")],
        )

        result = view.build_workspace_view_model(workspace)

        self.assertEqual(result.title, "Test workspace")
        self.assertEqual(result.sections[0].title, "Main")
        self.assertEqual(result.sections[0].components[0].component_type, "equation_view")
        self.assertEqual(result.sections[0].components[0].status, "ok")
        self.assertEqual(result.sections[0].components[0].content["equations"], ())

    def test_sir_contract_projects_to_structured_equation_and_parameter_views(self):
        view = self._view()
        from scripts.scientific_workspace_view import SirEquationView, SirParameterView

        model_path = Path(__file__).resolve().parents[1] / "examples" / "sir_model_demo.json"
        payload = json.loads(model_path.read_text(encoding="utf-8"))
        workspace = _load_workspace(
            [("model", "model_spec", "model.json", json.dumps(payload).encode())],
            [
                _component("equations", "equation_view", "model"),
                _component("parameters", "parameter_table", "model"),
            ],
        )

        equation, parameters = view.build_workspace_view_model(workspace).sections[0].components

        self.assertEqual(equation.status, "ok")
        self.assertIsInstance(equation.content, SirEquationView)
        self.assertEqual(equation.content.equation_set, "sir_frequency_dependent_v1")
        self.assertEqual(equation.content.states, ("S", "I", "R"))
        self.assertIn("beta(t) * S * I / N", dict(equation.content.equations)["dI/dt"])
        self.assertEqual(equation.content.population_unit, "person")
        self.assertEqual(equation.content.rate_unit, "1/day")
        self.assertEqual(parameters.status, "ok")
        self.assertIsInstance(parameters.content, SirParameterView)
        self.assertEqual(
            parameters.content.initial_conditions,
            (("S", 990.0), ("I", 10.0), ("R", 0.0)),
        )
        self.assertEqual(parameters.content.time_span, (0.0, 10.0))
        profiles = {profile.name: profile for profile in parameters.content.profiles}
        self.assertEqual(profiles["beta"].kind, "piecewise_linear")
        self.assertEqual(len(profiles["beta"].points), 3)
        self.assertEqual(profiles["beta"].unit, "1/day")
        self.assertEqual(profiles["gamma"].kind, "constant")
        self.assertEqual(parameters.content.integrator_method, "RK4_FIXED_STEP")

    def test_invalid_sir_contract_is_a_component_error_not_raw_formula_text(self):
        view = self._view()
        model_path = Path(__file__).resolve().parents[1] / "examples" / "sir_model_demo.json"
        payload = json.loads(model_path.read_text(encoding="utf-8"))
        payload["equations"]["dS/dt"] = "__import__('os').system('whoami')"
        workspace = _load_workspace(
            [("model", "model_spec", "model.json", json.dumps(payload).encode())],
            [_component("equations", "equation_view", "model")],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.status, "error")
        self.assertIn("equations must exactly match", component.message)

    def test_source_artifact_is_bounded_plain_text(self):
        view = self._view()
        source = b'raise RuntimeError("this content must remain inert")\n'
        workspace = _load_workspace(
            [("source", "source_code", "model.py", source)],
            [_component("code", "code_view", "source", {"language": "python"})],
        )

        result = view.build_workspace_view_model(workspace)
        rendered = result.sections[0].components[0]

        self.assertEqual(rendered.status, "ok")
        self.assertEqual(rendered.content, source.decode("utf-8"))
        self.assertIsInstance(rendered.content, str)

    def test_source_text_control_characters_are_sanitized_for_widgets(self):
        view = self._view()
        workspace = _load_workspace(
            [("source", "source_code", "model.py", b"x\x00y\n")],
            [_component("code", "code_view", "source", {"language": "python"})],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.content, "x\uFFFDy\n")

    def test_simulation_plot_selects_configured_series_from_core_result(self):
        view = self._view()
        simulation = {
            "schema_version": 1,
            "method": "rk4",
            "times": [0.0, 1.0, 2.0],
            "state_names": ["S", "I"],
            "values": [[99.0, 1.0], [98.0, 2.0], [96.0, 4.0]],
            "parameters": {"beta": 0.1},
            "requested_max_step": 1.0,
            "actual_step_size": 1.0,
            "step_count": 2,
        }
        workspace = _load_workspace(
            [("sim", "simulation_result", "sim.json", json.dumps(simulation).encode())],
            [_component("plot", "simulation_plot", "sim", {"x_axis": "time", "series": ["I"]})],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.status, "ok")
        self.assertEqual(component.content["times"], (0.0, 1.0, 2.0))
        self.assertEqual(component.content["series_names"], ("I",))
        self.assertEqual(component.content["series_indices"], (1,))
        self.assertEqual(tuple(row[1] for row in component.content["values"]), (1.0, 2.0, 4.0))

    def test_actual_scientific_core_solution_matches_the_view_contract(self):
        view = self._view()
        solution = solve_rk4(
            OdeProblem(
                rhs=lambda _time, _state, _parameters: (0.0,),
                t_span=(0.0, 1.0),
                initial_state=(2.0,),
                state_names=("constant",),
            ),
            0.3,
        )
        workspace = _load_workspace(
            [
                (
                    "sim",
                    "simulation_result",
                    "sim.json",
                    json.dumps(solution.to_dict()).encode(),
                )
            ],
            [_component("plot", "simulation_plot", "sim", {"x_axis": "time", "series": ["constant"]})],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.status, "ok", component.message)
        self.assertEqual(component.content["row_count"], solution.step_count + 1)
        self.assertEqual(component.content["times"], solution.times)

    def test_malformed_simulation_is_a_component_error_not_workspace_crash(self):
        view = self._view()
        simulation = {
            "schema_version": 1,
            "method": "rk4",
            "times": [0.0, 1.0],
            "state_names": ["I"],
            "values": [[1.0]],
            "parameters": {},
            "requested_max_step": 1.0,
            "actual_step_size": 1.0,
            "step_count": 1,
        }
        workspace = _load_workspace(
            [("sim", "simulation_result", "sim.json", json.dumps(simulation).encode())],
            [_component("plot", "simulation_plot", "sim", {"x_axis": "time", "series": ["I"]})],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.status, "error")
        self.assertIn("values", component.message)

    def test_strict_json_errors_are_scoped_to_the_component(self):
        view = self._view()
        for content, expected in (
            (b'{"x":1,"x":2}', "duplicate"),
            (b'{"x":NaN}', "constant"),
            (b'{"x":' + b"[" * 33 + b"0" + b"]" * 33 + b"}", "nesting"),
        ):
            with self.subTest(content=content[:32]):
                workspace = _load_workspace(
                    [("model", "model_spec", "model.json", content)],
                    [_component("equations", "equation_view", "model")],
                )
                component = view.build_workspace_view_model(workspace).sections[0].components[0]
                self.assertEqual(component.status, "error")
                self.assertIn(expected, component.message)

    def test_configured_simulation_series_must_exist(self):
        view = self._view()
        simulation = {
            "schema_version": 1,
            "method": "rk4",
            "times": [0.0, 1.0],
            "state_names": ["I"],
            "values": [[1.0], [2.0]],
            "parameters": {},
            "requested_max_step": 1.0,
            "actual_step_size": 1.0,
            "step_count": 1,
        }
        workspace = _load_workspace(
            [("sim", "simulation_result", "sim.json", json.dumps(simulation).encode())],
            [_component("plot", "simulation_plot", "sim", {"x_axis": "time", "series": ["R"]})],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.status, "error")
        self.assertIn("absent", component.message)

    def test_simulation_step_metadata_must_match_solver_grid(self):
        view = self._view()
        for changes, expected in (
            ({"step_count": 0}, "positive"),
            ({"requested_max_step": -1.0}, "positive"),
            ({"actual_step_size": 0.0}, "positive"),
            ({"actual_step_size": 3.0, "requested_max_step": 3.0}, "time grid"),
            ({"requested_max_step": 0.5}, "requested maximum"),
            ({"step_count": 2}, "time grid"),
        ):
            with self.subTest(changes=changes):
                simulation = {
                    "schema_version": 1,
                    "method": "rk4",
                    "times": [0.0, 1.0],
                    "state_names": ["I"],
                    "values": [[1.0], [2.0]],
                    "parameters": {},
                    "requested_max_step": 1.0,
                    "actual_step_size": 1.0,
                    "step_count": 1,
                    **changes,
                }
                workspace = _load_workspace(
                    [("sim", "simulation_result", "sim.json", json.dumps(simulation).encode())],
                    [_component("plot", "simulation_plot", "sim", {"x_axis": "time", "series": ["I"]})],
                )
                component = view.build_workspace_view_model(workspace).sections[0].components[0]
                self.assertEqual(component.status, "error")
                self.assertIn(expected, component.message)

    def test_duplicate_generic_views_share_cached_payload(self):
        view = self._view()
        workspace = _load_workspace(
            [("model", "model_spec", "model.json", b'{"parameters":{"beta":0.2}}')],
            [
                _component("parameters-a", "parameter_table", "model"),
                _component("parameters-b", "parameter_table", "model"),
            ],
        )

        components = view.build_workspace_view_model(workspace).sections[0].components

        self.assertIs(components[0].content, components[1].content)

    def test_failed_json_resource_is_parsed_once_across_component_types(self):
        view = self._view()
        workspace = _load_workspace(
            [("model", "model_spec", "model.json", b'{"x":NaN}')],
            [
                _component("equations", "equation_view", "model"),
                _component("parameters", "parameter_table", "model"),
            ],
        )
        with patch.object(view, "_parse_json", wraps=view._parse_json) as parse_json:
            components = view.build_workspace_view_model(workspace).sections[0].components

        self.assertEqual(parse_json.call_count, 1)
        self.assertTrue(all(component.status == "error" for component in components))

    def test_ui_component_limit_is_explicit_and_counted(self):
        view = self._view()
        components = [
            _component(f"equation-{index}", "equation_view", "model")
            for index in range(view.MAX_UI_COMPONENTS + 1)
        ]
        workspace = _load_workspace(
            [("model", "model_spec", "model.json", b'{"equations":[]}')],
            components,
        )

        model = view.build_workspace_view_model(workspace)

        self.assertEqual(len(model.sections[0].components), view.MAX_UI_COMPONENTS)
        self.assertEqual(model.omitted_component_count, 1)
        self.assertEqual(model.sections[0].omitted_component_count, 1)

    def test_total_json_budget_is_enforced_across_unique_resources(self):
        view = self._view()
        workspace = _load_workspace(
            [
                ("model-a", "model_spec", "a.json", b"{}"),
                ("model-b", "model_spec", "b.json", b"{}"),
            ],
            [
                _component("equations-a", "equation_view", "model-a"),
                _component("equations-b", "equation_view", "model-b"),
            ],
        )
        with patch.object(view, "MAX_TOTAL_JSON_VIEW_BYTES", 3):
            components = view.build_workspace_view_model(workspace).sections[0].components

        self.assertEqual(components[0].status, "ok")
        self.assertEqual(components[1].status, "error")
        self.assertIn("budget", components[1].message)

    def test_generic_json_preview_is_bounded_but_payload_is_cached(self):
        view = self._view()
        content = json.dumps({"note": "x" * 40_000}).encode("utf-8")
        workspace = _load_workspace(
            [("model", "model_spec", "model.json", content)],
            [
                _component("equations-a", "equation_view", "model"),
                _component("equations-b", "equation_view", "model"),
            ],
        )

        components = view.build_workspace_view_model(workspace).sections[0].components

        self.assertTrue(components[0].truncated)
        self.assertLessEqual(len(components[0].preview_text), view.MAX_JSON_TEXT_PREVIEW_BYTES)
        self.assertEqual(len(components[0].content["note"]), 40_000)
        self.assertIs(components[0].content, components[1].content)
        self.assertIs(components[0].preview_text, components[1].preview_text)

    def test_observation_contract_exposes_units_and_provenance(self):
        view = self._view()
        observations = {
            "schema_version": 1,
            "time_unit": "day",
            "variables": [{"name": "infected", "unit": "people"}],
            "observations": [
                {"time": 0.0, "values": {"infected": 1.0}},
                {"time": 1.0, "values": {"infected": 2.0}},
            ],
            "provenance": {"source": "synthetic test fixture"},
        }
        workspace = _load_workspace(
            [("obs", "observations", "observations.json", json.dumps(observations).encode())],
            [_component("table", "observation_table", "obs")],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.status, "ok")
        self.assertEqual(component.content["time_unit"], "day")
        self.assertEqual(component.content["variable_units"]["infected"], "people")
        self.assertEqual(component.content["provenance"]["source"], "synthetic test fixture")

    def test_large_text_preview_is_truncated_and_marked(self):
        view = self._view()
        source = (b"x" * (view.MAX_TEXT_PREVIEW_BYTES + 1))
        workspace = _load_workspace(
            [("source", "source_code", "model.py", source)],
            [_component("code", "code_view", "source", {"language": "python"})],
        )

        component = view.build_workspace_view_model(workspace).sections[0].components[0]

        self.assertEqual(component.status, "ok")
        self.assertLessEqual(len(component.content), view.MAX_TEXT_PREVIEW_BYTES)
        self.assertTrue(component.truncated)


if __name__ == "__main__":
    unittest.main()
