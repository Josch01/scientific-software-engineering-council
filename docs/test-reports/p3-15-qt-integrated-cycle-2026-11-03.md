# P3.15 — ciclo integrado del workspace Qt

## Resultado

Se agregó una prueba offscreen que recorre en una ventana Qt: solicitud de propuesta, validación y diff, aprobación create-only, simulación del fixture SIR sintético mediante el solver SSEC existente, y solicitud de auditoría. La prueba automatiza las respuestas de confirmación; verifica que las rutas de confirmación se solicitan y que el manifiesto original permanece byte por byte intacto.

La generación de propuesta, la respuesta de auditoría y los cuadros de confirmación se sustituyen por respuestas deterministas. El flujo no llama Codex, Gemini ni AGY. La simulación numérica sí usa `scientific_core` y su salida es evidencia de software sobre el fixture sintético; no establece validez para el modelo SIR del usuario.

## Verificación

- Prueba integral Qt: **1 pasada**; propuesta/aprobación, solver SIR real de SSEC, auditoría mockeada y copia create-only.
- Suite combinada de workspace, proveedores y Qt: **178 pruebas, 0 fallos, 1 omitida**. La omisión es el fixture symlink que Windows no puede crear sin privilegios (`WinError 1314`).
- Comando de la prueba integral: `python -m unittest tests.test_scientific_workspace_qt_e2e -q`.
- `py_compile` y `git diff --check`: pasaron.

## Limitaciones y estados

- CLI real, compatibilidad de cuenta y revisión por especialistas reales: `NOT_RUN`.
- Ecuaciones/datos del SIR real del usuario y validez científica: `NOT_RUN`.
- Linux con PySide6 y prueba visual Qt allí: `NOT_RUN`.
- CI del commit `406f271`: run [#174](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41776412231), en curso en Windows/Ubuntu × Python 3.11/3.12; esos jobs no instalan PySide6.

## Entrega

- Commit: `406f271` (`test: cover integrated Qt workspace cycle`).
- El incremento solo agrega cobertura de integración y documentación; no requiere cambios al código de producción.
- PR draft [#39](https://github.com/Josch01/scientific-software-engineering-council/pull/39), apilado sobre P3.14; abierto y sin merge.
- No se invocaron proveedores, no se instalaron dependencias y no se hizo merge.
