# P3.21 — Acción Qt para análisis SIR

**Estado local: PASS en pruebas focalizadas de Windows.** Suite: 123 pasaron, 2 omitidas por privilegios de symlink; `compileall` y `git diff --check`: PASS. Salida completa: `%TEMP%\ssec-p3-21-targeted-tests-2026-11-12.log`.

- Entorno/comando: Windows, Python 3.14.0, PySide6 6.11.1; `python -m unittest` sobre `test_scientific_run_log`, `test_scientific_sir_analysis_demo`, `test_scientific_control_center_qt`, `test_scientific_workspace_science_views`, `test_scientific_workspace_qt_views`, `test_scientific_core`, `test_scientific_observations` y `test_scientific_workspace_loader`.
- Cobertura: aceptación/rechazo, fallo sin cargar resultados antiguos, ejecución fuera del hilo GUI, carga validada y bloqueo de duplicados; además, carrera de creación de logs.
- Defectos corregidos: checkout Windows alteraba bytes de recursos con SHA-256; dos ejecuciones simultáneas podían chocar al crear el directorio de logs.
- Decisiones: se reutiliza el builder P3.20; resultados nuevos van a un directorio exclusivo, conservan entradas/log/procedencia y se cargan solo tras validación; no se ejecuta código del proyecto.
- Límites: sin cancelación segura porque el motor actual no admite interrupción; progreso indeterminado, sin porcentajes inventados. Suite completa y verificación Linux: `NOT_RUN` en este incremento.
- Validez: solo fixture sintético; SIR/datos del usuario `NOT_RUN`; incertidumbre y validez matemática `NOT_ASSESSED`; ningún proveedor invocado.
- GitHub: rama `codex/p3-21-qt-analysis-action`; commit y PR pendientes; no hay merge a `main` ni release.
