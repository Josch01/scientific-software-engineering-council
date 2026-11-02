#!/usr/bin/env python3
"""Validate claimed release evidence and artifact hashes; human approval is still required."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .route_task import required_checks
except ImportError:  # direct script execution
    from route_task import required_checks


def evaluate(task: dict[str, Any], evidence: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    checks_needed = required_checks(task)
    reasons: list[str] = []
    if not isinstance(evidence, dict) or evidence.get("task_id") != task["task_id"]:
        reasons.append("task_id mismatch or malformed evidence")
        checks: dict[str, Any] = {}
    else:
        checks = evidence.get("checks", {})
        if not isinstance(checks, dict):
            checks = {}
            reasons.append("checks must be a JSON object")
    trusted_root = evidence_root.resolve()
    for name in checks_needed:
        check = checks.get(name)
        if not isinstance(check, dict):
            reasons.append(f"{name}: missing check")
            continue
        if check.get("status") != "PASS" or check.get("exit_code") != 0:
            reasons.append(f"{name}: not PASS with exit_code=0")
            continue
        if not all(isinstance(check.get(key), str) and check[key].strip()
                   for key in ("command", "environment", "executed_at", "log_path", "sha256")):
            reasons.append(f"{name}: missing command/environment/date/log/hash")
            continue
        relpath = Path(check["log_path"])
        log_path = (trusted_root / relpath).resolve()
        if relpath.is_absolute() or not log_path.is_relative_to(trusted_root) or not log_path.is_file():
            reasons.append(f"{name}: log does not exist inside evidence root")
            continue
        digest = hashlib.sha256(log_path.read_bytes()).hexdigest()
        if digest != check["sha256"]:
            reasons.append(f"{name}: log SHA-256 mismatch")
        if name == "independent_review":
            independent = check.get("independence") in {
                "CROSS_PROVIDER_SEPARATE_CONTEXT", "SAME_PROVIDER_SEPARATE_CONTEXT"
            }
            producer_id = check.get("producer_context_id")
            reviewer_id = check.get("reviewer_context_id")
            separated = (isinstance(producer_id, str) and bool(producer_id.strip()) and
                         isinstance(reviewer_id, str) and bool(reviewer_id.strip()) and
                         producer_id != reviewer_id)
            if not independent or not separated:
                reasons.append(f"{name}: no two distinct declared review contexts")
    return {
        "task_id": task["task_id"],
        "gate_status": "BLOCKED" if reasons else "READY_FOR_MANUAL_REVIEW",
        "checks_required": checks_needed,
        "issues": reasons,
        "warning": "A log hash validates integrity, not provenance, adequacy of tests, review independence or mathematical truth.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--root", type=Path, help="Root directory for relative log files; defaults to evidence parent")
    args = parser.parse_args()
    try:
        task = json.loads(args.task.read_text(encoding="utf-8"))
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        result = evaluate(task, evidence, args.root or args.evidence.parent)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["gate_status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
