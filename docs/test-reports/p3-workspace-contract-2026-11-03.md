# P3.1 workspace contract evidence — 2026-11-03

## Status

`EXPERIMENTAL`. This increment supplies a versioned generic contract and validator for dynamic workspace metadata. It does not build the desktop application, load/render artifacts, or validate SIR science.

## Verified in this environment

- Windows 11 environment, Python 3.14.0.
- `python -m unittest discover -s tests -p test_scientific_workspace.py -v`: **16 tests, 15 passed, 1 skipped**.
- The skipped case attempts to create a directory symlink and is skipped because this Windows session lacks symlink-creation privilege (`WinError 1314`). Lexical traversal and path containment tests passed. The Linux PR CI should exercise the symlink escape test.
- Contract tests cover JSON round-trip/example validation, immutable detached records, unknown fields/schema versions, artifact compatibility and references, duplicate IDs/paths including Unicode normalization, collection/text bounds, Win32-forbidden names/8.3 aliases, ADS/drive/traversal syntax, directory-root validation, relative path resolution, and symlink escape when available.

## Not run / pending

- Full repository test suite: `NOT_RUN` for this increment; deferred to the cumulative P2/P3 verification gate because the existing integration suite is slow and P2.1's prior full run was interrupted.
- Linux CI, Windows CI on Python 3.11/3.12, and the P3 PR workflow: `NOT_RUN` at report creation; PR CI evidence must be checked and recorded separately.
- Native GUI renderer, artifact reader, plot configuration, generated-code execution, provenance/hash checks, and SIR integral workflow: `NOT_RUN` / out of scope.
- Actual SIR validation remains `BLOCKED` on receiving equations, units, initial conditions, and experimental data.

## Limits and security boundary

The validator accepts metadata only and never executes expressions or project files. It rejects path traversal and existing symlink/junction escapes during resolution, but returns a `Path`, not a race-free file descriptor; consumers opening mutable untrusted project trees require an OS-level secure-open policy. Artifact existence, type, hash, provenance, size, contents, and scientific validity are not checked. Path policy is intentionally conservative across Windows and POSIX platforms.

## Review findings

The independent path review found two reproducible minor defects: a DOS 8.3 alias could name the same existing file under two artifact paths, and a file could be accepted as the project root. Both were fixed with regressions (reject `~digits` aliases; require an existing directory). The final read-only re-review found no remaining findings.

## Architecture decision

Use one strict JSON v1 contract and an allowlisted reusable component catalog as the boundary between specialist agents and the eventual optional visual core. Keep model-specific scientific files as artifacts. This avoids per-model GUI rewrites and prevents manifests from becoming executable plugin/config payloads.
