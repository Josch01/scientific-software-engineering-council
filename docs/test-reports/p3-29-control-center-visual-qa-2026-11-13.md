# P3.29 — QA visual del Centro de Control

- UI/UX Pro Max está disponible localmente; no se instaló software adicional. El sistema Qt existente ya usa PySide6 + Qt WebEngine, SVG local, fallback Qt nativo y transiciones con opción de movimiento reducido.
- Se conservó la paleta charcoal/morado ya aprobada: el resultado inicial de búsqueda sugería una paleta naranja/neumórfica no adecuada al producto.
- Corregido el foco de teclado: se resalta el elemento de navegación, no el marco completo de la barra lateral. Tokens de documentación sincronizados con el tema.
- `PASS` — revisión visual Windows 1440×920; gráficas WebEngine cargadas y datos reales importados (56 semanas, SHA-256 coincidente).
- `PASS` — 31 pruebas focalizadas de SIR Qt, tema y charts; `py_compile` y `git diff --check`.
- La aplicación quedó abierta con los datos cargados. No se ejecutó simulación ni ajuste: SIR real `NOT_RUN`; validez/identificabilidad `NOT_ASSESSED`.
- CI y QA visual Linux quedan sujetos a los checks de este PR.
