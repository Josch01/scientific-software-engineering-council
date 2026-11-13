# P2.7 — Checklists científicas SIR

- `PASS` — perfiles Codex/Gemini/AGY reciben checklist por rol solo en tareas que nombran SIR/SEIR/epidemiología compartimental; tareas generales no reciben el bloque.
- `PASS` — presión ciega posterior: estado `NOT_ASSESSED`, cálculos `NOT_RUN`; separa formulación/unidades, error numérico, identificabilidad y límites de conclusiones, sin inferir de `RMSE=0.02`.
- `PASS` — `python -m unittest tests.test_routing tests.test_provider_modes -q`: 20 tests, 1 omitido por fixture symlink Windows; `python scripts/validate_skill.py`; `py_compile`; `git diff --check`.
- Baseline antes del cambio: detectó datos faltantes y cautela con RMSE, pero no separó estructural/práctica ni delimitó predicción/causalidad/validez epidemiológica; checklist añadida corrige esa brecha documental.
- `NOT_RUN` — proveedores reales y SIR del usuario. No se ejecutaron modelos, no se usaron la tesis ni sus datos.
- Límite: los bloques son prompts de revisión, no evidencia ni certificación. La detección requiere que la solicitud mencione SIR/SEIR o epidemiología compartimental.
