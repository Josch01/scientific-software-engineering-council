# P3.13 — workspace proposals in the PySide6 frontend

## Goal

Expose the existing safe P3.11 proposal service in Qt, plus manual JSON import, complete diff review, and human approval. Keep provider execution mocked in tests and leave real provider use `NOT_RUN`.

## Steps

1. Add offscreen Qt regressions for quota-confirmation decline, selected-resource dispatch, worker failure/cancellation, manual import, diff review, and create-only approval; observe failures before implementation.
2. Add Qt request/review dialogs and a cancellable worker around the existing `generate_workspace_proposal` service.
3. Reuse `preview_workspace_proposal` / `approve_workspace_proposal`; never auto-approve, overwrite sources, or execute generated code.
4. Document the Qt proposal route and update the feature matrix/report.
5. Run the focused workspace and Qt suite, compile/diff checks, then push a draft PR stacked on P3.12.

## Acceptance checks

- No provider call starts without an explicit quota confirmation.
- Only selected loader-verified resources enter the existing generation service.
- Failure, cancel, or unavailable provider never produces an approved workspace.
- Generated and manually imported JSON both pass existing loader/contract validation and show a complete bounded diff.
- Approval writes a digest-named copy and preserves the active manifest/resources.
- No real CLI/model call or new dependency is used during development.
