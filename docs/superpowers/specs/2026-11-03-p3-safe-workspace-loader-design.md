# P3.2 safe scientific workspace resource loader

## Intent

Allow the SSEC engine and headless tools to consume declared workspace artifacts only after their path is contained in a selected project root and their bytes match the manifest's SHA-256. This connects P3.1's structural manifest to future scientific components without requiring a GUI.

## Goals

- Accept the existing schema v1 manifest and portable relative resource paths.
- Require a declared lowercase SHA-256 for every resource being loaded.
- Open regular files under a selected project root without following an escaping symlink/junction. POSIX opens each path component relative to a directory descriptor with `O_NOFOLLOW` and `O_NONBLOCK` before checking regular-file type. Windows compares the final canonical path from the already-open handle to the canonical root using component-aware `commonpath`, normalizing `\\?\\` drive and UNC forms.
- Hash and capture bytes through the same open descriptor/handle; expose bytes only after a matching digest.
- Bound per-resource and aggregate bytes and fail the whole load without returning partial resources.
- Provide a CLI that prints a metadata-only verified summary and exits 2 on invalid or unsafe input.

## Non-goals and anti-goals

- No execution, import, rendering, CSV parsing, unit interpretation, decompression, or scientific validation of file contents.
- No arbitrary path access, automatic hash creation, network fetch, or trust/authenticity claim from SHA-256.
- No GUI, model-specific SIR schema, provider invocation, or OS sandbox.
- Do not return a path that a downstream consumer must reopen after verification.

## Approaches

1. **Path-only resolver:** reject. A consumer reopening the returned path can race with replacement after validation; it also leaves verified bytes undefined.
2. **Read through one verified OS handle and return captured bytes:** selected. It keeps the file identity stable from containment check through hashing and consumption; explicit size budgets bound memory. POSIX uses directory-relative opens with no-follow flags; Windows checks the final path from the already-open file handle against the canonical root. Unsupported handle semantics fail closed.
3. **Separate sandboxed worker/service:** defer. It is not needed to read bounded data artifacts and would add infrastructure without executing untrusted code.

## Contract and calls

- Add `scripts/scientific_workspace_loader.py`, separate from the P3.1 schema validator; the module is also directly executable as the CLI.
- Public API: `load_scientific_workspace(project_root, manifest_relative_path) -> LoadedWorkspace`; loaded resources are immutable records containing the declared ID/kind/path/digest and verified `bytes`.
- Manifest and artifacts must be project-relative and read with the same root-containment policy. The existing JSON byte/depth/duplicate-key/non-finite checks are reused.
- Initial budgets: at most 16 MiB per resource and 64 MiB aggregate, configurable only downward by callers. Reject non-regular files and missing digests. If any resource fails, return no `LoadedWorkspace`.
- CLI: `python scripts/scientific_workspace_loader.py --project-root PROJECT_ROOT MANIFEST_RELATIVE_PATH`; print only workspace/resource IDs, sizes, and digests with status `ARTIFACT_DIGESTS_MATCHED`. Exit 0 when declared hashes match, 2 on failure. This status is not a scientific-validity claim.
- `SHA256_VERIFIED` means the captured bytes match the manifest digest. It does not authenticate who created either the manifest or artifact.

## Constraints

Use the Python standard library only. Test Windows and Linux. Skip only symlink-fixture cases that cannot be created due to Windows host policy (`WinError 1314`), and report that exact limitation. Read at most `budget + 1` bytes before rejecting an over-budget stream; test that bound directly. Any future component must consume the returned bytes or an equivalent still-open verified handle, not reopen the path.

## Acceptance

Valid files load with exact bytes and digest; missing/mismatched hashes, path traversal, symlink/junction escapes, non-regular files, over-budget resources, invalid manifests, and unsupported safe-open behavior fail closed. Tests prove that mismatch or unsafe paths yield no partial loaded result and that CLI output never contains resource contents. No scientific validity is inferred.
