# P1.4.1 — despacho explícito del runtime AGY en el supervisor

## Intención

Permitir que el supervisor local seleccione `agy` para una auditoría real mediante el adaptador `AgyRuntime`, reutilizando el contrato `AgentRuntime` y conservando una sesión/hash por especialista. Esto conecta la CLI local autenticada con el ejecutor existente sin una API de pago independiente. El incremento no ejecutará proveedores durante desarrollo ni convertirá una salida de exit 0 en una auditoría aprobada.

## Alcance

- Añadir `agy` como modo explícito independiente en `configuration`, `prepare_agents`, `run_agents` y el selector de proveedor del panel.
- No mapear `gemini` a `agy`, no hacer fallback de proveedor y no cambiar la asignación `both` (Codex + Gemini).
- AGY no recibirá perfiles nativos ni subagentes supuestos: el rol/instrucción va en el prompt y packet SSEC; `profile` será `null` para esa asignación.
- Para una asignación `agy`, `run_agents` debe lanzar `create_runtime("agy")` con `RuntimeRequest(writable=False, cost_acknowledged=True)` después del ACK de coste no medido de la GUI/CLI. Respetar cancelación y plazo global; limpiar el handle.
- Guardar estado terminal, exit code, `provider_session_id`, SHA-256 de stdout/stderr y el límite de sandbox reportado; la finalización sigue `EXIT_ZERO_UNREVIEWED` y requiere revisión humana.
- Mantener el snapshot de auditoría en un directorio temporal por trabajador. Las limitaciones actuales de copia completa del proyecto y del aislamiento del SO se documentan; un futuro audit de workspace debe usar una lista permitida, no reutilizar el snapshot completo.

## Alternativas

1. **Usar `AgyRuntime` desde `run_agents` (seleccionada):** reutiliza detección, parsing JSON estricto, cancelación, contención de proceso y hashes ya probados; permite estado/sesión de AGY.
2. **Añadir un tercer bloque `subprocess` en `run_agents`:** pequeño al inicio, pero duplicaría argv, parseo, timeouts y garantías, además de perder trazabilidad uniforme.
3. **Alias silencioso `gemini` → `agy`:** oculta la elección explícita de CLI y hace que el comportamiento dependa de PATH; contradice el contrato de proveedor seleccionado.

## Fuera de alcance

No cambia los modos Codex/Gemini ni la semántica `both`; no activa delegación nativa, sandbox efectivo, límite de facturación, aceptación automática ni aprobación científica. No se hará otra llamada real con AGY. El auditor completo P1.4 por proveedor permanece `NOT_RUN` hasta una invocación futura autorizada.

## Criterios de aceptación

- El selector/validador y el planner reconocen `agy` sin fallback y producen packets con rol asignado.
- El runner usa `AgyRuntime`, propaga sesión y digests, respeta fallo/cancelación/timeout y ejecuta cleanup exactamente una vez.
- No se lanza ningún runtime si falta el ACK de coste.
- Pruebas con runtime falso y regresiones existentes pasan; no se invocan CLIs reales en CI.
- No se afirma que la opción `--sandbox` aísle archivos; ejecución real integrada, independencia y revisión científica continúan `NOT_RUN`.
