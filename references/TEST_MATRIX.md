# Matriz de pruebas para software científico

## Capas obligatorias según superficie

1. Contratos unitarios: tipos, unidades, array shape, valores faltantes/NaN/inf, límites y errores esperados.
2. Propiedades/invariantes: conservación, positividad cuando el modelo lo exige, simetría, idempotencia, monotonicidad demostrada donde aplique.
3. Oráculos: solución exacta, solución manufacturada, ejemplo conocido, segundo algoritmo o resultado independiente.
4. Numéricos: sensibilidad a paso/tolerancias, solver alternativo, convergencia/refinamiento, residuales, rigidez, precisión, error relativo/cotas.
5. Estadística/ML: train-val-test sin leakage, semillas, baselines, repeticiones, sensibilidad, intervalos, drift, shift, resultados fuera de muestra.
6. Optimización: dominio y restricciones, infeasibilidad, seeds, presupuestos, fitness evaluaciones, mejor/mediana/dispersion, reanudación, ejecución interrumpida.
7. Arquitectura/GUI: hilos sin bloqueo, cancelación, errores de I/O, progreso, guardado, exploración y exportación, DPI/accessibility, smoke real por SO.
8. IDL bridge: dtype, orden fila/columna, NaN, dimensión, errores, ownership/referencias, licencia y versión compatible.
9. Integración: archivos/revisión exacta, seguridad de rutas, actualizaciones/migraciones, rendimiento y regresión de benchmark.

Usar `pytest` + `hypothesis` cuando estén disponibles. Ruff/typing/coverage/audit de dependencias son checks recomendados, nunca sustitutos de tests numéricos. Dependencias/versiones/commands deben verificarse y fijarse por proyecto. Un check no ejecutado = `NOT_RUN`.

Protocolo de fallos: conservar caso mínimo reproducible; clasificar `IMPLEMENTATION_BUG | NUMERICAL_UNSTABLE | MODEL_INVALID | DATA_DEFECT | ENVIRONMENT | UNKNOWN`. No maquillar precisión con tolerancias elegidas después de ver resultados.
