# P1 independent review stage — design

## Scope

Add a coordinator-managed reviewer invocation after successful deterministic checks. In this increment the reviewer examines a separate copy of each worker candidate, recaptured only when its tree hash still matches the passing check manifest and archived check snapshot. The artifact is therefore a review of a worker candidate, not a review of a combined integration candidate.

## Why this increment

`development_runner.execute()` currently stops at `CHECKS_VERIFIED_AWAITING_REVIEW`; the P1 contract requires a separate reviewer process after checks. The current coordinator does not yet construct or test a combined candidate from multiple worktrees. Calling this stage a final consortium review would overstate its evidence, so the result must remain explicitly pending integration, fix-loop handling, and human decision.

## Flow

1. Finish all implementation workers.
2. Run the task's deterministic checks for every worker candidate.
3. If any worker/check failed, was cancelled, timed out, or is missing required check evidence, do not launch reviewers.
4. For each worker candidate, launch each configured reviewer using its persisted role/provider assignment and a fresh runtime request/session. Capture a separate review copy from the candidate worktree and require its Git-visible tree hash to match both the passing check manifest and archived check snapshot. Keep the prior check snapshot untouched.
5. Bind reviewer input to task ID/revision/digest, base commit, worker role/branch, candidate tree hash, check manifest hash, and the specific diff. Do not include a prior approval opinion in the first reviewer prompt.
6. Request read-only behavior, preserve provider/session/log/hash/timing observations, and re-hash the snapshot after review. Any change invalidates that review record. OS sandbox effectiveness remains separately `UNVERIFIED` unless the provider proves it.
7. Parse one unambiguous final provider response and validate a strict structured report. Only the concrete Codex/Gemini runtime adapter for the persisted provider can produce a successful review manifest; custom/test adapters and invalid, ambiguous, unavailable, timed out, cancelled, or mutated-snapshot outcomes cannot count as independent review evidence.
8. Persist a bounded, versioned review manifest and terminal attempt record under task metadata. If preparation fails before candidate identity is complete, persist an attempt record with `identity: null`. Persist the attempt before its manifest so an attempt-write failure cannot leave countable review evidence; if manifest validation or writing fails after a successful attempt write, atomically mark that attempt `FAILED`. Findings are recorded as requests for correction; this increment does not retry implementers or promote a final acceptance state.

## Evidence and statuses

Each review record binds the canonical task digest/revision, base commit, worker identity, candidate and diff hashes, check manifest hash, reviewer role/provider, concrete runtime adapter type, runtime run/session IDs, input and stdout/stderr hashes, start/end times, exit status, parsed verdict, findings, and limitations. A separate attempt record persists incomplete and failed preparation outcomes, including the absence of a complete candidate identity. The coordinator validates all fields and hashes before representing a review as observed. SHA-256 establishes byte identity only; it does not authenticate the CLI, account, reviewer identity, scientific claims, or a same-user editor.

Statuses must distinguish `PASSED`, `REQUEST_CHANGES`, `BLOCKED`, `NOT_RUN`, `CANCELLED`, and `TIMED_OUT`. The overall runner result may report review execution, but remains `REVIEWED_WORKER_CANDIDATES_AWAITING_INTEGRATION` (or a blocked status). It never means merge-ready, release-approved, or scientifically valid.

## Security and scientific boundaries

- `FakeRuntime`, custom runtime adapters, and local fixtures prove parsing or coordinator control flow only. They cannot produce a successful provider review manifest or establish real provider execution or independent reviewer identity.
- A new run/session ID is necessary evidence of a fresh invocation, but real provider independence still requires provider E2E evidence.
- Codex read-only and Gemini sandbox requests do not prove effective OS isolation. Review runs against archived copies, and a changed copy invalidates the result; broader filesystem/process isolation remains unverified.
- Reviewer output is untrusted data. It cannot write canonical acceptance state or bypass the gate.
- No review verdict certifies scientific validity; `SOFTWARE_VALIDITY`, `NUMERICAL_VALIDITY`, and `SCIENTIFIC_VALIDITY` remain separate.

## Deferred P1 work

This increment intentionally leaves the following as P1 blockers: deterministic combination of non-overlapping worker diffs into a final integration candidate; rerunning checks on that exact candidate; ownership enforcement; automatic bounded fix/recheck/re-review rounds; durable restart/idempotency; DAG scheduling and centralized semaphores; and real Codex/Gemini E2E evidence. Until those are implemented and verified, the gate remains blocked.
