# P3.32 — Qt fit workflow for thesis SIR

## Goal

Expose the P3.31 thesis-analysis bridge in the existing Control Center and load
its calculated results through the existing digest-verified workspace views.

## Scope

- Let the user explicitly select dynamic parameters and inspect initial values,
  contract-domain bounds, and local sensitivity perturbations.
- Require local output-folder selection and human confirmation showing the
  model, selected data/digest, parameters/bounds, RK4 step, and destination.
- Run the exact P3.31 engine and create a new, digest-verified analysis workspace
  in a background `QThread`; preserve all source files.
- Load the verified workspace into the existing results route with native
  simulation, fit, sensitivity, and residual views.
- Keep `NOT_ASSESSED` validity/identifiability and `NOT_CALCULATED` uncertainty.
- Use synthetic observations for tests. No provider/model calls and no supplied
  thesis-data calculation.

## Non-goals

- No new solver or optimizer, fit of initial conditions, ascertainment fraction
  `q`, or discrete delay; no uncertainty or identifiability calculation.
- No cancellation claim; the current optimizer does not expose safe cancellation.
- No GUI rewrite, remote assets, provider calls, merge, or release.

## Acceptance

1. Rejecting confirmation starts no worker and creates no output workspace.
2. Accepted analysis runs off the GUI thread, blocks duplicate/project changes,
   and reports real worker states without fabricated percentage progress.
3. Success creates a new workspace whose resources and view contracts validate,
   then loads it in the same Qt application.
4. Failure/corrupt result loads no workspace; source JSON remains byte-identical.
5. Fit, sensitivity and residual views use the actual P3.31 outputs and units;
   uncertainty, validity and identifiability remain explicitly unassessed.
