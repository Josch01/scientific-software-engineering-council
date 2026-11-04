# P4.3 — Sincronización de guías

**Estado:** `EXPERIMENTAL`. Se actualizaron instalación, arquitectura y contribución para representar el producto actual y sus límites.

## Cambios

- `INSTALLATION.md` distingue skill portable y Centro de Control opcional; documenta descubrimiento oficial de skills, runner de CLI local, confirmación/costo, frontend Qt opcional, pruebas y diagnósticos.
- `references/ARCHITECTURE.md` sustituye un esquema futuro de carpetas por módulos reales y límites de dependencia/confianza del motor, loader y GUI.
- `CONTRIBUTING.md` fija verificación local, evidencia científica, política de dependencias y límites para licencia/merge/release.
- `README.md` corrige afirmaciones antiguas de v0.2 que describían el router como único componente y los agentes como no ejecutables.
- `scripts/validate_skill.py` exige que las guías centrales permanezcan presentes.

## Verificación

- `python scripts/run_agents.py --help` — PASS, salida refleja `--execute` y aceptación explícita del costo no medido.
- `python scripts/scientific_control_center_qt.py --help` — PASS.
- `python scripts/scientific_workspace_qt.py --help` — PASS.
- `python scripts/validate_skill.py` — PASS.
- `python -m unittest tests.test_structure -v` — **1/1 OK**.
- `python -m compileall -q scripts tests` y `git diff --check` — PASS.
- Los CLI de runner, app y workspace Qt mostraron `--help` con exit code 0 en Windows/Python 3.14; no iniciaron procesos de proveedor.
- CI del incremento predecesor P4.1: PR [#43](https://github.com/Josch01/scientific-software-engineering-council/pull/43), run [41805070338](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41805070338), 4/4 jobs Windows/Ubuntu × Python 3.11/3.12 success.
- Las rutas e instrucciones de Codex y Gemini se contrastaron con documentación oficial enlazada en la guía; no se instaló ningún software ni skill.

## Límites

La guía no afirma que proveedores estén instalados/autenticados, no invoca modelos y no promete que todos usen un API de facturación particular. Las instrucciones describen discovery; CLI real, cuota, GUI Qt en Linux, licencia y release mantienen sus estados previos.
