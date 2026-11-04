# P4.1 — Portable Python Syntax Gate Implementation Plan

> **For agentic workers:** Use the existing repository workflow and verify each step locally before committing.

**Goal:** Make the existing Windows/Linux CI compile every Python source and test file without adding a dependency.

**Architecture:** Add one standard-library `compileall` command to the current validation job. Keep lint, type, secret, dependency, and vulnerability tools outside this increment and report them as not run.

**Tech Stack:** GitHub Actions, Python `compileall`, existing unittest workflow.

**Spec:** `docs/CODEX_MASTER_MISSION.md`, P4 item 1.

## Global Constraints

- Do not install or add external software.
- Keep the existing Windows/Linux and Python 3.11/3.12 CI matrix.
- Do not change runtime code or scientific claims.

## Review Focus

- Every tracked Python script and test is included in the syntax check.
- A syntax failure returns nonzero and fails the workflow.
- Existing workflow order and matrix remain intact.

### Task 1: Add the syntax gate

**Files:**
- Modify: `.github/workflows/validate.yml`
- Create: `docs/test-reports/p4-portable-syntax-gate-2026-11-04.md`

**Interfaces:**
- Consumes the checked-out `scripts/` and `tests/` trees.
- Produces a failing CI step if Python compilation fails.

- [x] Run `python -m compileall -q scripts tests` locally.
- [x] Add that exact command to the existing CI validation job before unit tests.
- [x] Verify the workflow diff and rerun the command locally.
- [x] Record results and remaining P4 tools as `NOT_RUN`.
- [ ] Commit the increment and open a draft PR targeting P3.18.
