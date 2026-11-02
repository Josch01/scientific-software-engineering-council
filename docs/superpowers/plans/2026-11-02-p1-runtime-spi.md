# P1 Runtime SPI and Provider Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct provider subprocess coupling with one typed runtime contract, Codex/Gemini adapters, and an integrated worker runner that preserves provider selection and truthful process evidence.

**Architecture:** A provider-neutral `AgentRuntime` SPI owns process lifecycle and typed results. Codex and Gemini adapters inspect local version/help, construct argv without a shell, collect structured output, and never fall back to another provider. A `FakeRuntime` supports control-flow tests only; its use will not be reported as provider E2E. Sandbox effectiveness and native-subagent delegation remain unverified until runtime events prove them.

**Tech Stack:** Python 3.11 standard library, `dataclasses`, `enum`, `typing.Protocol`, `subprocess`, and `unittest`.

**Spec:** `docs/CODEX_MASTER_MISSION.md`, sections 2.1–2.4 and P1 items 1, 2, 5, 7; `docs/architecture/ADR-001-runtime-boundaries.md`.

## Global Constraints

- `codex`: solo Codex como agente principal; `gemini`: solo Gemini como agente principal; `both`: ambos pueden ejecutar trabajos diferentes con contratos explícitos.
- No asumas que todas las versiones de CLI tienen las mismas opciones. Obtén versiones reales con `--version`/`--help` y consulta documentación oficial vigente.
- No confundas subagentes nativos del proveedor con procesos CLI independientes.
- En CI no se ejecutan llamadas a proveedores pagos; las pruebas con FakeRuntime no sustituyen ni se reportan como E2E real.
- No realices una ejecución real con coste no medido sin aprobación explícita; no inspecciones credenciales ni las copies al resultado.
- Un worktree no equivale a un sandbox de SO; distingue sandbox solicitado de sandbox efectivo verificado.
- No hagas merge a `main`, no publiques releases ni instales software externo.

## Review Focus

- El modo `codex` o `gemini` no puede invocar ni sustituir silenciosamente al otro proveedor; probar ausencia de CLI sin fallback.
- Un flag solicitado en el argv no demuestra un sandbox efectivo; las capacidades deben conservar estado `UNVERIFIED` hasta evidencia real.
- Timeout y cancelación deben terminar el proceso y mantener estados distintos de `FAILED`/`SUCCEEDED`.
- Salida JSONL malformada, sin evento terminal o con fallo explícito no puede reportar ejecución exitosa.
- Un `thread_id`/`session_id` del proceso principal no puede contarse como subagente nativo; solo IDs hijos observados pueden hacerlo.

Referencias primarias consultadas el 2026-11-02: [Codex CLI](https://learn.chatgpt.com/docs/cli/reference), [Codex non-interactive JSONL](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Gemini headless JSONL](https://geminicli.com/docs/cli/headless/), [Gemini CLI reference](https://geminicli.com/docs/cli/cli-reference/) y [Gemini subagents](https://geminicli.com/docs/core/subagents/).

---

### Task 1: Define Typed Runtime Contracts and FakeRuntime

**Files:**
- Create: `scripts/agent_runtime.py`
- Test: `tests/test_agent_runtime.py`

**Interfaces:**
- Create frozen `RuntimeRequest(run_id, task_id, role, prompt, cwd, stdout_path, stderr_path, timeout_seconds, writable, cost_acknowledged)`.
- Create `RuntimeCapabilities(provider, available, version, features, sandbox_effective, native_subagents)`; use explicit `UNKNOWN`/`UNVERIFIED` values rather than inferring support from a prompt or process start.
- Create `RuntimeStatus` enum (`RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, `UNAVAILABLE`) and frozen `RuntimeHandle`/`RuntimeResult` records. `RuntimeResult` carries `schema_version=1`, run/provider IDs, exit code, provider session ID, stdout/stderr paths and SHA-256, timestamps, and observed child-agent IDs.
- Define `AgentRuntime` method signatures exactly: `discover_capabilities() -> RuntimeCapabilities`; `launch(request: RuntimeRequest) -> RuntimeHandle`; `stream_or_collect(handle: RuntimeHandle) -> RuntimeResult`; `cancel(handle: RuntimeHandle) -> RuntimeResult`; `timeout(handle: RuntimeHandle) -> RuntimeResult`; `status(handle: RuntimeHandle) -> RuntimeStatus`; `cleanup(handle: RuntimeHandle) -> None`.
- Implement `FakeRuntime` for deterministic contract tests. It records invocations and exposes scripted status transitions but never identifies itself as Codex, Gemini, or a real provider run.

- [ ] **Step 1: Write contract tests.** Test required result schema version/fields, FakeRuntime launch and terminal collection, timeout versus cancellation statuses, cleanup idempotence, and invocation recording.
- [ ] **Step 2: Run `python -m unittest discover -s tests -p test_agent_runtime.py -v` and record expected missing-interface failures.**
- [ ] **Step 3: Implement the records, protocol, and FakeRuntime in `scripts/agent_runtime.py`.** Use only the standard library and keep provider-specific parsing out of this module.
- [ ] **Step 4: Run the focused tests and the full `python -m unittest discover -s tests -v` suite plus `python scripts/validate_skill.py`.** Report the two known local Windows symlink privilege errors separately if they recur.
- [ ] **Step 5: Commit `feat: define agent runtime contract`.**

### Task 2: Add Codex and Gemini CLI Runtime Adapters

**Files:**
- Create: `scripts/provider_runtimes.py`
- Test: `tests/test_provider_runtimes.py`

**Interfaces:**
- Implement `CodexRuntime` and `GeminiRuntime` against the Task 1 `AgentRuntime` protocol.
- Implement `create_runtime(provider: str) -> AgentRuntime`, accepting only the explicit values `codex` and `gemini`; it never falls back.
- Capability discovery may invoke only the selected executable's `--version` and `--help` (or provider command help), with bounded timeouts; it must not start a model session or inspect credentials.
- Build argv as an array with `shell=False`. Require `request.cost_acknowledged` before provider launch. Request the existing least-privilege mode supported by each CLI, but report `sandbox_effective=None`/`UNVERIFIED` until runtime evidence proves enforcement.
- Parse Codex JSONL (`thread.started`, terminal turn/error events) and Gemini `stream-json` (`init`, terminal `result`, error events). Set session IDs only from those protocol fields; leave `native_subagents` unverified unless a child-agent ID/event is actually observed.

- [ ] **Step 1: Add tests for explicit provider selection, no fallback when executable/help flags are missing, cost-ack rejection before spawn, no-shell argv construction, bounded capability discovery, provider session ID extraction, and malformed/no-terminal/failure JSONL.** Fixtures test parsers only and must be described as parser tests, not provider E2E.
- [ ] **Step 2: Run `python -m unittest discover -s tests -p test_provider_runtimes.py -v` and record failures before implementation.**
- [ ] **Step 3: Implement Codex/Gemini adapters in `scripts/provider_runtimes.py`.** Keep detected support distinct from runtime behavior proven by a paid CLI session.
- [ ] **Step 4: Run provider-adapter tests, full unittest suite, and structural validator.** No provider model/session calls are permitted in this task.
- [ ] **Step 5: Commit `feat: add Codex and Gemini runtime adapters`.**

### Task 3: Route Development Workers Through AgentRuntime

**Files:**
- Modify: `scripts/development_runner.py`
- Test: `tests/test_development_worktrees.py`
- Modify: `references/WORKTREE_DEVELOPMENT.md`
- Modify: `docs/roadmap/FEATURE_MATRIX.md`

**Interfaces:**
- Preserve `execute(project, task_id, task, *, launch=False, cost_ack=False, parallel=1, minutes=60)` behavior and add only a keyword-only runtime factory/injection seam for tests.
- Preview must not call `discover_capabilities()` or `launch()`. Real launch must still require `--accept-unmetered-cost` and route each worker only to its assigned provider.
- Worker results include runtime status, provider session ID, log paths/hashes, and observed child-agent IDs. A parent process/session ID is not a subagent ID.
- Missing/unsupported provider returns an explicit blocked/failed runtime result; it cannot substitute another CLI. Timeout and cancellation call the runtime contract methods.

- [ ] **Step 1: Add runner tests using `FakeRuntime` for preview without discovery, mode-specific dispatch for Codex-only/Gemini-only/both, no provider fallback, explicit cost acknowledgement, timeout and cancellation propagation, and result-to-mailbox handoff without privileged statuses. Add one local Python child-process test for process/log lifecycle only; label it as such, not provider E2E.**
- [ ] **Step 2: Run the focused worktree suite and capture expected failures against the current direct-`Popen` runner.**
- [ ] **Step 3: Refactor `development_runner.py` to use `create_runtime()` and the Task 1 protocol while preserving its CLI and preview semantics.**
- [ ] **Step 4: Update docs and matrix to identify runtime adapter coverage, `NOT_RUN` real Codex/Gemini E2E, `UNVERIFIED` native subagents/sandbox effectiveness, and P1 work still pending.**
- [ ] **Step 5: Run focused tests, full unittest suite, and structural validator. Inspect that no provider calls or credential access occurred.**
- [ ] **Step 6: Commit `refactor: route development workers through runtimes`.**
