# P1.4.1 AGY Supervisor Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the existing supervisor explicitly dispatch `agy` audits through `AgyRuntime`, preserving per-role lifecycle evidence without automatic approval.

**Architecture:** Add `agy` as a distinct provider mode and reuse the P1.4 `AgentRuntime` adapter only for those assignments. Codex, Gemini, and `both` retain their current commands and mapping. A successful AGY process remains `EXIT_ZERO_UNREVIEWED`.

**Tech Stack:** Python standard library, existing AgentRuntime/AgyRuntime, Tkinter, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-04-p1-agy-supervisor-dispatch.md`

## Global Constraints

- Do not invoke a provider during implementation or CI.
- Do not map `gemini` to `agy` or add fallback behavior.
- Require the existing explicit unmetered-cost acknowledgement before any process launch.
- Keep `writable=False`, sandbox effectiveness `UNKNOWN`, and human review mandatory.
- Do not turn process success into audit/scientific approval.

## Review Focus

- Unsupported provider modes fail validation before CLI discovery.
- `agy` roles must not accidentally use Codex/Gemini profiles or commands.
- Stop/cancel and the shared deadline reach the runtime control; cleanup still occurs once.
- Missing/invalid AGY response retains failure status and no fabricated session ID.
- Cost acknowledgement failure launches no runtime.

### Task 1: provider mode and role preparation

**Files:** `scripts/configuration.py`, `scripts/prepare_agents.py`, `scripts/config_panel.py`; tests in `tests/test_configuration.py`, `tests/test_provider_modes.py`.

- [x] Add RED tests for accepted explicit `agy`, unsupported mode rejection, role assignment, `profile=null` (no native AGY profile), safe task packets, and `build_policy`/headless GUI validation.
- [x] Run the tests and confirm they fail because `agy` is not currently a provider mode.
- [x] Implement explicit `agy` mode in the config, planner, null profile metadata, worker prompt, and GUI provider validation. Preserve `both` as Codex + Gemini.
- [x] Run the focused tests and retain the expected role/provider mapping. Six focused tests passed; broader config/provider-mode run had 21 pass and 2 `WinError 1314` fixture setup errors before assertions.

### Task 2: runtime-backed AGY worker lifecycle

**Files:** `scripts/run_agents.py`; tests in `tests/test_provider_modes.py`.

- [x] Add RED tests proving AGY uses an injected `AgentRuntime` with the worker snapshot/prompt, `writable=False`, and acknowledged cost; verify success remains `EXIT_ZERO_UNREVIEWED` with session/digests.
- [x] Add failure, cancellation, timeout, cleanup-downgrade and exactly-once cleanup regressions; confirm the cost gate prevents runtime factory calls.
- [x] Implement the AGY-only runtime branch using `RuntimeRequest`, `RuntimeLaunchControl`, status polling, `stream_or_collect`, and `cleanup`; pass a unique per-role run ID and shared deadline from `execute`.
- [x] Run focused worker lifecycle tests and provider runtime regressions. Combined command ran 86 tests: 84 passed, 2 symlink fixtures blocked before assertions by local `WinError 1314`.
- [x] Fix independent-review findings: worker/execute cancellation, timeout, and failure paths use one shared `RuntimeLaunchControl.set()` gate; `cancel_file` is observed at the final spawn gate and after runtime construction.

### Task 3: docs and verification

**Files:** `docs/roadmap/FEATURE_MATRIX.md`, `docs/test-reports/p1-agy-supervisor-dispatch-2026-11-04.md`.

- [x] Document the fake-verified runtime code path and the unverified provider-backed audit, sandbox, isolation, and scientific claims.
- [x] Run `python -m unittest tests.test_configuration tests.test_provider_modes tests.test_provider_runtimes tests.test_runner -q`, `py_compile`, and `git diff --check`; record Windows symlink setup limitations.
- [x] Complete focused independent review of the cancellation gate fix; fix reproducible important findings. A final minor TOCTOU remains if the marker is created after the final check and before `Popen`; documented because the worker cancels after `launch()` returns and no approval is produced.
- [ ] Commit/push a separate branch and open a draft PR stacked on #32; record CI, without merge or release.
