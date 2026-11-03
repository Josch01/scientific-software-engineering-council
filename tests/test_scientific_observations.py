import json
import math
import unittest
from copy import deepcopy

from scripts import scientific_core


def exponential_dataset(rate=0.8):
    times = (0.0, 0.15, 0.5, 1.0)
    return {
        "schema_version": 1,
        "time_unit": "day",
        "variables": [{"name": "infected", "unit": "people"}],
        "observations": [
            {"time": time, "values": {"infected": math.exp(-rate * time)}}
            for time in times
        ],
        "provenance": {"source": "synthetic test data"},
    }


class ObservationDatasetTests(unittest.TestCase):
    def test_versioned_sparse_dataset_round_trips_with_stable_digest(self):
        payload = {
            "schema_version": 1,
            "time_unit": "day",
            "variables": [
                {"name": "infected", "unit": "people"},
                {"name": "susceptible", "unit": "people"},
            ],
            "observations": [
                {"time": 0.0, "values": {"infected": 5.0}},
                {"time": 1.0, "values": {"susceptible": 95.0, "infected": 4.0}},
            ],
            "provenance": {"source": "field-notes.csv", "study": "example"},
        }

        original_payload = deepcopy(payload)
        dataset = scientific_core.ObservationDataset.from_dict(payload)
        payload["variables"][0]["unit"] = "changed"
        payload["observations"][0]["values"]["infected"] = 99.0
        payload["provenance"]["source"] = "changed source"
        serialized = dataset.to_dict()
        encoded = json.dumps(serialized, sort_keys=True, allow_nan=False)
        restored = scientific_core.ObservationDataset.from_dict(json.loads(encoded))

        self.assertEqual(
            dataset,
            scientific_core.ObservationDataset.from_dict(original_payload),
        )
        self.assertEqual(restored.content_sha256, dataset.content_sha256)
        self.assertEqual(restored.to_dict(), serialized)
        self.assertEqual(restored.times, (0.0, 1.0))
        self.assertEqual(restored.values[0], {"infected": 5.0})
        self.assertEqual(len(dataset.content_sha256), 64)
        with self.assertRaises(TypeError):
            dataset.values[0]["infected"] = 6.0

    def test_digest_mismatch_is_rejected(self):
        payload = exponential_dataset()
        payload["content_sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "content_sha256"):
            scientific_core.ObservationDataset.from_dict(payload)

    def test_variable_order_is_part_of_dataset_content_identity(self):
        first = {
            "schema_version": 1,
            "time_unit": "day",
            "variables": [{"name": "x", "unit": "m"}, {"name": "y", "unit": "s"}],
            "observations": [{"time": 0.0, "values": {"x": 1.0, "y": 2.0}}],
            "provenance": {"source": "synthetic"},
        }
        second = {
            **first,
            "variables": [{"name": "y", "unit": "s"}, {"name": "x", "unit": "m"}],
        }

        first_dataset = scientific_core.ObservationDataset.from_dict(first)
        second_dataset = scientific_core.ObservationDataset.from_dict(second)

        self.assertNotEqual(first_dataset.content_sha256, second_dataset.content_sha256)

    def test_public_constructor_cannot_bypass_dataset_validation_or_freezing(self):
        mutable_units = {"infected": "people"}
        mutable_row = {"infected": 1.0}

        with self.assertRaisesRegex(TypeError, "from_dict"):
            scientific_core.ObservationDataset(
                time_unit="day",
                variable_units=mutable_units,
                times=(0.0, 1.0),
                values=(mutable_row,),
                provenance={"source": "synthetic"},
                content_sha256="0" * 64,
            )

    def test_malformed_dataset_contracts_are_rejected(self):
        cases = []
        payload = exponential_dataset()
        payload["schema_version"] = True
        cases.append((payload, "schema_version"))
        payload = exponential_dataset()
        payload["time_unit"] = " "
        cases.append((payload, "time_unit"))
        payload = exponential_dataset()
        payload["observations"][1]["time"] = 0.0
        cases.append((payload, "strictly increasing"))
        payload = exponential_dataset()
        payload["observations"][0]["values"]["unknown"] = 1.0
        cases.append((payload, "unknown variable"))
        payload = exponential_dataset()
        payload["observations"][0]["values"]["infected"] = float("nan")
        cases.append((payload, "finite number"))
        payload = exponential_dataset()
        payload["provenance"] = {"study": "missing required source"}
        cases.append((payload, "source"))
        payload = exponential_dataset()
        payload["observations"][0]["values"] = {}
        cases.append((payload, "at least one measured variable"))

        for bad_payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError, message
            ):
                scientific_core.ObservationDataset.from_dict(bad_payload)


class ObservationEvaluationTests(unittest.TestCase):
    def _decay_problem(self, rate=0.8, rhs_calls=None):
        def rhs(_time, state, parameters):
            if rhs_calls is not None:
                rhs_calls.append(1)
            return (-parameters["rate"] * state[0],)

        return scientific_core.OdeProblem(
            rhs=rhs,
            t_span=(0.0, 1.0),
            initial_state=(1.0,),
            parameters={"rate": rate},
            state_names=("infected",),
        )

    def test_irregular_observation_times_are_integrated_without_interpolation(self):
        dataset = scientific_core.ObservationDataset.from_dict(exponential_dataset())
        evaluation = scientific_core.evaluate_observations(
            self._decay_problem(),
            dataset,
            model_time_unit="day",
            model_variable_units={"infected": "people"},
            max_step=0.1,
        )

        self.assertEqual(evaluation.times, dataset.times)
        self.assertEqual(evaluation.segment_step_counts, (0, 2, 4, 5))
        self.assertEqual(evaluation.total_step_count, 11)
        self.assertEqual(evaluation.residual_order, tuple((time, "infected") for time in dataset.times))
        self.assertTrue(all(abs(value) < 1e-5 for value in evaluation.residuals))
        self.assertEqual(evaluation.observation_sha256, dataset.content_sha256)
        json.dumps(evaluation.to_dict(), allow_nan=False)

    def test_residual_order_follows_declared_variable_order(self):
        dataset = scientific_core.ObservationDataset.from_dict(
            {
                "schema_version": 1,
                "time_unit": "day",
                "variables": [{"name": "x", "unit": "m"}, {"name": "y", "unit": "s"}],
                "observations": [{"time": 0.0, "values": {"y": 2.0, "x": 1.0}}],
                "provenance": {"source": "synthetic"},
            }
        )
        problem = scientific_core.OdeProblem(
            rhs=lambda _t, _state, _parameters: (0.0, 0.0),
            t_span=(0.0, 1.0),
            initial_state=(1.5, 2.5),
            parameters={},
            state_names=("x", "y"),
        )

        evaluation = scientific_core.evaluate_observations(
            problem,
            dataset,
            model_time_unit="day",
            model_variable_units={"x": "m", "y": "s"},
            max_step=0.1,
        )

        self.assertEqual(evaluation.residual_order, ((0.0, "x"), (0.0, "y")))
        self.assertEqual(evaluation.residuals, (0.5, 0.5))

    def test_variable_order_changes_both_digest_and_residual_order(self):
        payload = {
            "schema_version": 1,
            "time_unit": "day",
            "variables": [{"name": "x", "unit": "m"}, {"name": "y", "unit": "s"}],
            "observations": [{"time": 0.0, "values": {"x": 1.0, "y": 2.0}}],
            "provenance": {"source": "synthetic"},
        }
        reversed_payload = {
            **payload,
            "variables": [{"name": "y", "unit": "s"}, {"name": "x", "unit": "m"}],
        }
        problem = scientific_core.OdeProblem(
            rhs=lambda _t, _state, _parameters: (0.0, 0.0),
            t_span=(0.0, 1.0),
            initial_state=(1.5, 2.5),
            parameters={},
            state_names=("x", "y"),
        )

        first = scientific_core.evaluate_observations(
            problem,
            scientific_core.ObservationDataset.from_dict(payload),
            model_time_unit="day",
            model_variable_units={"x": "m", "y": "s"},
            max_step=0.1,
        )
        second = scientific_core.evaluate_observations(
            problem,
            scientific_core.ObservationDataset.from_dict(reversed_payload),
            model_time_unit="day",
            model_variable_units={"x": "m", "y": "s"},
            max_step=0.1,
        )

        self.assertNotEqual(first.observation_sha256, second.observation_sha256)
        self.assertEqual(first.residual_order, ((0.0, "x"), (0.0, "y")))
        self.assertEqual(second.residual_order, ((0.0, "y"), (0.0, "x")))

    def test_time_unit_state_unit_and_variable_mismatches_fail_before_rhs(self):
        dataset = scientific_core.ObservationDataset.from_dict(exponential_dataset())
        calls = []
        problem = self._decay_problem(rhs_calls=calls)
        arguments = {
            "problem": problem,
            "dataset": dataset,
            "model_time_unit": "day",
            "model_variable_units": {"infected": "people"},
            "max_step": 0.1,
        }

        with self.assertRaisesRegex(ValueError, "time unit"):
            scientific_core.evaluate_observations(
                **{**arguments, "model_time_unit": "hour"}
            )
        with self.assertRaisesRegex(ValueError, "unit mismatch"):
            scientific_core.evaluate_observations(
                **{**arguments, "model_variable_units": {"infected": "cases"}}
            )
        with self.assertRaisesRegex(ValueError, "not a problem state"):
            scientific_core.evaluate_observations(
                problem,
                dataset,
                model_time_unit="day",
                model_variable_units={"other": "people"},
                max_step=0.1,
            )
        self.assertEqual(calls, [])

    def test_time_range_and_work_budgets_are_checked_before_rhs_calls(self):
        dataset = scientific_core.ObservationDataset.from_dict(exponential_dataset())
        calls = []
        problem = self._decay_problem(rhs_calls=calls)

        with self.assertRaisesRegex(ValueError, "outside problem.t_span"):
            scientific_core.evaluate_observations(
                problem,
                scientific_core.ObservationDataset.from_dict(
                    {**exponential_dataset(), "observations": [
                        {"time": 2.0, "values": {"infected": 0.1}}
                    ]}
                ),
                model_time_unit="day",
                model_variable_units={"infected": "people"},
                max_step=0.1,
            )
        with self.assertRaisesRegex(ValueError, "max_total_steps"):
            scientific_core.evaluate_observations(
                problem,
                dataset,
                model_time_unit="day",
                model_variable_units={"infected": "people"},
                max_step=0.1,
                max_total_steps=10,
            )
        self.assertEqual(calls, [])

    def test_observation_residuals_compose_with_least_squares_fit(self):
        dataset = scientific_core.ObservationDataset.from_dict(exponential_dataset(0.8))

        def residuals(parameters):
            problem = self._decay_problem(parameters["rate"])
            return scientific_core.evaluate_observations(
                problem,
                dataset,
                model_time_unit="day",
                model_variable_units={"infected": "people"},
                max_step=0.05,
            ).residuals

        fit = scientific_core.fit_least_squares(
            residuals,
            {"rate": 0.3},
            {"rate": (0.0, 2.0)},
        )

        self.assertEqual(fit.status, "CONVERGED")
        self.assertAlmostEqual(fit.parameters["rate"], 0.8, delta=1e-4)
        self.assertLess(fit.cost, 1e-8)


if __name__ == "__main__":
    unittest.main()
