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
