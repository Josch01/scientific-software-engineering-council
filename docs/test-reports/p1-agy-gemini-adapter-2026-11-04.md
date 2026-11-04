# P1 — Compatibilidad offline del CLI AGY en el slot Gemini

**Estado:** `EXPERIMENTAL`; el E2E AGY real sigue `NOT_RUN`.  
**Base:** P4.5 commit `42a308f`; este cambio conserva `gemini` como proveedor lógico.

## Cambio

- `SSEC_GEMINI_CLI=agy` selecciona AGY en `run_agents.py` y `AgentRuntime`; sin la variable sigue seleccionado `gemini`.
- Un valor desconocido bloquea la selección. Si AGY no está en `PATH`, el runtime informa `UNAVAILABLE` y no cae silenciosamente a Gemini.
- Auditoría usa `agy --sandbox --settings '{"agentMode":""}' --output-format json`; el runtime usa `stream-json`, modo de revisión `agentMode=""` por sesión y `--mode accept-edits` para un worker cuyo destino es un worktree temporal. La ayuda instalada no acepta `default` como valor de `--mode`.
- El adaptador no usa `--dangerously-skip-permissions`, no acepta `tool_policy_path` de Gemini y registra `cli_binary` en resultados del runner de auditoría.
- El parser requiere `init`, `result.status=SUCCESS`, `usage` y un `conversation_id` coherente; extrae IDs de subagentes solo desde `subagent_info`.

## Verificación local

- RED: 3 pruebas focalizadas fallaron antes del cambio porque el argv emitía `--mode default` y el detector de capacidades exigía un modo no admitido.
- `agy --version`: `1.4.12`; `agy --help`: exit 0, 0 bytes en stdout y 3,052 bytes en stderr. Confirma `--settings`, `--sandbox`, `--mode (accept-edits, auto, plan)` y `--output-format stream-json`.
- `python -m unittest -q tests.test_provider_runtimes tests.test_runner`: **64/64 PASS** en Windows. Incluye argv, parser NDJSON, modo scoped, detección de flags en stderr, ausencia de fallback, y regresiones existentes de ambos módulos.
- Probe local `create_runtime("gemini").discover_capabilities()` con `SSEC_GEMINI_CLI=agy`: `available=True`, `version=1.4.12`; `sandbox_effective=None`, `native_subagents=UNKNOWN`. Solo ejecutó `--version`/`--help`; no envió prompt.
- `python scripts/validate_skill.py`: PASS; `python -m compileall -q scripts tests`: exit 0; `git diff --check`: PASS.
- CI Linux y Windows queda pendiente de los checks remotos para esta rama. No se envió prompt a AGY ni a Gemini. El E2E autenticado AGY/P1.4 sigue `NOT_RUN`; la autorización de invocación única ya se consumió en el intento Gemini anterior, que terminó con código 41 y sin respuesta.
- No se envió prompt a AGY ni a Gemini. La autenticación y el comportamiento real del protocolo en la instalación del usuario siguen `NOT_RUN`.

## Límites

El modo `default`/`accept-edits` y `--sandbox` son controles del CLI local, no prueba de aislamiento del sistema operativo. El adaptador no admite archivos de política de herramientas por ejecución de Gemini. El runner de desarrollo conserva el proveedor lógico `gemini`; el subtipo del runtime distingue AGY en sus evidencias. Ningún PASS offline demuestra autenticación, independencia de revisión ni validez científica.

Fuentes de protocolo y permisos: [AGY headless mode](https://antigravity.google/docs/cli/headless/) y [AGY execution modes](https://antigravity.google/docs/cli/modes/).
