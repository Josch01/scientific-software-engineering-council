# P3.11 — Propuestas de workspace desde CLI local

## Objetivo

Permitir que el usuario describa cambios en un workspace científico y reciba una propuesta estructurada que pueda inspeccionar y aprobar desde el diff existente.

## Contrato

- La GUI solicita un objetivo y uno o más recursos verificados; solo esos bytes capturados y el contexto de componentes relacionados llegan al proceso del CLI.
- Antes del proceso, la GUI muestra el proveedor, recursos, límite no medido de cuota y pide confirmación humana explícita.
- Solo Gemini CLI es elegible para esta función: usa `plan` más una política administrativa temporal que deniega todas las herramientas excepto lectura de archivos incorporada y deniega herramientas MCP. Si la versión del CLI carece de esos controles o existen políticas administrativas estándar que puedan desplazar la política temporal, el flujo queda `PROVIDER_UNAVAILABLE` sin invocar un modelo.
- Codex CLI queda deshabilitado para esta función mientras su adaptador no pueda demostrar que el agente carece de comandos ejecutables. `read-only` por sí solo no satisface ese requisito. La configuración `both` selecciona Gemini únicamente.
- La salida contiene solo `title`, `description` y `sections`; SSEC añade schema, workspace ID y recursos seleccionados con SHA-256, y vuelve a validar con el contrato y loader actuales.
- Un candidato se guarda bajo `.ssec/runs/<run_id>/` con `NOT_APPROVED` y `NOT_ASSESSED`. El flujo reutiliza el diff completo y la aprobación humana existentes; guardar crea una copia canónica y conserva el manifiesto original.
- No se ejecuta código generado. Un proveedor no disponible, un error, una cancelación o una respuesta inválida no producen aprobación.
- **Revisar propuesta** conserva la importación manual JSON como alternativa.

## Fuera de alcance

Llamadas reales a modelos durante desarrollo, ejecución de código de agentes, generación automática de Python, edición directa de manifiestos originales, medición de cuota y pruebas de validez científica del SIR del usuario.

## Aceptación

Pruebas deterministas verifican selección/digests, política de herramientas, rechazo seguro de Codex, política Gemini, JSON inválido, cancelación/fallo, candidate persistente sin aprobación, confirmación de cuota y uso del diff/aprobación existentes. La invocación real de proveedor se reporta `NOT_RUN`.
