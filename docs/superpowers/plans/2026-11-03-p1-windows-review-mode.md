# Implementation plan — P1 Windows review mode evidence

## Goal

Allow strict review evidence to represent Git's logical executable modes on Windows without weakening candidate-tree binding or POSIX mutation detection.

## Files

- Modify `scripts/check_runner.py` only if `SnapshotReference` must expose its validated logical mode inventory.
- Modify `scripts/development_runner.py` to persist versioned inventory evidence for reviews.
- Modify `scripts/review_evidence.py` to strictly parse inventory and recompute the candidate hash from the snapshot's real file paths/bytes and logical modes.
- Modify `tests/test_review_evidence.py` and focused downstream tests available in this base checkout.
- No dependencies or providers.

## Steps

1. Write failing Windows regressions using a real temporary Git repo: baseline and tracked `100755` cases, including mode inventory tampering and path-set mismatches.
2. Run focused tests and record RED for the current snapshot-stat-only validator.
3. Implement a versioned strict inventory captured alongside snapshot entries, not reconstructed from the Windows snapshot's lost mode bits.
4. Recompute the tree digest from actual snapshot bytes/paths and persisted logical modes; bind it to both review tree digest and candidate identity. On POSIX, require inventory mode to match physical mode.
5. Run focused modules and full suite on Windows; run relevant tests in the already-available Docker Python image if feasible without pulling/installing anything.
6. Record exact output, skip reasons, log hashes, limitations (`NOT_RUN` provider E2E; no scientific-validity claim), and commit this fix on its own branch.
7. Have an independent reviewer inspect the patch. Stack it into P1.3 and run the unskipped Windows review-to-integration regression there.

## Invariants

- No modification to source/worker snapshots while collecting evidence.
- Mode inventory is strict, canonical, and exact-path matched; no coercion of strings/integers to bool.
- Hashes still include executable mode, path, size, and exact bytes.
- Artifact before/after checks and provider-independence caveats remain intact.
- No merge to `main`, release, external software install, paid provider call, or scientific validity claim.
