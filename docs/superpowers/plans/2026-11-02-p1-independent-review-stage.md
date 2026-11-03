# P1 independent review stage — implementation plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development. Implement each task test-first, run the listed commands, and stop only when evidence or a blocker is recorded.

**Goal:** Add an evidence-bound reviewer invocation after deterministic worker checks without claiming integration acceptance or scientific validity.

**Architecture:** Keep the existing `AgentRuntime` boundary. Add a strict provider-output extractor and structured review report validator, then invoke reviewers only after every worker's checks pass. Recapture a separate copy of each checked candidate; bind its Git-visible tree hash to the worker check manifest and record its artifact hash before/after review. Bind the invocation to persisted role/provider, input, logs, and hashes. Keep review evidence separate from canonical acceptance. Use bounded JSON manifests under coordinator metadata. Existing gate remains `BLOCKED` until integration and fix-loop gates exist.

**Tech stack:** Python standard library, existing Codex/Gemini runtime adapters, `unittest`, Git temporary repositories.

### Task 1: Strict final-response extraction

**Files:** `scripts/reviewer_output.py`, `tests/test_reviewer_output.py`

1. Add offline JSONL fixture tests for valid Codex/Gemini final messages, missing/failure terminal, malformed JSON, ambiguous/multiple final messages, wrong types/providers, and size bound.
2. Run `python -m unittest tests.test_reviewer_output -v` and confirm the new cases fail before implementation.
3. Implement extraction only; it must not interpret verdicts or claim reviewer independence.
4. Rerun the focused tests and retain output.

### Task 2: Strict review report contract

**Files:** `scripts/review_evidence.py`, `tests/test_review_evidence.py`

1. Test bounded JSON parsing, exact schema, allowed verdict/severity values, finding path safety, duplicate JSON keys rejection, and task/candidate/check bindings.
2. Implement report parsing/serialization and evidence hash verification. Reject extra/missing fields and non-finite JSON values.
3. Run `python -m unittest tests.test_review_evidence -v`.

### Task 3: Coordinator reviewer stage

**Files:** `scripts/development_runner.py`, `scripts/review_evidence.py`, `tests/test_development_worktrees.py`

1. Add failing tests proving reviewer is not called after failed/missing checks, custom/fake runtime adapters cannot create review evidence, incomplete reviews return nonzero, and cancelled/preparation-failed attempts are persisted.
2. Add parser fixtures for successful Codex/Gemini-shaped output and coordinator tests that reject offline runtime fixtures, bind attempt records, and preserve non-acceptance states. These fixtures do not create successful provider review manifests.
3. Implement bounded reviewer launch within remaining global deadline using persisted role/provider and the concrete runtime adapter. Bound diff collection while reading, save manifests and terminal attempts inside task metadata, mark provider/sandbox/E2E limitations explicitly, and downgrade a successful attempt to `FAILED` if its manifest cannot be validated or persisted.
4. Add tests that findings stay `REQUEST_CHANGES`, no mailbox `REVIEW_ACCEPTED` is emitted, and overall result/gate remain non-accepting.
5. Run `python -m unittest tests.test_development_worktrees tests.test_review_evidence tests.test_reviewer_output -v`.

### Task 4: Documentation, matrix, and full verification

**Files:** `docs/roadmap/FEATURE_MATRIX.md`, `docs/test-reports/p1-independent-review-stage-2026-11-02.md`

1. Document only what the local tests and observed provider runtime support; real Codex/Gemini review remains `NOT_RUN` unless explicitly executed.
2. Run `python -m unittest discover -s tests -v` and `python scripts/validate_skill.py`.
3. Record commit SHA, OS, Python, exact commands, exit codes/counts, log paths/hashes, defects, and `NOT_RUN`/`BLOCKED` requirements.
4. Review the full diff in a separate context, fix findings, commit on `codex/p1-independent-review-loop`, and open a draft PR targeting the P1.1b branch. Never merge, release, or auto-accept.

## Acceptance for this increment

- No reviewer process launches unless all applicable worker deterministic checks pass.
- Provider final response, review schema, candidate/check identity, and runtime observations are strictly bound and bounded.
- A successful attempt is not left terminally successful when its corresponding manifest fails validation or persistence; offline fixtures cannot create a countable provider review manifest.
- Fake/custom/local fixtures can verify parser and state transitions but cannot yield a `PASSED` provider review manifest.
- Mutation, wrong reviewer, absent CLI/session, malformed output, ambiguity, timeout, cancellation, and missing evidence all fail closed.
- No mailbox or run output can set release approval; the coordinator gate stays blocked pending final integration, fix loop, and human decision.
