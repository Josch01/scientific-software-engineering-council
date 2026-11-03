# P2.2 local ODE parameter sensitivity evidence — 2026-11-03

## Status

`EXPERIMENTAL`. The new API estimates local derivatives of fixed-step RK4 trajectories with explicit absolute perturbations. It does not perform parameter fitting or scientific validation.

## Verified locally

- Windows 11, Python 3.14.0.
- `python -m unittest discover -s tests -p test_scientific_sensitivity.py -v`: **9/9 passed**.
- `python -m unittest discover -s tests -p test_scientific_core.py -v`: **14/14 passed**; P2.1 regression behavior is preserved.
- Analytic decay sensitivity matches `d(y0*exp(-p*t))/dp`; a two-state linear system checks [time][state][parameter] axes and cross terms; an unused parameter has zero sensitivity.
- `y'=p^3` with fixed time grid shows central-difference truncation error reduced by four when the absolute perturbation is halved.
- Tests cover zero and negative parameters, effective bounds, JSON serialization, unrepresentable perturbations, invalid parameter selection, step and memory preflight that invoke no RHS callbacks, and contextual failure on one perturbation side.
- Independent numerical/code review found one minor memory-bound undercount; the guard was updated and a no-callback regression added. Final re-review confirmed no remaining findings.
- Linux/Windows Python 3.11/3.12 PR CI is not yet run for this commit.

## Limits

- No user SIR equations, units, initial conditions, or data were supplied. SIR implementation and scientific validation remain `NOT_RUN`.
- Sensitivity values are numerical approximations of discretized trajectories. The API does not estimate derivative error, automatically select perturbations, verify smoothness/determinism, enforce model-specific parameter domains, establish identifiability, or quantify measurement uncertainty.
- The RHS is executed in-process; this API is not a sandbox.
- Adaptive/stiff integration, optimization, uncertainty propagation, and the complete P2 acceptance gate remain pending.
