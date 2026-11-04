# P3.16 — native scientific result views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Show versioned fit, sensitivity, and observation-residual results in reusable PySide6 views, with local interactive charts and explicit provenance/unit limits.

**Architecture:** Keep numerical contracts in `scientific_core`; add strict presentation adapters in `scientific_workspace_view`. Register one `observation_evaluation` resource kind and `residual_plot` component. Render tables natively and charts through local static HTML/SVG hosted by optional Qt WebEngine, with a QtPainter fallback; project content never becomes HTML or executable code.

**Tech Stack:** Python 3.11+, existing PySide6, optional QtWebEngine already present locally, unittest, QPainter, inline SVG/JavaScript only.

**Spec:** `docs/superpowers/specs/2026-11-04-p3-16-native-scientific-views-design.md`

## Global Constraints

- No dependency installation, provider call, project-code execution, remote asset, or uncertainty estimator/schema.
- Fit/sensitivity/residuals, practical identifiability, and statistical uncertainty stay distinct.
- Missing units/provenance are displayed as not supplied; SHA-256 proves byte integrity only.
- Uncertainty remains JSON with an explicit `NOT_ASSESSED`/`NOT_CALCULATED` label; never fabricate intervals or bands.
- The user's actual SIR remains `NOT_RUN`; the demo is synthetic software evidence only.

## Review Focus

- Malformed/non-finite/version-mismatched result JSON → view adapter tests reject it without partial plots.
- Sensitivity tensor order or configured axes mismatch → view tests verify [time][state][parameter] selection and fail closed.
- Sparse or reordered residual records → tests preserve `(time, variable)` correspondence instead of assuming a flat time index.
- HTML/script injection in project-supplied labels → chart tests verify base64 data transport, text-only insertion, CSP, no bridge, and no remote/local-file access.
- Missing units/provenance or absent Qt WebEngine → tests show “not supplied” and retain a readable QtPainter/data fallback.

---

### Task 1: Register the observation-evaluation result component

**Files:**
- Modify: `scripts/scientific_workspace.py`
- Modify: `scripts/scientific_workspace_generation.py`
- Test: `tests/test_scientific_workspace.py`
- Test: `tests/test_scientific_workspace_generation.py`

**Interfaces:**
- Consumes: `ObservationEvaluation.to_dict()` schema v1.
- Produces: resource kind `observation_evaluation`; renderer type `residual_plot`; empty component config; generation proposal allowlist entry.

- [x] Write failing tests `test_residual_plot_accepts_observation_evaluation_resource` and `test_residual_plot_rejects_other_kinds_and_config_fields` in `tests/test_scientific_workspace.py`.
- [x] Run those tests and confirm failure is due to the missing registrations.
- [x] Register the exact resource/component mapping in both validators/allowlists; keep manifest schema version 1 because this adds a component/resource kind without changing existing fields.
- [x] Add a deterministic proposal-contract test that permits the new component without provider use.
- [x] Run `python -m unittest tests.test_scientific_workspace tests.test_scientific_workspace_generation -v`; expect focused cases to pass.
- [x] Commit as `feat: register residual workspace component`.

### Task 2: Add strict presentation models for fit, sensitivity, residuals, and provenance

**Files:**
- Modify: `scripts/scientific_workspace_view.py`
- Test: `tests/test_scientific_workspace_view.py`
- Test: `tests/test_scientific_workspace_science_views.py` (new)

**Interfaces:**
- Produce frozen display models `FitSummaryView`, `SensitivityPlotView`, `ObservationEvaluationView`, `ScientificSeriesView`, and `ComponentView.source_resources`.
- Produce builders `build_fit_summary_view(payload, config, unit_context)`, `build_sensitivity_plot_view(payload, config, unit_context)`, and `build_observation_evaluation_view(payload)`; return validated immutable view data only.
- Derive unit labels only from declared SIR v1 units or result fields; unknown models/units stay “not supplied”. Attach referenced `ResourceView` ID/path/SHA-256 from loader-captured bytes.

- [x] Write `test_fit_summary_v1_orders_configured_parameters_and_labels_missing_units` and `test_fit_summary_rejects_nonfinite_cost_and_mismatched_parameters`.
- [x] Write `test_sensitivity_v1_selects_time_state_parameter_axes` and `test_sensitivity_v1_rejects_invalid_tensor_dimensions` for the `[time][state][parameter]` tensor.
- [x] Write `test_observation_evaluation_preserves_sparse_residual_order_and_provenance` and `test_observation_evaluation_rejects_unknown_residual_coordinates`.
- [x] Write `test_component_views_include_resource_path_and_digest` using loader-captured metadata.
- [x] Run focused tests and confirm expected missing-model failures.
- [x] Implement bounded strict builders; reuse existing JSON artifact limits and do not calculate fit, residuals, sensitivity, identifiability, or uncertainty.
- [x] Attach loader-verified resource metadata to each component view and render the uncertainty status as `NOT_ASSESSED` without changing its JSON payload.
- [x] Run `python -m unittest tests.test_scientific_workspace_science_views tests.test_scientific_workspace_view -v`; expect all focused view cases to pass.
- [x] Commit as `feat: add scientific result view models`.

### Task 3: Build a local WebEngine chart with a QtPainter fallback

**Files:**
- Create: `scripts/scientific_workspace_qt_charts.py`
- Test: `tests/test_scientific_workspace_qt_charts.py` (new)

**Interfaces:**
- Produce `build_scientific_chart_html(plot_data) -> str` and optional `ScientificChartWidget`.
- Chart payload contains only validated finite points, bounded series, axis labels/units, and plain text labels. The HTML is SSEC-authored, embeds JSON via base64, uses CSP, blocks navigation, disables remote/file access, and creates no QWebChannel/Python bridge.
- If Qt WebEngine cannot import, display the same bounded series through QPainter and a native table.

- [x] Write `test_chart_html_uses_csp_and_has_no_remote_url_or_bridge`, `test_hostile_labels_are_transported_as_data_not_html`, and `test_chart_rejects_unbounded_series_and_points`.
- [x] Run the focused chart tests and confirm they fail because the chart builder/widget is absent.
- [x] Implement static inline SVG/JavaScript with hover value inspection and legend toggles; use `textContent` for all labels and set a restrictive CSP.
- [x] Add a local WebEngine page that rejects navigation and denies remote/local-file access; implement the QtPainter fallback.
- [x] Write `test_chart_widget_uses_native_fallback_when_webengine_is_unavailable`; test the offscreen WebEngine page when available and skip only that optional runtime case otherwise.
- [x] Run `python -m unittest tests.test_scientific_workspace_qt_charts -v`.
- [x] Commit as `feat: add local scientific chart widget`.

### Task 4: Wire Qt fit, sensitivity, residual, and uncertainty views

**Files:**
- Modify: `scripts/scientific_workspace_qt.py`
- Test: `tests/test_scientific_workspace_qt_views.py` (new)

**Interfaces:**
- `_render_fit_summary` displays a summary and accessible parameter/residual table.
- `_render_sensitivity` and `_render_residual_plot` use the validated chart widget plus a bounded data table and source digest/provenance labels.
- `_render_uncertainty` shows JSON plus the explicit `NOT_ASSESSED`/`NOT_CALCULATED` status; it never draws confidence bands.

- [x] Write `test_fit_renderer_shows_parameters_bounds_units_and_resource_digest`, `test_sensitivity_renderer_shows_axes_series_and_provenance`, `test_residual_renderer_shows_observed_simulated_residuals_and_units`, and `test_uncertainty_renderer_marks_not_assessed`.
- [x] Run those tests and confirm missing renderer/metadata failures.
- [x] Register the three native renderer methods and replace only the current JSON routes for fit/sensitivity; add `residual_plot` and explicit uncertainty labeling.
- [x] Run `python -m unittest tests.test_scientific_workspace_qt_views -v`; expect all renderers to show bounded data and preserve plain-text safety.
- [x] Commit as `feat: render scientific results in Qt`.

### Task 5: Update the dynamic workspace example and durable evidence

**Files:**
- Modify: `examples/scientific_workspace_template.json`
- Modify: `references/SCIENTIFIC_WORKSPACES.md`
- Modify: `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-16-native-scientific-views-2026-11-04.md`

- [x] Add a declared `observation_evaluation` resource and `residual_plot` to the generic template without asserting that corresponding result files exist.
- [x] Add `test_generic_template_includes_observation_evaluation_and_residual_view` to ensure the template manifest validates.
- [x] Document schemas consumed, units/provenance display, WebEngine restrictions/fallback, and the explicit uncertainty limitation.
- [x] Record actual Windows Qt/WebEngine tests, CI state, and Linux/real-SIR/provider paths as `NOT_RUN` where applicable.
- [x] Run `python -m unittest discover -s tests -v`, `python -m py_compile` for changed modules, and `git diff --check`; record exact counts and skip reasons.
- [x] Commit documentation and create draft PR #40 stacked on P3.15 PR #39; leave unmerged.
