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
- En Windows, ningún shim batch llega a `Popen`; Gemini usa Node nativo más la entrada instalada de su paquete o falla como `UNAVAILABLE`. Los metacaracteres del prompt siguen siendo un único argumento.
- Una segunda ejecución no trunca ni reutiliza logs anteriores; stdout/stderr no pueden ser la misma ruta y las colisiones se rechazan antes de crear el proceso.
- Un `thread_id`/`session_id` del proceso principal no puede contarse como subagente nativo; solo IDs hijos observados pueden hacerlo.

Referencias primarias consultadas el 2026-11-02: [Codex CLI](https://learn.chatgpt.com/docs/cli/reference), [Codex non-interactive JSONL](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Gemini headless JSONL](https://geminicli.com/docs/cli/headless/), [Gemini CLI reference](https://geminicli.com/docs/cli/cli-reference/) y [Gemini subagents](https://geminicli.com/docs/core/subagents/).

---

### Task 1: Define Typed Runtime Contracts and FakeRuntime

**Files:**
- Create: `scripts/agent_runtime.py`
- Test: `tests/test_agent_runtime.py`

**Interfaces:**
- Create frozen `RuntimeRequest(run_id: str, task_id: str, role: str, prompt: str, cwd: Path, stdout_path: Path, stderr_path: Path, timeout_seconds: float, writable: bool, cost_acknowledged: bool)`; reject empty IDs/role, timeout values that are not finite and positive, and NUL in prompt.
- Create `RuntimeCapabilityStatus` enum (`SUPPORTED`, `UNSUPPORTED`, `UNKNOWN`) and `RuntimeCapabilities(provider: str, available: bool, version: str | None, features: tuple[str, ...], sandbox_effective: bool | None, native_subagents: RuntimeCapabilityStatus)`; use explicit unknown values rather than inferring support from a prompt or process start.
- Create `RuntimeStatus` enum (`RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, `UNAVAILABLE`), frozen `RuntimeHandle(token: str, run_id: str, provider: str, process_id: int | None)`, and frozen `RuntimeResult(schema_version: int, run_id: str, provider: str, status: RuntimeStatus, exit_code: int | None, provider_session_id: str | None, stdout_path: Path, stderr_path: Path, stdout_sha256: str, stderr_sha256: str, started_at_utc: str, finished_at_utc: str, observed_child_agent_ids: tuple[str, ...], error: str | None)`.
- Define `AgentRuntime` method signatures exactly: `discover_capabilities() -> RuntimeCapabilities`; `launch(request: RuntimeRequest) -> RuntimeHandle`; `stream_or_collect(handle: RuntimeHandle) -> RuntimeResult`; `cancel(handle: RuntimeHandle) -> RuntimeResult`; `timeout(handle: RuntimeHandle) -> RuntimeResult`; `status(handle: RuntimeHandle) -> RuntimeStatus`; `cleanup(handle: RuntimeHandle) -> None`.
- Implement `FakeRuntime` for deterministic contract tests. It records invocations and exposes scripted status transitions; `stream_or_collect()` preserves an already terminal `CANCELLED`, `TIMED_OUT`, `FAILED`, or `UNAVAILABLE` status instead of converting it to success. It never identifies itself as Codex, Gemini, or a real provider run.

- [x] **Step 1: Write contract tests.** Add `test_fake_runtime_records_provider_request`, `test_fake_runtime_terminal_results_are_schema_versioned`, `test_timeout_and_cancel_statuses_are_distinct`, `test_collection_preserves_cancelled_and_timed_out_terminal_status`, `test_cleanup_is_idempotent`, and `test_runtime_request_rejects_nonfinite_timeout_and_nul_prompt`. Assert exact status/field values, not only non-emptiness.
- [x] **Step 2: Run `python -m unittest discover -s tests -p test_agent_runtime.py -v` and record expected missing-interface failures.**
- [x] **Step 3: Implement the records, protocol, and FakeRuntime in `scripts/agent_runtime.py`.** Use only the standard library and keep provider-specific parsing out of this module.
- [x] **Step 4: Run the focused tests and the full `python -m unittest discover -s tests -v` suite plus `python scripts/validate_skill.py`.** Report the two known local Windows symlink privilege errors separately if they recur.
- [x] **Step 5: Commit `feat: define agent runtime contract`.**

### Task 2: Add Codex and Gemini CLI Runtime Adapters

**Files:**
- Create: `scripts/provider_runtimes.py`
- Test: `tests/test_provider_runtimes.py`

**Interfaces:**
- Implement `CodexRuntime` and `GeminiRuntime` against the Task 1 `AgentRuntime` protocol.
- Implement `create_runtime(provider: str) -> AgentRuntime`, accepting only the explicit values `codex` and `gemini`; it never falls back.
- Give each adapter a pure `build_argv(request: RuntimeRequest) -> tuple[str, ...]` method. Codex chooses `read-only` or `workspace-write` from `request.writable`; Gemini uses `--sandbox` and non-YOLO default approval. Do not claim the Gemini argv enforces a read-only workspace.
- Capability discovery may invoke only the selected executable's `--version` and `--help` (or provider command help), with bounded timeouts; it must not start a model session or inspect credentials.
- Build argv as an array with `shell=False`. Require `request.cost_acknowledged` before provider launch. Request the existing least-privilege mode supported by each CLI, but report `sandbox_effective=None`/`UNVERIFIED` until runtime evidence proves enforcement.
- Never pass Windows `.cmd`/`.bat` shims to `subprocess`; for Gemini's npm shim, resolve and invoke its package JavaScript entry point via native `node.exe`, or report the adapter unavailable. Do not use a shell wrapper or manually shell-quote prompt text.
- Reserve stdout/stderr log paths exclusively for one run: they must differ, must not already exist or belong to another run, and must be created without truncation. Reject collisions before spawning a provider.
- Parse Codex JSONL (`thread.started`, terminal turn/error events) and Gemini `stream-json` (`init`, terminal `result`, error events). Set session IDs only from those protocol fields; leave `native_subagents` unverified unless a child-agent ID/event is actually observed.

- [x] **Step 1: Add tests for explicit provider selection, no fallback when executable/help flags are missing, cost-ack rejection before spawn, no-shell argv construction and permission-claim limits, bounded capability discovery, provider session ID extraction, and malformed/no-terminal/failure JSONL.** Fixtures test parsers only and must be described as parser tests, not provider E2E.
- [x] **Step 2: Run `python -m unittest discover -s tests -p test_provider_runtimes.py -v` and record failures before implementation.**
- [x] **Step 3: Implement Codex/Gemini adapters in `scripts/provider_runtimes.py`.** Keep detected support distinct from runtime behavior proven by a paid CLI session.
- [x] **Step 4: Run provider-adapter tests, full unittest suite, and structural validator.** No provider model/session calls are permitted in this task.
- [x] **Step 5: Commit `feat: add Codex and Gemini runtime adapters`.**

**Review correction round 1 (blocking before Task 3):**
- [x] Add regression coverage that rejects Windows batch shims or resolves Gemini to native `node.exe` plus the installed `gemini.js` entry point; assert no batch shim is passed to `Popen`, prompt metacharacters stay a single argv element, and missing native components yield UNAVAILABLE.
- [x] Exclusively create run logs, reject stdout/stderr aliases and existing/reserved paths before spawn, and add a regression showing a second run cannot alter or relabel the first run's evidence.
- [x] Run the focused provider adapter suite and record exact results in the task report.
- [x] Obtain a scoped re-review against base `f791473bdab826a438f9035cf3842671ca6266c3` before continuing to Task 3.

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
