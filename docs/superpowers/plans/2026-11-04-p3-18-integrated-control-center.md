# P3.18 Integrated Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one optional Qt desktop application with shared project navigation, the existing scientific workspace, and a Qt agent-supervisor page.

**Architecture:** Add a `ControlCenterWindow` shell that embeds `ScientificWorkspaceWindow` and routes category navigation to existing workspace sections. Add a focused supervisor widget that reuses policy, agent preparation, CLI runner and progress contracts without importing the Tk main loop.

**Tech Stack:** Python 3.11+, optional PySide6, Qt Widgets/QProcess, existing `configuration`, `prepare_agents`, `run_agents`, safe workspace loader.

**Spec:** `docs/superpowers/specs/2026-11-04-p3-18-integrated-control-center-design.md`

## Global Constraints

- Do not add or install dependencies.
- Do not merge to `main`, publish a release or invoke a provider/model.
- Load workspace resources only through the existing SHA-256/containment safe loader.
- Require explicit human confirmation before starting a real agent CLI; preserve cancellation and `NOT_APPROVED` terminal semantics.
- Project and generated code remain inert; only existing host-approved scientific actions can run.
- Keep the Qt app optional; headless tools and portable skill remain usable without it.

## Review Focus

- Canceled/failed project selection preserves the active project and loaded workspace; test dialog cancel and load error.
- Missing category components produce an explicit empty state instead of silently showing unrelated content; test all category mappings.
- Declined agent-run confirmation starts no process and writes no run artifacts; test the rejection path.
- Malformed/oversized progress events do not produce progress or approval status; test through the bounded parser.
- Process start failure/cancel/exit zero never becomes approved; test each terminal status without a provider call.

---

### Task 1: Define route mapping and workspace signals

**Files:**
- Modify: `scripts/scientific_workspace_qt.py`
- Create: `scripts/scientific_control_center_qt.py`
- Test: `tests/test_scientific_control_center_qt.py`

**Interfaces:**
- `workspace_section_index(view_model, category) -> int | None` finds the first section containing the category's existing component types.
- `ScientificWorkspaceWindow.auditResultChanged` emits only the completed audit result mapping for the shell to display.

- [x] Add tests for route-to-section mapping, no-match handling, and audit result signal exposure.
- [x] Run the tests and confirm the missing route/signal behavior fails.
- [x] Implement the minimal pure route resolver and signal.
- [x] Run the route/view tests and existing Qt workspace tests.

### Task 2: Add the Qt shell and common project navigation

**Files:**
- Modify: `scripts/scientific_control_center_qt.py`
- Test: `tests/test_scientific_control_center_qt.py`

**Interfaces:**
- `ControlCenterWindow.load_project(project_root, manifest_relative_path)` loads through the embedded `ScientificWorkspaceWindow` and updates shared project state only after success.
- Navigation exposes `Projects`, `Agents`, `Experiments`, `Audits`, `Code`, and `Results`; category links reuse existing workspace sections.

- [x] Add tests for embedded workspace, shared project path, category navigation and cancellation/error state preservation.
- [x] Run the Qt shell tests before implementation and confirm expected failures.
- [x] Implement project selection, shell navigation, embedded workspace and explicit empty states.
- [x] Run Qt shell and workspace navigation regressions.

### Task 3: Port the existing supervisor flow to a Qt page

**Files:**
- Create: `scripts/scientific_control_center_qt.py` supervisor page/controller
- Test: `tests/test_scientific_control_center_qt.py`

**Interfaces:**
- Reuse `config_panel.build_policy()` and `latest_progress_event()`, `prepare_agents.prepare(..., apply=False)`, and `run_agents.plan()`.
- Launch only `kind=audit` through `QProcess` with argv entries, project cwd, bounded log, cancel-file path and the existing CLI arguments.
- Inject a confirmation handler/process factory only at an internal test boundary; production default must always use the human dialog.

- [x] Test policy validation/plan preview, declined confirmation, bounded progress, cancel request, launch failure/retry and exit-zero-unapproved using deterministic local test processes.
- [x] Verify the start/cancel tests fail before implementation.
- [x] Implement start, progress, cancel and terminal error/status handling with no provider calls.
- [x] Run supervisor and integration tests.

### Task 4: Add demonstration and delivery evidence

**Files:**
- Create: `docs/test-reports/p3-18-integrated-control-center-2026-11-04.md`
- Modify: `README.md`, `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/assets/p3-18-control-center.png`

- [x] Launch the application with the checked-in synthetic SIR workspace and capture an actual UI screenshot; no agent provider is invoked.
- [x] Record focused test commands, screenshot/demo command, Linux/provider limitations, defects and architectural decisions.
- [x] Run `py_compile`, focused regression suites and `git diff --check`.
- [ ] Create a draft PR stacked on P3.17; do not merge.
