"""Run one explicitly confirmed rework, then fresh checks and integrated review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.development_runner import _confirm_task_check_commands, execute
from scripts.integration_candidate import build_integration_candidate
from scripts.integration_review import prepare_rework_packet, run_integration_review, validate_rework_packet


def run_rework_cycle(project, task, task_id, integration_id, operator_instruction, *,
                     launch=False, confirm=False, cost_ack=False, parallel=1, minutes=60,
                     review_minutes=30, runtime_factory=None):
    """Preview or run exactly one rework cycle; never makes a human decision."""
    packet = prepare_rework_packet(project, task_id, integration_id, operator_instruction)
    packet_sha256 = validate_rework_packet(project, task_id, packet)
    result = {
        "schema_version": 1,
        "task_id": task_id,
        "source_integration_id": integration_id,
        "source_review_bundle_sha256": packet["source_review_bundle_sha256"],
        "rework_packet_sha256": packet_sha256,
        "finding_count": len(packet["findings"]),
        "execution_status": "NOT_RUN",
        "integration_status": "NOT_RUN",
        "integrated_review_status": "NOT_RUN",
        "approval_status": "NOT_APPROVED",
        "automatic_merge": False,
        "release_status": "NOT_APPROVED",
    }
    if not launch:
        result["status"] = "PREVIEW_ONLY"
        return result
    if not confirm:
        raise ValueError("explicit rework confirmation is required")
    if not cost_ack:
        raise ValueError("--accept-unmetered-cost required")
    execution = execute(
        project, task_id, task, launch=True, cost_ack=True, parallel=parallel,
        minutes=minutes, runtime_factory=runtime_factory, rework_packet=packet,
        rework_confirmed=True,
    )
    result["execution_id"] = execution.get("run_id")
    result["execution_status"] = execution.get("execution", "UNKNOWN")
    if execution.get("execution") != "REVIEWED_WORKER_CANDIDATES_AWAITING_INTEGRATION":
        result["status"] = "WORKER_STAGE_BLOCKED"
        return result
    candidate = build_integration_candidate(project, task_id, execution["run_id"])
    result["integration_id"] = candidate.integration_id
    result["integration_status"] = candidate.status
    if candidate.status != "CHECKED_AWAITING_INTEGRATED_REVIEW":
        result["status"] = "INTEGRATION_BLOCKED"
        return result
    review = run_integration_review(
        project, task_id, candidate.integration_id, launch=True, cost_ack=True,
        minutes=review_minutes, runtime_factory=runtime_factory,
    )
    result["integrated_review_status"] = review["status"]
    if review["status"] == "PASSED":
        result["approval_status"] = "NEEDS_HUMAN"
        result["status"] = "NEEDS_HUMAN"
    else:
        result["status"] = review["status"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_json", type=Path)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--integration-id", required=True)
    parser.add_argument("--rework-instruction", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-rework", action="store_true")
    parser.add_argument("--accept-unmetered-cost", action="store_true")
    parser.add_argument("--max-parallel", type=int, default=1)
    parser.add_argument("--max-minutes", type=int, default=60)
    parser.add_argument("--max-review-minutes", type=int, default=30)
    args = parser.parse_args()
    try:
        task = json.loads(args.task_json.read_text(encoding="utf-8"))
        if args.execute:
            if not args.confirm_rework or not args.accept_unmetered_cost:
                raise ValueError("--execute requires --confirm-rework and --accept-unmetered-cost")
            phrase = f"REWORK {args.task_id} FROM {args.integration_id}"
            if input(f"This runs all workers and independent reviewers. Type {phrase!r}: ").strip() != phrase:
                raise ValueError("rework confirmation did not match")
            _confirm_task_check_commands(task, args.task_id)
        elif args.confirm_rework or args.accept_unmetered_cost:
            raise ValueError("confirmation and cost flags are only valid with --execute")
        result = run_rework_cycle(
            args.project, task, args.task_id, args.integration_id, args.rework_instruction,
            launch=args.execute, confirm=args.confirm_rework,
            cost_ack=args.accept_unmetered_cost, parallel=args.max_parallel,
            minutes=args.max_minutes, review_minutes=args.max_review_minutes,
        )
    except (EOFError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PREVIEW_ONLY", "NEEDS_HUMAN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
