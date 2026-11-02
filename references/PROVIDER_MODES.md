# Modos de subagentes: Gemini, Codex o ambos

La elección del usuario define **el proveedor**, no los roles. El router SSEC determina los especialistas necesarios para el trabajo. Son tres opciones independientes:

| Modo | Responsable principal | Subagentes |
| --- | --- | --- |
| \`gemini\` | Gemini CLI | Gemini nativo, \`.gemini/agents/*.md\` |
| \`codex\` | Codex | Codex nativo, \`.codex/agents/*.toml\` |
| \`both\` | Dos sesiones principales coordinadas externamente | Codex (arquitectura, motor y cómputo), Gemini (GUI y revisión independiente) |

Los perfiles se crean por cada tarea, con instrucciones específicas por rol y un **Task Packet** mínimo.

## Preparación (dry-run predeterminado)

Ejecuta desde la raíz de la skill con Python 3.11 o posterior:

\`\`\`bash
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode gemini --project /ruta/al/proyecto
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode gemini --project /ruta/al/proyecto --apply
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode codex --project /ruta/al/proyecto --apply
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode both --project /ruta/al/proyecto --apply
\`\`\`

Genera perfiles nativos en el directorio del proyecto y paquetes \`.ssec/tasks/<id>/*\`. **No ejecuta agentes** ni modifica la skill original. Por seguridad no reemplaza archivos ajenos ni sigue rutas simbólicas.

## Uso en la CLI

- Gemini CLI: inicia Gemini desde el directorio del proyecto, verifica los agentes con \`/agents\`, y pide al agente principal que delegue; para uno específico usa \`@ssec-software-auditor\`.
- Codex: inicia Codex desde el directorio del proyecto, solicita delegación por los agentes \`ssec-*\`, y observa hilos con \`/subagents\`.
- Ambos: debes iniciar **dos sesiones raíz separadas** y transportar los paquetes/resultados. El runner automático cross-provider, sincronización de worktrees y aprobación humana aún **no están implementados**.

La skill controla la política de mínima selección y el límite de validez. La CLI decide si puede iniciar realmente los subagentes y con qué permisos. No confundir aislamiento de contexto con aislamiento de escritura. En Codex los subagentes heredan sandbox/approvals del padre. El script no instala dependencias ni ejecuta procesos externos.

**No introducir tokens, datos privados o secretos en \`request\`**, ya que el Task Packet se escribe en el proyecto. Los archivos generados para un modo anterior permanecen si cambias de proveedor: no borrarlos automáticamente.

Fuentes: [Gemini CLI subagents](https://geminicli.com/docs/core/subagents/), [Codex custom subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
