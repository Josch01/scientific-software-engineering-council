# P3.1 workspace contract implementation plan

Implement `docs/superpowers/specs/2026-11-03-p3-workspace-contract-design.md` in isolation on `codex/p3-workspace-contract`, based on P2.1.

## Files and responsibilities

- `scripts/scientific_workspace.py`: strict immutable v1 records, component/artifact registry, validation, safe artifact path resolution.
- `tests/test_scientific_workspace.py`: valid round-trip, schema failures, component bindings, limits, Windows path aliases, relative-path and project-root containment.
- `examples/scientific_workspace_minimal.json`: inert, explicitly generic contract example.
- `references/SCIENTIFIC_WORKSPACES.md`: contract, safe use, catalog, and SIR/GUI boundaries.
- `SKILL.md`: portable skill discovery path.
- `docs/roadmap/FEATURE_MATRIX.md`: P3.1 status and remaining renderer/UI limits.
- `docs/test-reports/p3-workspace-contract-2026-11-03.md`: evidence, platform results, and pending work.

## Tasks

1. Write contract behavior tests first and run only `test_scientific_workspace.py`; confirm each missing behavior fails clearly.
2. Implement strict immutable records and validators, then rerun focused tests. Do not evaluate expressions or execute referenced files.
3. Add the example and user documentation; keep all current artifact readers/renderers out of scope.
4. Confirm Windows path handling rejects ADS, reserved device aliases, trailing dot/space, forbidden characters, and case/Unicode-normalization path collisions. Symlink escape tests skip only on Windows privilege denial; Linux CI covers the actual symlink case.
5. Run focused tests and structural validation; rely on the new PR's CI for Windows/Linux where available. Defer one full repository suite until the cumulative P2/P3 gate to avoid repeating the slow integration suite after every small increment.
6. Review the diff, record findings/limits, commit and push a separate draft PR targeting P2.1. Do not merge or release.
