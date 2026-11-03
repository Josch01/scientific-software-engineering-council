# P3.5 — Supervisor progress dashboard

**Estado:** `EXPERIMENTAL` · 2026-11-03

## Entregado

- `run_agents.execute` acepta un callback optativo y emite snapshots sincronizados por especialista. Los estados `RUNNING` aparecen solo tras crear el proceso; waves aún no iniciadas permanecen `NOT_STARTED` si una wave falla.
- El CLI habilita eventos `SSEC_PROGRESS` schema v1 únicamente con `--emit-progress-jsonl`. Sin el flag conserva JSON normal. Cada evento declara `release_status=NOT_APPROVED`; `EXIT_ZERO_UNREVIEWED` no significa que la revisión se haya aprobado.
- El panel presenta contador, barra y tabla de especialista/proveedor/estado y conserva el log de texto. El parser tiene límites de tamaño y rechaza versiones desconocidas, datos incoherentes, tipos JSON incorrectos y reclamos de aprobación.
- No se invocaron Codex, Gemini ni AGY. El smoke de interfaz usó un proceso falso local y no demuestra comportamiento de proveedores.

## Verificación

- Windows local, Python 3.14: `python -m unittest tests.test_runner tests.test_control_center tests.test_scientific_workspace_app -q` → **28 passed**.
- Tk oculto: **PASS**. El panel mostró una fila `EXIT_ZERO_UNREVIEWED` desde el evento falso y mantuvo `NO APROBADA`.
- Docker/Linux local, imagen ya disponible `jerk-rpo-capd:6.1.0-python3.14.0`: suite `python -m unittest discover -s tests -v` → **410 tests, 6 skipped, OK**. Log completo: [`docker-full.log`](p3-supervisor-progress-dashboard-2026-11-03-docker-full.log).
- `python -m py_compile scripts/run_agents.py scripts/config_panel.py`, `python scripts/config_panel.py --check` y `git diff --check` → **PASS**.
- Revisión estática independiente: detectó un `TypeError` ante campos JSON con tipo incorrecto y un `ValueError` ante enteros JSON demasiado largos. Ambos se corrigieron con tests de regresión; la revisión confirmó resueltos los dos hallazgos.
- Se inició una suite Windows no requerida por el plan (413 tests descubiertos) y se detuvo tras 146 resultados registrados; no mostró fallos antes de detenerse, pero **no cuenta como suite completa**. Log parcial: [`windows-full-partial.log`](p3-supervisor-progress-dashboard-2026-11-03-windows-full-partial.log). La verificación Windows reportada es la suite enfocada de 28 tests.
- Una primera corrida Docker usó la raíz `/workspace` y falló solo `test_valid_structure`, que requiere que la carpeta se llame como el paquete. Se repitió con destino `/scientific-software-engineering-council` y pasó completa. Log de esa corrida diagnóstica: [`docker-full-wrong-root.log`](p3-supervisor-progress-dashboard-2026-11-03-docker-full-wrong-root.log).

## Límites y pendientes

- No hay DAG general, log filtrado por especialista, retry de tareas ni panel de artefactos/diffs. Cancel conserva la señal ya existente al runner.
- No hay E2E real de proveedor en P3.5. La evidencia de procesos es local y simulada.
- El caso SIR con ecuaciones, unidades, condiciones iniciales y datos experimentales continúa `NOT_RUN` porque esos insumos no están disponibles; este dashboard no verifica resultados científicos.
- `scientific_core` seguirá ejecutando solo callbacks confiables, revisados y aprobados explícitamente por una persona. Un runner separado con aislamiento efectivo para código generado por agentes sigue `PLANNED`; Docker no se describirá como aislamiento absoluto.
- P3.5 no integra, mezcla ni aprueba cambios. El CI remoto de la rama y el PR se registrarán tras publicar la rama; el PR seguirá en borrador y sin merge.
