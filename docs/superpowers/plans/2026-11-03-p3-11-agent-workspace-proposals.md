# P3.11 — Plan y verificación

- [x] Reutilizar el loader, snapshot selectivo, registro de componentes y validador de workspace existentes.
- [x] Añadir servicio de propuesta separado de Tkinter con respuesta JSON cerrada, digestada y sin aprobación automática.
- [x] Exigir confirmación explícita de coste/cuota antes de iniciar el único proceso CLI.
- [x] Restringir Gemini a plan mode con política temporal de herramientas; omitir Codex al no tener un control de no-ejecución verificable.
- [x] Conectar botón, selector de recursos, objetivo y worker asíncrono al diálogo de diff/aprobación existente.
- [x] Mantener el flujo de importación/revisión JSON sin proveedor.
- [x] Añadir pruebas deterministas de servicio, adaptadores y GUI; no invocar modelo.
- [ ] Obtener CI de Windows/Linux del PR P3.11.
- [x] Documentar que el proveedor real y el SIR del usuario continúan `NOT_RUN`.
