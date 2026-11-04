# P1 — Compatibilidad offline del CLI AGY en el slot Gemini

**Estado:** `EXPERIMENTAL`.
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
- Verificación final focalizada tras revisión independiente: `python -m unittest -q tests.test_provider_runtimes tests.test_runner tests.test_reviewer_output tests.test_review_evidence tests.test_development_worktrees`: **157 pruebas ejecutadas, OK; 2 omitidas por condiciones de plataforma**. Incluye el ciclo integrado de revisión usando un proceso Python local y eventos AGY deterministas; no es una invocación del proveedor.
- Probe local `create_runtime("gemini").discover_capabilities()` con `SSEC_GEMINI_CLI=agy`: `available=True`, `version=1.4.12`; `sandbox_effective=None`, `native_subagents=UNKNOWN`. Solo ejecutó `--version`/`--help`; no envió prompt.
- `python scripts/validate_skill.py`: PASS; `python -m compileall -q scripts tests`: exit 0; `git diff --check`: PASS.
- La revisión independiente halló y motivó dos correcciones: admitir solo la clase concreta `AgyGeminiRuntime` en el flujo P1.4, extractor y manifiesto; y rechazar streams sin `init` válido o un ID terminal vinculado. La prueba de proceso local recorre runner, parser, reporte, persistencia y revalidación; no establece validez ni independencia real.
- Ya existe un smoke real previo de `AgyRuntime`/AGY 1.4.12: una solicitud en un proyecto temporal vacío terminó con exit 0 y respuesta/sesión observadas ([PR #32](https://github.com/Josch01/scientific-software-engineering-council/pull/32)). Ese smoke no cubrió este `AgyGeminiRuntime`, `stream-json`, el modo session-only ni el flujo integrado de P1.4. El intento `GeminiRuntime`/`gemini` anterior falló con código 41 y sin respuesta.
- CI Linux y Windows queda pendiente de los checks remotos para esta rama. Revisión integrada P1.4 por AGY permanece `NOT_RUN`; no se hicieron nuevas invocaciones de modelos.

## Límites

El modo de revisión por sesión, `accept-edits` y `--sandbox` son controles del CLI local, no prueba de aislamiento del sistema operativo. El adaptador no admite archivos de política de herramientas por ejecución de Gemini. El runner de desarrollo conserva el proveedor lógico `gemini`; el subtipo del runtime distingue AGY en sus evidencias. Ningún PASS offline demuestra autenticación, independencia de revisión ni validez científica.

## Limitaciones diferidas de la revisión

- `run_agents.py` y `AgyGeminiRuntime` no comparten una política de resolución de shims `.cmd`/`.bat`; la instalación observada es un `.exe`. Los fallos de lanzamiento continúan como no aprobados, sin fallback.
- Falta una regresión dedicada para probes de versión/ayuda que terminen con código distinto de cero; una comprobación de revisión verificó el comportamiento actual como no disponible.
- No se verificaron los eventos `stream-json` de este runtime, el significado efectivo de `--settings`, los permisos, el sandbox ni la independencia del revisor. Permanecen `NOT_RUN`/`UNKNOWN`; el smoke real previo no cubre esos puntos.

Fuentes de protocolo y permisos: [AGY headless mode](https://antigravity.google/docs/cli/headless/) y [AGY execution modes](https://antigravity.google/docs/cli/modes/).
