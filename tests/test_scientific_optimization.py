import json
import unittest
from unittest.mock import patch

from scripts import scientific_core


class LeastSquaresTests(unittest.TestCase):
    def test_recovers_an_overdetermined_linear_solution(self):
        def residuals(parameters):
            first = parameters["a"]
            second = parameters["b"]
            return (
                first + second - 5.0,
                2.0 * first - second - 1.0,
                3.0 * first + 2.0 * second - 12.0,
            )

        result = scientific_core.fit_least_squares(
            residuals,
            {"a": -1.0, "b": 0.0},
            {"a": (-10.0, 10.0), "b": (-10.0, 10.0)},
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertAlmostEqual(result.parameters["a"], 2.0, delta=1e-7)
        self.assertAlmostEqual(result.parameters["b"], 3.0, delta=1e-7)
        self.assertAlmostEqual(result.cost, 0.0, delta=1e-14)

    def test_active_bound_is_respected_and_reported_as_constrained_fit(self):
        observed = []

        def residuals(parameters):
            value = parameters["rate"]
            observed.append(value)
            return (value - 2.0,)

        result = scientific_core.fit_least_squares(
            residuals, {"rate": 0.5}, {"rate": (0.0, 1.0)}
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertEqual(result.parameters["rate"], 1.0)
        self.assertAlmostEqual(result.cost, 0.5, delta=1e-14)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in observed))

    def test_non_linear_residual_converges_from_initial_lower_bound(self):
        result = scientific_core.fit_least_squares(
            lambda parameters: (parameters["rate"] ** 2 - 4.0,),
            {"rate": 0.0},
            {"rate": (0.0, 5.0)},
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertAlmostEqual(result.parameters["rate"], 2.0, delta=1e-5)
        self.assertLess(result.cost, 1e-10)

    def test_parameter_fit_is_invariant_to_small_residual_scale(self):
        result = scientific_core.fit_least_squares(
            lambda parameters: (1e-6 * (parameters["rate"] - 0.7),),
            {"rate": 0.2},
            {"rate": (0.0, 1.0)},
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertAlmostEqual(result.parameters["rate"], 0.7, delta=1e-5)
        self.assertFalse(result.cost_underflowed)

    def test_parameter_scales_do_not_hide_a_small_jacobian_column(self):
        result = scientific_core.fit_least_squares(
            lambda parameters: (
                1e6 * (parameters["a"] - 0.5),
                parameters["b"] - 0.7,
            ),
            {"a": 0.5, "b": 0.2},
            {"a": (0.0, 1.0), "b": (0.0, 1.0)},
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertAlmostEqual(result.parameters["a"], 0.5, delta=1e-8)
        self.assertAlmostEqual(result.parameters["b"], 0.7, delta=1e-6)
        self.assertLess(result.cost, 1e-12)

    def test_initial_parameter_is_preserved_with_wide_symmetric_bounds(self):
        observed = []

        def residuals(parameters):
            observed.append(parameters["rate"])
            return (parameters["rate"] - 1.0,)

        result = scientific_core.fit_least_squares(
            residuals,
            {"rate": 1.0},
            {"rate": (-1e16, 1e16)},
        )

        self.assertEqual(observed[0], 1.0)
        self.assertEqual(result.parameters["rate"], 1.0)
        self.assertEqual(result.cost, 0.0)
        self.assertEqual(result.status, "CONVERGED")

    def test_wide_bounds_use_a_representable_finite_difference_for_large_residuals(self):
        target = 1e13
        result = scientific_core.fit_least_squares(
            lambda parameters: (parameters["rate"] - target,),
            {"rate": 1.0},
            {"rate": (-1e16, 1e16)},
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertLess(abs(result.residuals[0]) / target, 1e-8)
        self.assertLess(result.cost, 1e10)

    def test_subnormal_objective_cost_does_not_skip_parameter_updates(self):
        result = scientific_core.fit_least_squares(
            lambda parameters: (1e-200 * (parameters["rate"] - 0.7),),
            {"rate": 0.2},
            {"rate": (0.0, 1.0)},
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertAlmostEqual(result.parameters["rate"], 0.7, delta=1e-5)
        self.assertTrue(result.cost_underflowed)

    def test_optimizer_composes_with_rk4_for_synthetic_parameter_fit(self):
        def problem(rate):
            return scientific_core.OdeProblem(
                rhs=lambda _time, state, parameters: (
                    -parameters["rate"] * state[0],
                ),
                t_span=(0.0, 1.0),
                initial_state=(1.0,),
                parameters={"rate": rate},
                state_names=("amount",),
            )

        observation_indices = (2, 5, 10)
        observed_solution = scientific_core.solve_rk4(problem(0.8), max_step=0.1)
        observed = tuple(
            observed_solution.states[index][0] for index in observation_indices
        )

        def residuals(parameters):
            solution = scientific_core.solve_rk4(
                problem(parameters["rate"]), max_step=0.1
            )
            return tuple(
                solution.states[index][0] - value
                for index, value in zip(observation_indices, observed)
            )

        result = scientific_core.fit_least_squares(
            residuals, {"rate": 0.3}, {"rate": (0.0, 2.0)}
        )

        self.assertEqual(result.status, "CONVERGED")
        self.assertAlmostEqual(result.parameters["rate"], 0.8, delta=1e-5)
        self.assertEqual(len(result.residuals), len(observation_indices))

    def test_evaluation_budget_returns_best_point_without_false_convergence(self):
        calls = []

        def residuals(parameters):
            calls.append(parameters["rate"])
            return (parameters["rate"] - 2.0,)

        result = scientific_core.fit_least_squares(
            residuals,
            {"rate": 0.25},
            {"rate": (0.0, 1.0)},
            max_function_evaluations=1,
        )

        self.assertEqual(result.status, "MAX_FUNCTION_EVALUATIONS")
        self.assertEqual(result.parameters["rate"], 0.25)
        self.assertEqual(result.function_evaluations, 1)
        self.assertEqual(result.function_evaluations, len(calls))

    def test_fit_record_is_immutable_and_json_safe(self):
        def residuals(parameters):
            with self.assertRaises(TypeError):
                parameters["rate"] = 0.75
            return (parameters["rate"] - 0.5,)

        result = scientific_core.fit_least_squares(
            residuals,
            {"rate": 0.0},
            {"rate": (0.0, 1.0)},
        )

        self.assertEqual(result.status, "CONVERGED")
        with self.assertRaises(TypeError):
            result.parameters["rate"] = 0.75
        payload = result.to_dict()
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["method"], "BOUNDED_LEVENBERG_MARQUARDT")
        self.assertEqual(payload["status"], "CONVERGED")
        self.assertFalse(payload["cost_underflowed"])
        json.dumps(payload, allow_nan=False)

    def test_invalid_inputs_and_residual_callbacks_fail_explicitly(self):
        invalid_inputs = (
            ({}, {}, "non-empty"),
            ({"rate": 2.0}, {"rate": (0.0, 1.0)}, "within its bounds"),
            ({"rate": 0.5}, {"rate": (1.0, 1.0)}, "lower < upper"),
            ({"rate": 0.5}, {}, "exactly the initial parameter names"),
        )
        for initial, bounds, message in invalid_inputs:
            with self.subTest(initial=initial, bounds=bounds), self.assertRaisesRegex(
                ValueError, message
            ):
                scientific_core.fit_least_squares(lambda _parameters: (0.0,), initial, bounds)

        with self.assertRaisesRegex(ValueError, "at least one residual"):
            scientific_core.fit_least_squares(lambda _parameters: (), {"rate": 0.5}, {"rate": (0.0, 1.0)})
        with self.assertRaisesRegex(ValueError, "must be a finite number"):
            scientific_core.fit_least_squares(lambda _parameters: (float("nan"),),
                                              {"rate": 0.5}, {"rate": (0.0, 1.0)})
        with self.assertRaisesRegex(ValueError, "residual evaluation failed.*bad callback"):
            scientific_core.fit_least_squares(
                lambda _parameters: (_ for _ in ()).throw(RuntimeError("bad callback")),
                {"rate": 0.5},
                {"rate": (0.0, 1.0)},
            )

    def test_residual_dimension_changes_are_rejected(self):
        calls = 0

        def changing_residuals(_parameters):
            nonlocal calls
            calls += 1
            return (1.0,) if calls == 1 else (1.0, 2.0)

        with self.assertRaisesRegex(ValueError, "changed its residual dimension"):
            scientific_core.fit_least_squares(
                changing_residuals, {"rate": 0.5}, {"rate": (0.0, 1.0)}
            )

    def test_domain_error_on_finite_difference_is_contextual(self):
        def residuals(parameters):
            if parameters["rate"] < 0.5:
                raise ValueError("outside caller domain")
            return (parameters["rate"],)

        with self.assertRaisesRegex(
            ValueError, "parameter 'rate' lower difference.*outside caller domain"
        ):
            scientific_core.fit_least_squares(
                residuals,
                {"rate": 0.5},
                {"rate": (0.0, 1.0)},
                finite_difference_fraction=0.1,
            )

    def test_jacobian_size_is_bounded_before_differencing(self):
        calls = []
        with patch.object(scientific_core, "_MAX_FIT_JACOBIAN_VALUES", 4):
            with self.assertRaisesRegex(ValueError, "Jacobian exceeds 4 values"):
                scientific_core.fit_least_squares(
                    lambda _parameters: calls.append(1) or (1.0, 2.0, 3.0),
                    {"a": 0.0, "b": 0.0},
                    {"a": (-1.0, 1.0), "b": (-1.0, 1.0)},
                )
        self.assertEqual(calls, [1])

    def test_iteration_limit_is_not_reported_as_convergence(self):
        result = scientific_core.fit_least_squares(
            lambda parameters: (parameters["rate"] - 2.0,),
            {"rate": 0.0},
            {"rate": (-5.0, 5.0)},
            max_iterations=1,
        )

        self.assertEqual(result.status, "MAX_ITERATIONS")
        self.assertEqual(result.iterations, 1)
        self.assertLess(result.parameters["rate"], 2.0)


if __name__ == "__main__":
    unittest.main()
