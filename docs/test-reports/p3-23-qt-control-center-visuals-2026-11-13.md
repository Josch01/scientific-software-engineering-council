# P3.23 · Qt Scientific Control Center visuals

Status: implementation complete locally; PR/CI pending. The refresh applies a
shared charcoal/violet theme to the control center and embedded workspace, uses
the same palette in Qt WebEngine charts and native fallbacks, shortens the
active-project label while retaining its full path as a tooltip, and adds small
route/series transitions with reduced-motion support. No scientific engine,
contract, solver, or approval behavior changed.

## Evidence

- `PASS` 47 focused Qt tests: control-center shell, embedded workspace, chart
  renderers, WebEngine local-content restrictions and computed dark chart
  background/series color.
- `PASS` Python compile check for the 4 modified Qt modules.
- `PASS` `git diff --check`.
- `PASS` visual render at 1440 × 920; screenshot:
  `docs/test-reports/assets/p3-23-scientific-control-center.png`.
- `PASS` sampled contrast: secondary text 7.95:1; selected text 6.88:1; chart
  series samples 6.37:1–8.26:1 against the chart surface.
- Qt WebEngine was already installed and was used; no software was installed.

The screenshot uses `sir_profiled_analysis_workspace_demo`, a synthetic
fixture. The thesis model and selected DGE series remain `NOT_RUN`; the
interface appearance is not evidence of scientific validity. Linux visual QA
is `NOT_RUN`. The native chart fallback is covered by the focused tests.

## Decisions and follow-up

- A shared `scientific_ui_theme.py` keeps the desktop and chart palettes aligned.
- WebEngine remains local-only with its existing content restrictions; no CDN,
  remote resources, or fonts were added. System Segoe UI was loaded only for
  offscreen screenshot capture; the app uses the system font stack.
- `SSEC_REDUCED_MOTION=1` disables Qt route fades; chart CSS honors
  `prefers-reduced-motion`.
- Next: connect the thesis-specific model/data loader and analysis workflow to
  this UI after the model increment is reviewed. Do not treat the synthetic
  demo as the user's real SIR run.

Branch: `codex/p3-23-scientific-control-center-visuals`, based on
`codex/p3-22-run-history`. No merge or release performed.
