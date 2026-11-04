# P4.5 — Security and Release Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the contract-required threat model and release checklist, with structural validation and claims limited to existing evidence.

**Architecture:** Keep governance in standalone Markdown documents, link them from the existing release policy, and require both paths in `scripts/validate_skill.py`.

**Tech Stack:** Markdown, Python standard library, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-04-p4-release-governance-design.md` and `docs/CODEX_MASTER_MISSION.md`.

## Global Constraints

- No external dependencies or tools are installed.
- No release, tag, merge to `main`, license, or provider invocation is performed.
- Missing evidence stays `NOT_RUN`, `UNVERIFIED`, or `BLOCKED`.
- A software test does not establish mathematical or scientific validity.

## Review Focus

- Missing governance files must fail structural validation: `test_release_governance_documents_are_mandatory`.
- Document claims must map to existing evidence or be marked as a gap: `git diff` and reviewer check against reports.
- Release remains blocked without owner license decision and required evidence: checklist states current blockers.

---

### Task 1: Add and validate governance documents

**Files:**
- Create: `docs/security/THREAT_MODEL.md`
- Create: `docs/release/RELEASE_CANDIDATE_CHECKLIST.md`
- Modify: `docs/roadmap/FEATURE_MATRIX.md`
- Modify: `references/RELEASE_POLICY.md`
- Modify: `scripts/validate_skill.py`
- Test: `tests/test_structure.py`

**Interfaces:**
- Consumes: existing threat evidence in `docs/test-reports/p4-adversarial-self-review-2026-11-04.md`; release requirements in `docs/CODEX_MASTER_MISSION.md`.
- Produces: `validate()` rejects the package when either governance document is absent.

- [x] Add `test_release_governance_documents_are_mandatory`; it failed before implementation because the threat model path was not mandatory.
- [x] Add the two required paths to `MANDATORY`; write the threat model and checklist with evidence-linked limits.
- [x] Link both documents from `references/RELEASE_POLICY.md`.
- [x] Run `python scripts/validate_skill.py`, `python -m unittest tests.test_structure -v` (2/2), `python -m compileall -q scripts tests`, and `git diff --check` — all pass.
- [x] Commit the focused increment.
