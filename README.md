# Scientific Software Engineering Council — v0.2.0-dev.2

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
