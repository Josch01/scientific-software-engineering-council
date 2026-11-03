# P3.4 Control Center Workspace Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open the validated P3.3 scientific workspace view from the existing SSEC supervisor window.

**Architecture:** Extend the workspace window factory with an optional parent and project root. The supervisor lazily opens it as a Tk `Toplevel`, using its existing root and project path; the secure loader stays the only resource reader.

**Tech Stack:** Python standard library, Tkinter/ttk, `scientific_workspace_loader`, `scientific_workspace_view`.

**Spec:** `docs/superpowers/specs/2026-11-03-p3-control-center-workspace-link-design.md`

## Global Constraints

- Add no dependency or installation.
- Keep `--check` headless and defer importing Tkinter until a real window is requested.
- Open project resources only through the safe loader; preserve root containment, digest verification, and byte limits.
- Never execute project or agent-generated code or callbacks in the UI.
- Do not invoke Codex/Gemini/AGY in this increment.

## Review Focus

- The supervisor and workspace must share one Tk root/event loop; test the window factory's parent path.
- A missing/invalid current project must fall back to project selection without breaking the supervisor; test root selection helper.
- A canceled manifest picker must have no side effect; test the open flow or manual smoke.
- Invalid/out-of-root resources must still fail through the existing safe loader; retain loader regression coverage.
- `--check` must not import Tk after adding the embedded path; retain subprocess headless test.

---

### Task 1: Support embedding the workspace window

**Files:**
- Modify: `scripts/scientific_workspace_app.py`
- Test: `tests/test_scientific_workspace_app.py`

**Interfaces:**
- `_create_window_root(tk, parent)` returns `tk.Tk()` when `parent is None`, otherwise `tk.Toplevel(parent)`.
- `_project_root_hint(project_root) -> Path | None` returns an existing directory or `None`.
- `create_workspace_window(view_model, *, parent=None, project_root=None)` uses both helpers; an invalid project root keeps the existing root-picker path.

- [ ] Add a failing test for standalone-vs-child window selection through a small root factory helper.
- [ ] Run the test and confirm it fails because the factory always creates `Tk`.
- [ ] Implement the optional parent and project root behavior; preserve the existing CLI.
- [ ] Run the app tests and the existing headless `--check` regression.

### Task 2: Launch the workspace from the supervisor

**Files:**
- Modify: `scripts/config_panel.py`
- Test: `tests/test_configuration.py` or a focused `tests/test_control_center.py`

**Interfaces:**
- `open_scientific_workspace(parent, project_root, *, window_factory=None)` lazily resolves `create_workspace_window` and passes the existing root/project path.
- The supervisor exposes an “Abrir espacio científico” button that calls this helper.

- [ ] Create `tests/test_control_center.py` with a failing test that verifies the supervisor passes its root and selected project to the workspace factory.
- [ ] Run the test and confirm the launch helper is missing.
- [ ] Implement the lazy launch helper and button; keep agent execution flow unchanged.
- [ ] Run focused supervisor and workspace tests.

### Task 3: Record evidence and deliver the increment

**Files:**
- Modify: `README.md`, `references/SCIENTIFIC_WORKSPACES.md`, `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-control-center-workspace-link-2026-11-03.md`

- [ ] Run a hidden Tk smoke using one root and a child workspace window; record `NOT_RUN` only if the host has no display/Tk.
- [ ] Run focused Windows tests, `py_compile`, and `git diff --check`.
- [ ] Run the repository test suite in Docker/Linux once for this increment and record the actual result.
- [ ] Commit the implementation and evidence; push a separate draft PR targeting the P3.3 branch.
