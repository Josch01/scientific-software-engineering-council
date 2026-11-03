# P1.3 Deterministic Integration Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a deterministic, uncommitted integration worktree from workers whose ownership, check, and review evidence validate, then rerun task checks against the combined tree.

**Architecture:** Add typed per-role work items and a focused integration builder. The builder validates persisted evidence, computes non-overlapping file operations, overlays them onto an initialized-base Git worktree, and calls `run_checks()` with an integration identity. The coordinator records the resulting manifest but always leaves the release gate blocked pending independent review of the integrated candidate.

**Tech Stack:** Python standard library, Git worktrees, existing `check_runner`, `review_evidence`, `execution_evidence`, `worktree_coordinator`, and `unittest` suite. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-02-p1-deterministic-integration-design.md`

## Global Constraints

- Preserve Python 3.11/3.12 support on Windows and Linux.
- Do not install external packages or invoke paid providers.
- Do not commit or merge the integration worktree; do not alter source or worker worktrees.
- Reject unsafe paths, symlinks, junctions/reparse points, special files, and ambiguous path collisions.
- Do not treat local hashes as provider authentication, OS sandboxing, or scientific validation.
- `dependencies` must be empty until a real DAG scheduler enforces them.
- Integration checks do not authorize acceptance: `gate()` remains `BLOCKED` pending integrated review and remaining P1 criteria.

## Review Focus

- Absolute, drive-qualified, traversal, NUL, wildcard, and malformed output scopes must be rejected by work-item validation.
- Exact, ancestor, and case-folded collisions must block before a candidate worktree is created.
- Stale, failed, incomplete, tampered, cross-role, or wrong-base worker/reviewer evidence must not produce an integration candidate.
- Links/reparse points, special files, ignored files, and binary output must not escape or silently change the overlay contract.
- Integration-only failures, post-check mutation, cancellation, and manifest-storage failure must never produce a passed integration result.

---

### Task 1: Validate role-owned work items

**Files:**

- Create: `scripts/work_items.py`
- Create: `tests/test_work_items.py`
- Modify: `scripts/worktree_coordinator.py`
- Modify: `tests/test_development_worktrees.py`

**Interfaces:**

- Produce `validate_work_items(task, worker_roles, required_reviewers, check_ids) -> dict[str, WorkItem]`.
- `worker_roles` comes from the existing `choose_roles()` result; `work_items` must match that role set exactly and cannot override role selection.
- Each item has exactly `id`, `role`, `reason`, `risk`, `inputs`, `outputs`, `dependencies`, `file_ownership`, `tests`, `required_reviewers`, and `acceptance_criteria`.
- Paths use repository-relative POSIX syntax. A trailing slash declares a directory prefix; no globs. Outputs must be covered by ownership. Dependencies are required to be an empty list in this increment.
- Older packets without `work_items` remain loadable, but integration must return a clear blocked result.

- [x] **Step 1: Add failing schema and compatibility tests**

Add tests for exact role-set matching, duplicate IDs, strict fields/types, required reviewer/check references, safe paths, output-under-ownership, overlapping scopes, unsupported dependencies, and legacy packets that remain loadable but cannot integrate.

- [x] **Step 2: Run tests and confirm RED**

Run: `python -m unittest -v tests.test_work_items`

Expected: FAIL because the validator and its contract type do not exist.

- [x] **Step 3: Implement validation**

Implement a frozen `WorkItem` data type and one validator in `scripts/work_items.py`. Normalize paths once; reject absolute/drive paths, `..`, `.`, empty components, NUL, wildcard metacharacters, and cross-role ownership collisions. Call validation from `plan()` and `_validate_state_packet()` whenever work items are present.

- [x] **Step 4: Run tests and confirm GREEN**

Run: `python -m unittest -v tests.test_work_items tests.test_development_worktrees`

Expected: all pass; existing packets without work items remain valid for prior workflows.

- [x] **Step 5: Commit**

Commit as `feat: add role-owned work item contracts`.

### Task 2: Validate evidence and compose the candidate

**Files:**

- Create: `scripts/integration_candidate.py`
- Create: `tests/test_integration_candidate.py`
- Modify: `scripts/development_runner.py`
- Modify: `tests/test_development_worktrees.py`

**Interfaces:**

- Add `run_id` to launched `execute()` reports; it identifies the persisted review tree under `dev-logs/<run_id>/reviews/...`.
- Produce `build_integration_candidate(project, task_id, execution_id) -> IntegrationResult`.
- `IntegrationResult` carries the integration ID, terminal status, candidate worktree path, integration manifest path, check manifest path, and blockers. It never carries an acceptance/release decision.

- [x] **Step 1: Add failing evidence-selection and conflict tests**

Use real temporary Git repositories and worktrees. Assert that missing, failed, stale, tampered, mismatched-role/base, or incomplete check/review evidence is rejected; verify passed reviewer records point to the same current worker tree and check manifest. Add exact, ancestor, case-folded, ownership, output-scope, symlink, and special-file rejection cases.

- [x] **Step 2: Run tests and confirm RED**

Run: `python -m unittest -v tests.test_integration_candidate`

Expected: FAIL because no integration builder exists.

- [x] **Step 3: Implement persisted-evidence validation and stable operations**

Discover manifests from metadata, validate each with existing readers, bind them to the task/base/current worker hash, and require every expected reviewer. Derive Git-visible tracked changes, deletions, and nonignored untracked files; validate them against owned outputs. Block exact, ancestor, and case-folded collisions before creating a candidate.

- [x] **Step 4: Add deterministic overlay and atomic manifest**

Create a fresh integration branch/worktree at the initialized `base_commit`. Apply only sorted, validated operations; preserve deletions and executable mode; stage the disposable tree without committing. Persist a schema-versioned manifest atomically with input manifest hashes, worker hashes, role/path operations, base, candidate hash, and unique integration ID. A retry always gets a fresh ID and worktree.

- [x] **Step 5: Run tests and confirm GREEN**

Run: `python -m unittest -v tests.test_integration_candidate`

Expected: real Git worktrees remain unchanged, repeated overlays have equal tree hashes, and conflicts/evidence drift block.

- [x] **Step 6: Commit**

Committed as `618c32c feat: compose an evidence-bound integration candidate`.

### Task 3: Recheck the combined worktree and preserve the blocked gate

**Files:**

- Modify: `scripts/integration_candidate.py`
- Modify: `scripts/worktree_coordinator.py`
- Modify: `tests/test_integration_candidate.py`
- Modify: `tests/test_development_worktrees.py`

**Interfaces:**

- Run existing task check specs on the integration worktree with synthetic role `integration_candidate`, its own branch, and a one-worker in-memory check identity. Do not add that role to persisted implementation workers.
- `gate()` reports the latest validated integration result and its check status, but always includes a blocker for missing independent integrated review.

- [x] **Step 1: Add failing combined-check tests**

Assert an integration-only check failure produces `FAILED`; post-check candidate drift invalidates the evidence; persistence failure cannot yield `PASSED`; a passing integrated check still leaves `gate()` blocked.

- [x] **Step 2: Run tests and confirm RED**

Run: `python -m unittest -v tests.test_integration_candidate tests.test_development_worktrees`

Expected: FAIL because integrated checks and gate reporting are not connected.

- [x] **Step 3: Implement integrated checks and evidence validation**

Call the real `run_checks()` against the combined Git worktree and verify its manifest/log/snapshot identities. Validate persisted integration manifests and current tree hash when `gate()` reports them. Never promote worker-only check/review evidence to the combined candidate.

- [x] **Step 4: Run tests and confirm GREEN**

Run: `python -m unittest -v tests.test_integration_candidate tests.test_development_worktrees`

Expected: an integration-specific failure cannot pass through worker evidence, and the release gate is still `BLOCKED`.

- [x] **Step 5: Commit**

Commit as `feat: recheck integrated candidates without accepting them`.

### Task 4: Verify, document, and prepare a separate draft PR

**Files:**

- Create: `docs/test-reports/p1-deterministic-integration-2026-11-03.md`
- Modify: `docs/test-reports/P1 acceptance matrix` (only if one exists)

- [x] **Step 1: Run focused integration regressions on Windows and Docker/Linux**

Run the five regressions recorded in `docs/test-reports/p1-deterministic-integration-2026-11-03.md` in both environments. Record exact counts and limits.

- [ ] **Step 2: Run the full suite and structural checks**

Run: `python -m unittest discover -v -s tests`; `python -m compileall -q scripts tests`; `git diff --check`; validate the skill from its canonical root name. Do not add dependencies.

- [x] **Step 3: Record evidence and limits**

Document commits, tests, defects, architectural decisions, `NOT_RUN` provider E2E, unverified provider/authentication boundaries, and remaining P1 scheduler/recovery/fix-loop gates. State that scientific validity is not assessed.

- [x] **Step 4: Commit the report**

Commit as `docs: record deterministic integration verification`.

- [x] **Step 5: Push the P1.3 branch and create a separate draft PR**

Base it on `codex/p1-windows-review-mode`; do not merge to `main` or release.

## Plan Self-Review

- Every design goal is assigned to Tasks 1–3; the P1 non-goals remain explicitly pending.
- Every subsystem has a test-first, RED, implementation, GREEN, and commit cycle.
- Integration checks use the existing check-run interface but a separate identity, and the canonical gate never changes to acceptance.
- The five review-focus input classes are pinned by tests in Tasks 1–3.
- This plan does not claim provider E2E, authentication, sandboxing, or scientific validity.
