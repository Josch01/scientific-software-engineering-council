# P3.24 — Thesis SIR workspace in the Control Center

## Goal

Let a researcher inspect the thesis SIR definition, import the selected DGE
reconstruction JSON, enter explicit model parameters, run the P2.5 forward
model after confirmation, inspect calculated output, and export the result.

## User flow

1. Open **SIR de tesis** in the existing Qt Control Center.
2. Choose a reconstruction JSON. Read it as a bounded, regular local file and
   pass its bytes to `parse_dge_reconstruction_json`; only
   `DGE_monday_sunday_candidate` is used. The source remains read-only.
3. Enter the harmonic count, coefficients, frequencies, initial state, gamma,
   ascertainment fraction, and one of the declared delay scenarios. No
   scientific parameter is pre-filled.
4. Review the input path, source digest, selected series, parameters, fixed RK4
   step and result destination in a human confirmation dialog.
5. Run `evaluate_thesis_sir_weekly_counts` in a `QThread`. Show no invented
   percentage. On success, show observed-vs-predicted weekly counts and the S/I/R
   boundary trajectory using the existing chart component.
6. Export the versioned result JSON only to a user-selected new/existing output
   file; never overwrite the selected input source.

## Boundaries

- Reuse the P2.5 model/data contracts, existing RK4 implementation and Qt chart
  component. Do not add fitting, sensitivity, uncertainty or another solver.
- Do not import or execute project Python, call an external model provider, or
  run the user's thesis data during development tests.
- Preserve `NOT_ASSESSED` validity, identifiability and uncertainty statuses.
- Invalid inputs, user rejection and worker errors cannot produce a success
  result. Disable duplicate runs while a worker is active.
- The chart remains local-only with the existing Qt WebEngine restrictions and
  native fallback.

## Acceptance evidence

- Qt tests cover JSON source selection/loading, required-parameter validation,
  human rejection, successful synthetic execution, worker failure, and export
  preserving the source file.
- Focused Windows Qt tests and available Linux CI pass. Thesis-data simulation
  remains `NOT_RUN` until the user conducts the confirmed run.
