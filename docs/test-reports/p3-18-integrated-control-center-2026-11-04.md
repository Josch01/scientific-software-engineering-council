# P3.18 — Centro de Control Qt integrado

## Resultado

P3.18 entrega una aplicación PySide6 opcional que integra una raíz de proyecto y workspace verificado con navegación persistente a **Proyectos, Agentes, Experimentos, Auditorías, Código y Resultados**. El shell incrusta el `ScientificWorkspaceWindow` existente y reutiliza sus componentes; no duplica el motor científico ni modifica su contrato. `scripts/scientific_control_center_qt.py` ya se puede lanzar directamente, con o sin proyecto inicial.

La página **Agentes** reutiliza configuración, previsualización/preparación de perfiles y `run_agents.py`. Solo admite tareas de auditoría, advierte que una ejecución CLI puede consumir cuota sin costo medible, exige confirmación humana, usa argv con `QProcess`, muestra el último progreso JSONL válido dentro del límite y permite solicitar cancelación por archivo. Vista previa y rechazo de confirmación no inician procesos ni escriben configuración/logs de ejecución. `FailedToStart`, cancelación y exit 0 sin revisión quedan explícitamente `NOT_APPROVED` / **NO APROBADA**.

Los cambios de proyecto se validan antes de cargar el workspace y se rechazan durante una auditoría activa. El loader existente verifica SHA-256 y contención. El import del módulo no inicia Tkinter. PySide6 continúa opcional; el frontend científico existente conserva WebEngine local/fallback Qt nativo.

## Commits P3.18

- `9ca601e` — mapa de secciones de workspace para las rutas científicas.
- `19a5540` — shell Qt y navegación común de proyectos.
- `388edeb` — supervisor Qt, CLI ejecutable, regresiones de lifecycle y ciclo local integrado.

La documentación de entrega y captura visual se añade en un commit separado de este informe.

La rama `codex/p3-18-integrated-control-center` se apila sobre `codex/p3-17-sir-analysis-integration` (P3.17, draft PR #41). Sin merge a `main` ni release.

## Verificación

Entorno local: Windows, Python 3.14.0, PySide6 6.11.1.

```text
python -m unittest -q tests.test_control_center tests.test_scientific_control_center_qt tests.test_scientific_sir_analysis_demo tests.test_scientific_workspace_qt
Ran 30 tests — OK

python -m py_compile scripts/scientific_control_center_qt.py
git diff --check
python scripts/scientific_control_center_qt.py --help
```

La prueba Qt determinista usa procesos Python locales de fixture, sin Codex/Gemini/Antigravity ni llamadas de modelo. Cubre navegación, carga/cancelación y preservación del proyecto, rechazo de cambio mientras hay ejecución, validación de política, preview sin escritura, confirmación declinada, progreso, cancelación, exit 0 sin aprobación, fallo de arranque y reuso del mismo `QProcess` para el siguiente intento.

Se abrió la app en modo Windows con `examples/sir_analysis_workspace_demo/workspace.json`, se verificó `ARTIFACT_DIGESTS_MATCHED`, se navegó a Resultados y se inspeccionaron las vistas calculadas en la ventana nativa. Captura: [Centro de Control con resultados SIR sintéticos](assets/p3-18-control-center.png). No se ejecutó el botón de simulación ni se solicitó una auditoría real durante esta demostración.

## Defectos encontrados y corregidos

1. La ruta Agentes aún era un placeholder; ahora contiene la página supervisora Qt.
2. El botón Cancelar permanecía deshabilitado después de `QProcess.start()`: el estado se actualizaba antes de que llegara la señal `started`. El slot ahora refresca los controles al iniciar.
3. Un `FailedToStart` seguido de una prueba Qt con `QThread` podía terminar Python con código nativo `-1073740791` y dejar el log abierto en Windows. La causa era destruir el `QProcess` dentro de la secuencia de señal y perder su instancia; el supervisor ahora conserva y reutiliza el proceso detenido. Una regresión cubre fallo→reintento y las 29 pruebas combinadas terminan correctamente.

## Decisiones y límites

- La interfaz es una capa opcional: el workspace, los contratos científicos, el loader seguro y la skill portable siguen separados de Tkinter/PySide6.
- La navegación de experimentos/código/resultados selecciona secciones/componentes existentes. Un workspace que no tenga una categoría muestra un estado vacío explícito.
- El supervisor Qt adapta el runner local existente; no agrega un DAG general, recuperación distribuida ni aprobación automática.
- La demostración usa exclusivamente resultados calculados desde un fixture SIR sintético reproducible. El ajuste conserva estado `STALLED`; el SIR/datos particulares del usuario, identificabilidad, incertidumbre estadística y validez científica permanecen `NOT_RUN`/`NOT_ASSESSED`.
- **NOT_RUN:** proveedor real iniciado desde esta app; auditoría independiente real; interfaz Qt en Linux; prueba con datos SIR del usuario. La suite de procesos usa ejecutables locales deterministas y no prueba CLIs autenticadas ni su cuota.
- **Pendiente:** primer uso autorizado de proveedor desde la app; entregar ecuaciones/datos reales del usuario; aislamiento efectivo de procesos/modelos generados, empaquetado y evaluación P4/v1.0.
