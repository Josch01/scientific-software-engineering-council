# P1.4.1 — dispatch AGY desde el supervisor (2026-11-04)

## Alcance

`agy` es un proveedor explícito en configuración, GUI, planner y CLI. Para ese modo, `run_agents.execute` crea un `RuntimeRequest` por rol y usa `AgyRuntime`; no sustituye `gemini`, no cambia `both` y no crea perfiles nativos AGY. Cada petición usa `writable=False`, acknowledgement de coste explícito, deadline global y control compartido de cancelación. Los resultados conservan el ID de runtime por rol, estado, exit code, sesión y hashes stdout/stderr. La salida exit 0 continúa como `EXIT_ZERO_UNREVIEWED`; el resumen termina en `PROCESSES_COMPLETED_NOT_AUDITED` y `release_status=NOT_APPROVED`.

No se invocó un modelo/proveedor durante este incremento. No demuestra el recorrido real del supervisor, revisión integrada, independencia, autenticación ni aislamiento efectivo. La única llamada real autorizada anterior validó el adaptador `AgyRuntime` por separado ([reporte](p1-agy-runtime-adapter-2026-11-03.md)).

## Verificación local

| Comando/alcance | Resultado |
|---|---|
| Nueve pruebas AGY específicas de selección, ejecución fake, ACK, fallo, cancelación, timeout, cleanup y gate de lanzamiento | `PASS`, incluidas en la suite combinada de 86 tests |
| `python -m unittest tests.test_configuration tests.test_provider_modes tests.test_provider_runtimes tests.test_runner -q` | `BLOCKED` parcialmente por entorno: 86 tests ejecutados; 84 pasaron. Dos fixtures no pudieron crear symlinks (`WinError 1314`) antes de sus aserciones. |
| `python -m unittest tests.test_runner -q` | `PASS`, 8/8; regresión de compatibilidad del worker existente. |
| `python -m py_compile` en módulos/tests modificados; `git diff --check` | `PASS`, ambos comandos terminaron sin errores. |
| Windows/Linux CI para el commit `8466e7b2a3aa7966ce7c339febf2f100387273b0` | `PASS`, run [#148](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/41754856720), 4/4 jobs (Windows/Ubuntu × Python 3.11/3.12). |
| Despacho supervisor → CLI AGY real | `NOT_RUN`; no repetir la invocación real ya autorizada. |

La prueba de `execute` usa runtimes falsos: verifica el enlace por rol, `runtime_run_id` distinto por especialista y que un grupo de exit 0 no genera aprobación. No prueba el comportamiento del proveedor ni de su sandbox.

La revisión independiente encontró dos carreras de cancelación antes de `Popen`. En modo AGY, `execute` ahora comparte el mismo `RuntimeLaunchControl` con todos los workers; cancelación, fallo y deadline se registran mediante `set()`, y `blocked_status()` observa el archivo de cancelación dentro del gate final justo antes del spawn. El worker vuelve a comprobarlo al retornar de `runtime_factory`, antes de llamar al runtime. Las regresiones cubren cancelación previa a la ola, aparición durante la creación del runtime y durante la reserva de outputs; los caminos de worker verifican el mismo control.

La revisión clasificó como menor una ventana TOCTOU restante: si el archivo aparece inmediatamente después de devolver `blocked_status()` y antes de que `Popen` ejecute, esa sesión puede iniciarse; al volver `launch()`, el worker detecta la marca y solicita `cancel()`. La cancelación fuera de banda no comparte un lock con la llamada del SO. El resultado no concede review ni aprobación; queda documentado como limitación.

## Limitaciones y pendientes

- El CLI configura `--mode=plan` y `--sandbox`, pero `sandbox_effective` queda `None`; son opciones solicitadas, no una garantía de solo lectura.
- Coste en USD no medido ni limitado por SSEC. `--accept-unmetered-cost` es confirmación explícita, no control de cuota.
- La integración real del reviewer/coordinador P1.4 permanece `NOT_RUN`; el humo AGY previo no valida el supervisor.
- `run_agents` continúa copiando el snapshot completo del proyecto sujeto a exclusiones/límites. Un audit dinámico debe enviar solo recursos elegidos explícitamente, después de verificación de hash y contención.
- Un archivo de cancelación creado justo después del chequeo final previo a `Popen` puede perder esa carrera estrecha; el worker lo cancela al regresar `launch()`. Esto no produce un estado de aprobación, pero puede iniciar brevemente una sesión.
- La evidencia por hash no autentica la cuenta, el proveedor, el operador ni el emisor.

## Estado

Incremento de software local comprobable con runtime fake. Revisión independiente concluida; la TOCTOU menor está documentada. Commit `8466e7b2a3aa7966ce7c339febf2f100387273b0`; PR draft #33 apilado sobre #32. Run #148 pasó los 4 jobs. No merge ni release.
