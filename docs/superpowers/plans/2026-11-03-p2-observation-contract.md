# P2.4 observation/residual bridge implementation plan

> **For agentic workers:** Use task checkboxes and keep this increment isolated from P2.3.

**Goal:** Connect a versioned, provenance-carrying observation contract to RK4 simulation and bounded least-squares residuals.

**Architecture:** Add immutable dataset/evaluation records and bounded validation in `scripts/scientific_core.py`. Integrate to exact observation times by splitting the existing RK4 interval; do not interpolate or assume a particular model. Keep parameterized model construction in the caller.

**Tech stack:** Python standard library and `unittest`; no installs.

**Spec:** `docs/superpowers/specs/2026-11-03-p2-observation-contract-design.md`.

## Global constraints

- No SIR equations, datasets, or domain-specific claims.
- Reject mismatched units/names and bad provenance fields; a hash is content identity, not authentication.
- Enforce payload and integration budgets before execution; no partial result on failure.
- Keep numerical/scientific validity separate and document the fixed-step RK4 limits.

## Review focus

- Canonical digest is deterministic and verifies a supplied digest.
- Sparse rows and variable ordering yield deterministic, auditable residual order.
- Irregular observation times are integrated exactly without interpolation.
- Work-budget failures occur before any RHS callback.
- Unit/state/time mismatches fail before integration.
- The returned residual vector composes correctly with `fit_least_squares`.
- The content digest represents variable/residual order; validated datasets cannot be directly instantiated or mutated through caller-owned inputs.
- Residuals are raw and unweighted; the API does not imply a meaningful joint objective across unlike units.

## Task 1: Observation contract and RK4 residual adapter

- [x] Add failing tests for schema validation, stable content digest, sparse values, units, and deterministic residual order.
- [x] Add a failing irregular-time integration test with synthetic known dynamics.
- [x] Add preflight budget, no-partial-result, and optimizer-composition tests.
- [x] Implement immutable `ObservationDataset` and `ObservationEvaluation` contracts plus bounded segmented RK4 evaluation.
- [x] Run focused tests on Windows and Docker/Linux; run `py_compile` and `git diff --check`.
- [ ] Update the feature matrix and create a concise evidence report with limitations.
- [x] Obtain one independent read-only review, fix any critical/important findings, and rerun focused tests.
- [ ] Wait for the PR branch CI matrix and record its 3.11/3.12 Windows/Linux result.
- [ ] Commit, push, and open a separate draft PR stacked on P2.3; do not merge.
