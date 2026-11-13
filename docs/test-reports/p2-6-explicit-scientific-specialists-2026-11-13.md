# P2.6 — Especialistas científicos explícitos

**Estado:** EXPERIMENTAL. El router ahora planifica perfiles y evidencia obligatoria; no ejecuta modelos ni produce validación científica.

## Cambio

- `identifiability` asigna `identifiability_specialist`; `dynamics` asigna `dynamical_systems_specialist`; `differential_algebra` y `symbolic` asignan `differential_algebra_specialist`.
- Se preservan las responsabilidades existentes de `numerical_analyst` y `mathematical_model_specialist`; los especialistas nuevos cubren obligaciones acotadas y no sustituyen esas revisiones.
- Los dominios de claims científicos requieren `scientific_validation` desde R0/R1. R2/R3 conserva además revisión independiente y auditoría de seguridad.
- `prepare_agents` genera perfiles y task packets mediante los adaptadores existentes para Codex, Gemini y AGY. Ningún modelo fue invocado.

## Verificación

- RED observado: prueba de routing falló por ausencia de los tres roles; prueba de perfiles falló porque no había roles específicos que generar.
- PASS: `python -m unittest tests.test_routing tests.test_provider_modes -q` — 17 tests, 1 omitido por privilegio de symlink de Windows.
- PASS: `python -m unittest tests.test_integration_candidate.IntegrationCandidateTests.test_science_validation_stays_pending_after_software_manual_approval` — 1 flujo local, 333.7 s. La decisión manual conserva `scientific_validation` pendiente, `automatic_merge=false` y `release_status=NOT_APPROVED`; la revisión usa un fixture local, no un proveedor real.
- PASS: smoke `python scripts/route_task.py examples/seir_desktop_audit.json` — incluye los expertos de dinámica e identificabilidad y evidencia `scientific_validation`.
- PASS: `python scripts/validate_skill.py`, `python -m py_compile scripts/route_task.py scripts/prepare_agents.py`, `git diff --check`.
- PASS: CI del commit `ca2926980c7063510283197e2b5cbd50fc314b15`, 4/4 jobs Windows/Ubuntu × Python 3.11/3.12. La regresión agregada después queda pendiente de CI en el nuevo head.

## Límites

Los perfiles son asignaciones, no invocaciones reales. `scientific_validation` queda como obligación pendiente si no existe evidencia aceptada; su inclusión en el plan no constituye una revisión. La aprobación probada solo permite considerar manualmente la integración de software: no limpia esa obligación, no permite merge automático ni aprueba release o validez científica. Sin análisis nuevo del modelo/datos del usuario: SIR real `NOT_RUN`; validez científica, identificabilidad e incertidumbre `NOT_ASSESSED`.
