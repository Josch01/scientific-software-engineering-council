# P3.16 — native scientific result views

## Delivery status

P3.16 implements native PySide6 views for the existing fit, local-sensitivity, and observation-evaluation contracts. The user SIR remains `NOT_RUN`; the checked-in example is a synthetic software/UI fixture and does not support a scientific claim.

The workspace contract now registers `observation_evaluation` and `residual_plot`. Fit and sensitivity results are displayed from their versioned schema v1 records. Residual coordinates retain their `(time, variable)` mapping, including sparse rows, and supplied residuals are checked against simulated minus observed values. Views show verified source resource IDs, paths, and SHA-256 digests. Digests establish byte equality with the manifest only.

Qt WebEngine renders SSEC-authored local SVG with hover inspection and legend toggles. Trace rendering is sampled to at most 2,001 endpoints while hover values come from the validated original series. The only permitted page load is Qt's initial `data:text/html` document; later navigation is blocked, remote and local-file access are disabled, and there is no JavaScript-to-Python bridge. Documents over 2,000,000 UTF-8 bytes use QPainter and a bounded table to stay below the local WebEngine data-URL budget. The fallback displays both axis labels. Uncertainty remains inert JSON marked `NOT_ASSESSED / NOT_CALCULATED`; no estimator, interval, or confidence band was added.

## Commits

- `eb36f8e` — register residual workspace component.
- `2386c67` — add scientific result view models.
- `47fd70c` — add local scientific chart widget.
- `3e6b396` — render scientific results in Qt.
- Documentation/report and review-fix commit: pending.

All commits are on `codex/p3-16-native-science-views`, based on P3.15 (`7ba39e9`). No merge to `main` was performed.

## Verification

Targeted checks completed on Windows with Python 3.14 and the existing PySide6/Qt WebEngine environment:

- Manifest/generation tests: **28 passed**; includes deterministic residual-view proposal validation without provider use.
- Scientific view adapters, including actual `scientific_core` output records: passed.
- Qt renderers: passed; fit ordering/bounds, sensitivity axes, observed/simulated/residual display, units/provenance, and explicit uncertainty status covered.
- WebEngine local chart: passed; the HTML script rendered SVG, CSP/data-only labels were checked, and external navigation was rejected.
- QtPainter fallback: rendered to a Qt image and passed a nonblank-pixel assertion.
- Generic template validator: `VALID`, exit 0.
- Synthetic example loader: `ARTIFACT_DIGESTS_MATCHED`, exit 0.
- Final focused regression after independent review fixes: **114 passed, 1 skipped** in 13.633 s across the app registry, manifest/generation, view models, scientific adapters, Qt charts/renderers, and secure loader modules. New cases cover a WebEngine chart beyond the JavaScript argument limit, native fallback for large pages, visible fallback Y-axis labels, bounded fit-residual rows, and unit mismatch rejection.
- `python -m py_compile` for changed Python modules: passed.
- `git diff --check`: passed.
- Full `python -m unittest discover -s tests -v`: **534 tests, 7 skipped, 2 errors, 2 failures** in 1,364.875 s. Two errors were Windows symlink-creation failures (`WinError 1314`); one failure was the skill validator requiring the checkout root folder to match skill frontmatter; the other was the Tk renderer registry missing the new `residual_plot` route. The Tk registry regression was fixed and the focused suite above passed afterward. The full suite was not rerun after this focused fix to avoid repeating a 22-minute run; full-suite status is therefore not green.

## Independent review and fixes

An independent read-only review reproduced four P2 issues. They are fixed and covered by the focused regressions: WebEngine no longer spreads large arrays into function arguments and downsamples only the rendered path; oversized local documents use the native fallback; fit residual tables are limited to 200 evenly sampled rows including both endpoints; evaluation views reject model/observation time or variable-unit mismatches; and QPainter now paints the Y-axis label. The mathematical result data is not modified by display sampling.

## Limitations and pending evidence

- Real user SIR equations/data and scientific validity: `NOT_RUN`.
- Linux Qt visual execution and provider CLI invocation: `NOT_RUN`.
- Fit and sensitivity schema v1 do not carry units; the frontend labels these as not supplied unless an explicit trusted unit context is provided. Residual units and time unit come from the evaluation contract.
- No contract or estimator for statistical uncertainty exists; status remains `NOT_ASSESSED / NOT_CALCULATED`.
- Sensitivity is local and does not assess practical identifiability. Fit convergence and residuals do not establish identifiability or model validity.
- In the native fallback, the chart is static; hover and legend interaction require Qt WebEngine. Fit residual tables show at most 200 evenly sampled rows; chart paths show at most 2,001 sampled points per series while tooltips use original validated values.
- Symlink refusal cases needing symlink-creation privileges and the root-folder/frontmatter structure check remain environment/worktree limitations; 7 tests were skipped with platform/environment reasons. These are recorded rather than treated as product verification.
- Independent review: completed; the four reproducible P2 findings above were fixed and the focused regression passed. CI and draft PR state: pending.

## Example

`examples/scientific_workspace_science_views_demo/` contains a SHA-256-verified workspace with all three native views and a visibly marked synthetic uncertainty resource. Open it with:

```text
python scripts/scientific_workspace_qt.py --project-root examples scientific_workspace_science_views_demo/workspace.json
```

The example README states that it is software/UI evidence only. It is not the user's SIR or experimental data.
