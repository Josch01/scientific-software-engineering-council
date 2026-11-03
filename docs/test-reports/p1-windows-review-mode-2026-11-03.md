# P1 — Corrección de modos ejecutables en evidencia de revisión Windows

**Estado del incremento:** implementado y revisado independientemente. La regresión Windows revisión→integración se verificará al apilarlo en P1.3.

**Base:** `8f8f3375c192d1bb17b7a65b19ac7cc8c59a8a43` (`codex/p1-independent-review-loop`, PR #12).
**Commits:** `6d18d95` diseño/plan; `3bbb1a5` implementación.
**Rama:** `codex/p1-windows-review-mode` (PR draft separado; base `codex/p1-independent-review-loop`).

## Defecto y cambio

Git conserva modo `100755` en el índice de Windows, aunque el snapshot copiado aparece como `100666`. El hash del candidato conservaba el modo lógico y el validador de revisión lo reconstruía desde `stat`, por lo que rechazaba un snapshot válido. El fallo afectaba también a ejecutables del árbol base que el worker no había cambiado.

La captura ahora conserva un inventario ordenado e inmutable de modos por ruta obtenido de las mismas entradas validadas que se copiaron. Los nuevos manifiestos de revisión usan schema 2 y validan el inventario de forma estricta. Para reportes exitosos se exige coincidencia exacta de rutas, bytes y modos con el digest del candidato. POSIX compara también el inventario con los modos físicos. Schema 1 mantiene su formato y lectura anteriores; los modos Windows ausentes no se inventan. Los intentos fallidos sin reporte conservan artefactos de forensia y no pueden convertirse en evidencia `PASS`.

No cambiaron el hash mode-aware, la validación de proveedores, el estado de aceptación ni la política de pruebas. No se llamó a Codex/Gemini; provider E2E queda `NOT_RUN`. La prueba de persistencia local con runtime fake prueba sólo el contrato y se conserva como evidencia no verificada.

## Verificación

| Entorno y comando | Resultado | SHA-256 del log |
|---|---:|---|
| Windows/Python 3.14: `python -m unittest -v tests.test_review_evidence tests.test_development_worktrees.WorktreeTests.test_review_persists_logical_modes_for_executable_baseline_without_provider_e2e` | 32 tests, OK; 2 skips explícitos | `d41392f081854540a50b250891d616eb205d9dd495d2ba8264c74a34f9927754` |
| Docker, imagen local `python:3.14.0-bookworm`: módulos enfocados `tests.test_review_evidence` y `tests.test_development_worktrees` | 118 tests, OK; 5 skips de plataforma | `1cc9c175ae082a7df456c5ea89659002b5083085c68576962254865261bac6f7` |
| Docker, raíz del paquete montada como `/scientific-software-engineering-council`: `python -m unittest discover -v` | 217 tests, OK; 5 skips de plataforma | `b72ea4e9ba9f51782b69953ea14d6053b85268217c3116dabf978758c67f4863` |
| Windows, copia local verificada con nombre canónico: `python -m unittest discover -v` | 217 tests; 2 errores de entorno, 3 skips. No se afirma suite verde. | `c2878b1d5199cf560fd5463052c19e503bab106db1d12047a27602f0c0e24f72` |

La suite Windows canónica no pudo crear symlinks en dos pruebas existentes: `tests.test_configuration.ConfigTests.test_symlink_refusal` y `tests.test_provider_modes.TestModes.test_symlink`; ambas reciben `WinError 1314` antes de ejecutar sus aserciones. No se cambiaron ni omitieron. La primera ejecución Linux montada en `/workspace` falló únicamente porque `test_valid_structure` requiere el nombre de raíz canónico; la repetición correcta pasó. Los logs originales y la copia Windows con manifiesto SHA-256 se conservan localmente en `.superpowers/sdd/2026-11-03-p1-windows-review-mode/`, fuera del commit.

`git diff --check` pasó. Los seis archivos Python cambiados pasan parseo de gramática Python 3.11 en el host Python 3.14. Python 3.11/3.12 reales y provider E2E: `NOT_RUN`. No se instalaron ni descargaron paquetes o imágenes.

## Revisión independiente y límite

La revisión acotada encontró el defecto original corregido y no halló defectos nuevos críticos o importantes. La prueba Windows real del snapshot `100755` ya no se omite. Aún debe ejecutarse, en la rama P1.3, la prueba que valida la revisión de worker y luego construye el candidato de integración con ese modo. Hasta completarla, el soporte de esa ruta integrada queda pendiente.

Este trabajo prueba contratos de evidencia de software. No afirma identidad/autenticidad del proveedor, sandbox efectivo, validez científica, aceptación humana ni readiness de release.
