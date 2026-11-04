# P3.14 — auditoría de workspace en PySide6

## Resultado

La ventana Qt permite solicitar una auditoría mediante el servicio P3.10 existente. No selecciona recursos por defecto; exige selección explícita y confirmación antes de enviar datos a procesos CLI que pueden consumir cuota. La ejecución corre en un `QThread`, admite cancelación con un archivo temporal conservado hasta que termina el worker, y presenta el informe en texto de solo lectura. No ejecuta código del proyecto.

La UI refuerza `release_status=NOT_APPROVED`, `scientific_validity=NOT_CERTIFIED` y `human_review=NOT_PERFORMED`. Si terminan los procesos CLI, el estado sigue siendo `PROCESSES_COMPLETED_NOT_AUDITED`.

## Verificación

- Windows 10.0.26300, Python 3.14.0 y PySide6 6.11.1 ya instalados. No se instaló software.
- Las 7 pruebas Qt nuevas pasaron offscreen. Cubren rechazo de cuota, selección explícita, despacho de IDs seleccionados y reporte no aprobado, cancelación, fallo al iniciar el worker, error del servicio y lanzamiento directo con `--help`.
- Suite combinada de workspace, proveedores y Qt: **177 pruebas, 0 fallos, 1 omitida**. La omisión es el fixture de symlink que Windows no puede crear sin privilegios (`WinError 1314`).
- Comando ejecutado:

```text
python -m unittest tests.test_scientific_workspace_generation tests.test_scientific_workspace_proposals tests.test_scientific_workspace_audit tests.test_scientific_workspace_app tests.test_scientific_workspace_actions tests.test_scientific_workspace_loader tests.test_scientific_workspace_view tests.test_scientific_workspace tests.test_provider_runtimes tests.test_scientific_workspace_qt tests.test_scientific_workspace_qt_proposals tests.test_scientific_workspace_qt_audit -q
```

- Revisión independiente del diff: sin hallazgos reproducibles P0–P2; el revisor repitió las 7 pruebas Qt y el `--help` de lanzamiento directo.

## Limitaciones y estados

- Auditoría real con Gemini/AGY/Codex CLI: `NOT_RUN`; las pruebas mockean el servicio y no consumen cuota.
- Ejecución visual Qt en Linux: `NOT_RUN`; la suite sin PySide6 omite estas pruebas opcionales.
- Auditoría independiente de las salidas, validez matemática/científica y SIR concreto del usuario: `NOT_RUN`.
- CI de esta rama: pendiente.
- Se corrigió un defecto reproducible del modo de lanzamiento documentado: la ejecución directa del script no encontraba `scripts.agent_runtime`; ahora la raíz del repositorio se agrega a la ruta de imports. La regresión de `--help` pasa. Otros hallazgos reproducibles P0–P2: ninguno; los tests rojos anteriores confirmaron la ausencia de la acción Qt y el fallo de import, no se usaron como prueba de seguridad.

## Entrega

- Commit: pendiente.
- PR draft: pendiente.
- No se hizo merge ni se invocó ningún proveedor real.
