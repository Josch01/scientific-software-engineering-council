# P1.4 — revisión integrada y decisión humana (2026-11-03)

## Alcance y revisión

Rama: `codex/p1-integrated-review-approval`; base de integración propuesta: `codex/p1-integration-candidate`. Fuente de la verificación original: `2f76bb09af5ebc2d13307035e3890afc4ffd656f`; el commit documental `7c1e12e` añadió informe, matriz y estado del plan. La corrección posterior de revisión final y su evidencia enfocada se registran al final de este informe. No se hizo merge, tag, release ni publicación.

| Commit | Cambio y revisión |
|---|---|
| `8385c38` | Diseño y plan P1.4. |
| `680e1b7` | Inventario persistido de sesiones. |
| `4ea29fb` | Corrección tras revisión: rechazar reparse antes de load/runtime y conservar destino create-only. |
| `6287139` | Estado/documentación Task 1. |
| `94d2524` | Review explícita del candidato integrado, bundle y bindings. |
| `b3808e9` | Corrección tras revisión: inventarios completos corroborados con transcripts; historial interrumpido bloquea. |
| `f6f64f3` | Estado/documentación Task 2. |
| `7abdbbf` | Gate y decisión humana enlazada a evidencia vigente. |
| `04c59bb` | Corrección tras revisión: ambas decisiones exigen reviewers completos; evidencia BLOCKED/FAILED prevalece sobre findings. |
| `2f76bb0` | Contrato final de decisión y estado Task 3. |

Los informes de Tasks 1/2, conservados bajo `.superpowers/sdd/2026-11-03-p1-integrated-review-human-decision/` (archivos versionados), y el registro local `.superpowers/sdd/2026-11-03-p1-integrated-review-human-decision/task-3-report.md` registran RED/GREEN y fixes de revisión. El controlador confirmó revisión independiente aprobada de los cambios de Tasks 1–3. La revisión independiente del paquete final de Task 4 y la creación del draft PR se registran por separado; este informe no las presume realizadas.

## Evidencia Windows

Entorno: Windows, PowerShell, Python 3.14.0. Logs completos redirigidos a `.superpowers/sdd/2026-11-03-p1-integrated-review-human-decision/task-4-*.log` (metadata local ignorada; los totales se conservan aquí).

| Comando/grupo | Resultado |
|---|---|
| Inventario/reparse, offline y preview (Task 1), ejecución fresca | OK: 6 tests, 67.137 s; 0 fallos, 0 errores, 0 skips. |
| Task 2, seis casos exactos + siete regresiones P1.3 | OK: 13 tests, 553.737 s; 0 fallos, 0 errores, 0 skips. Evidencia vigente de `04c59bb`, sin cambios posteriores de código. |
| Task 3, seis casos de gate/decisión | OK: 6 tests, 517.360 s; 0 fallos, 0 errores, 0 skips. Misma fuente final. |
| Dos regresiones de decisión con reviewers incompletos | OK: 2 tests, 247.664 s; 0 fallos, 0 errores, 0 skips. Misma fuente final. |
| `python -m unittest discover -v -s tests` | FAIL, exit 1: 298 tests en 2397.351 s; 289 PASS, 1 failure, 2 errors, 6 skips. Detalle abajo. |
| `python scripts/validate_skill.py` | FAIL, exit 1: `frontmatter name must match root directory name`; la carpeta del worktree se llama `p1-integrated-review-approval`. |
| Mismo validador en export Git HEAD con carpeta `scientific-software-engineering-council` | PASS, exit 0: `VALID STRUCTURE`; export temporal, sin modificar código/validator. |
| `python -m unittest -v tests.test_structure` en el mismo export correctamente nombrado | PASS: 1 test, 0.015 s; 0 fallos/errores/skips. |
| `python -m compileall -q scripts tests` | PASS, exit 0. |
| `git diff --check` | PASS, exit 0; comprobación repetida al cerrar el informe. |

El resultado global es **FAIL**, no una suite totalmente verde. Los tres problemas corresponden al entorno/ubicación:

- `test_structure.StructureTests.test_valid_structure`: failure por `frontmatter name must match root directory name`; el mismo HEAD pasa al exportarlo bajo el nombre exigido.
- `test_configuration.ConfigTests.test_symlink_refusal`: error `WinError 1314` al crear el fixture `.ssec`, antes de probar la guarda.
- `test_provider_modes.TestModes.test_symlink`: error `WinError 1314` al crear el fixture `.gemini`, antes de probar la guarda.

Los seis skips fueron:

| Test | Motivo |
|---|---|
| `test_integration_candidate.IntegrationCandidateTests.test_casefold_sibling_collision_blocks` | Filesystem sensible a mayúsculas requerido. |
| `test_integration_candidate.IntegrationCandidateTests.test_special_output_is_rejected_without_opening_it` | FIFO requiere POSIX. |
| `test_integration_candidate.IntegrationCandidateTests.test_symlink_output_is_rejected_before_candidate_creation` | Creación de symlink sin privilegio (`WinError 1314`). |
| `test_posix_process_containment.PosixProcessContainmentTests.test_native_sa_nocldwait_is_rejected_before_work_launch` | Requiere semántica Linux sigaction. |
| `test_review_evidence.ReviewManifestTests.test_rejects_symlink_references` | Fixture de symlink no disponible en este host. |
| `test_review_evidence.ReviewManifestTests.test_schema2_rehashed_posix_chmod_tampering_rejected` | Semántica chmod POSIX. |

Los seis casos Task 1 ejecutados aisladamente fueron `test_execute_persists_runtime_session_inventory`, `test_execute_session_manifest_failure_keeps_review_incomplete`, `test_execute_rejects_reparse_metadata_before_load_or_runtime`, `test_runtime_session_inventory_refuses_existing_destination`, `test_offline_provider_fixture_cannot_be_counted_as_review_evidence` (clase `tests.test_development_worktrees.WorktreeTests`) y `test_preview_and_missing_ack_make_zero_runtime_calls` (clase `tests.test_development_worktrees.RuntimeRunnerTests`).

La suite fresca también confirmó PASS en todos los casos enfocados de Tasks 1–3, incluidos ambos tests de reviewers incompletos; no hubo fallos de aserción P1.4. Las guardas reparse simuladas pasan sin requerir privilegio de symlink; eso no reemplaza los fixtures reales omitidos o bloqueados.

No se repitieron aisladamente los 21 casos vigentes de Tasks 2/3 para ahorrar una ejecución redundante: la suite final también los descubre. Los seis casos Task 2 son preview sin proveedor, latest checked candidate, sesión reutilizada, roster incompleto/mal ligado, latest review incompleta y metadata reparse. Los seis Task 3 son NEEDS_HUMAN, digest exacto, drift, integración nueva, merge/release deshabilitados y rechazo de findings completos. Las dos regresiones adicionales son `test_decision_rejects_incomplete_reviewer_results` y `test_gate_rejects_decision_bound_to_incomplete_reviewer_results`.

RED histórico: Task 1 tuvo dos fallos esperados por inventario/hook ausente; Task 2 seis ModuleNotFoundError antes de existir el módulo; Task 3 falló antes de implementar gate/decisión. La corrección `04c59bb` confirmó RED en los dos tests nuevos (ocho subcasos fallidos por aceptación indebida de rechazo) y GREEN en ambos tras exigir evidencia terminal completa. No se volvió a deshacer código para recrear RED en la entrega documental.

## Entornos no ejecutados y límites

- Docker/Linux: `BLOCKED`. El controlador comprobó que el daemon local falla con `failed to connect to ... dockerDesktopLinuxEngine`; no se instaló ni se reintentó repetidamente. No hay resultado Linux para P1.4.
- Provider E2E Codex/Gemini: `BLOCKED` para cierre verificado. Se ejecutó una sola invocación real mediante `GeminiRuntime`/`gemini` 0.64.0: proceso `FAILED`, exit code 41, stdout vacío y sin sesión/respuesta observada. Se conservó únicamente el SHA-256 de stderr (`c3ad69d861b08eb4c63c5b6e21e0b19fd38213edf10fd89623a2289d8eadd071`), no el diagnóstico legible; la causa queda sin determinar y no se reintentó. La CLI local `agy` 1.4.12 sí está instalada y su ayuda confirma `--prompt`/`-p`, `--output-format json` y `--sandbox`; no se le envió un prompt, por lo que su autenticación, sesión real y adaptación desde SSEC siguen `NOT_RUN`. La [documentación oficial de modo headless de AGY](https://antigravity.google/docs/cli/headless/) documenta `agy -p "..."`; esto no convierte el intento fallido de Gemini en evidencia de AGY.
- Independencia de sesión/cuenta/contexto y sandbox efectivo: `UNVERIFIED`. IDs distintos y hashes locales no autentican proveedor ni demuestran aislamiento de SO.
- GUI visual: `NOT_RUN`; no hay validación científica ni certificado matemático/numérico nuevo.

## Decisión arquitectónica y operación

Se reutiliza `_review_one()` en un comando explícito sobre el último candidato compuesto con checks válidos. Preview no invoca runtimes; ejecutar requiere `--execute --accept-unmetered-cost`. Cada rol exacto del roster usa un nuevo objeto runtime y produce manifiesto ligado a task/revisión/digest/base, integration ID, tree, check y bundle. Las guardas reparse se aplican antes de resolver o hacer I/O de metadata.

Inventarios deben contener el roster completo de implementación, sesiones corroboradas con stdout canónico y registros terminales coherentes. Historial legacy sin inventario, inventario parcial, transcript ausente/malformado, intentos interrumpidos o logs huérfanos bloquean review. No se migran ni se borran automáticamente: puede requerirse un task/workspace/run nuevo con historial completo, tras revisión manual.

Review completa PASS produce `NEEDS_HUMAN`. `APPROVE_FOR_MANUAL_INTEGRATION` exige todos los PASS y digest completo del bundle actual; `REJECT` admite findings `REQUEST_CHANGES` completos. Ambos rechazan reviewers BLOCKED/FAILED, faltantes o mal ligados. Cada lectura revalida candidato/checks/latest/bundle y decisión; drift, intento nuevo incompleto o digest viejo invalidan la decisión previa. El archivo de decisión es create-only por integración.

`operator` es un nombre declarado, sin autenticación ni firma. Quien puede editar coherentemente el almacén local puede alterar evidencia; hashes verifican bindings/contenido local. Aprobar solo registra consideración para integración manual: siempre `automatic_merge=false` y `release_status=NOT_APPROVED`.

El retry es manual y acotado: un finding exige cambios de workers y una nueva integración con ID nuevo; no existe fix loop autónomo ni recuperación durable general. Un nuevo intento incompleto no hereda PASS ni aprobación anterior. P2/P3/P4 no se declaran completados; GUI, ciencia y release quedan fuera del incremento.

## Corrección de revisión final: historial de worker reviews incompleto

Sobre `7c1e12ef9aa809ed7a49f2ba8d52d702fc0ae4c9`, se reprodujo que un run anterior `REVIEW_INCOMPLETE` podía contener stdout de una worker review sin manifest, o un manifest `FAILED` con sesión nula, y quedar fuera del control de reutilización. Un candidato posterior válido con bundle PASS seguía siendo elegible.

`_historical_sessions` ahora exige manifest y stdout canónicos, regulares y protegidos por las guardas reparse; valida el manifest completo y sus bindings de task/worker/reviewer/provider/stdout; exige correspondencia de cada sesión con el inventario y evidencia canónica para cada entrada inventariada. Salida no vacía sin sesión corroborada bloquea. No se recuperan IDs desde contenido no confiable.

RED y GREEN usan exactamente:

```text
python -m unittest -v tests.test_integration_candidate.IntegrationCandidateTests.test_prior_worker_review_missing_manifest_blocks_later_valid_candidate tests.test_integration_candidate.IntegrationCandidateTests.test_prior_worker_review_null_session_with_output_blocks_later_valid_candidate
```

RED: `FAILED (failures=10)`, 2 tests en 131.404 s. Ambos casos reprodujeron gate `NEEDS_HUMAN`, aceptación de bundle/preview y llegada indebida a runtime factory. GREEN: `OK`, 2 tests en 113.311 s, sin fallos, errores ni skips. Cada caso parte de un candidato posterior y bundle válidos, confirma `NEEDS_HUMAN` antes de introducir el historial interrumpido y después exige gate `BLOCKED`, rechazo de bundle/preview/ejecución y cero llamadas al runtime factory.

Regresiones afectadas: `OK`, 14 tests en 425.837 s, sin fallos, errores ni skips: los ocho casos Task 2 de historial/preview/latest/reutilización/roster/reparse, `test_gate_needs_human_after_valid_integrated_review`, `test_decision_rejects_incomplete_reviewer_results`, `test_gate_rejects_decision_bound_to_incomplete_reviewer_results` y los tres tests de `tests.test_release_gate`. Comando exacto conservado en el informe Task 2. Total de esta corrección: 16 tests enfocados GREEN. `python -m py_compile scripts/integration_review.py tests/test_integration_candidate.py` y `git diff --check`: PASS. No se repitió la suite amplia; su resultado original arriba permanece sin cambios.

Límite operativo: historial legacy con manifest/stdout ausente, evidencia no ligada o salida no vacía con sesión nula ahora bloquea incluso si una ejecución posterior es válida. No se migra ni descarta automáticamente; puede requerir un task/workspace nuevo con historial completo tras revisión manual. Fixtures locales exclusivamente; provider E2E sigue `NOT_RUN`, independencia/sandbox siguen `UNVERIFIED`.

## Entrega

PR draft [#16](https://github.com/Josch01/scientific-software-engineering-council/pull/16), base `codex/p1-integration-candidate`, head `codex/p1-integrated-review-approval`. Abierto y sin merge; no release.
