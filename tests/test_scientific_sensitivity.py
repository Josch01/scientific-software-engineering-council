import importlib
import importlib.util
import json
import math
import unittest


def load_scientific_core(test_case):
    spec = importlib.util.find_spec("scripts.scientific_core")
    test_case.assertIsNotNone(spec, "scripts.scientific_core must expose sensitivity analysis")
    return importlib.import_module("scripts.scientific_core")


class ParameterSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.core = load_scientific_core(self)

    def test_exponential_decay_sensitivity_matches_analytic_derivative(self):
        problem = self.core.OdeProblem(
            rhs=lambda _time, state, parameters: (-parameters["rate"] * state[0],),
            t_span=(0.0, 1.0),
            initial_state=(2.0,),
            parameters={"rate": 0.7},
            state_names=("amount",),
        )

        result = self.core.parameter_sensitivities(
            problem, {"rate": 0.01}, max_step=0.02
        )

        for index, time in enumerate(result.times):
            expected = -time * 2.0 * math.exp(-0.7 * time)
            self.assertAlmostEqual(result.values[index][0][0], expected, delta=2e-5)
        self.assertEqual(result.values[0][0][0], 0.0)
        self.assertEqual(result.base_solution.parameters["rate"], 0.7)

    def test_axes_follow_time_state_and_explicit_parameter_order(self):
        problem = self.core.OdeProblem(
            rhs=lambda _time, _state, parameters: (parameters["a"], parameters["b"]),
            t_span=(0.0, 1.0),
            initial_state=(0.0, 0.0),
            parameters={"a": 2.0, "b": 3.0, "unused": 9.0},
            state_names=("x", "z"),
        )

        result = self.core.parameter_sensitivities(
            problem,
            {"b": 0.02, "a": 0.01, "unused": 0.2},
            max_step=0.2,
        )

        self.assertEqual(result.parameter_names, ("b", "a", "unused"))
        self.assertAlmostEqual(result.values[-1][0][0], 0.0, delta=1e-12)
        self.assertAlmostEqual(result.values[-1][0][1], 1.0, delta=1e-12)
        self.assertAlmostEqual(result.values[-1][0][2], 0.0, delta=1e-12)
        self.assertAlmostEqual(result.values[-1][1][0], 1.0, delta=1e-12)
        self.assertAlmostEqual(result.values[-1][1][1], 0.0, delta=1e-12)
        self.assertAlmostEqual(result.values[-1][1][2], 0.0, delta=1e-12)

    def test_halving_absolute_perturbation_reduces_cubic_central_difference_error_by_four(self):
        problem = self.core.OdeProblem(
            rhs=lambda _time, _state, parameters: (parameters["p"] ** 3,),
            t_span=(0.0, 1.0),
            initial_state=(0.0,),
            parameters={"p": 2.0},
        )

        coarse = self.core.parameter_sensitivities(
            problem, {"p": 0.2}, max_step=0.25
        )
        fine = self.core.parameter_sensitivities(
            problem, {"p": 0.1}, max_step=0.25
        )
        exact = 3.0 * 2.0**2
        coarse_error = abs(coarse.values[-1][0][0] - exact)
        fine_error = abs(fine.values[-1][0][0] - exact)

        self.assertAlmostEqual(coarse_error / fine_error, 4.0, delta=1e-10)

    def test_absolute_perturbations_work_at_zero_and_negative_parameter_values(self):
        for parameter_value in (0.0, -0.5):
            with self.subTest(parameter_value=parameter_value):
                problem = self.core.OdeProblem(
                    rhs=lambda _time, _state, parameters: (parameters["p"],),
                    t_span=(0.0, 1.0),
                    initial_state=(0.0,),
                    parameters={"p": parameter_value},
                )

                result = self.core.parameter_sensitivities(
                    problem, {"p": 0.1}, max_step=0.2
                )

                self.assertAlmostEqual(result.values[-1][0][0], 1.0, delta=1e-12)
                self.assertEqual(problem.parameters["p"], parameter_value)

    def test_serialization_records_effective_bounds_and_work(self):
        problem = self.core.OdeProblem(
            rhs=lambda _time, _state, parameters: (parameters["rate"],),
            t_span=(0.0, 1.0),
            initial_state=(0.0,),
            parameters={"rate": 0.5},
            state_names=("state",),
        )

        result = self.core.parameter_sensitivities(
            problem, {"rate": 0.1}, max_step=0.25
        )
        payload = result.to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["method"], "CENTRAL_FINITE_DIFFERENCE")
        self.assertEqual(payload["state_names"], ["state"])
        self.assertEqual(payload["parameter_names"], ["rate"])
        self.assertEqual(payload["parameter_bounds"]["rate"], {"lower": 0.4, "upper": 0.6})
        self.assertEqual(payload["total_step_count"], 12)
        self.assertEqual(payload["rhs_evaluation_count"], 48)
        json.dumps(payload, allow_nan=False)

    def test_rejects_invalid_parameters_and_unrepresentable_perturbation_bounds(self):
        def problem(value):
            return self.core.OdeProblem(
                rhs=lambda _time, _state, _parameters: (0.0,),
                t_span=(0.0, 1.0),
                initial_state=(0.0,),
                parameters={"p": value},
            )

        invalid_steps = (
            ({}, "non-empty"),
            ({"unknown": 0.1}, "unknown"),
            ({"p": 0.0}, "positive"),
            ({"p": float("inf")}, "finite"),
        )
        for selected, expected in invalid_steps:
            with self.subTest(selected=selected), self.assertRaisesRegex(
                ValueError, expected
            ):
                self.core.parameter_sensitivities(
                    problem(1.0), selected, max_step=0.1
                )

        for value, step in ((1e300, 1.0), (1e308, 1e308)):
            with self.subTest(value=value, step=step), self.assertRaisesRegex(
                ValueError, "perturbation"
            ):
                self.core.parameter_sensitivities(
                    problem(value), {"p": step}, max_step=0.1
                )

    def test_aggregate_step_budget_is_checked_before_rhs_calls(self):
        calls = []
        problem = self.core.OdeProblem(
            rhs=lambda *_: calls.append(1) or (0.0,),
            t_span=(0.0, 1.0),
            initial_state=(0.0,),
            parameters={"p": 1.0},
        )

        with self.assertRaisesRegex(ValueError, "max_total_steps"):
            self.core.parameter_sensitivities(
                problem,
                {"p": 0.1},
                max_step=0.25,
                max_total_steps=11,
            )
        self.assertEqual(calls, [])

    def test_output_memory_bound_is_checked_before_rhs_calls(self):
        calls = []
        parameter_names = tuple(f"p{index}" for index in range(5))
        problem = self.core.OdeProblem(
            rhs=lambda *_: calls.append(1) or (0.0,),
            t_span=(0.0, 1.0),
            initial_state=(0.0,),
            parameters={name: 1.0 for name in parameter_names},
        )
        perturbations = {name: 0.1 for name in parameter_names}

        with self.assertRaisesRegex(ValueError, "output/intermediates"):
            self.core.parameter_sensitivities(
                problem,
                perturbations,
                max_step=1.0 / 80_000,
                max_total_steps=1_000_000,
            )
        self.assertEqual(calls, [])

    def test_failure_of_a_perturbed_trajectory_is_contextual_and_has_no_result(self):
        problem = self.core.OdeProblem(
            rhs=lambda _time, _state, parameters: (
                (_ for _ in ()).throw(ValueError("negative parameter rejected"))
                if parameters["p"] < 0.0
                else 0.0,
            ),
            t_span=(0.0, 1.0),
            initial_state=(0.0,),
            parameters={"p": 0.1},
        )

        with self.assertRaisesRegex(ValueError, "parameter 'p'.*lower perturbation"):
            self.core.parameter_sensitivities(
                problem, {"p": 0.2}, max_step=0.5
            )


if __name__ == "__main__":
    unittest.main()
