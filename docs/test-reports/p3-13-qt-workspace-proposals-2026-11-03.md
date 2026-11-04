# P3.13 — propuestas de workspace en PySide6

**Estado:** implementación local, pruebas deterministas y revisión independiente completadas; CI del PR pendiente. No se hizo merge ni release.

## Capacidad

La ventana Qt ahora permite describir cambios, seleccionar recursos verificados y solicitar una propuesta local usando el servicio P3.11. Ningún recurso se preselecciona. Antes del despacho muestra confirmación explícita de posible consumo de cuota; una respuesta negativa no llama al servicio. Durante la generación presenta progreso y cancelación. Un resultado listo permanece `NOT_APPROVED` hasta que se valida con el loader, se muestra el diff acotado completo y la persona selecciona **Aprobar y guardar**. La aprobación guarda/abre un manifiesto nuevo digest-nombrado. La importación manual JSON usa el mismo preview y gate.

No se ejecuta código generado ni se sobrescriben los archivos originales. Si la configuración no admite una política de propuesta segura o el CLI no puede aplicarla, la interfaz conserva la importación manual.

## Evidencia local

- Windows 10.0.26300, Python 3.14.0, PySide6 6.11.1 ya instalado; no se instalaron paquetes.
- Suite Qt propuesta: **6 pasaron**. Cubren rechazo de confirmación de cuota, bloqueo si no hay selección explícita, dispatch mock con `accept_unmetered_cost=True`, diff y aprobación create-only, importación manual sin proveedor, cancelación y fallo al iniciar worker.
- Suite combinada workspace/provider/Qt: **170 pruebas, 0 fallos, 1 omitida**. La omisión continúa siendo el fixture symlink bloqueado por `WinError 1314` en Windows. Comando reproducible:

  ```text
  python -m unittest tests.test_scientific_workspace_generation tests.test_scientific_workspace_proposals tests.test_scientific_workspace_audit tests.test_scientific_workspace_app tests.test_scientific_workspace_actions tests.test_scientific_workspace_loader tests.test_scientific_workspace_view tests.test_scientific_workspace tests.test_provider_runtimes tests.test_scientific_workspace_qt tests.test_scientific_workspace_qt_proposals -q
  ```

- `py_compile` y `git diff --check`: **PASS**.
- Captura del diálogo de selección/datos verificados inspeccionada con Qt nativo; se corrigió el contraste de diálogo heredado del tema oscuro.
- Las llamadas a `generate_workspace_proposal` son mocks deterministas. No se invocó ningún modelo ni CLI real, no hubo coste y no se afirmó validez científica.

## Defectos encontrados y decisiones

- La tabla inicialmente esperaba `byte_count` en `LoadedResource`; el contrato expone bytes y ahora el conteo se deriva de `len(content)`.
- Qt `QProgressDialog` no expone `cancelButton()`; la ruta de cancelación usa el botón Qt real y fue reproducida offscreen.
- `reset()` no ocultaba el diálogo de progreso al estar desactivado el auto-reset; la UI ahora lo oculta explícitamente al cancelar, completar o fallar el inicio.
- Se conserva el servicio de generación y el validador de propuestas existentes; no se duplica el prompt, staging, parser, diff ni persistencia.

## Límites

- Proveedor real, autenticación/cuota, y el caso SIR del usuario permanecen `NOT_RUN`.
- CI en esta rama aún no se ejecuta; como PySide6 es opcional, los jobs estándar que no lo incluyen omitirán los 12 tests Qt específicos acumulados.
- La solicitud de auditoría P3.10 todavía solo se expone desde Tk. El runner para código de modelo generado sigue pospuesto.

## Entrega

- Commit y PR draft: por registrar.
- Revisión independiente: completa, solo lectura; sin defectos reproducibles P0–P2 pendientes.
- Merge a `main` y release: no realizados.
