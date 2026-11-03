# P3.6 — ejecución de simulación aprobada en workspace

## Objetivo

Permitir que un host confiable conecte un callback científico aprobado a una vista `simulation_plot`; una persona decide cuándo ejecutarlo y ve la salida validada dentro del workspace.

## Decisión

- `create_workspace_window` recibe un mapa optativo `component_id -> ApprovedSimulationAction`. Cada acción contiene una etiqueta visible y un callback Python proporcionado por el host.
- La app no busca, importa ni ejecuta código desde el proyecto o desde un manifiesto. El callback recibe solo el `LoadedWorkspace` producido por el loader seguro y la vista validada de la componente.
- El botón aparece solo para componentes `simulation_plot` con acción inyectada y workspace cargado. Al hacer clic, una confirmación humana explica que el callback corre en el proceso local y puede leer los bytes verificados.
- El callback corre en un hilo daemon para no bloquear Tk. Su salida debe ser `OdeSolution`, se valida con el contrato de `scientific_core` y con la proyección de `simulation_plot` antes de añadirse una pestaña de resultado.
- La salida es temporal en memoria en este incremento; no se escribe ni se modifica el manifiesto. No se realizan ajuste, sensibilidad, incertidumbre ni evaluación de validez científica.

## Límites

El mapa de callbacks es una API de host confiable, no una frontera de sandbox. El usuario debe revisar y aprobar explícitamente la implementación antes de inyectarla y pulsar el botón. No hay cancelación segura de un callback arbitrario, límite de recursos ni persistencia de resultados; esas funciones quedan pendientes hasta que el caso SIR justifique su alcance. No se integra un modelo SIR ficticio mientras falten sus ecuaciones y datos.

## Aceptación

- Sin acción inyectada, abrir un workspace nunca ejecuta callbacks ni muestra un botón de ejecución.
- Rechazar la confirmación ejecuta cero callbacks; aceptarla invoca exactamente la acción asignada después de cargar recursos verificados.
- Resultados válidos se renderizan como `simulation_plot`; valores inválidos o excepciones dejan la vista original intacta y se presentan como error.
- La prueba Tk usa callback local controlado. No se invocan agentes/proveedores ni se afirma validez científica.
