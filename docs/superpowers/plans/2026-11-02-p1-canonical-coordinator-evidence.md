# P1 Canonical Coordinator Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Have the coordinator run user-declared deterministic checks against an immutable candidate snapshot and persist verifiable, versioned evidence without authorizing review, scientific validity, or release.

**Architecture:** Bind the task to a canonical SHA-256 at initialization and reject later task drift. Capture tracked plus non-ignored untracked regular files into an execution-specific validation snapshot; reject symlinks and unsupported entries. Run only typed `argv` specifications from the original task, with `shell=False`, bounded timeout, process containment, file-backed logs, and a coordinator-written atomic manifest. Require Python safe-path mode for unittest checks. Hash and revalidate the complete archived snapshot after execution so ignored additions and later snapshot tampering cannot be treated as unchanged evidence. The worktree gate recomputes and verifies check evidence against the exact task, policy, base, candidate tree, command, snapshot artifact, and log hashes; independent review remains a separate required stage.

**Tech Stack:** Python 3.11+ standard library, `dataclasses`, `hashlib`, `subprocess`, `unittest`, Git worktrees.

**Spec:** `docs/CODEX_MASTER_MISSION.md` §2.4 and P1 items 3–6/Gate P1; `docs/architecture/ADR-001-runtime-boundaries.md` contracts and review boundary; `docs/superpowers/plans/2026-11-02-p1-untrusted-evidence.md` fail-closed baseline.

## Global Constraints

- No merge to `main`, release, external installation, credential inspection, or real provider call.
- Test commands come only from the user task's typed `check_specs`, never worker text or mailbox; execute argument arrays with `shell=False`.
- A `unit_tests` check must use the Python unittest protocol with `-P` or `-I` before `-m unittest`, and report at least one executed test; a command that only prints `PASS`, shadows the unittest module, or discovers zero tests is not a pass.
- Persisted hashes establish byte integrity and candidate identity, not cryptographic authenticity against a same-user writer or scientific truth.
- Provider E2E, native reviewer/subagents, effective OS sandbox, POSIX native behavior on this Windows host, and scientific certification remain `NOT_RUN`/`UNVERIFIED`.
- Check evidence may establish only the checks actually run on the exact recorded candidate; software/independent/security/release review, GUI, IDL, and scientific obligations stay pending until separately verified.
- Each worker worktree receives separate check evidence; tests for one worker do not prove a combined integration candidate or another worker's branch.

## Review Focus

- Same `task_id` with changed request/check command: reject before execution by comparing the canonical task digest.
- Same-named untracked file with changed bytes or a tracked edit: candidate digest must change; symlink/special entries fail closed.
- Candidate-local `unittest/__main__.py` that prints a forged summary: reject the command unless Python safe-path mode is enabled.
- Check command exits 0 after printing `PASS` or running zero tests: `unit_tests` must fail because the unittest count is absent/zero.
- Snapshot writes, including ignored files, and later archive edits: fail the run or make the manifest invalid.
- Replayed or modified manifest, logs outside the evidence root, wrong base/task/candidate/argv, or a changed candidate: gate must reject the record.
- All configured deterministic checks pass but reviewer/scientific evidence is absent: gate remains `BLOCKED`, with `evidence_verified: false` and release not approved.

---

### Task 1: Define Task, Snapshot, and Evidence Contracts

**Files:**
- Create: `scripts/execution_evidence.py`
- Test: `tests/test_execution_evidence.py`
- Modify: `scripts/route_task.py`
- Test: `tests/test_routing.py`

**Interfaces:**
- `canonical_task_sha256(task: Mapping[str, Any]) -> str`
- Frozen `CheckSpec(check_id: str, argv: tuple[str, ...], cwd: str, timeout_seconds: float, protocol: str)`; accepted protocols are `exit_code` and `unittest`, and `unit_tests` requires `unittest` plus Python `-P`/`-I` before `-m unittest`.
- `validate_check_specs(task: Mapping[str, Any]) -> tuple[CheckSpec, ...]`; IDs must be unique and belong to `required_checks(task)`, cwd must be relative and contained, argv entries nonempty/NUL-free, timeout finite and positive.
- `candidate_tree_sha256(root: Path) -> str`; hash sorted Git-visible tracked/non-ignored-untracked paths, executable bit, and file bytes; reject symlinks, submodules, special files, path escape, and read errors.
- Frozen `SnapshotReference(source_tree_sha256: str, snapshot_tree_sha256: str, file_count: int, total_bytes: int, snapshot_path: Path)`; capture must prove the source stayed stable while copying.
- Frozen `EvidenceRecord` and strict schema-version-1 JSON encode/decode. Required fields bind task digest/revision, execution/check IDs, base commit, candidate digest before/after, resolved executable/hash, argv/cwd, OS/Python/environment allowlist, start/finish UTC, timeout, process status/exit code, unittest count, evidence-relative log paths and SHA-256 values.

- [ ] Add RED tests for canonical task hashing (request/check changes alter digest), check spec validation, untracked-content digest changes, tracked edits, and symlink/special-file refusal.
- [ ] Run `python -m unittest discover -s tests -p test_execution_evidence.py -v`; confirm the new contract tests fail because the module/types/functions are absent.
- [ ] Implement the contracts and strict field/path/status validation in `scripts/execution_evidence.py`; do not add authentication claims or trust a JSON `source` field.
- [ ] Run the focused evidence and routing suites; confirm exact digests and invalid inputs behave as specified.
- [ ] Commit `feat: define coordinator execution evidence contracts`.

### Task 2: Run Checks on Immutable Snapshots

**Files:**
- Create: `scripts/check_runner.py`
- Test: `tests/test_check_runner.py`
- Consume: `scripts/execution_evidence.py`, `scripts/process_containment.py`

**Interfaces:**
- `capture_snapshot(source: Path, destination: Path) -> SnapshotReference`; copy the candidate manifest from Task 1, verify source stability during capture, and retain an immutable snapshot under `.ssec-state/<task>/check-runs/<execution-id>/<worker-role>/snapshot`.
- `run_checks(task: Mapping[str, Any], state: Mapping[str, Any], worker: Mapping[str, str], metadata: Path, *, stop_event: threading.Event, deadline: float) -> CheckRunResult`; each worker candidate gets its own snapshot and records include its role/branch. Run configured checks sequentially in that snapshot, use `shell=False`, a sanitized recorded environment, process containment, exclusive file-backed logs, and bounded cancellation/timeout.
- Persist each final record only after containment quiesces and logs close/hash; atomically publish a schema-version-2 terminal manifest. Version-1 manifests are rejected and must be regenerated; interrupted/incomplete manifests cannot pass the gate.
- Compute pass status from process outcome and protocol. For `unit_tests`, require safe-path Python, exit code 0 and a positive `Ran N tests` summary; zero/missing count fails. Any snapshot drift, including ignored files, invalidates the record and withholds passing status. Persist and verify a separate full snapshot artifact hash.

- [ ] Add RED subprocess tests using a temporary Python repository: one actual unittest passes, one fails; `print("PASS")` and zero-test discovery fail as `unit_tests`; timeout/cancel, snapshot drift, malformed/partial manifest, and output hash tampering do not publish valid PASS evidence.
- [ ] Run `python -m unittest discover -s tests -p test_check_runner.py -v`; confirm expected failures before implementation.
- [ ] Implement snapshot capture, bounded check execution, containment, evidence-relative logs, hashes, and atomic terminal manifest.
- [ ] Run the focused check-runner suite; inspect the actual child-process exit results and log hashes.
- [ ] Commit `feat: execute deterministic checks into evidence manifests`.

### Task 3: Integrate Evidence and Preserve the Review Gate

**Files:**
- Modify: `scripts/worktree_coordinator.py`
- Modify: `scripts/development_runner.py`
- Test: `tests/test_development_worktrees.py`
- Modify: `references/WORKTREE_DEVELOPMENT.md`
- Modify: `docs/roadmap/FEATURE_MATRIX.md`

**Interfaces:**
- Initialization persists `task_sha256`; `execute()` refuses a same-ID task whose canonical digest differs.
- After every assigned implementation process succeeds, `execute()` calls `run_checks()` for each worker using only the original user task's `check_specs`; reports `CHECKS_VERIFIED_AWAITING_REVIEW`, `CHECKS_FAILED_NOT_REVIEWED`, or explicit `NOT_RUN` without promoting a worker result.
- `gate()` reads only coordinator check-run manifests under the task metadata directory, verifies schema, task/policy/base/role/branch/candidate digests, command/spec equality, evidence-root containment, current snapshot artifact hash, and current stdout/stderr hashes for every worker. It reports verified check IDs, missing checks, and policy-derived non-process obligations.
- Even when every deterministic check passes, review, scientific, security, or release obligations derived from the task and initialized policy remain pending; `status == "BLOCKED"`, `evidence_verified == false`, and `release_status == "NOT_APPROVED"`.

- [ ] Add RED integration tests for task drift rejection, valid checks bound to the initialized base and exact candidate, changed tracked/untracked bytes invalidating evidence, forged mailbox records having no effect, tampered/replayed manifests blocking, and valid check evidence without review remaining blocked.
- [ ] Run `python -m unittest discover -s tests -p test_development_worktrees.py -v`; confirm the new assertions fail against the current runner/gate.
- [ ] Integrate task digest, check execution, manifest verification and truthful report/gate states; preserve preview behavior and explicit provider cost acknowledgement.
- [ ] Run the focused worktree, evidence, and check-runner suites; update docs/matrix with limitations and `NOT_RUN` labels.
- [ ] Commit `feat: verify coordinator check evidence in worktree gate`.

### Task 4: Close the Increment

**Files:**
- Modify: `docs/superpowers/plans/2026-11-02-p1-canonical-coordinator-evidence.md`
- Create: `docs/test-reports/p1-canonical-coordinator-evidence-2026-11-02.md`

- [ ] Run full `python -m unittest discover -s tests -v`; report every failure, including known Windows symlink-fixture setup errors without skipping or weakening tests.
- [ ] Run `python scripts/validate_skill.py`, relevant CLI `--help`, and `git diff --check`.
- [ ] Record exact commit/SHA, commands/counts/results, open risks, provider/native-POSIX `NOT_RUN`, scientific boundary, and next P1 work.
- [ ] Obtain one independent scoped review of the full increment. Fix only blocking findings in one TDD pass; document non-blocking risks and retain truthful gate states.
- [ ] Commit `docs: record canonical coordinator evidence verification`.
