# P3.28 — Control del paso RK4

- Implementación: paso RK4 seleccionable de 0.1–0.001 semanas; confirmación humana, resultado digestado y datos previos invalidados si cambia el paso.
- `PASS` — 31 pruebas focalizadas de SIR Qt, tema y charts; incluye fixture sintético de alta transmisión con Δt=0.01 y verificación de procedencia/invalidez.
- `PASS` — `py_compile` y `git diff --check`.
- Log completo: temporal local `%TEMP%\ssec-p3-28-qt-regression.log`.
- SIR de tesis con datos reales: `NOT_RUN`; validez e identificabilidad: `NOT_ASSESSED`.
- Sin cambios al modelo, solver ni archivos fuente de tesis; no se ejecutó proveedor.
