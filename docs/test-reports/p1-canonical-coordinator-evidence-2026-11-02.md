# P1.1b — Evidencia canónica del coordinador

**Estado:** incremento implementado; P1 y el gate de release permanecen `BLOCKED`.
**Base:** `69da9c05ca3d08cd7bca38c74403407c490d0d29` (`codex/p1-evidence-verification`).
**Commit de código probado:** `85ffc9a28e49b54a65e1e9d5958cf456af2a17f9`.
**Rama:** `codex/p1-coordinator-evidence`.

## Alcance y decisiones

- El coordinador valida specs tipadas y ejecuta checks declarados contra snapshots por worker. `unit_tests` exige Python `-P`/`-I` y una ejecución real de unittest; manifiestos schema v2 incluyen el hash del snapshot completo.
- El gate verifica manifiestos, logs, snapshot y candidate actual. El estado schema v3 rederiva los workers, provider, branch, path, revisores y obligaciones esperados desde el task y `audit_level` guardados.
- Se conserva el gate fail-closed: checks completos solo producen `CHECKS_VERIFIED_AWAITING_REVIEW`; no acreditan revisión, validez científica ni release.
- State schema v2 no se migra. No incluye `audit_level` ni valida el inventario de workers; se requiere reinicialización y, al reutilizar el mismo task ID, revisión/limpieza manual de los worktrees, branches y metadata anteriores. La metadata JSON no autentica una edición coherente por un proceso del mismo usuario.
- Una revisión independiente encontró tres brechas del productor/gate —suplantación del runner unittest, obligaciones de revisión incompletas y drift del snapshot archivado— y una omisión de workers. Las regresiones correspondientes se observaron fallar y pasan tras las correcciones. El reviewer final no encontró hallazgos nuevos de implementación; fue revisión estática y no ejecutó tests.

## Pruebas y comandos

| Entorno | Comando / alcance | Resultado |
|---|---|---|
| Windows 11, Python 3.14.0 | `python -m unittest tests.test_development_worktrees -v` | `31/31` OK. Incluye las regresiones de reviewer-policy y worker omission. |
| Linux amd64, Docker, imagen local `python:3.14.0-bookworm` | Suite completa `python -m unittest discover -s tests -v`, con `--pull=never` y mount de solo lectura en `/opt/scientific-software-engineering-council` | `160/160` OK, exit 0. El comando de la primera ejecución montó en `/workspace` y falló solo `test_valid_structure` porque el validador requiere que el nombre del directorio raíz coincida con el frontmatter; una ejecución de suite bajo carga concurrente reportó una vez `test_gate_rejects_post_run_snapshot_tampering` como `NOT_RUN`. No se reprodujo en test aislado, módulo aislado ni suite completa serial; causa no determinada. |
| Windows 11, Python 3.14.0 | Suite completa desde un worktree cuyo directorio raíz era `scientific-software-engineering-council` | 160 tests: 158 pasaron, 1 skip de plataforma y 2 errores de setup antes de las aserciones: `test_configuration.ConfigTests.test_symlink_refusal` y `test_provider_modes.TestModes.test_symlink`, ambos `WinError 1314` al crear symlinks. No se deshabilitaron ni debilitaron. |
| Windows 11, Python 3.14.0 | `python scripts/validate_skill.py` desde un worktree con nombre canónico | `VALID STRUCTURE`; no implica validez de software o ciencia. El mismo script desde `p1-coordinator-evidence` falla por su comprobación intencional del nombre de raíz. |
| Windows 11, Python 3.14.0 | `--help` de `worktree_coordinator.py`, `development_runner.py`, `prepare_agents.py`, `route_task.py`; `py_compile` de coordinador y test; `git diff --check` | Exit 0. |

Hubo una primera ejecución completa Linux simultánea con la suite Windows que reportó un fallo transitorio en la prueba de snapshot; la suite serial posterior pasó. Se conserva como intermitencia investigada, no se atribuye una causa confirmada. Los resultados crudos de estas últimas suites no se guardaron como archivos separados; este informe registra conteos, entornos, comandos y defectos observados.

La limpieza de la copia temporal Windows después de la suite falló: `git worktree remove` devolvió `Permission denied` luego de retirar su marcador `.git` y desregistrarla. La revisión automática rechazó la limpieza recursiva posterior. Queda la copia local generada en `C:\Users\artur\Documents\Skill\ssec-validation\scientific-software-engineering-council` sin registro Git; esto no modifica la rama ni el repositorio fuente. Una re-ejecución posterior de `validate_skill.py` sobre esa copia incompleta falló por faltar `.github/workflows/validate.yml`; la ejecución válida de `VALID STRUCTURE` se hizo antes del intento de cleanup.

## Defectos, límites y trabajo pendiente

- Windows no pudo verificar las dos rutas de rechazo de symlink por falta del privilegio requerido. Linux sí ejecutó la suite completa, incluidas esas pruebas.
- Provider E2E de Codex/Gemini, credenciales, subagentes nativos y coordinación real `both`: `NOT_RUN`. El runtime Python local/fakes son pruebas de software del coordinador, no provider E2E.
- POSIX host-nativo: `NOT_RUN`; la regresión nativa de `SA_NOCLDWAIT` y el runtime se verificaron dentro de Docker Linux con imagen local.
- GUI visual, IDL/licencia, sandbox efectivo, recuperación durable, scheduler DAG, locks/idempotencia y ciclo real reviewer→fix→review: `NOT_RUN` o `BLOCKED`; siguen siendo trabajo P1.
- Sin certificación científica: no se ejecutaron oráculos científicos ni se validaron modelos. Esta evidencia no prueba validez numérica ni científica.
- Una edición coordinada del mismo `state.json` por el mismo usuario puede cambiar el `audit_level` y las obligaciones de modo coherente; el sistema no ofrece autenticidad criptográfica. La aprobación automática y release permanecen desactivados.
- P2 no inicia hasta cumplir Gate P1, especialmente reviewer separado, scheduler/DAG, recovery, idempotencia, retries, cancelación y conflictos.

**Estado de release:** `PARTIAL`; `evidence_verified: false`; `release_status: NOT_APPROVED`.

## Seguimiento de CI Windows — 2026-11-03

El workflow de PR #11, run `41570073658`, confirmó un defecto de compatibilidad en Windows además de una aserción de prueba dependiente de la forma textual de la ruta. En Windows/Python 3.12 el job terminó con 160 pruebas: una falla, un error y un skip; el job Windows/Python 3.11 fue cancelado después del fallo, mientras Ubuntu 3.11 y 3.12 pasaron.

- `capture_snapshot` rechazaba `.gitignore` como escape al resolver el archivo copiado a una ruta con alias DOS 8.3 y compararla contra `root` aún no resuelto. `_lstat_candidate` ahora resuelve tanto la raíz como el archivo antes de comprobar contención; mantiene la inspección `lstat` de cada componente y el rechazo de symlinks.
- La aserción del snapshot comparaba dos `Path` por representación textual. En CI una ruta usaba `RUNNER~1` y la otra `runneradmin`, aunque designaban el mismo objeto. Se cambió a `os.path.samefile`.
- La regresión del alias se observó fallar antes del cambio y pasar después. En Windows 11 / Python 3.14.0 pasaron los módulos afectados `tests.test_check_runner` y `tests.test_execution_evidence`: `41/41` en `62.577s`; las tres pruebas focalizadas también pasaron.
- El run #84 terminó con los cuatro jobs verdes tras reintentar los jobs cancelados por `fail-fast`: Windows y Ubuntu, Python 3.11 y 3.12. En el primer intento falló una vez `test_real_local_execution_runs_per_worker_checks_and_gate_stays_blocked` en Ubuntu 3.11 (`PARTIAL_OR_FAILED`); Ubuntu 3.12 y ambos jobs Windows se cancelaron. El reintento de Ubuntu 3.11 pasó, y el caso pasó cinco veces seguidas dentro de Docker/Linux local. No se determinó la causa de esa primera falla, por lo que queda registrada como intermitencia sin reproducir, no como defecto corregido por este cambio.
- El comportamiento de proveedor real, el ciclo con CLI autenticada y las limitaciones generales de P1 descritas arriba no cambian.

**Decisión:** mantener ambas rutas resueltas en la verificación de contención evita falsos rechazos por alias sin relajar el gate. No se habilita ninguna aprobación por este cambio.
