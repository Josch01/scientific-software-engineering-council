# P1.3 — Deterministic integration candidate

## Intent

Turn independently checked and reviewed worker worktrees into a reproducible, disposable candidate tree. The purpose is to make multiworker changes inspectable together and run the declared deterministic checks against the combined result. A successful build means only `INTEGRATED_CANDIDATE_CHECKED_AWAITING_REVIEW`; it does not mean accepted or releasable.

## Current state and why this is needed

`development_runner.execute()` checks and reviews each worker snapshot separately. `worktree_coordinator.gate()` verifies worker checks and exact path overlap, then stays `BLOCKED`. It has no enforced per-role ownership, no combined candidate, and no rechecks for interactions between workers. The task contract in `docs/CODEX_MASTER_MISSION.md` requires a reviewable integration gate and forbids inferring combined validity from separate worker results.

## Goals

- Bind each expected implementation role to a typed task contract containing role, reason, risk, inputs, outputs, dependencies, file ownership, tests, required reviewers, and acceptance criteria.
- Validate file ownership before any integration work. Reject path traversal, absolute paths, ambiguous wildcard semantics, overlapping ownership, and outputs outside owned paths.
- Require the current worker tree to match its passing check manifest and each required reviewer manifest to validate against that same tree and check manifest.
- Build a new, uncommitted Git worktree from the initialized base commit. Apply only declared worker output paths in stable role/path order. Never change the source checkout or worker worktrees.
- Block exact-path, file/ancestor, and case-folded path collisions before copying files.
- Run the task's declared deterministic checks against the combined worktree. Persist a schema-versioned, atomic integration manifest that records all input manifest hashes, worker tree hashes, path operations, candidate tree hash, and integrated check manifest identity.
- Keep the canonical release gate `BLOCKED` until the integrated candidate receives an independent review and the remaining P1 acceptance obligations are satisfied.

## Non-goals

- No automatic commit, merge, push, release, or source/worker branch mutation.
- No claim that provider output, account identity, reviewer independence, sandbox behavior, or scientific validity is authenticated by local hashes.
- No fix loop or final acceptance decision in this increment; those remain later P1 work.
- No dependency scheduling in this increment. Work item dependencies must be empty and the plan must fail closed if nonempty dependencies are requested; runtime DAG execution remains pending P1.
- No paid Codex/Gemini E2E call. Tests use real Git worktrees and process checks for software contracts; they do not substitute for provider E2E.

## Approaches considered

1. **Coordinator-owned path overlay in a disposable worktree — chosen.** Validate ownership and all source evidence, compute a deterministic file-operation set, then copy only those files over the pinned base. It makes deletion, additions, exact conflicts, ancestor conflicts, and Windows case collisions explicit. The source tree stays unchanged and no commits are created.
2. **Git merge/cherry-pick on a temporary branch.** This delegates conflict behavior to Git and is compact, but worker branches are uncommitted worktrees and may contain untracked outputs. Merge order and conflict resolution would become part of the result, and a branch operation is harder to inspect and safely retry.
3. **Keep worker manifests as the final result without assembling files.** This matches current behavior but cannot reveal cross-worker conflicts or integration-only test failures, so it does not meet P1's integration requirement.

The owner selected approach 1 under the existing project instruction to work autonomously. Keep the integration worktree and evidence as a separate artifact; never promote it to source automatically.

## Data contract proposal

Add `work_items` to a task packet as an exact list with one entry per implementation role derived by `choose_roles()`. The list must match that derived role set exactly; it cannot invent roles or override the router's authority. Each entry has `id`, `role`, `reason`, `risk`, `inputs`, `outputs`, `dependencies`, `file_ownership`, `tests`, `required_reviewers`, and `acceptance_criteria`. IDs and paths use stable, portable spellings. Paths are repository-relative POSIX paths. A directory scope is explicitly written with a trailing slash; no glob expansion is used. `outputs` must be covered by `file_ownership`, and every actual changed path must be covered by both. This increment accepts only empty `dependencies` because no runtime DAG scheduler exists yet.

## Integration evidence and lifecycle

An explicit worker execution ID selects reviewer artifacts under `dev-logs/<execution_id>/reviews/<worker_role>/<reviewer_role>/manifest.json`. The integrator also discovers and validates per-role check manifests from `check-runs/`; it does not trust a caller-supplied report or mailbox event. Each manifest must bind the task digest, task revision, base commit, worker role, branch, current candidate tree hash, and the expected check/reviewer role. All roles must be present with the required outcomes before the builder creates a candidate.

Each integration attempt receives a fresh opaque ID. Its candidate worktree is created from `base_commit` on a temporary SSEC integration branch. The builder applies changed files, computes the combined tree hash, and calls the existing real `run_checks()` against that worktree using an integration identity. The manifest is atomically published for both passed and failed terminal checks. Failed attempts remain forensic artifacts. A retry gets a new ID and a new worktree; it never overwrites evidence.

`gate()` reports the latest validated integration manifest and its checks for visibility but remains `BLOCKED` with an explicit missing integrated-review blocker. No worker check or review is transferred to the integrated tree.

## Acceptance tests

- Compose disjoint edits, additions, deletions, and executable-mode changes deterministically; verify source and worker worktrees remain unchanged.
- Reject missing, failed, stale, tampered, mismatched, and incomplete check/review manifests; reject candidate drift after evidence creation.
- Reject changed paths outside owned/output scopes and overlapping ownership declarations.
- Reject exact, file/ancestor, and case-insensitive path collisions before candidate creation.
- Verify checks run on the combined candidate and an integration-only test failure yields a failed integration manifest, even when worker checks passed.
- Verify post-check candidate mutation invalidates integration evidence; failed manifest persistence never yields a passed result.
- Verify retries use a distinct integration ID and worktree, while `gate()` remains blocked pending independent review.

## Remaining decisions for implementation

- Reuse `check_runner.run_checks()` with a synthetic `integration_candidate` identity only for check execution; add separate integration validation rather than pretending this identity is an initialized worker.
- Build path operations from Git-visible candidate changes and reject symlinks, junctions, reparse points, special files, and binary data unless the existing tree contract explicitly supports them.
- Preserve testability without counting fixture manifests or FakeRuntime output as real provider evidence. The unit suite verifies validator behavior; real provider E2E remains `NOT_RUN` unless separately authorized and available.
