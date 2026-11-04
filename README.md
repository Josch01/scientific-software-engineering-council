# Scientific Software Engineering Council — v0.2.0-dev.3

Skill portable de ingeniería de software científico orientada a auditorías, desarrollo, GUI de escritorio, IDL y experimentos reproducibles. **Repositorio nuevo y separado** de `Josch01/skill-investigacion-cientifica-rag`.

## Qué es y qué no es

- Es una skill `SKILL.md` con protocolos, plantillas y herramientas pequeñas verificables con Python estándar.
- El router prepara un plan mínimo de especialistas y gates; **no inicia agentes** ni descarga skills automáticamente.
- El gate comprueba estructura e integridad de evidencias aportadas, pero no comprueba la honestidad de un log ni certifica algoritmos.
- Para contextos realmente separados: configurar en v0.2 un adaptador al runtime de Codex, Gemini CLI o Antigravity con sesiones/worktrees reales, permisos y presupuestos.
- IDL significa *Interactive Data Language* de NV5; si se usa otro significado de IDL, cambiar el adaptador.

## Inicio rápido

```bash
python scripts/validate_skill.py
python -m unittest discover -s tests -v
python scripts/route_task.py examples/seir_desktop_audit.json
python scripts/release_gate.py --task examples/seir_desktop_audit.json --evidence examples/release_evidence_not_run.json
```

El último comando debe bloquear (exit code 2) porque se incluyen verificaciones **no realizadas**: es un ejemplo de comportamiento seguro.

## Ejemplo de uso con un agente

> Usa `scientific-software-engineering-council` para auditar mi código SEIR y su GUI. No modifiques archivos hasta levantar un inventario. Distingue fallos matemáticos, numéricos y de software. Diseña un plan modular, propón las pruebas, delega la implementación y la revisión en contextos separados si el runtime lo permite. Bloquea release ante tests no ejecutados o evidencia incompleta.

## Ruta de evolución

- `v0.1`: skill portátil, router de riesgo/roles, contratos, tests propios y release gate mecánico.
- `v0.2`: adaptadores reales para CLI de agentes con aislamiento, worktrees, rollback, trazas, presupuestos, sandbox y revisión independiente.
- `v0.3`: presets de proyectos `numpy/scipy`, `PySide6`, `idlpy`, optimización, ML y datos; CI con pruebas de entorno.
- `v1.0`: benchmarks reproducibles, evaluación del propio consorcio, política de actualización de skills dependientes y distribución multiplataforma auditada.

Documentación de referencia: https://agentskills.io/specification , https://doc.qt.io/qtforpython-6/ , https://www.nv5geospatialsoftware.com/docs/Python.html

## Panel gráfico SSEC (v0.2-dev.2)

Control local para **Gemini / Codex / ambos**, máximo simultáneo planificado de subagentes, política de permisos, presupuesto estimado y auditoría. Requiere escritorio Windows o Linux y Python 3.11+ con Tkinter:

```bash
python scripts/config_panel.py
```

- **Previsualizar**: plan de roles y tandas sin escribir.
- **Guardar configuración**: solo `.ssec/config.json` bajo el proyecto elegido.
- **Preparar perfiles**: definición nativa y contexto mínimo para cada rol seleccionado, previa confirmación; no arranca modelos.
- **Sin GUI**: `python scripts/config_panel.py --check` valida el modelo sin abrir ventana.

Documentación y límites: [Panel y control de seguridad](references/CONFIG_PANEL.md). El coste/tiempo y permisos son políticas **solicitadas, no aplicadas**. El runner real queda pendiente.

El panel incluye **Abrir espacio científico**. Abre el manifiesto del proyecto seleccionado en una ventana hija y vuelve a usar el loader con verificación SHA-256; no inicia agentes ni ejecuta archivos del proyecto.

## Auditorías reales desde el panel — v0.2-dev.3

Se agregó un ejecutor **experimental y limitado a auditorías**: inicia procesos Codex y/o Gemini desde snapshots separados, guarda logs, controla concurrencia y termina procesos por tiempo o cancelación. El panel incluye **4 · Ejecutar auditoría** y **Cancelar**. La simulación del ejecutor se prueba en CI; no requiere cuentas de los proveedores.

```bash
# Solo planificar, sin ejecución/coste/escritura
python scripts/run_agents.py examples/seir_desktop_audit.json --mode both --project /ruta/proyecto
# Ejecutar CLIs instaladas y autenticadas, con consentimiento sobre coste no medido
python scripts/run_agents.py examples/seir_desktop_audit.json --mode both --project /ruta/proyecto --execute --accept-unmetered-cost
```

El supervisor muestra progreso por especialista mediante eventos JSONL versionados (`--emit-progress-jsonl`, habilitado por la GUI). Estos estados describen procesos y conservan `NOT_APPROVED`; no significan que la auditoría haya sido aceptada. La salida JSON original del CLI permanece igual cuando no se activa el flag.

Lee [RUNNER.md](references/RUNNER.md) antes de ejecutar: snapshots no son un sandbox del sistema operativo, límites de USD no son medibles, el resultado no certifica validez científica y no se integran cambios automáticamente.

## Worktrees y coordinación de desarrollo — v0.2-dev.4

Se añadió un [coordinador por worktrees](references/WORKTREE_DEVELOPMENT.md), un mailbox de handoffs y un ejecutor opt-in de CLI para desarrollo en ramas separadas. Gemini y Codex se eligen por tarea. Aún **no** hay integración automática de cambios ni auditoría autónoma cerrada; el gate bloquea y exige revisión humana.

```bash
python scripts/worktree_coordinator.py plan examples/seir_worktree_build.json --project /path/to/clean-git-project
python scripts/worktree_coordinator.py init examples/seir_worktree_build.json --project /path/to/clean-git-project --apply
python scripts/worktree_coordinator.py gate --project /path/to/clean-git-project --task-id SEIR-BUILD-01
```

## Espacios científicos dinámicos (experimental)

La app opcional abre las secciones configuradas por manifiesto, carga recursos mediante el loader seguro y muestra simulaciones y observaciones con componentes reutilizables. Puede abrirse sola o desde **Abrir espacio científico** del supervisor, donde aparece como ventana hija y comienza en el proyecto seleccionado. No necesita paquetes adicionales; la interfaz usa Tkinter, y el modo `--check` no importa ni inicia Tk. El renderer tiene límites de vista documentados, anuncia truncamientos y conserva las series completas en la tabla; esto no valida ciencia.

```bash
python scripts/scientific_workspace_app.py --project-root /ruta/al/proyecto workspace.json
python scripts/scientific_workspace_app.py --check --project-root /ruta/al/proyecto workspace.json
```

Los recursos de código se muestran como texto inerte y la app no importa código del proyecto o del manifiesto. Un host confiable puede inyectar un callback de simulación ya revisado; el usuario debe confirmar cada ejecución, la salida se muestra en memoria y no valida ciencia. Consulte [manifiestos, loader y espacio de escritorio](references/SCIENTIFIC_WORKSPACES.md) para el contrato y sus límites.

## Centro de Control Científico Qt (experimental, P3.18)

La aplicación opcional de PySide6 integra proyectos, agentes, experimentos, auditorías, código y resultados en una ventana. Reutiliza el workspace y los componentes científicos existentes; carga manifiestos y recursos por el loader con contención y SHA-256. La vista de agentes reutiliza configuración, preparación de perfiles y el runner local. Guardar política, preparar perfiles e iniciar auditorías requiere confirmación humana; la confirmación de auditoría describe la actualización de `.ssec/config.json` y advierte que puede consumir cuota sin costo medible. Cancelar, fallar o salir con código cero nunca aprueba el resultado. Abrir la aplicación no invoca proveedores.

```bash
python scripts/scientific_control_center_qt.py
python scripts/scientific_control_center_qt.py --project-root /ruta/al/proyecto --manifest workspace.json
```

PySide6 sigue siendo opcional. Las vistas científicas usan WebEngine local si está disponible y mantienen su fallback nativo; no necesitan CDN. La demostración reproducible y sus límites están en [el informe P3.18](docs/test-reports/p3-18-integrated-control-center-2026-11-04.md). El SIR y los datos del usuario siguen `NOT_RUN`.

## Catálogo opt-in de extensiones (P4.2)

El catálogo v1 acepta solo metadatos con fuente, commit y digest fijados, permisos declarados, revisión y rollback. El CLI valida un archivo local; no descarga, instala, importa ni ejecuta extensiones. El catálogo de ejemplo está vacío hasta que una extensión haya sido revisada explícitamente.

```bash
python scripts/extension_catalog.py validate examples/extension_catalog.json
```

Consulte [el contrato y los límites del catálogo](references/EXTENSION_CATALOG.md).
