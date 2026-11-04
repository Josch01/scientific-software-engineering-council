# P4.4 — Auto revisión adversarial acotada

**Estado:** `EXPERIMENTAL`. Se contrastaron las amenazas requeridas en `CODEX_MASTER_MISSION.md` con los tests disponibles y la CI más reciente que ejecutó el conjunto completo de P1–P3. No se hicieron llamadas de proveedor ni una suite nueva.

## Controles con evidencia existente

| Amenaza | Evidencia disponible |
|---|---|
| Worker falso declara revisión/aprobación o test aprobado | `test_mailbox_rejects_worker_self_review`, `test_mailbox_rejects_privileged_events_for_every_sender`, `test_gate_ignores_privileged_events_injected_into_mailbox`; manifiestos de evidencia requieren exit 0, identidad de candidato, test count y contención (`tests/test_execution_evidence.py`). |
| Paquete incompleto, fuente dirty, checks ausentes o colisión | `test_load_revalidates_work_items_even_with_recomputed_packet_digest`, `test_gate_blocks_missing_checks_and_collisions`, `test_wrong_task_or_dirty_source_rejected` en `tests/test_development_worktrees.py`. |
| Exposición de secretos | `test_snapshot_excludes_known_secrets` en `tests/test_runner.py`; es una política/fixture concreta, no un escaneo exhaustivo de secretos. |
| Proveedor ausente, timeout, cancelación y descendientes | `test_missing_cli_blocks_and_logs` (`test_runner.py`); timeout/cancel/cleanup en `tests/test_provider_runtimes.py`, incluidos hijos locales y confirmación de contención antes de publicar evidencia. |
| Symlink/traversal y presupuestos de recursos | Tests de modo symlink/traversal del workspace loader, límites de artefactos y rechazo de diff parcial; los manifiestos se vuelven a validar antes de aprobar. |

La ejecución remota completa más reciente de estas pruebas es CI PR #43, [run 41805070338](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41805070338): 4/4 jobs `success`, Windows/Ubuntu × Python 3.11/3.12. P3.17 y P3.18 también pasaron sus matrices completas en CI PR #41 y #42.

## Estados no verificados

- Inyección adversarial de instrucciones dentro de un `Task Packet` con proveedor real: `NOT_RUN`. Hay tests del transporte del prompt como argumento único, pero no se ejecutó un runtime real bajo ataque.
- Rate limit y desbordamiento real del contexto de Codex/Gemini: `NOT_RUN`; no se invocaron proveedores.
- Cancelación durante escritura concurrente de un artefacto grande real: `NOT_RUN`; los tests cubren fallos de persistencia, cancelación de worker y publicación terminal, no todos los cortes de energía/OS.
- Symlink creado localmente en Windows con permisos limitados: `NOT_RUN` cuando la creación del fixture falla por `WinError 1314`; CI Windows no se usa aquí para afirmar que esa ruta se ejercitó salvo evidencia del runner.
- Edición coherente de estado/logs por el mismo usuario con acceso al workspace: `UNVERIFIED`; hashes detectan cambios no coherentes, pero no autentican una identidad ni una fuente de confianza.
- Consistencia independiente de este informe: `VERIFIED` mediante revisión documental acotada. El revisor contrastó el reporte completo, sus mapeos de pruebas y las referencias CI de PR #43, #41 y #42; no encontró contradicciones P0–P2. No revisó toda la base de código ni ejecutó pruebas o proveedores.
- Revisión independiente integral del sistema/código P4.4: `NOT_RUN`; la revisión documental anterior no la sustituye.
- Escaneo automatizado de secretos/dependencias/vulnerabilidades y benchmark de tres proyectos: `NOT_RUN`; las herramientas requerirían selección/aprobación de dependencias y los benchmarks reales requieren proyectos de referencia y autorización de proveedor.

## Hallazgos y alcance

No se reprodujo un nuevo defecto P0–P2 en esta lectura de cobertura. Esto no es una certificación de seguridad ni reemplaza las verificaciones `NOT_RUN` anteriores. No se abrió otra ronda de hardening por asuntos menores.
