# Auditoría baseline SSEC

**Fecha:** 2026-11-02<br>
**Propósito:** P0; estado reproducible antes de cambios de producto.<br>
**Repositorio:** [Josch01/scientific-software-engineering-council](https://github.com/Josch01/scientific-software-engineering-council)<br>
**Commit base:** `908e35637518c4c1ab56c1f75138d194cadd3938` (`main`)<br>
**Rama de auditoría:** `codex/p0-baseline-audit-phase2`
**Estado inicial:** checkout limpio. Los artefactos añadidos después de la captura son este informe, ADR-001, la matriz de funciones y los registros de `docs/test-reports/`; no se modificaron scripts ni tests.

## Resumen ejecutivo

SSEC ya contiene un router determinista, preparación de perfiles, un panel Tkinter, un runner local de auditoría de solo lectura y un experimento de desarrollo con worktrees y procesos CLI. Son incrementos útiles y explícitamente limitados. No hay todavía un consorcio que complete el ciclo implementador → pruebas verificadas → revisor independiente → decisión de aceptación: el runner de desarrollo no ejecuta pruebas ni reviewers; el mailbox y el gate consumen declaraciones por rol; el gate de evidencia de release valida hashes y rutas, pero no la procedencia de una ejecución.

La brecha científica de fase P2 es mayor: existen reglas de enrutamiento, guías y ejemplos de tareas, pero no paquetes científicos ejecutables, oráculos numéricos ni pruebas que establezcan resultados científicos. Ningún test actual demuestra convergencia, precisión, identificabilidad, estabilidad, optimalidad o una afirmación matemática.

La suite baseline en este host Windows/Python 3.14 terminó con **45 tests y 2 errores de entorno**: dos pruebas intentaron crear symlinks sin el privilegio de Windows requerido (`WinError 1314`). Las otras 43 pruebas pasaron. En paralelo, GitHub Actions sí tiene una ejecución `push` exitosa para este SHA exacto: cuatro jobs Windows/Ubuntu × Python 3.11/3.12 completaron en `success`. Son entornos distintos; el CI verde no convierte los errores locales de Python 3.14 en PASS.

## Identidad del entorno y ejecución

| Campo | Valor |
|---|---|
| SHA de código probado | `908e35637518c4c1ab56c1f75138d194cadd3938` |
| OS | Microsoft Windows 10.0.26300 |
| Python | 3.14.0 |
| Git | 2.49.0.windows.1 |
| Inicio de captura de entorno | `2026-11-02T18:04:29.6898526Z` |
| Paquetes instalados para la auditoría | Ninguno |

Los comandos y salidas completas están guardados en `docs/test-reports/`. Los hashes SHA-256 cubren los logs tal como fueron guardados por PowerShell; `.gitattributes` conserva sus bytes sin normalización EOL, y `environment.txt` registra el SHA y las versiones. El log de unittest registra `Ran 45 tests in 75.590s` y `FAILED (errors=2)`. El [manifest JSON](../test-reports/baseline-908e356-2026-11-02-manifest.json) registra argv, exit code, conteo de tests, resultado, horas UTC de creación/cierre, ruta y hash por comando, además de los IDs y conclusiones de jobs remotos.

| Comando | Exit code | Resultado observado | Log / SHA-256 |
|---|---:|---|---|
| `python scripts/validate_skill.py` | 0 | Estructura válida; el propio comando aclara que no garantiza corrección de software/ciencia. | [`baseline-…-validate-skill.log`](../test-reports/baseline-908e356-2026-11-02-validate-skill.log) · `FE6296FD79B50E9C53053C744957702F9BC53269FB51764FC8907A22440C7E78` |
| `python -m unittest discover -s tests -v` | 1 | 45 tests; 43 `ok`, 2 `ERROR` durante creación de symlink. | [`baseline-…-unittest.log`](../test-reports/baseline-908e356-2026-11-02-unittest.log) · `3BB88639A5E812ABD8AD8EC7BF7F10CDC04F6BA2E4385EC306E97D13C01482A8` |
| `python scripts/route_task.py examples/seir_desktop_audit.json` | 0 | Emite plan determinista; indica `SINGLE_CONTEXT_SEQUENTIAL` y no ejecución de agentes. | [`baseline-…-router-smoke.log`](../test-reports/baseline-908e356-2026-11-02-router-smoke.log) · `58CF6F365F6C00E57FB82533974CD5DD27C9B76B70DE67DC0CF14C68D798C344` |
| `python scripts/config_panel.py --check` | 0 | Modelo headless válido; no abrió ni probó una ventana. | [`baseline-…-config-panel-check.log`](../test-reports/baseline-908e356-2026-11-02-config-panel-check.log) · `F0A185FE38A62B41767046FC377B9B2E6F10586128679F7B23F66AF86D1DF09C` |
| `python scripts/release_gate.py --task examples/seir_desktop_audit.json --evidence examples/release_evidence_not_run.json` | 2 (esperado) | Gate `BLOCKED` por evidencia ausente; comportamiento negativo correcto. | [`baseline-…-release-gate-not-run-example.log`](../test-reports/baseline-908e356-2026-11-02-release-gate-not-run-example.log) · `B637A006F0D73814965A84080FC6B44BF613A55BD840F8CACA03A079E91A8CB0` |
| `codex --version`; `codex exec --help` | 0; 0 | `codex-cli 0.166.0-alpha.5.1`; help lista `--sandbox`, `--json`, `--skip-git-repo-check` y `--cd`. | [`version`](../test-reports/baseline-908e356-2026-11-02-codex-version.log) · `757DA76996755D1184FC47EF1CF5530C61EF15A8DCF90F8DB5D2D20E60E69276`; [`help`](../test-reports/baseline-908e356-2026-11-02-codex-exec-help.log) · `FF5A00D7F3926A45D9B58EC703A45D6972B1664C0FA465156C48577BB4CEEAF4` |
| `gemini --version`; `gemini --help` | 0; 0 | Gemini CLI `0.64.0`; help lista `--sandbox`, `--approval-mode`, `--output-format` y `--prompt`. | [`version`](../test-reports/baseline-908e356-2026-11-02-gemini-version.log) · `BA800D24CE0D5479E0531A2F5441D48833F2871E4A5A4C2B606DB58606E35B5D`; [`help`](../test-reports/baseline-908e356-2026-11-02-gemini-help.log) · `7E15A18C398C2AB4FBC80FC552F41B901D890DF1B361E5782AFFCF603AAA0BB0` |

Los dos errores fueron `test_configuration.ConfigTests.test_symlink_refusal` (línea 51) y `test_provider_modes.TestModes.test_symlink` (línea 62). Ambos fallaron en `Path.symlink_to` con `WinError 1314`; las aserciones que verifican el rechazo de symlink no llegaron a ejecutarse. Se registran como limitación de verificación de este entorno, no como fallo de la validación de producto. Linux y Python 3.11/3.12 quedan `NOT_RUN` en esta sesión.

Los CLI `codex` y `gemini` están presentes. Se consultó únicamente versión y ayuda; no se ejecutaron prompts, modelos, autenticación ni llamadas con coste. Las pruebas end-to-end reales de cada proveedor continúan `NOT_RUN`. La ayuda confirma opciones presentes en esta instalación; las capacidades de subagentes y permisos efectivos requieren una prueba de contrato/ejecución aparte. Referencias oficiales consultadas: [Codex CLI](https://learn.chatgpt.com/docs/cli/reference), [subagentes Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Gemini CLI](https://geminicli.com/docs/cli/cli-reference/) y [subagentes Gemini](https://geminicli.com/docs/core/subagents/).

## Repositorio, historial, CI e issues

- `main` apuntaba a `908e356` (`docs: add Codex completion mission and auditable SSEC v1.0 roadmap`); el commit padre es `46c82a4` (`feat: role-owned worktrees and handoff protocol`). La rama P0 se creó desde el checkout limpio de ese `main`.
- Ramas remotas observadas: `main`, `feature/config-panel-v0.2-dev2`, `feat/audit-runner-v020dev3` y `feature/isolated-worktrees-and-handoffs`. No hay tags.
- Pull requests #6, #7 y #8 están cerrados/mergeados. Sus descripciones reconocen, respectivamente, que el panel no lanza agentes; el runner no ejecutó proveedores reales; y worktrees, mailbox y logs no proveen sandbox de SO ni procedencia autenticada.
- Issues [#1–#5](https://github.com/Josch01/scientific-software-engineering-council/issues) siguen abiertas. Cubren consorcio/runtime, módulos científicos, GUI/IDL, calidad/benchmarks/release y licencia/gobernanza; #5 reserva explícitamente al dueño la elección de licencia.
- `.github/workflows/validate.yml` fija las acciones por SHA y configura Ubuntu/Windows × Python 3.11/3.12. Ejecuta validación estructural, unittest, router smoke y check headless.
- La ejecución `push` [#41496442300](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41496442300) del SHA `908e356` concluyó `success` el 2026-11-02 a las 18:00; sus cuatro jobs Windows/Ubuntu × Python 3.11/3.12 y los pasos de tests, router y panel headless completaron en `success`. GitHub muestra cuatro warnings y dos notices: los actions fijados a revisiones que apuntan a Node.js 20 se ejecutan con Node.js 24, y `ubuntu-latest` recibió un aviso de migración de imagen. El run no presenta artifacts descargables; el conteo local de 45 tests corresponde únicamente al host Python 3.14.
- Los cuatro jobs verdes de PRs anteriores [#6](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41489290191), [#7](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41491357337) y [#8](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41494925474) son evidencia histórica en otros SHAs.
- El repositorio no trae `pyproject.toml`, `setup.cfg`, `requirements.txt`, `pytest.ini` ni un manifiesto de dependencias Python. Los scripts y tests del baseline usan la biblioteca estándar. No se instaló software.
- No hay archivo `LICENSE`; no se infiere licencia a partir de que el repositorio sea público.

## Inventario de módulos, interfaces y flujo de permisos

| Módulo | Superficie/API observada | Conducta efectiva y límite |
|---|---|---|
| `scripts/route_task.py` | `validate_task`, `required_checks`, `route` | Valida una tarea JSON, elige roles y checks por dominio/interfaz/riesgo y emite modo/acción. Es planificación determinista; no crea procesos ni DAG ejecutable. |
| `scripts/prepare_agents.py` | `provider_for`, `choose_roles`, `schedule_waves`, `make_files`, `prepare` | Genera perfiles Gemini/Codex, packets y `dispatch.json`. `actual_subagent_runs=0`; límites/permisos se marcan no aplicados. |
| `scripts/configuration.py` | `validate_config`, `load_config`, `save_config` | Config JSON con versión 1, allowlist de campos y guardado explícito. El campo de permisos es política solicitada; el módulo no impone permisos de procesos. |
| `scripts/config_panel.py` | `build_policy`, `main`; callbacks Tkinter | UI de configuración y ejecución/cancelación del runner de auditoría. La opción `--check` solo valida el modelo de datos sin importar/abrir la ventana. |
| `scripts/run_agents.py` | snapshot, `command_for`, `run_one`, `plan`, `execute` | Lanza procesos CLI top-level en snapshots temporales para tareas `audit`, aplica concurrencia/deadline/cancelación y registra logs. Devuelve `EXIT_ZERO_UNREVIEWED`; el modo `both` son procesos separados, no un coordinador de mensajes entre proveedores. No integra cambios ni acredita subagentes nativos. |
| `scripts/worktree_coordinator.py` | `repository`, `plan`, `initialize`, `load`, `message`, `inspect`, `gate` | Crea branches/worktrees para roles de implementación y un mailbox JSONL; detecta base local sucia, diffs con error y paths solapados. El gate devuelve como máximo `DECLARED_READY_FOR_HUMAN_REVIEW`, con `evidence_verified: false`. |
| `scripts/development_runner.py` | `command_for`, `run_worker`, `execute` | Ejecuta CLIs top-level en worktrees por rol, con concurrencia y límite global de minutos opt-in. No ejecuta pruebas deterministas ni inicia reviewers/fix loop; el resultado es `PROCESSES_FINISHED_UNREVIEWED`. |
| `scripts/release_gate.py` | `evaluate` | Exige checks declarados, `exit_code=0`, log bajo el root y SHA coincidente; una review requiere dos IDs de contexto distintos declarados. El SHA prueba integridad del archivo, no quién lanzó el proceso, qué código revisó o si IDs/contextos son auténticos. |
| `scripts/validate_skill.py` | `validate` | Validador mecánico de estructura documental, expresamente no certifica software ni ciencia. |
| `references/`, `templates/`, `examples/` | Protocolos, paquetes de muestra y ADR/report templates | Material documental; los JSON de SEIR/ML describen encargos, no traen implementaciones científicas, conjuntos de referencia ni oráculos. |

Flujo de preparación: usuario elige `gemini | codex | both` en configuración/CLI → router selecciona perfiles → preparación escribe packets/manifiesto → runner existente inicia proceso CLI con permiso/sandbox propio del proveedor. El panel guarda valores de coste, permisos y minutos; solo algunos controles de concurrencia/deadline se aplican en runners. USD se reconoce como no medido. Las pruebas no abren una GUI visible, inspeccionan permisos efectivos del SO ni autentican modelos.

**Llamadas principales verificadas en código:** `config_panel.start_audit()` valida inputs y consentimiento → inicia `run_agents.py`; `run_agents.execute()` valida tarea/configuración → construye manifiesto con `prepare_agents.make_files()` → ejecuta waves de `run_one()` → almacena logs/`run_summary.json`. Para desarrollo, `worktree_coordinator.initialize()` crea branches/worktrees y `state.json` → `development_runner.execute()` lee estado e inspecciona base → inicia futures/CLIs top-level → escribe `WORKER_RESULT` en mailbox. `worktree_coordinator.gate()` vuelve a inspeccionar paths y lee eventos. `release_gate.main()` lee task/evidence JSON y llama `evaluate()`. No hay puerto común de runtime entre esos flujos.

**Inventario de los 45 tests baseline:**

| Archivo | Tests | Superficie ejercitada |
|---|---:|---|
| `tests/test_configuration.py` | 13 | Config schema, política, persistencia, protección symlink, waves y check headless. |
| `tests/test_development_worktrees.py` | 8 | Repo Git temporal, worktrees independientes, mailbox, gate, CLI fake y preview. |
| `tests/test_provider_modes.py` | 8 | Perfiles por proveedor, preparación, idempotencia, no sobrescritura y symlink. |
| `tests/test_release_gate.py` | 3 | Evidencia ausente, fixture con hash, ids de review y traversal. |
| `tests/test_routing.py` | 4 | Router SEIR/IDL/riesgo y dominio inválido. |
| `tests/test_runner.py` | 8 | Snapshot, preview, fake CLI, timeout, ausencia de CLI y no escritura del original. |
| `tests/test_structure.py` | 1 | Bundle/documentación requerida. |

Las pruebas de proceso sustituyen la resolución del CLI por ejecutables Python locales; miden el shell/proceso con respuestas preparadas. No acreditan autenticación, sandbox, precio, capacidades o respuestas de un provider.

La documentación confirma que los subagentes nativos están disponibles en runtimes actuales de Codex/Gemini. El código SSEC aquí probado crea perfiles y lanza procesos top-level, y no recoge una traza verificable de delegación nativa. Por eso «perfil preparado», «proceso iniciado» y «subagente invocado» son estados diferentes.

## Contradicciones y documentación desincronizada

- `README.md` titula la versión `v0.2.0-dev.3`; `SKILL.md` declara `0.2.0-dev.4` e `INSTALLATION.md` aún se presenta como `v0.1.0`.
- El roadmap del README describe rollback, trazas, presupuestos, sandbox y revisión independiente como objetivos de v0.2; el runner de worktrees actual dice que no ofrece revisión automática, rollback ni sandbox de SO. Deben leerse como backlog, no como capacidades disponibles.
- El docstring de `scripts/config_panel.py` dice “No network or AI execution”, aunque el panel incluye una acción opt-in que inicia `run_agents.py` con CLIs reales. El check headless no descubre esa ruta.
- La GUI y README muestran permisos, concurrencia y presupuesto. La política guardada no impone permisos por sí sola ni limita USD; el runner sí limita procesos top-level/tiempo según configuración. Es necesario distinguir configuración, aplicación del runner y enforcement del sandbox del proveedor.
- Los textos del runner nombran procesos reales de CLI, mientras perfiles/manifiestos usan vocabulario de “agentes/subagentes”. El proceso CLI lanzado por SSEC no prueba que el proveedor haya delegado a un subagente nativo; la documentación de cada capa debe reservar nombres distintos.

## Brechas de fase P2 (issue #2)

1. **No hay biblioteca científica ejecutable.** No existe `scientific_core/`, paquete de solvers, optimizadores, modelos, identificabilidad o ML. `references/ARCHITECTURE.md` lo presenta como diseño futuro; guías como `SCIENTIFIC_BOUNDARY.md` describen protocolos, no cálculos.
2. **El catálogo de roles no satisface el catálogo objetivo.** `route_task.py` agrupa álgebra diferencial/simbólica, dinámica e identificabilidad en `mathematical_model_specialist` o `numerical_analyst`; no existen especialistas explícitos `differential_algebra_specialist`, `dynamical_systems_specialist` e `identifiability_specialist`.
3. **Las obligaciones científicas se activan por riesgo R2/R3, no por todo claim científico.** `required_checks()` agrega `scientific_validation` bajo riesgo alto. Dominios de claims pueden activar un puente/review nominal sin asegurar un check ejecutado cuando la tarea tiene riesgo R0/R1.
4. **Faltan oráculos y pruebas científicas.** Tests actuales verifican asignación, opciones y estructura. No contrastan soluciones ODE/PDE conocidas, precisión/convergencia, invariantes, sensibilidad, simetrías/fibras, estabilidad, métricas de optimización o ML, seeds/multiruns, units ni resultados reproducibles con versiones fijadas.
5. **Faltan ejemplos que deban fallar y certificados/procedencia externos.** Los ejemplos son packets JSON; no son benchmarks. El adaptador opcional a `scientific-research-rag-council` no está implementado.

**Conclusión P2:** `PLANNED`/documental. No hay base para afirmar validez numérica o científica. El trabajo P2 debe seguir separado en `SOFTWARE_VALIDITY`, `NUMERICAL_VALIDITY` y `SCIENTIFIC_VALIDITY`, y sus fixtures deben establecer resultados de referencia con límites calibrados.

## Defectos y riesgos priorizados

| Prioridad | Hallazgo y evidencia | Impacto / reproducción o verificación siguiente |
|---|---|---|
| P0 / entorno | En el host local, dos tests de symlink terminan con `WinError 1314` antes de evaluar el código de rechazo. | Este host/Python 3.14 no acredita esos dos checks. La matriz CI Windows/Python 3.11 y 3.12 pasó; usar esos entornos como evidencia soportada y no cambiar la baseline para simular PASS. |
| P1 bloqueante | `worktree_coordinator.message()` permite que un emisor cuyo nombre sea un reviewer declare `REVIEW_ACCEPTED`; `gate()` busca etiqueta + tipo de evento, no una ejecución/contexto autenticado. `TEST_RESULT` acepta un resumen literal `<check>:PASS`. | Autodeclaraciones bastan para `DECLARED_READY_FOR_HUMAN_REVIEW`; el mismo módulo reconoce `evidence_verified:false`. Añadir primero tests de falsificación y mover estado canónico al coordinador. |
| P1 alto | `release_gate.evaluate()` acepta campos `PASS`, exit 0, IDs separados y un hash correcto sin validar procedencia de ejecución. `tests/test_release_gate.py::test_success_is_not_final_approval` usa `command="fixture-only"` y logs de fixture y espera `READY_FOR_MANUAL_REVIEW`. | El estado evita liberar automáticamente, pero no demuestra que tests/review se ejecutaron. Exigir registros vinculados a run, commit, input y proceso verificados; conservar el gate humano. |
| P1 alto | `development_runner.execute()` lanza solo implementers; no inicia tests, reviewers ni loop de correcciones. | No hay secuencia de aceptación del issue #1. Reproducible con `test_fake_cli_processes_do_not_change_source`: los CLI simulados modifican su propio worktree y el runner registra el proceso como no revisado. |
| P1 alto | `development_runner.execute()` no persiste estado de ejecución ni adquiere lock; logs por rol se abren `wb` y se pueden pisar con ejecuciones repetidas/concurrentes. No existe recuperación/cleanup transaccional tras un `worktree add` parcial. | Riesgo de carreras, pérdida de evidencia y worktrees/branches huérfanos. Añadir lock, run ID, transiciones idempotentes y recuperación antes de retries. |
| P1 alto | `inspect()` añade nombres de archivos untracked al texto cuyo hash calcula, pero no el contenido de esos archivos; no contrasta ese hash con handoff/gate. | Hash estable frente a cambios de contenido untracked. El test debe modificar contenido manteniendo nombre. |
| P1 medio-alto | `plan()` comprueba el destino final inexistente; `initialize()` crea `base/task_id` con `mkdir(parents=True)` sin validar el ancestro. | Un ancestro symlink puede redirigir la creación fuera del árbol esperado. Probar ancestros/rutas canónicas y carreras antes de habilitar escrituras externas. |
| P1 / confianza | `file_ownership` no figura en el plan; el gate detecta paths editados por varios workers, no si un worker modifica un path fuera de su permiso. Worktrees tampoco son aislamiento de SO. | La colisión no equivale a ownership ni sandbox. Mantener `NEEDS_HUMAN` en conflictos y describir los límites por runtime. |
| P1 / independencia | Los dos IDs distintos del release evidence y la etiqueta reviewer del mailbox son autocargados; no acreditan un contexto separado. | Vincular revisión a una sesión/contexto real y su input hash; auditor no debe recibir veredicto previo como premisa. |
| P3 | La prueba GUI es headless y no importa/abre Tkinter; no hay smoke visual Windows/Linux. | Estado de GUI real `NOT_RUN`; agregar E2E en runner de escritorio cuando esté disponible. |
| P3 | No se probó instalación/licencia de IDL ni puente Python. | `idl_integration=NOT_RUN`; conservarlo así y dar instrucciones de validación para un host con licencia. |
| P4 bloqueante por dueño | No hay decisión/archivo LICENSE ni política de contribución. | No agregar licencia por inferencia; issue #5 requiere decisión expresa del propietario. |

No se confirmó un exploit de symlink externo; el hallazgo es una ruta de código que requiere prueba adversarial. Las deficiencias de logs/estados se describen como riesgos de procedencia e integridad, no como ruptura criptográfica: el diseño actual no promete una firma ni un límite de sistema operativo.

## Backlog P0 → P4 por riesgo y dependencia

1. **P1.1 — Evidencia canónica (bloqueante):** pruebas rojas para `REVIEW_ACCEPTED`/`TEST_PASS` falsos; ejecutar checks desde el coordinador; ligar logs a `run_id`, SHA base, task/input hashes, argv aprobado, entorno y exit code; derivar estado desde resultados validados.
2. **P1.2 — Runtime SPI y modos de proveedor:** `AgentRuntime`, `FakeRuntime`, detección versionada de capacidades, Codex/Gemini adapters opcionales; validar que la elección explícita no despache al segundo proveedor. No ejecutar llamadas pagas en CI.
3. **P1.3 — Ciclo operativo y recuperación:** DAG real, semáforo, exclusión/locks, retries acotados, timeout/cancelación de árbol de procesos, reinicio/idempotencia y rollback/cleanup de worktrees parciales.
4. **P1.4 — Revisión y gate de integración:** tests deterministas después del implementer, reviewer en contexto separado con diff/hash exactos, loop de fixes, ownership de archivos, conflicto → `NEEDS_HUMAN`; no merge automático.
5. **P1.5 — Límites de seguridad declarados y probados:** rutas UNC/Windows, enlaces y ancestros, procesos hijos, logs/secretos, proyecto Git dirty y aislamiento real por proveedor/host. Worktree y separación de contexto no se presentarán como sandbox del SO.
6. **P2 — Paquetes científicos opt-in:** elegir el módulo mínimo necesario por dominio y añadir referencias/oráculos/tests adversariales reproducibles antes de elevar cualquier estado de validez numérica o científica.
7. **P3 — GUI/IDL:** supervisor no bloqueante/headless, pruebas visibles Windows/Linux; puente IDL separado, con `NOT_RUN` si no hay instalación/licencia.
8. **P4 — Calidad/benchmarks/releases:** gates estáticos, seguridad/dependencias, tres proyectos benchmark, threat model y RC condicionado por evidencia. Actualizar actions/runner OS a revisiones explícitamente soportadas tras verificar compatibilidad; el run actual advierte la transición Node 20→24 y el carácter móvil de `ubuntu-latest`. Resolver licencia y gobernanza con el propietario antes de distribución.

## Estados de fase

| Fase | Estado en este commit |
|---|---|
| P0 | `IMPLEMENTED`; baseline, ADR-001 y matriz de funciones documentados. |
| P1 | `EXPERIMENTAL`; se inicia con evidencia verificable, pero gates completos pendientes. |
| P2 | `PLANNED`; los módulos científicos y oráculos no existen. |
| P3 | `EXPERIMENTAL` para panel; GUI visual y puente IDL `NOT_RUN`. |
| P4 | `PLANNED`; existe CI Windows/Linux × Python 3.11/3.12, pero benchmarks, gates adicionales y decisión legal siguen pendientes. |

**Release status:** `PARTIAL`. No se propone cerrar ninguna issue ni declarar v1.0.
