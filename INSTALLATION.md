# Instalación y primeros usos

SSEC ofrece dos modos con contratos y límites compartidos:

- **Modo A — skill portable:** el agente descubre `SKILL.md` y sus referencias. Puede usarse sin la aplicación visual.
- **Modo B — Centro de Control:** la app PySide6 opcional abre proyectos/workspaces locales y puede iniciar el runner de auditoría solo después de confirmación explícita.

La skill y el motor pueden revisarse sin instalar paquetes. Esta guía no instala software, skills ni proveedores.

## Modo A — Codex

Para un proyecto, copia o clona este repositorio bajo `.agents/skills/scientific-software-engineering-council/`. Para disponibilidad del usuario, usa `~/.agents/skills/scientific-software-engineering-council/`. Codex busca `.agents/skills` en el proyecto y sus directorios superiores; inicia una sesión nueva para que descubra la skill.

Referencia oficial: [crear y usar skills en Codex](https://learn.chatgpt.com/docs/build-skills?kbid=111697).

## Modo A — Gemini CLI

La documentación oficial permite instalar desde Git o enlazar una ruta local. Si decides instalar desde Git, deja activa la confirmación de seguridad:

```bash
gemini skills install https://github.com/Josch01/scientific-software-engineering-council.git --scope user
gemini skills list --all
```

Para un proyecto usa `--scope workspace`; antes de hacerlo, revisa el repositorio y confía el workspace solo si corresponde. En la sesión, verifica con `/skills list` y actualiza el descubrimiento con `/skills reload`. No uses `--consent` para omitir la confirmación salvo aprobación explícita.

Referencias del proveedor: [gestión de skills](https://geminicli.com/docs/cli/skills/) y [descubrimiento y confianza](https://geminicli.com/docs/cli/tutorials/skills-getting-started/).

## Modo B — runner local

Requiere que el propietario haya instalado y autenticado la CLI de proveedor que elija con el método admitido por ese proveedor. SSEC no instala proveedores ni agrega una API aparte; el proveedor puede requerir su propia autenticación y cuota. SSEC no cambia a otro proveedor ni inicia agentes al abrir la app.

```bash
python scripts/run_agents.py --help
```

`--execute` inicia procesos de CLI en snapshots desechables; requiere además `--accept-unmetered-cost`, porque el costo no se mide de forma fiable. Sin ambos, no se debe declarar una auditoría ejecutada. Los resultados del proveedor tampoco son aprobación independiente ni certificación científica.

## Aplicación de escritorio

El motor y la skill son utilizables sin PySide6. Si PySide6 ya está instalado y está aprobado para ese entorno:

```bash
python scripts/scientific_control_center_qt.py
python scripts/scientific_control_center_qt.py --project-root /ruta/al/proyecto --manifest workspace.json
```

La app inicia sin invocar un modelo. Sus acciones de auditoría muestran una confirmación antes de iniciar el runner. PySide6/Qt WebEngine no están fijados en un lockfile en este estado experimental; no se instalan automáticamente. WebEngine local es opcional y las vistas tienen fallback Qt nativo. El modo Tkinter del workspace permanece disponible si PySide6 no está instalado.

## Validación local sin proveedor

Requiere Python 3.11 o posterior. No llama a modelos ni acredita validez científica:

```bash
python scripts/validate_skill.py
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
python scripts/route_task.py examples/seir_desktop_audit.json
```

Para ver la app sin datos del usuario, abre `examples/sir_analysis_workspace_demo/workspace.json`. La demo usa un fixture sintético; su ajuste indica `STALLED`, y no acredita identificabilidad, incertidumbre o validez científica.

## Diagnóstico rápido

| Síntoma | Acción |
|---|---|
| La skill no aparece | Confirma el directorio de descubrimiento del proveedor y abre una sesión nueva; en Gemini usa `/skills list` y `/skills reload`. |
| Falta la CLI o la autenticación | El runner debe quedar `BLOCKED`; no hay fallback silencioso a otro proveedor. |
| Falta PySide6 | Usa el modo portable o la app Tkinter; no se instala PySide6 automáticamente. |
| No hay WebEngine | La vista usa el fallback nativo de Qt. |
| Auditoría termina sin revisión verificable | Conserva `NOT_APPROVED`; exit code 0 no basta para aprobar. |
| SIR o datos del usuario no disponibles | Marca simulación y análisis de ese caso `NOT_RUN`; no sustituyas los datos por el fixture sintético. |

## Estado de release

P1–P4 continúan experimentales y `v1.0` no está listo. La CI cubre parte de Windows/Linux; GUI Qt Linux, proveedor real desde la app, benchmarks de tres proyectos, sandbox efectivo y decisión de licencia siguen pendientes o `NOT_RUN`. Véase la [matriz de capacidades](docs/roadmap/FEATURE_MATRIX.md) y el [informe P3.18](docs/test-reports/p3-18-integrated-control-center-2026-11-04.md).
