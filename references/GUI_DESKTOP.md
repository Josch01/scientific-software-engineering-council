# GUI para Windows/Linux

Por defecto evaluar PySide6 (Qt for Python) para UI de escritorio; escoger otro framework sólo por necesidades claras o base existente. Separar `scientific_core` de `desktop_ui`; Qt nunca debe definir las ecuaciones científicas.

Flujo esperado: proyecto/experimento -> parámetros validados -> estimación de coste -> iniciar -> progreso, logs, pausas/cancelación -> tablas/plots -> comparación -> exportación reproducible.

- No ejecutar ODE, training o búsquedas grandes en el event loop; usar threads/processes con señales, mensajes y política de cancelación; evitar tocar widgets desde workers.
- Controlar BLAS/OpenMP/process pools y recursos GPU; impedir que un pool y una GUI multipliquen el CPU sin control.
- Para datasets grandes: paginación, lazy-load, decimación gráfica sin cambiar los datos reales.
- Visualización: ejes, unidades, leyendas, incertidumbre y separación entre datos y simulaciones.
- Configuración y resultados exportables/importables (JSON/CSV/HDF5/Parquet según necesidad), IDs, hashes, versión, seeds, tolerancias.
- Validación de UX: accesibilidad, teclado, pantallas DPI, Linux/Windows, modo oscuro si sirve, mensajes accionables, reconexión tras error.
- `pyside6-deploy` es opción oficial de packaging; probar ejecutables en runners/VM de cada OS, no inferir portabilidad sólo por compilar Linux.

## Propuestas de espacios desde agentes

El flujo P3.9 acepta como propuesta un manifiesto JSON v1 bajo la raíz del proyecto. El agente solo describe recursos y componentes ya registrados; cada recurso debe incluir un SHA-256 que el loader verifica antes de leerlo.

1. Abre el workspace activo del proyecto.
2. Selecciona **Revisar propuesta…** y el manifiesto JSON entregado por el agente.
3. Revisa el diff completo. Propuestas con diffs mayores a 64 KiB se rechazan para no presentar una revisión parcial.
4. **Rechazar** cierra el diálogo sin escribir. **Aprobar y guardar** crea una copia nueva `.ssec-workspace-<sha256>.json` en la raíz y abre esa disposición; no sobrescribe el manifiesto fuente.

La propuesta y sus recursos deben estar dentro del proyecto. Mantén estable y bajo control confiable la raíz del proyecto y sus directorios ascendentes durante la aprobación: el loader contiene cada apertura individual, pero una sustitución concurrente de la raíz por otro proceso local con acceso a su padre queda fuera de las garantías de P3.9. El cambio modifica la disposición visual: no ejecuta Python, comandos ni callbacks de la propuesta, y no acredita validez científica. Ejemplo con fixtures sintéticas: raíz `examples`, workspace activo `sir_scientific_workspace.json`, propuesta `sir_workspace_proposal.json`; la propuesta agrega una pestaña de estado que declara `NOT_ASSESSED` y `NOT_RUN`.

Documentación actual: https://doc.qt.io/qtforpython-6/ y https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html
