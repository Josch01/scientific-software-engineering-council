# P3.5 — progreso estructurado por especialista

**Intención.** Dar al usuario una vista verificable del avance de cada especialista en la auditoría local que ya ejecuta el supervisor.

**Estado actual.** `run_agents.py` mantiene estados por rol y escribe un `progress.json` dentro de cada ejecución, pero el panel no conoce el directorio de ejecución; solo muestra un log combinado. El CLI devuelve su resumen final al terminar.

**Enfoques considerados.** (1) Buscar la carpeta de ejecución más reciente desde la GUI: puede confundir corridas concurrentes y depende del orden temporal. (2) Emitir eventos JSONL versionados en el stdout del runner cuando el supervisor lo solicita, y reutilizar el log que el panel ya captura: es la opción elegida, correlaciona naturalmente el proceso, no agrega archivos/rutas ni modifica el CLI por omisión. (3) Crear un broker persistente de eventos: requiere infraestructura no necesaria para el flujo local.

**Alcance y contrato.** El flag GUI `--emit-progress-jsonl` habilita líneas `SSEC_PROGRESS <JSON>` con `schema_version=1`, `run_id`, `task_id`, `execution`, `completed`, `total`, `release_status=NOT_APPROVED` y filas por rol/proveedor/estado. El runner emite estados `NOT_STARTED`, `STARTING`, `RUNNING` y el resultado terminal existente. El panel analiza solo eventos válidos y muestra progreso y tabla por rol; el texto de log queda disponible. Un evento de progreso nunca significa aceptación.

**Restricciones.** El CLI normal conserva su salida actual si no se activa el flag. No cambia scheduling, límites de coste, autorización, ejecución de agentes ni la semántica de cancelación. No hay llamada real a proveedor ni scheduler DAG general.

**Criterio de aceptación.** Tests con un proceso Python local controlado demuestran transiciones de estado y salida no aprobada; tests del panel comprueban el análisis acotado del JSONL; smoke Tk muestra la tabla en la ventana existente sin bloquear el hilo. Los providers reales continúan fuera de esta verificación.
