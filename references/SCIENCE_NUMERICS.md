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

The internal grid is uniform, reaches the requested end time, and uses no more than `max_steps` (default 1,000,000). The solver rejects malformed dimensions and non-finite values at every derivative stage. It does not interpolate, estimate local error, adapt the step, detect stiffness, check positivity/conservation/units, or certify equations. The SIR-specific adapter below adds only the positivity and population-conservation checks implied by its fixed equations.

The supplied `rhs` callable executes in the caller's Python process. This API is **not a code-execution sandbox** and does not authenticate model code. For the first prototype, run only callbacks from trusted, reviewed code that a human has explicitly approved. Never import or execute arbitrary agent-generated Python automatically in the application process. A future runner for generated model code must use a separate process and effective OS isolation. If Docker is selected, configure resource limits, no network unless needed, read-only inputs, and bounded outputs; Docker must not be described as absolute isolation.

## Evidence and validity boundaries

- **Software validity:** API input checks and result serialization are covered by unit tests.
- **Numerical validity:** the test suite compares exponential decay to its analytic solution and checks the expected fourth-order global convergence under step halving for that smooth example. This is evidence about the solver on that test case, not an error bound for an arbitrary project model.
- **Scientific validity:** not assessed by this component. Model equations, assumptions, units, initial conditions, data provenance, and suitability require a separate domain review. A successful integration or small residual does not establish identifiability, uniqueness, causal validity, or model correctness.

## Declarative SIR contract v1 (experimental)

`SirModelDefinition.from_json()` accepts a strict UTF-8 JSON contract capped at 1 MiB. It permits only `schema_version: 1`, `model_type: "sir"`, and the fixed frequency-dependent equation set `sir_frequency_dependent_v1`, with states in `S, I, R` order. The equation strings must exactly equal the documented formulas; they are inert identifiers and are never parsed or evaluated. Python callbacks can be used by the lower-level `OdeProblem` API, but workspace project files cannot supply or import them.

The contract validates nonnegative finite initial populations with positive total, exactly `beta` and `gamma`, nonnegative finite rates, a finite forward time interval, explicit unit labels (`rate` must be `1/<time>`), and `RK4_FIXED_STEP` settings within a 99,999-step budget. Units are labels: no dimensional algebra or unit conversion is performed. Rates accept only constants or piecewise-linear schedules with 2–128 ordered points covering the full interval. Schedule knots must align with the uniform grid chosen by the existing RK4 solver.

`solve_sir_model()` reuses `OdeProblem` and `solve_rk4`. It rejects any negative compartment or population drift beyond `max(1e-12, N*1e-9)` and never clips or projects results. These checks do not establish stability, accuracy for a particular real system, parameter identifiability, or scientific validity.

`examples/sir_model_demo.json` and `examples/run_sir_model_demo.py` are a deterministic synthetic software fixture. The output is explicitly marked `scientific_validity: NOT_ASSESSED`; it exercises the contract and solver only. The user's modified SIR, its equations, parameters, units, initial conditions, observations, and scientific review remain `NOT_RUN` until supplied.

The dynamic workspace's `equation_view` and `parameter_table` components recognize this validated contract. They render the fixed equations, declared units, initial conditions, integration interval/settings, and constant or piecewise-linear rate profiles as reusable views selected by the manifest. Other model resources remain bounded, inert JSON; no renderer imports project modules. The example manifest at `examples/sir_scientific_workspace.json` combines these views with the existing simulation plot and human-confirmed run action.

## SIR parameter analysis bridge v1 (experimental P3.17)

`SirModelDefinition.to_ode_problem()` exposes the same closed SIR equations to existing fit/sensitivity APIs when both rates are constant. Piecewise-linear schedules remain supported for simulation, but fitting their knots is not supported. `analyze_sir_parameters()` composes the existing bounded least-squares fit, local central-difference sensitivity, fixed-step RK4 solution, and observation residual evaluator; it adds no optimizer, solver, or uncertainty algorithm.

The bridge requires exact `beta`/`gamma` inputs, nonnegative rate bounds and sensitivity endpoints, matching model/observation time units, and population-unit labels matching the SIR contract. Residuals remain raw and unweighted; the wrapper currently requires every measured compartment to use the same declared population unit. A shared scalar-step budget covers fit evaluations and returned analysis trajectories. A checked RHS enforces nonnegative intermediate compartments and population conservation throughout fit and sensitivity solves; the returned fitted trajectory is checked as well.

The fit contract's status is displayed exactly. For the checked-in exact synthetic fixture, it currently reports `STALLED` while recovering rates within 4e-9 of the declared synthetic values. This numerical result does not demonstrate convergence, identifiability, model validity, or agreement with empirical data. The reproducible workspace is `examples/sir_analysis_workspace_demo/`; run `python scripts/build_sir_analysis_demo.py` to regenerate it. Its observations are generated from the same model, uncertainty is `NOT_CALCULATED`, scientific validity and identifiability are `NOT_ASSESSED`, and the user's model/data remain `NOT_RUN`.

Adaptive/stiff solvers, general equation languages, unit conversion, time-varying-rate fit parameterization, uncertainty, PDEs, and scientific audit automation remain outside this increment.

## Local ODE parameter sensitivities (experimental P2.2)

`parameter_sensitivities(problem, perturbations, max_step, *, max_steps=..., max_total_steps=...)` estimates local derivatives of the RK4 trajectory. `perturbations` maps selected parameter names to explicit positive **absolute** step sizes; parameter mapping order is preserved in the final axis. The function computes one base solution and two perturbed trajectories per selected parameter, with other parameters and the initial state fixed.

For each time and state, the result stores

```text
(y(p_upper) - y(p_lower)) / (p_upper - p_lower)
```

under `OdeSensitivity.values[time][state][parameter]`. The serialized form includes the base trajectory, supplied steps, effective representable bounds, grid, aggregate integration work, and RHS evaluation count. `max_total_steps` is checked before any RHS callback runs. A callback failure at either perturbed endpoint aborts the whole computation and identifies the parameter and side.

The central difference approximates the sensitivity of **discretized** trajectories. Its accuracy depends on perturbation size, local smoothness, floating-point cancellation, and the RK4 step size. The caller is responsible for choosing perturbations that stay within the model's parameter domain. A request is bounded to 100 parameters and 1,000,000 scalar output/intermediate values; `max_total_steps` defaults to 1,000,000 and is checked before any callback runs. The API does not estimate derivative error, choose perturbations, test identifiability, propagate measurement uncertainty, or validate scientific assumptions. Its callback executes in-process and is not sandboxed.

Tests compare exponential decay sensitivities with an analytic derivative, exercise state/parameter axis ordering and cross terms, and verify second-order central-difference error reduction on `y'=p^3`. These checks establish behavior only for the tested functions; they do not validate the user's still-unspecified SIR.
