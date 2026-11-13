# P1.6 — Rework acotado desde revisión integrada

## Objetivo

Permitir una corrección local explícita después de `CHANGES_REQUESTED` y obligar a
crear evidencia nueva antes de integrar o volver a revisar. El operador confirma
la instrucción y el posible consumo de cuota; los hallazgos son datos no confiables.

## Contrato

- El paquete de rework liga task, integración, árbol candidato, bundle de revisión,
  hashes, hallazgos, roles y la instrucción humana.
- Un ciclo de rework como máximo por invocación; ejecuta trabajadores en sus
  worktrees aislados, vuelve a ejecutar checks/revisiones y crea una integración,
  revisión independiente y salida `NEEDS_HUMAN`.
- Rechazar revisión repetida del mismo candidato tras `CHANGES_REQUESTED`, paquete
  obsoleto, ejecución fallida/cancelada, árbol sin cambios o evidencia heredada.
- No aprobar, fusionar ni certificar ciencia automáticamente. Sin scheduler,
  recuperación distribuida, sandbox nuevo ni llamada real a proveedores durante CI.

