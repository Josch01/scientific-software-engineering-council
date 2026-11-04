# P3.10 — auditoría de recursos verificados del workspace

## Intención

Permitir que una persona solicite a los especialistas SSEC una auditoría de un espacio científico abierto. El snapshot que reciben los agentes contendrá solo los recursos declarados y seleccionados del workspace, con bytes capturados por el loader seguro y digests revalidados; nunca se copiará el resto del proyecto para esta ruta.

## Enfoque elegido y alternativas

1. **Snapshot efímero desde `LoadedWorkspace` (elegido):** usar los bytes inmutables ya cargados/verificados, revalidar SHA-256, escribirlos a una raíz temporal y pasar esa lista exacta al runner. Reutiliza el snapshot existente y deja logs/evidencia en `.ssec/runs`.
2. **Volver a leer rutas del manifiesto al empezar la auditoría:** menos staging, pero duplica la lógica de contención/digest y abre una carrera entre la vista cargada y la auditoría. Descartado.
3. **Copiar el proyecto completo y pedir a los agentes que ignoren otros archivos:** contradice el control de recursos del caso SIR y expone datos no seleccionados. Descartado.

## Requisitos

- La persona confirma la auditoría y ve el conjunto exacto de recursos (ID, tipo, ruta, tamaño y digest) antes de que se cree cualquier runtime. La confirmación advierte que el coste del proveedor no está medido y que los agentes solo reciben esos recursos.
- Un contrato puro crea el task de tipo `audit`, enlaza workspace/manifiesto/recursos con SHA-256 y selecciona únicamente IDs existentes y únicos.
- La ejecución revalida los bytes en memoria y crea un proyecto temporal que contiene solo esos recursos y contexto derivado. Se invoca el runner existente dentro de esa raíz, por lo que su escaneo habitual no puede alcanzar otros archivos del proyecto original. El proyecto original solo recibe el reporte persistido en `.ssec/runs`.
- El informe guardado conserva el digest del manifiesto, IDs/rutas/digests seleccionados y estados por worker. Exit 0 se etiqueta como proceso completado sin auditoría aprobada; no certifica validez científica ni produce aprobación humana.
- La GUI ejecuta el trabajo fuera del hilo Tk, ofrece una señal de cancelación enlazada a `run_agents.execute` y presenta resultados/errores terminales sin bloquear controles ni pintar `NOT_RUN` como éxito.
- Pruebas con runtimes falsos validan el bundle y el flujo. No se invoca Codex/Gemini/AGY durante desarrollo.

## Fuera de alcance

No ejecutar código Python del proyecto/agentes, no generar código, no hacer ajuste científico automáticamente, no producir validez matemática, no crear un reviewer de proveedor en tiempo real y no cambiar el loader o la semántica de aprobación P1. La auditoría real por proveedor será opt-in tras confirmación y coste no medido.

## Decisiones para el implementador

- El alcance inicial permite seleccionar uno o más IDs de recursos del workspace actual; por omisión la UI puede proponer todos, pero no enviar ninguno sin confirmación visible.
- Reutilizar el router/run_agents ya existente y los parámetros de proveedor guardados en la raíz del proyecto; si la configuración es inválida, fallar antes de preguntar/ejecutar.
- Mantener el resultado como `PROCESSES_COMPLETED_NOT_AUDITED` cuando todos los workers salgan 0 y `release_status=NOT_APPROVED`.
- Decisión de integración: no cambiar `run_agents.py`; su API escanea la raíz dada. Se limita el alcance mediante una raíz temporal de un solo uso y se exige que el escaneo descubra exactamente los recursos seleccionados más el contexto. Esto reduce el área de cambio y evita conflictos con el incremento de runtime P1.
