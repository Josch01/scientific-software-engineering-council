# P1.2 — Etapa de revisión de candidatos por worker

**Resultado:** implementado como etapa experimental; P1 no está cerrado.  
**Base:** `efb3087831d11de2bd8e9654636eb53ec75b6261` (`codex/p1-coordinator-evidence`).  
**Commit del incremento:** `9a3d72f` (`feat: add evidence-bound worker review stage`).  
**Fecha de verificación:** 2026-11-02.  
**Plataformas:** Windows 11 Pro, Python 3.14.0; Docker Linux, `python:3.14.0-bookworm`, image `sha256:ec171bc30122c014f83f7756fe21c4ab26d33e7c4610a63a18da2728f9ed33f8`.

## Qué implementa y por qué

El coordinador ahora invoca reviewers después de que todos los workers pasan sus checks deterministas. Para cada candidato crea una copia separada, enlaza el review al task, worker, tree hash, diff, manifiesto de checks y salida del runtime, y valida un reporte JSON estricto. Los diffs se capturan con límite de 1 MiB y sin filtros de texto externos. Los artefactos incompletos se registran como intentos fallidos; si falla el guardado del manifiesto, el intento no queda en estado exitoso.

La etapa comprueba la transición `checks → review por snapshot`, conserva evidencia y evita tratar fixtures como llamadas reales a proveedores. No integra los árboles de varios workers, no corre un fix loop y no cambia la decisión de release.

## Pruebas ejecutadas

Para las filas Docker, el comando se ejecutó en `python:3.14.0-bookworm` mediante `docker run --rm --pull=never --mount "type=bind,source=C:\Users\artur\Documents\Skill\ssec-worktrees\p1-independent-review-loop,target=/workspace/scientific-software-engineering-council" --workdir /workspace/scientific-software-engineering-council`; el comando de la tabla va como argumento de imagen.

| Entorno | Comando | Resultado | Salida guardada |
|---|---|---:|---|
| Docker Linux, Python 3.14.0 | `docker run --rm --pull=never --mount "type=bind,source=C:\Users\artur\Documents\Skill\ssec-worktrees\p1-independent-review-loop,target=/workspace/scientific-software-engineering-council" --workdir /workspace/scientific-software-engineering-council python:3.14.0-bookworm python -m unittest discover -v -s tests` | exit 0; **201 tests OK** | [log](p1-independent-review-stage-2026-11-02-docker-unittest.log), SHA-256 `C4FC8C837ADC6DB5EC131E3430D3991F4CB6F126F282D2AE80C1DCB19E4BC7A1` |
| Docker Linux, Python 3.14.0 | `python -m unittest tests.test_development_worktrees tests.test_review_evidence tests.test_reviewer_output tests.test_provider_runtimes` | exit 0; **113 tests OK** | [log](p1-independent-review-stage-2026-11-02-docker-focused.log), SHA-256 `557EDFC09DBD2784436A617FDB0FE2A5E8A7D0CFA01F7CAE7CE77189482657C1` |
| Windows 11, Python 3.14.0 | `python -m unittest tests.test_development_worktrees.WorktreeTests.test_attempt_persistence_failure_prevents_successful_review_manifest tests.test_development_worktrees.WorktreeTests.test_manifest_persistence_failure_marks_successful_attempt_failed tests.test_review_evidence.ReviewEvidenceTests` | exit 0; **9 tests OK** | [log](p1-independent-review-stage-2026-11-02-windows-focused.log), SHA-256 `E30A1E57EA334381856833F367EBFC8BC21A006704AA16E0222E84B97E271AC6` |
| Docker Linux, Python 3.14.0 | `python scripts/validate_skill.py` | exit 0; `VALID STRUCTURE` | [log](p1-independent-review-stage-2026-11-02-docker-validator.log), SHA-256 `5FFC92F13CB27C289CBB1FA8CB77897EC203C0254B8CA6F89D805254C208A37E` |
| Docker Linux, Python 3.14.0 | `python -m compileall -q scripts tests` | exit 0 | Sin salida |
| Windows 11, Git | `git diff --check` | exit 0 | Sin salida |

El contenedor se montó en `/workspace/scientific-software-engineering-council`, nombre canónico que requiere el validador del frontmatter. Una corrida anterior montada como `/workspace/ssec` falló solo por ese nombre de montaje; al usar la ruta canónica, el test estructural y el validador pasaron. No se alteró el frontmatter para ocultar la diferencia.

La suite completa de Windows tras este commit: `NOT_RUN`. El grupo Windows de nueve tests sí ejecutó las rutas de persistencia y schema que cambiaron en este incremento.

## Defectos detectados y correcciones

- La revisión estática encontró que un `git diff` podía ejecutar filtros `textconv` configurados en el repositorio. Se añadió `--no-textconv` y una regresión que detecta ejecución de un filtro externo.
- La revisión detectó que un intento podía conservar `REVIEW_REPORT_VALID` si después fallaba el manifiesto. La persistencia ahora rebaja el intento a `FAILED` y hay regresión de fallo de almacenamiento. También se prueba que el fallo al guardar el intento impide guardar el manifiesto.
- En Docker Linux, el escaneo de `/proc/<pid>/stat` podía lanzar `ProcessLookupError` si el proceso desaparecía entre la enumeración y lectura. Se trata como una entrada de `/proc` racy; otros errores continúan cerrando la ejecución.
- Una corrida completa intermedia registró 200 tests y falló solo en la comprobación estructural porque el montaje usaba `/workspace/ssec`, cuyo nombre no coincide con el frontmatter. La repetición con la ruta canónica y el test nuevo sobre el commit final pasó 201/201. No queda un fallo conocido de la suite del commit `9a3d72f` en el entorno Docker reportado.

## Revisión y decisiones arquitectónicas

Una revisión independiente del diff informó los casos `exit 0` con review incompleta, runtime fixture que aparentaba provider, límite aplicado después de cargar el diff, rutas Windows malformadas, intentos no persistidos y ejecución de filtros externos. Se corrigieron y se añadieron regresiones; la revisión final no encontró defectos nuevos. Esa revisión fue estática y no sustituye pruebas de proveedor.

Se conserva `AgentRuntime` como frontera de ejecución. Los artefactos del reviewer siguen en metadata y separados de aceptación canónica. Solo el adaptador concreto Codex/Gemini podría producir un manifiesto observado; el fake, subclases de fixture y adaptadores custom quedan fuera. No se afirma que los directorios sean un sandbox del sistema operativo.

## `NOT_RUN`, `UNVERIFIED` y trabajo P1 pendiente

- Codex real, Gemini real, modo `both`, credenciales, coste y E2E: **NOT_RUN**. No se inició ningún proceso de proveedor durante estas pruebas.
- Independencia real del reviewer, identidad de cuenta, aislamiento efectivo y sandbox del proveedor: **UNVERIFIED**. Una sesión distinta no demuestra independencia organizativa ni aislamiento del sistema.
- Scheduler DAG y semáforos centrales, durable recovery/restart e idempotencia, retry acotado, detección/decisión de ownership y conflicto, integración determinista de candidatos, rechecks sobre el candidato integrado, fix/review loops y decisión humana: **BLOCKED / PENDIENTE EN P1**.
- Resultado científico, numérico o matemático: **NOT_RUN**. Estas pruebas acreditan contratos de software y evidencia del runner; no certifican conclusiones científicas.
- **P2 no iniciada:** su gate es posterior al de P1 y el coordinador aún carece de integración final verificada, corrección iterativa, recuperación/scheduler y E2E opt-in con proveedores.

**Estado de entrega:** incremento comprometido en `codex/p1-independent-review-loop`; proponer como PR draft separado hacia `codex/p1-coordinator-evidence`. Sin merge a `main`, tag o release.
