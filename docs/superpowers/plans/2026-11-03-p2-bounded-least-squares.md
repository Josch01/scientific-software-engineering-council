# P2.3 bounded least-squares Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a bounded, dependency-free local least-squares optimizer for caller-supplied residual functions.

**Architecture:** Keep the fitting result and algorithm in `scripts/scientific_core.py`, alongside the RK4 and sensitivity APIs. Validate and bound all callback work, optimize initial-centered, locally scaled bounded coordinates with damped finite-difference Gauss–Newton, and report status without scientific-validity claims.

**Tech Stack:** Python standard library only; `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-03-p2-bounded-least-squares-design.md`.

## Global Constraints

- Do not install or add external dependencies.
- Keep every parameter inside explicit finite bounds and enforce function-evaluation/iteration limits.
- No SIR-specific equations, fitting data, or claims of identifiability or scientific validity.
- Preserve the existing RK4 and sensitivity APIs.

## Review Focus

- Parameters at active bounds use a feasible one-sided finite difference and cannot step outside the declared box.
- Different Jacobian column magnitudes cannot hide a valid parameter update; the initial values survive wide-bound coordinate transforms exactly.
- A small initial parameter with a large residual and wide bounds receives a representable finite-difference step.
- Rank-deficient or flat residuals never yield fabricated parameter certainty or false convergence claims.
- Very small residuals do not stop fitting just because their squared floating-point cost underflows.
- Callback dimension changes, exceptions, and non-finite values fail clearly.
- Evaluation-budget exhaustion returns a non-converged status with the best fully evaluated point.
- Large parameter/residual dimensions are rejected before allocating an oversized Jacobian.

---

### Task 1: Bounded local least-squares API

**Files:**
- Modify: `scripts/scientific_core.py`
- Create: `tests/test_scientific_optimization.py`
- Update: `docs/test-reports/p2-bounded-least-squares-2026-11-03.md`

**Interfaces:**
- Consumes: `Mapping`, finite-vector validation conventions, and the existing immutable numerical result style in `scripts/scientific_core.py`.
- Produces: `fit_least_squares(residual_function, initial_parameters, bounds, *, max_iterations=100, max_function_evaluations=10000, finite_difference_fraction=1e-4, gradient_tolerance=1e-8, cost_tolerance=1e-10, step_tolerance=1e-8) -> LeastSquaresFit`.
- `LeastSquaresFit` exposes ordered parameter names, immutable initial/final parameters and bounds, final residuals/cost/status, iterations, accepted steps, function evaluations, and `to_dict()`.

- [x] Write failing analytic recovery test for a two-parameter overdetermined linear residual system and verify it fails before the API exists.
- [x] Add tests for bounds, an active-bound optimum, immutable serialization, non-finite/changed residual vectors, callback exceptions, invalid inputs, function-evaluation exhaustion, mismatched Jacobian column scales, exact initial-value preservation, and large-residual finite-difference cancellation.
- [x] Implement bounded finite-difference Levenberg–Marquardt with partial-pivot linear solve, initial-centered locally scaled coordinates, explicit limits, and truthful termination statuses.
- [x] Run `python -m unittest tests.test_scientific_optimization tests.test_scientific_sensitivity tests.test_scientific_core -q` on Windows and Docker/Linux.
- [ ] Run the repository CI matrix and record exact results, limitations, and the P2.4 next step in the evidence report.
- [ ] Commit and push this increment to its own draft PR; do not merge.
