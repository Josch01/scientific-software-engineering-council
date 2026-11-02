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

Documentación oficial: https://geminicli.com/docs/core/subagents/ y https://learn.chatgpt.com/docs/agent-configuration/subagents.
