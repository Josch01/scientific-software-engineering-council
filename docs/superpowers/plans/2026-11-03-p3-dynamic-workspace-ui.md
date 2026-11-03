# P3.3 Dynamic Scientific Workspace UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open a hash-checked scientific workspace and render its manifest-configured sections in a reusable, inert Tkinter desktop shell.

**Architecture:** Extend the safe loader to retain a deeply immutable copy of the exact validated manifest. A pure bounded presentation layer creates view data from that definition and captured resource bytes. A fixed Tkinter renderer registry creates section tabs and safe components; unknown payload schemas remain plain bounded text.

**Tech Stack:** Python standard library, Tkinter/ttk, `scientific_workspace_loader`, `scientific_core.ObservationDataset`.

**Spec:** `docs/superpowers/specs/2026-11-03-p3-dynamic-workspace-ui-design.md`

## Global Constraints

- No additional dependency or installation.
- Never reopen artifact paths after loader verification.
- Never execute project or agent-generated code in the app process.
- Manifest config selects only registered component types.
- Displaying results does not establish scientific validity.
- Preserve the current CLI/API and the loader's digest/budget/containment behavior.
- Bound the view to 100 rendered components, 1 MiB per JSON resource, 2 MiB total unique JSON, 32 KiB JSON text previews, 256 KiB text previews, and 1,000 table rows.

## Review Focus

- Mutating a returned layout cannot change the validated configuration: test recursive immutability.
- Duplicate JSON keys, non-finite values, excessive depth/size, and invalid UTF-8 must fail closed: test the decoder.
- A source artifact is rendered as bounded text and never imported or evaluated: test view-model content and inert dispatch.
- Malformed simulation dimensions or an unavailable configured series must become a visible component error, not crash the workspace: test component status.
- Large resources must be preview-bounded while retaining safe loader byte limits: test truncation and limits.

---

### Task 1: Retain the validated manifest in immutable loader output

**Files:**
- Modify: `scripts/scientific_workspace_loader.py`
- Test: `tests/test_scientific_workspace_loader.py`

**Interfaces:**
- `LoadedWorkspace.manifest: Mapping[str, object]` contains the validated manifest recursively converted to read-only mappings and tuples.
- `load_scientific_workspace(...)` reads no path a second time and continues to return no partial result.

- [ ] Add tests that the loaded manifest includes its dynamic sections and rejects nested mutation.
- [ ] Run the focused loader tests and observe the missing property/mutability failure.
- [ ] Implement recursive freezing after same-handle parse and validation.
- [ ] Re-run loader tests and existing manifest tests.

### Task 2: Build a bounded inert presentation model

**Files:**
- Create: `scripts/scientific_workspace_view.py`
- Create: `tests/test_scientific_workspace_view.py`

**Interfaces:**
- `build_workspace_view_model(workspace: LoadedWorkspace) -> WorkspaceViewModel`
- Registered view types: `equation_view`, `parameter_table`, `observation_table`, `simulation_plot`, `fit_summary`, `sensitivity_plot`, `uncertainty_summary`, `audit_summary`, `artifact_browser`, `code_view`.
- Each component carries an `ok` or `error` status and a safe, bounded payload; no component executes content.

- [ ] Add tests for duplicate keys/non-finite/deep JSON, source-as-text, observation contract data, valid simulation series, malformed simulation series, unknown result payloads, and preview truncation.
- [ ] Run the new view tests and observe failures before implementation.
- [ ] Implement strict bounded JSON decoding, simulation contract extraction, observation parsing, generic text fallback, and fixed component dispatch.
- [ ] Re-run view and loader tests.

### Task 3: Add a dynamic Tkinter desktop shell and headless CLI

**Files:**
- Create: `scripts/scientific_workspace_app.py`
- Modify: `SKILL.md`, `README.md`, `references/SCIENTIFIC_WORKSPACES.md`
- Test: `tests/test_scientific_workspace_app.py`

**Interfaces:**
- `python scripts/scientific_workspace_app.py --project-root ROOT MANIFEST` opens the optional desktop UI.
- `python scripts/scientific_workspace_app.py --check --project-root ROOT MANIFEST` securely loads and prepares view models without importing/initializing Tk.
- `create_workspace_window(workspace_view_model)` builds tabs by manifest section with fixed safe renderers.

- [ ] Add CLI tests for successful `--check`, invalid digest failure, and no Tk import in check mode.
- [ ] Run CLI tests and observe failures before implementation.
- [ ] Implement the ttk shell, keyboard-first navigation, visible labels/focus, empty/error states, plot legend and accompanying table, and inert code/text rendering.
- [ ] Re-run app/view/loader tests and the repository validation command.
- [ ] Attempt a real window smoke test only when a GUI display is available; record `NOT_RUN` otherwise.

### Task 4: Record evidence and roadmap status

**Files:**
- Modify: `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-dynamic-workspace-ui-2026-11-03.md`

- [ ] Record exact commit, commands, Windows/Linux evidence, real-UI state, data schema limits, and missing-SIR state.
- [ ] Run focused tests, `python scripts/validate_skill.py`, `python -m unittest discover -s tests -q`, and `git diff --check` where runtime allows.
- [ ] Commit and push the P3.3 branch; create a draft PR targeting the P3.2 branch.

