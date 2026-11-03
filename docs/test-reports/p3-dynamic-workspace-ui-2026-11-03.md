# P3.3 — espacio científico dinámico opcional

**Estado:** prototipo experimental; loader, presentación headless y construcción real de widgets Windows verificadas. El SIR concreto sigue `NOT_RUN`; no se recibió su modelo ni datos.

## Implementación

- `LoadedWorkspace.manifest` conserva una copia profundamente inmutable del manifiesto que el loader ya leyó y validó; la UI no vuelve a abrir recursos por sus paths.
- La capa pura `scientific_workspace_view.py` traduce secciones/componentes a modelos de vista. El registro Tkinter es fijo; nombres/configuración de manifiesto no agregan código renderer.
- Observaciones usan `ObservationDataset` schema v1. La gráfica acepta `scientific_core` simulation-result v1 y comprueba dimensiones, nombres, números finitos, paso solicitado/real y grilla temporal antes de dibujar.
- Código y JSON se muestran como texto/datos inertes; no se importa ni ejecuta código de proyectos/agentes. El `--check` carga y prepara vistas sin importar Tk.
- La app ofrece navegación por secciones, lista de recursos, tabla de observaciones, gráfica Canvas con leyenda y tabla, resúmenes de error y diálogo para abrir proyecto.
- Límites: 100 componentes; 1 MiB por artefacto JSON y 2 MiB de JSON único por espacio; preview JSON 32 KiB y código/texto 256 KiB; hasta 1.000 filas en la tabla y 5 series dibujadas (la tabla conserva todas las series configuradas). Los recortes se anuncian.

La paleta y comportamiento usan ttk nativo, foco/orden de teclado del toolkit, etiquetas visibles, estilos de línea además de color y tabla junto a la gráfica. La guía consultada no aporta recomendaciones específicas para Tkinter; la solución usa controles nativos conservadores. No se hizo inspección visual manual ni prueba de interacción con usuarios.

## Verificación

| Entorno | Comando / actividad | Resultado |
|---|---|---|
| Windows, Python 3.14.0 | `python -m unittest tests.test_scientific_workspace tests.test_scientific_workspace_loader tests.test_scientific_workspace_view tests.test_scientific_workspace_app -q` | PASS: 47 ejecutados, 46 pasan y 1 se omite por `WinError 1314` al crear fixture symlink |
| Windows, Python 3.14.0 | `python -m py_compile ...` para loader, view, app y tests; `git diff --check` | PASS |
| Windows, Tkinter real | Creación de ventana/widgets oculta con resultado serializado por `solve_rk4` para RHS sintética constante; se comprobó una pestaña, tablas, 6 series y que todas las coordenadas Canvas son finitas | PASS de construcción de widgets; fixture sintética, no SIR ni validación científica |
| Docker/Linux, Python 3.14.0 | `python scripts/validate_skill.py` bajo la ruta canónica del skill | PASS: `VALID STRUCTURE` |
| Docker/Linux, Python 3.14.0 | `python -m unittest discover -s tests -q` bajo la ruta canónica del skill | PASS: 397 tests, 6 omitidos, 128.725 s |
| GitHub Actions de P3.3 | CI asociado al PR #25, run [#116](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41703973926) | PASS: 4/4 jobs Windows/Ubuntu × Python 3.11/3.12 |

## Revisión y defectos corregidos

La revisión estática independiente no ejecutó pruebas. Identificó cinco defectos importantes reproducibles en el diseño/código revisado: multiplicación de memoria al repetir payloads JSON, metadatos RK4 inconsistentes, overflow de coordenadas con extremos finitos, leyenda ilegible con muchas series y controles Unicode/surrogates inseguros para widgets. Se corrigieron con caches, presupuestos de vista, límite explícito de componentes, validación de la grilla y paso, escalado numérico, leyenda de cinco series y saneamiento de texto. La revisión de seguimiento confirmó los cinco puntos cerrados y no encontró otro hallazgo importante.

También se corrigió el fallback de imports para ejecutar el CLI como script y se sanitizó NUL en texto de código antes de pasarlo a Tk.

## Límites científicos y de seguridad

- No hay ecuaciones, unidades, condiciones iniciales ni datos experimentales SIR disponibles; simulación/ajuste/auditoría del caso concreto `NOT_RUN`.
- Modelos, parámetros, fit, sensibilidad, incertidumbre y auditoría que no tienen renderer de contrato específico se muestran como JSON acotado e inerte; la UI no calcula ajuste, sensibilidad ni incertidumbre.
- La construcción visual real se probó con un artefacto `solve_rk4` sintético; no constituye SIR, precisión numérica general ni validación científica.
- No se invocó AGY/Codex/Gemini. El proveedor real y cualquier aprobación de especialistas quedan fuera de esta UI.
- Se conserva la decisión del propietario: ejecutar solo callbacks confiables, revisados y aprobados explícitamente por una persona. No autoejecutar código Python arbitrario de agentes en el proceso principal. El runner en proceso separado con aislamiento efectivo queda como requisito futuro; Docker no equivale a aislamiento absoluto.
- La GUI carga recursos y prepara vistas en el hilo UI, dentro de los presupuestos del loader y renderer. En proyectos grandes puede pausar; el cálculo largo/cancelación con workers es futuro.
- Windows symlink escape local y full suite Windows local permanecen `NOT_RUN`/`BLOCKED` por permisos/tiempo del entorno anterior; la matriz CI P3.2 ya pasó run #112 4/4. La integración real P1 con AGY sigue `NOT_RUN`.

## Entrega

La rama P3.3 se apila sobre `codex/p3-safe-workspace-loader`. El PR se mantiene en borrador y apunta a P3.2; no se hace merge, release ni invocación adicional de modelo.

