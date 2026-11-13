# P3.22 — Historial de corridas SIR

**Estado local: PASS.** Windows, Python 3.14.0 y PySide6 6.11.1: 54 pruebas focalizadas pasaron; 2 pruebas de symlink omitidas por privilegios del entorno. compileall y git diff --check: PASS. Salida detallada: %TEMP%\ssec-p3-22-focused-tests-2026-11-13.log.

- Verificado: historial ordenado y acotado a 100 registros; logs dañados/no seguros no se abren; diálogo Qt deshabilita fallos; corrida exitosa se abre como histórica; digest discordante conserva las vistas existentes.
- Defectos corregidos: en Windows, DirEntry.stat no entregaba identidad de archivo; además, el ID hexadecimal real de P3.21 era rechazado por fixtures con guiones. El lector ahora coteja lstat/descriptor y acepta el formato productor, cubierto por regresión.
- Arquitectura: sin nuevo solver ni ejecución de código; reutiliza loader, vista y digest de salida P3.21. Lee como máximo 65 536 bytes por log y exige la ruta generada del mismo run ID.
- Riesgos: las bitácoras no están firmadas; el digest verifica integridad frente a lo registrado, no autenticidad. Prueba de symlink omitida por política del host.
- Pendiente: suite completa local, Windows CI todavía IN_PROGRESS, GUI Qt Linux y datos SIR reales NOT_RUN; validez matemática e incertidumbre NOT_ASSESSED.
- GitHub: PR #53 borrador apilado sobre P3.21; workflow #231 reporta Ubuntu 3.11/3.12 SUCCESS y Windows 3.11/3.12 IN_PROGRESS. Sin merge a main ni release.
