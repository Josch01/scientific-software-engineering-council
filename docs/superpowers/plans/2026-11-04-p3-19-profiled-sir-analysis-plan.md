# P3.19 Profiled SIR Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse existing RK4, bounded least-squares, local sensitivity, residual, and workspace-view contracts to analyze a declarative SIR with selected piecewise-linear rate knots.

**Architecture:** Keep the SIR v1 model schema unchanged. Add explicit fit-knot selection at the analysis API, evaluate fitted knot values through the validated `TimeFunction`, split observation integration at declared knots, and show the resulting parameter units through the existing workspace view path.

**Tech Stack:** Python standard library, `unittest`, existing SSEC scientific and optional Qt modules; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-04-p3-19-profiled-sir-analysis-design.md`

## Global Constraints

- No `eval`, `exec`, external model calls, new numerical algorithms, or new dependencies.
- Reuse the validated SIR v1 contract and existing RK4 / bounded least-squares / finite-difference sensitivity implementations.
- Respect declared resource budgets; failed runs never produce approved or scientifically certified status.
- Preserve uncertainty as `NOT_CALCULATED` and scientific validity/identifiability as `NOT_ASSESSED`.
- Use only reproducible synthetic data in this increment; the user SIR remains `NOT_RUN`.

## Review Focus

1. Invalid, duplicate, or out-of-range knot indices — reject before solving; test each case.
2. Irregular observation intervals crossing multiple knots — split at each knot and preserve residual ordering; test with exact fixture values.
3. A candidate rate below zero or outside its bounds — reject/clip only through the existing bounded optimizer contract; test negative bound and perturbation cases.
4. Analysis step size not aligned with a declared knot — fail before simulation; test a profile valid at model max-step but invalid at requested smaller step.
5. Knot parameter labels/units in fit and sensitivity views — render `beta_knot_<index>` / `gamma_knot_<index>` with rate units; test the workspace view context.

---

### Task 1: Parameterize validated rate profiles and residual breakpoints

**Files:**
- Modify: `scripts/scientific_core.py`
- Test: `tests/test_scientific_core.py`
- Test: `tests/test_scientific_observations.py`

**Interfaces:**
- `TimeFunction.evaluate(time, *, value_overrides: Mapping[int, float] | None = None) -> float` evaluates an existing profile after finite overrides at explicit knot indices.
- `evaluate_observations(..., breakpoints: Sequence[float] = ()) -> ObservationEvaluation` splits each observation interval at sorted, unique, in-span breakpoints before using the same RK4 solver and shared step budgets.
- `analyze_sir_parameters(..., fit_knots: Mapping[str, Sequence[int]] | None = None, ...) -> SirParameterAnalysis` derives canonical knot parameter names and reuses existing fit and sensitivity functions.

- [x] **Step 1: Add failing core tests** named `test_piecewise_linear_evaluate_overrides_selected_knots_only`, `test_analyze_profiled_sir_recovers_selected_beta_knot_and_preserves_unselected_knots`, and `test_analyze_profiled_sir_rejects_invalid_knot_selection_and_non_aligned_step`. Assert hand-derived profile interpolation, recovered synthetic knot value, unchanged unselected knots, rejection of duplicate/out-of-range indices, and pre-solve rejection when a smaller analysis grid crosses a model knot.
- [x] **Step 2: Run the focused tests and confirm expected failures** with `python -m unittest tests.test_scientific_core.SIRDeclarativeContractTests tests.test_scientific_core.SIRParameterAnalysisTests -v`.
- [x] **Step 3: Add failing observation tests** named `test_evaluate_observations_splits_rk4_at_breakpoints` and `test_evaluate_observations_rejects_unsorted_duplicate_or_out_of_span_breakpoints`. Use `y'=1` before `t=0.5`, `y'=2` after, one observation interval `[0, 1]`, and assert the split result `y(1)=1.5` and total of two RK4 steps.
- [x] **Step 4: Run the focused observation tests and confirm expected failures** with `python -m unittest tests.test_scientific_observations -v`.
- [x] **Step 5: Implement profile overrides, breakpoint-aware segment accounting, and fit-knot parameterization** without changing the SIR v1 payload or optimizer/solver algorithms.
- [x] **Step 6: Run both focused suites**; expected all new and existing tests pass.
- [x] **Step 7: Commit** as `feat: analyze piecewise SIR rate parameters` (`ad994aa`).

### Task 2: Render a reproducible profiled-SIR workspace

**Files:**
- Modify: `scripts/build_sir_analysis_demo.py`
- Modify: `scripts/scientific_workspace_view.py`
- Modify: `.gitattributes`
- Create: `examples/sir_profiled_analysis_workspace_demo/`
- Modify: `tests/test_scientific_control_center_qt.py`
- Test: `tests/test_scientific_sir_analysis_demo.py`
- Test: `tests/test_scientific_workspace_science_views.py`
- Test: `tests/test_scientific_workspace_qt_views.py`

**Interfaces:**
- Demo builder adds a deterministic `profiled` scenario while preserving the existing default constant-rate scenario.
- Workspace context derives units for declared knot parameters from the validated SIR model and leaves result contracts unchanged.

- [x] **Step 1: Add failing tests** named `test_profiled_demo_workspace_contains_calculated_fit_and_explicit_scientific_status`, `test_profiled_parameter_units_are_derived_from_model_resource`, and `test_qt_fit_and_sensitivity_views_render_profiled_rate_units`. Build a profiled fixture in a temporary directory, load it through the safe loader, and assert `beta_knot_1` is shown with `1/day`, with the observation evaluation linked to the calculated fit.
- [x] **Step 2: Run the new test and confirm it fails** because the profiled scenario/unit mapping is unavailable.
- [x] **Step 3: Implement the `profiled` demo scenario and knot-unit derivation** using the existing builder, loader, view model, and Qt renderer.
- [x] **Step 4: Run the demo/view/Qt focused tests** and confirm constant-rate rendering remains unchanged. The profiled artifact also loads in `ControlCenterWindow` with the supervisor sharing the same verified project; two local Qt fallback captures document fit/residual and sensitivity views.
- [x] **Step 5: Commit** as `feat: add profiled SIR analysis workspace demo` (`709d239`).

### Task 3: Record evidence and update the phase matrix

**Files:**
- Modify: `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-19-profiled-sir-analysis-2026-11-04.md`

- [x] **Step 1: Run the targeted scientific/workspace regression set, structure validator, compileall, and `git diff --check`; save the compact execution record in the plan workspace.**
- [x] **Step 2: Record commit SHA, OS/Python, commands, counts, fixture source, limitations, and defects in the report.**
- [x] **Step 3: Mark P3.19 `EXPERIMENTAL`; keep SIR-user validity and provider E2E `NOT_RUN` and uncertainty `NOT_CALCULATED`.**
- [x] **Step 4: Commit** as `docs: record P3.19 profiled SIR evidence`.
