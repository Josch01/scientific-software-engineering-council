# P3.1 scientific workspace manifest implementation plan

> **For agentic workers:** Keep the increment headless and bounded; complete the checklist before creating the draft PR.

**Goal:** Let agents describe a scientific project workspace through a versioned manifest whose resources and reusable view components can later be rendered by the stable GUI core.

**Architecture:** Add `scripts/scientific_workspace.py` with a fixed component/resource registry, a strict schema validator, and a read-only JSON CLI. The validator checks references and portable relative paths only; it does not read or execute artifacts.

**Tech stack:** Python standard library and `unittest`; no installs.

**Spec:** `docs/superpowers/specs/2026-11-03-p3-workspace-manifest-design.md`.

## Global constraints

- No GUI or model-specific equations/data.
- No arbitrary components, HTML, JS, shell commands, or code execution from manifest fields.
- Use portable relative resource paths and no file writes.
- Distinguish structural schema validation from file/path verification and scientific validity.

## Review focus

- Only registered component/resource kinds and their exact config fields are accepted.
- All component references resolve to declared resources of compatible kinds.
- IDs and paths are unique and safe across Windows/Linux syntax, including Win32 reserved names/characters and Unicode case/normalization collisions.
- JSON duplicate keys, non-finite numeric values/constants, deep nesting, invalid UTF-8, and oversized input are rejected consistently.
- The CLI touches only the selected manifest; it never opens resource paths.
- Each component type has an exact config contract, and arbitrary text is inert/escaped by future renderers.
- Example manifest is an empty, model-agnostic structure with placeholders, not evidence of an SIR implementation.

## Task 1: Workspace schema and validator

- [x] Write failing validator tests for resource/component contract and ordering.
- [x] Add failing cross-platform path, duplicate-key, invalid JSON, and size-limit tests.
- [x] Add CLI success/failure tests and assert that referenced artifact files are not opened.
- [x] Implement strict manifest validator, fixed component registry, portable path checks, and read-only CLI.
- [x] Add a model-agnostic workspace template and concise P3.1 evidence report.
- [x] Run focused Windows/Linux tests, `py_compile`, and `git diff --check`.
- [x] Obtain an independent read-only review, fix critical/important findings, and rerun focused tests.
- [x] Update the feature matrix, commit, push, and open a separate draft PR stacked on P2.4; do not merge.
- [ ] Record branch CI results and keep the roadmap state evidence-calibrated.
