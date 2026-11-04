# Plan P1.4 — Adaptador AGY

1. [x] **Tests primero:** factory/argv seguro, detección de capacidades, parseo del envelope JSON válido y rechazo de estado/error/session/respuesta incompletos. Confirmar RED.
2. [x] **Implementar:** `AgyRuntime` en `provider_runtimes.py`, parseo de JSON estricto y registro explícito en `create_runtime`; mantener sandbox `UNKNOWN` y subagents `UNKNOWN`.
3. [x] **Verificar:** 47 tests focalizados Windows; `py_compile`; diff check. Linux local quedó `BLOCKED` por daemon Docker no disponible; CI del branch se consultará después del push.
4. [x] **E2E:** una solicitud autorizada por `AgyRuntime`, en proyecto temporal vacío; exit 0. Guardar resumen con uso de cuota `NOT_RECORDED`. No repetir.
5. [ ] **Entrega:** documentar límites y estado real de P1.4, crear commit y PR draft apilado sobre #16; sin merge/release.
