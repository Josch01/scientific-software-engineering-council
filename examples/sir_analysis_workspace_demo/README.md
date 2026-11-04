# SIR analysis workspace demonstration

This is a reproducible software demonstration built from the checked-in SIR v1 fixture. It solves the declarative model with the existing RK4 solver, samples those synthetic trajectories as observations, then calls the existing fit, sensitivity, and observation-residual APIs. The workspace links each analysis panel to the verified model and observation resources so the view can derive units and show provenance.

The observation values are generated from the same model used for fitting. They are synthetic and do not establish scientific validity or practical identifiability. The current least-squares implementation returns `STALLED` for this exact fixture; the displayed status is preserved, and the recovered rates are shown without relabeling the optimizer result as convergence. Uncertainty is `NOT_CALCULATED` and no intervals or bands are shown. The user's SIR equations and experimental data remain `NOT_RUN` because they have not been provided.

Open the workspace from the repository root:

```powershell
python scripts/scientific_workspace_qt.py --project-root examples/sir_analysis_workspace_demo workspace.json
```

Regenerate the deterministic model, observations, results, hashes, and manifest:

```powershell
python scripts/build_sir_analysis_demo.py
```

Pass `--output-dir <directory>` to build a copy elsewhere. The generated `code/build_sir_analysis_demo.py` is displayed as text and is never executed by the workspace viewer.
