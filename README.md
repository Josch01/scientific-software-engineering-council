# Scientific Software Engineering Council — v0.1.0

Skill portable de ingeniería de software científico orientada a auditorías, desarrollo, GUI de escritorio, IDL y experimentos reproducibles. **Repositorio nuevo y separado** de `Josch01/skill-investigacion-cientifica-rag`.

## Qué es y qué no es

- Es una skill `SKILL.md` con protocolos, plantillas y herramientas pequeñas verificables con Python estándar.
- El router prepara un plan mínimo de especialistas y gates; **no inicia agentes** ni descarga skills automáticamente.
- El gate comprueba estructura e integridad de evidencias aportadas, pero no comprueba la honestidad de un log ni certifica algoritmos.
- Para contextos realmente separados: configurar en v0.2 un adaptador al runtime de Codex, Gemini CLI o Antigravity con sesiones/worktrees reales, permisos y presupuestos.
- IDL significa *Interactive Data Language* de NV5; si se usa otro significado de IDL, cambiar el adaptador.

## Instalar en Gemini CLI y Codex

Consulta [INSTALLATION.md](INSTALLATION.md) para instalarla desde GitHub y comprobar su funcionamiento.

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

## Modos de subagentes (v0.2-dev)

Elegir **solo Gemini**, **solo Codex** o **ambos**. El router escoge los especialistas; `prepare_agents.py` genera perfiles nativos y paquetes por rol, sin ejecutarlos:

```bash
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode gemini --project /ruta/al/proyecto
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode codex --project /ruta/al/proyecto --apply
python scripts/prepare_agents.py examples/seir_desktop_audit.json --mode both --project /ruta/al/proyecto --apply
```

Ver [modos y límites](references/PROVIDER_MODES.md). La coordinación automática entre proveedores sigue pendiente.
