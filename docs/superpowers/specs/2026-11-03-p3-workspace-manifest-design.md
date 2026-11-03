# P3.1 scientific workspace manifest

## Intent

Give agents a versioned, portable contract for arranging reusable scientific views around project artifacts. This increment supplies a headless validator and built-in component registry IDs; it does not build the desktop GUI or execute artifacts.

## Manifest shape

- `schema_version: 1`, workspace ID/title/optional description.
- Ordered `resources`: stable ID, artifact kind, portable project-relative path, optional expected SHA-256.
- Ordered `sections`: stable ID/title and ordered `components`.
- Each component has a fixed registry `type`, title, resource references, and a type-specific config object.
- Built-in resource kinds: model spec, observations, simulation result, fit result, sensitivity result, uncertainty result, audit report, source code, generic artifact.
- Built-in components: equation view, parameter table, observation table, simulation plot, fit summary, sensitivity plot, uncertainty summary, audit summary, artifact browser, and code view.
- Components accept references only to compatible resource kinds. The schema has no fields for custom HTML, scripts, shell commands, callbacks, or executable expressions.

### Fixed registry

| Component | Required resource kind | Exact config |
|---|---|---|
| `equation_view` | one `model_spec` | `{}` |
| `parameter_table` | one `model_spec` | `{}` |
| `observation_table` | one `observations` | `{}` |
| `simulation_plot` | one `simulation_result` | `{"x_axis":"time","series":[name,...]}`; 1–50 unique names |
| `fit_summary` | one `fit_result` | `{"parameter_names":[name,...]}`; 1–50 unique names |
| `sensitivity_plot` | one `sensitivity_result` | `{"state_names":[...],"parameter_names":[...]}`; each 1–50 unique names |
| `uncertainty_summary` | one `uncertainty_result` | `{"quantities":[name,...]}`; 1–50 unique names |
| `audit_summary` | one `audit_report` | `{}` |
| `artifact_browser` | 1–100 resources of any kind | `{}` |
| `code_view` | one `source_code` | `{"language":"python"|"json"|"markdown"|"text"}` |

Each resource has exactly `id`, `kind`, `path`, and optional `sha256`. IDs match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. SHA-256 is 64 lowercase hex characters. Component IDs are unique across the workspace; resource IDs and section IDs are each unique in their own namespace. Resource paths are unique under NFKC+casefold comparison.

## Safety and validation

- Validate IDs, schema version, exact keys, resource references, uniqueness, bounded counts/text, and config fields.
- Resource paths use portable `/` separators and reject absolute paths, drive/UNC prefixes, backslashes, empty/dot/traversal segments, and NUL. Path uniqueness is textual after NFKC+casefold normalization, not physical-file identity. The validator does not resolve paths, follow symlinks, read resources, verify hashes against files, or execute files; a future loader must enforce containment and verify an expected digest before display.
- JSON CLI loading rejects duplicate keys, non-finite constants, invalid UTF-8, and oversized manifests.
- Bound the manifest to 1 MiB, nesting to 32 containers, resources to 500, sections to 100, components to 1,000, references/config-name lists to 100, path length to 512 characters/32 segments, and user text to 4,096 characters. Read only `MAX_BYTES + 1` before deciding size.
- Reject Windows-forbidden/control characters in path segments, ADS colons, trailing spaces/periods, reserved device basenames (including superscript COM/LPT forms), and any basename stem ending in `~` plus digits (short 8.3-alias-looking names regardless of prefix). Cross-platform tests apply the same policy on Windows and Linux.
- Treat descriptions, titles, and labels as inert text; a renderer must escape them. Schema-key validation cannot make arbitrary UI rendering safe.
- A valid manifest proves only structural compatibility. It does not prove artifact existence, model correctness, unit consistency, numerical validity, or scientific validity.

## Limits

This is a layout/resource contract and headless validator only. No GUI, dynamic rendering, file preview, scientific model parser, artifact loader, or SIR-specific schema is implemented. `uncertainty_summary` is a reusable view contract; it does not implement uncertainty analysis.

## Acceptance

- Validate a model-agnostic workspace manifest covering core scientific views and artifact resources.
- Reject unsafe paths, missing/duplicate references, incompatible resource kinds, unknown component/config fields, duplicate JSON keys, and oversized input.
- A CLI validates a manifest with stable JSON summary and exit 0 on valid, exit 2 on invalid; it never opens, stats, or resolves referenced resources.
- Reject deeply nested JSON, invalid UTF-8, `1e400`, boolean schema version, and byte-limit overflow with the same portable failure code.
- Tests exercise portability/security invariants and verify no artifact file is opened or executed.
- No external dependency or GUI package is added.
