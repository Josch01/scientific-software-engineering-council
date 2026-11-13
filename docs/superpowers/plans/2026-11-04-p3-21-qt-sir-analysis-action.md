# Plan P3.21 — Ejecutar análisis SIR desde Qt

Base: `0fb5f7e` (`codex/p3-20-sir-analysis-input`). Ejecutar en el worktree `p3-21-qt-analysis-action`.

## Pasos verificables

1. **Estabilizar fixture Windows.** Añadir `-text` a `examples/sir_analysis_input_demo/**`; conservar bytes LF en los recursos con SHA-256. Ejecutar los dos casos base que fallaban y la prueba de hashes.
2. **Salida anidada create-only.** Cambiar primero las pruebas del builder para crear el resultado bajo una subcarpeta vacía del proyecto, cargar su manifiesto con la raíz del proyecto y confirmar que los bytes originales no cambiaron. Mantener rechazo del root, ancestros, rutas fuera de raíz y destinos no vacíos. Validar el manifiesto antes de crear archivos.
3. **Acción Qt en worker.** Añadir disponibilidad basada en contrato, resumen de entradas/destino, confirmación `No` por defecto, progreso indeterminado, bloqueo de acciones concurrentes y protección de cierre/cambio de proyecto. Resultado verificado se carga con la raíz existente y abre Resultados.
4. **Pruebas de flujo.** Cubrir rechazo sin salida, aceptación con el builder real, fallo sin cambio de vista y la carga/navegación del resultado con sus vistas de ajuste, sensibilidad y residuales. Comprobar que entradas no se alteran y estados `NOT_ASSESSED`/`NOT_RUN` permanecen explícitos.
5. **Verificación y entrega.** Ejecutar suite específica de SIR y Qt, `compileall`, `git diff --check`; revisar diff, documentar hallazgos y limitación de cancelación, actualizar matriz de funciones, crear commit y PR draft sin merge. CI remoto indicará soporte Linux/Windows.

Cada paso de código sigue RED→GREEN; no se inicia el siguiente hasta leer el resultado de la prueba previa.
