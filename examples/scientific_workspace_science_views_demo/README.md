# Synthetic scientific-view demonstration

This workspace exercises the fit, local-sensitivity, and observation-residual views with deliberately synthetic values. It is software/UI evidence only: it is not the user's SIR model, experimental data, an identifiability analysis, or a scientifically validated result. The uncertainty resource is explicitly `NOT_CALCULATED`.

From the repository root, open it with:

```powershell
python scripts/scientific_workspace_qt.py --project-root examples scientific_workspace_science_views_demo/workspace.json
```

The workspace loader verifies each resource SHA-256 before the view model reads it. If Qt WebEngine is unavailable, charts render through the native Qt fallback.
