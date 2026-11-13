# P3.25 implementation plan

Status: implementation complete locally; PR/CI pending.
Evidence: 183 focused Windows tests passed; provider and user SIR remain `NOT_RUN`.

**Goal:** Bind a completed thesis SIR run to the current digest-verified audit flow.

**Architecture:** A pure bundle writer serializes a versioned workspace with
model, selected observations, simulation output, and exact source resources.
The page asks for an output parent and confirmation, then emits the validated
workspace path. `ControlCenterWindow` loads it with the existing loader and opens
the existing audit selector/confirmation; no new runner or provider call.

**Tests first:**
- Write invalid-result, digest, no-overwrite, and resource-inclusion tests.
- Verify current UI state gates the action; rejection/failure keeps it inert.
- Test the Control Center handoff into the existing audit dialog with the
  provider service patched, and prove it is not called until explicit submit.

**Files:** `scripts/thesis_sir_audit_workspace.py`, `scripts/thesis_sir_qt.py`,
`scripts/scientific_control_center_qt.py`, the corresponding test modules,
`docs/roadmap/FEATURE_MATRIX.md`, and a P3.25 report.

**Limits:** synthetic fixtures only; user SIR execution and real CLI audit remain
`NOT_RUN`; validity/identifiability/uncertainty stay `NOT_ASSESSED`.
