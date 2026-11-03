# P1.2 — Etapa de revisión de candidatos por worker

**Resultado:** implementado como etapa experimental; P1 no está cerrado.  
**Base:** `efb3087831d11de2bd8e9654636eb53ec75b6261` (`codex/p1-coordinator-evidence`).  
**Commits del incremento:** `9a3d72f` (`feat: add evidence-bound worker review stage`) y `1212c2c` (`fix: normalize candidate roots on Windows`).
**Fecha de verificación:** 2026-11-02.  
**Plataformas:** Windows 11 Pro, Python 3.14.0; Docker Linux, `python:3.14.0-bookworm`, image `sha256:ec171bc30122c014f83f7756fe21c4ab26d33e7c4610a63a18da2728f9ed33f8`.

## Qué implementa y por qué

El coordinador ahora invoca reviewers después de que todos los workers pasan sus checks deterministas. Para cada candidato crea una copia separada, enlaza el review al task, worker, tree hash, diff, manifiesto de checks y salida del runtime, y valida un reporte JSON estricto. Los diffs se capturan con límite de 1 MiB y sin filtros de texto externos. Los artefactos incompletos se registran como intentos fallidos; si falla el guardado del manifiesto, el intento no queda en estado exitoso.

La etapa comprueba la transición `checks → review por snapshot`, conserva evidencia y evita tratar fixtures como llamadas reales a proveedores. No integra los árboles de varios workers, no corre un fix loop y no cambia la decisión de release.

## Pruebas ejecutadas

Para las filas Docker, el comando se ejecutó en `python:3.14.0-bookworm` mediante `docker run --rm --pull=never --mount "type=bind,source=C:\Users\artur\Documents\Skill\ssec-worktrees\p1-independent-review-loop,target=/workspace/scientific-software-engineering-council" --workdir /workspace/scientific-software-engineering-council`; el comando de la tabla va como argumento de imagen.

| Entorno | Comando | Resultado | Salida guardada |
|---|---|---:|---|
| Docker Linux, Python 3.14.0 | `python -m unittest discover -v -s tests` | exit 0; **202 tests OK** | [log](p1-independent-review-stage-2026-11-02-postfix-docker-unittest.log), SHA-256 `9D63CD57C88BDFDF719021FAE91E052BD6774290CF2F22A3716921BC5A8870A2` |
| Docker Linux, Python 3.14.0 | `python -m unittest tests.test_execution_evidence tests.test_check_runner tests.test_development_worktrees tests.test_review_evidence tests.test_reviewer_output tests.test_provider_runtimes` | exit 0; **154 tests OK** | [log](p1-independent-review-stage-2026-11-02-postfix-docker-focused.log), SHA-256 `92A952183ED73812145B7BFD5F1B9D1AAC2C6932CD7C7A8DFE1EE5F5F31CA756` |
| Windows 11, Python 3.14.0 | `python -m unittest tests.test_execution_evidence tests.test_check_runner tests.test_review_evidence` | exit 0; **62 passed, 1 skipped** (63 total; symlink privilege not available) | [log](p1-independent-review-stage-2026-11-02-postfix-windows-focused.log), SHA-256 `803A49602815806725551DBC60B052114217003C656E4EE05CECCC384BDA399C` |
| Docker Linux, Python 3.14.0 | `python scripts/validate_skill.py` | exit 0; `VALID STRUCTURE` | [log](p1-independent-review-stage-2026-11-02-postfix-docker-validator.log), SHA-256 `5FFC92F13CB27C289CBB1FA8CB77897EC203C0254B8CA6F89D805254C208A37E` |
| Docker Linux, Python 3.14.0 | `python -m compileall -q scripts tests` | exit 0 | Sin salida |
| Windows 11, Git | `git diff --check` | exit 0 | Sin salida |

El contenedor se montó en `/workspace/scientific-software-engineering-council`, nombre canónico que requiere el validador del frontmatter. Una corrida anterior montada como `/workspace/ssec` falló solo por ese nombre de montaje; al usar la ruta canónica, el test estructural y el validador pasaron. No se alteró el frontmatter para ocultar la diferencia.

La suite completa de Windows local tras el fix: `NOT_RUN`; la matriz de GitHub Actions para el nuevo commit `1212c2c` está pendiente de repetición. El grupo Windows focalizado cubre evidencia, snapshots, checks y manifests afectados. La prueba con privilegios de symlink fue `SKIPPED` en Windows local.

## Defectos detectados y correcciones

- La revisión estática encontró que un `git diff` podía ejecutar filtros `textconv` configurados en el repositorio. Se añadió `--no-textconv` y una regresión que detecta ejecución de un filtro externo.
- La revisión detectó que un intento podía conservar `REVIEW_REPORT_VALID` si después fallaba el manifiesto. La persistencia ahora rebaja el intento a `FAILED` y hay regresión de fallo de almacenamiento. También se prueba que el fallo al guardar el intento impide guardar el manifiesto.
- En Docker Linux, el escaneo de `/proc/<pid>/stat` podía lanzar `ProcessLookupError` si el proceso desaparecía entre la enumeración y lectura. Se trata como una entrada de `/proc` racy; otros errores continúan cerrando la ejecución.
- CI Windows Server 2025/Python 3.12 en el commit `6b11440120769da17781b9aa4714e9172b060b19` falló con **1 failure + 14 errors**: `Path.resolve()` normalizaba el perfil `C:\Users\RUNNER~1` a `C:\Users\runneradmin`, pero `_lstat_candidate()` comparaba esa ruta con una raíz léxica sin normalizar. Las 14 trazas salían de hashes de snapshots de checks/reviews; la aserción del snapshot comparaba también objetos Path con alias distintos. Evidencia: [Actions run 41576208698, job Windows/Python 3.12](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41576208698/job/125720178850).
- Se añadió una regresión con raíz léxica equivalente que falló antes del fix (`candidate path escapes repository root`) y pasó después. Ahora ambos lados de la prueba de contención se resuelven antes de comparar; la aserción de snapshot compara rutas resueltas.
- Sobre el árbol del commit `1212c2c`, Docker/Linux pasó **202/202**, Docker review/runtime enfocado **154/154**, Windows local enfocado pasó **62/63** y omitió un test por privilegio symlink. La matriz CI que valida Python 3.11/3.12 en Windows/Linux para el nuevo commit queda pendiente; por tanto la suite CI multiplataforma aún no se marca como verde.

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
