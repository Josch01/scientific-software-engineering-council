# P3.7 — contrato declarativo SIR y simulación aprobada

**Estado:** `EXPERIMENTAL`. El contrato SIR cerrado puede cargar desde un workspace verificado y ejecutarse con confirmación humana mediante RK4 existente. La demo y workspace incluidos son fixtures sintéticos; el modelo SIR concreto del usuario sigue `NOT_RUN`.

## Entrega

- Schema JSON v1 para `sir_frequency_dependent_v1`; estados `S, I, R`, condiciones iniciales, intervalo, etiquetas de unidades, parámetros `beta`/`gamma` e integración `RK4_FIXED_STEP`.
- Coeficientes declarativos `constant` y `piecewise_linear`. Las funciones por tramos deben cubrir el intervalo y sus nudos alinearse con la malla RK4.
- Fórmulas aceptadas por igualdad exacta; no se usa `eval`, `exec`, parser de expresiones ni importación de código del proyecto.
- Adaptador a `OdeProblem`/`solve_rk4`; rechaza compartimentos negativos y deriva poblacional sobre `max(1e-12, N*1e-9)`, sin recortar o proyectar la trayectoria.
- El botón built-in se habilita solo si existe un `model_spec` válido único. La ejecución requiere confirmación; digest, estado matemático y fallo permanecen vinculados a la salida o al error visible.
- Contrato, resultado y manifest de ejemplo en `examples/`; el manifest puede abrirse con la app desde la raíz `examples`.

## Verificación ejecutada

| Entorno | Comando/actividad | Resultado |
|---|---|---|
| Windows, Python 3.14.0 | `python -m unittest discover -s tests -p 'test_scientific*.py' -q` | PASS: 127 tests, 1 omitido |
| Windows, Tkinter real oculto | Abrir `sir_scientific_workspace.json`; rechazo y aprobación; revisar pestaña y hash de archivos | PASS: rechazo = 0 ejecuciones; aprobación = 1; pestaña resultado; archivos intactos |
| Windows, Tkinter real oculto | Workspace con `model_spec` JSON inválido | PASS: error de contrato visible; botón ausente |
| Docker/Linux, Python 3.14.0 | `python -m unittest discover -s tests -v` | PASS: 438 tests, 6 omitidos. Log en [`p3-sir-declarative-ode-2026-11-03-docker-full.log`](p3-sir-declarative-ode-2026-11-03-docker-full.log) |
| Docker/Linux, Python 3.14.0 | `python scripts/validate_skill.py` | PASS: `VALID STRUCTURE` |
| Docker/Linux, Python 3.14.0 | `python scripts/scientific_workspace_app.py --check --project-root examples sir_scientific_workspace.json` | PASS: `VIEW_PREPARED`, 2 componentes, 0 errores |
| Windows, Python 3.14.0 | `python examples/run_sir_model_demo.py` | PASS: `SIMULATED_FIXTURE`, 100 pasos, `scientific_validity=NOT_ASSESSED`, hash del modelo `a131a2b9e2e06544ef165419be769eb025f74529941171c1711b2f0803a38cef` |
| Windows, Python 3.14.0 | `py_compile` de módulos/tests modificados y `git diff --check` | PASS |
| Revisión independiente | Contrato, solver y enlace al workspace; alcance estático acotado | PASS: sin hallazgos críticos/importantes reproducibles; revisión no ejecutó Tk visible |
| GitHub Actions de P3.7 | Requiere push/PR | `NOT_RUN` |

## Limitaciones y riesgos

- El usuario aún no ha proporcionado ecuaciones exactas, parámetros, unidades, condiciones iniciales ni datos. Su SIR, residuales, ajuste, sensibilidad, identificabilidad, auditoría científica y validez siguen `NOT_RUN`.
- `beta` y `gamma` no negativas, población constante y las fórmulas de frecuencia dependiente son supuestos de este contrato específico. No hay conversión de unidades ni análisis dimensional general; las unidades son etiquetas con una comprobación de tasa `1/<tiempo>`.
- RK4 es fijo y no estima error local ni detecta rigidez. Una trayectoria que viole positividad o conservación se rechaza; el contrato no garantiza que el paso aceptado sea suficientemente preciso.
- La salida aparece en memoria y no se persiste. Callbacks personalizados suministrados por un host siguen ejecutándose dentro del proceso y no están aislados; el workspace no puede registrar callbacks ni ejecutar Python generado.
- Fit SIR integrado al workspace, incertidumbre, auditoría automatizada, selección de múltiples modelos y espacio configurado directamente por agentes siguen pendientes. CI P3.7 se ejecutará al publicar el PR.

## Entrega Git

Rama `codex/p3-sir-declarative-ode`, basada en `codex/p3-workspace-approved-simulation` (P3.6). Commit/push/PR pendiente; sin merge ni release.
