# P2 ODE Specialist Routing Implementation Plan

> **For agentic workers:** Required sub-skill: use `superpowers:executing-plans` to implement this plan task by task.

**Goal:** Route declared ODE tasks to a model-formulation specialist and a numerical analyst.

**Architecture:** Extend the router's closed domain set and deterministic role mapping. Keep scientific claim review conditional on claim-bearing domains/risk; update the portable skill reference and feature matrix without touching solvers or provider execution.

**Tech Stack:** Python 3.14, `unittest`, Markdown.

**Spec:** `docs/superpowers/specs/2026-11-04-p2-ode-specialist-routing-design.md`

## Files

- `tests/test_routing.py`: regression for ODE role selection, required evidence and portable role name.
- `scripts/route_task.py`: closed domain and role mapping.
- `SKILL.md`, `references/ROUTER.md`: portable specialist/routing contract.
- `docs/roadmap/FEATURE_MATRIX.md`, `docs/test-reports/p2-ode-specialist-routing-2026-11-04.md`: state and evidence.

## Tasks

- [x] Add one failing R1 ODE routing regression; run it and confirm the expected missing-domain failure.
- [x] Add the minimal `ode` mapping and profile task; 45 focused routing/evidence/work-item tests pass.
- [x] Update portable routing guidance and feature matrix; `validate_skill.py`, compile and diff checks pass.
- [x] Record final implementation commit `bf03202123c7c9a6bfe9315fd537424eae6f4d16`; open draft PR #50 against `codex/p4-release-governance`.
