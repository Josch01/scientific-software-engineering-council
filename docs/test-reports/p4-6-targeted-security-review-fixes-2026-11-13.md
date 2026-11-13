# P4.6 — Correcciones focalizadas de revisión

- Hallazgos: el coordinator y `run_worker` rechazan rutas junction/reparse; `execute` se detiene cuando `inspect` marca un worker inválido. El CLI muestra `argv`, `cwd` y timeout como JSON ASCII escapado y exige confirmación interactiva ligada al task ID antes de iniciar.
- `PASS` — 8 regresiones locales: planificación por junction, atributo reparse Windows sin `Path.is_junction`, `inspect`, bloqueo de dispatch en `execute`, bloqueo de `runtime_factory` en `run_worker`, preview sin caracteres de control, rechazo de aprobación y bloqueo sin terminal interactiva.
- `PASS` — Se observaron fallos `RED` para las rutas junction, falta de aprobación, dispatch prematuro y preview sin escape; las ocho pruebas focalizadas pasan tras las correcciones.
- `PASS` — Revisión independiente acotada del diff hasta `664d214`: sin hallazgos críticos/mayores. El revisor no ejecutó pruebas ni proveedores.
- `NOT_RUN_INCOMPLETE` — La corrida conjunta de `test_development_worktrees.py`, `test_check_runner.py` y `test_execution_evidence.py` se interrumpió tras ~180 s; no había reportado fallos, pero no se considera aprobada.
- `NOT_RUN` — No se creó una junction real en Windows; el entorno puede no conceder el privilegio. Los dos mecanismos de detección se probaron con fixtures deterministas.
- Límite: la confirmación del CLI hace visible y requiere autorizar los comandos, pero no es sandbox. Los procesos siguen teniendo permisos del usuario. APIs Python llamadas directamente se consideran invocaciones de confianza.
- `NOT_RUN` — E2E con proveedor real y ejecución del SIR particular; no se invocaron modelos ni se leyeron de nuevo los datos.
- Sin instalación externa, merge, release ni cambio a `main`.
