# Provider Modes — Gemini, Codex, Ambos

El investigador elige `gemini`, `codex` o `both`. El router selecciona especialistas **por tarea**; el modo designa proveedor. No es obligatorio usar dos modelos.

- `gemini`: perfiles `.gemini/agents/ssec-*.md` para Gemini CLI.
- `codex`: perfiles `.codex/agents/ssec-*.toml` para Codex.
- `both`: dos sesiones principales **todavía no lanzadas automáticamente**; en la propuesta inicial Codex implementa motor, Gemini GUI/auditoría. Se necesita runner externo.

Usa [el panel de configuración](CONFIG_PANEL.md) o el comando:

```bash
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode gemini --project /ruta/proyecto
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode gemini --project /ruta/proyecto --apply
```

El primer comando es una previsualización sin mutación. El segundo prepara archivos. Se generan packets por rol y un `.ssec/tasks/<task_id>/dispatch.json` con tandas y resultados `PREPARED_NOT_EXECUTED`. Ningún perfil constituye por sí solo un subagente ejecutado.

Las sesiones reales se controlan en las CLIs: Gemini con `/agents` y Codex con `/subagents` donde esté disponible. Configurar permisos reales y capacidades de subagentes en el CLI principal. No garantizar aislamiento de procesos ni revisión independiente solo por separar instrucciones.

### AGY como CLI alternativo para el proveedor Gemini

El CLI local AGY puede seleccionarse explícitamente en el slot lógico `gemini`, sin cambiar el modo guardado ni instalar nada:

```powershell
$env:SSEC_GEMINI_CLI = "agy"
python scripts/run_agents.py examples/seir_desktop_audit.json --project C:\ruta\proyecto
```

Sin la variable, SSEC conserva `gemini`. Solo se aceptan `gemini` y `agy`; un valor distinto bloquea la configuración, y si se selecciona AGY pero no está disponible no se intenta Gemini como fallback. El runner de auditoría y el runtime usan `--settings '{"agentMode":""}'` para fijar el modo predeterminado de revisión por esta sesión; AGY no acepta `default` como valor de `--mode`. El runtime usa `--mode accept-edits` para un worker cuyo destino es un worktree desechable. Ninguno usa `--dangerously-skip-permissions`. Esto no certifica el sandbox efectivo; no se provee una política de herramientas por ejecución para AGY.

La adaptación se basa en el [modo headless oficial de AGY](https://antigravity.google/docs/cli/headless/) y sus [modos de ejecución](https://antigravity.google/docs/cli/modes/). E2E real de AGY desde SSEC permanece `NOT_RUN` hasta una invocación autorizada.

Documentación oficial: https://geminicli.com/docs/core/subagents/ y https://learn.chatgpt.com/docs/agent-configuration/subagents.
