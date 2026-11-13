# P2.5 Thesis SIR Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the thesis's bounded harmonic SIR and weekly incidence observation contract, without running the user's real series.

**Architecture:** Add a versioned, typed thesis model in `scripts/thesis_sir_model.py` and a narrow JSON adapter in `scripts/thesis_sir_data.py`. Keep `scientific_core.py` unchanged; integrate each weekly interval through its existing generic `OdeProblem` and fixed-step RK4 with an internal incidence accumulator.

**Tech Stack:** Python standard library, existing `OdeProblem`/`solve_rk4`, unittest.

**Spec:** `docs/superpowers/specs/2026-11-13-p2-5-thesis-sir-model.md`.

## Global Constraints

- No `eval`, `exec`, new numerical integrator, or external dependency.
- Match the thesis parameterization, units, bounds, fixed population, q and delay semantics.
- Use only the JSON's `DGE_monday_sunday_candidate` series; retain source digest and provenance.
- Tests use synthetic fixtures only; real SIR execution remains `NOT_RUN` pending system completion and human approval.
- Keep fitting, GUI, and scientific-validity claims outside this increment.

## Review Focus

- Invalid harmonic counts, nonfinite/out-of-bound coefficients, and infeasible initial states must fail before integration.
- Weekly boundaries must shift by `delta/7`, and the predicted count must equal q times accumulated incidence on that interval.
- Malformed/duplicate/missing/noninteger data must fail without silently substituting another JSON series.
- Conservation and fixed-step convergence must be checked on synthetic inputs; extreme valid parameters may still produce an explicit numerical failure at a chosen step size.

---

### Task 1: Versioned model contract

**Files:** Create `scripts/thesis_sir_model.py`; test `tests/test_thesis_sir.py`.

- [x] Add failing tests for the exponential Fourier beta value, exact RHS, all thesis bounds, and the initial-state feasibility condition.
- [x] Run only the new tests and confirm they fail because the contract is absent.
- [x] Add immutable typed harmonic component and parameter objects with strict `from_dict`/`to_dict`; compute beta only with `math.exp/sin/cos`.
- [x] Re-run the new tests and the existing scientific-core tests; require concise PASS output.

### Task 2: Weekly incidence evaluator

**Files:** Modify `scripts/thesis_sir_model.py`; test `tests/test_thesis_sir.py`.

- [x] Add failing tests for delta-shifted weekly intervals, q-scaled integrated incidence, population conservation, and RK4 step-halving convergence.
- [x] Confirm RED, then augment the existing `OdeProblem` with an incidence state and reuse `solve_rk4` per weekly interval; reject work-budget or numeric failures.
- [x] Confirm GREEN on synthetic cases; do not load the target JSON in these tests.

### Task 3: Strict reconstruction JSON adapter

**Files:** Create `scripts/thesis_sir_data.py`; create `tests/test_thesis_sir_data.py`.

- [x] Add failing synthetic JSON tests for selection of only `DGE_monday_sunday_candidate`, ordering, 56-row shape, nonnegative integer counts, malformed JSON and missing values.
- [x] Implement bounded strict parsing and preserve the raw-source SHA-256 plus series identifier.
- [x] Confirm tests pass; never fall back to the `local` or official Sunday–Saturday columns.

### Task 4: Reproducible synthetic example

**Files:** Create `examples/sir_thesis_forward_demo.py`.

- [x] Add an explicitly `SYNTHETIC_FIXTURE` four-week demonstration using the thesis SIR equations and parameter bounds.
- [x] Run the example once and confirm it reports the fixed-step method and finite means; label all values synthetic.

### Task 5: Report and roadmap

**Files:** Create `docs/test-reports/p2-5-thesis-sir-model-2026-11-13.md`; update `docs/roadmap/FEATURE_MATRIX.md`.

- [x] Record focused test totals in a short report, synthetic-only scope, pending CI and real-run `NOT_RUN`.
- [ ] Verify `git diff --check`, report links, and a clean staged diff before commit.
- [ ] Commit and push this increment on a separate branch; open a draft PR stacked on P3.22 without merging.
