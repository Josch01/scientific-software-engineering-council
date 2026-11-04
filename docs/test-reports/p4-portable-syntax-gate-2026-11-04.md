# P4.1 — Check sintáctico portable

**Estado:** `EXPERIMENTAL`. El workflow valida el parseo/compilación de todos los módulos Python en su matriz existente. No se añadieron dependencias.

## Cambio

`validate.yml` ejecuta `python -m compileall -q scripts tests` antes de unittest en Windows/Ubuntu y Python 3.11/3.12. Esto detecta errores sintácticos incluso en archivos que los tests no importen.

## Evidencia

- Windows, Python 3.14.0: `python -m compileall -q scripts tests` — **PASS**, exit code 0.
- P3.18, Windows/Python 3.14.0: integración focalizada de workspace/control center — **32 pruebas OK** en el commit base `e1a3490`.
- `python scripts/validate_skill.py` pasó desde el checkout canónico; desde el directorio de worktree `p4-compileall-gate` falla porque compara el nombre del directorio con el `name` del frontmatter. CI hace checkout con el slug canónico del repo. Se registra como limitación del validador local de worktrees, fuera del alcance de este cambio.
- Nueva ejecución completa `python -m unittest discover -s tests -q`: se interrumpió manualmente tras más de cinco minutos sin resultado terminal; **`NOT_RUN`**. No se obtuvo un fallo ni un resultado completo. Log temporal: `%TEMP%\ssec-p3-18-full-unittest.log`.
- CI PR [#43 / run 41805070338](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41805070338): **4/4 jobs success**, Windows/Ubuntu × Python 3.11/3.12. El paso `Compile Python sources and tests` y la suite determinista pasaron en cada job.
- `ruff`, `mypy`/`pyright`, escáner de secretos, auditoría de vulnerabilidades y Hypothesis: no están instalados; no se instalaron paquetes.

## Límites

`compileall` solo prueba que el código puede compilar con la versión de Python ejecutada. No comprueba estilo, tipos, seguridad, dependencias, compatibilidad de ejecución, corrección científica ni comportamiento de GUI. Esos gates permanecen `PLANNED`/`NOT_RUN` hasta seleccionar herramientas y autorizar cualquier dependencia externa.
