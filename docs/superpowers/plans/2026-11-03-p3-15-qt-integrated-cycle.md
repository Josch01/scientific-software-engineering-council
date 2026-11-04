# P3.15 — integrated Qt workspace cycle

## Goal

Prove the existing Qt proposal, human approval, trusted synthetic SIR simulation, and audit request can be used in sequence without model providers or generated-code execution.

## Steps

1. Add one offscreen end-to-end test with mocked proposal/audit providers and observe failure before implementation.
2. Reuse existing validation, approval, and simulation services; do not add orchestration or provider infrastructure.
3. Assert the active source manifest remains unchanged, the approved copy is loaded, the SIR solver returns a verified result, and audit stays not approved/not certified.
4. Update the P3.15 report/feature matrix and run the focused Qt plus workspace regression suite.

## Acceptance checks

- Proposal and audit network/provider calls are mocked; actual CLI use remains `NOT_RUN`.
- Human proposal approval is exercised, then the existing confirmed SIR action runs.
- The audit result remains `NOT_APPROVED` and `NOT_CERTIFIED`; no scientific claim is inferred from the synthetic fixture.
- The original manifest is byte-for-byte unchanged.
