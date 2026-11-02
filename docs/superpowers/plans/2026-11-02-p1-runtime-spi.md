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
- Recolección, cancelación y timeout concurrentes no pueden sobrescribir un resultado terminal ya elegido; cada run publica exactamente un resultado terminal.
- Los IDs de hijos observados se excluyen si coinciden con el ID de sesión padre, incluso si el evento de spawn precede al evento que revela la sesión padre.
- Cancelar/agotar timeout termina y espera el proceso aislado en su grupo/sesión; una falla para terminar el árbol no se presenta como éxito o cancelación confirmada.
- Si peer-stop o deadline vence durante discovery, no se inicia el modelo al terminar la consulta acotada; la verificación de stop/deadline ocurre antes del `Popen` billable.
- `FakeRuntime` conserva el primer resultado terminal después de `SUCCEEDED`, `FAILED`, `UNAVAILABLE`, `CANCELLED` o `TIMED_OUT`, igual que un adaptador real.
- Referencias de mailbox para stdout distinguen directorio de ejecución además del rol; ejecuciones repetidas no apuntan al mismo artifact.
- El mailbox no referencia un artifact inexistente cuando el worker no llegó a crear logs.
- Si falla el comando de terminar el árbol, el runtime no bloquea indefinidamente ni presenta la terminación completa como confirmada.
- La autorización de launch se sincroniza con stop/deadline hasta el punto de creación del proceso; una señal registrada antes de `Popen` impide spawn.
- Tras terminar el proceso CLI principal, los miembros que sigan vivos en su grupo/Job Object se terminan antes de calcular/publicar hashes; un hijo ordinario no puede mutar logs después de SUCCEEDED.
- En POSIX, el líder del grupo no se reapeará hasta terminar la señalización/verificación del grupo; un PGID perdido provoca fallo cerrado y nunca una señal a una identidad numérica posiblemente reutilizada.
- Precondición explícita del host POSIX: `SIGCHLD` debe ser `SIG_DFL` antes de crear el proveedor; `SIG_IGN`, callable o disposición desconocida bloquean `Popen`. El host no cambiará esa disposición ni ejecutará un reaper externo (`waitpid(-1)` u otro) durante las corridas. El runtime conserva `Popen` privado y es dueño de wait/poll; la comprobación no impide reapers ajenos en otros hilos y no es aislamiento general.
- Distinguir pérdida real de identidad (`ChildProcessError`/`ECHILD` o PID inesperado) de fallo de observación (`PermissionError`/otro `OSError`): mientras el runtime conserva el líder sin reapear, debe intentar señalizar/verificar/reapear el grupo aunque no pueda observarlo. Conservar `FAILED`/`UNVERIFIED` y hashes vacíos; si falla la señalización/verificación, cleanup reintenta sin reapear antes y registra `cleanup_error` si tampoco termina.
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
- Implement `FakeRuntime` for deterministic contract tests. It records invocations and exposes scripted status transitions; the first terminal status/result is immutable across `stream_or_collect()`, `cancel()`, and `timeout()`. It never identifies itself as Codex, Gemini, or a real provider run.

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

**Final branch review correction round 1:**
- [x] Add a two-thread regression that blocks collection, cancels the process, and proves both paths return the same `CANCELLED` result; make first terminal-result publication atomic.
- [x] Add a Codex fixture where a completed `spawn_agent` event reports the parent ID before `thread.started`; the result must not count that ID as a child.
- [x] Run focused adapter/worktree tests, full suite, structural validator, and `git diff --check`; record exact results.
- [x] Obtain scoped independent re-review of both fixes and address any remaining findings before continuing.

**Final branch review correction round 2:**
- [x] Start each provider child in its own OS process group/session and terminate/reap that group on cancel/timeout; add a local Python parent/child regression proving an ordinary inherited descendant stops before result/log hashing. Preserve the explicit limit that detached descendants and OS sandboxing are not proven.
- [x] Prevent billable launch if peer-stop/deadline arrives during bounded discovery: separate/cache discovery, check stop and remaining deadline after it and immediately before launch, and create no provider process when either has fired. Add deterministic blocked-discovery tests for both stop and timeout.
- [x] Make FakeRuntime preserve its first terminal result/status for later cancel/timeout/collection; add regressions for completed success and failure.
- [x] Store an execution-specific relative stdout artifact path in the mailbox (including `dev-logs/<execution-id>/`); prove repeated runs do not produce identical artifact references.
- [x] Run adapter/runner focused tests, full suite, validator and diff check; capture evidence and limitations.
- [x] Obtain independent scoped review of the fixes; address findings before moving to the coordinator evidence producer.

**Final branch review correction round 3:**
- [x] Return an empty mailbox artifact reference when no log file exists; add a prelaunch-unavailable regression.
- [x] Handle nonzero/failed Windows process-tree termination without hanging in `wait()` or silently claiming confirmed cancellation; add offline failure-path coverage.
- [x] Run focused worktree/provider tests and `git diff --check`; append evidence and review this follow-up.

**Final branch review correction round 4:**
- [x] Perform the final stop/deadline check after reservation/open and synchronize that check with `Popen` (shared launch gate/token); add barrier-controlled stop and timeout tests that previously reached `Popen` after stop.
- [x] Terminate residual process-group/job members even when the CLI parent exits first; on Windows use a job mechanism established before provider code runs, and on POSIX stop the isolated process group. Add a local Python parent-exits/child-mutates-stdout regression; hash only after descendants are stopped. Keep breakaway descendants and OS sandbox unverified.
- [x] Preserve the POSIX root PID/PGID until process-group signalling and live-member confirmation finish; observe exit with non-reaping `waitid(..., WNOWAIT)`, fail before launch if safe confirmation support is missing, and cover collect/status/cancel/timeout/setup-failure/concurrent collection plus lost identity.
- [x] Separate actual POSIX identity loss from observation errors; cover owned-group cleanup after waitid PermissionError, failed signalling and explicit cleanup retry while retaining the first FAILED result with no finalized log evidence.
- [x] Enforce the explicit default-SIGCHLD host precondition before Popen; cover ignored/custom/None dispositions as unavailable and default disposition as available using offline doubles, without claiming to prevent foreign reapers or later host changes.
- [ ] Run focused/full tests, validator/help/diff checks, and obtain independent scoped review before continuing to coordinator evidence work.

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

- [x] **Step 1: Add runner tests using `FakeRuntime` for preview without discovery, mode-specific dispatch for Codex-only/Gemini-only/both, no provider fallback, explicit cost acknowledgement, timeout and cancellation propagation, and result-to-mailbox handoff without privileged statuses. Add one local Python child-process test for process/log lifecycle only; label it as such, not provider E2E.**
- [x] **Step 2: Run the focused worktree suite and capture expected failures against the current direct-`Popen` runner.**
- [x] **Step 3: Refactor `development_runner.py` to use `create_runtime()` and the Task 1 protocol while preserving its CLI and preview semantics.**
- [x] **Step 4: Update docs and matrix to identify runtime adapter coverage, `NOT_RUN` real Codex/Gemini E2E, `UNVERIFIED` native subagents/sandbox effectiveness, and P1 work still pending.**
- [x] **Step 5: Run focused tests, full unittest suite, and structural validator. Inspect that no provider calls or credential access occurred.**
- [x] **Step 6: Commit `refactor: route development workers through runtimes`.**
