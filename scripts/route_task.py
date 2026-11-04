#!/usr/bin/env python3
"""Deterministic, read-only role router; DOES NOT spawn agents or modify code."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

KINDS = {"build", "audit", "debug", "refactor", "optimize", "migrate", "release"}
DOMAINS = {"numerical", "ode", "identifiability", "dynamics", "differential_algebra", "optimization", "ml", "data", "symbolic", "general"}
INTERFACES = {"desktop_gui", "cli", "api", "none"}
TARGETS = {"windows", "linux", "macos"}
LANGUAGES = {"python", "idl", "cpp", "rust", "julia", "other"}
RISKS = {"R0", "R1", "R2", "R3"}
SCIENCE_CLAIM_DOMAINS = {"identifiability", "dynamics", "differential_algebra", "symbolic"}
NUMERICAL_DOMAINS = {"numerical", "ode", "identifiability", "dynamics", "optimization", "ml"}


def _validate_task_fields(task: dict[str, Any]) -> None:
    if not isinstance(task, dict):
        raise ValueError("The task must be a JSON object")
    for name in ("task_id", "request"):
        if not isinstance(task.get(name), str) or not task[name].strip():
            raise ValueError(f"{name} must be a nonempty string")
    kind = task.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    for name, choices in (("domains", DOMAINS), ("interfaces", INTERFACES),
                          ("targets", TARGETS), ("languages", LANGUAGES)):
        items = task.get(name)
        if not isinstance(items, list) or not items or any(not isinstance(i, str) or i not in choices for i in items):
            raise ValueError(f"{name} must be a nonempty list drawn from {sorted(choices)}")
    if task.get("risk") not in RISKS:
        raise ValueError("risk must be one of R0, R1, R2, R3")
    runtime = task.get("runtime", {})
    if not isinstance(runtime, dict) or any(not isinstance(runtime.get(k, False), bool)
                                            for k in ("real_subagents", "separate_contexts")):
        raise ValueError("runtime must be an object with boolean capabilities")


def _required_checks_for_valid_task(task: dict[str, Any]) -> list[str]:
    """Derive required checks without calling either public validator."""
    result = ["unit_tests", "static_analysis"]
    if task["kind"] in {"audit", "debug", "refactor", "optimize", "migrate"}:
        result.append("regression")
    if task["risk"] in {"R2", "R3"}:
        result.extend(["scientific_validation", "independent_review", "security_audit"])
    if "desktop_gui" in task["interfaces"]:
        result.append("gui_smoke")
    if {"windows", "linux"}.issubset(task["targets"]):
        result.append("cross_platform")
    if "idl" in task["languages"]:
        result.append("idl_integration")
    return result


def validate_task(task: dict[str, Any]) -> None:
    _validate_task_fields(task)
    if "check_specs" in task:
        try:
            from .execution_evidence import validate_check_specs
        except ImportError:  # Support direct execution/import from scripts directory.
            from execution_evidence import validate_check_specs
        validate_check_specs(task)


def required_checks(task: dict[str, Any]) -> list[str]:
    validate_task(task)
    return _required_checks_for_valid_task(task)


def route(task: dict[str, Any]) -> dict[str, Any]:
    validate_task(task)
    d, l, ui = set(task["domains"]), set(task["languages"]), set(task["interfaces"])
    primary = ["software_architect"]
    if task["kind"] != "audit":
        primary.append("implementation_engineer")
    for need, role in (
        ("ode" in d, "ode_model_specialist"),
        (bool(d & NUMERICAL_DOMAINS), "numerical_analyst"),
        (bool(d & SCIENCE_CLAIM_DOMAINS), "mathematical_model_specialist"),
        (bool(d & {"ml", "optimization"}), "optimization_ml_engineer"),
        ("data" in d, "data_engineer"),
        ("desktop_gui" in ui, "gui_engineer"),
        ("idl" in l, "idl_engineer"),
    ):
        if need:
            primary.append(role)
    reviewers = ["software_auditor"]
    if task["risk"] in {"R2", "R3"}:
        reviewers.extend(["security_reviewer", "independent_reviewer"])
    if task["kind"] == "release" or {"windows", "linux"}.issubset(task["targets"]):
        reviewers.append("release_engineer")
    runtime = task.get("runtime", {})
    isolated = runtime.get("real_subagents", False) and runtime.get("separate_contexts", False)
    return {
        "task_id": task["task_id"],
        "kind": task["kind"],
        "risk": task["risk"],
        "runtime_mode": "MULTI_CONTEXT_ELIGIBLE_NOT_STARTED" if isolated else "SINGLE_CONTEXT_SEQUENTIAL",
        "implementation_or_domain_roles": list(dict.fromkeys(primary)),
        "review_roles": list(dict.fromkeys(reviewers)),
        "scientific_bridge": "REQUIRES_EXTERNAL_SCIENTIFIC_REVIEW" if d & SCIENCE_CLAIM_DOMAINS else "CONDITIONAL_ON_CLAIMS",
        "required_evidence": _required_checks_for_valid_task(task),
        "next_action": "READ_ONLY_INVENTORY" if task["kind"] == "audit" else "INVENTORY_AND_ADR_BEFORE_IMPLEMENTATION",
        "note": "Plan only. No subagents executed, no tests run, no software certified.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_json", type=Path)
    args = parser.parse_args()
    try:
        task = json.loads(args.task_json.read_text(encoding="utf-8"))
        plan = route(task)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
