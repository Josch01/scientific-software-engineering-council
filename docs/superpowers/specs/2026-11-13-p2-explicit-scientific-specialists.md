# P2.6 — Especialistas científicos explícitos

## Intención

Que la skill portable y el router SSEC asignen especialistas adecuados para álgebra diferencial, dinámica e identificabilidad, y que las tareas con claims científicos requieran evidencia de validación científica aunque sean de riesgo bajo.

## Enfoques considerados

- **A. Extender router y perfiles existentes (seleccionado):** asignar los tres roles por dominio, generar sus paquetes mediante el perfil actual y mantener el router determinista. Es el cambio mínimo que hace operativa la especialización.
- **B. Ampliar solo la documentación:** no cambia el comportamiento del planificador y deja intacta la brecha observada en P0.
- **C. Añadir un subsistema/plugin científico:** permite más aislamiento, pero duplica el catálogo y la selección actual sin ser necesario para este alcance.

La misión maestra ya autoriza el catálogo bajo demanda; se elige A para cumplir esa obligación sin infraestructura nueva.

## Alcance

- `identifiability` selecciona `identifiability_specialist`.
- `dynamics` selecciona `dynamical_systems_specialist`.
- `differential_algebra` y `symbolic` seleccionan `differential_algebra_specialist`.
- Se conservan los expertos numérico y de modelo cuando sus obligaciones existentes aplican; los roles adicionales aportan revisión específica, no sustituyen cálculos ni validación externa.
- Todo claim en `SCIENCE_CLAIM_DOMAINS` exige `scientific_validation`; R2/R3 conserva además revisión independiente y auditoría de seguridad.
- Los tres roles quedan disponibles en los perfiles portables Codex/Gemini/AGY existentes.

## Límites

No se añaden algoritmos, agentes persistentes, proveedores, invocaciones reales ni certificación científica. El router expresa obligaciones; no ejecuta agentes ni produce evidencia. La validez numérica y científica se mantiene separada de la validez del software.

## Criterio de aceptación

Pruebas deterministas demuestran el mapeo por dominio, la obligación científica en R1 y la generación de paquetes de los tres roles; el caso general no activa especialistas científicos innecesarios. Skill, matriz y reporte registran el alcance y sus límites.
