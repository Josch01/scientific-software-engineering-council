# P3.5 Supervisor Progress Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show live per-specialist status and bounded progress in the existing supervisor panel.

**Architecture:** Add an optional progress callback to the audit runner and serialize schema-v1 status events to stdout only under `--emit-progress-jsonl`. The GUI already captures runner stdout in its owned log; it will parse valid events into a progress bar and role table while retaining the textual log.

**Tech Stack:** Python standard library, Tkinter/ttk, JSON Lines, `run_agents.execute`.

**Spec:** `docs/superpowers/specs/2026-11-03-p3-supervisor-progress-dashboard-design.md`

## Global Constraints

- Keep CLI output byte-compatible when progress events are not requested.
- Never label process exit as review acceptance; preserve `EXIT_ZERO_UNREVIEWED` and `release_status=NOT_APPROVED`.
- Do not call Codex/Gemini/AGY or add dependencies.
- The GUI consumes an append-only stdout log and remains responsive through its current polling callback.
- Event parsing is bounded and fail-closed; malformed events do not alter status.

## Review Focus

- Concurrent workers must not interleave JSON event bytes; test complete parseable event lines.
- Queued roles must remain `NOT_STARTED` if an earlier wave fails or is canceled; test failure/partial state.
- Status events must never imply approval; assert `EXIT_ZERO_UNREVIEWED` and `NOT_APPROVED` through the final event.
- Malformed/oversized/unknown-schema events must not crash the panel or replace a valid status; test parser behavior.
- Progress-event output must be opt-in; test the default CLI/execute path has no callback side effects.

---

### Task 1: Emit synchronized role progress from the existing runner

**Files:**
- Modify: `scripts/run_agents.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- `execute(..., progress_callback=None)` accepts an optional callback and emits schema-v1 snapshots.
- `run_one(..., on_started=None)` reports a role as `RUNNING` only after `Popen` succeeds.
- CLI flag `--emit-progress-jsonl` prints `SSEC_PROGRESS ` followed by one complete JSON object per event; default output is unchanged.

- [x] Add a failing local-child test for initial, running, and terminal events plus `NOT_APPROVED`.
- [x] Run it and confirm the progress callback/event stream is absent.
- [x] Implement locked event snapshots and the opt-in CLI emitter.
- [x] Run `tests.test_runner`; assert a failed wave leaves later roles `NOT_STARTED`.

### Task 2: Present progress in the supervisor panel

**Files:**
- Modify: `scripts/config_panel.py`
- Test: `tests/test_control_center.py`

**Interfaces:**
- `latest_progress_event(text: str) -> dict | None` extracts the last valid bounded schema-v1 line from the captured log tail.
- The panel shows total/completed progress and one Treeview row per role/provider/status; raw text logs remain available.
- GUI starts `run_agents.py` with `--emit-progress-jsonl` and never promotes an exit to review acceptance.

- [x] Add parser tests for multiple lines, malformed/oversized lines, unknown schema, wrong JSON types, integer overflow and status values.
- [x] Observe parser tests fail before implementation.
- [x] Add progress widget and event parsing/polling; preserve `--check` headless behavior.
- [x] Run the focused supervisor/runner tests.

### Task 3: Verify, document, and deliver

**Files:**
- Modify: `README.md`, `references/RUNNER.md`, `references/CONFIG_PANEL.md`, `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p3-supervisor-progress-dashboard-2026-11-03.md`

- [x] Run a hidden Tk smoke showing per-role status without starting provider CLIs.
- [x] Run Windows focused tests, `py_compile`, and `git diff --check`.
- [x] Run the full Docker/Linux suite and record exact output.
- [ ] Commit, push, and create a separate draft PR targeting P3.4; record CI and keep it unmerged.
