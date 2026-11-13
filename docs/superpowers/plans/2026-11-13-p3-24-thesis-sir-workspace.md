# P3.24 Thesis SIR Workspace Implementation Plan

> **For agentic workers:** Execute this plan task by task; each step ends with a focused check.

**Goal:** Connect the P2.5 thesis SIR contract to a human-confirmed Qt workspace.

**Architecture:** Add an isolated PySide6 page and worker, then register that page in the existing Control Center. The page reuses the versioned model/data adapters and chart renderer; input is bounded and read-only, and exports are explicit user-selected files.

**Tech Stack:** Python, PySide6, local Qt WebEngine charts, existing SSEC scientific core.

**Spec:** `docs/superpowers/specs/2026-11-13-p3-24-thesis-sir-workspace.md`

## Global Constraints

- The project source JSON stays read-only and the parser selects only the declared Monday–Sunday candidate series.
- Parameters must be supplied explicitly; do not infer or invent them.
- Require human confirmation before running the thesis SIR model.
- Keep the run off the Qt main thread and reuse the existing RK4 evaluator.
- Never report scientific validity, identifiability or uncertainty as assessed by this UI.
- Do not simulate the user's thesis data during implementation or tests.

## Review Focus

- Malformed/oversized/changed JSON: fail before execution and retain no stale observation chart.
- Missing/out-of-range parameters: keep execution unavailable and show a field-level error.
- Rejected confirmation or worker exception: never show success or previous results as current.
- Duplicate clicks while running: allow one worker only.
- Saving to the source file: reject without changing source bytes.

### Task 1: Standalone thesis SIR Qt page

**Files:**
- Create: `scripts/thesis_sir_qt.py`
- Test: `tests/test_thesis_sir_qt.py`

- [ ] Test bounded source loading, input validation, confirmation rejection, synthetic worker success/failure, and safe export.
- [x] Run the new tests to observe expected failures.
- [x] Implement the page using the P2.5 contracts, a `QThread`, and existing chart widgets.
- [x] Run the focused new tests.

### Task 2: Control Center route and evidence

**Files:**
- Modify: `scripts/scientific_control_center_qt.py`
- Modify: `scripts/thesis_sir_data.py` only if a public bounded-read limit is needed.
- Modify: `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-24-thesis-sir-workspace-2026-11-13.md`

- [x] Add an accessible “SIR de tesis” route without changing the existing routes' behavior.
- [x] Run focused Control Center, thesis SIR and chart tests; compile and diff-check.
- [x] Capture a synthetic-only visual demonstration and document its renderer/limits.

### Task 3: Polish the scientific workspace presentation

- [x] Reorganize setup and results into separate panels under the existing Qt design tokens.
- [x] Keep dataset digest and path provenance visible without letting long paths dominate the layout.
- [x] Present observed/predicted and compartment plots as accessible tabs.
- [x] Round only displayed table values; preserve exact numbers in Qt user data and tooltips.
- [x] Keep the WebEngine renderer and native fallback; retain existing reduced-motion behavior.
- [x] Verify 121 focused tests, compile checks, screenshots, and diff check.
- [ ] Commit and open a stacked draft PR.
