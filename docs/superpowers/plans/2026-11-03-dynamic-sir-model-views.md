# P3.8 — implementación de vistas SIR estructuradas

## Meta

Renderizar en el workspace los contratos SIR validados como vistas de ecuaciones y parámetros reutilizables, junto a la simulación existente.

## Pasos

1. [x] Añadir pruebas RED para contenido estructurado, SIR inválido, fallback JSON y colisión de marcadores; reproducir el fallo.
2. [x] Proyectar `SirModelDefinition` a dataclasses inmutables para `equation_view` y `parameter_table`.
3. [x] Renderizar ecuaciones, unidades, perfiles, condiciones iniciales e intervalo/solver con el registro Tk existente.
4. [x] Ampliar el workspace sintético y verificar CLI headless, smoke Tk y aprobación/rechazo.
5. [x] Ejecutar regresiones, suite Docker completa y revisión independiente; registrar límites. Commit/PR borrador pendiente.

No modificar el esquema del manifest ni ejecutar código del proyecto.
