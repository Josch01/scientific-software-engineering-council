# P2.3 bounded least-squares design

## Intent

Add a reusable local parameter-fit primitive for future scientific projects, including the requested SIR workspace. No SIR equations, measurements, units, or initial conditions have been supplied, so this increment will fit only caller-provided residual functions and will make no model-specific claim.

## Approaches considered

1. **Bounded Levenberg–Marquardt with finite-difference Jacobian (selected).** Uses the standard library, explicit parameter bounds and work budgets, and handles smooth local least-squares problems without adding a package. It is a local optimizer and can stop at a local or constrained stationary point.
2. **SciPy `least_squares`.** Offers mature algorithms and diagnostics, but this repository declares no numerical runtime dependency and the user has not authorized installing one. Revisit when a supplied project requires it.
3. **Derivative-free coordinate search.** Simpler, but may require many callback evaluations and has weak convergence behavior as parameter count grows; it is a poor default for the planned parameter-identification workflow.

The user delegated autonomous continuation, requested optimization and parameter identification in the SIR workspace, and has not authorized new packages. The selected scope is a dependency-free, bounded local fit primitive.

## Contract

Add `fit_least_squares(residual_function, initial_parameters, bounds, *, max_iterations, max_function_evaluations, finite_difference_fraction, gradient_tolerance, cost_tolerance, step_tolerance)` to `scripts/scientific_core.py` and return an immutable `LeastSquaresFit`.

- Parameter order follows `initial_parameters`; every parameter must have a finite, strictly increasing `(lower, upper)` bound and an initial value within that interval.
- The callback receives an immutable mapping and returns a non-empty finite residual vector. The minimized unweighted objective is `0.5 * sum(residual_i**2)`; callers can scale residuals explicitly.
- Optimize in bounded, locally scaled coordinates centered exactly on the caller's initial values. The coordinate scale for each parameter is `max(abs(initial_value), min(bound_width, 1.0))`; this preserves the initial float exactly while keeping large boxes from erasing small meaningful updates. Scale Jacobian columns for the linear solve, then map steps back through those scales. The physical finite-difference step is `finite_difference_fraction * bound_width`, clipped to feasible distance; this avoids unrepresentable perturbations when the box is much wider than the local coordinate scale. Use central differences in the interior and one-sided differences at active bounds. Clamp trial points to the box.
- Keep residual normalization fixed to at least the initial residual scale while iterating. This keeps gradient stopping scale-invariant without allowing one large Jacobian column to hide progress in another parameter. `gradient_tolerance` is applied to this scaled local gradient; it does not promise an absolute residual threshold.
- The result contains initial/final parameters, bounds, final residuals and cost, a truthful status (`CONVERGED`, `MAX_ITERATIONS`, `MAX_FUNCTION_EVALUATIONS`, or `STALLED`), iteration/accepted-step/evaluation counts, and JSON-safe serialization. If a nonzero residual norm squares below the representable float range, report `cost_underflowed: true`; the residual vector remains authoritative.
- Reject malformed inputs, non-finite or changing residual dimensions, non-finite objective/Jacobian/step values, excessive parameter/Jacobian size, and callback failures with context. Never label a budget stop as convergence.
- Limit parameters to 100 and Jacobian values to 1,000,000. Bound callback invocations through `max_function_evaluations`.

## Limits and anti-claims

The callback is expected to be deterministic and locally smooth; the optimizer does not verify either property. It does not provide global optimization, multi-start, residual weighting, missing-data handling, covariance, uncertainty, profile likelihood, structural/practical identifiability, causal inference, or scientific validation. It does not sandbox callback code. Convergence means only that this numerical stopping rule was met for this supplied residual function and initialization.

## Acceptance

- Recover a known interior solution for an overdetermined linear residual system.
- Recover a small residual component when another parameter has a much larger Jacobian column.
- Preserve the exact initial parameter for a very wide finite bound interval.
- Avoid finite-difference cancellation when a wide-box parameter is small relative to the residual magnitude.
- Respect box bounds and report constrained convergence without claiming the unconstrained target was reached.
- Record immutable, JSON-safe results and exact work counts.
- Reject invalid bounds, initial values, residual values/dimensions, callback failures, and exhausted work budgets without false convergence.
- Add no external dependency and preserve RK4/sensitivity behavior.
