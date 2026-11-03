# Numerical simulation core (experimental)

SSEC provides an optional, dependency-free fixed-step Runge–Kutta 4 solver in `scripts/scientific_core.py`. It accepts an ODE right-hand side `rhs(t, state, parameters)`, a finite forward interval, finite initial state/parameters, and a maximum time step. The result has aligned `times` and `states` tuples and `to_dict()` emits a versioned JSON-safe payload for later workspace components.

```python
from scripts.scientific_core import OdeProblem, solve_rk4

problem = OdeProblem(
    rhs=lambda _t, y, p: (-p["decay"] * y[0],),
    t_span=(0.0, 1.0),
    initial_state=(1.0,),
    parameters={"decay": 1.0},
    state_names=("quantity",),
)
result = solve_rk4(problem, max_step=0.01)
payload = result.to_dict()
```

The internal grid is uniform, reaches the requested end time, and uses no more than `max_steps` (default 1,000,000). The solver rejects malformed dimensions and non-finite values at every derivative stage. It does not interpolate, estimate local error, adapt the step, detect stiffness, check positivity/conservation/units, or certify equations.

The supplied `rhs` callable executes in the caller's Python process. This API is **not a code-execution sandbox** and does not authenticate model code. Do not load agent-generated or otherwise untrusted Python callbacks into the desktop application's process; using untrusted model code requires a separate, verified execution boundary.

## Evidence and validity boundaries

- **Software validity:** API input checks and result serialization are covered by unit tests.
- **Numerical validity:** the test suite compares exponential decay to its analytic solution and checks the expected fourth-order global convergence under step halving for that smooth example. This is evidence about the solver on that test case, not an error bound for an arbitrary project model.
- **Scientific validity:** not assessed by this component. Model equations, assumptions, units, initial conditions, data provenance, and suitability require a separate domain review. A successful integration or small residual does not establish identifiability, uniqueness, causal validity, or model correctness.

Use this API as a reusable engine for a future project-specific workspace. The modified SIR model and experimental-data workflow remain pending user-provided equations/data; no SIR result is included or claimed here. Adaptive/stiff solvers, optimization, uncertainty, PDEs, and scientific audit automation remain planned.

## Local ODE parameter sensitivities (experimental P2.2)

`parameter_sensitivities(problem, perturbations, max_step, *, max_steps=..., max_total_steps=...)` estimates local derivatives of the RK4 trajectory. `perturbations` maps selected parameter names to explicit positive **absolute** step sizes; parameter mapping order is preserved in the final axis. The function computes one base solution and two perturbed trajectories per selected parameter, with other parameters and the initial state fixed.

For each time and state, the result stores

```text
(y(p_upper) - y(p_lower)) / (p_upper - p_lower)
```

under `OdeSensitivity.values[time][state][parameter]`. The serialized form includes the base trajectory, supplied steps, effective representable bounds, grid, aggregate integration work, and RHS evaluation count. `max_total_steps` is checked before any RHS callback runs. A callback failure at either perturbed endpoint aborts the whole computation and identifies the parameter and side.

The central difference approximates the sensitivity of **discretized** trajectories. Its accuracy depends on perturbation size, local smoothness, floating-point cancellation, and the RK4 step size. The caller is responsible for choosing perturbations that stay within the model's parameter domain. A request is bounded to 100 parameters and 1,000,000 scalar output/intermediate values; `max_total_steps` defaults to 1,000,000 and is checked before any callback runs. The API does not estimate derivative error, choose perturbations, test identifiability, propagate measurement uncertainty, or validate scientific assumptions. Its callback executes in-process and is not sandboxed.

Tests compare exponential decay sensitivities with an analytic derivative, exercise state/parameter axis ordering and cross terms, and verify second-order central-difference error reduction on `y'=p^3`. These checks establish behavior only for the tested functions; they do not validate the user's still-unspecified SIR.
