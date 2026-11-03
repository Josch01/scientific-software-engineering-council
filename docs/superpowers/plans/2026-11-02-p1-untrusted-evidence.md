# P1 Untrusted Evidence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent worker-controlled mailbox events and self-reported release JSON from advancing SSEC to a review-ready state before coordinator-produced execution evidence exists.

**Architecture:** Keep mailbox entries as untrusted worker communication and make the gate fail closed when coordinator-verified test and review records are absent. Keep the existing integrity checks for declared release logs, but distinguish byte integrity from execution provenance and never let evidence JSON attest to its own provenance. This is a bounded P1.1 hardening increment; it does not create the coordinator execution/evidence producer.

**Tech Stack:** Python standard library, `unittest`, Git worktrees and JSON artifacts.

**Spec:** `docs/CODEX_MASTER_MISSION.md`, P1 items 4–6 and Gate P1; architectural decisions in `docs/architecture/ADR-001-runtime-boundaries.md`.

## Global Constraints

- Do not merge to `main`, publish a stable release, or make a release decision in place of the human.
- CI must not call paid providers; real end-to-end provider checks remain opt-in and are never replaced by mocks or reported as run when absent.
- A worker cannot fabricate `REVIEW_ACCEPTED`, `TEST_PASS` or `RELEASE_READY` simply by writing JSON.
- Do not confuse a declared process, successful software test, or numerical result with independent review or scientific validity.
- Distinguish context isolation, directory isolation, and operating-system isolation; do not promise a sandbox the provider or host does not supply.
- Preserve explicit `NOT_RUN`/`BLOCKED` status when evidence is unavailable.

## Review Focus

- A worker submits a privileged event through `message()`; it must be rejected and cannot advance the gate.
- A worker edits `mailbox.jsonl` directly to add acceptance and `PASS` events; the gate must still block because the mailbox is untrusted.
- A reviewer submits its own `REVIEW_ACCEPTED` event; role labels do not prove an independent review execution.
- A fixture log has a matching SHA-256, exit code, timestamp, command and distinct claimed context IDs; integrity alone must not yield review readiness.
- A passing mechanical check must not imply scientific validity or human release approval.

---

### Task 1: Fail Closed on Self-Reported Mailbox and Release Evidence

**Files:**
- Modify: `scripts/worktree_coordinator.py`
- Test: `tests/test_development_worktrees.py`
- Modify: `scripts/release_gate.py`
- Test: `tests/test_release_gate.py`
- Modify: `references/WORKTREE_DEVELOPMENT.md`
- Modify: `references/RELEASE_POLICY.md`
- Modify: `docs/roadmap/FEATURE_MATRIX.md`

**Interfaces:**
- Keep public function signatures `message(project, task_id, sender, kind, summary, artifact="")`, `gate(project, task_id)`, and `evaluate(task, evidence, evidence_root)` unchanged.
- `message()` may record worker handoffs, review findings, change requests, and blockers, but rejects `REVIEW_ACCEPTED` and `TEST_RESULT` for every sender.
- `gate()` derives no test or review success from mailbox content. Until coordinator-run evidence records exist, missing verified tests/review keep its status `BLOCKED` and `evidence_verified` false, including if privileged JSON lines are injected directly.
- `evaluate()` may report declared log integrity, but raw evidence JSON cannot establish process provenance; without a coordinator-produced record the result is `BLOCKED`, with a specific provenance issue and `provenance_verified: false`.

- [x] **Step 1: Add regression tests for forged events and fixture evidence.** Add tests for worker and reviewer attempts to send both privileged message types; direct injection of `WORKER_RESULT`, `REVIEW_ACCEPTED`, and all required `TEST_RESULT` values into `mailbox.jsonl`; and valid-hash fixture logs with fabricated context IDs. Assert that the mailbox API rejects privileged events, the worktree gate stays `BLOCKED` with `evidence_verified` false, and the release gate stays `BLOCKED` with a provenance issue even though declared hashes match.
- [x] **Step 2: Run the new focused tests and record the expected failures.** Run `python -m unittest discover -s tests -p test_development_worktrees.py -v` and `python -m unittest discover -s tests -p test_release_gate.py -v`. The new assertions must fail against the baseline for the reasons above.
- [x] **Step 3: Implement fail-closed status derivation.** Restrict `message()` to non-approval communication and make `gate()` ignore mailbox claims as test/review authorization. Retain the current path/hash validation in `release_gate.evaluate()`, but prevent raw JSON declarations from reaching `READY_FOR_MANUAL_REVIEW`; report missing coordinator provenance explicitly. Do not add a field that JSON can self-assert as trusted.
- [x] **Step 4: Update user-facing policy and evidence matrix.** Document the untrusted mailbox, fail-closed gate, and absence of a coordinator evidence producer. Mark this increment as anti-forgery hardening, not completion of P1.1 or of the consortium.
- [x] **Step 5: Run focused and full regression suites.** Run `python -m unittest discover -s tests -p test_development_worktrees.py -v`, `python -m unittest discover -s tests -p test_release_gate.py -v`, then `python -m unittest discover -s tests -v`, and `python scripts/validate_skill.py`. Record exact results; the two baseline Windows symlink tests may remain blocked by host privilege (`WinError 1314`) and must not be hidden or recast as product failures.
- [x] **Step 6: Review and commit the task.** Inspect the full diff and commit only the listed files with message `fix: fail closed on self-reported evidence`.
