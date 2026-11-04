# P3.12 — frontend científico opcional PySide6

**Estado:** implementación y revisión independiente terminadas; CI del PR pendiente. No se hizo merge ni se publicó una release.

## Capacidad

Se añadió `scripts/scientific_workspace_qt.py` como frontend opcional fuera de Tkinter. Abre un proyecto y manifiesto, usa el loader existente para verificar recursos y SHA-256 antes de cambiar la vista activa, y construye la interfaz desde `WorkspaceViewModel`. Las pestañas, vistas de ecuaciones/parámetros, gráficas y recursos usan renderers fijos; archivos de Python siguen siendo texto inerte.

El botón de simulación solo aparece para una acción SIR confiable registrada por SSEC. La confirmación humana predeterminada es negativa. Tras aprobar, la acción corre en un hilo Qt, el resultado vuelve a pasar por el contrato de salida existente y se muestra en memoria. La interfaz no guarda ni sobrescribe archivos del proyecto. Los errores de ejecución no producen resultados. Tk y los servicios de propuestas/auditoría continúan disponibles sin PySide6.

## Evidencia local

- Plataforma: Windows 10.0.26300, Python 3.14.0, PySide6 6.11.1 ya presente; no se instaló software.
- Suite Qt: `python -m unittest tests.test_scientific_workspace_qt -v` — **6 pasaron, 0 fallaron**. Incluye workspace verificado, digest incorrecto, rechazo de confirmación, simulación SIR sintética aprobada con archivos fuente intactos, manifiesto anidado seleccionado desde el diálogo y fallo al iniciar el worker.
- Suite enfocada combinada: **164 pruebas, 0 fallos, 1 omitida** con el comando:

  ```text
  python -m unittest tests.test_scientific_workspace_generation tests.test_scientific_workspace_proposals tests.test_scientific_workspace_audit tests.test_scientific_workspace_app tests.test_scientific_workspace_actions tests.test_scientific_workspace_loader tests.test_scientific_workspace_view tests.test_scientific_workspace tests.test_provider_runtimes tests.test_scientific_workspace_qt -q
  ```

- La única omisión local es el caso de escape por symlink que no pudo crear su fixture en Windows (`WinError 1314`).
- `py_compile` y `git diff --check`: **PASS**.
- `python scripts/validate_skill.py` se ejecutó, pero esa verificación estructural falla en el worktree local porque exige que el nombre de la carpeta raíz coincida con el nombre frontmatter `scientific-software-engineering-council`; esta rama vive en la carpeta aislada `p3-12-pyside6-workspace`. No reporto el resultado como PASS. El job CI ejecutará el validador en el checkout canónico.
- Se abrió el ejemplo sintético `examples/sir_scientific_workspace.json` con el plugin Qt nativo y se inspeccionó una captura. Se ajustaron colores para impedir que el tema oscuro del sistema redujera el contraste.
- El CI de P3.11 base terminó después de su implementación: run [#158](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41766130701), 4/4 jobs Windows/Ubuntu × Python 3.11/3.12 correctos. El CI de P3.12 todavía debe ejecutarse.

## Defectos y correcciones

Las regresiones end-to-end detectaron tres defectos importantes y se corrigieron:

- El botón quedaba deshabilitado después de un worker exitoso; ahora se restaura al recibir la señal terminal de Qt.
- En Windows, `os.path.relpath` produce separadores `\\` que el loader portable rechaza para manifiestos anidados; el diálogo convierte a `/` y tiene un caso reproducible.
- Un error al iniciar `QThread` dejaba la ventana ocupada sin proceso; se limpia el ticket/estado de la UI, no se muestra un resultado y se presenta el error.

También se probó que fallar al cargar un digest nuevo no reemplaza el workspace previamente verificado. La revisión independiente encontró estos tres casos en la primera pasada; la revisión de seguimiento confirmó que las correcciones son adecuadas y no reportó defectos reproducibles P0–P2.

## Decisiones y límites

- Qt es una alternativa opcional; no se cambia ni se elimina Tk. El módulo comunica PySide6 ausente y no intenta instalarlo.
- Se usa `QPainter` para gráficas pequeñas; no se requiere Qt WebEngine ni una dependencia de gráficos adicional.
- El ejemplo ejecutado es sintético y solo verifica integración de software. Ecuaciones, unidades y datos del SIR del usuario siguen `NOT_RUN`; esto no establece validez científica.
- CI no instala PySide6; por diseño, omitirá los cuatro tests específicos del frontend si la dependencia no está presente. La ejecución de widgets y la inspección visual aquí son solo Windows local; UI Qt en Linux sigue `NOT_RUN`.
- Las pantallas Qt aún no exponen el despacho de auditoría P3.10 ni la generación/revisión de propuestas P3.11; esos flujos permanecen en Tk y sus servicios permanecen desacoplados de la UI.
- Invocaciones reales de Codex/Gemini/AGY, instalación de dependencias, ejecución de código generado y validez matemática/científica no se realizaron.

## Entrega

- Commit de implementación: pendiente.
- Pull request P3.12: pendiente; se mantendrá como borrador apilado sobre P3.11.
- Revisión independiente: completa, solo lectura; sin hallazgos P0–P2 pendientes.
- Merge a `main` y release: no realizados.
