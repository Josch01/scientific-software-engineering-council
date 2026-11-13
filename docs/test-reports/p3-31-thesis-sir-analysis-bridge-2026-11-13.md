# P3.31 — Puente de análisis del SIR armónico de tesis

**Estado:** `EXPERIMENTAL`; rama `codex/p3-31-thesis-sir-analysis-bridge`.

## Resultado

- Se conectó el modelo armónico y su observador semanal exactos a los contratos
  existentes de ajuste acotado, RK4 fijo, sensibilidad local, simulación y
  residuales. Las vistas existentes aceptan ahora el resultado de media por
  intervalo sin representarla como un estado del modelo.
- Solo se ajustan parámetros dinámicos seleccionados: `d0`, `gamma` y los
  coeficientes/frecuencias armónicas declarados. Condiciones iniciales, `q` y
  retardo quedan fijos en sus valores explícitos. La sensibilidad describe
  estados locales del modelo, no identificabilidad.
- La validez científica e identificabilidad quedan `NOT_ASSESSED`; incertidumbre
  `NOT_CALCULATED`. El evaluador conserva el digest de origen cuando existe; un
  hash detecta cambios, no autentica al productor.

## Verificación

- `PASS` — 90 pruebas focalizadas de puente, modelo SIR de tesis, optimizador,
  contratos/vistas de workspace y loader; 1 fixture de symlink omitido por
  limitación del entorno Windows.
- `PASS` — `scripts/validate_skill.py`, `py_compile`, `git diff --check` y demo
  sintética reproducible.
- Demo: recuperó `d0=-0.4500000068` frente a `-0.45`, residuo máximo
  `0.4446` casos. `fit_status=STALLED` por el redondeo de conteos sintéticos;
  no se presenta como convergencia ni validación científica.
- Revisión independiente encontró que el preflight de sensibilidad omitía
  arreglos intermedios. Se alineó con la fórmula del solver y una regresión de
  56 semanas / paso 0.001 rechaza el caso antes de llamar al evaluador.

## Límites y siguiente paso

- Modelo/datos reales de la tesis: `NOT_RUN`; invocación de proveedor: `NOT_RUN`.
- No estima incertidumbre, no verifica error de integración por refinamiento y
  no demuestra identificabilidad ni validez epidemiológica.
- P3.32 conectará este motor con la acción confirmada de Qt y cargará sus
  resultados en el workspace del Centro de Control. No se ejecutará el JSON
  real durante ese desarrollo.
