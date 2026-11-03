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

## Evidence and validity boundaries

- **Software validity:** API input checks and result serialization are covered by unit tests.
- **Numerical validity:** the test suite compares exponential decay to its analytic solution and checks the expected fourth-order global convergence under step halving for that smooth example. This is evidence about the solver on that test case, not an error bound for an arbitrary project model.
- **Scientific validity:** not assessed by this component. Model equations, assumptions, units, initial conditions, data provenance, and suitability require a separate domain review. A successful integration or small residual does not establish identifiability, uniqueness, causal validity, or model correctness.

Use this API as a reusable engine for a future project-specific workspace. The modified SIR model and experimental-data workflow remain pending user-provided equations/data; no SIR result is included or claimed here. Adaptive/stiff solvers, sensitivity, optimization, uncertainty, PDEs, and scientific audit automation remain planned.
