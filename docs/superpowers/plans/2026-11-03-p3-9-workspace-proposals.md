# P3.9 Workspace Proposal Review Implementation Plan

> **For agentic workers:** Use TDD for each task. Work in this feature worktree and preserve the P3.7/P3.8 commits and their draft PRs.

**Goal:** Let the scientific workspace GUI preview an agent-provided validated manifest and persist a digest-bound copy only after explicit human approval.

**Architecture:** Add a small pure-Python proposal module that reuses the safe workspace loader and performs canonical digest binding, full bounded diff generation, and create-only persistence. Add a modal GUI review using that API; the existing manifest remains untouched and the active view changes only after approval.

**Tech Stack:** Python standard library, existing workspace loader/viewer, Tkinter, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-03-p3-9-workspace-proposals.md`

## Global Constraints

- No arbitrary Python execution, shell commands, provider invocation, or new dependency.
- Candidate resources must pass the existing project-root containment and SHA-256 loader.
- Preview/reject do not write; approval is digest-bound and never overwrites the source manifest.
- User SIR data and scientific validity remain `NOT_RUN`/`NOT_ASSESSED`.

## Review Focus

- Proposal resource path escapes or digest failures must fail before display.
- Proposal bytes changing after preview must block approval.
- Active workspace changing after preview must block approval.
- Refusal or a no-op proposal must not create a project file.
- An existing digest target must never be overwritten.

### Task 1: Proposal validation, diff, and create-only persistence

**Files:** Create `scripts/scientific_workspace_proposals.py`; create `tests/test_scientific_workspace_proposals.py`.

**Interfaces:** `preview_workspace_proposal(project_root, active_workspace, proposal_relative_path) -> WorkspaceProposalPreview`; `approve_workspace_proposal(project_root, active_workspace, preview) -> ApprovedWorkspaceProposal`.

- [x] Write tests for validated preview and no writes, stale proposal/current manifest/resource, missing or invalid resource digests, oversized diff, create-only persistence, idempotent identical approval, and collision refusal.
- [x] Run focused tests and confirm expected failures.
- [x] Implement canonical JSON digest, unified diff capped at 64 KiB, revalidation on approval, and exclusive create of `.ssec-workspace-<sha256>.json`.
- [x] Run focused tests and verify source manifests/resources are unchanged.

### Task 2: Human-reviewed GUI proposal flow and evidence

**Files:** Modify `scripts/scientific_workspace_app.py`; modify `tests/test_scientific_workspace_app.py`; update `docs/roadmap/FEATURE_MATRIX.md`; create `docs/test-reports/p3-workspace-proposals-2026-11-03.md`.

**Interfaces:** Add `Revisar propuesta…`; show the full diff in a modal dialog; only `Aprobar y guardar` calls the create-only approval API. After success, load and display the approved copy.

- [x] Add GUI/API regressions for human approve/reject, stale previews, oversized valid manifests, canonical-copy collisions, and lossless Unicode review.
- [x] Run focused GUI tests, workspace test groups, validation CLI, and `git diff --check`.
- [x] Record Windows/Docker evidence, synthetic fixture limits, user SIR `NOT_RUN`, provider E2E `NOT_RUN`, and root replacement residual.
- [x] Commit the increment and open draft PR #31 based on P3.8; do not merge.
