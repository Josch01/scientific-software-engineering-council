import importlib
import importlib.util
import json
import math
import unittest


def load_scientific_core(test_case):
    spec = importlib.util.find_spec("scripts.scientific_core")
    test_case.assertIsNotNone(
        spec, "scripts.scientific_core must provide the reusable ODE API"
    )
    return importlib.import_module("scripts.scientific_core")


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

    def test_solver_enforces_step_count_budget(self):
        with self.assertRaisesRegex(ValueError, "max_steps"):
            self.core.solve_rk4(self.decay_problem(), max_step=0.001, max_steps=10)


if __name__ == "__main__":
    unittest.main()
