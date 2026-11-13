import importlib
import importlib.util
import json
import math
import unittest


class ThesisSIRModelTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("scripts.thesis_sir_model")
        self.model = importlib.import_module("scripts.thesis_sir_model") if spec else None

    def require_model_api(self):
        for name in (
            "HarmonicTerm",
            "ThesisSIRParameters",
            "WeeklyCountObservations",
            "evaluate_thesis_sir_weekly_counts",
        ):
            self.assertIsNotNone(self.model, "thesis SIR model module is missing")
            self.assertTrue(hasattr(self.model, name), f"missing scientific API: {name}")

    def parameters(self, **changes):
        self.require_model_api()
        values = {
            "d0": 0.0,
            "harmonics": (self.model.HarmonicTerm(1.0, 0.5, 0.5),),
            "gamma": 0.2,
            "log10_initial_infectious": 2.0,
            "susceptible_fraction": 0.999,
            "ascertainment_fraction": 0.5,
            "delay_days": 4.3,
        }
        values.update(changes)
        return self.model.ThesisSIRParameters(**values)

    def test_exponential_fourier_transmission_matches_direct_formula(self):
        parameters = self.parameters()
        self.assertAlmostEqual(parameters.beta(0.0), math.exp(1.0), places=12)
        self.assertAlmostEqual(parameters.beta(math.pi), math.exp(0.5), places=12)

    def test_compartment_rhs_matches_the_declared_sir_equations(self):
        parameters = self.parameters()
        self.assertTrue(hasattr(parameters, "derivative"), "thesis SIR RHS is missing")
        population = self.model.THESIS_SIR_POPULATION
        state = (0.7 * population, 1_000_000.0, 0.3 * population - 1_000_000.0)
        beta = parameters.beta(0.0)
        infection = beta * state[0] * state[1] / population
        removal = parameters.gamma * state[1]
        derivative = parameters.derivative(0.0, state)
        self.assertAlmostEqual(derivative[0], -infection, places=8)
        self.assertAlmostEqual(derivative[1], infection - removal, places=8)
        self.assertAlmostEqual(derivative[2], removal, places=8)
        self.assertAlmostEqual(sum(derivative), 0.0, places=8)

    def test_thesis_parameter_bounds_and_initial_feasibility_are_enforced(self):
        self.require_model_api()
        term = self.model.HarmonicTerm
        make = self.model.ThesisSIRParameters
        valid = {
            "d0": 0.0,
            "harmonics": (term(0.0, 0.0, 0.5),),
            "gamma": 0.2,
            "log10_initial_infectious": 2.0,
            "susceptible_fraction": 0.5,
            "ascertainment_fraction": 0.5,
            "delay_days": 4.3,
        }
        for field, value in (("d0", 2.01), ("gamma", 0.04),
                             ("log10_initial_infectious", 9.0),
                             ("susceptible_fraction", 1.01),
                             ("ascertainment_fraction", 1.01),
                             ("delay_days", 2.0)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                make(**{**valid, field: value})
        with self.assertRaises(ValueError):
            make(**{**valid, "harmonics": ()})
        with self.assertRaises(ValueError):
            make(**{**valid, "harmonics": tuple(term(0.0, 0.0, 0.5) for _ in range(4))})
        with self.assertRaises(ValueError):
            make(**{**valid, "harmonics": (term(2.01, 0.0, 0.5),)})
        with self.assertRaises(ValueError):
            make(**{**valid, "harmonics": (term(0.0, 0.0, 2.21),)})
        with self.assertRaises(ValueError):
            make(**{**valid, "susceptible_fraction": 1.0})

    def test_upper_initial_infectious_bound_rounds_to_exact_population(self):
        self.require_model_api()
        population = self.model.THESIS_SIR_POPULATION
        parameters = self.parameters(
            log10_initial_infectious=math.log10(population),
            susceptible_fraction=0.0,
        )
        self.assertEqual(parameters.initial_state(), (0.0, population, 0.0))

    def test_weekly_incidence_uses_shift_q_and_preserves_population(self):
        self.require_model_api()
        observations = self.model.WeeklyCountObservations(
            week_labels=("2021-SE44", "2021-SE45"), counts=(10, 12)
        )
        parameters = self.parameters(
            harmonics=(self.model.HarmonicTerm(0.0, 0.0, 0.5),),
            delay_days=3.5,
        )
        result = self.model.evaluate_thesis_sir_weekly_counts(
            parameters, observations, max_step=0.1, max_steps_per_interval=20
        )
        self.assertEqual(result.interval_starts, (-0.5, 0.5))
        self.assertEqual(result.interval_ends, (0.5, 1.5))
        self.assertEqual(len(result.predicted_means), 2)
        self.assertTrue(all(value > 0.0 for value in result.predicted_means))
        self.assertTrue(all(abs(sum(state[:3]) - 129_960_600) < 1e-5
                            for state in result.states_at_boundaries))
        serialized = result.to_dict()
        prediction = serialized["prediction"]
        self.assertEqual(prediction["state_boundary_times_week"], [-0.5, 0.5, 1.5])
        self.assertEqual(serialized["scientific_validity"], "NOT_ASSESSED")

    def test_default_delay_shifts_first_week_by_the_thesis_central_value(self):
        self.require_model_api()
        observations = self.model.WeeklyCountObservations(
            week_labels=("2021-SE44",), counts=(10,)
        )
        result = self.model.evaluate_thesis_sir_weekly_counts(
            self.parameters(), observations, max_step=0.1, max_steps_per_interval=20
        )
        self.assertAlmostEqual(result.interval_starts[0], -4.3 / 7.0, places=14)
        self.assertAlmostEqual(result.interval_ends[0], 1.0 - 4.3 / 7.0, places=14)

    def test_observation_fraction_scales_weekly_means_and_q_respects_data_bound(self):
        self.require_model_api()
        observations = self.model.WeeklyCountObservations(
            week_labels=("2021-SE44",), counts=(10,)
        )
        common = {
            "harmonics": (self.model.HarmonicTerm(0.0, 0.0, 0.5),),
            "delay_days": 0.0,
        }
        half = self.model.evaluate_thesis_sir_weekly_counts(
            self.parameters(ascertainment_fraction=0.5, **common), observations,
            max_step=0.1, max_steps_per_interval=20,
        )
        full = self.model.evaluate_thesis_sir_weekly_counts(
            self.parameters(ascertainment_fraction=1.0, **common), observations,
            max_step=0.1, max_steps_per_interval=20,
        )
        self.assertAlmostEqual(half.predicted_means[0], 0.5 * full.predicted_means[0], places=8)
        with self.assertRaises(ValueError):
            self.model.evaluate_thesis_sir_weekly_counts(
                self.parameters(ascertainment_fraction=1e-9, **common), observations,
                max_step=0.1, max_steps_per_interval=20,
            )

    def test_weekly_incidence_shows_fourth_order_step_refinement(self):
        self.require_model_api()
        observations = self.model.WeeklyCountObservations(
            week_labels=("2021-SE44",), counts=(10,)
        )
        parameters = self.parameters(
            harmonics=(self.model.HarmonicTerm(0.0, 0.0, 0.5),),
            delay_days=0.0,
        )
        def mean(step):
            result = self.model.evaluate_thesis_sir_weekly_counts(
                parameters, observations, max_step=step,
                max_steps_per_interval=100,
            )
            return result.predicted_means[0]

        coarse, medium, fine = mean(0.5), mean(0.25), mean(0.125)
        self.assertGreater(abs(coarse - medium), 8.0 * abs(medium - fine))

    def test_evaluator_bounds_work_and_rejects_counts_above_population(self):
        self.require_model_api()
        parameters = self.parameters(
            harmonics=(self.model.HarmonicTerm(0.0, 0.0, 0.5),),
            delay_days=0.0,
        )
        small_data = self.model.WeeklyCountObservations(
            week_labels=("2021-SE44",), counts=(10,)
        )
        with self.assertRaisesRegex(ValueError, "max_steps_per_interval"):
            self.model.evaluate_thesis_sir_weekly_counts(
                parameters, small_data, max_step=1e-320,
                max_steps_per_interval=100,
            )
        oversized_data = self.model.WeeklyCountObservations(
            week_labels=("2021-SE44",), counts=(129_960_601,)
        )
        with self.assertRaisesRegex(ValueError, "population bound"):
            self.model.evaluate_thesis_sir_weekly_counts(
                parameters, oversized_data, max_step=0.1,
                max_steps_per_interval=20,
            )

    def test_from_dict_round_trip_preserves_versioned_contract(self):
        self.require_model_api()
        parameters = self.parameters()
        parsed = self.model.ThesisSIRParameters.from_dict(parameters.to_dict())
        self.assertEqual(parsed, parameters)
        payload = parameters.to_dict()
        payload["unexpected"] = True
        with self.assertRaises(ValueError):
            self.model.ThesisSIRParameters.from_dict(payload)


class ThesisSIRDataAdapterTests(unittest.TestCase):
    def test_strict_json_adapter_selects_only_the_declared_candidate_series(self):
        spec = importlib.util.find_spec("scripts.thesis_sir_data")
        self.assertIsNotNone(spec, "scripts.thesis_sir_data adapter is missing")
        adapter = importlib.import_module("scripts.thesis_sir_data")
        labels = [f"2021-SE{i:02d}" for i in range(44, 53)]
        labels.extend(f"2022-SE{i}" for i in range(1, 48))
        payload = {
            "target_window": {
                "n_weeks": 56,
                "first_week": labels[0],
                "last_week": labels[-1],
            },
            "week_by_week_comparison": [
                {"week": week, "local": 999, "DGE_sunday_saturday": 888,
                 "DGE_monday_sunday_candidate": index}
                for index, week in enumerate(labels)
            ],
        }
        dataset = adapter.parse_dge_reconstruction_json(json.dumps(payload))
        self.assertEqual(dataset.series_id, "DGE_monday_sunday_candidate")
        self.assertEqual(dataset.week_labels, tuple(labels))
        self.assertEqual(dataset.counts, tuple(range(56)))
        self.assertEqual(len(dataset.source_sha256), 64)

    def test_adapter_rejects_missing_noninteger_duplicate_or_wrong_length_series(self):
        spec = importlib.util.find_spec("scripts.thesis_sir_data")
        self.assertIsNotNone(spec, "scripts.thesis_sir_data adapter is missing")
        adapter = importlib.import_module("scripts.thesis_sir_data")
        labels = [f"2021-SE{i:02d}" for i in range(44, 53)]
        labels.extend(f"2022-SE{i}" for i in range(1, 48))
        rows = [{"week": week, "DGE_monday_sunday_candidate": index}
                for index, week in enumerate(labels)]
        gap_rows = [*rows]
        gap_rows[1] = {**gap_rows[1], "week": "2021-SE46"}

        def encode(test_rows):
            return json.dumps({
                "target_window": {"n_weeks": 56, "first_week": labels[0],
                                  "last_week": labels[-1]},
                "week_by_week_comparison": test_rows,
            })

        for invalid_rows in (
            rows[:-1],
            [{**rows[0], "DGE_monday_sunday_candidate": None}, *rows[1:]],
            [{**rows[0], "DGE_monday_sunday_candidate": True}, *rows[1:]],
            [rows[0], {**rows[1], "week": rows[0]["week"]}, *rows[2:]],
            gap_rows,
            [{"week": row["week"], "local": 1} for row in rows],
        ):
            with self.subTest(rows=invalid_rows[0]), self.assertRaises(ValueError):
                adapter.parse_dge_reconstruction_json(encode(invalid_rows))

    def test_adapter_rejects_malformed_json_and_duplicate_object_keys(self):
        spec = importlib.util.find_spec("scripts.thesis_sir_data")
        self.assertIsNotNone(spec, "scripts.thesis_sir_data adapter is missing")
        adapter = importlib.import_module("scripts.thesis_sir_data")
        for payload in ("{broken", '{"target_window": {}, "target_window": {}}'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                adapter.parse_dge_reconstruction_json(payload)
