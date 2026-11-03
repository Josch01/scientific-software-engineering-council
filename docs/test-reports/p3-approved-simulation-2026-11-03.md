# P3.6 — acción de simulación aprobada

**Estado:** `EXPERIMENTAL`. Se añadió un botón opcional para ejecutar callbacks científicos registrados por un host confiable, solo después de una confirmación humana. El SIR real y la ejecución de proveedores continúan `NOT_RUN`.

## Capacidades entregadas

- La app muestra una acción únicamente para un componente `simulation_plot` cuando el host inyecta un callback asociado al `workspace_id` y `component_id` cargados.
- La confirmación explica que el callback corre como código Python local confiable. Rechazar no crea ticket ni invoca el callback; aceptar emite un ticket de un solo uso.
- El callback recibe el workspace validado por el loader y la vista del componente. El proyecto y el manifiesto no pueden registrar ni importar callbacks.
- La salida debe ser un `OdeSolution`; se comprueban límites de filas, valores, estados y parámetros antes de serializar. La gráfica resultante queda en una pestaña temporal en memoria.
- La ejecución se hace en un hilo daemon para mantener receptiva la UI. Fallos, incluidos `BaseException`, publican un estado terminal para restaurar los controles y no mostrar resultados parciales.

## Verificación

| Entorno | Actividad | Resultado |
|---|---|---|
| Windows, Python 3.14 | `python -m unittest tests.test_scientific_workspace_actions tests.test_scientific_workspace_app tests.test_scientific_workspace_view -q` | PASS: 34 tests |
| Windows, Tkinter real oculto | Callback controlado; rechazo y aprobación, pestaña de salida y comparación de archivos del proyecto | PASS: rechazo = 0 llamadas; aprobación = 1 llamada; resultado mostrado; archivos intactos |
| Docker/Linux, Python 3.14.0 | `python -m unittest discover -s tests -v` | PASS: suite completa registrada en [`docker-full.log`](p3-approved-simulation-2026-11-03-docker-full.log); 419 tests, 6 omitidos |
| Docker/Linux, Python 3.14.0 | `python scripts/validate_skill.py` con la raíz montada como `scientific-software-engineering-council` | PASS: `VALID STRUCTURE` |
| Windows, Python 3.14 | `py_compile` de los módulos/tests cambiados y `git diff --check` | PASS |
| Revisión estática independiente | Dimensiones/colecciones sin límite previo a serialización; callback que termina con `SystemExit` | Ambos hallazgos corregidos con regresiones; el revisor confirmó que quedan resueltos |
| GitHub Actions | PR #28, rama `codex/p3-workspace-approved-simulation` | PASS: runs [41727587626](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41727587626) y [41727621114](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41727621114), cada uno con 4/4 jobs Windows/Ubuntu × Python 3.11/3.12 |
| SIR modificado con datos experimentales | Configuración, simulación y auditoría científicas | `NOT_RUN`: no se han entregado ecuaciones, unidades, condiciones iniciales ni datos |
| Codex/Gemini/AGY real | Invocación del proveedor | `NOT_RUN`: no se consumió una invocación autorizada durante este incremento |

## Riesgos y pendientes

- El callback inyectado es código confiable ejecutado en el proceso local; no existe sandbox, límite de recursos ni cancelación segura. La confirmación humana no es una frontera de aislamiento.
- La pestaña no persiste el resultado. El smoke usa un callback matemático sintético y solo valida integración de software, no precisión numérica ni validez científica.
- La app standalone no registra acciones. El futuro runner separado para código generado por agentes queda `PLANNED`; si usa Docker deberá imponer límites de recursos, desactivar red cuando no sea necesaria y montar entradas de solo lectura con salidas acotadas, sin afirmar aislamiento absoluto.
- Ajuste, identificación, sensibilidad e incertidumbre no se ejecutan en esta acción. El siguiente incremento debe cerrar el ciclo del primer workspace dinámico con componentes ya aprobados y después continuar la interfaz dinámica, sin inventar un modelo SIR.

## Entrega

Rama `codex/p3-workspace-approved-simulation`, apilada sobre P3.5, PR borrador [#28](https://github.com/Josch01/scientific-software-engineering-council/pull/28) dirigido a `codex/p3-supervisor-progress-dashboard`. No merge, release ni invocación de proveedor.
