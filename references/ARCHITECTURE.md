# Arquitectura actual y límites

SSEC tiene una superficie portable y una aplicación local opcional. Ambas comparten contratos; la GUI no es requisito para usar la skill.

| Límite | Componentes actuales | Responsabilidad |
|---|---|---|
| Skill portable | `SKILL.md`, `references/`, `scripts/route_task.py` | Instrucciones, selección de roles y contratos para Codex/Gemini. Un plan generado no demuestra ejecución. |
| Orquestación local | `scripts/run_agents.py`, `scripts/provider_runtimes.py`, `scripts/worktree_coordinator.py`, `scripts/development_runner.py` | Procesos de proveedor, snapshots/worktrees y evidencia experimental. Sin auto-merge ni certificación; aislamiento OS efectivo y subagentes nativos reales siguen `UNVERIFIED`/`NOT_RUN`. |
| Dominio científico | `scripts/scientific_core.py` | Contratos ODE/SIR, solver RK4 fijo y composición de los algoritmos numéricos disponibles. No importa Qt ni carga código Python de proyectos. |
| Workspace científico | `scripts/scientific_workspace.py`, `scripts/scientific_workspace_loader.py`, `scripts/scientific_workspace_view.py`, `scripts/scientific_workspace_qt.py` | Valida manifiestos versionados, lee recursos acotados con SHA-256 y presenta solo componentes registrados. Recursos de proyecto son datos inertes. |
| Aplicación escritorio | `scripts/scientific_control_center_qt.py` | Navegación de proyectos, agentes, experimentos, auditorías, código y resultados. Reutiliza el workspace Qt existente y delega en el runner local después de confirmación. |

```text
Codex / Gemini ── skill portable ───────────────┐
                                                ├── contratos y evidencia
App PySide6 ── workspace verificado ────────────┤
             └── runner local con confirmación ┘
```

## Reglas de dependencia

- El núcleo científico y los contratos son independientes de Tkinter, PySide6 y proveedores.
- La GUI llama APIs del motor por contratos versionados; no contiene ecuaciones específicas por proyecto.
- El loader comprueba digest/contención al leer recursos. Los digests declaran igualdad de bytes, no autenticidad de origen.
- Solo acciones registradas por el host pueden ejecutar callbacks aprobados; no se importan ni ejecutan módulos arbitrarios del proyecto o generados por agentes.
- Abrir la aplicación, validar un catálogo o construir un plan no invoca modelos.
- Los datos y decisiones canónicos requieren validación del coordinador/usuario; workers no elevan por sí mismos estados de review o aprobación.
- Las acciones con CLI de modelo requieren selección explícita, confirmación humana y aceptación de costo no medido.

## Núcleo científico disponible

`scientific_core` usa Python estándar y límites computacionales explícitos. La implementación actual incluye solver RK4 fijo, sensibilidad local por diferencias centrales, ajuste local acotado y contratos de observaciones/residuales. El helper del SIR declarativo compone esos algoritmos para tasas constantes. El workspace de demo contiene una fixture sintética reproducible, no el modelo/datos del usuario.

`CONVERGED`, `STALLED`, sensibilidad local y residuales describen resultados numéricos bajo los contratos implementados. No acreditan identificabilidad estructural/práctica, incertidumbre estadística, adecuación de datos ni validez científica. Incertidumbre no calculada conserva `NOT_CALCULATED`/`NOT_ASSESSED`.

## Decisiones y trabajo pendiente

- PySide6 es opcional y las dependencias no están fijadas en un lockfile; la instalación automática está prohibida.
- El Centro de Control muestra páginas para experimentos/código/resultados a partir de secciones registradas; no es un IDE general.
- El runner no es un sandbox de sistema operativo. El aislamiento de código generado por agentes, la GUI Qt en Linux, proveedor real desde la app, benchmark de tres proyectos y P4 siguen pendientes o `NOT_RUN`.
- Un ADR nuevo se justifica ante un cambio material de límites, ejecución, confianza o representación científica; no por cada vista o prueba.

Ver [instalación y modos de uso](../INSTALLATION.md), [workspaces científicos](SCIENTIFIC_WORKSPACES.md) y [matriz de capacidades](../docs/roadmap/FEATURE_MATRIX.md).
