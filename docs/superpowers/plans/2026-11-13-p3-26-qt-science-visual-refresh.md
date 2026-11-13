# P3.26 Qt Science Visual Refresh Implementation Plan

Status: implementation complete locally; PR/CI pending.
Evidence: 69 focused Windows tests, WebEngine keyboard interaction, screenshot,
compile check and diff check pass.

> **For agentic workers:** Implement natively in this session, task by task; use TDD and keep the diff confined to the Qt theme, chart renderer, tests, and report.

**Goal:** Give the existing SSEC desktop control center a polished charcoal/violet visual system and more readable animated scientific charts.

**Architecture:** Keep PySide6 as the native application shell and local Qt WebEngine as an optional SVG chart renderer. Share semantic palette tokens with the Qt chart fallback; preserve the existing CSP and business/scientific contracts.

**Tech Stack:** Python, PySide6, Qt WebEngine, inline SVG/CSS/JavaScript, unittest.

**Spec:** `docs/superpowers/specs/2026-11-13-p3-26-qt-science-visual-refresh.md`

## Global Constraints

- No new package, CDN, external font, provider request, model/data execution, or unrestricted project code.
- Keep Qt native fallback, CSP, user confirmation, and scientific engine contracts intact.
- Use synthetic fixtures only; scientific validity remains `NOT_ASSESSED` and the user's thesis SIR remains `NOT_RUN`.
- Honor `SSEC_REDUCED_MOTION` in Qt and `prefers-reduced-motion` in local chart HTML.

## Review Focus

- Text contrast after lightening surfaces: test normal text against each main palette surface at 4.5:1 or greater.
- Reduced motion enabled: test Qt transition opt-out and CSS animation suppression.
- Six-series chart: test series patterns, palette cycling, label, legend, and tooltip survive rendering.
- WebEngine unavailable: keep the tested native chart fallback and shared colors.
- Untrusted chart labels: retain existing base64 payload encoding and restrictive no-network CSP.

## Files

- Modify `scripts/scientific_ui_theme.py` for tokens and native Qt styles.
- Modify `scripts/scientific_workspace_qt_charts.py` for chart presentation only.
- Modify `tests/test_scientific_control_center_qt.py`, `tests/test_scientific_workspace_qt.py`, and `tests/test_scientific_workspace_qt_charts.py` for regression coverage.
- Update `docs/roadmap/FEATURE_MATRIX.md` with P3.26 evidence and the completed P3.25 CI result.
- Add `docs/test-reports/p3-26-qt-science-visual-refresh-2026-11-13.md` and one synthetic screenshot under `docs/test-reports/assets/`.

### Task 1: Charcoal/violet Qt design tokens

**Test first:** Add assertions for token values, readable text contrast across background/sidebar/surface/raised surfaces, focus selectors, and reduced-motion route transitions. Run the named test to see expected failures.

**Implement:** Update palette in `scientific_ui_theme.py`, improve toolbar/navigation/card/form/table/button states and visible keyboard focus, and keep native chart colors sourced from the same tokens.

**Verify:** Run control-center, theme, thesis-page, and native chart tests; capture the current-project route at 1440×920 and confirm visible focus/hover/disabled states.

### Task 2: Scientific SVG chart polish

**Test first:** Assert axis title/units, all series names, tooltip, distinct line patterns, palette colors, local-only CSP, and both motion-preference paths in generated chart HTML.

**Implement:** Improve spacing/grid/legend/tooltip and add a short SVG line-draw entrance animation. Keep existing numeric values and rendering algorithm unchanged.

**Verify:** Run chart tests with WebEngine available and native fallback tests. Render the same synthetic chart and inspect the PNG for unclipped labels, legible legend, and data-consistent traces.

### Task 3: Evidence and handoff

- Record the focused test count and compile/diff results in the short P3.26 report.
- Mark WebEngine visual QA Windows, Linux CI, user SIR execution, and scientific validity separately; do not imply a scientific result from the screenshot.
- Commit, push, and open a separate draft PR based on P3.25; do not merge or release.
