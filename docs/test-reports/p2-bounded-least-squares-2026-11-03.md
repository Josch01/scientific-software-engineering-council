# P2.3 bounded least-squares evidence

**State:** local verification complete; branch CI pending. This is an experimental numerical utility, not a scientific result.

## Implemented

`fit_least_squares` in `scripts/scientific_core.py` performs bounded, local Levenberg–Marquardt/Gauss–Newton fitting against a caller-supplied residual callback. It uses locally scaled coordinates centered exactly on the initial values, normalizes Jacobian columns for the linear solve, and maps steps back through those scales. Each coordinate scale is `max(abs(initial_value), min(bound_width, 1.0))`; the physical finite-difference step is `finite_difference_fraction * bound_width`, clipped to feasible distance. The gradient tolerance is evaluated after normalization by the initial residual scale and column scales, so it is a relative stopping rule rather than an absolute residual threshold. The callback must return a deterministic, fixed-length finite residual vector. Parameter count, Jacobian size, iteration count, and callback evaluations have explicit limits. The immutable result serializes as schema v1 and records the termination status, work counts, bounds, residuals, and cost-underflow flag.

The API composes with the existing fixed-step RK4 solver. A synthetic decay example recovers its generating rate, but this is only a software/numerical integration check.

## Verification performed

| Environment | Command | Result |
|---|---|---|
| Windows, local Python 3.14.0 | `python -m unittest tests.test_scientific_optimization tests.test_scientific_sensitivity tests.test_scientific_core -q` | PASS, 39 tests |
| Docker/Linux, `python:3.14.0-bookworm` | Same unittest command | PASS, 39 tests |
| Windows, local Python | `python -m py_compile scripts/scientific_core.py tests/test_scientific_optimization.py` | PASS |
| Windows, local Python | `git diff --check` | PASS |

Focused cases cover overdetermined analytic recovery, a constrained optimum, nonlinear recovery from a bound, small and underflowing residual scales, mismatched Jacobian column magnitudes, exact initial-value preservation under wide bounds, finite-difference cancellation at wide bounds, synthetic RK4 composition, immutable JSON output, input/callback failures, dimension changes, work limits, and Jacobian allocation bounds.

## Interpretation and limits

- `CONVERGED` means only that this local solver met its implemented stopping rule. It does not establish identifiability, uniqueness, global optimality, parameter certainty, or scientific validity.
- The method uses finite differences and a local damped Gauss–Newton step. It does not provide multistart/global search, residual weighting, regularization, covariance, confidence intervals, or uncertainty analysis.
- The caller owns equations, data provenance, residual construction, units, observation mapping, and domain constraints beyond the parameter box.
- Callbacks execute in-process and are not sandboxed. The optimizer bounds its own callback count and dense Jacobian dimensions, but not callback runtime or memory.
- Extreme finite inputs whose least-squares cost overflows are rejected with `ValueError`; cost underflow is represented explicitly while optimization compares the residual norm.
- No modified SIR equations, initial conditions, units, or experimental data were provided. SIR-specific fitting and scientific review are therefore `NOT_RUN`.
- AGY CLI E2E/provider-backed review is `NOT_RUN`; branch CI is pending. The local independent code review recorded below is not a provider E2E. This report does not substitute for either.

An independent read-only code review reproduced three numerical defects during development (column-scale masking, initial-value rounding, and finite-difference cancellation); each now has a regression test that passes. The final review found no remaining critical or important defect. Branch CI is still pending.

## Next increment

P2.4 should add a versioned, provenance-preserving observation/residual contract only after it is grounded in the first SIR input. Until the equations and data arrive, retain the current generic callbacks and avoid adding data-import or domain-specific assumptions.
