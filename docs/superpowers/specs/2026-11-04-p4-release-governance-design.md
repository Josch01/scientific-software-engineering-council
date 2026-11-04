# P4.5 — Security and release governance documents

## Intent

Make SSEC's trust boundaries and release blockers explicit so contributors can use the application without mistaking declared evidence for authenticated provenance or software tests for scientific certification.

## Goals and non-goals

- Add a threat model and a release-candidate checklist at the paths required by `CODEX_MASTER_MISSION.md`.
- Describe only controls supported by the code, tests, CI, or existing reports; label gaps `NOT_RUN`, `UNVERIFIED`, or `BLOCKED`.
- Make both files part of structural package validation.
- Do not add security mechanisms, dependencies, release automation, a license, or scientific claims in this increment.

## Approaches

1. **Two focused documents plus mandatory-path validation (chosen):** readable, traceable, and aligned with the existing release policy.
2. Expand `references/RELEASE_POLICY.md` only: less discoverable and fails to provide the two contract-required artifacts.
3. Add a machine-readable release inventory: requires new schemas and evidence producers that do not exist yet.

## Constraints

The repository has no `LICENSE`; the owner must decide licensing. The release gate intentionally blocks unverifiable self-reported evidence. Real-provider, three-project benchmark, full independent security review, and user SIR evidence remain separate gates. No merge, tag, or release is authorized.
