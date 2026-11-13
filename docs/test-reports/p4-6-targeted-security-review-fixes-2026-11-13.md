# P4.6 — Correcciones focalizadas de revisión

- Hallazgos: rechazo de junctions/reparse points en rutas de worktree y metadata; el CLI ahora presenta `argv`, `cwd` y timeout de cada check y exige confirmación interactiva ligada al task ID antes de iniciar la ejecución.
- `PASS` — 6 regresiones locales: junction por API y atributo reparse, worker con ruta junction, vista previa y aprobación del CLI, rechazo de aprobación y bloqueo sin terminal interactiva.
- `PASS` — Se observaron fallos `RED` de las tres pruebas iniciales y de la regresión de `inspect`; las seis pruebas focalizadas pasan después de las correcciones.
- `NOT_RUN_INCOMPLETE` — La corrida conjunta de `test_development_worktrees.py`, `test_check_runner.py` y `test_execution_evidence.py` se interrumpió tras ~180 s; no había reportado fallos, pero no se considera aprobada.
- `NOT_RUN` — No se creó una junction real en Windows; el entorno puede no conceder el privilegio. Los dos mecanismos de detección se probaron con fixtures deterministas.
- Límite: la confirmación del CLI hace visible y requiere autorizar los comandos, pero no es sandbox. Los procesos siguen teniendo permisos del usuario. APIs Python llamadas directamente se consideran invocaciones de confianza.
- `NOT_RUN` — E2E con proveedor real y ejecución del SIR particular; no se invocaron modelos ni se leyeron de nuevo los datos.
- Sin instalación externa, merge, release ni cambio a `main`.
