# CODEX MASTER MISSION — Scientific Software Engineering Council (SSEC)

**Tipo:** misión ejecutable de ingeniería, auditoría y evolución de un repositorio existente  
**Idioma de trabajo:** español; código, APIs y nombres de archivos en inglés cuando resulte natural  
**Fecha de referencia:** 2026-11-02  
**Objetivo de versión:** SSEC v1.0, *únicamente cuando sus criterios de aceptación sean demostrablemente satisfechos*  
**Repositorio de trabajo:** https://github.com/Josch01/scientific-software-engineering-council  
**Repositorio científico complementario, de solo lectura:** https://github.com/Josch01/skill-investigacion-cientifica-rag  
**Versión observada al preparar este encargo:** `SKILL.md` declara `0.2.0-dev.4`; no asumir que sigue vigente: verificar `main`, historial, pruebas, issues y ramas al comenzar.

> **Encargo principal:** convierte SSEC en una skill y plataforma ligera de orquestación de ingeniería de software científico, modular, portable, verificable y mantenible. Debe diseñar, auditar, crear, corregir, probar y preparar software científico con especialistas seleccionados dinámicamente, y soportar ejecución con **solo Codex**, **solo Gemini** o **Codex + Gemini**. No confundas una definición de subagente, un proceso iniciado o un test exitoso con una auditoría rigurosa ni una liberación aprobada.

---

## 0. Autoridad, autonomía y límites

Eres el **Engineering Lead** responsable de planificar, implementar, refactorizar de modo acotado, probar, documentar y proponer integraciones. El objetivo no es escribir un plan sin ejecutar, sino producir avances verificables en código y pruebas. Empieza con auditoría del estado real y continúa hasta completar los incrementos posibles sin pedir aprobación rutinaria.

**Autorizado dentro del repositorio SSEC:** inspeccionar archivos, reproducir fallos, escribir pruebas, implementar módulos, utilizar ramas de trabajo, crear commits descriptivos y preparar pull requests. Si tienes un entorno con subagentes de contextos separados, úsalos cuando aporten una revisión o ejecución genuinamente distinta; no crees roles ficticios ni simules independencia.

**Requiere aprobación explícita del propietario:** merge a `main`, push a un repositorio público cuando publique datos o cambios externos no revisados, publicación de releases/tags estables, modificación del repositorio científico complementario, instalación o ejecución de skills externas, descargas de código ejecutable no auditado, exposición de proyectos privados a modelos externos, cambios de permisos, manipulación de credenciales, ejecución real con coste no medido, despliegues y cualquier decisión de licencia. Si el acceso Git ya incluye autorización de trabajo en rama, no lo interpretes como autorización irrestricta de `main`.

**Prohibiciones:** `git push --force` a ramas ajenas, borrar historial, inventar resultados de Windows/Linux/IDL, ocultar tests fallidos, quitar gates para pasar CI, desactivar sandbox para que una demo funcione, autoaceptar el propio código, extraer secretos, usar voto mayoritario como sustituto de evidencia técnica, y promover estimaciones numéricas a teoremas.

**No reescribas todo:** reutiliza y consolida el proyecto existente. Mantén interfaz compatible cuando sea viable, usa migraciones/versionado cuando no lo sea. Prefiere un núcleo pequeño con adaptadores y paquetes especializados sobre un monolito. No impongas bases de datos, microservicios o contenedores si no son necesarios para el caso.

Si hay restricciones importantes, registra el bloqueo con comando, salida, impacto, workaround seguro y estado `BLOCKED` / `NOT_RUN`. No presentes esas partes como terminadas.

---

## 1. Estado real a auditar antes de implementar

Verifica el repositorio, su rama principal, conflictos, issues, historial, workflows y estado de pruebas. Los siguientes elementos **existían** al preparar este encargo, pero su comportamiento debe auditarse, no asumirse:

- `SKILL.md` y `README.md` (hay indicios de versión/documentación parcialmente desincronizadas).
- `scripts/route_task.py`: router determinista por dominio, riesgo, interfaz, lenguaje y tarea.
- `scripts/prepare_agents.py`: definición de perfiles nativos y paquetes acotados por rol.
- `scripts/configuration.py` y `scripts/config_panel.py`: política y GUI Tkinter.
- `scripts/run_agents.py`: runner experimental de auditoría de solo lectura.
- `scripts/worktree_coordinator.py` y `scripts/development_runner.py`: ramas/worktrees, mailbox, planificación y ejecución experimental.
- `scripts/release_gate.py` y `scripts/validate_skill.py`: chequeos mecánicos/estructura.
- `references/`, `templates/`, `examples/`, `tests/` y `.github/workflows/validate.yml`.
- Issues #1–#5: orquestación, paquetes científicos, GUI/IDL, benchmarks/release, licencia/gobernanza.

Los CI previos de Windows/Linux/Python verificaban la base, **pero no demuestran integración real con cuentas Gemini/Codex, GUI visible, licencia IDL ni seguridad de aislamiento de procesos**. Distínguelos por separado.

### Paso obligatorio de entrada (fase P0)

1. Inventariar módulos, llamadas, APIs públicas, pruebas, archivos de configuración y flujos de permisos.
2. Ejecutar los tests existentes sin alterarlos y conservar salida, versiones y SHA.
3. Generar `docs/audits/BASELINE_AUDIT.md` con fallos demostrables, riesgos, severidad, ubicación y test de reproducción.
4. Detectar contradicciones entre README, `SKILL.md`, GUI y comportamiento efectivo. Precisar el alcance del runner actual y los subagentes que realmente se invocan.
5. Construir `docs/architecture/ADR-001-runtime-boundaries.md`: núcleo, adaptadores Codex/Gemini, coordinador, estado, evidencia, GUI y módulos científicos; detallar alternativas y tradeoffs.
6. Publicar una matriz `FEATURE_MATRIX.md` con estados `IMPLEMENTED | VERIFIED | EXPERIMENTAL | NOT_RUN | BLOCKED | PLANNED`.
7. Ordenar el backlog según **riesgo y dependencia real**, no por número de archivos o cantidad de agentes.

**Gate P0:** no iniciar una reescritura grande ni declarar ninguna fase cerrada antes de establecer el baseline.

---

## 2. Comportamiento del producto que debes alcanzar

### 2.1 Selección del proveedor por tarea (requisito absoluto)

- `codex`: solo Codex como agente principal; usa subagentes de Codex cuando su runtime real lo soporte.
- `gemini`: solo Gemini como agente principal; usa subagentes nativos de Gemini cuando su runtime real lo soporte.
- `both`: ambos pueden ejecutar trabajos diferentes con contratos explícitos. No se requiere instalar el segundo proveedor si el usuario eligió uno solo.
- `auto` puede proponerse más adelante, pero **nunca debe ignorar una elección explícita** ni cambiar de proveedor sin avisar.
- El router selecciona **especialidades según las obligaciones**, no invoca siempre a todos. Los perfiles son una descripción de capacidades, no una excusa para aumentar gasto.

No asumas que todas las versiones de CLI tienen las mismas opciones. Obtén versiones reales con `--version`/`--help` y consulta documentación oficial vigente; usa adaptadores con detección de capacidades, validación, errores claros y pruebas de contrato. No confundas *subagentes nativos del proveedor* con *procesos CLI independientes*.

### 2.2 Especialidades por demanda

Catálogo extensible (no todas activas siempre): `software_architect`, `implementation_engineer`, `numerical_analyst`, `mathematical_model_specialist`, `differential_algebra_specialist`, `dynamical_systems_specialist`, `identifiability_specialist`, `optimization_ml_engineer`, `data_engineer`, `gui_engineer`, `idl_engineer`, `software_auditor`, `security_reviewer`, `independent_reviewer`, `release_engineer`.

El planner produce un **DAG de tareas** con `role`, `reason`, `risk`, `inputs`, `outputs`, `dependencies`, `file_ownership`, `tests`, `required_reviewers` y `acceptance_criteria`. No crees un agente si la tarea no justifica su coste. Cada worker recibe un `Task Packet` *mínimo, reproducible e inmutable para esa revisión* y devuelve un `Worker Result` tipado. Revisión adversarial en contexto distinto cuando el runtime lo permita; si no, etiqueta la independencia real.

### 2.3 Modos de trabajo

`AUDIT | BUILD | DEBUG | REFACTOR | OPTIMIZE | MIGRATE | GUI | IDL | RELEASE`.

En `AUDIT` por defecto **solo lectura**; en `BUILD` cambios solo en rama/worktree aislado y bajo permisos efectivos, no simplemente instrucciones. `RELEASE` exige auditoría, evidencias y autorización humana para pasos irreversibles o públicos.

### 2.4 Arquitectura y evolutividad

Separar como mínimo:

`task specification → router/planner → runtime adapter → worker execution → artifact/evidence registry → independent audit → integration gate → human decision`.

Diseñar interfaces tipadas para `AgentRuntime`, `TaskPacket`, `WorkerResult`, `AuditReport`, `RunEvent`, `EvidenceRecord` y `ReleaseDecision`. Facilitar añadir nuevos providers, nuevos solvers o nuevos perfiles GUI/ML sin cambiar el núcleo. Preferir dependencias mínimas y plugins/adaptadores opcionales. Mantener schemas versionados y migración explícita.

---

## 3. Fases a implementar y sus criterios de cierre

### P1 — Completar el orquestador operativo (cerrar issue #1)

1. Implementar interfaz `AgentRuntime` con `discover_capabilities`, `launch`, `stream_or_collect`, `cancel`, `timeout`, `status`, `cleanup`. Dos adaptadores, Codex y Gemini, más `FakeRuntime` para pruebas.
2. Planificar por DAG y tandas con semáforos reales, manejo de crash/reinicio, idempotencia, retries acotados, cancelación y protección ante ejecuciones duplicadas.
3. Ramas/worktrees exclusivos por trabajador, revisión de conflictos de ficheros, control de archivos autorizados, hashes de base/input/resultados, detección de base obsoleta, rollback/cleanup explícito y no destructivo.
4. Mailbox/event log estructurado con schema y estados reproducibles. El orquestador es el único que altera el estado canónico; un worker no puede fabricar `REVIEW_ACCEPTED`, `TEST_PASS` ni `RELEASE_READY` simplemente escribiendo JSON.
5. Ejecución secuenciada `implementer → deterministic tests → reviewer in separate context → fix loop → acceptance decision`. Evitar dependencia del veredicto previo para el primer juicio independiente.
6. Revisión de cambios real (diff, tests, ownership, referencias a commits), detección de contradicciones y paso a `NEEDS_HUMAN` si los conflictos no se resuelven.
7. Separar aislamiento de contexto, aislamiento de directorio y aislamiento de sistema operativo. Nunca prometer un sandbox que el proveedor o el host no proporcionan. Verificar comportamiento seguro con rutas UNC/Windows, enlaces simbólicos, procesos hijos, interrupción y logs.
8. Prohibir merge automático al principio; ofrecer propuesta verificable de PR con evidencia, conservando la aprobación final en el humano.

**Gate P1:** tests de worktrees, inyección de fallos, reinicio/recuperación, conflictos, timeouts, cancelación, simulaciones Codex-only/Gemini-only/both, reviewer no-autorizado, ausencia de CLIs y ausencia de credenciales. CI no llama proveedores pagos. Prueba real end-to-end opt-in con cada CLI disponible, nunca sustituida por mocks ni reportada como ejecutada si falta el entorno.

### P2 — Biblioteca científica modular (issue #2)

Agregar especializaciones **bajo demanda**, no código científico genérico obligatorio:

- Numéricos: ODE/PDE, rigidez, tolerancias, error, convergencia, condiciones iniciales, invariantes, positividad, units/escala, solución de referencia y sensibilidad.
- Álgebra diferencial y cálculo simbólico: dominios, supuestos, operaciones exactas, ramas, divisiones y conjuntos excepcionales.
- Dinámica: estabilidad, Floquet, mapas estroboscópicos, Lyapunov, bifurcación, diferencia entre simulación y prueba rigurosa.
- Identificabilidad: estructural/global/local vs práctica, simetrías/fibras, perfil de verosimilitud, sensibilidad, correlación y condiciones de parámetros/datos. Evitar `RMSE bajo ⇒ unicidad`.
- Optimización: GA, DE, ACOR, CMA-ES y otros según el problema; restricciones, evaluaciones, seeds, baselines, múltiples ejecuciones, trazas, pruebas de regresión y comparación estadística.
- ML: PyTorch/JAX/XGBoost cuando proceda, splits sin leakage, cross-validation, seeds, incertidumbre, ablation, inferencia reproducible; SHAP como explicación de un predictor, no prueba causal o de identificabilidad por sí misma.
- Ciencia de datos y decisiones: calidad, procedencia, contrato de dataset, métricas y riesgos de decisiones.

La skill científica existente puede consultarse mediante un **adaptador opcional de solo lectura**: `scientific-research-rag-council`, en https://github.com/Josch01/skill-investigacion-cientifica-rag. Reutiliza sus protocolos/certificados **solo si están disponibles, son aplicables y su procedencia está confirmada**. No importes su repositorio entero por defecto, no lo edites y no cambies sus estados epistemológicos. Mantén `SOFTWARE_VALIDITY`, `NUMERICAL_VALIDITY` y `SCIENTIFIC_VALIDITY` como campos y gates distintos.

**Gate P2:** casos científicamente significativos con valores de referencia, tests de precisión/convergencia, ejemplos que deben fallar, resultados reales y advertencias correctas. Los tests de integración numérica ordinaria no demuestran teoremas.

### P3 — Panel de supervisión y GUI científica (issue #3)

1. Evolucionar el panel de configuración existente sin perder portabilidad. Elegir una tecnología de GUI justificada (mantener Tkinter si basta; usar PySide6 solo si la funcionalidad requiere su coste/dependencias). No confundir GUI del **supervisor SSEC** con templates GUI para aplicaciones científicas de usuarios.
2. Supervisor SSEC: selección de proveedor y agentes, cola DAG, árbol de tareas, estado por proceso, progreso, logs filtrados por rol, artefactos, diferencias, auditorías y bloqueos; Cancel/Retry con semántica comprobable.
3. No bloquear el hilo de UI. Incluir modos sin pantalla/headless y fallbacks claros; persistencia de configuración y restauración tras fallos.
4. Crear preset para aplicaciones científicas de Windows/Linux: núcleo desacoplado de la UI, ejecución larga en worker, cancelación/progreso, gráficos, import/export, errores visibles y tareas científicas reproducibles.
5. IDL = **Interactive Data Language (NV5)** de acuerdo con los archivos actuales. Añadir un puente IDL/Python opcional con pruebas de dtypes, shapes, orden en memoria, NaN, excepciones y compatibilidad versionada. Si no existe instalación/licencia IDL, marcar `NOT_RUN` y dar instrucciones de validación, no inventar un `PASS`.
6. Empaquetado reproducible y smoke tests de Windows/Linux: un chequeo Tkinter headless no equivale a una prueba visual real.

**Gate P3:** E2E del supervisor y pruebas de interacción de GUI donde haya escritorio disponible, tests headless en CI, logs de fallos/cancelación, smoke tests cruzados; reporte explícito de IDL si no hay licencia.

### P4 — Calidad, catálogo confiable y release 1.0 (issue #4)

1. Tests estáticos, de tipos, estilo, secretos, dependencias, vulnerabilidades, regresión, propiedad, integración, procesos concurrentes, seguridad de CLI y compatibilidad de schemas; versiones de librerías fijadas con política de actualización.
2. Catálogo opt-in de extensiones/skills: fuente original, maintainer, licencia, checksum/commit fijo, capacidades, permisos, revisión, versión y rollback. **Nunca autoejecutar código descargado** ni instalar skills de terceros sin permiso.
3. Benchmarks instrumentados sobre al menos tres proyectos de referencia: un bug numérico conocido, una GUI/concurrencia defectuosa y un problema de ML/datos o identificabilidad. Reportar defectos encontrados, falsos positivos, cobertura real, coste cuando pueda medirse y limitaciones.
4. Revisión adversarial de la propia skill: prompt injection en `Task Packet`, rutas maliciosas, secrets, symlinks, archivos enormes, `git` dirty, base movida, takeover del mailbox, falso `PASS`, proveedor ausente, rate limiting, context overflow, cancelación a mitad de escritura y procesos huérfanos.
5. Documentación de arquitectura, APIs, perfiles, instalación/actualización, troubleshooting, ejemplos completos y guía de contribución.
6. Revisar licencia y política de contribuciones (**issue #5**): está pendiente decisión del dueño. Proponer opciones y riesgos; no crear una licencia legalmente vinculante por suposición.
7. Preparar release candidate (`v1.0.0-rc1`) solo si hay matriz de evidencia; **no publicar tag estable ni release ni merge a main sin autorización**. Un RC puede mantener estado `CONDITIONAL` / `BLOCKED` para plataformas que no se probaron.

**Gate P4:** reporte completo de cumplimiento, auditoría de seguridad independiente, regresión contra baseline, evidencia de reproducibilidad y decisión humana sobre licencia y release.

---

## 4. Matriz obligatoria de pruebas

Conservar resultados por combinación, no resumir como “todo pasó” si solo hubo simulación:

| Escenario | Evidencia esperada |
|---|---|
| Solo Codex | selección de roles, no invocación Gemini, trabajo acotado, trazas y revisor |
| Solo Gemini | selección de roles, no invocación Codex, trazas y revisor |
| Ambos proveedores | contratos cruzados, IDs correlacionados, sin carreras ni asunción de agente único |
| Ninguna CLI instalada | `BLOCKED` explícito, sin falsas ejecuciones |
| Proyecto Git dirty | bloqueo de escritura o ruta segura e informada |
| Dos workers alteran mismo archivo | conflicto detectado, no merge silencioso |
| Agente falsifica `REVIEW_ACCEPTED` o `TEST_PASS` | gate impide elevar estado sin evidencia verificada |
| Timeout/cancelación/crash | terminación de procesos hijos, recuperación y limpieza controlada |
| Ruta simbólica o fuera del proyecto | rechazo bajo política sin escape de escritura |
| Archivo con credenciales / datos privados | no exportación silenciosa ni logs públicos |
| Windows / Linux | CI y pruebas de rutas/procesos por plataforma; GUI real donde sea posible |
| GUI con cómputo largo | UI responde, progreso y cancelación, sin bloqueo del hilo |
| IDL sin licencia | `NOT_RUN`, ruta de validación declarada |
| Validación científica | casos numéricos y teóricos separados, sin sobreafirmaciones |
| Revisión independiente | auditor sin compartir juicio previo, evidencia y limitación de independencia |
| Fuente externa y actualización | versión fijada, auditoría previa, aprobación antes de instalar |
| Proceso con código 0 sin pruebas | no `RELEASE_APPROVED` |

Ejecutar `python scripts/validate_skill.py`, `python -m unittest discover -s tests -v`, pruebas de proyecto apropiadas y CI multiplataforma. Añadir nuevos comandos reproducibles según el stack real. Para tests de CLI externos con dinero/credenciales, usar `opt-in` y nunca ejecutarlos implícitamente en CI público. Registrar cada ejecución con `commit_sha`, OS, versión Python/CLI, command, exit code, test count, log path, timestamp y hash si aplica.

---

## 5. Política de entrega y documentación

**Al iniciar:** revisar `/README.md`, `/SKILL.md`, `/references/` y los scripts existentes; no fiarse de esta misión como descripción exhaustiva de la versión nueva.

**Para cada fase:** producir cambios pequeños en ramas/PRs separados, tests que demuestren el fallo o comportamiento antes/después, riesgos y ADR si cambia arquitectura. Revisores con contexto distinto cuando el runtime lo permita. Es válido dividir una fase en varias PRs para mantenerlos auditables.

**Artefactos duraderos recomendados:**

- `docs/audits/BASELINE_AUDIT.md` (hallazgos iniciales con evidencias).
- `docs/architecture/ADR-001-runtime-boundaries.md` y más ADR si procede.
- `docs/roadmap/FEATURE_MATRIX.md` con entregables/estados y compromisos.
- `docs/protocols/TASK_PACKET_SCHEMA.md`, `WORKER_RESULT_SCHEMA.md`, `AUDIT_REPORT_SCHEMA.md` o schemas JSON equivalentes.
- `docs/test-reports/<id>.md` para evidencia por plataforma y proveedor.
- `docs/security/THREAT_MODEL.md` (trust boundaries y ataques).
- `docs/release/RELEASE_CANDIDATE_CHECKLIST.md`.

**Informe final obligatorio:**

```
BASE_COMMIT:
FINAL_COMMIT/PRs:
PHASES: [P0, P1, P2, P3, P4] con estados por fase
IMPLEMENTED:
TESTED: (comandos, entornos y resultados reales)
NOT_RUN / BLOCKED:
SECURITY_FINDINGS:
SCIENTIFIC_BOUNDARY:
REGRESSIONS / BREAKING_CHANGES:
EVIDENCE_REFERENCES:
RELEASE_STATUS: DRAFT | PARTIAL | CONDITIONAL | RC_READY | HUMAN_APPROVAL_REQUIRED
REMAINING_RISKS:
OWNER_DECISIONS_REQUIRED:
```

No denomines `CERTIFIED` una prueba de software sin certificado del alcance técnico; no denomines `SCIENTIFICALLY_CERTIFIED` una simulación. Si una fase no se termina, entrega el estado y los PRs útiles con fallos honestamente reportados, no una promesa de trabajo en segundo plano.

## 6. Primera instrucción ejecutiva

**Empieza ahora por P0** en una rama nueva a partir de `main` limpio. Reproduce los tests actuales, audita las lagunas reales de la fase 2 y crea el roadmap de implementación basado en evidencias. Una vez documentado el baseline, implementa P1 empezando por **verificación de resultados y auditoría automática**, porque la infraestructura actual tiene worktrees y procesos, pero todavía no hay integración confiable de evidencias. Procede fase por fase sin esperar nuevas instrucciones salvo decisiones reservadas al propietario. No publiques automáticamente la versión 1.0.

**Criterio rector:** `PLAN ≠ EXECUTION ≠ VERIFICATION ≠ SCIENTIFIC_CERTIFICATION ≠ HUMAN_RELEASE_APPROVAL`.