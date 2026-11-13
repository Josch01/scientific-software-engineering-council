# P3.30 — Límite de autenticidad del historial

- `PASS`: prueba Qt focalizada del diálogo de historial, 1 passed en Windows/offscreen.
- El diálogo advierte que SHA-256 detecta cambios frente al digest guardado, pero no autentica autor ni proceso; estilo de advertencia compartido y etiqueta accesible.
- Sin cambios al motor, los logs, los digests ni la ejecución científica; no se añade firma ni dependencia.
- `NOT_RUN`: suite Qt completa y renderizado Linux. El modelo/datos SIR de tesis permanece `NOT_RUN`.
