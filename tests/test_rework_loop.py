import unittest
from unittest.mock import patch

from scripts import rework_loop


class ReworkLoopTests(unittest.TestCase):
    def setUp(self):
        self.packet = {
            "source_integration_id": "source-integration",
            "source_review_bundle_sha256": "a" * 64,
            "findings": [{"id": "F-1"}],
        }

    def test_preview_does_not_execute_or_build_candidate(self):
        with (patch.object(rework_loop, "prepare_rework_packet", return_value=self.packet),
              patch.object(rework_loop, "validate_rework_packet", return_value="b" * 64),
              patch.object(rework_loop, "execute") as execute,
              patch.object(rework_loop, "build_integration_candidate") as build,
              patch.object(rework_loop, "run_integration_review") as review):
            result = rework_loop.run_rework_cycle(
                "project", {}, "task", "source-integration", "Fix F-1",
            )

        self.assertEqual(result["status"], "PREVIEW_ONLY")
        self.assertEqual(result["finding_count"], 1)
        self.assertEqual(result["execution_status"], "NOT_RUN")
        execute.assert_not_called()
        build.assert_not_called()
        review.assert_not_called()

    def test_cancelled_worker_stage_stops_before_candidate_and_review(self):
        with (patch.object(rework_loop, "prepare_rework_packet", return_value=self.packet),
              patch.object(rework_loop, "validate_rework_packet", return_value="b" * 64),
              patch.object(rework_loop, "execute", return_value={
                  "run_id": "run-1", "execution": "CANCELLED",
              }) as execute,
              patch.object(rework_loop, "build_integration_candidate") as build,
              patch.object(rework_loop, "run_integration_review") as review):
            result = rework_loop.run_rework_cycle(
                "project", {}, "task", "source-integration", "Fix F-1",
                launch=True, confirm=True, cost_ack=True,
            )

        self.assertEqual(result["status"], "WORKER_STAGE_BLOCKED")
        self.assertEqual(result["approval_status"], "NOT_APPROVED")
        execute.assert_called_once()
        build.assert_not_called()
        review.assert_not_called()

    def test_rework_launch_requires_confirmation_and_cost_ack_before_execution(self):
        with (patch.object(rework_loop, "prepare_rework_packet", return_value=self.packet),
              patch.object(rework_loop, "validate_rework_packet", return_value="b" * 64),
              patch.object(rework_loop, "execute") as execute):
            with self.assertRaisesRegex(ValueError, "confirmation"):
                rework_loop.run_rework_cycle(
                    "project", {}, "task", "source-integration", "Fix F-1",
                    launch=True, confirm=False, cost_ack=True,
                )
            with self.assertRaisesRegex(ValueError, "unmetered-cost"):
                rework_loop.run_rework_cycle(
                    "project", {}, "task", "source-integration", "Fix F-1",
                    launch=True, confirm=True, cost_ack=False,
                )

        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
