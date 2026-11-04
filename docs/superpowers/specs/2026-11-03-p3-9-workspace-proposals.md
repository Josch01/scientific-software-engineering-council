# P3.9 — Revisión y aceptación de propuestas de workspace

## Goal

Permitir que un agente entregue un manifiesto JSON de espacio científico, verlo como una propuesta validada y activar su disposición únicamente después de aprobación humana.

## Design

- Reutilizar `load_scientific_workspace` para validar el manifiesto, la contención de recursos y sus digests antes de presentarlo.
- Comparar la representación JSON canónica del workspace activo y la propuesta; rechazar diffs mayores a 64 KiB en vez de mostrar una revisión parcial.
- Vincular la previsualización a digests de ambos manifiestos. Al aprobar, volver a cargar la propuesta y rechazar cambios desde la revisión.
- El loader exige y verifica el SHA-256 declarado de cada recurso antes de leerlo. Persistir una copia canónica inmutable con nombre basado en SHA-256 mediante creación exclusiva bajo la raíz del proyecto. Nunca sobrescribir el manifiesto fuente.
- Mantener estables y bajo control confiable la raíz del proyecto y sus ancestros durante toda la aprobación. Una sustitución concurrente de la raíz por otro proceso local con acceso a su directorio padre queda fuera del modelo de amenaza del JSON propuesto.
- La GUI muestra el diff completo y ofrece rechazar o aprobar y guardar. Rechazar y previsualizar no escriben nada.
- Las propuestas solo describen componentes ya registrados. No ejecutan Python, comandos, modelos de agentes ni callbacks.

## Not in scope

Invocar proveedores, crear propuestas automáticamente, modificar componentes registrados, ejecutar código propuesto, generalizar el manifiesto a lenguajes de plugins o evaluar la validez científica de un modelo.

## Acceptance

1. Preview validates candidate resources and digests before displaying a complete diff.
2. Invalid, oversized, changed, or stale proposals fail closed without modifying the project.
3. Approval creates or reuses only the exact digest-named manifest; every resource hash remains present and verified, and the source manifest/resources remain unchanged.
4. The GUI requires an explicit approve action before persistence and then displays the loaded proposal.
5. A rejected proposal leaves project files unchanged.
6. The report marks agent generation/provider E2E and user-specific SIR science `NOT_RUN`.

## Riesgo residual

El loader protege cada apertura individual contra traversal y escapes por symlink/reparse point. La aprobación usa la ruta de la raíz del proyecto en varias operaciones; un proceso local concurrente que pueda reemplazar la raíz o sus ancestros podría redirigir operaciones posteriores. El JSON de la propuesta no puede causar esto. No describir la función como resistente a carreras frente a un proceso hostil que controle el directorio padre.
