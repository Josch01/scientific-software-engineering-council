# P2.2 local ODE parameter sensitivity design

## Intent

Add a transparent sensitivity primitive needed by the requested SIR workflow while the actual SIR equations and data remain unavailable. This is local numerical analysis of a caller-supplied ODE callback; it does not perform parameter fitting, identifiability analysis, or scientific validation.

## API and semantics

Add `parameter_sensitivities(problem, perturbations, max_step, *, max_steps, max_total_steps)` to `scripts/scientific_core.py` and an immutable `OdeSensitivity` result.

- `perturbations` is a non-empty mapping from selected parameter name to an explicit positive **absolute** perturbation in that parameter's units. Mapping order determines the parameter axis. The API does not choose a step size.
- Solve one base trajectory and two perturbed trajectories per parameter, keeping every other parameter and the initial state fixed, on the same RK4 grid.
- For output state `i`, time `t`, and selected parameter `j`, compute
  `S[t,i,j] = (y_i(t; p_j^+) - y_i(t; p_j^-)) / (p_j^+ - p_j^-)`.
  Record the effective floating-point bounds; they need not be exactly symmetric around the base value.
- Result axes are exactly `[time][state][parameter]`; include the base solution, parameter names, supplied perturbations, effective bounds, RK4 grid, trajectory count, total integration steps, and RHS evaluation count in serialization.
- Sensitivity is of the discretized RK4 trajectory with the initial state held fixed. At the initial time all parameter sensitivities are zero.
- Reject unknown parameters, invalid/collapsed/non-finite bounds, non-finite differences, parameter/domain failures, and excessive work. Limit a request to 100 parameters and 1,000,000 scalar value slots. Preflight `(1 + 2*m) * step_count <= max_total_steps` and memory/output bounds before invoking the RHS. A failed perturbed trajectory raises with parameter and lower/upper context; no partial result or unilateral fallback is returned.

## Limits

The caller must choose perturbations that stay within the model's domain. The RHS is expected to be deterministic and locally smooth, but the API does not certify either property. Central differences have truncation and cancellation error; RK4 integration error also contributes. The method does not estimate those errors, adapt perturbations, establish identifiability, or infer uncertainty/causality. It executes the supplied callback in-process and is not a sandbox.

## Verification

- `y'=-p*y` against its analytic derivative.
- `x'=a, z'=b` to verify axes, cross terms, and parameter ordering.
- `y'=p^3` with halved absolute perturbation to show the expected second-order central-difference error reduction without ODE integration error.
- Zero/negative parameter values, unchanged inputs, explicit work limits, malformed bounds, and a failure on one perturbation side.
