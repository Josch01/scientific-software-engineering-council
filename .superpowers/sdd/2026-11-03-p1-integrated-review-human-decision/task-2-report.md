# Task 2 — integrated candidate review

Implemented `scripts.integration_review` with the requested API and CLI. Preview validates evidence without runtime creation or artifact writes. Execution validates the latest checked candidate and the originating terminal runtime inventory, then reuses `_review_one()` exactly once for the configured reviewer roster with a fresh runtime instance, existing deadline/cancellation handling, and read-only snapshot requests. No call to `execute()` is made.

A create-only, ordered review-attempt directory and RUNNING bundle are published before runtime execution. Reviewer results incrementally update this separate schema-1 bundle. The validator revalidates integration/check evidence, exact roster, reviewer manifests and digests, task/tree/check bindings, historical session uniqueness, and latest-attempt selection. Empty/incomplete newer attempts invalidate an older PASS.

Windows investigation found that nesting reviewer cwd under both integration and review-attempt IDs makes CreateProcess fail with WinError 267. Reviewer logs/snapshots therefore use the shorter `metadata/dev-logs/<review_attempt_id>` root; the required bundle remains at `integrations/<integration_id>/review-attempts/<review_attempt_id>/bundle.json` and binds the exact reviewer manifest paths/hashes. Both trees use the shared reparse-aware guard. Changes in development_runner/review_evidence are limited to the guards required by this review path.

TDD evidence:

- Initial exact six-test RED run: six ModuleNotFoundError failures because `scripts.integration_review` did not exist.
- Additional inventory subcases RED: nonterminal `RUNNING` inventory was incorrectly accepted; wrong execution ID and duplicate-session cases already rejected. Added terminal inventory validation and successful originating-execution status checks.
- First GREEN attempt exposed WinError 267 in the offline local child runtime. Instrumented the runtime result, isolated the long cwd, then shortened only the reviewer work/log root.
- Corrective focused run: 5 tests passed (three formerly failing runtime/bundle cases plus both required regression cases).
- Review-evidence regression run plus portable simulated Windows reparse case: 32 tests run, OK with 2 platform skips (unavailable symlink privilege and POSIX chmod on Windows).
- Final exact six focused tests plus the two required regression cases: PASS (8 tests; final frozen-code run in 200.813s).
- CLI `python -m scripts.integration_review review --help`: passed.
- `git diff --check`: passed.

Offline assurance: tests patch concrete Gemini adapter discovery and argv construction to launch only `sys.executable -c` with deterministic local JSON output. They never resolve, probe, or launch Gemini/Codex CLIs and cannot incur provider cost. Provider E2E, account/context independence, effective OS sandboxing, scientific validity, merge/release, and human approval are not claimed. Verification is limited to the focused/regression commands requested for this task and the directly affected review-evidence module.

Final history audit: added a RED subcase for an older `dev-logs/<run_id>` worker-review tree without a runtime inventory; the test demonstrated it was skipped. Such launch history now blocks review rather than claiming session non-reuse from incomplete records. Integrated-review log roots remain governed by their durable review-attempt records and bundles; orphan integrated-review logs also block. Legacy workspaces with pre-inventory launch logs may require a fresh task/workspace/run with complete inventory history.

The first final combined command passed all 8 tests in 192.935s. A fresh combined run after the legacy-history correction passed all 8 tests in 199.588s. Review-evidence regression result is precisely 32 tests run, OK with 2 platform skips.

Malformed-roster audit: `reviewers=[null]` reproduced AttributeError (RED). The validator now checks entry object shape before role lookup and returns deterministic ValueError; the focused test passed in 37.384s. No broader suite is required by the supervising task instruction; final verification remains the six Task 2 tests plus the two specified regressions, rerun after this last validator change.


Final frozen-code verification after the malformed-roster guard: exact six Task 2 tests from the brief plus `test_executable_index_mode_is_preserved` and `test_integrated_checks_run_against_composed_candidate_and_gate_stays_blocked` — PASS, 8 tests in 200.813s. `git diff --cached --check` and compilation also pass. No provider calls, approval, merge, release, or broader suite.

## Task 2 fix round 1 — corroborated session history

Review finding 1: “Incomplete implementation inventories are accepted. `integration_review.py:99` validates individual entries but never requires a complete implementation roster or binds its sessions to implementation records. A terminal successful inventory containing `implementation_sessions=[]` passes. An integrated reviewer can therefore reuse an omitted implementation session undetected. Require corroborated completeness, or reject inventories that cannot establish it. The test fixture itself generates an empty implementation inventory, so existing coverage misses this requirement.”

The inventory must now contain exactly one session for every configured worker. Each entry's provider must match its worker assignment; successful execution records require SUCCEEDED worker outcomes. Every session is corroborated against the provider's session events in its canonical `dev-logs/<execution_id>/<worker_role>.stdout` record, with bounded strict JSONL parsing, reparse guards, and before/after hashes. Missing/empty/partial inventories, missing transcripts, and session mismatches block before any reviewer runtime. The offline fixture now includes the complete worker roster and provider-shaped implementation transcripts.

Review finding 2: “Interrupted integrated reviews can disappear from session history. `integration_review.py:146` accepts an earlier bundle with no recorded reviewers; `integration_review.py:161` silently ignores reviewer directories without manifests. If execution stops after the provider launches and writes its session to stdout, but before `_review_one()` persists its manifest, a subsequent attempt neither recovers that session nor rejects the incomplete history. Require complete, corroborated launch history or block the new attempt.”

Earlier integrated attempts must now have terminal full-roster bundles and each exact reviewer manifest with its bound digest and validated evidence/session identity. A RUNNING bundle or missing manifest blocks a later review, even when output already contains the launched provider session. Reviewer directories with missing manifests or unknown roles also block. Tests cover both a terminal bundle whose reviewer manifest disappeared and a RUNNING bundle with no recorded reviewers after stdout was written.

Exact RED command:

```text
python -m unittest -v tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_incomplete_implementation_history tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_interrupted_launch_without_manifest
```

Result: FAILED (5 failures), reproducing acceptance of incomplete/unbound implementation history and interrupted launch history. Refined the misbound-session fixture to use distinct wrong IDs so duplicate-session rejection could not mask the missing transcript binding. Exact refined RED command:

```text
python -m unittest -v tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_incomplete_implementation_history
```

Result: FAILED (4 failures, 28.025s): empty roster, partial roster, distinct misbound sessions, and missing implementation stdout all remained accepted.

The initial two-test command above then passed after the production fix: 2 tests in 54.513s. Compilation and `git diff --check` pass. Final verification includes the two affected tests, the exact six Task 2 tests, and the required executable-mode and composed-candidate-check regressions; its exact command/result follow below.

Limit: older partial launches or interrupted integrated reviews whose session history cannot be corroborated now block conservatively. They require a fresh task/workspace with complete history rather than silently claiming non-reuse. No provider E2E, paid CLI call, `execute()` invocation, acceptance, merge, or release was introduced.


Final frozen-code command:

```text
python -m unittest -v tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_incomplete_implementation_history tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_interrupted_launch_without_manifest tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_preview_makes_no_provider_call tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_requires_latest_checked_candidate tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_reused_runtime_session tests.test_integration_candidate.IntegrationCandidateTests.test_review_bundle_rejects_incomplete_or_misbound_roster tests.test_integration_candidate.IntegrationCandidateTests.test_latest_incomplete_review_does_not_reuse_previous_pass tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_metadata_reparse_path tests.test_integration_candidate.IntegrationCandidateTests.test_executable_index_mode_is_preserved tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_checks_run_against_composed_candidate_and_gate_stays_blocked
```

Result: OK — 10 tests in 254.829s, no skips or failures. Also ran `python -m py_compile scripts/integration_review.py tests/test_integration_candidate.py` and `git diff --cached --check`: both pass. Only the requested affected/focused/regression cases were run; no broad repository suite.
