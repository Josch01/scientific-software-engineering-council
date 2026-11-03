# P1.2 — Etapa de revisión de candidatos por worker

**Resultado:** implementado como etapa experimental; P1 no está cerrado.  
**Base:** `efb3087831d11de2bd8e9654636eb53ec75b6261` (`codex/p1-coordinator-evidence`).  
**Commits del incremento:** `9a3d72f` (`feat: add evidence-bound worker review stage`), `1212c2c` (`fix: normalize candidate roots on Windows`) y `d73c2ab` (`fix: reject Windows junction path aliases`).
**Fecha de verificación:** 2026-11-02.  
**Plataformas:** Windows 11 Pro, Python 3.14.0; Docker Linux, `python:3.14.0-bookworm`, image `sha256:ec171bc30122c014f83f7756fe21c4ab26d33e7c4610a63a18da2728f9ed33f8`.

## Qué implementa y por qué

El coordinador ahora invoca reviewers después de que todos los workers pasan sus checks deterministas. Para cada candidato crea una copia separada, enlaza el review al task, worker, tree hash, diff, manifiesto de checks y salida del runtime, y valida un reporte JSON estricto. Los diffs se capturan con límite de 1 MiB y sin filtros de texto externos. Los artefactos incompletos se registran como intentos fallidos; si falla el guardado del manifiesto, el intento no queda en estado exitoso.

La etapa comprueba la transición `checks → review por snapshot`, conserva evidencia y evita tratar fixtures como llamadas reales a proveedores. No integra los árboles de varios workers, no corre un fix loop y no cambia la decisión de release.

## Pruebas ejecutadas

Para las filas Docker, el comando se ejecutó en `python:3.14.0-bookworm` mediante `docker run --rm --pull=never --mount "type=bind,source=C:\Users\artur\Documents\Skill\ssec-worktrees\p1-independent-review-loop,target=/workspace/scientific-software-engineering-council" --workdir /workspace/scientific-software-engineering-council`; el comando de la tabla va como argumento de imagen.

| Entorno | Comando | Resultado | Salida guardada |
|---|---|---:|---|
| Docker Linux, Python 3.14.0 | `python -m unittest discover -v -s tests` | exit 0; **207 tests, 4 skips esperados, 0 fallos** | [log](p1-independent-review-stage-2026-11-02-release-candidate-docker-unittest.log), SHA-256 `C418DE4CEA9C0875FE74240DC3B948F31B25B3FC3545676F82C6E2D998452D35` |
| Windows 11, Python 3.14.0 | `python -m unittest -v tests.test_check_runner tests.test_development_worktrees` | exit 0; **60 tests OK** | [log](p1-independent-review-stage-2026-11-02-release-candidate-windows-focused.log), SHA-256 `64DF5E77262B5C45BFE8FCAB6CD9AE5FAFFC355204B9A1DE434396856D178034` |
| Windows 11, Python 3.14.0 | `python -m unittest -v tests.test_check_runner` | exit 0; **19 tests OK**, incluyendo las tres regresiones de junction | [log](p1-independent-review-stage-2026-11-02-release-candidate-windows-check-runner.log), SHA-256 `BBAC08968D07AEC93D8AA8C38487A95DC3BED359D4322A5B0856D438CE09A6AE` |
| Windows 11, Python 3.14.0 | `python -m compileall -q scripts tests` | exit 0 | Sin salida |
| Windows 11, Git | `git diff --check` | exit 0 | Sin salida |
| Windows 11, Python 3.14.0 | `scripts.validate_skill.validate()` desde una copia temporal con el nombre canónico `scientific-software-engineering-council` | exit 0; `VALID STRUCTURE` | [log](p1-independent-review-stage-2026-11-02-final-validator.log), SHA-256 `042B7FB13C3FE11543BCE9F3D0C0406C062B451E141FDA20566D5A66AE2EAD1E` |

Los cuatro skips del full suite Docker son pruebas exclusivas de Windows (tres junctions y una ruta corta 8.3); las pruebas equivalentes se ejecutaron y pasaron en Windows local.

El contenedor se montó en `/workspace/scientific-software-engineering-council`, nombre canónico que requiere el validador del frontmatter. La invocación local directa `python scripts/validate_skill.py` falla porque este worktree se llama `p1-independent-review-loop`; el validador compara el nombre del directorio con el frontmatter. Se verificó el contenido actual en una copia temporal con el nombre canónico y pasó. No se alteró el frontmatter para ocultar la diferencia.

La suite completa de Windows local: `NOT_RUN`; la matriz de GitHub Actions para el commit `d73c2ab` está pendiente de repetición. Los dos módulos Windows ejecutados cubren snapshots, checks, manifests y ejecución coordinada. No se ejecutaron Codex/Gemini reales.

## Defectos detectados y correcciones

- La revisión estática encontró que un `git diff` podía ejecutar filtros `textconv` configurados en el repositorio. Se añadió `--no-textconv` y una regresión que detecta ejecución de un filtro externo.
- La revisión detectó que un intento podía conservar `REVIEW_REPORT_VALID` si después fallaba el manifiesto. La persistencia ahora rebaja el intento a `FAILED` y hay regresión de fallo de almacenamiento. También se prueba que el fallo al guardar el intento impide guardar el manifiesto.
- En Docker Linux, el escaneo de `/proc/<pid>/stat` podía lanzar `ProcessLookupError` si el proceso desaparecía entre la enumeración y lectura. Se trata como una entrada de `/proc` racy; otros errores continúan cerrando la ejecución.
- CI Windows Server 2025/Python 3.12 en el commit `6b11440120769da17781b9aa4714e9172b060b19` falló con **1 failure + 14 errors**: `Path.resolve()` normalizaba el perfil `C:\Users\RUNNER~1` a `C:\Users\runneradmin`, pero `_lstat_candidate()` comparaba esa ruta con una raíz léxica sin normalizar. Las 14 trazas salían de hashes de snapshots de checks/reviews; la aserción del snapshot comparaba también objetos Path con alias distintos. Evidencia: [Actions run 41576208698, job Windows/Python 3.12](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41576208698/job/125720178850).
- Se añadió una regresión con raíz léxica equivalente que falló antes del fix (`candidate path escapes repository root`) y pasó después. Ahora ambos lados de la prueba de contención se resuelven antes de comparar; la aserción de snapshot compara rutas resueltas.
- CI Windows, commit `1a91cf0`, volvió a fallar: 13 errores por comparar el nombre corto `C:\Users\RUNNER~1` con la ruta resuelta `C:\Users\runneradmin` en `_relative_metadata_path` y `_walk_snapshot`. Se añadieron regresiones para ambos casos; normalizar la raíz antes de comparar resolvió las pruebas locales.
- Una revisión estática detectó que un junction Windows en la raíz del snapshot podía redirigir el recorrido fuera de la raíz. Después se detectó el mismo bypass cuando el junction estaba en un componente padre, incluso en el directorio de destino de `capture_snapshot`. Las tres pruebas nuevas dieron `RED` antes del arreglo y pasan en Windows. `_walk_snapshot`, `_ensure_no_symlink_path` y `_resolve_evidence_path` ahora rechazan symlinks y puntos de reanálisis en todos los componentes antes de resolver la ruta, además de comprobar contención canónica.
- En el árbol actual, Docker/Linux pasó **207 tests con 4 skips esperados**, y Windows local pasó **60/60 pruebas focalizadas**. La revisión estática final no encontró bypass deterministas restantes. La sustitución concurrente de un componente después de inspeccionarlo continúa siendo una carrera TOCTOU general; este control no constituye sandbox del sistema operativo. La matriz CI Python 3.11/3.12 en Windows/Linux para `d73c2ab` sigue pendiente.

## Revisión y decisiones arquitectónicas

Una revisión independiente del diff informó los casos `exit 0` con review incompleta, runtime fixture que aparentaba provider, límite aplicado después de cargar el diff, rutas Windows malformadas, intentos no persistidos y ejecución de filtros externos. La revisión final separada analizó las rutas por junction/reparse points y no encontró bypass deterministas restantes. La revisión fue estática y no sustituye pruebas de proveedor.

Se conserva `AgentRuntime` como frontera de ejecución. Los artefactos del reviewer siguen en metadata y separados de aceptación canónica. Solo el adaptador concreto Codex/Gemini podría producir un manifiesto observado; el fake, subclases de fixture y adaptadores custom quedan fuera. No se afirma que los directorios sean un sandbox del sistema operativo.

## `NOT_RUN`, `UNVERIFIED` y trabajo P1 pendiente

- Codex real, Gemini real, modo `both`, credenciales, coste y E2E: **NOT_RUN**. No se inició ningún proceso de proveedor durante estas pruebas.
- Independencia real del reviewer, identidad de cuenta, aislamiento efectivo y sandbox del proveedor: **UNVERIFIED**. Una sesión distinta no demuestra independencia organizativa ni aislamiento del sistema.
- Scheduler DAG y semáforos centrales, durable recovery/restart e idempotencia, retry acotado, detección/decisión de ownership y conflicto, integración determinista de candidatos, rechecks sobre el candidato integrado, fix/review loops y decisión humana: **BLOCKED / PENDIENTE EN P1**.
- Resultado científico, numérico o matemático: **NOT_RUN**. Estas pruebas acreditan contratos de software y evidencia del runner; no certifican conclusiones científicas.
- **P2 no iniciada:** su gate es posterior al de P1 y el coordinador aún carece de integración final verificada, corrección iterativa, recuperación/scheduler y E2E opt-in con proveedores.

**Estado de entrega:** incremento comprometido en `codex/p1-independent-review-loop`; proponer como PR draft separado hacia `codex/p1-coordinator-evidence`. Sin merge a `main`, tag o release.
