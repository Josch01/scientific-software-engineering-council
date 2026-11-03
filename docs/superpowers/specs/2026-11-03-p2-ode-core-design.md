# P2 ODE core — design

## Intent

Deliver the first reusable scientific computation component behind SSEC: a deterministic, dependency-free initial-value ODE solver that future model code and scientific workspaces can call. The user has not supplied the modified SIR equations or data, so this increment must not invent or certify that model.

## Goals

- Expose a small Python contract for a model right-hand side, parameters, initial state, and forward time interval.
- Implement classical fixed-step fourth-order Runge–Kutta (RK4) with a caller-specified maximum step and bounded work.
- Return a structured time/state series usable by later workspace and plotting components.
- Reject invalid dimensions, non-finite values, invalid intervals/steps, and excessive step counts clearly.
- Establish software and numerical evidence with an analytic solution and a step-halving convergence check.

## Non-goals and anti-goals

- No model-specific SIR equations, experimental-data claims, parameter fitting, uncertainty, sensitivity, stiffness handling, adaptive error control, GUI, or provider orchestration.
- No external dependency installation and no solver-generated `SCIENTIFIC_VALIDITY=PASS` claim.
- Do not infer positivity, conservation, units, identifiability, stability, or scientific correctness without model-specific contracts and evidence.

## Approaches considered

1. **Pure-Python fixed-step RK4 (selected).** Small stable interface, no installation, deterministic tests against analytic values. Its limits are explicit and suitable for the first model workspace.
2. **SciPy adaptive solver.** Better options for stiffness and error control, but no scientific dependency is currently declared and adding/installing one is outside this bounded increment. Revisit when a supplied model requires it.
3. **Hard-coded SIR solver.** Rejected because the model equations and data are not available; it would couple the core to invented assumptions and impede reuse.

The user delegated autonomous continuation and confirmed the model details are not yet available; approach 1 is therefore this increment's implementation choice.

## Contract

Add `scripts/scientific_core.py` with an immutable `OdeProblem` describing `rhs(t, state, parameters)`, `t_span`, `initial_state`, optional state names, and numeric parameters. `solve_rk4(problem, max_step, max_steps=...)` returns an `OdeSolution` containing ordered times, ordered state tuples, state names, parameters, method, requested/actual step sizes, and step count. Its `to_dict()` emits a versioned JSON-safe contract for later workspace components. The solver uses `ceil((t1-t0)/max_step)` equal substeps so it reaches the endpoint exactly; it does not interpolate or estimate local error. Validate callback result dimension and finiteness at every RK stage.

The component reports software-contract errors by raising `ValueError` with actionable context. It reports no general scientific-validity status. Consumers must record model assumptions and separately establish numerical/scientific validity.

## Acceptance

- Analytic exponential decay is reproduced within a stated test tolerance.
- Halving the step reduces the smooth-problem global error by approximately the fourth-order factor (assert a conservative ratio).
- Invalid inputs, dimension mismatches, non-finite derivatives, and a step budget overflow fail explicitly.
- The result records the actual uniform step and reaches `t1` exactly.
- Focused tests and one final full existing suite run on Windows; Linux CI evidence is reported only if actually available.
- No specific SIR result or scientific claim is reported as verified.
