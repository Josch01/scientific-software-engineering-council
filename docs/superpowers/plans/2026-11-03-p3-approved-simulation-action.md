# P3.6 Approved scientific simulation action

**Goal:** Let a trusted host inject an approved callback for a `simulation_plot`; require a human confirmation before execution and render only a validated `OdeSolution` in the workspace.

**Spec:** `docs/superpowers/specs/2026-11-03-p3-approved-simulation-action-design.md`

## Steps

1. [x] Add API/UI regressions: no callback by default, declined confirmation executes nothing, approved callback receives the verified workspace, invalid output never appears as a result.
2. [x] Implement `ApprovedSimulationAction`, optional callback injection, per-component action button, confirmation, daemon-thread execution and bounded error/result display.
3. [x] Validate `OdeSolution` and its bounded simulation projection; add an in-memory result tab without mutating project files.
4. [x] Run focused Windows tests and hidden Tk smoke, Docker/Linux full suite, compilation and `git diff --check`; request one independent static review.
5. [ ] Document limitations and create a separate draft PR targeting P3.5; record CI without merging.

## Guardrails

- Never import callback modules or code from a project or manifest.
- Never execute on workspace load. Every run requires a human confirmation.
- Do not label solver output scientifically valid; do not claim sandboxing.
- If a manifest resource fails SHA-256/containment checks, do not offer or invoke the action.
