# P3.1 — Scientific workspace contract design

## Intent

Give agents a versioned, structured way to configure project workspaces from a stable component catalog. This is the contract foundation for later scientific views; it does not build the visual application or assume the still-unspecified modified SIR.

## Approaches

1. **Versioned declarative JSON with an allowlisted component catalog (selected).** Portable between the skill and app, deterministic to validate, and keeps model-specific content in project artifacts.
2. **A separate GUI/plugin implementation for each model.** Rejected because it rewrites the visual core and couples the UI to a particular scientific model.
3. **Arbitrary HTML/Python or plugin code inside the workspace manifest.** Rejected because the manifest is agent-authored input and must remain inert; code execution requires a separate reviewed execution boundary.

The user authorized autonomous continuation and asked for dynamic workspaces with reusable components and a stable optional GUI core. The selected contract is a narrow first increment of that requirement.

## Goals

- Define `schema_version=1` with a model card, named artifacts, ordered pages, and reusable components.
- Register stable component kinds for model overview/equations/parameters, simulation plots, optimization, sensitivity, uncertainty, results, audit, and project files.
- Validate exact fields, identifiers, references, compatible artifact kinds, duplicate IDs/paths, and bounded collections/text.
- Restrict artifact references to safe project-relative paths and provide a resolver that rejects paths escaping the project root, including existing symlink/junction resolution where supported.
- Reject path aliases that are unsafe or ambiguous across Windows/Linux/macOS: drive/ADS colons, Windows-reserved characters/devices, DOS 8.3 short-name suffixes, control characters, leading/trailing ASCII spaces, trailing dots, and case/Unicode-normalization collisions.
- Serialize validated contracts deterministically so portable skill and future app can share them.
- Reject arbitrary executable/config payloads; component content and model equations remain data, not evaluated code.

## Non-goals

- No GUI, renderer, arbitrary component plugin loading, SIR equations/data, equation parser, numerical solver changes, generated-code execution, authentication, or scientific certification.
- This validator does not prove a referenced data file's scientific provenance or correctness. A future loader must verify file hashes, media contents, and trust policy before display/use.

## Contract

Add `scripts/scientific_workspace.py` with immutable workspace/page/component/artifact records and `validate_workspace(data)` / `resolve_artifact_path(project_root, relative_path)`. Schema v1 uses exact keys: workspace `{schema_version, model, artifacts, pages}`, model `{id, title, summary}`, artifact `{id, kind, path}`, page `{id, title, components}`, and component `{id, kind, title, artifact_ids}`. IDs are unique within artifact, page, or component namespaces. Strict versioned keys prevent silently accepting fields that may later imply execution. Component kinds have compatible artifact kinds. Paths use POSIX separators in JSON and reject absolute paths, empty/dot/parent segments, Windows path syntax and aliases; resolution must remain under the canonical project root.

The manifest carries model title/summary and artifact references, not equations encoded as executable expressions. An equations component displays content from a declared `model_definition` artifact. Generated source can be cataloged as a `source_code` artifact, but this contract never executes it.

## Acceptance

- A minimal JSON example validates and round-trips with stable versioned serialization.
- Unknown fields/component kinds, duplicate identifiers or paths, undeclared/incompatible artifact bindings, unsafe paths, and over-limit collections fail explicitly.
- A path that resolves outside the project root is rejected; symlink-specific tests may skip only when the Windows host denies symlink creation. The resolver returns a checked path, not a race-free file descriptor; a future artifact reader must secure the open operation against concurrent symlink replacement.
- Focused contract tests and structural validation pass. Full-suite verification is reserved for the cumulative P2/P3 phase close; PR CI evidence is reported separately.
- No SIR-specific workspace or scientific-validity claim is reported as verified.

## Windows portability basis

The portable manifest rejects colons (including NTFS alternate data streams), the Win32 reserved filename characters, reserved device basenames even with extensions, DOS 8.3 aliases ending in `~digits`, leading/trailing ASCII space aliases, and trailing dot aliases. Microsoft documents these naming and stream rules in [Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file) and [File Streams](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams). Path duplication uses NFKC plus casefold as a conservative cross-platform collision key. The resolver also requires an existing directory as its project root.
