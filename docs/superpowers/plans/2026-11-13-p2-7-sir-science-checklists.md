# P2.7 SIR Science Checklists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded, role-specific SIR audit prompts to existing scientific profiles and the portable SSEC skill.

**Architecture:** `prepare_agents.make_files` detects explicit SIR/SEIR/compartmental epidemiology terms and passes task context to the existing profile renderer. Only selected scientific roles receive their checklist. The portable skill contains the same distinctions for native Codex/Gemini use.

**Tech Stack:** Python standard library, `unittest`, Markdown.

**Spec:** `docs/superpowers/specs/2026-11-13-p2-7-sir-science-checklists.md`

## Global Constraints

- Do not add algorithms, models, solvers, roles, router schema, or evidence claims.
- Only add SIR-specific text to matching scientific role profiles; preserve non-SIR output.
- Treat checklists as prompts, not evidence or scientific certification.
- Missing execution inputs remain `NOT_RUN`; unsupported scientific claims remain `NOT_ASSESSED`.
- Do not call AGY/Codex/Gemini providers or use user thesis data.

## Review Focus

- Lowercase or accented/unaccented SIR task wording must be detected case-insensitively.
- Ordinary scientific/software requests must not receive the SIR checklist.
- The generated checklist must keep RMSE, solver error, identifiability, and scientific validity distinct.
- Modified SIR variants must not be assumed to conserve `S+I+R`.
- Codex, Gemini, and AGY profile modes must receive equivalent role-specific content.

---

### Task 1: Pin conditional role checklist behavior

**Files:** `tests/test_provider_modes.py`

- [x] Add a failing test that explicit SIR tasks inject the correct checklists into selected scientific profiles across existing provider modes.
- [x] Add a failing test that non-SIR tasks omit SIR-specific profile content and preserve existing role routing.
- [x] Add a failing content check for the portable checklist and its `NOT_RUN`/`NOT_ASSESSED` boundary.
- [x] Run the focused tests and record the expected baseline failure.

### Task 2: Implement the minimal profile and skill update

**Files:** `scripts/prepare_agents.py`, `SKILL.md`, `docs/roadmap/FEATURE_MATRIX.md`

- [x] Add explicit SIR-task detection and the four role checklists to existing generated profiles.
- [x] Add the matching concise instructions to the portable skill; do not change router roles or schemas.
- [x] Add the P2.7 row and link to its test report in the feature matrix.

### Task 3: Verify and report

**Files:** `docs/test-reports/p2-7-sir-science-checklists-2026-11-13.md`

- [x] Re-run the focused profile tests, `python scripts/validate_skill.py`, `py_compile`, and `git diff --check`; save short PASS/FAIL output.
- [x] Run one blind follow-up pressure scenario against the updated skill; record any remaining gaps.
- [x] Record that SIR-specific calculations and provider execution remain `NOT_RUN`; commit on a separate P2 branch and open a draft PR without merging.
