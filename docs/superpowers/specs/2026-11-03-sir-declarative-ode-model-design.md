# SIR declarative ODE model contract

## Intent

Let a scientific workspace describe and run a small SIR initial-value problem using verified JSON data and SSEC's existing fixed-step RK4 solver. The project supplies equations as a closed, versioned equation set; it cannot supply executable Python. Each run remains behind the workspace's human-confirmed, one-use simulation action.

The owner selected this declarative contract and specified that only the initial SIR case is implemented. The actual modified SIR remains `NOT_RUN` until its exact equations, units, parameters, initial conditions, interval, and data are supplied.

## Approaches considered

1. **Closed SIR contract (selected):** accept one exact equation set and two explicitly supported time profiles. Small, auditable validation surface; other models need a future schema extension.
2. **General expression AST:** parse a safe mathematical expression language. More flexible, but introduces a symbolic language and operator/resource limits before a real model needs them.
3. **Python callback from the project:** flexible, but would load project code into the SSEC process and violate the stated execution boundary.

## Contract v1

The core accepts only `schema_version: 1`, `model_type: "sir"`, and `equation_set: "sir_frequency_dependent_v1"`. It requires the exact states and order `S, I, R`, three corresponding initial values, parameters `beta` and `gamma`, a finite forward `t_span`, explicit unit labels, and integrator configuration `method: "RK4_FIXED_STEP"` with finite positive `max_step` and a step budget no greater than 99,999.

The equation map is data checked against these exact formulas; formulas are never parsed or evaluated from strings:

```text
N = S(0) + I(0) + R(0)
dS/dt = -beta(t) * S * I / N
dI/dt =  beta(t) * S * I / N - gamma(t) * I
dR/dt =  gamma(t) * I
```

Both rates accept exactly two function forms:

- `{"kind":"constant","value":number}`
- `{"kind":"piecewise_linear","points":[[time,value], ...]}`

Piecewise-linear schedules have 2–128 points, start and end at the integration interval endpoints, use strictly increasing finite times, and have finite nonnegative values. Every knot must align with the uniform grid selected by the existing fixed-step solver; this avoids stepping across a profile's slope change. No discontinuous schedule or arbitrary expression syntax is accepted. `beta` and `gamma` use `1/<time-unit>`; all states use the declared population unit. Units are labels and are not converted.

Validation rejects unknown keys/symbols, wrong dimensions, duplicate or missing states/parameters, negative or non-finite rates/initial states, a zero total population, invalid intervals/profiles, unsupported equations/integrators, and work above the solver budget. The adapter constructs an `OdeProblem` and calls the existing `solve_rk4`; it adds no integrator. SIR output is rejected if any compartment becomes negative or total population drifts beyond a documented relative tolerance. It is never clipped or repaired.

## Workspace and UI binding

The built-in SIR action reads the unique `model_spec` resource only from `LoadedWorkspace` bytes and binds to existing `simulation_plot` components. A malformed or unsupported contract reaches the existing visible action-error path and never yields a result tab. The app imports no project code. Each actual run requires the existing human confirmation and one-use ticket. Host-injected callbacks remain supported; they take precedence for the same component.

The first contract intentionally supports one model resource per workspace. Multiple-model selection, SEIR, free-form equations, unit conversion, fitting, and scientific validity claims are outside this increment. A synthetic example will be explicitly labeled as a software fixture, not as a real or validated SIR study.

## Verification target

Tests cover strict schema and profile validation, independently derived RK4 behavior, SIR population/positivity checks, safe workspace-to-action binding, human decline/acceptance, visible failures, and an end-to-end synthetic example. No user-specific SIR claim is made.
