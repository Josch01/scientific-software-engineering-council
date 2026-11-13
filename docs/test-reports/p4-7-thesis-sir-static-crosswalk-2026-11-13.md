# P4.7 — Correspondencia estática tesis–adaptador SIR

## Fuentes fijadas

- Tesis: cap. 3, ecuaciones 3.1–3.8, pp. impresas 9–11; SHA-256 `AA8ECAD90A2D52942081B40FD78849D2DC4B280BBCB4B5BD828E4812DFEC5486`.
- Código revisado en commit `8657304fbf4c3ed8022aae74d3bad380989c466f`: `scripts/thesis_sir_model.py` SHA-256 `BA0C1E44BCFB31FFB915D3390FD8735597DDCDD76A574C730A908EAFB2EB5F55`; `scripts/thesis_sir_data.py` SHA-256 `016FAF0B4504965DEF7620B74E2654D3EE263663F9A078E41A48DE46F3DEC592`.
- El hash de datos ya registrado en el ingreso de fuentes es `c010ea2ecd7286fde9684a485d135d06d30440c516d61e3fb162b29fb5072a94`. El JSON no se leyó de nuevo en este incremento.

## Correspondencia observada

| Tesis | Adaptador | Estado del mapeo |
|---|---|---|
| Población fija `N=129,960,600`; flujo `lambda=beta*S*I/N`; EDO SIR (3.1–3.3) | `THESIS_SIR_POPULATION` (línea 14), `ThesisSIRParameters.derivative()` (141), flujo de infección/remoción (156–158) | Consistente estáticamente |
| Beta positiva armónica de 1–3 términos (3.4–3.5) | `HarmonicTerm` (44), validación de parámetros (69–119), `beta()` (125–138) | Consistente estáticamente |
| Iniciales `I0=10^ell_I`, `S0=N*f_S`, `R0=N-S0-I0>=0` (3.6–3.7) | `initial_state()` (163–170) y factibilidad inicial (121–123) | Consistente estáticamente |
| Media semanal `q * integral(beta*S*I/N)` sobre intervalo desplazado por `delta/7` (3.8) | `evaluate_thesis_sir_weekly_counts()` (337), desplazamiento (375), intervalos (392–393) y media predicha (411) | Consistente estáticamente |
| Serie seleccionada para observación | `scripts/thesis_sir_data.py` fija `DGE_monday_sunday_candidate`; el ingreso de fuentes documenta 56 semanas y digest | Sin cambio ni relectura de datos |

## Límites

- `SOURCE_CODE_CROSSWALK: PASS` significa que el mapeo estático anterior coincide con la especificación de las páginas indicadas; no es una revisión matemática formal ni prueba del solver.
- Simulación/calibración con datos reales: `NOT_RUN`. Validez numérica: `NOT_RUN`. Validez científica e identificabilidad: `NOT_ASSESSED`.
- No se hizo ajuste, se generaron estimaciones, se invocó un proveedor ni se ejecutó código del proyecto en este incremento.
