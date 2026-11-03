# P3.2 safe workspace resource loader plan

**Goal:** Safely load bounded workspace artifacts into immutable bytes only after same-handle containment and digest verification.

**Design:** `docs/superpowers/specs/2026-11-03-p3-safe-workspace-loader-design.md`.

**Files:** `scripts/scientific_workspace.py` (share strict parsing of bounded raw JSON), new `scripts/scientific_workspace_loader.py` (safe open/read/hash/API and CLI), `tests/test_scientific_workspace_loader.py`, `references/SCIENTIFIC_WORKSPACES.md`, `SKILL.md`, roadmap and evidence report.

## Tasks

- [x] Add focused failing tests for digest-required loading, exact verified bytes, mismatch rejection, all-or-nothing results, byte budgets, safe manifest path, and metadata-only CLI output.
- [x] Add cross-platform tests for traversal/symlink escape, non-regular files, and supported handle behavior; skip only Windows symlink fixture creation blocked by `WinError 1314`. Prove streaming reads stop at `budget + 1` and failures expose no partial result.
- [x] Factor strict bounded JSON-byte parsing so both P3.1 validation CLI and loader use the same duplicate-key, nesting, UTF-8, and finite-number rules.
- [x] Implement descriptor/handle-based containment, bounded reads, mandatory SHA-256, and immutable loaded records; do not return reopenable paths as verified content. Include POSIX `O_NONBLOCK`; normalize Windows extended/UNC final handle paths and compare with component-aware `commonpath`.
- [x] Implement the metadata-only loader CLI with exit 0/2 and document use in the portable skill reference.
- [ ] Run focused Windows and Docker/Linux tests, full repository suite once, `py_compile`, CLI checks, and `git diff --check`. Focused Windows/Linux and full Linux passed; full Windows local is `NOT_RUN`; branch CI pending.
- [x] Obtain one independent security review; fix only critical/important findings and rerun targeted regressions.
- [x] Update P3.2 evidence/roadmap, commit and push a separate branch, open draft PR #24 stacked on P3.1, attach it, and record the pending CI run #106 without merging.
- [ ] Record final run #106 status and adjust the evidence report/feature matrix if CI differs from local evidence.
