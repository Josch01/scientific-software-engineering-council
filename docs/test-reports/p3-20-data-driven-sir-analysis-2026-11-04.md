# P3.20 — análisis SIR desde recursos de workspace verificados

## Resultado

El CLI ahora construye un workspace de análisis desde `model_spec`, `observations` y una configuración `generic` declarados en un manifiesto. `load_scientific_workspace` comprueba contención, límites y coincidencia de SHA-256 con el manifiesto antes de parsear los recursos. El digest no autentica el origen de los datos. El constructor valida el modelo SIR v1, los datos y la configuración estricta; ejecuta `analyze_sir_parameters`, conserva las entradas y la configuración originales, y guarda simulación, ajuste, sensibilidad, residuales, procedencia y digests del manifiesto, entradas, builder y `scientific_core.py` en un directorio de salida nuevo o vacío.

No se añadió un integrador, optimizador o estimador nuevo. No se importa ni ejecuta código del proyecto fuente. El contrato sigue limitado al SIR declarativo v1 y a los análisis ya implementados.

## Demostración reproducible

```powershell
python scripts/build_sir_analysis_demo.py `
  --source-root examples/sir_analysis_input_demo `
  --source-manifest workspace.json `
  --output-dir sir-analysis-output
python scripts/scientific_control_center_qt.py `
  --project-root sir-analysis-output `
  --manifest workspace.json
```

La prueba CLI realiza esta generación desde el fixture versionado y abre el resultado con el loader. Una prueba Qt adicional carga el workspace recién calculado en el Centro de Control integrado y comprueba que aparecen el ajuste, las unidades, los residuales y la misma raíz de proyecto en el supervisor. La [captura del Centro de Control](assets/p3-19-profiled-control-center.png) documenta el mismo renderer y contrato científico con el fixture perfilado P3.19.

Resultado del fixture: `SYNTHETIC_FIXTURE`; ajuste `CONVERGED`; `beta_knot_1 = 0.44999999999`, `gamma = 0.099999999997`, máximo residual absoluto `6.48e-10`. Estos valores solo verifican la ruta de software para el fixture reproducible.

## Verificación

Entorno local: Windows, Python 3.14.0, PySide6 6.11.1.

- `python -m unittest tests.test_scientific_sir_analysis_demo tests.test_scientific_control_center_qt tests.test_scientific_workspace_science_views tests.test_scientific_workspace_qt_views tests.test_scientific_core tests.test_scientific_observations tests.test_scientific_workspace_loader` — **116 pruebas OK, 1 omitida**. La omisión corresponde a la creación de symlinks no autorizada por este entorno Windows.
- Cobertura específica: reproducibilidad byte a byte, CLI desde el ejemplo sintético, rechazo de configuración inválida, rechazo de digest incorrecto antes de crear salida, protección de los archivos existentes y rechazo de escribir dentro del proyecto fuente.
- Prueba Qt offscreen: carga el workspace calculado y comprueba parámetros/unidades y tabla de residuales en el Centro de Control.
- `python -m compileall -q scripts tests` — exit 0.
- `git diff --check` — exit 0.
- Métricas del fixture verificadas después de volver a cargar todos los recursos con SHA-256; manifiesto `VALID`, 11 recursos.
- Revisión independiente: se corrigió un `data_status` con caracteres de control que podía invalidar el manifiesto y el indicador fijo `real_user_sir=NOT_RUN`, contradictorio con la ejecución sobre entradas declaradas. También se conserva el digest del motor científico y la versión de Python para trazabilidad del cálculo.
- Llamadas a proveedores y datos del SIR del usuario: `NOT_RUN`.

## Decisiones y límites

- La configuración de análisis es un recurso versionado `generic`, con esquema cerrado v1. Declara parámetros iniciales, cotas, perturbaciones, nudos seleccionados y límites de ajuste; el motor existente valida sus compatibilidades matemáticas.
- El resultado copia modelo, observaciones y configuración originales. `analysis-provenance` registra el digest del manifiesto fuente, los SHA-256 de las entradas y el digest de `scientific_core.py`, además de la versión de Python.
- El CLI devuelve `analysis_execution=COMPUTED_FROM_DECLARED_INPUTS`; el estado `NOT_RUN` del SIR particular del usuario solo se afirma para este fixture, que no contiene sus ecuaciones/datos.
- La salida no sustituye ni modifica el workspace fuente y debe escribirse fuera de él. Los archivos se crean en modo exclusivo para evitar sobreescrituras.
- El fixture es enteramente sintético. `scientific_validity=NOT_ASSESSED`, `identifiability=NOT_ASSESSED`, `uncertainty=NOT_CALCULATED` y el SIR particular del usuario `NOT_RUN`.
- La GUI continua siendo opcional; la generación y validación funcionan desde CLI. El builder solo acepta SIR v1 y la configuración de análisis implementada; SEIR u otros modelos, intervalos de incertidumbre validados, proveedor real desde el Centro de Control, WebEngine para esta entrada, GUI Linux y ejecución real de agentes siguen `NOT_RUN`.

## Defectos y estado

La brecha atendida era que el builder solo aceptaba escenarios de demo codificados. P3.20 permite suministrar recursos estructurados y seguros sin crear algoritmos científicos. La entrada de procedencia se conserva como declarada y su autenticidad queda `NOT_ASSESSED`. Los dos defectos importantes encontrados por revisión independiente se corrigieron y tienen pruebas de regresión. No quedan defectos críticos/importantes reproducibles en el alcance verificado.

Commit `3df8ec0` — `feat: build SIR analysis from verified workspace`. PR [#51](https://github.com/Josch01/scientific-software-engineering-council/pull/51) abierto en estado draft contra `codex/p3-19-sir-profile-analysis`; no está mergeado. En la consulta inicial de CI, GitHub aún no devolvía checks para el head `3df8ec0`; la verificación CI queda `PENDING` hasta que aparezcan los jobs. No se hizo merge a `main` ni se publicó una release.

**Siguiente objetivo:** avanzar con los siguientes componentes de P3 del Centro de Control, conservando la aplicación Qt como shell común y la lógica científica independiente del frontend. Aplicar a datos del usuario cuando estén disponibles; no afirmar validez científica o identificabilidad desde esta prueba sintética.
