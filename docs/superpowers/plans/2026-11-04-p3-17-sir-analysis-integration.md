# P3.17 — SIR analysis integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calculate SIR fit, local sensitivity, and observation residual records through existing `scientific_core` APIs and render them in one reproducible synthetic workspace.

**Architecture:** Add a constant-rate adapter and an orchestration wrapper in `scientific_core`; keep solver and optimizer implementations unchanged. Add optional typed model context references to simulation, fit, and sensitivity views so display units, parameters, solver metrics, and provenance can derive from a verified SIR contract; generate and render a deterministic demo.

**Tech Stack:** Python 3.11+, existing scientific_core RK4/fit/sensitivity/observation contracts, existing safe workspace loader, PySide6 with optional local Qt WebEngine, unittest.

**Spec:** `docs/superpowers/specs/2026-11-04-p3-17-sir-analysis-integration-design.md`

## Global Constraints

- No dependency installation, external model invocation, project-code execution, or new numerical algorithm.
- Only constant SIR rates are fit/sensitivity parameters in this increment; scheduled rates remain simulation-only.
- Synthetic observations are generated from the declared SIR fixture and must be labeled synthetic and exact.
- No uncertainty, practical identifiability, or scientific-validity claims.
- Resource SHA-256 verifies manifest byte equality only; it is not a scientific provenance certificate.

## Review Focus

- Rate override crosses into existing SIR RHS → test `to_ode_problem()` against `solve_sir_model` and reject nonconstant profiles.
- Fit bounds/perturbations permit negative physical rates → test rate-domain validation and bounded recovery.
- Model/dataset units disagree → test rejection before fitting.
- Context resource IDs/kinds are untrusted manifest input → test unknown, duplicate, and invalid-kind references.
- Missing or non-SIR context could produce false units → test labels remain not supplied unless validated SIR context resolves.

---

### Task 1: Expose constant-rate declarative SIR as a parameterized ODE problem

**Files:**
- Modify: `scripts/scientific_core.py`
- Test: `tests/test_scientific_core.py`

**Interfaces:**
- Produce `SirModelDefinition.to_ode_problem() -> OdeProblem` for constant beta/gamma only; returned parameters are `beta` and `gamma`, and the callable reuses the SIR contract's equation body while honoring exactly those overrides.
- Preserve `solve_sir_model()` behavior for constant and scheduled profiles.

- [x] Write failing tests that compare the adapter to `solve_sir_model`, show changing beta/gamma changes the trajectory, reject piecewise schedules, and reject negative overrides.
- [x] Run only those tests and verify the missing API / rejection behavior fails as expected.
- [x] Implement the adapter without duplicating or changing the SIR equations or RK4 solver.
- [x] Run `python -m unittest tests.test_scientific_core.SIRDeclarativeContractTests -v`.

### Task 2: Compose existing fit, sensitivity, and residual APIs for SIR

**Files:**
- Modify: `scripts/scientific_core.py`
- Test: `tests/test_scientific_core.py`

**Interfaces:**
- Produce frozen `SirParameterAnalysis(fit, sensitivity, evaluation, solution)` and `analyze_sir_parameters(definition, dataset, *, initial_parameters, bounds, perturbations, max_step, max_iterations=..., max_function_evaluations=...)`.
- Validate exact beta/gamma keys, nonnegative fit bounds, positive perturbations whose lower endpoints remain nonnegative, and SIR nonnegativity/population conservation for fit and sensitivity trajectories; call existing algorithms only.

- [x] Add a synthetic known-parameter fixture and failing tests for bounded parameter recovery, nonzero sensitivities, actual evaluated residuals, invariant checks, invalid rate bounds/perturbation endpoints, and unit mismatch rejection.
- [x] Run the new test methods and verify the bridge is absent.
- [x] Implement the result-composition wrapper with deterministic fit residuals.
- [x] Run the SIR analysis tests and existing P2 numerical tests.

### Task 3: Add typed workspace context references and unit derivation

**Files:**
- Modify: `scripts/scientific_workspace.py`
- Modify: `scripts/scientific_workspace_generation.py`
- Modify: `scripts/scientific_workspace_view.py`
- Test: `tests/test_scientific_workspace.py`
- Test: `tests/test_scientific_workspace_generation.py`
- Test: `tests/test_scientific_workspace_science_views.py`

**Interfaces:**
- Optional `config.context_refs: string[]` is accepted by `simulation_plot`, `fit_summary`, and `sensitivity_plot`; IDs must exist, be unique and distinct from the primary resource. Simulation accepts one `model_spec`; fit accepts at most one `model_spec` plus one `observations`; sensitivity accepts one `model_spec`.
- Primary `resource_refs` remains exactly one versioned result artifact.
- View models include primary and context resources as verified sources. A validated SIR v1 context supplies population, rate, and time units; all other contexts leave units unspecified. Simulation views also expose recorded parameter values and solver step metrics.

- [x] Add failing validator/proposal/view tests for accepted context links, wrong resource kinds, unresolved/duplicate/primary IDs, and unit derivation only from a validated SIR.
- [x] Run focused tests and confirm missing fields/derivation fail.
- [x] Update manifest and proposal validators, then derive display unit context from loaded safe-loader resources.
- [x] Run manifest, generation, and scientific view tests.

### Task 4: Generate and display a computed synthetic SIR workspace

**Files:**
- Create: `scripts/build_sir_analysis_demo.py`
- Create: `examples/sir_analysis_workspace_demo/README.md`
- Create: `examples/sir_analysis_workspace_demo/workspace.json` and result resources
- Test: `tests/test_scientific_sir_analysis_demo.py` (new)
- Test: `tests/test_scientific_workspace_qt_views.py`

**Interfaces:**
- Builder loads a constant-rate SIR JSON fixture, creates exact model-generated observations, calls `analyze_sir_parameters()`, and writes byte-stable schema v1 resources and SHA-256 manifest entries to a requested output directory.
- Demo workspace shows equations, parameters, simulation, observation table, fit, sensitivity, residuals, and explicitly unassessed uncertainty.

- [x] Add failing reproducibility and computed-result assertions, including `scientific_validity=NOT_ASSESSED` text in the demo documentation.
- [x] Run the new tests and observe failure before implementation.
- [x] Implement the bounded demo builder with no provider or project-code imports.
- [x] Add a Qt render test that compares visible parameter values/units and status with the computed records.
- [x] Run demo builder, safe loader, and the Qt focused tests; record Qt unavailable cases as skipped.

### Task 5: Document evidence and prepare a separate draft PR

**Files:**
- Modify: `references/SCIENCE_NUMERICS.md`
- Modify: `references/SCIENTIFIC_WORKSPACES.md`
- Modify: `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-17-sir-analysis-integration-2026-11-04.md`

- [ ] Document the constant-rate limit, model-derived units, linked-resource semantics, and scientific non-claims.
- [ ] Run focused regression, `python -m py_compile`, template/digest checks, and `git diff --check`; do not repeat the full suite.
- [ ] Record real SIR, real observations, and Linux Qt as `NOT_RUN`; create a draft PR stacked on P3.16 without merging.
