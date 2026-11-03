# P3.4 — enlace entre supervisor y workspace científico

**Estado:** experimental. La app científica ya se puede abrir desde el supervisor sin crear un segundo root Tk. El SIR real y el uso de proveedores siguen `NOT_RUN`.

## Cambio

- `config_panel.py` ofrece **Abrir espacio científico** y abre la vista como un `Toplevel` hijo del supervisor.
- La raíz de proyecto seleccionada se usa para iniciar el selector del manifiesto. El loader sigue verificando contención y SHA-256 antes de que la UI reciba bytes.
- La vista continúa opcional y ejecutable por CLI. El import de Tk se mantiene diferido; el modo `--check` sigue headless.
- No se inicia ningún modelo ni se ejecuta código o callback del proyecto.

## Verificación

| Entorno | Actividad | Resultado |
|---|---|---|
| Windows, Python 3.14 | Tests del enlace y renderer | PASS: 11 tests |
| Windows, Python 3.14 | Configuración, excluyendo el fixture de symlink | PASS: 12 tests |
| Windows, Tkinter real | Dos smokes ocultos: botón → `Toplevel` hijo → selector bajo el proyecto existente; y campo de proyecto vacío → selector de raíz → manifiesto de fixture y render de sección/recurso | PASS. Selector controlado y fixture JSON sintético; no SIR ni evidencia científica |
| Windows, Python 3.14 | `test_symlink_refusal` preexistente | `NOT_RUN` en este host: `WinError 1314` al crear symlink; no se alteró el test. Docker/Linux y CI verificarán este caso en su entorno |
| Docker/Linux, Python 3.14.0 | `python scripts/validate_skill.py` | PASS: `VALID STRUCTURE` |
| Docker/Linux, Python 3.14.0 | `python -m unittest discover -s tests -q` (repetido tras el fix de revisión) | PASS: 401 tests, 6 omitidos, 162.408 s |
| Windows, Python 3.14 | `py_compile` de supervisor/UI/tests y `git diff --check` | PASS |
| GitHub Actions | PR de P3.4, con fix de revisión | Pendiente |

Los tests nuevos se observaron fallar antes del código: no existían `_create_window_root`, `_project_root_hint` ni `open_scientific_workspace`. El revisor independiente detectó que una cadena vacía terminaba en el directorio actual; la regresión falló antes del arreglo y pasó al hacer que valores vacíos o solo espacios activen la selección de raíz. La revisión fue estática, no ejecutó pruebas; no se solicitó otra ronda después del fix porque la regresión cubre el caso señalado.

## Límites pendientes

- El smoke probó widgets Tk reales y un selector controlado; no fue una inspección visual manual ni una sesión con usuario.
- El panel todavía no presenta cola/árbol DAG, estado/progreso por worker, logs filtrados, artefactos/diffs ni Cancel/Retry integrados al viewer. Este incremento solo conecta el panel actual con la vista científica.
- No se solicitó ni hizo una invocación de AGY/Codex/Gemini.
- No hay ecuaciones, unidades, condiciones iniciales ni datos experimentales del SIR; su simulación, ajuste y auditoría siguen `NOT_RUN`.
- El runner aislado para código de agentes sigue pendiente; callbacks requieren aprobación humana y no se ejecutan desde la app.

## Entrega

Rama separada apilada sobre P3.3; PR borrador dirigido a `codex/p3-dynamic-workspace-ui`. No merge ni release.
