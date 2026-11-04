# P2.5 — enrutamiento explícito de modelos ODE

## Resultado

`domains: ["ode"]` ahora asigna `ode_model_specialist` y `numerical_analyst`; una tarea de construcción conserva `implementation_engineer`. `prepare_agents.py` puede generar el perfil local del nuevo rol con su obligación concreta. La selección de ODE por sí sola no afirma estabilidad, identificabilidad o validez, ni exige revisión de claims; esos controles siguen ligados a los dominios científicos y el riesgo declarados.

La skill portable y su referencia de routing documentan la especialidad. No se modificaron solvers, análisis SIR, contratos científicos ni invocaciones de proveedor.

## Verificación

Windows, Python 3.14:

- TDD: antes de la implementación, la nueva regresión falló porque `ode` no estaba en `DOMAINS`; tras la implementación, el test pasó.
- `python -m unittest -v tests.test_routing tests.test_execution_evidence tests.test_work_items`: **45/45 PASS**, incluido el test que pasa por `make_files` y comprueba el perfil y packet generados.
- `python scripts/validate_skill.py`: PASS (`VALID STRUCTURE`; no certifica corrección científica).
- `python -m compileall -q scripts tests`: PASS.
- `git diff --check`: PASS.
- Una corrida auxiliar de `tests.test_routing tests.test_execution_evidence tests.test_configuration tests.test_provider_modes tests.test_work_items` ejecutó 66 casos: 64 pasaron y dos fixtures fallaron antes de llegar al código por `WinError 1314` al crear symlinks en `test_symlink_refusal` y `test_symlink`. La suite de routing/evidencia/work items sin esos fixtures de plataforma se repitió y pasó 45/45.

La prueba real de una CLI/proveedor y la delegación a subagentes nativos quedan `NOT_RUN`; esta entrega prueba el plan y la preparación local de perfil, no la ejecución. No se llamó a un modelo.

La revisión independiente no encontró defectos críticos ni importantes. Su observación menor —cubrir la integración por `make_files`— quedó atendida por el test enfocado.

## Decisiones, defectos y límites

- **Decisión:** ODE activa formulación del modelo y revisión numérica. Los claims de identificabilidad, estabilidad y demostración matemática siguen siendo obligaciones distintas.
- **Defecto corregido:** no había un dominio cerrado para ODE y `prepare_agents` rechazaría un rol nuevo sin una entrada en su registro `ROLE_TASKS`.
- **Riesgo no bloqueante:** el nombre/perfil del rol no demuestra que un proveedor nativo lo ejecute en un contexto separado. P1 conserva esa capacidad como `UNVERIFIED`.
- **Pendiente:** PDE; oráculos, referencias y claims del SIR particular; invocación real de proveedor (no autorizada en este tramo); identidad/autenticidad de roles y auditorías.

## Commits y PR

La rama es `codex/p2-ode-specialist-routing`, separada de P3 y basada en `codex/p4-release-governance`. Se entrega como PR draft independiente, sin merge ni release; los commits están registrados en el historial de la rama.
