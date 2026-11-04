# SIR declarative ODE model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate a closed declarative SIR contract in `scientific_core`, run it with existing RK4, and connect verified workspaces to the human-confirmed simulation button.

**Architecture:** `scientific_core.py` owns the immutable SIR contract, the allowlisted coefficient profiles, and an adapter to `OdeProblem`/`solve_rk4`. `scientific_workspace_actions.py` binds the safe loaded model bytes to the existing one-use approval API; the app registers the built-in action for matching plots. No resource code is imported or evaluated.

**Tech Stack:** Python standard library, existing SSEC ODE solver, JSON workspace loader, Tk UI, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-03-sir-declarative-ode-model-design.md`

## Global Constraints

- Implement only `sir_frequency_dependent_v1`; no general AST, `eval`, `exec`, or project Python imports.
- Accept only `constant` and `piecewise_linear` rate profiles with at most 128 points, exact interval coverage, and knots on the chosen RK4 grid.
- Use `RK4_FIXED_STEP` via existing `solve_rk4`; at most 99,999 steps per run.
- Require nonnegative finite initial states/rates, positive total population, and explicit compatible unit labels.
- Keep every execution behind human confirmation; errors never create result tabs.
- Keep the user-specific SIR scientific state `NOT_RUN` without its supplied equations and data.

## Review Focus

- Unknown or malformed equation/profile fields: reject before any solver call.
- Profile knots outside, unordered, or off the uniform RK4 grid: reject before any solver call.
- Stable but coarse RK4 steps that violate compartment constraints: report an error, never clip.
- Missing or ambiguous model resources: do not register a runnable action.
- Declined confirmation or callback error: no solver side effect/result tab.

---

### Task 1: SIR contract and admitted coefficient profiles

**Files:**
- Modify: `scripts/scientific_core.py`
- Test: `tests/test_scientific_core.py`

**Interfaces:**
- Add `SirModelDefinition.from_dict(payload: object) -> SirModelDefinition`.
- Add immutable `TimeFunction.from_dict(payload: object, *, t_span: tuple[float, float]) -> TimeFunction` with `evaluate(time: float) -> float`.
- `SirModelDefinition` exposes canonical states, initial conditions, `rhs(time, state, parameters)`, interval, unit labels, and integrator settings.

- [x] **Step 1: Write RED tests** for the canonical equation map and independently computed RHS; accept constant and piecewise-linear beta/gamma; reject extra keys, unknown symbols/equations, negative/non-finite values, wrong vector dimensions, malformed units, unsorted/out-of-range knots, and unsupported profile kinds.
- [x] **Step 2: Run the focused core tests** and confirm failures were feature-missing or expected validation failures.
- [x] **Step 3: Implement the immutable contract** with exact-key validation and fixed formulas; no expression parsing.
- [x] **Step 4: Re-run the focused tests** and confirm all pass.

### Task 2: Existing RK4 adapter and mathematical invariants

**Files:**
- Modify: `scripts/scientific_core.py`
- Test: `tests/test_scientific_core.py`

**Interfaces:**
- Add `solve_sir_model(definition: SirModelDefinition) -> OdeSolution`.
- It creates an `OdeProblem` and calls `solve_rk4`; it does not implement a second integrator.

- [x] **Step 1: Write RED tests** for a hand-derived one-step recovery-only trajectory, a time-varying profile, population conservation, nonnegative output, and a step-budget failure.
- [x] **Step 2: Run the focused tests** and verify the missing adapter was the cause.
- [x] **Step 3: Implement the RK4 adapter and output checks**; reject negative compartments or excessive conservation drift without clipping.
- [x] **Step 4: Re-run the focused tests**.

### Task 3: Safe workspace action binding and visible errors

**Files:**
- Modify: `scripts/scientific_workspace_actions.py`
- Modify: `scripts/scientific_workspace_app.py`
- Test: `tests/test_scientific_workspace_actions.py`
- Test: `tests/test_scientific_workspace_app.py`

**Interfaces:**
- Add `sir_simulation_actions_for_workspace(workspace: LoadedWorkspace) -> Mapping[str, ApprovedSimulationAction]`.
- Bind a validated `model_spec` resource from loader-captured bytes to eligible `simulation_plot` component IDs.
- Merge built-in actions with host-injected mappings while preserving host precedence.

- [x] **Step 1: Write RED tests** for unique model resource binding, missing/ambiguous resources, malformed JSON/contract errors, host override, declined confirmation, accepted action, and absent result tab on failure.
- [x] **Step 2: Run focused action/app tests** and verify the new binding path was missing.
- [x] **Step 3: Implement the action adapter** using the existing strict JSON parser and `SirModelDefinition` API; pass no project module paths to imports.
- [x] **Step 4: Register it in the reusable workspace window** for both initial and interactively opened workspaces; keep confirmation mandatory.
- [x] **Step 5: Re-run action/app tests and a hidden real-Tk smoke** for the accepted/declined flows.

### Task 4: Reproducible synthetic example, documentation, and verification

**Files:**
- Create: `examples/sir_model_demo.json`
- Create: `examples/sir_demo_result.json`
- Create: `examples/sir_scientific_workspace.json`
- Create: `examples/run_sir_model_demo.py`
- Modify: `references/SCIENCE_NUMERICS.md`
- Modify: `references/SCIENTIFIC_WORKSPACES.md`
- Modify: `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-sir-declarative-ode-2026-11-03.md`

- [x] **Step 1: Add a synthetic demo** with explicit unit labels and deterministic output; label it as a software fixture, not the user's SIR.
- [x] **Step 2: Run the demo and compare literal output assertions** in a regression test.
- [x] **Step 3: Run focused Windows tests, the full Docker/Linux suite, validation, compilation and diff checks.**
- [x] **Step 4: Request one independent review**, fix reproducible important defects with TDD, and document remaining limits.
- [x] **Step 5: Commit and push a separate branch; open a draft PR based on P3.6 and record CI without merging.** — PR draft [#29](https://github.com/Josch01/scientific-software-engineering-council/pull/29); corrected SHA `4f2b27cc41e20cf4ee48a4e8ec0393a9913fccea`; runs `41735442816` and `41735436247` passed 4/4 jobs each. Incremento de software cerrado; el SIR concreto del usuario sigue `NOT_RUN`.
