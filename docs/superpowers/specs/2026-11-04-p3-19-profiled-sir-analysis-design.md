# P3.19 — Análisis SIR con tasas declarativas variables

## Goal

Permitir que el puente de análisis SIR reutilice simulación, ajuste, sensibilidad y residuales existentes cuando `beta(t)` o `gamma(t)` son perfiles piecewise lineales declarados.

## Scope

- Mantener tiempos de nudos fijos; el operador selecciona explícitamente qué ordenadas se ajustan mediante `fit_knots: Mapping[str, Sequence[int]]`.
- Nombrar los parámetros ajustables como `beta_knot_<index>` / `gamma_knot_<index>`; tasas constantes conservan `beta` / `gamma`.
- Mantener las ordenadas no seleccionadas como están en el modelo. Validar índices, unicidad, cotas no negativas, unidades y límites de trabajo.
- Ampliar `evaluate_observations(..., breakpoints=...)` para dividir RK4 en nudos declarados dentro de intervalos de observación irregulares.
- Exigir que todos los nudos pertenezcan a la malla RK4 final de análisis; rechazar una configuración que cruzaría un nudo con un paso.
- Extender el demo sintético para mostrar los valores calculados y resolver unidades de los parámetros de nudo.

## No-goals

- No añadir solvers, algoritmos de optimización, interpolación de observaciones, incertidumbre, identificabilidad ni afirmaciones de validez científica.
- No cambiar el esquema SIR v1 ni evaluar expresiones Python.
- No ejecutar proveedor ni código de agente.

## Acceptance

1. Los perfiles constantes conservan salida/API previas.
2. Un fixture exacto con beta piecewise y gamma constante recupera una ordenada seleccionada mediante el ajuste existente; residuales, sensibilidad y solución corresponden al mismo resultado.
3. El evaluador segmenta en nudos con observaciones que los cruzan; entradas inválidas o mallas no alineadas fallan antes de anunciar resultados.
4. El workspace sintético muestra `beta_knot_<index>` con unidad `1/<time>` y conserva `NOT_ASSESSED` / `NOT_CALCULATED` donde corresponde.
5. El SIR y los datos del usuario permanecen `NOT_RUN`.
