# P3.16 — native scientific result views

## Context

The PySide6 workspace already loads digest-verified resources and has fixed renderers, but `fit_summary` and `sensitivity_plot` currently appear as inert JSON. `ObservationEvaluation.to_dict()` provides versioned observation values and residuals, yet the workspace contract has no dedicated residual component. `scientific_core` has no uncertainty estimator or uncertainty-result schema. Qt WebEngine is present in the current development environment; no installation is needed.

## Design

Keep numerical algorithms and result contracts independent from Qt. Add presentation adapters for existing versioned records:

- `fit_summary` consumes `LeastSquaresFit` schema v1 and shows fit status, cost, work counts, and an accessible parameter table (initial value, fitted value, bounds, and units only when declared).
- `sensitivity_plot` consumes `OdeSensitivity` schema v1 and renders configured state/parameter derivative series over time.
- Add a `residual_plot` workspace component for `ObservationEvaluation` schema v1. It shows observed/simulated values and residuals against observation time, using the supplied time/variable units and observation provenance.
- Attach loader-verified source resource ID/path/SHA-256 to each component view. Do not infer missing source-data provenance or units.
- `uncertainty_summary` remains inert JSON with an explicit `NOT_CALCULATED`/`NOT_ASSESSED` notice. No interval, band, uncertainty estimate, or new uncertainty schema is introduced.

Sensitivity and residual plots use a local, SSEC-authored HTML/SVG view hosted by optional Qt WebEngine. Data is accepted only after bounded schema/shape/finite-number validation; labels are serialized as text. The page uses a restrictive CSP, has no network or local-file access, and exposes no Python/Qt JavaScript bridge. Hover inspection and legend toggles provide interaction. A native QtPainter/data-table fallback remains available when Qt WebEngine is absent.

## Scientific interpretation

Fit residuals/cost, local sensitivity, practical identifiability, and statistical uncertainty remain separate quantities. The UI shows supplied values and methods without computing identifiability or uncertainty. Missing units or provenance are labeled as not supplied. Digests establish byte integrity only, not source authenticity or scientific validity.

## Out of scope

No solver, optimizer, sensitivity algorithm, uncertainty estimator, provider call, project-code execution, generated HTML/JavaScript, remote asset, or dependency installation. The real user SIR remains `NOT_RUN` until equations and data are provided. Qt WebEngine is an optional presentation layer; headless scientific contracts remain usable without it.

## Verification

Add deterministic schema/view tests for valid and malformed result payloads, axes, bounds and provenance. Add offscreen Qt tests for each renderer, `NOT_ASSESSED` uncertainty display, and no remote content/bridge. Keep the synthetic example labeled as software evidence and do not claim scientific validity.
