# Generar un workspace de análisis SIR

El constructor puede consumir recursos `model_spec`, `observations` y `generic` declarados en un manifiesto SSEC. El loader verifica contención, tamaño y coincidencia de SHA-256 con el manifiesto antes de leerlos; ese digest no autentica quién declaró la procedencia. El constructor valida el contrato SIR v1, las observaciones y la configuración de ajuste. El directorio de salida debe ser nuevo o estar vacío, y debe quedar fuera del proyecto fuente.

Desde la raíz del repositorio, ejecuta el ejemplo sintético:

```powershell
python scripts/build_sir_analysis_demo.py `
  --source-root examples/sir_analysis_input_demo `
  --source-manifest workspace.json `
  --output-dir sir-analysis-output
python scripts/scientific_control_center_qt.py `
  --project-root sir-analysis-output `
  --manifest workspace.json
```

La entrada de ejemplo está en [sir_analysis_input_demo](../../examples/sir_analysis_input_demo/workspace.json). `config/sir-analysis.json` usa este esquema cerrado:

```json
{
  "schema_version": 1,
  "initial_parameters": {"beta_knot_1": 0.3, "gamma": 0.08},
  "bounds": {"beta_knot_1": [0.05, 0.8], "gamma": [0.02, 0.4]},
  "perturbations": {"beta_knot_1": 0.001, "gamma": 0.001},
  "fit_knots": {"beta": [1]},
  "max_iterations": 100,
  "max_function_evaluations": 500
}
```

`fit_knots` puede ser `null` para las tasas constantes. Los nombres, cotas, unidades y compatibilidad con el modelo los valida el motor científico existente. El resultado contiene simulación, ajuste, sensibilidad local, residuales, configuración y digests de las entradas, del builder y de `scientific_core.py`; también registra la versión de Python. `analysis_execution=COMPUTED_FROM_DECLARED_INPUTS` indica que el cálculo se realizó; no certifica la autenticidad de los datos ni validez científica, identificabilidad o incertidumbre estadística. Este ejemplo declara `SYNTHETIC_FIXTURE`; el SIR y los datos particulares del usuario siguen `NOT_RUN` en esta validación.

No se importa ni ejecuta código del proyecto fuente. La ventana puede mostrar los resultados del workspace; el builder no invoca proveedores ni cambia el proyecto fuente.
