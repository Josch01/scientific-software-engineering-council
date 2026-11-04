# P1.4 — Adaptador local AGY

**Objetivo:** permitir que la interfaz `AgentRuntime` lance una sola solicitud al `agy` autenticado localmente y capture respuesta, conversación y hashes para evidencia de P1.4.

**Alternativas:** ejecutar `agy` por fuera de SSEC no prueba su captura de evidencia; reutilizar `GeminiRuntime` confunde dos CLI/protocolos; agregar un `AgyRuntime` pequeño preserva el contrato explícito y el parseo JSON oficial. Se elige el adaptador dedicado.

**Alcance:** `agy --sandbox`, `--output-format json`, `-p/--prompt`; solo estado `SUCCESS` sin campo `error`, con `conversation_id` no vacío y respuesta textual no vacía cuenta como éxito. `writable=False` selecciona `--mode=plan` como instrucción, no como barrera de escritura; las reglas configuradas pueden permitir escrituras. `writable=True` selecciona `--mode=accept-edits`. `--sandbox` cubre restricciones de terminal, no demuestra aislamiento de archivos; `sandbox_effective` permanece `UNKNOWN`. Se conserva el requisito `cost_acknowledged` del runtime.

**Fuera de alcance:** agregar AGY a perfiles nativos o modo global de configuración; inferir autenticación; afirmar independencia de cuenta/contexto, aislamiento del SO o validez científica; reintentar o consumir más de una llamada real.

**Aceptación:** pruebas offline de argv, factory, capabilities y JSON estricto; una sola invocación real corta mediante `AgyRuntime` con caché autenticada y prompt no modificador; registrar estado, sesión, versión y digests. Si falla, registrar el fallo y no repetir.

**Referencia primaria:** [AGY headless mode](https://antigravity.google/docs/cli/headless/) y [execution modes](https://antigravity.google/docs/cli/modes/); confirmados además por `agy 1.4.12 --help` local.
