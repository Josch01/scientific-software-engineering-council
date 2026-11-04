import importlib
import importlib.util
import json
import math
from collections.abc import Sequence
from pathlib import Path
import subprocess
import sys
import unittest


def load_scientific_core(test_case):
    spec = importlib.util.find_spec("scripts.scientific_core")
    test_case.assertIsNotNone(
        spec, "scripts.scientific_core must provide the reusable ODE API"
    )
    return importlib.import_module("scripts.scientific_core")


def sir_contract_payload():
    return {
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
        "t_span": [0.0, 2.0],
        "units": {"time": "day", "population": "person", "rate": "1/day"},
        "integrator": {
            "method": "RK4_FIXED_STEP",
            "max_step": 0.1,
            "max_steps": 100,
        },
    }


class ODERK4Tests(unittest.TestCase):
    def setUp(self):
        self.core = load_scientific_core(self)

    def decay_problem(self):
        return self.core.OdeProblem(
            rhs=lambda _time, state, parameters: (
                -parameters["rate"] * state[0],
            ),
            t_span=(0.0, 1.0),
            initial_state=(1.0,),
            parameters={"rate": 1.0},
            state_names=("amount",),
        )

    def test_rk4_matches_analytic_decay_and_reaches_exact_endpoint(self):
        solution = self.core.solve_rk4(self.decay_problem(), max_step=0.02)

        self.assertEqual(solution.times[0], 0.0)
        self.assertEqual(solution.times[-1], 1.0)
        self.assertEqual(solution.state_names, ("amount",))
        self.assertEqual(len(solution.times), len(solution.states))
        self.assertEqual(solution.method, "RK4_FIXED_STEP")
        self.assertAlmostEqual(solution.states[-1][0], math.exp(-1.0), delta=1e-8)

    def test_solution_reports_uniform_substeps_when_max_step_does_not_divide_span(self):
        solution = self.core.solve_rk4(self.decay_problem(), max_step=0.3)

        self.assertEqual(solution.step_count, 4)
        self.assertEqual(solution.step_size, 0.25)
        self.assertEqual(solution.times, (0.0, 0.25, 0.5, 0.75, 1.0))

    def test_halving_step_exhibits_fourth_order_global_convergence(self):
        problem = self.decay_problem()
        coarse = self.core.solve_rk4(problem, max_step=0.2)
        fine = self.core.solve_rk4(problem, max_step=0.1)
        exact = math.exp(-1.0)
        coarse_error = abs(coarse.states[-1][0] - exact)
        fine_error = abs(fine.states[-1][0] - exact)

        self.assertGreater(coarse_error / fine_error, 14.0)
        self.assertLess(coarse_error / fine_error, 18.0)

    def test_solution_serializes_a_finite_structured_result(self):
        solution = self.core.solve_rk4(self.decay_problem(), max_step=0.1)

        payload = solution.to_dict()
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["method"], "RK4_FIXED_STEP")
        self.assertEqual(payload["state_names"], ["amount"])
        self.assertEqual(payload["parameters"], {"rate": 1.0})
        self.assertEqual(payload["times"][-1], 1.0)
        json.dumps(payload, allow_nan=False)


    def test_problem_rejects_empty_state_and_nonforward_interval(self):
        core = self.core

        with self.assertRaises(ValueError):
            core.OdeProblem(rhs=lambda *_: (), t_span=(0.0, 1.0), initial_state=())
        with self.assertRaises(ValueError):
            core.OdeProblem(
                rhs=lambda *_: (0.0,), t_span=(1.0, 1.0), initial_state=(0.0,)
            )
        with self.assertRaises(ValueError):
            core.OdeProblem(
                rhs=lambda *_: (0.0,), t_span=(2.0, 1.0), initial_state=(0.0,)
            )

    def test_problem_rejects_text_instead_of_numeric_sequences(self):
        with self.assertRaises(ValueError):
            self.core.OdeProblem(
                rhs=lambda *_: (0.0,), t_span=(0.0, 1.0), initial_state="1"
            )

    def test_problem_rejects_mismatched_state_names_and_invalid_parameters(self):
        core = self.core
        rhs = lambda *_: (0.0,)

        with self.assertRaises(ValueError):
            core.OdeProblem(
                rhs=rhs,
                t_span=(0.0, 1.0),
                initial_state=(0.0,),
                state_names=("first", "second"),
            )
        with self.assertRaises(ValueError):
            core.OdeProblem(
                rhs=rhs,
                t_span=(0.0, 1.0),
                initial_state=(0.0,),
                parameters={"rate": math.inf},
            )
        with self.assertRaises(ValueError):
            core.OdeProblem(
                rhs=rhs,
                t_span=(0.0, 1.0),
                initial_state=(0.0,),
                parameters={"rate": "1.0"},
            )

    def test_solver_rejects_nonpositive_or_nonfinite_max_step(self):
        problem = self.decay_problem()
        for step in (0.0, -0.1, math.inf, math.nan):
            with self.subTest(step=step):
                with self.assertRaises(ValueError):
                    self.core.solve_rk4(problem, max_step=step)

    def test_solver_rejects_derivative_with_wrong_dimension(self):
        problem = self.core.OdeProblem(
            rhs=lambda *_: (1.0,),
            t_span=(0.0, 1.0),
            initial_state=(0.0, 0.0),
        )

        with self.assertRaisesRegex(ValueError, "dimension"):
            self.core.solve_rk4(problem, max_step=0.1)

    def test_solver_rejects_nonfinite_derivative_values(self):
        problem = self.core.OdeProblem(
            rhs=lambda *_: (math.nan,),
            t_span=(0.0, 1.0),
            initial_state=(0.0,),
        )

        with self.assertRaisesRegex(ValueError, "finite"):
            self.core.solve_rk4(problem, max_step=0.1)

    def test_solver_avoids_overflow_in_weighted_average_of_finite_derivatives(self):
        problem = self.core.OdeProblem(
            rhs=lambda *_: (1.0e308,),
            t_span=(0.0, 1.0e-308),
            initial_state=(0.0,),
        )

        try:
            solution = self.core.solve_rk4(problem, max_step=1.0e-308)
        except ValueError as exc:
            self.fail(f"finite weighted derivative should remain representable: {exc}")

        self.assertAlmostEqual(solution.states[-1][0], 1.0, delta=1e-15)

    def test_solver_preserves_subnormal_derivative_with_large_step(self):
        problem = self.core.OdeProblem(
            rhs=lambda *_: (5e-324,),
            t_span=(0.0, 1e308),
            initial_state=(0.0,),
        )

        solution = self.core.solve_rk4(problem, max_step=1e308)

        self.assertAlmostEqual(solution.states[-1][0], 5e-324 * 1e308, delta=1e-30)

    def test_problem_rejects_nonsequence_state_names_with_value_error(self):
        try:
            self.core.OdeProblem(
                rhs=lambda *_: (0.0,),
                t_span=(0.0, 1.0),
                initial_state=(0.0,),
                state_names=42,
            )
        except Exception as exc:
            self.assertIsInstance(exc, ValueError)
            self.assertIn("state_names", str(exc))
        else:
            self.fail("non-sequence state_names should be rejected")

    def test_solver_enforces_step_count_budget(self):
        with self.assertRaisesRegex(ValueError, "max_steps"):
            self.core.solve_rk4(self.decay_problem(), max_step=0.001, max_steps=10)


class SIRDeclarativeContractTests(unittest.TestCase):
    def setUp(self):
        self.core = load_scientific_core(self)

    def test_contract_computes_the_fixed_frequency_dependent_sir_rhs(self):
        contract_type = getattr(self.core, "SirModelDefinition", None)
        self.assertIsNotNone(contract_type, "scientific_core must expose SirModelDefinition")
        contract = contract_type.from_dict(sir_contract_payload())

        self.assertEqual(contract.state_names, ("S", "I", "R"))
        for actual, expected in zip(
            contract.rhs(0.0, (90.0, 10.0, 0.0), {}), (-2.7, 1.7, 1.0)
        ):
            self.assertAlmostEqual(actual, expected)

    def test_piecewise_linear_rates_interpolate_declared_knots(self):
        payload = sir_contract_payload()
        payload["parameters"]["beta"] = {
            "kind": "piecewise_linear",
            "points": [[0.0, 0.2], [1.0, 0.4], [2.0, 0.1]],
        }

        contract = self.core.SirModelDefinition.from_dict(payload)

        self.assertAlmostEqual(contract.parameters["beta"].evaluate(0.5), 0.3)
        self.assertAlmostEqual(contract.parameters["beta"].evaluate(1.5), 0.25)

    def test_parameterized_ode_problem_reuses_sir_equations_and_honors_rate_overrides(self):
        contract = self.core.SirModelDefinition.from_dict(sir_contract_payload())
        to_problem = getattr(contract, "to_ode_problem", None)
        self.assertIsNotNone(to_problem, "SIR v1 must expose a parameterized OdeProblem")

        problem = to_problem()
        reference = self.core.solve_sir_model(contract)
        actual = self.core.solve_rk4(problem, max_step=contract.max_step)

        self.assertEqual(problem.parameters, {"beta": 0.3, "gamma": 0.1})
        self.assertEqual(actual.times, reference.times)
        for actual_state, expected_state in zip(actual.states, reference.states):
            for actual_value, expected_value in zip(actual_state, expected_state):
                self.assertAlmostEqual(actual_value, expected_value, places=13)

        higher_beta = self.core.OdeProblem(
            rhs=problem.rhs, t_span=problem.t_span, initial_state=problem.initial_state,
            parameters={"beta": 0.5, "gamma": 0.1}, state_names=problem.state_names,
        )
        changed = self.core.solve_rk4(higher_beta, max_step=contract.max_step)
        self.assertGreater(changed.states[-1][1], actual.states[-1][1])

        negative_beta = self.core.OdeProblem(
            rhs=problem.rhs, t_span=problem.t_span, initial_state=problem.initial_state,
            parameters={"beta": -0.1, "gamma": 0.1}, state_names=problem.state_names,
        )
        with self.assertRaisesRegex(ValueError, "rates must be nonnegative"):
            self.core.solve_rk4(negative_beta, max_step=contract.max_step)

    def test_parameterized_ode_problem_rejects_time_varying_rate_profiles(self):
        payload = sir_contract_payload()
        payload["parameters"]["beta"] = {
            "kind": "piecewise_linear", "points": [[0.0, 0.3], [2.0, 0.2]],
        }
        contract = self.core.SirModelDefinition.from_dict(payload)

        with self.assertRaisesRegex(ValueError, "constant beta and gamma"):
            contract.to_ode_problem()

    def test_contract_rejects_unknown_equation_text_and_profile_functions(self):
        payload = sir_contract_payload()
        payload["equations"]["dS/dt"] = "__import__('os').system('whoami')"
        with self.assertRaisesRegex(ValueError, "equations must exactly match"):
            self.core.SirModelDefinition.from_dict(payload)

        payload = sir_contract_payload()
        payload["parameters"]["beta"] = {
            "kind": "python_expression", "expression": "__import__('os')"
        }
        with self.assertRaisesRegex(ValueError, "kind must be"):
            self.core.SirModelDefinition.from_dict(payload)

    def test_contract_rejects_wrong_state_dimensions_negative_values_and_units(self):
        bad_payloads = []
        payload = sir_contract_payload()
        payload["states"] = ["S", "I"]
        bad_payloads.append((payload, "states must be exactly"))

        payload = sir_contract_payload()
        payload["initial_conditions"]["I"] = -1.0
        bad_payloads.append((payload, "initial conditions must be nonnegative"))

        payload = sir_contract_payload()
        payload["parameters"]["gamma"]["value"] = -0.1
        bad_payloads.append((payload, "coefficient values must be nonnegative"))

        payload = sir_contract_payload()
        payload["units"]["rate"] = "1/hour"
        bad_payloads.append((payload, "units.rate must equal"))

        for bad_payload, message in bad_payloads:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.core.SirModelDefinition.from_dict(bad_payload)

    def test_piecewise_linear_profile_requires_ordered_knots_covering_interval(self):
        payload = sir_contract_payload()
        payload["parameters"]["beta"] = {
            "kind": "piecewise_linear",
            "points": [[0.0, 0.2], [1.5, 0.4], [1.0, 0.3], [2.0, 0.1]],
        }
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            self.core.SirModelDefinition.from_dict(payload)

        payload["parameters"]["beta"] = {
            "kind": "piecewise_linear", "points": [[0.0, 0.2], [1.0, 0.4]]
        }
        with self.assertRaisesRegex(ValueError, "cover both t_span endpoints"):
            self.core.SirModelDefinition.from_dict(payload)

    def test_piecewise_linear_knots_must_align_with_existing_uniform_rk4_grid(self):
        payload = sir_contract_payload()
        payload["t_span"] = [0.0, 1.0]
        payload["integrator"] = {
            "method": "RK4_FIXED_STEP", "max_step": 0.3, "max_steps": 4
        }
        payload["parameters"]["beta"] = {
            "kind": "piecewise_linear",
            "points": [[0.0, 0.2], [0.3, 0.4], [1.0, 0.1]],
        }

        with self.assertRaisesRegex(ValueError, "align with the RK4 time grid"):
            self.core.SirModelDefinition.from_dict(payload)

    def test_contract_rejects_integrator_budget_before_solving(self):
        payload = sir_contract_payload()
        payload["integrator"]["max_step"] = 0.001
        payload["integrator"]["max_steps"] = 10

        with self.assertRaisesRegex(ValueError, "exceeds the declared step budget"):
            self.core.SirModelDefinition.from_dict(payload)

    def test_contract_round_trip_preserves_declared_profile_and_units(self):
        payload = sir_contract_payload()
        payload["parameters"]["gamma"] = {
            "kind": "piecewise_linear", "points": [[0.0, 0.1], [2.0, 0.2]]
        }

        contract = self.core.SirModelDefinition.from_dict(payload)

        self.assertEqual(contract.to_dict(), payload)

    def test_from_json_rejects_duplicate_keys_nonstandard_numbers_and_oversize(self):
        parser = getattr(self.core.SirModelDefinition, "from_json", None)
        self.assertIsNotNone(parser, "SirModelDefinition must parse bounded strict JSON")
        encoded = json.dumps(sir_contract_payload(), separators=(",", ":"))
        duplicate_key = encoded.replace('"schema_version":1,', '"schema_version":1,"schema_version":1,', 1)
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            parser(duplicate_key)

        nonstandard_number = encoded.replace('"max_step":0.1', '"max_step":NaN', 1)
        with self.assertRaisesRegex(ValueError, "non-standard JSON constant"):
            parser(nonstandard_number)

        with self.assertRaisesRegex(ValueError, "exceeds the .*byte limit"):
            parser(b" " * (1_048_577))

    def test_from_dict_rejects_oversized_sequences_before_iterating_them(self):
        class LengthOnlySequence(Sequence):
            def __init__(self, length):
                self.length = length

            def __len__(self):
                return self.length

            def __getitem__(self, _index):
                raise AssertionError("oversized sequence must be rejected before iteration")

        payload = sir_contract_payload()
        payload["states"] = LengthOnlySequence(4)
        with self.assertRaisesRegex(ValueError, "states must be exactly"):
            self.core.SirModelDefinition.from_dict(payload)

        payload = sir_contract_payload()
        payload["parameters"]["beta"] = {
            "kind": "piecewise_linear", "points": LengthOnlySequence(129)
        }
        with self.assertRaisesRegex(ValueError, "2 to 128 entries"):
            self.core.SirModelDefinition.from_dict(payload)

    def test_solver_reuses_rk4_for_time_varying_recovery_and_preserves_population(self):
        payload = sir_contract_payload()
        payload["initial_conditions"] = {"S": 0.0, "I": 10.0, "R": 0.0}
        payload["parameters"]["beta"] = {"kind": "constant", "value": 0.0}
        payload["parameters"]["gamma"] = {
            "kind": "piecewise_linear", "points": [[0.0, 0.1], [0.1, 0.2]]
        }
        payload["t_span"] = [0.0, 0.1]
        payload["integrator"] = {
            "method": "RK4_FIXED_STEP", "max_step": 0.1, "max_steps": 1
        }
        contract = self.core.SirModelDefinition.from_dict(payload)
        solver = getattr(self.core, "solve_sir_model", None)
        self.assertIsNotNone(solver, "scientific_core must expose solve_sir_model")

        solution = solver(contract)

        self.assertEqual(solution.method, "RK4_FIXED_STEP")
        self.assertEqual(solution.step_count, 1)
        self.assertAlmostEqual(solution.states[-1][0], 0.0, places=12)
        self.assertAlmostEqual(solution.states[-1][1], 9.85111939375, places=12)
        self.assertAlmostEqual(solution.states[-1][2], 0.14888060625, places=12)
        self.assertAlmostEqual(sum(solution.states[-1]), 10.0, places=12)

    def test_solver_rejects_rk4_trajectory_with_negative_compartment(self):
        payload = sir_contract_payload()
        payload["initial_conditions"] = {"S": 9.0, "I": 1.0, "R": 0.0}
        payload["parameters"]["beta"] = {"kind": "constant", "value": 100.0}
        payload["parameters"]["gamma"] = {"kind": "constant", "value": 0.0}
        payload["t_span"] = [0.0, 1.0]
        payload["integrator"] = {
            "method": "RK4_FIXED_STEP", "max_step": 1.0, "max_steps": 1
        }
        contract = self.core.SirModelDefinition.from_dict(payload)

        with self.assertRaisesRegex(ValueError, "negative compartment"):
            self.core.solve_sir_model(contract)


class SIRDemoTests(unittest.TestCase):
    def test_synthetic_demo_runs_from_outside_repo_and_marks_science_unassessed(self):
        repository = Path(__file__).resolve().parents[1]
        script = repository / "examples" / "run_sir_model_demo.py"
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "SIMULATED_FIXTURE")
        self.assertEqual(report["scientific_validity"], "NOT_ASSESSED")
        self.assertEqual(report["equation_set"], "sir_frequency_dependent_v1")
        self.assertEqual(report["method"], "RK4_FIXED_STEP")
        self.assertEqual(report["step_count"], 100)
        self.assertEqual(len(report["model_sha256"]), 64)
        self.assertEqual(report["model_sha256"], report["model_sha256"].lower())
        self.assertEqual(set(report["final_state"]), {"S", "I", "R"})
        self.assertAlmostEqual(report["final_state"]["S"], 934.418041713437, delta=1e-10)
        self.assertAlmostEqual(report["final_state"]["I"], 41.39894426760634, delta=1e-10)
        self.assertAlmostEqual(report["final_state"]["R"], 24.183014018957, delta=1e-10)
        self.assertAlmostEqual(sum(report["final_state"].values()), 1_000.0, delta=1e-8)

if __name__ == "__main__":
    unittest.main()
