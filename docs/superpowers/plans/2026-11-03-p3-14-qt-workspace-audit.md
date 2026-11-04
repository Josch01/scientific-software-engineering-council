# P3.14 — workspace audit in the PySide6 frontend

## Goal

Expose the existing verified-resource audit service in Qt. Keep provider calls mocked in tests, require explicit quota consent, and label every result as unaudited by SSEC and unapproved.

## Steps

1. Add offscreen regressions for resource selection, consent, cancellation, service/start failures, and safe result display; observe failures before implementation.
2. Add an asynchronous Qt worker around `run_workspace_audit`, with a temporary cancellation file retained until the worker exits.
3. Show a bounded read-only report and preserve `NOT_APPROVED` / `NOT_CERTIFIED`; do not treat completed CLI processes as an independent audit.
4. Update concise usage docs, feature matrix, and a test report.
5. Run focused workspace and Qt tests, compile/diff checks, then publish a draft PR stacked on P3.13.

## Acceptance checks

- No audit starts before explicit cost/quota consent and at least one verified resource is selected.
- Only selected resource IDs reach the existing audit service.
- Cancellation, failure, and successful process completion never produce approval or scientific certification.
- Cancellation storage survives until the worker exits; original project resources remain unchanged.
- Development uses mocks only; actual CLI audit stays `NOT_RUN`.
