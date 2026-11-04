# P3.17 — integrar análisis existentes con SIR declarativo

## Entrega

P3.17 conecta el contrato SIR declarativo con los algoritmos existentes de simulación RK4, ajuste acotado, sensibilidad local y evaluación de observaciones/residuales. La vista Qt muestra resultados calculados desde una fixture sintética reproducible y deriva unidades solo de un recurso `model_spec` SIR v1 enlazado y validado.

La demo se abre desde la raíz del repositorio con:

```text
python scripts/scientific_workspace_qt.py --project-root examples/sir_analysis_workspace_demo workspace.json
```

Se regenera con `python scripts/build_sir_analysis_demo.py`. La tabla de observaciones procede de la misma trayectoria sintética que se usa en el ajuste; no representa evidencia empírica. Los resultados son una demostración del flujo de software.

## Commits

- `662a36c` — exponer el SIR constante como `OdeProblem` parametrizado.
- `321863e` — componer ajuste, sensibilidad, simulación y residuales SIR.
- `7e44991` — validar y enlazar recursos de contexto para unidades de las vistas.
- `49ae05c` — agregar builder determinista, workspace calculada y renderizado Qt.
- `3468038` — rechazar contextos de modelo ambiguos en vistas de sensibilidad.

Rama: `codex/p3-17-sir-analysis-integration`. Draft PR [#41](https://github.com/Josch01/scientific-software-engineering-council/pull/41), apilado sobre P3.16 [#40](https://github.com/Josch01/scientific-software-engineering-council/pull/40). GitHub informa `mergeable=true`; no se hizo merge ni release.

## Verificación ejecutada

- `python -m unittest tests.test_scientific_core -v`: **33/33 pruebas OK**.
- `python -m unittest tests.test_scientific_workspace tests.test_scientific_workspace_generation tests.test_scientific_workspace_science_views tests.test_scientific_sir_analysis_demo tests.test_scientific_workspace_qt_views -v`: **54/54 pruebas OK**.
- `python -m unittest tests.test_scientific_workspace_qt_charts tests.test_scientific_workspace_qt tests.test_scientific_workspace_qt_e2e -v`: **16/16 pruebas OK**, incluyendo Qt WebEngine local, fallback nativo y flujo Qt integrado.
- Tras el arreglo de revisión: `python -m unittest -q tests.test_scientific_workspace tests.test_scientific_workspace_generation tests.test_scientific_workspace_science_views tests.test_scientific_sir_analysis_demo tests.test_scientific_workspace_qt_views`: **54/54 pruebas OK**. La reproducción añadió el rechazo de dos modelos en `sensitivity_plot`.
- Builder ejecutado y cargado por el safe loader. Dos construcciones temporales generaron archivos byte por byte idénticos; los SHA-256 coincidieron.
- `WEBENGINE_AVAILABLE`: `True`. Las pruebas verificaron render WebEngine local y fallback Qt nativo.
- `python -m py_compile` para módulos y pruebas modificados: OK.
- `git diff --check`: OK.
- Estado de checks remotos consultado después de publicar PR #41: no hay estados reportados aún.

## Resultado científico de la fixture y límites

- El ajuste exacto sintético reporta `STALLED`, mostrado sin reinterpretación. Estimó `beta=0.29999999719205395` y `gamma=0.09999999727721538` frente a los valores sintéticos `0.3` y `0.1`.
- La sensibilidad reutiliza diferencias centrales; los residuales son crudos, no ponderados, y calculados como simulación menos observación.
- El wrapper acepta ajuste/sensibilidad solo para `beta` y `gamma` constantes, con cotas y endpoints no negativos, unidades temporales compatibles y unidades poblacionales iguales. Los perfiles temporales siguen simulables, pero su ajuste no está implementado.
- Un RHS verificador rechaza compartimentos negativos o deriva de población durante estados intermedios de RK4 en ajuste/sensibilidad. La solución completa final también se valida. No se crean estimadores ni algoritmos científicos nuevos.
- `scientific_validity=NOT_ASSESSED`, `identifiability=NOT_ASSESSED` y `uncertainty=NOT_CALCULATED`; no se generan intervalos ni bandas.
- Las referencias de contexto muestran recursos y hashes verificados; los digests prueban igualdad de bytes con el manifiesto, no que el cálculo usara esos bytes.

## Defectos encontrados y corregidos

- Un render de workspace SIR falló porque el dispatcher Qt enviaba `action_error` al renderer de tabla JSON, cuya firma no lo aceptaba. Se corrigió y se cubrió con render de la tabla de observaciones.
- La demo P3.16 existente contenía cuatro digests que no coincidían con sus recursos; se actualizaron para restaurar su prueba de carga Qt.
- La revisión independiente halló que `sensitivity_plot` aceptaba dos recursos `model_spec`, aunque la vista deriva unidades solo de un modelo. Se reprodujo y corrigió el validador para rechazar esa configuración; la regresión focalizada pasó y el revisor confirmó el arreglo sin otros hallazgos P0–P2.

## Pendiente

- SIR modificado del usuario y datos experimentales: `NOT_RUN` (no proporcionados).
- Qt en Linux: `NOT_RUN` (entorno disponible: Windows).
- Ajuste interactivo desde el botón Qt: fuera de este incremento; el motor de análisis ya es invocable mediante API.
- Integrar supervisor de agentes y workspaces científicos en una aplicación Qt unificada, con navegación por proyectos, agentes, experimentos, auditorías, código y resultados: siguiente incremento P3.18.
- CI remota para PR #41: pendiente/no hay checks reportados al consultar; actualizar cuando GitHub Actions publique resultado.
