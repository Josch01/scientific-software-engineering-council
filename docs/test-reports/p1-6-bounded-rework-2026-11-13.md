# P1.6 — Rework acotado

- `PASS` — ciclo local completo: `CHANGES_REQUESTED` → paquete ligado a hallazgos → corrección → checks reales del fixture → integración nueva → revisión determinista → `NEEDS_HUMAN`; sin aprobación ni merge automáticos. 1 prueba, 394.444 s en Windows.
- `PASS` — 3 pruebas rápidas del CLI/rework (`tests.test_rework_loop`); `py_compile`; `git diff --check`; fixture Windows con `git diff --check` vacío en ambos worktrees.
- `PASS` — evidencia de la integración fuente se valida con sus hashes persistidos después de cambiar los worktrees; el gate requiere árbol actual para la última ejecución e historial verificable para las anteriores.
- `NOT_RUN` — ejecución real del ciclo de rework con AGY/Codex/Gemini. La revisión multiagente de la prueba usa una respuesta fixture determinista; no cuenta como proveedor real. No se hicieron invocaciones de modelos.
- Defectos corregidos: validación histórica atada al árbol vivo, gate que invalidaba integraciones/checks anteriores al rework y fixture Windows que escribía CRLF como espacios finales; IDs de sesiones fixture ahora son únicos por ejecución.
- Pendiente de P1: rework con proveedor autenticado sigue `NOT_RUN`; no se afirma que el flujo de agentes reales esté verificado. Scheduler DAG, recuperación distribuida y sandboxing general siguen pospuestos.
