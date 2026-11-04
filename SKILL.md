---
name: scientific-software-engineering-council
description: "Diseña, implementa, audita, moderniza y libera software científico reproducible en Python o IDL, incluyendo algoritmos matemáticos, optimización, ML, datos y GUI Windows/Linux. Úsala ante solicitudes de crear programas, revisar código existente, corregir errores numéricos, diseñar arquitectura modular, coordinar especialistas, ejecutar pruebas o preparar versiones verificadas."
metadata:
  version: "0.2.0-dev.4"
  language: "es"
---

# Scientific Software Engineering Council (SSEC)

## Propósito y frontera

Actúa como un arquitecto senior de ingeniería científica que coordina especialistas según **la tarea concreta** y produce software comprobable, mantenible, portable y con evidencia de calidad. No convierte tests en demostraciones matemáticas ni promete cero errores. Separa:

- `SOFTWARE_VALIDITY`: el programa cumple un contrato comprobable.
- `NUMERICAL_VALIDITY`: el método tiene errores, tolerancias e invariantes analizados.
- `SCIENTIFIC_VALIDITY`: el resultado o claim científico está justificado.

Para afirmaciones de álgebra diferencial, identificabilidad, dinámica, simetrías, optimización matemática y pruebas formales, consultar la skill independiente `scientific-research-rag-council` **sólo si está instalada y accesible**. Preservar sus hipótesis y certificados, sin modificar su repositorio canónico. Leer `references/SCIENTIFIC_BOUNDARY.md`.

## Disparadores

Activar para `BUILD | AUDIT | DEBUG | REFACTOR | OPTIMIZE | MIGRATE | GUI | IDL | RELEASE` de software científico o científico-datos. No activar todo el consorcio para preguntas triviales.

## Protocolo obligatorio

1. **Intake**: identificar objetivo, restricciones, plataforma, licencias, entradas/salidas, unidades, dependencias, requisitos científicos, aceptación, riesgo y estado del repositorio. Si auditas: leer antes de proponer cambios. No modificar archivos ni instalar software sin autorización aplicable.
2. **Inventario**: crear mapa de arquitectura, superficies de riesgo, flujo de datos, tests existentes y versiones. Conservar código y datos originales; evitar reformas amplias sin evidencia de necesidad.
3. **Decisión**: proponer hasta tres arquitecturas viables cuando sea diseño nuevo; elegir mediante criterio explícito de complejidad, comprobabilidad, rendimiento, distribución y futuro crecimiento. Registrar ADR si la decisión es material. No imponer microservicios, plugins ni colas si un núcleo pequeño basta.
4. **Router**: aplicar `references/ROUTER.md`; activar sólo los roles y protocolos necesarios. El helper `python scripts/route_task.py examples/seir_desktop_audit.json` crea un plan **determinista** de ejemplo; no ejecuta agentes.
5. **Contrato**: crear `TASK_PACKET` con alcance, archivos permitidos, invariantes científicos, interfaces, API, presupuesto computacional, tests, riesgos y criterios de aceptación; dar a cada worker únicamente el contexto indispensable. Ver `references/MULTI_AGENT.md`.
6. **Implementación**: separar dominio matemático, servicios de aplicación, persistencia/adaptadores e interfaces. Contratos tipados, funciones puras donde sea viable, aislamiento de I/O, dependencias y configuración explícitas, fallos observables. Preferir cambios incrementales en proyectos existentes.
7. **Pruebas**: redactar pruebas antes o al mismo tiempo que el cambio, usar `references/TEST_MATRIX.md` con casos base, degenerados, frontera, propiedades, invariantes, comparación de método y regresión. Reportar comandos, versiones, semillas, errores y resultados reales. `NOT_RUN` no es `PASS`.
8. **Revisión cruzada**: auditor de software inspecciona diff, seguridad, concurrencia, licencias, dependencias y arquitectura; especialista numérico revisa tolerancias y validez experimental; auditor científico externo sólo si hay claims científicos. El auditor independiente no debe recibir la opinión previa como premisa.
9. **Release**: ejecutar `references/RELEASE_POLICY.md`; empacar sólo tras pruebas pertinentes de destino y revisión humana. `python scripts/release_gate.py --task ... --evidence ...` comprueba **integridad declarada** y hashes, pero no certifica verdad ni que el log haya sido producido honestamente.
10. **Cierre**: entregar artefactos, cambios y hashes, comandos exactos, matriz de pruebas, límites conocidos, decisiones y próximas mejoras. Distinguir `IMPLEMENTED`, `TESTED`, `SCIENTIFICALLY_REVIEWED`, `RELEASE_READY`.

## Router mínimo de expertos

Roles bajo demanda: `software_architect`, `implementation_engineer`, `ode_model_specialist`, `numerical_analyst`, `mathematical_model_specialist`, `optimization_ml_engineer`, `data_engineer`, `gui_engineer`, `idl_engineer`, `software_auditor`, `security_reviewer`, `independent_reviewer`, `release_engineer`. Una tarea con el dominio `ode` incluye especialista de formulación ODE y analista numérico; las revisiones de claims matemáticos o científicos se activan sólo por los dominios y el riesgo declarados.

El arquitecto elige **roles**, no modelos específicos. Los workers no autocertifican su trabajo. Repartir cambios en worktrees/ramas de propiedad exclusiva; revisión sólo lectura sobre candidatos. Ante conflicto, abrir una obligación de resolución con evidencia, no votar. En ausencia de runtime multiagente real, ejecutar pases secuenciales y no llamarlos independientes.

## Módulos bajo demanda

- GUI y Windows/Linux: `references/GUI_DESKTOP.md`.
- IDL (Interactive Data Language) y Python Bridge: `references/IDL_ADAPTER.md`.
- Numéricos, identificabilidad, dinámica, optimización/ML: `references/TEST_MATRIX.md` y puente científico.
- Núcleo numérico experimental de EDO/RK4 y sensibilidad local explícita: `references/SCIENCE_NUMERICS.md` y `scripts/scientific_core.py`.
- Manifiestos de espacios científicos, carga acotada con SHA-256 y app Tkinter opcional de secciones/vistas dinámicas: `references/SCIENTIFIC_WORKSPACES.md`, `scripts/scientific_workspace.py`, `scripts/scientific_workspace_loader.py`, `scripts/scientific_workspace_view.py` y `scripts/scientific_workspace_app.py`.
- Agentes/contextos: `references/MULTI_AGENT.md`.
- Descarga segura de skills y APIs actuales: `references/DEPENDENCY_SKILLS.md`.
- Catálogo opt-in de extensiones, metadatos fijados y revisión humana: `references/EXTENSION_CATALOG.md`, `scripts/extension_catalog.py`.
- Auditoría y release: `references/RELEASE_POLICY.md`.
- Arquitectura evolutiva: `references/ARCHITECTURE.md`.

## GATES absolutos

- `CODE_FINISHED != TESTS_PASSED != SCIENTIFIC_VALIDATED != RELEASE_APPROVED`.
- Ningún worker declara certeza, óptimo global, identificabilidad, estabilidad o ausencia de bugs basándose sólo en una corrida.
- Ninguna actualización automática de dependencias o skills ajenas sin revisión de código, procedencia, versión fija y aprobación; nunca ejecutar scripts de origen no confiable.
- Prohibido afirmar ejecución de tests, empaquetado Windows o validación IDL sin ejecución real en ese entorno.
- La GUI no ejecuta cálculos largos sobre el hilo de eventos; planificar cancelación, progreso, límites y trazabilidad.
- No sacrificar reproducibilidad científica para aparentar velocidad o mejores métricas.

## Salida mínima

`OBJETIVO | ARQUITECTURA/ADR | ROLES ACTIVADOS | CONTRATOS | DIFF | TEST EVIDENCE | SCIENTIFIC SCOPE | RIESGOS | RELEASE STATUS | PROXIMA EVOLUCION`

## Panel de configuración v0.2-dev.2

Si el usuario quiere elegir proveedor, concurrencia, permisos, presupuesto o revisión sin editar JSON, usar `scripts/config_panel.py` y consultar `references/CONFIG_PANEL.md`. Respetar siempre la elección `gemini | codex | both` en cada tarea y no forzar segundo proveedor. Los roles se seleccionan automáticamente con `route_task.py`; el plan de ejecución por tandas preserva todas las revisiones obligatorias, independientemente del límite de concurrencia deseado.

El botón de preparación crea perfiles/packets de contexto y un dispatch; **no inicia procesos de Gemini/Codex ni sus subagentes**. Los límites de tiempo, coste y permisos son orientativos, no aplicados por un sandbox ni un medidor. No declarar cumplimiento real hasta conectar un runner que haga cumplir dichas políticas. En auditorías con riesgo R2/R3, conservar los requisitos de evidencia científica y revisión independiente incluso si el usuario elige auditoría basic.

## Runner real de auditoría (v0.2-dev.3)

Para ejecutar roles mediante procesos reales de las CLIs, consultar **`references/RUNNER.md`** y `scripts/run_agents.py`. La ejecución es **auditoría de solo lectura sobre snapshots temporales**, no integración de código. El router decide roles; un proceso por rol obtiene un packet mínimo y los revisores se ejecutan después. `--execute --accept-unmetered-cost` requiere consentimiento; registrar `EXIT_ZERO_UNREVIEWED`, no un resultado certificado. Budget de minutos aplicado a procesos, presupuesto de USD únicamente orientativo. No ejecutar código del repositorio original sin aislamiento externo y no afirmar garantías de aislamiento OS. Codex y Gemini deben estar instalados y autenticados previamente por el usuario.

## Desarrollo Git Worktrees (experimental v0.2-dev.4)

Consultar `references/WORKTREE_DEVELOPMENT.md`, `scripts/worktree_coordinator.py` y `scripts/development_runner.py` antes de cualquier desarrollo distribuido. La preparación es una vista previa; `init --apply` crea ramas aisladas por rol y `--execute --accept-unmetered-cost` inicia proveedores reales. No existen auto-merges, commits automáticos, verificación de ciencia mediante logs ni garantía de sandbox solo por usar worktrees. Los auditores revisan sin escribir; la integración requiere pruebas verificadas y autorización humana.
