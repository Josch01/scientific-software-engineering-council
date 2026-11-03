# P1.4 — Revisión integrada y decisión humana

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Completar el ciclo P1 con una revisión del candidato integrado y una decisión humana ligada al bundle exacto, manteniendo bloqueados merge y release automáticos.

**Architecture:** Reusar `_review_one()` sobre el candidato validado, con un comando explícito y un bundle versionado independiente del manifiesto checked. Persistir las sesiones vistas durante `execute()` para evitar reusar una sesión; derivar el gate desde checks, roster de reviewers y decisión local inmutable.

**Tech Stack:** Python estándar, Git/worktrees temporales, adaptadores Codex/Gemini ya existentes, `unittest`; sin paquetes nuevos.

**Spec:** `docs/superpowers/specs/2026-11-03-p1-integrated-review-human-decision-design.md`.

## Global constraints

- El comando de review hace cero invocaciones sin `--execute`; el lanzamiento requiere `--accept-unmetered-cost`.
- Solo `CodexRuntime` o `GeminiRuntime` concretos pueden producir review contable; FakeRuntime/fixtures solo validan contratos y nunca son provider E2E.
- No cambiar worktrees fuente/worker, manifiesto checked ni checkout del usuario; no commit, merge, push o release automático.
- El roster de reviewers es exactamente `state["review_roles"]`; no se acepta subconjunto ni reviewer extra.
- Metadata y artefactos se verifican contra symlink, junction y cualquier reparse point antes de `resolve()`, lectura o escritura.
- Hashes identifican contenido local, pero no autentican a una persona, proveedor, cuenta, ciencia o sandbox.
- La aprobación propuesta solo autoriza consideración para integración manual; mantener `automatic_merge=false` y `release_status=NOT_APPROVED`.
- Una corrección requiere nuevos workers y nueva integration ID. No implementar un fix loop automático.

## Review focus

1. **Sesión/runtime reusado:** persistir `execution_id`, sesiones de implementación y reviews por rol/provider; un session ID duplicado bloquea la review integrada. Test: `test_integrated_review_rejects_reused_runtime_session`.
2. **Evidencia vieja:** latest integration/review incompleta no hereda PASS o aprobación anterior. Tests: `test_latest_incomplete_review_does_not_reuse_previous_pass`, `test_new_integration_invalidates_old_human_decision`.
3. **Roster y bindings:** missing/extraneous reviewer, manifest hash, check path/hash, task/base, integration ID o candidate digest alterado bloquean. Test: `test_review_bundle_rejects_incomplete_or_misbound_roster`.
4. **Rutas Windows:** junction/reparse bajo metadata se rechaza antes de resolver/leer/escribir bundle, snapshot o decision. Test: `test_integrated_review_rejects_metadata_reparse_path`.
5. **Decisión obsoleta o ambigua:** digest ausente, abreviado, incorrecto o viejo bloquea; aprobación nunca habilita merge/release. Tests: `test_decision_requires_exact_current_bundle_digest`, `test_approval_never_enables_merge_or_release`.

---

### Task 1: Persistir sesiones de ejecución

**Files:**
- Modify: `scripts/development_runner.py`
- Modify: `tests/test_development_worktrees.py`

**Interface:**
- `execute()` crea `dev-logs/<run_id>/runtime-sessions.json` con schema 1, identidad de task, run_id, estado terminal y listas ordenadas de sesiones de implementación y worker-review. Cada registro contiene role, provider, session ID y estado.
- Añadir al reporte `runtime_sessions_manifest_path` y `runtime_sessions_manifest_sha256`. La escritura atómica falla cerrada: el reporte no marca reviews completas si no se puede persistir el manifest.
- No se invocan runtimes adicionales en preview.

- [x] **Step 1: Escribir pruebas RED**

Añadir `test_execute_persists_runtime_session_inventory` y `test_execute_session_manifest_failure_keeps_review_incomplete`. Usar el runtime local/fake existente solo para probar los datos persistidos; no marcarlo como review válida.

- [x] **Step 2: Ejecutar y confirmar RED**

Run: `python -m unittest -v tests.test_development_worktrees.WorktreeTests.test_execute_persists_runtime_session_inventory tests.test_development_worktrees.WorktreeTests.test_execute_session_manifest_failure_keeps_review_incomplete`

Expected: los campos/archivo de sesiones no existen o el fallo de escritura no bloquea el estado.

- [x] **Step 3: Implementar persistencia atómica y guarda reparse-aware**

Usar la identidad de `state`, `report["results"]` y `report["review_evidence"]`. No escribir secretos ni prompts/logs en este inventario.

- [x] **Step 4: Ejecutar GREEN y regressions relacionadas**

Run: los dos tests anteriores y `python -m unittest -v tests.test_development_worktrees.WorktreeTests.test_offline_provider_fixture_cannot_be_counted_as_review_evidence`.

- [x] **Step 5: Commit** — `680e1b7` (implementación), `4ea29fb` (fix de revisión independiente).

`feat: persist runtime session inventory`.

### Task 2: Ejecutar y validar review integrada

**Files:**
- Create: `scripts/integration_review.py`
- Modify: `scripts/development_runner.py` (solo guardas reparse-aware que necesita `_review_one`)
- Modify: `scripts/review_evidence.py` (validación reparse-aware)
- Modify: `tests/test_integration_candidate.py`

**Interfaces:**

- `run_integration_review(project, task_id, integration_id, *, launch=False, cost_ack=False, minutes=30, runtime_factory=None) -> dict`.
- `validate_integration_review_bundle(path, metadata, state, integration, check_manifest) -> dict`.
- CLI: `python -m scripts.integration_review review --project PATH --task-id ID --integration-id ID [--execute --accept-unmetered-cost] [--max-minutes N]`.
- Bundle path: `metadata/integrations/<integration_id>/review-attempts/<review_attempt_id>/bundle.json`.

- [x] **Step 1: Escribir pruebas RED**

Añadir `test_integrated_review_preview_makes_no_provider_call`, `test_integrated_review_requires_latest_checked_candidate`, `test_integrated_review_rejects_reused_runtime_session`, `test_review_bundle_rejects_incomplete_or_misbound_roster`, `test_latest_incomplete_review_does_not_reuse_previous_pass` y `test_integrated_review_rejects_metadata_reparse_path`.

- [x] **Step 2: Ejecutar y confirmar RED**

Run: `python -m unittest -v tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_preview_makes_no_provider_call tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_requires_latest_checked_candidate tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_reused_runtime_session tests.test_integration_candidate.IntegrationCandidateTests.test_review_bundle_rejects_incomplete_or_misbound_roster tests.test_integration_candidate.IntegrationCandidateTests.test_latest_incomplete_review_does_not_reuse_previous_pass tests.test_integration_candidate.IntegrationCandidateTests.test_integrated_review_rejects_metadata_reparse_path`

Expected: el comando/validador no existe.

- [x] **Step 3: Reusar `_review_one()` sin lanzar workers**

Exigir que `integration_id` sea el latest, que su manifest/check estén validados y PASSED, que el `runtime-sessions.json` corresponda al mismo execution ID y que todas las sesiones históricas conocidas sean únicas. Ejecutar exactamente una vez cada `state["review_roles"]`, en snapshots no-writable, con deadline/cancelación existentes. Bundle liga hashes de integration manifest, check y cada review manifest.

- [x] **Step 4: Ejecutar GREEN y regresiones relacionadas**

Run: los seis tests de Task 2 y los tests de `test_executable_index_mode_is_preserved` y `test_integrated_checks_run_against_composed_candidate_and_gate_stays_blocked`.

- [x] **Step 5: Commit** — `94d2524` (flujo inicial), `b3808e9` (historias verificables; revisión independiente aprobada).

`feat: review integrated candidate with bound evidence`.

### Task 3: Gate y decisión humana explícita

**Files:**
- Modify: `scripts/integration_review.py`
- Modify: `scripts/worktree_coordinator.py`
- Modify: `tests/test_integration_candidate.py`

**Interfaces:**

- `record_human_decision(project, task_id, integration_id, *, expected_bundle_sha256, decision, operator, reason) -> dict`.
- CLI: `python -m scripts.integration_review decide --project PATH --task-id ID --integration-id ID --expected-bundle-sha256 SHA256 --decision APPROVE_FOR_MANUAL_INTEGRATION|REJECT --operator TEXT --reason TEXT`.
- Decision path: `metadata/integrations/<integration_id>/human-decision.json`, create-only, schema 1.
- `gate()` añade `integrated_review_verified`, bundle hash/status, `human_decision_verified`, decision status, y estados `BLOCKED | CHANGES_REQUESTED | NEEDS_HUMAN | APPROVED_FOR_MANUAL_INTEGRATION | REJECTED_BY_HUMAN`.
- Ruling: `APPROVE` requiere bundle actual terminal y roster completo con todos los veredictos `PASSED`; `REJECT` también requiere evidencia terminal, íntegra y roster completo, y admite veredictos `REQUEST_CHANGES`. `BLOCKED`, `FAILED`, manifests faltantes o evidencia mal ligada bloquean ambas decisiones.

- [x] **Step 1: Escribir pruebas RED**

Añadir `test_gate_needs_human_after_valid_integrated_review`, `test_decision_requires_exact_current_bundle_digest`, `test_candidate_drift_invalidates_human_decision`, `test_new_integration_invalidates_old_human_decision`, y `test_approval_never_enables_merge_or_release`.

- [x] **Step 2: Ejecutar y confirmar RED**

Run: los cinco tests; deben fallar antes de implementar la decisión/gate.

- [x] **Step 3: Implementar decisión inmutable y revalidación**

Aceptar solo `APPROVE_FOR_MANUAL_INTEGRATION` o `REJECT`, digest SHA-256 completo y exacto del bundle vigente, integration ID explícito, operator/reason no vacíos. Rechazar overwrite. En gate, rederivar todo el evidence set y descartar cualquier decisión ligada a tree/check/review/latest distinto.

- [x] **Step 4: Ejecutar GREEN**

Run: los cinco tests, los seis tests de Task 2 y P1.3 history/tamper/executable-mode regressions.

- [x] **Step 5: Commit** — `7abdbbf` (gate/decisión), `04c59bb` (evidencia completa; review aprobado).

`feat: gate manual decision on current integrated review`.

### Task 4: Documentar, revisar y entregar PR separado

**Files:**
- Create: `docs/test-reports/p1-integrated-review-human-decision-2026-11-03.md`
- Update: `docs/roadmap/FEATURE_MATRIX.md` solo cuando el ciclo P1 completo tenga evidencia; no adelantar estados P2.

- [ ] **Step 1: Ejecutar pruebas enfocadas en Windows y Docker/Linux**

Registrar RED/GREEN, skips, resultados con fixture, y `NOT_RUN` provider E2E. Los fixtures de PASS no son evidencia de provider E2E.

- [ ] **Step 2: Ejecutar suite final de P1 y validación estructural**

Run: `python -m unittest discover -v -s tests`; `python scripts/validate_skill.py`; `python -m compileall -q scripts tests`; `git diff --check`. Repetir la suite Python en la imagen Docker local si el tiempo es razonable. Reportar `NOT_RUN` o errores de privilegios sin ocultarlos.

- [ ] **Step 3: Registrar decisión arquitectónica y límites**

Documentar commits, tests, review, provider/sandbox `UNVERIFIED`, operador no autenticado, retry manual y ausencia de validez científica/GUI.

- [ ] **Step 4: Review independiente del diff**

Usar un paquete de review acotado de esta rama; corregir findings Critical/Important antes de declarar el incremento listo.

- [ ] **Step 5: Commit y crear PR draft separado**

Base: `codex/p1-integration-candidate`. No merge a `main`, tag ni release.
