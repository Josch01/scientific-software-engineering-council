# Matriz de capacidades y evidencia

**Referencia:** commit base `908e35637518c4c1ab56c1f75138d194cadd3938`; auditoría 2026-11-02.
**Estados:** `IMPLEMENTED | VERIFIED | EXPERIMENTAL | NOT_RUN | BLOCKED | PLANNED`.

`VERIFIED` se limita a la afirmación de la fila y al entorno/comando citado. No implica independencia, seguridad completa, validez científica ni readiness de release.

| Capacidad | Estado | Evidencia disponible | Límite / siguiente paso |
|---|---|---|---|
| Validador estructural de la skill | `VERIFIED` | Windows, Python 3.14.0; `python scripts/validate_skill.py`, exit 0. | Verifica estructura documental únicamente. No valida software o ciencia. |
| Router por tarea/riesgo/proveedor | `VERIFIED` | Tests de routing y smoke `python scripts/route_task.py examples/seir_desktop_audit.json`, exit 0. | Plan determinista; no DAG ejecutado, subagente ni gate de claim científico general. |
| Perfiles y packets Gemini/Codex | `VERIFIED` | Tests provider mode generan archivos/manifiestos para cada selección. | Preparar perfil no invoca agente ni hace cumplir permisos. |
| Configuración JSON/panel headless | `VERIFIED` | Tests de configuración disponibles pasaron excepto caso symlink; `python scripts/config_panel.py --check`, exit 0. | Valores de presupuesto/permisos son solicitados; el check no abre ventana. |
| Protección symlink del guardado de config/perfiles en este Windows | `BLOCKED` | `test_symlink_refusal` y `test_symlink` terminan en `WinError 1314` al crear el fixture. | Reejecutar con privilegio apropiado o en runner Windows con symlink habilitado; no reportar PASS hasta que llegue a la aserción. |
| Runner de auditoría con procesos fake | `EXPERIMENTAL` | Tests de fake CLI, timeout, ausencia de CLI y snapshot sin secretos. | Proveedor real, auth, sandbox efectivo, costos y perfil de cuenta siguen `NOT_RUN`; top-level CLI, no delegación nativa demostrada. |
| Codex CLI instalado y opciones de ayuda | `VERIFIED` | `codex-cli 0.166.0-alpha.5.1`; `--version`/`codex exec --help` exit 0. | Sin prompt ni E2E real. No se inspeccionaron credenciales. |
| Gemini CLI instalado y opciones de ayuda | `VERIFIED` | `0.64.0`; `--version`/`--help` exit 0. | Sin prompt ni E2E real. No se inspeccionaron credenciales. |
| Codex-only real en SSEC | `NOT_RUN` | No hay invocación de modelo en baseline. | E2E opt-in, requiere autorización/costo medido y evidencia de proceso/runtime. |
| Gemini-only real en SSEC | `NOT_RUN` | No hay invocación de modelo en baseline. | E2E opt-in, requiere autorización/costo medido y evidencia de proceso/runtime. |
| `both` real con coordinación cruzada | `NOT_RUN` | Tests solo validan asignación de proveedores; no hay intercambio runtime verificado. | Correlacionar IDs, contratos, estados y concurrencia de ambos runtimes. |
| Subagentes nativos por proveedor | `NOT_RUN` | Docs oficiales actuales describen subagentes, pero la salida de help/version no es prueba de una delegación ejecutada. | Adaptador requiere detección de capacidades y traza real; distinguir de procesos CLI top-level. |
| Worktrees Git de roles y aislamiento de archivos | `EXPERIMENTAL` | Tests crean worktrees Git temporales y prueban independencia del árbol fuente. | Faltan ownership, limpieza transaccional, recovery, lock/idempotencia y prueba contra symlinks ancestro. Worktree no es sandbox de SO. |
| Mailbox de worker/reviewer | `EXPERIMENTAL` | Rechaza auto-review bajo la etiqueta de worker y usa JSONL. | Las etiquetas de rol no autentican emisor/contexto; el reviewer puede auto-declarar acceptance. |
| Verificación de tests/reviews del worktree gate | `BLOCKED` | `gate()` reconoce `TEST_RESULT` por resumen `<check>:PASS`; no inspecciona proceso/log/hash. | P1.1 debe impedir falsificación y calcular estado canónico desde ejecución y evidencia validadas. |
| Gate mecánico de evidencia de release | `EXPERIMENTAL` | Prueba hash/ruta, falta de evidencia y fixture; ejemplo NOT_RUN bloquea (exit 2). | Fixture `fixture-only` con PASS/hash correcto obtiene `READY_FOR_MANUAL_REVIEW`; falta provenance. El estado no libera automáticamente. |
| Orden tests deterministas → reviewer independiente → fix loop | `PLANNED` | No se observa en `development_runner`. | Secuencia completa es gate P1 pendiente. |
| Tipos `AgentRuntime`, scheduler DAG, recuperación y semáforo central | `PLANNED` | No hay interfaz/runtime SPI central ni state machine durable. | Prioridad P1 tras el test de evidencia canónica. |
| Tkinter visible, responsive E2E Windows/Linux | `NOT_RUN` | Solo check headless del modelo. | Se necesita runner con escritorio, pruebas de cancelación/progreso y evidencia visual. |
| IDL Interactive Data Language + Python Bridge | `NOT_RUN` | Ninguna ejecución/licencia verificada. | Conservar `idl_integration=NOT_RUN`; validar dtypes/shapes/orden/NaN/errores en instalación licenciada. |
| Biblioteca científica modular y opt-in | `PLANNED` | Referencias y ejemplos JSON; sin `scientific_core` ni solver ejecutable. | Issue #2: ODE/PDE, álgebra/dinámica/identificabilidad, optimización/ML/datos por demanda. |
| Oráculos numéricos, pruebas de convergencia/precisión y regresiones | `PLANNED` | No hay fixtures con valores científicos de referencia. | Crear casos exactos/analíticos y límites antes de afirmar validez numérica. |
| Pruebas matemáticas/certificados científicos | `NOT_RUN` | No se ejecutó una prueba rigurosa; el baseline no contiene certificado científico verificable. | No inferir unicidad, estabilidad, optimalidad o causalidad de una corrida/test. |
| CI del commit baseline actual | `VERIFIED` | Push run [#41496442300](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41496442300), SHA `908e356`, cuatro jobs Windows/Ubuntu × Python 3.11/3.12 `success`; jobs `125452535840`, `125452536188`, `125452536466`, `125452536536`. | El run no trae artifacts descargables ni test count registrado aquí. Tiene avisos Node 20→24 y `ubuntu-latest` móvil. No sustituye GUI visual ni entorno local Python 3.14. |
| Linux, Python 3.11 y Python 3.12 en el host local | `NOT_RUN` | El host disponible es Windows/Python 3.14.0; el CI remoto sí cubre Linux/Windows 3.11/3.12. | Esta fila solo se refiere al entorno local; no duplica la evidencia CI. |
| Linting, tipos, secretos, dependencias, vulnerabilidades, benchmark 3 proyectos | `PLANNED` | El workflow actual no configura estos gates. | P4; fijar dependencias/política al elegir paquetes reales. Actualizar actions/runner OS después de revisar las advertencias vigentes. |
| Decisión de licencia y contribuciones | `BLOCKED` | Issue #5 abierta; no existe `LICENSE`. | Requiere decisión del propietario; no generar archivo vinculante por suposición. |
| Release SSEC 1.0 | `PLANNED` | Faltan gates P1–P4 completos, benchmarks, auditoría de seguridad independiente y decisión de licencia, aunque el baseline actual sí pasó CI. | No `RC_READY`; mantener `PARTIAL` hasta evidencia y decisión humana. |

## Lectura del estado

P0 está implementado documentalmente en [`BASELINE_AUDIT.md`](../audits/BASELINE_AUDIT.md) y [`ADR-001-runtime-boundaries.md`](../architecture/ADR-001-runtime-boundaries.md). P1 sigue experimental y tiene bloqueante de procedencia. P2 permanece planeado. P3 tiene un panel Tkinter con prueba headless, pero GUI visual e IDL están `NOT_RUN`. P4 y v1.0 no están listos.
