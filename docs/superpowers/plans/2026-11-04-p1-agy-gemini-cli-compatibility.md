# P1 — AGY compatibility for the Gemini CLI slot

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let SSEC route the logical Gemini provider through the already-installed AGY CLI when explicitly selected, using its official headless protocol.

**Architecture:** Preserve `gemini` as the logical provider and default binary. `SSEC_GEMINI_CLI=agy` selects AGY in both the audit runner and `AgentRuntime`; a dedicated adapter translates permissions/argv and validates AGY NDJSON events. Invalid or unsupported configuration fails closed.

**Tech Stack:** Python standard library, `unittest`, AGY CLI headless NDJSON.

**Spec:** User request to use the local `agy` CLI for P1.4; [AGY headless docs](https://antigravity.google/docs/cli/headless/) and [execution modes](https://antigravity.google/docs/cli/modes/).

## Global Constraints

- No model invocation during implementation; the prior one-time provider call was already consumed by the failed Gemini attempt.
- Default remains the installed `gemini` command. No fallback from an explicitly selected `agy` binary.
- Never pass `--dangerously-skip-permissions`; retain `--sandbox`, use session-only `--settings '{"agentMode":""}'` for default-mode reviewers, and `--mode accept-edits` for disposable worker copies.
- Do not claim sandbox enforcement or real-provider integration from help probes or fixtures.

## Review Focus

- AGY NDJSON must bind one init/result `conversation_id`, require successful terminal status, and reject malformed or duplicate data: parser tests.
- A configured AGY must not silently accept per-run Gemini admin-policy files it cannot enforce: request test.
- CLI selection must be consistent between the legacy audit runner and `AgentRuntime`: command-construction tests.
- A failed/absent AGY binary must not fall back to Gemini: discovery test.
- Real AGY authentication and SSEC end-to-end remain `NOT_RUN` until newly authorized.

---

### Task 1: Add opt-in AGY runtime mapping

**Files:**
- Modify: `scripts/provider_runtimes.py`
- Modify: `scripts/run_agents.py`
- Test: `tests/test_provider_runtimes.py`
- Test: `tests/test_runner.py`
- Modify: `references/PROVIDER_MODES.md`, `INSTALLATION.md`, `docs/roadmap/FEATURE_MATRIX.md`
- Create: `docs/test-reports/p1-agy-gemini-adapter-2026-11-04.md`

**Interfaces:**
- `SSEC_GEMINI_CLI` accepts only `gemini` (default) or `agy`.
- `create_runtime("gemini")` returns `GeminiRuntime` by default and `AgyGeminiRuntime` for explicit `agy` selection.
- The logical persisted provider remains `gemini`.

- [x] Add failing argv, environment selection, and AGY NDJSON tests.
- [x] Implement explicit command resolution and event parsing without weakening existing Gemini/Codex behavior.
- [x] Document permissions and the unverified real-provider boundary.
- [x] Run focused tests, `compileall`, validator, and `git diff --check`.
- [x] Commit the focused increment.
