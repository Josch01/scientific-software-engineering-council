# P3.19 — análisis SIR con tasa perfilada

## Resultado

P3.19 extiende `analyze_sir_parameters` para ajustar ordenadas de nudos seleccionadas en perfiles lineales `beta(t)`/`gamma(t)`. Conserva el contrato SIR v1 y reutiliza RK4, ajuste acotado, diferencias finitas centrales, sensibilidad y residuales existentes. La integración de observaciones se segmenta en los tiempos de nudo; los parámetros no seleccionados permanecen declarados en el modelo.

El builder agrega el escenario reproducible `profiled`. La fuente sintética usa `beta(0)=0.3`, `beta(5)=0.45`, `beta(10)=0.3` y `gamma=0.1`; el workspace de ajuste declara un valor inicial `beta(5)=0.3` y ajusta `beta_knot_1` y `gamma` desde observaciones diarias generadas por `solve_sir_model`. La procedencia de los datos contiene el perfil fuente. La integración en el Centro de Control abre el mismo workspace verificado en la página Resultados y conserva la raíz compartida con el supervisor de agentes.

El [demo perfilado](../../examples/sir_profiled_analysis_workspace_demo/workspace.json) se puede regenerar y abrir así:

```powershell
python scripts/build_sir_analysis_demo.py --output-dir examples/sir_profiled_analysis_workspace_demo --scenario profiled
python scripts/scientific_control_center_qt.py --project-root examples/sir_profiled_analysis_workspace_demo --manifest workspace.json
```

Capturas PySide6 del Centro de Control con fallback Qt nativo: [ajuste y residuales](assets/p3-19-profiled-control-center.png) y [sensibilidad local y residuales](assets/p3-19-profiled-control-center-sensitivity.png).

## Resultado calculado

- Ajuste sintético: `CONVERGED`; `beta_knot_1=0.44999999999264595 1/day`, `gamma=0.09999999999712308 1/day`; coste `1.0295996350836065e-18`, 33 residuales.
- La evaluación de observaciones referencia exactamente los parámetros finales del ajuste; el máximo residuo absoluto es aproximadamente `6.48e-10` para esta fixture.
- La vista muestra parámetros/cotas/unidades, métricas del ajuste, sensibilidad local, residuales y procedencia con SHA-256. La sensibilidad usa el contrato de diferencias finitas centrales existente.
- `scientific_validity=NOT_ASSESSED`, `identifiability=NOT_ASSESSED`, `uncertainty=NOT_CALCULATED`; la fixture no es evidencia empírica ni una afirmación de identificabilidad.

## Commits

- `38cf936` — plan y contrato de P3.19.
- `ad994aa` — ajuste explícito de parámetros en nudos de perfiles SIR.
- `709d239` — builder perfilado, workspace reproducible, unidades y prueba dentro del Centro de Control.
- Commit de este informe y matriz: se completará al cerrar la documentación.

Rama: `codex/p3-19-sir-profile-analysis`, apilada sobre `codex/p4-release-governance` (P4.5). No se hizo merge a `main` ni release. Estado de PR/CI: pendiente de publicación/consulta.

## Verificación ejecutada

Entorno local: Windows 11, Python 3.14.0, PySide6 6.11.1.

- Regresión dirigida: `python -m unittest -q tests.test_scientific_core tests.test_scientific_observations tests.test_scientific_sir_analysis_demo tests.test_scientific_workspace_science_views tests.test_scientific_workspace_qt_views tests.test_scientific_control_center_qt` — **94 pruebas OK**.
- Prueba adicional del puente integrado: `python -m unittest -q tests.test_scientific_control_center_qt tests.test_scientific_workspace_qt_e2e` — **20/20 OK**. La nueva regresión carga el SIR perfilado, abre Resultados, navega a Auditorías, selecciona el recurso verificado `model`, confirma el envío y comprueba que el servicio local de fixture recibe el mismo root/workspace/recurso y que el shell presenta `PROCESSES_COMPLETED_NOT_AUDITED`, `NOT_APPROVED` y `NOT_CERTIFIED`.
- `python scripts/validate_skill.py` — `VALID STRUCTURE`; el validador declara que esto no garantiza corrección de software ni científica.
- `python -m compileall -q scripts tests` — exit 0.
- `git diff --check` — exit 0; Git emitió únicamente una advertencia de conversión CRLF para este plan Markdown.
- Los escenarios `constant` y `profiled` se generaron mediante el CLI. Las pruebas comparan dos generaciones perfiladas byte a byte y cargan el demo versionado con el loader que comprueba digests.
- Pruebas Qt: fallback nativo verificado para `fit_summary`, `sensitivity_plot` y el Centro de Control integrado. No se invocó una CLI de proveedor, no se ejecutó una auditoría de agentes y no se llamó a un modelo.
- El test de handoff usa un servicio de auditoría de fixture para verificar la conexión UI→workspace; no cuenta como ejecución de especialistas ni proveedor real. Los otros 94 tests no se repitieron en esa última corrida.
- Revisión independiente de código: no encontró defectos críticos ni importantes reproducibles. Recomendó hacer explícito el perfil que genera los datos sintéticos; la procedencia del fixture ahora lo declara.

## Decisiones y limitaciones

- La selección de nudos es una configuración explícita de ejecución, no un cambio al contrato SIR v1. Los nombres canónicos son `beta_knot_<índice>` y `gamma_knot_<índice>`; la unidad proviene únicamente del `model_spec` validado enlazado al componente.
- Se mantiene la restricción existente de que los nudos internos deben coincidir con la malla RK4 del análisis. Los nudos se mantienen fijos durante el ajuste; solo varían las ordenadas seleccionadas.
- `evaluate_observations` limita su lista genérica de puntos de corte a 128. Por ello, modelos con más de 128 nudos internos distintos combinados entre beta y gamma no entran en este incremento, aunque cada perfil individual acepte hasta 128 puntos. Este límite no afecta el demo.
- El builder normaliza a LF el código fuente embebido y `.gitattributes` conserva bytes exactos de los recursos del demo en checkout. Esto permite que los digests no cambien por conversiones de fin de línea Windows.
- La captura de esta entrega usa Qt nativo; las pruebas anteriores del frontend verifican WebEngine local para los renderizadores genéricos. WebEngine para este workspace perfilado, GUI Linux y CI de esta rama quedan `NOT_RUN` hasta su ejecución remota.
- El botón de ejecución de simulación requiere confirmación humana. Esta captura no lo activa ni solicita una auditoría.
- El SIR particular del usuario, sus datos, unidades y ecuaciones siguen `NOT_RUN` porque aún no se han proporcionado. Sin esos insumos no se evalúan ajuste empírico, validez matemática, identificabilidad práctica ni incertidumbre estadística.

## Defectos encontrados y requisitos pendientes

- No se encontró un defecto crítico o importante reproducible en las vistas existentes. La brecha de este incremento era que el puente de ajuste rechazaba los perfiles variables y las vistas no asignaban unidades a parámetros de nudo; ambas capacidades quedaron implementadas y probadas.
- `NOT_RUN`: ecuaciones/datos reales del usuario, Qt visual en Linux, proveedor real desde la aplicación, render WebEngine del workspace perfilado y CI del nuevo test de handoff hasta terminar la corrida en la rama publicada.
- `NOT_CALCULATED`: incertidumbre estadística. `NOT_ASSESSED`: validez científica e identificabilidad. No se fabricaron bandas ni intervalos.
- Próximo trabajo del roadmap: aplicar el flujo integrado al proyecto SIR del usuario cuando comparta sus ecuaciones/datos; mantener P3 dinámico y la skill portable utilizables sin exigir GUI. P4/v1.0 continúa pendiente de sus gates.
