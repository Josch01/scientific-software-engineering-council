# P3.31 — Thesis SIR analysis bridge implementation plan

1. Add focused RED tests for synthetic parameter recovery, residual
   provenance, unsupported parameters, and work-budget rejection.
2. Implement a bounded bridge around the existing thesis forward evaluator and
   `scientific_core.fit_least_squares` / `parameter_sensitivities`; add a
   versioned result envelope and strict parameter-domain checks.
3. Add a deterministic synthetic example and command-line entry point; never
   use the supplied thesis JSON or invoke a provider in this increment.
4. Run the focused tests, skill validator, compile check, and diff check; write
   a compact report with exact statuses and limits.
5. Update the feature matrix and submit a draft PR stacked on P3.30.
