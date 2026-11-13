# Provider Modes — Gemini, Codex, AGY

El investigador elige `gemini`, `codex`, `both` o `agy`. El router selecciona especialistas **por tarea**; el modo designa proveedor.

- `gemini`: perfiles `.gemini/agents/ssec-*.md` para Gemini CLI.
- `codex`: perfiles `.codex/agents/ssec-*.toml` para Codex.
- `both`: mantiene la asignación existente entre workers Codex y revisores Gemini.
- `agy`: workers AGY y revisores independientes Codex. El coordinador crea el perfil AGY dentro de cada worktree con herramientas de archivo permitidas, comandos desactivados y subagentes anidados desactivados.

El runtime AGY usa `--prompt`, `--output-format stream-json`, `--sandbox`, `--mode accept-edits` y el agente de workspace `ssec-<rol>`. Nunca pasa `--dangerously-skip-permissions`. AGY no se ofrece para propuestas de workspace que requieran una política externa de no ejecución. La prueba con proveedor real sigue `NOT_RUN`; tests con eventos de ejemplo solo prueban el adaptador.

Usa [el panel de configuración](CONFIG_PANEL.md) o el comando:

```bash
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode gemini --project /ruta/proyecto
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode gemini --project /ruta/proyecto --apply
```

El primer comando es una previsualización sin mutación. El segundo prepara archivos. Se generan packets por rol y un `.ssec/tasks/<task_id>/dispatch.json` con tandas y resultados `PREPARED_NOT_EXECUTED`. Ningún perfil constituye por sí solo un subagente ejecutado.

Las sesiones reales requieren CLI instalado, autenticación local y consentimiento de coste. El runner no afirma que `--sandbox` garantice aislamiento del SO. Codex conserva la política de revisión independiente; la configuración de un perfil o un proceso terminado no equivale a aceptación.

Documentación oficial: [Antigravity CLI headless](https://antigravity.google/docs/cli/headless), [agentes personalizados](https://antigravity.google/docs/subagents?tab=cli), [Gemini CLI](https://github.com/google-gemini/gemini-cli) y [Codex CLI](https://developers.openai.com/codex/cli).
