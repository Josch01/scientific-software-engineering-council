# P3.25 — Auditable SIR run handoff

## Goal

Let a user prepare a digest-verified workspace from a completed thesis SIR run
and open the existing specialist-audit selection flow in the Qt Control Center.

## Flow

1. After a successful SIR calculation, the user selects a parent folder and
   confirms creation of a new audit bundle.
2. SSEC copies only normalized selected observations, the declarative model and
   explicit parameters, the computed result, and exact SIR engine/adapter source
   into a unique new folder. The imported source JSON and thesis PDF remain
   untouched and are not copied.
3. SSEC validates the manifest, resource digests, and rendered workspace through
   the existing secure loader before opening it in the app.
4. The Control Center opens the existing audit resource selector. A separate
   existing confirmation is still required before selected bytes reach a local
   provider CLI. No provider is called while creating the bundle.

## Boundaries

- Bundle creation requires a current `COMPUTED_FROM_DECLARED_INPUTS` result whose
  model, observations, and source digest match the page state.
- Never overwrite an existing output directory or modify the selected source.
- Use current workspace v1 resource/component contracts and `load_project`; do
  not add a second audit runner or scheduler.
- Audit output remains informative, `NOT_APPROVED`, and does not certify
  scientific validity, identifiability, or uncertainty.
- Tests use deterministic synthetic inputs and patch the provider boundary. A
  real provider call and the user's thesis data remain `NOT_RUN`.

## Acceptance

- A completed synthetic run produces a manifest/resource set accepted by the
  secure loader and Qt view; each resource hash matches its exact bytes.
- The bundle contains only the selected observations and declared artifacts;
  it includes source-code bytes for the model and observation adapter.
- A rejected/failed export creates no workspace and makes no audit request.
- The loaded bundle reaches the existing resource-selection UI, where the user
  must separately approve provider submission.
- Reopen/confirmation and audit service regressions pass without a real provider
  call.
