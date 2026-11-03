"""Bounded independent review of the latest checked integration; no approval authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import uuid
import math
import os
from pathlib import Path
import threading
import time

from .check_runner import _ensure_no_symlink_path, _resolve_evidence_path, read_check_manifest
from .development_runner import _review_one, _write_review_json, _MAX_REVIEW_INVOCATIONS
from .execution_evidence import validate_check_specs
from .integration_candidate import (_INTEGRATION_ID_RE, _json_file, _new_integration_id,
                                    _sha256, validate_integration_manifest)
from .prepare_agents import provider_for
from .provider_runtimes import create_runtime
from .review_evidence import validate_review_manifest
from .reviewer_output import _read_log, _MAX_LOG_BYTES
from .worktree_coordinator import directory, load


_IDENTITY = ("task_id", "task_revision", "task_sha256", "base_commit")
_BUNDLE_FIELDS = {"schema_version", "terminal", "status", "review_attempt_id", "integration_id",
                  "integration_manifest_sha256", "candidate_tree_sha256", "check_manifest_path",
                  "check_manifest_sha256", "review_roles", "reviewers", *_IDENTITY}


def _latest(root, selected):
    _ensure_no_symlink_path(root)
    attempts = sorted(root.iterdir(), key=lambda item: item.name)
    for attempt in attempts:
        _ensure_no_symlink_path(attempt)
        if not attempt.is_dir() or not _INTEGRATION_ID_RE.fullmatch(attempt.name):
            raise ValueError("invalid attempt directory")
    if not attempts or attempts[-1].name != selected:
        raise ValueError("only the latest attempt is eligible")


def _session(item):
    provider, session = item.get("provider"), item.get("provider_session_id")
    if provider not in {"codex", "gemini"} or type(session) is not str or not session or "\x00" in session:
        raise ValueError("invalid historical runtime session identity")
    return provider, session


def _corroborate_implementation_sessions(run, entries, state, *, successful):
    workers = {worker["role"]: worker for worker in state["workers"]}
    if sorted(item["role"] for item in entries) != sorted(workers):
        raise ValueError("implementation session inventory must contain the complete exact worker roster")
    for item in entries:
        role, provider = item["role"], item["provider"]
        if provider != workers[role]["provider"] or (successful and item["outcome"] != "SUCCEEDED"):
            raise ValueError("implementation session provider/outcome does not match the worker")
        path = run / (role + ".stdout")
        _ensure_no_symlink_path(path)
        if not path.is_file() or path.stat().st_size > _MAX_LOG_BYTES:
            raise ValueError("implementation session requires a bounded regular stdout record")
        before = _sha256(path)
        try:
            events = _read_log(path)
            kind, field = (("thread.started", "thread_id") if provider == "codex" else ("init", "session_id"))
            observed = [event.get(field) for event in events if event["type"] == kind]
            if not observed or any(value != item["provider_session_id"] for value in observed):
                raise ValueError("implementation session does not match the implementation stdout record")
            if _sha256(path) != before:
                raise ValueError("implementation stdout changed during validation")
        except (OSError, ValueError) as exc:
            raise ValueError("implementation session cannot be corroborated: " + str(exc)) from exc


def _historical_sessions(metadata, state, integration, *, exclude=None):
    """Reject duplicate observed sessions and include incomplete integrated attempts."""
    sessions = set()
    worker_reviews = {}
    review_logs, known_attempts = set(), set()
    def add(item):
        key = _session(item)
        if key in sessions:
            raise ValueError("historical runtime sessions must be unique")
        sessions.add(key)
    logs = metadata / "dev-logs"
    _ensure_no_symlink_path(logs)
    required = logs / integration["execution_id"] / "runtime-sessions.json"
    _ensure_no_symlink_path(required)
    if not required.is_file():
        raise ValueError("execution runtime-sessions.json is missing")
    for run in logs.iterdir():
        _ensure_no_symlink_path(run)
        path = run / "runtime-sessions.json"
        _ensure_no_symlink_path(path)
        if not path.exists():
            if not _INTEGRATION_ID_RE.fullmatch(run.name):
                raise ValueError("historical execution is missing a runtime session inventory")
            review_logs.add(run.name)
            reviews = run / "reviews"
            _ensure_no_symlink_path(reviews)
            if reviews.exists():
                for worker in reviews.iterdir():
                    _ensure_no_symlink_path(worker)
                    if worker.name != "integration_candidate":
                        raise ValueError("historical worker review is missing a runtime session inventory")
            continue
        data = _json_file(path)
        fields = {"schema_version", *_IDENTITY, "run_id", "run_status", "process_execution",
                  "check_status", "review_status", "implementation_sessions", "worker_review_sessions"}
        if (type(data) is not dict or set(data) != fields or type(data["schema_version"]) is not int or
                data["schema_version"] != 1 or data["run_id"] != run.name or
                any(data[key] != state[key] for key in _IDENTITY) or
                any(type(data[key]) is not str or not data[key] for key in
                    ("run_status", "process_execution", "check_status", "review_status"))):
            raise ValueError("runtime session inventory identity/status mismatch")
        if data["run_status"] not in {
                "NOT_RUN", "CHECKS_FAILED_NOT_REVIEWED", "CHECKS_VERIFIED_AWAITING_REVIEW",
                "REVIEW_BLOCKED_NO_CONFIGURED_REVIEWER", "REVIEW_BLOCKED_INVOCATION_LIMIT",
                "REVIEWED_WORKER_CANDIDATES_AWAITING_INTEGRATION", "REVIEW_FINDINGS_AWAITING_FIX",
                "REVIEW_BLOCKED", "REVIEW_INCOMPLETE"}:
            raise ValueError("runtime session inventory is not a terminal execution record")
        if path == required and (
                data["run_status"] != "REVIEWED_WORKER_CANDIDATES_AWAITING_INTEGRATION" or
                data["process_execution"] != "PROCESSES_FINISHED_UNREVIEWED" or
                data["check_status"] != "CHECKS_VERIFIED_AWAITING_REVIEW" or
                data["review_status"] != "WORKER_REVIEWS_COMPLETE_AWAITING_INTEGRATION"):
            raise ValueError("integration execution inventory does not record completed worker reviews")
        for field in ("implementation_sessions", "worker_review_sessions"):
            if type(data[field]) is not list:
                raise ValueError("runtime session inventory must contain session lists")
            for item in data[field]:
                expected = ({"role", "provider", "provider_session_id", "outcome"} if field == "implementation_sessions"
                            else {"worker_role", "reviewer_role", "provider", "provider_session_id", "outcome"})
                if type(item) is not dict or set(item) != expected or not isinstance(item["outcome"], str):
                    raise ValueError("runtime session inventory entry is invalid")
                role = item.get("role", item.get("worker_role"))
                if role not in {w["role"] for w in state["workers"]}:
                    raise ValueError("runtime session inventory has unknown worker")
                if field == "worker_review_sessions" and item["reviewer_role"] not in state["review_roles"]:
                    raise ValueError("runtime session inventory has unknown reviewer")
                add(item)
                if field == "worker_review_sessions":
                    worker_reviews[(run.name, role, item["reviewer_role"])] = _session(item)
        _corroborate_implementation_sessions(run, data["implementation_sessions"], state,
            successful=data["process_execution"] == "PROCESSES_FINISHED_UNREVIEWED")
        reviews = run / "reviews"
        _ensure_no_symlink_path(reviews)
        if reviews.exists():
            for worker in reviews.iterdir():
                _ensure_no_symlink_path(worker)
                for reviewer in worker.iterdir():
                    _ensure_no_symlink_path(reviewer)
                    manifest = reviewer / "manifest.json"
                    _ensure_no_symlink_path(manifest)
                    if manifest.exists():
                        review = _json_file(manifest)
                        session = review.get("provider_session_id")
                        if session is not None and worker_reviews.get((run.name, worker.name, reviewer.name)) != (
                                review.get("observed_provider"), session):
                            raise ValueError("worker review session is absent or misbound in runtime inventory")
    # Each previous attempt's bundle is also an incremental session journal.
    for candidate in (metadata / "integrations").iterdir():
        _ensure_no_symlink_path(candidate)
        attempts = candidate / "review-attempts"
        _ensure_no_symlink_path(attempts)
        if not attempts.exists():
            continue
        for attempt in attempts.iterdir():
            _ensure_no_symlink_path(attempt)
            known_attempts.add(attempt.name)
            if exclude is not None and attempt == exclude:
                continue
            bundle = attempt / "bundle.json"
            _ensure_no_symlink_path(bundle)
            # Missing terminal evidence cannot prove that an earlier launch's
            # observed session was inventoried. Block rather than infer no launch.
            recorded = set()
            if not bundle.is_file():
                raise ValueError("historical integrated review is incomplete: missing bundle")
            data = _json_file(bundle)
            if (type(data) is not dict or set(data) != _BUNDLE_FIELDS or data["terminal"] is not True or
                    data["status"] not in ("PASSED", "CHANGES_REQUESTED", "BLOCKED") or
                    data["review_attempt_id"] != attempt.name or data["integration_id"] != candidate.name or
                    data["review_roles"] != state["review_roles"] or type(data["reviewers"]) is not list or
                    any(type(item) is not dict for item in data["reviewers"]) or
                    [item.get("reviewer_role") for item in data["reviewers"]] != state["review_roles"]):
                raise ValueError("historical integrated review is incomplete or has an invalid roster")
            for item in data["reviewers"]:
                canonical = metadata / "dev-logs" / attempt.name / "reviews" / "integration_candidate" / item["reviewer_role"] / "manifest.json"
                _ensure_no_symlink_path(canonical)
                if not canonical.is_file() or item.get("manifest_path") != canonical.relative_to(metadata).as_posix():
                    raise ValueError("historical integrated review is incomplete: missing reviewer manifest")
                if _sha256(canonical) != item.get("manifest_sha256"):
                    raise ValueError("historical reviewer manifest digest mismatch")
                review = validate_review_manifest(_json_file(canonical), metadata)
                if (any(item.get(key) != review[key] for key in ("status", "verdict", "provider_session_id")) or
                        item.get("provider") != review["observed_provider"] or
                        review["reviewer_role"] != item["reviewer_role"] or review["worker_role"] != "integration_candidate"):
                    raise ValueError("historical reviewer manifest/session binding mismatch")
                if item.get("provider_session_id") is not None:
                    add(item)
                    recorded.add(_session(item))
                elif review["stdout_path"] is not None:
                    stdout = _resolve_evidence_path(metadata, review["stdout_path"], directory=False)
                    if stdout.stat().st_size:
                        raise ValueError("historical reviewer output has no corroborated session")
            reviews = metadata / "dev-logs" / attempt.name / "reviews" / "integration_candidate"
            _ensure_no_symlink_path(reviews)
            if reviews.exists():
                for reviewer in reviews.iterdir():
                    _ensure_no_symlink_path(reviewer)
                    manifest = reviewer / "manifest.json"
                    _ensure_no_symlink_path(manifest)
                    if not manifest.is_file() or reviewer.name not in state["review_roles"]:
                        raise ValueError("historical integrated review is incomplete: missing reviewer manifest")
                    if manifest.exists():
                        data = _json_file(manifest)
                        if data.get("provider_session_id") is not None:
                            item = dict(provider=data.get("observed_provider"), provider_session_id=data["provider_session_id"])
                            if _session(item) not in recorded:
                                add(item)
    if review_logs - known_attempts:
        raise ValueError("historical integrated review logs have no durable attempt record")
    return sessions


def _context(project, task_id, integration_id):
    project = Path(os.path.abspath(project))
    _ensure_no_symlink_path(project)
    metadata = directory(project, task_id)
    _ensure_no_symlink_path(metadata / "state.json")
    state, metadata = load(project, task_id)
    _ensure_no_symlink_path(metadata)
    metadata = metadata.resolve(strict=True)
    _latest(metadata / "integrations", integration_id)
    path = metadata / "integrations" / integration_id / "manifest.json"
    integration, check = validate_integration_manifest(path, metadata, state, validate_check_specs(state["task_packet"]))
    if integration["status"] != "CHECKED_AWAITING_INTEGRATED_REVIEW" or check is None or check["status"] != "PASSED":
        raise ValueError("integrated review requires the latest checked PASSED candidate")
    return state, metadata, integration, check


def validate_integration_review_bundle(path, metadata, state, integration, check_manifest):
    """Validate only the latest complete, bound roster, including persisted reports."""
    metadata, path = Path(metadata), Path(path)
    _ensure_no_symlink_path(metadata)
    _ensure_no_symlink_path(path)
    parts = path.relative_to(metadata).parts
    if (len(parts) != 5 or parts[0] != "integrations" or parts[1] != integration["integration_id"] or
            parts[2] != "review-attempts" or not _INTEGRATION_ID_RE.fullmatch(parts[3]) or parts[4] != "bundle.json"):
        raise ValueError("review bundle is outside canonical layout")
    _latest(metadata / "integrations", integration["integration_id"])
    _latest(path.parent.parent, path.parent.name)
    manifest = metadata / "integrations" / integration["integration_id"] / "manifest.json"
    current, checked = validate_integration_manifest(manifest, metadata, state, validate_check_specs(state["task_packet"]))
    if current != integration or checked != check_manifest or checked is None or checked["status"] != "PASSED":
        raise ValueError("integration/check evidence changed")
    before = _sha256(path)
    data = _json_file(path)
    if (type(data) is not dict or set(data) != _BUNDLE_FIELDS or type(data["schema_version"]) is not int or
            data["schema_version"] != 1 or data["terminal"] is not True or data["status"] not in {"PASSED", "CHANGES_REQUESTED", "BLOCKED"}):
        raise ValueError("incomplete or invalid review bundle")
    expected = {**{key: state[key] for key in _IDENTITY}, "integration_id": integration["integration_id"],
                "review_attempt_id": path.parent.name, "integration_manifest_sha256": _sha256(manifest),
                "candidate_tree_sha256": integration["candidate_tree_sha256"],
                "check_manifest_path": integration["check_manifest_path"],
                "check_manifest_sha256": integration["check_manifest_sha256"], "review_roles": state["review_roles"]}
    if any(data[key] != value for key, value in expected.items()):
        raise ValueError("review bundle identity, roster or digest mismatch")
    roster = state["review_roles"]
    if (not roster or type(data["reviewers"]) is not list or
            any(type(item) is not dict for item in data["reviewers"]) or
            [item.get("reviewer_role") for item in data["reviewers"]] != roster):
        raise ValueError("review bundle must contain the complete exact roster")
    sessions = _historical_sessions(metadata, state, integration, exclude=path.parent)
    statuses = []
    for item in data["reviewers"]:
        if set(item) != {"reviewer_role", "manifest_path", "manifest_sha256", "status", "verdict", "provider", "provider_session_id"}:
            raise ValueError("reviewer bundle fields are invalid")
        canonical = metadata / "dev-logs" / path.parent.name / "reviews" / "integration_candidate" / item["reviewer_role"] / "manifest.json"
        review_path = _resolve_evidence_path(metadata, item["manifest_path"], directory=False)
        if review_path != canonical or _sha256(review_path) != item["manifest_sha256"]:
            raise ValueError("review manifest path/digest mismatch")
        review = validate_review_manifest(_json_file(review_path), metadata)
        identity = {**{key: state[key] for key in _IDENTITY}, "worker_role": "integration_candidate",
                    "candidate_tree_sha256": integration["candidate_tree_sha256"],
                    "check_manifest_path": integration["check_manifest_path"],
                    "check_manifest_sha256": integration["check_manifest_sha256"],
                    "reviewer_role": item["reviewer_role"], "reviewer_provider": provider_for(item["reviewer_role"], state["mode"])}
        if (any(review[key] != value for key, value in identity.items()) or
                any(item[key] != review[key] for key in ("status", "verdict", "provider_session_id")) or
                item["provider"] != review["observed_provider"]):
            raise ValueError("reviewer evidence binding mismatch")
        if item["provider_session_id"] is not None:
            key = _session(item)
            if key in sessions:
                raise ValueError("reviewer reused historical session")
            sessions.add(key)
        statuses.append(review["status"])
        if _sha256(review_path) != item["manifest_sha256"]:
            raise ValueError("review manifest changed during validation")
    status = _aggregate(statuses)
    if data["status"] != status or _sha256(path) != before:
        raise ValueError("review bundle status mismatch or evidence changed")
    return data


def _aggregate(statuses):
    return ("PASSED" if statuses and all(s == "PASSED" for s in statuses) else
            "CHANGES_REQUESTED" if "REQUEST_CHANGES" in statuses else "BLOCKED")


def run_integration_review(project, task_id, integration_id, *, launch=False, cost_ack=False,
                           minutes=30, runtime_factory=None):
    if type(minutes) not in (int, float) or not math.isfinite(minutes) or minutes <= 0:
        raise ValueError("max minutes must be positive and finite")
    state, metadata, integration, check = _context(project, task_id, integration_id)
    roster = state["review_roles"]
    if not roster or len(roster) > _MAX_REVIEW_INVOCATIONS:
        raise ValueError("integrated review requires a bounded configured reviewer roster")
    sessions = _historical_sessions(metadata, state, integration)
    report = dict(status="PREVIEW_NOT_STARTED", review_roles=roster, review_results=[], bundle_path=None,
                  automatic_merge=False, release_status="NOT_APPROVED")
    if not launch:
        return report
    if not cost_ack:
        raise ValueError("execution requires --accept-unmetered-cost")
    attempt_id = _new_integration_id()
    attempt = metadata / "integrations" / integration_id / "review-attempts" / attempt_id
    _ensure_no_symlink_path(attempt)
    attempt.mkdir(parents=True, exist_ok=False)
    path = attempt / "bundle.json"
    bundle = dict(schema_version=1, terminal=False, status="RUNNING", review_attempt_id=attempt_id,
        integration_id=integration_id, **{key: state[key] for key in _IDENTITY},
        integration_manifest_sha256=_sha256(metadata / "integrations" / integration_id / "manifest.json"),
        candidate_tree_sha256=integration["candidate_tree_sha256"], check_manifest_path=integration["check_manifest_path"],
        check_manifest_sha256=integration["check_manifest_sha256"], review_roles=roster, reviewers=[])
    _write_review_json(path, bundle)
    report["bundle_path"] = path.relative_to(metadata).as_posix()
    # Keep reviewer cwd below Windows' CreateProcess directory length limit.
    # Only the durable bundle is nested beneath the integration attempt.
    logs = metadata / "dev-logs" / attempt_id
    _ensure_no_symlink_path(logs)
    logs.mkdir(parents=True, exist_ok=False)
    worker = dict(role="integration_candidate", path=integration["candidate_worktree_path"],
                  branch=integration["candidate_branch"], _check_manifest_path=str(metadata / integration["check_manifest_path"]))
    deadline, stop = time.monotonic() + minutes * 60, threading.Event()
    runtimes = []
    def fresh_runtime(provider):
        runtime = (runtime_factory or create_runtime)(provider)
        if any(runtime is previous for previous in runtimes):
            raise ValueError("integrated reviewers require a fresh runtime instance")
        runtimes.append(runtime)
        return runtime
    for role in roster:
        result = _review_one(state["task_packet"], state, worker, role, metadata, logs,
                             deadline, stop, fresh_runtime, cost_ack, sessions)
        report["review_results"].append(result)
        reference = result["manifest_path"]
        review_path = _resolve_evidence_path(metadata, reference, directory=False) if reference else None
        digest = _sha256(review_path) if review_path else None
        manifest = _json_file(review_path) if review_path else None
        bundle["reviewers"].append(dict(reviewer_role=role, manifest_path=reference,
            manifest_sha256=digest,
            status=manifest["status"] if manifest else "FAILED", verdict=result["verdict"],
            provider=result["provider"], provider_session_id=result["provider_session_id"]))
        _write_review_json(path, bundle, replace_existing=True)
    bundle.update(terminal=True, status=_aggregate([item["status"] for item in bundle["reviewers"]]))
    _write_review_json(path, bundle, replace_existing=True)
    report["status"] = bundle["status"]
    if report["status"] in {"PASSED", "CHANGES_REQUESTED"}:
        validate_integration_review_bundle(path, metadata, state, integration, check)
    return report



_DECISIONS = {"APPROVE_FOR_MANUAL_INTEGRATION", "REJECT"}
_DECISION_FIELDS = {"schema_version", "decision_id", "integration_id", "review_bundle_path",
                    "review_bundle_sha256", "candidate_tree_sha256", "check_manifest_sha256",
                    "decision", "operator", "reason", "created_at_utc", *_IDENTITY}


def current_integration_review(metadata, state, integration, check):
    """Return the exact latest canonical bundle after rederiving all bindings."""
    attempts = metadata / "integrations" / integration["integration_id"] / "review-attempts"
    _ensure_no_symlink_path(attempts)
    entries = sorted(attempts.iterdir(), key=lambda item: item.name) if attempts.is_dir() else []
    latest = entries[-1] if entries else None
    if latest is None:
        raise ValueError("independent integrated review and human approval are required: review bundle missing")
    path = latest / "bundle.json"
    before = _sha256(path)
    bundle = validate_integration_review_bundle(path, metadata, state, integration, check)
    if _sha256(path) != before:
        raise ValueError("review bundle changed during validation")
    return path, bundle, before


def _decision_text(value):
    return type(value) is str and bool(value.strip()) and "\x00" not in value


def validate_human_decision(path, metadata, state, integration, check):
    """Validate local declared attestation, without authenticating the operator."""
    canonical = metadata / "integrations" / integration["integration_id"] / "human-decision.json"
    if path != canonical:
        raise ValueError("human decision is outside canonical layout")
    _ensure_no_symlink_path(path)
    before = _sha256(path)
    data = _json_file(path)
    bundle_path, bundle, bundle_hash = current_integration_review(metadata, state, integration, check)
    expected = {**{key: state[key] for key in _IDENTITY}, "integration_id": integration["integration_id"],
                "review_bundle_path": bundle_path.relative_to(metadata).as_posix(),
                "review_bundle_sha256": bundle_hash, "candidate_tree_sha256": integration["candidate_tree_sha256"],
                "check_manifest_sha256": integration["check_manifest_sha256"]}
    if (type(data) is not dict or set(data) != _DECISION_FIELDS or
            type(data["schema_version"]) is not int or data["schema_version"] != 1 or
            any(data[key] != value for key, value in expected.items()) or
            (data["decision"] != "REJECT" and bundle["status"] != "PASSED") or
            type(data["decision"]) is not str or data["decision"] not in _DECISIONS or
            not all(_decision_text(data[key]) for key in ("operator", "reason")) or
            type(data["decision_id"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", data["decision_id"]) or
            type(data["created_at_utc"]) is not str or
            not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", data["created_at_utc"])):
        raise ValueError("human decision identity, binding or declaration mismatch")
    datetime.strptime(data["created_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    if _sha256(path) != before:
        raise ValueError("human decision changed during validation")
    return data


def record_human_decision(project, task_id, integration_id, *, expected_bundle_sha256,
                          decision, operator, reason):
    """Create an immutable local attestation for consideration of manual integration."""
    if (type(expected_bundle_sha256) is not str or
            not re.fullmatch(r"[0-9a-f]{64}", expected_bundle_sha256)):
        raise ValueError("expected bundle digest must be a full lowercase SHA-256")
    if type(decision) is not str or decision not in _DECISIONS:
        raise ValueError("invalid human decision")
    if not all(_decision_text(value) for value in (operator, reason)):
        raise ValueError("operator and reason must be nonempty declarations")
    state, metadata, integration, check = _context(project, task_id, integration_id)
    bundle_path, bundle, bundle_hash = current_integration_review(metadata, state, integration, check)
    if bundle_hash != expected_bundle_sha256:
        raise ValueError("decision requires the exact current review bundle digest")
    if decision == "APPROVE_FOR_MANUAL_INTEGRATION":
        from .worktree_coordinator import gate
        if bundle["status"] != "PASSED" or gate(Path(os.path.abspath(project)), task_id)["status"] != "NEEDS_HUMAN":
            raise ValueError("approval requires a current PASSED bundle and gate NEEDS_HUMAN")
    path = metadata / "integrations" / integration_id / "human-decision.json"
    _ensure_no_symlink_path(path)
    data = dict(schema_version=1, decision_id=uuid.uuid4().hex,
        **{key: state[key] for key in _IDENTITY}, integration_id=integration_id,
        review_bundle_path=bundle_path.relative_to(metadata).as_posix(), review_bundle_sha256=bundle_hash,
        candidate_tree_sha256=integration["candidate_tree_sha256"],
        check_manifest_sha256=integration["check_manifest_sha256"], decision=decision,
        operator=operator, reason=reason, created_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    # Exclusive creation prevents concurrent writers from replacing a decision.
    # A partial write remains invalid and blocks rather than inheriting approval.
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ValueError("human decision already exists; decisions are immutable") from exc
    return validate_human_decision(path, metadata, state, integration, check)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review")
    review.add_argument("--project", type=Path, required=True)
    review.add_argument("--task-id", required=True)
    review.add_argument("--integration-id", required=True)
    review.add_argument("--execute", action="store_true")
    review.add_argument("--accept-unmetered-cost", action="store_true")
    review.add_argument("--max-minutes", type=float, default=30)
    decide = commands.add_parser("decide")
    decide.add_argument("--project", type=Path, required=True)
    decide.add_argument("--task-id", required=True)
    decide.add_argument("--integration-id", required=True)
    decide.add_argument("--expected-bundle-sha256", required=True)
    decide.add_argument("--decision", choices=sorted(_DECISIONS), required=True)
    decide.add_argument("--operator", required=True)
    decide.add_argument("--reason", required=True)
    args = parser.parse_args()
    import json
    try:
        if args.command == "decide":
            result = record_human_decision(args.project, args.task_id, args.integration_id,
                expected_bundle_sha256=args.expected_bundle_sha256, decision=args.decision,
                operator=args.operator, reason=args.reason)
        else:
            result = run_integration_review(args.project, args.task_id, args.integration_id,
                launch=args.execute, cost_ack=args.accept_unmetered_cost, minutes=args.max_minutes)
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if args.command == "decide" or result["status"] in {"PASSED", "PREVIEW_NOT_STARTED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
