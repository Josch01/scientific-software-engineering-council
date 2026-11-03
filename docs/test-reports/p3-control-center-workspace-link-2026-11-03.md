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
| Windows, Tkinter real | Smoke oculto: botón → `Toplevel` hijo → selector en el proyecto → carga de manifiesto de fixture y render de sección/recurso; selector cancelable simulado | PASS. Fixture JSON sintético, no SIR ni evidencia científica |
| Windows, Python 3.14 | `test_symlink_refusal` preexistente | `NOT_RUN` en este host: `WinError 1314` al crear symlink; no se alteró el test. Docker/Linux y CI verificarán este caso en su entorno |
| Docker/Linux, Python 3.14.0 | `python scripts/validate_skill.py` | PASS: `VALID STRUCTURE` |
| Docker/Linux, Python 3.14.0 | `python -m unittest discover -s tests -q` | PASS: 401 tests, 6 omitidos, 158.886 s |
| Windows, Python 3.14 | `py_compile` de supervisor/UI/tests y `git diff --check` | PASS |
| GitHub Actions | PR de P3.4 | Pendiente |

Los tests nuevos se observaron fallar antes del código: no existían `_create_window_root`, `_project_root_hint` ni `open_scientific_workspace`. Pasaron después de implementar la fábrica de ventana hija y el enlace diferido.

## Límites pendientes

- El smoke probó widgets Tk reales y un selector controlado; no fue una inspección visual manual ni una sesión con usuario.
- El panel todavía no presenta cola/árbol DAG, estado/progreso por worker, logs filtrados, artefactos/diffs ni Cancel/Retry integrados al viewer. Este incremento solo conecta el panel actual con la vista científica.
- No se solicitó ni hizo una invocación de AGY/Codex/Gemini.
- No hay ecuaciones, unidades, condiciones iniciales ni datos experimentales del SIR; su simulación, ajuste y auditoría siguen `NOT_RUN`.
- El runner aislado para código de agentes sigue pendiente; callbacks requieren aprobación humana y no se ejecutan desde la app.

## Entrega

Rama separada apilada sobre P3.3; PR borrador dirigido a `codex/p3-dynamic-workspace-ui`. No merge ni release.
