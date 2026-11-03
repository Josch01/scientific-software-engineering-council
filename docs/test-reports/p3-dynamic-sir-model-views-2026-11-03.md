# P3.8 — vistas estructuradas del modelo SIR

**Estado:** `EXPERIMENTAL`. El núcleo visual permanece basado en manifests y renderers registrados. Para el SIR v1, ecuaciones y parámetros ahora tienen vistas científicas estructuradas; las demás familias siguen usando sus renderers o el fallback JSON acotado.

## Entrega

- `equation_view` muestra el conjunto v1, balance poblacional, estados, ecuaciones y unidades declaradas desde un `SirModelDefinition` validado.
- `parameter_table` muestra condiciones iniciales, población inicial, intervalo y configuración RK4, además de valores constantes o cada nudo de perfiles lineales `beta`/`gamma`.
- Manifests de modelos no SIR se conservan como datos JSON inertes; un contrato declarado como SIR que no valida produce un error del componente.
- El workspace reproducible usa el mismo manifest para ecuaciones, parámetros y gráfica; la acción de ejecución continúa tras confirmación humana.
- P3.7 incorporó `eol=lf` para los JSON SIR hasheados. Un worktree limpio de Windows (`core.autocrlf=true`) y Docker/Linux pasan el loader y `VIEW_PREPARED` con los digests declarados.

## Verificación

| Entorno | Comando/actividad | Resultado |
|---|---|---|
| Windows, Python 3.14.0 | `python -m unittest discover -s tests -p 'test_scientific*.py' -q` | PASS: 131 tests, 1 omitido |
| Windows, Tkinter real oculto | Abrir manifest de ejemplo; revisar fórmulas, unidades, tabla de perfiles, condiciones iniciales; declinar y aceptar ejecución | PASS: fórmulas visibles; 4 filas de perfiles; declinar no ejecuta; aceptar muestra pestaña; archivos intactos |
| Windows, Tkinter real oculto | Modelo SIR inválido | PASS: error visible y botón de simulación ausente |
| Worktree limpio de Windows | Prueba de digest del manifest SIR y `--check` | PASS: SHA-256 y `VIEW_PREPARED` |
| Docker/Linux, Python 3.14.0 | `python scripts/scientific_workspace_app.py --check --project-root examples sir_scientific_workspace.json` | PASS: `VIEW_PREPARED`, 3 componentes, 0 errores |
| Docker/Linux, Python 3.14.0 | `python scripts/validate_skill.py` | PASS: `VALID STRUCTURE` |
| Docker/Linux, Python 3.14.0 | Suite completa `python -m unittest discover -s tests -v` | PASS: 442 tests, 6 omitidos. Log en [`p3-dynamic-sir-model-views-2026-11-03-docker-full.log`](p3-dynamic-sir-model-views-2026-11-03-docker-full.log) |
| Windows, Python 3.14.0 | `py_compile` de módulos/tests y `git diff --check` | PASS |
| Revisión independiente | Proyección, renderers y fallback JSON | PASS: un hallazgo P2 de colisión del marker JSON se reprodujo y corrigió con dataclasses internas; el revisor confirmó ambos casos; smoke Tk ejecutado localmente |
| GitHub Actions de P3.8 | PR borrador #30, SHA `61ef7b9` | En curso: runs [41737649443](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41737649443) y [41737623315](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41737623315), matriz Windows/Ubuntu × Python 3.11/3.12 |

## Limitaciones

- Las vistas científicas especializadas admiten únicamente el contrato SIR de ecuación cerrada. SEIR y otros modelos siguen como JSON inerte hasta que exista su contrato versionado y revisión específica.
- Las unidades se muestran como etiquetas, sin conversión. Una vista no establece precisión numérica, identificación, incertidumbre ni validez científica.
- El manifest ya puede seleccionar componentes estructurados; no hay aún un flujo in-app para proponer un manifest desde agentes, revisar su diff y aprobar su persistencia. Ese puente queda como P3.9 planeada.
- Los resultados de simulación no se persisten automáticamente. El SIR del usuario y sus datos siguen `NOT_RUN`.

## Defecto encontrado y corrección

La primera versión utilizaba el campo de datos `view_kind` para seleccionar el renderer SIR. Revisión independiente demostró que un JSON genérico con ese campo podía causar un `KeyError` y detener el montaje del componente. Se reemplazó el marker por los tipos inmutables `SirEquationView` y `SirParameterView`, creados únicamente después de validar `SirModelDefinition`. Las regresiones exigen que ambos markers falsos usen el fallback JSON; pasan la suite y la revisión confirmó el fix.

## Entrega Git

Rama `codex/p3-dynamic-sir-model-views`, commit `61ef7b9`, PR borrador [#30](https://github.com/Josch01/scientific-software-engineering-council/pull/30) apilado sobre PR borrador #29 (`codex/p3-sir-declarative-ode`). CI remota en curso. Sin merge ni release.
