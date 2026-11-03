# P1.3 — Candidato integrado y verificación de checks

**Estado:** incremento P1.3 implementado y revisión independiente aprobada. La integración comprobada permanece bloqueada hasta P1.4 (revisión independiente del candidato integrado y decisión humana explícita).

**Base:** `206d59ccba65ecbff6fc4a5fabc52781184dae3f` (`codex/p1-windows-review-mode`).
**Branch:** `codex/p1-integration-candidate`.
**HEAD de código:** `dd9f5ba7e5b14ce7b247d92e34543b06c853c08d`.
**PR:** [borrador #15](https://github.com/Josch01/scientific-software-engineering-council/pull/15), apilado sobre `codex/p1-windows-review-mode`. No se hizo merge ni release.

## Implementación y decisiones

- Los `work_items` vinculan roles, ownership, outputs, checks y reviewers; no se permite que la integración copie rutas fuera de esos contratos.
- La integración crea un worktree desechable desde `base_commit`, aplica operaciones deterministas y conserva los worktrees fuente y worker. No hace commit ni altera la rama del usuario.
- Los checks declarados corren contra el candidato compuesto mediante el runner real de checks. La identidad `integration_candidate` se crea solo en memoria y no se agrega al roster canónico.
- El manifiesto de integración schema 2 liga candidate tree, operaciones, hashes de workers, checks y reviews al `execution_id`. El gate vuelve a derivar bindings exactos desde evidencia persistida y valida los archivos actuales.
- El gate selecciona el intento más reciente por ID timestamp-prefix. Un intento nuevo `BUILT`, fallido, incompleto o alterado no hereda un check previo. Los manifiestos históricos inválidos permanecen en `invalid_integration_manifests`, pero no agregan un blocker cuando el intento más reciente es válido.
- El gate sigue devolviendo `BLOCKED`, `evidence_verified=false`, `release_status=NOT_APPROVED` y `automatic_merge=false`. Los checks del candidato compuesto no conceden aceptación.

## Defectos encontrados y resueltos

1. Una ruta con superscript de dispositivo Windows podía evadir la detección de nombres reservados. Se añadió rechazo en `5ef370d`.
2. La composición podía modificar índices Git o publicar éxito canónico antes de validar todos los datos. Se hicieron la verificación de índice de solo lectura y la publicación atómica posterior a las validaciones en `e6a4188`.
3. Una ejecución integrada nueva no revalidaba los archivos del candidato de forma conjunta; ahora ejecuta los checks reales y reporta su manifiesto en `33c878f`.
4. La revisión independiente encontró que un intento histórico inválido ocultaba uno vigente válido y que hashes de worker inventados/listas de inputs incompletas podían verificarse. Se corrigió la selección de intento y se exige igualdad exacta con bindings rederivados para `execution_id` en `71cb0c6` y `9ad23e3`.
5. La prueba de `100755` estaba omitida en Windows, y sus fixtures aún usaban review schema 1. Tras rebasar sobre la corrección Windows de schema 2, se actualizaron fixtures para registrar `snapshot_logical_modes`, se eliminó el skip y el caso pasó.

## Verificación ejecutada

| Entorno | Comando | Resultado |
|---|---|---|
| Windows, Python 3.14 | `python -m unittest -v tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_manifest_and_check_identity_tampering_are_rejected_by_gate tests.test_integration_candidate.IntegrationCandidateTests.test_crash_after_built_publication_cannot_pass_gate tests.test_integration_candidate.IntegrationCandidateTests.test_invalid_historical_attempt_does_not_hide_latest_valid_integrated_checks tests.test_integration_candidate.IntegrationCandidateTests.test_executable_index_mode_is_preserved tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_checks_run_against_composed_candidate_and_gate_stays_blocked` | 5 tests, OK (163.089 s) |
| Docker Linux, imagen local `jerk-rpo-capd:6.1.0-python3.14.0` | El mismo comando, con el checkout montado en `/repo` | 5 tests, OK (10.434 s) |
| Windows, Python 3.14 | `python -m unittest -v tests.test_integration_candidate.IntegrationCandidateTests.test_executable_index_mode_is_preserved` | 1 test, OK (17.967 s); luego incluido en el bloque de cinco |
| Windows, antes de los últimos fixes/rebase | `python -m unittest -v tests.test_integration_candidate tests.test_development_worktrees` | 88 tests, OK, 4 skips; esta ejecución no cubre el estado final y no se usa como evidencia final del branch |
| Windows | `git diff --check` (código y pruebas, antes del commit del informe) | Sin errores; Git emitió solo avisos de normalización LF/CRLF |

## Revisión independiente

La revisión independiente de `e44b052..aeadf33` fue aprobada tras los fixes. Confirmó que (a) los bindings de worker/check/reviewer se rederivan por `execution_id`, (b) el intento histórico permanece diagnóstico sin bloquear un intento vigente válido, (c) el último intento incompleto no hereda PASS y (d) el bloqueo obligatorio por revisión integrada/aprobación humana sigue presente. No reportó findings Critical o Important pendientes.

El fix Windows de modos lógicos fue revisado independientemente en su propio incremento y sus GitHub Actions terminaron exitosamente en `41592879271`. La prueba de integración review→candidato que estaba omitida ya se ejecutó sin skip en Windows y Docker/Linux.

## Límites y pendientes

- Provider E2E real Codex/Gemini, identidad de cuenta, independencia efectiva del reviewer y sandbox de SO: `NOT_RUN`/`UNVERIFIED`. Los hashes locales no autentican a un usuario con escritura en el almacén.
- Revisión independiente del candidato integrado y decisión humana explícita: pendientes del siguiente incremento P1; por ello el gate nunca reporta aceptación.
- Scheduler DAG, recuperación durable tras restart e idempotencia global: pendientes; documentados para cierre acotado de P1 o seguimiento si no afectan al primer ciclo local.
- Fix loop automático acotado: pendiente; los fallos y findings continúan bloqueando y requieren una nueva acción explícita.
- Pruebas científicas, identificación estructural de parámetros y validez matemática: `NOT_RUN`. Esta fase valida integración de software, no el modelo científico.
- Suite completa del repositorio y structural check sobre el HEAD final: `NOT_RUN` en este incremento; se difieren a la verificación del flujo P1 completo para no repetir una suite larga tras cada fix acotado.
