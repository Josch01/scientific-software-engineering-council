# P2.5 — SIR armónico de tesis

- Contrato, observador semanal y RK4 existente: **PASS**; 62 pruebas focalizadas en Windows (Python 3.14), `compileall` y `git diff --check`.
- Ejemplo de cuatro semanas sintéticas: **PASS** (`SYNTHETIC_FIXTURE`); no presenta validez científica.
- Importación de solo lectura del JSON: **PASS**; campo `DGE_monday_sunday_candidate`, 56 filas y SHA-256 registrado en el [ingreso de fuentes](sir-thesis-validation-target-2026-11-13.md). No se ejecutó el modelo con esos datos.
- Revisión independiente: corregido redondeo de `I₀=N` y añadida prueba del retardo central; la fuente primaria y ecuaciones quedaron citadas en la especificación.
- Ejecución SIR real, optimización/calibración y CI Windows/Linux de este incremento: **NOT_RUN**. Validez numérica/científica e identificabilidad del caso real: **NOT_ASSESSED**.
- Límite: este incremento calcula medias semanales para parámetros explícitos; no estima parámetros ni afirma que éstos estén identificados.
