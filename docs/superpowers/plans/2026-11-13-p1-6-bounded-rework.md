# P1.6 Bounded Rework Implementation Plan

> **For agentic workers:** implement each checked task with TDD; do not call a real provider.

**Goal:** Make one human-authorized fix cycle traceable from an exact `CHANGES_REQUESTED` review to fresh integration evidence.

**Architecture:** A versioned rework packet captures the current review findings and operator instruction. Existing worker, check, integration, and review APIs are reused; a fresh human decision remains required.

**Tech Stack:** Python CLI, existing Git worktrees, JSON evidence contracts, unittest.

**Spec:** `docs/superpowers/specs/2026-11-13-p1-6-bounded-rework-design.md`

## Tasks

- [x] Add a regression test that a `CHANGES_REQUESTED` integration cannot be reviewed again without a fresh rework integration.
- [ ] Add rework packet validation and fresh-tree binding; pass only validated findings to workers as untrusted context.
- [ ] Add one explicit CLI path for rework → checks → new integration → independent review; preserve human-only decision.
- [ ] Add deterministic local E2E coverage for correction, stale packets, failure/cancellation, and no false approval.
- [ ] Write a short phase report; run focused regression tests and one final P1 suite appropriate to runtime/time limits.

