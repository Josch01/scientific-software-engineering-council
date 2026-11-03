# P1 Review Snapshot Mode Evidence — Windows Git executable-bit fix

## Problem

SSEC's candidate-tree hash binds each tracked path, exact bytes, and Git's logical executable mode. On Windows, Git's index retains mode `100755`, while a copied review snapshot is commonly materialized with filesystem mode `100666`. `execution_evidence` hashes the former; `review_evidence` currently re-hashes only filesystem modes. A legitimate review snapshot containing a tracked executable therefore fails validation, and downstream integration must block.

## Required design

Persist a strict, canonical, per-path logical executable-mode inventory in versioned review evidence at snapshot capture time. The inventory must be derived from the same validated candidate entries used to capture and hash the snapshot; do not infer modes from the Windows snapshot filesystem. Bind it to the candidate by recomputing the existing candidate-tree digest from the snapshot's actual normalized paths and bytes plus the recorded logical modes, then requiring exact equality with `candidate_tree_sha256` and `review_snapshot_tree_sha256`.

The validator must reject malformed schema/version, extra or missing inventory fields, duplicate or non-normalized paths, invalid boolean values, inventory/path-set mismatch, symlinks/special files, and digest mismatch. Keep the existing snapshot before/after artifact checks. On POSIX, compare inventory modes to physical executable bits and preserve detection of chmod tampering. Existing schema-1 evidence should retain its documented compatibility where safe; new Windows executable evidence must use the new strict version.

No change may remove executable mode from candidate hashes, weaken review manifest validation, mark this case skipped, or treat a hash as provider or scientific authentication. Preserve review-provider independence limitations and fail closed if mode evidence is absent or malformed.

## Acceptance

- A real temporary Git repository with a tracked `100755` file can be copied into a review snapshot on Windows and its successful review manifest validates against the exact candidate tree hash.
- Include an unchanged executable baseline file and a changed executable file where feasible; mode evidence must be per-path.
- Corrupt, duplicate, reorder (if canonical ordering is mandated), omit, add, or alter inventory entries and prove validation blocks; update artifact hashes in tests where needed so the mode-binding validator is exercised rather than only the outer artifact hash.
- The same validation detects POSIX executable-mode tampering and continues to validate normal non-executable snapshots.
- A real review-to-integration regression passes on Windows once this fix is stacked with P1.3; integration's prior executable-mode skip must be removed when the stack is verified.
- Keep provider E2E and scientific validity claims separate and `NOT_RUN` unless independently exercised.
