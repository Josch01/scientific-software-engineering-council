# P2.6 Explicit Scientific Specialists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route scientific tasks to explicit domain specialists and require scientific validation evidence for scientific claims regardless of risk tier.

**Architecture:** Extend the deterministic router's domain-to-role mapping and check derivation. Add the roles to the existing native profile catalog and portable skill; do not add an executor, algorithm, or dependency.

**Tech Stack:** Python 3.11+ standard library, `unittest`, Markdown skill/reference documentation.

**Spec:** `docs/superpowers/specs/2026-11-13-p2-explicit-scientific-specialists.md`

## Global Constraints

- Select only domain-required specialists; no provider is invoked by routing or profile generation.
- Never equate software tests or numerical output with scientific validity.
- R2/R3 security and independent-review evidence remains additive and unchanged.
- Preserve Codex/Gemini/AGY profile behavior and schema compatibility.

## Review Focus

- Identifiability domain selects its specialist plus existing numerical needs; test R1.
- Dynamics domain selects only its domain expert in addition to existing numerical needs; test no identifiability/algebra role leakage.
- Differential algebra and symbolic map to the same exact specialist; test both domains.
- A low-risk scientific claim still requires `scientific_validation`; test R1.
- General GUI/CLI tasks receive no scientific specialist or scientific-validation obligation; test existing baseline behavior.

---

### Task 1: Deterministic routing and evidence obligations

**Files:** `scripts/route_task.py`, `tests/test_routing.py`

**Interfaces:** `route(task)` continues to return the version-1 plan; the implementation/domain role list gains only experts selected by the task domains.

- [x] Add tests for the domain-to-specialist mapping and R1 scientific-validation obligation.
- [x] Run `python -m unittest tests.test_routing.RoutingTests.test_science_claim_domains_route_specific_experts_and_validation_at_r1 -q`; it failed because the new specialist roles were absent.
- [x] Implement the minimal mapping and validation rule without changing the plan schema.
- [x] Run `python -m unittest tests.test_routing -q`; 7 tests pass.

### Task 2: Portable role profiles and documentation

**Files:** `scripts/prepare_agents.py`, `tests/test_provider_modes.py`, `SKILL.md`, `docs/roadmap/FEATURE_MATRIX.md`, `docs/test-reports/p2-6-explicit-scientific-specialists-2026-11-13.md`

**Interfaces:** `make_files(task, mode, config)` creates the usual provider-native profile and task packet for each new role; router remains the only source of task-specific selection.

- [x] Add a test that routed expert roles have provider-native profiles and task packets for Codex, Gemini, and AGY.
- [x] Run the test and confirm it failed because the router emitted none of the requested domain specialists.
- [x] Add bounded role remits in `ROLE_TASKS` and the portable skill; document evidence limits and update the phase matrix/report.
- [x] Run the focused routing/profile tests and structural skill validator; PASS (17 tests, 1 Windows symlink fixture skipped).

### Task 3: Verification and delivery

**Files:** changed P2.6 files only.

- [ ] Run `python -m unittest tests.test_routing tests.test_provider_modes -q` and the repository's available CI suite; report complete, failed, or blocked status.
- [ ] Run `python scripts/validate_skill.py`, `python -m py_compile scripts/route_task.py scripts/prepare_agents.py`, and `git diff --check`.
- [ ] Commit the increment on its P2 branch and open a separate draft PR stacked on P1.5; do not merge or release.
