# P3.10 — solicitud de auditoría desde un workspace verificado

**Estado:** implementado en rama de trabajo; CI del incremento pendiente. No se hizo merge ni se publicó una release.

## Resultado

La GUI permite elegir recursos del `LoadedWorkspace`, muestra ID, tipo, ruta, tamaño y SHA-256, y exige confirmación humana antes del despacho. La confirmación advierte que el proveedor puede cobrar y que SSEC no mide ni limita la facturación. El trabajo se ejecuta en un hilo separado, expone cancelación y presenta el resumen terminal como no aprobado.

El plan inmutable vincula la solicitud a `workspace_id`, digest del manifiesto y recursos seleccionados. El dispatcher revalida los bytes capturados por el loader y arma una raíz temporal nueva con solo esos archivos y contexto de componentes que los referencian. Antes de invocar el runner, compara el conjunto encontrado con el conjunto permitido. El runner existente conserva su comportamiento y no vuelve a escanear el proyecto original. El reporte queda en `.ssec/runs/<run_id>/run_summary.json` con procedencia, hashes, recursos, rutas y estado de ejecución.

Exit 0 se mantiene como `PROCESSES_COMPLETED_NOT_AUDITED`; fallo o cancelación no aprueban nada. `release_status` siempre es `NOT_APPROVED` y `scientific_validity` es `NOT_CERTIFIED`. No se ejecuta código del proyecto ni código generado por agentes.

## Evidencia local

- Plataforma: Windows 10.0.26300, Python 3.14.0.
- Suite enfocada del subsistema workspace/runner: **108 tests, 0 fallos, 1 omitido**. El omitido es la prueba de escape con symlink del loader; Windows no concedió privilegio para crear el enlace (`WinError 1314`), así que esa aserción no se ejecutó.
- Comando reproducible: `python -m unittest tests.test_scientific_workspace tests.test_scientific_workspace_loader tests.test_scientific_workspace_view tests.test_scientific_workspace_actions tests.test_scientific_workspace_proposals tests.test_scientific_workspace_audit tests.test_scientific_workspace_app tests.test_runner -q`.
- Cobertura del incremento: selección conocida/única, plan y task inmutables, SHA-256, staging allowlist, exclusión de nombres protegidos, ACK de coste, persistencia de procedencia, fallo sin aprobación, cancelación antes del lanzamiento y GUI con confirmación, thread, cancelación y salida `NOT_APPROVED`.
- Las pruebas GUI condujeron widgets Tk en ventanas retiradas; una interacción visual manual sigue `NOT_RUN`.
- `python -m py_compile scripts/scientific_workspace_audit.py scripts/scientific_workspace_app.py tests/test_scientific_workspace_audit.py tests/test_scientific_workspace_app.py`: **PASS**.
- `git diff --check`: **PASS**.
- CI Windows/Linux del nuevo commit: **PENDING**.

Los procesos CLI de las pruebas fueron falsos. No se invocó Codex, Gemini ni AGY, no hubo coste, y la integración real con proveedores queda `NOT_RUN` conforme a la instrucción del propietario de no realizar llamadas adicionales. No se dispone aún de las ecuaciones ni de los datos del SIR del usuario; ese caso científico integral sigue `NOT_RUN`.

## Defectos y revisión independiente

La revisión independiente encontró un defecto importante reproducible: la UI no podía cancelar el runner. Se añadió una señal temporal fuera del snapshot, se conectó a `run_agents.execute`, se conserva el estado de cancelación en el resumen y al cerrar la ventana se solicita cancelación y se espera el resultado terminal. Se añadieron pruebas del botón, cancelación antes del lanzamiento y cierre de ventana. El revisor confirmó la corrección; verificó además con proceso falso ya iniciado que el resumen persiste `CANCELLED`, `NOT_APPROVED` y `cancellation_requested=true`. La cancelación de un proveedor real permanece `NOT_RUN`.

La suite combinada reprodujo dos problemas Tcl/Tk en Python 3.14. Primero, el resultado entraba a la cola antes de que el hilo worker terminara, y el cierre podía destruir el intérprete mientras ese hilo aún salía; la GUI ahora espera que el worker termine antes de limpiar la señal o destruir la ventana. Después, el test combinado mostró que intérpretes Tk de fixtures ya destruidos podían recolectarse desde un hilo de `test_runner`; los fixtures ahora recolectan esos ciclos desde el hilo principal. La suite combinada pasó después de ambos cambios. Revisión independiente final: **4/4 pruebas focales pasaron** para ejecución normal, cancelación por botón, cierre durante auditoría y cancelación antes del lanzamiento; sin hallazgos importantes residuales.

La inspección del staging también halló un posible choque entre un recurso raíz llamado `ssec-workspace-context.json` y el archivo reservado de contexto; ahora el recurso se rechaza antes de lanzar procesos y tiene regresión específica.

También se corrigieron dos problemas de prueba/integración durante el trabajo: un fixture usaba un tipo de componente no registrado y un resumen reconstruido omitía `cancellation_requested`. Ambos tienen regresión verde.

## Decisión arquitectónica

No se añadió una segunda API de snapshot a `run_agents.py`: se invoca el runner actual contra una raíz temporal de un solo uso cuyo contenido se inspecciona y compara exactamente. Esto mantiene pequeño el cambio de runtime y evita acoplar esta rama P3 con el cambio paralelo de runtime P1. La persistencia de logs y resumen es deliberada; el contenido recibido del proveedor se guarda localmente en `.ssec/runs`.

## Limitaciones restantes

- La CLI no proporciona aislamiento absoluto de sistema operativo. La auditoría debe tratarse como una operación local que puede compartir los recursos seleccionados con el proveedor configurado.
- El runner conserva sus límites actuales: la facturación no se mide, los logs no tienen una cuota dura y la terminación de procesos depende de capacidades del host/CLI.
- Las respuestas por rol son resultados de procesos, no una revisión independiente verificada por un segundo gate SSEC. No se producen pruebas científicas, aprobación humana ni aprobación de release.
- El SIR del usuario, sus ecuaciones, unidades y datos siguen `NOT_RUN`; el ejemplo existente es sintético.
- Linux y Python 3.11/3.12 para este incremento quedan pendientes del CI del PR.

## Estado de entrega

- Commit de rama: pendiente.
- Pull request draft apilado sobre P3.9: pendiente.
- Merge a `main`, tag y release: no realizados.
- Próximo paso: confirmar revisión puntual de cancelación, crear el commit y PR draft, y registrar el CI del incremento.
