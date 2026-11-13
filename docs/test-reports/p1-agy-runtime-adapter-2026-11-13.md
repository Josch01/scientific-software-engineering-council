# P1.5 — Adaptador local AGY

**Estado:** EXPERIMENTAL; proveedor real NOT_RUN. Este incremento añade el camino offline para workers AGY y conserva Codex como reviewer independiente. No constituye evidencia de una sesión autenticada ni de validez científica.

## Capacidad y límites

- CLI local observado: agy 1.5.0; --version/--help disponibles. La invocación de un prompt usa agy --prompt=<texto> --output-format stream-json --sandbox --mode accept-edits --agent ssec-<rol>. No se usa --dangerously-skip-permissions.
- El formato AGY es distinto de Gemini: event=init, event=step_update, event=result; el identificador es conversation_id y el resultado exitoso tiene estado SUCCESS. SSEC valida ese contrato al recoger logs y al corroborar la sesión durante la revisión integrada.
- provider_mode=agy asigna workers a AGY y reviewers a Codex. Cada worktree recibe un perfil AGY fijo con view_file, grep_search, replace_file_content y write_to_file; commandExecutionPolicy: off y subagent: false. El coordinador no escribe el perfil en el proyecto original. Los archivos del perfil cuentan como parte del candidato del worker.
- AGY se rechaza para solicitudes de solo lectura y para propuestas que requieren el archivo externo de política no-ejecución. Las propuestas de workspace conservan el fallback manual JSON/Gemini existente.
- Preflight local: AGY se bloquea antes de arrancar si `allowNonWorkspaceAccess` está activo, mal formado o no puede leerse de forma segura. Se rechazan settings con enlaces/reparse points, tipos JSON ambiguos y archivos no regulares o mayores a 1 MiB. La ausencia de configuración conserva el default documentado del proveedor.
- La revisión histórica admite la identidad `init` de sesiones AGY fallidas/interrumpidas aunque no haya `result`, pero solo las registra como fallidas. Una entrada `SUCCEEDED` aún requiere un terminal exitoso y completo.
- --sandbox es una restricción declarada por el proveedor; SSEC no afirma aislamiento absoluto del SO. No se inspeccionaron credenciales, no se envió prompt y no se consumió cuota.

Documentación oficial consultada: [headless mode y NDJSON](https://antigravity.google/docs/cli/headless), [custom agents y lista de herramientas](https://antigravity.google/docs/subagents?tab=cli), [modos de ejecución](https://antigravity.google/docs/cli/modes).

## Verificación de este incremento

- PASS — 4 regresiones focalizadas: settings AGY no seguros, parser de stream AGY, corroboración de sesión AGY completa y archivo histórico AGY incompleto fallido (4 passed, 12.55 s).
- PASS — probes locales agy --version/agy --help; no enviaron prompt.
- PASS — compilación de módulos tocados, validador de skill y git diff --check.
- BLOCKED — el grupo combinado `tests/test_development_worktrees.py` + `tests/test_integration_candidate.py` quedó sin terminar ni producir resumen; se interrumpió después de espera prolongada. No se cuenta como verificación.
- NOT_RUN — ejecución autenticada real de agy, ciclo completo con coste del proveedor y evaluación de eficacia real de restricciones del agente/sandbox. No se repite la llamada autorizada previamente.
- NOT_RUN — SIR particular del usuario; simulación, ajuste, residuales, sensibilidad, identificabilidad y validez científica.

## Riesgos y pendiente acotado

La herramienta AGY puede leer/escribir archivos del worktree mediante su lista permitida; esto no equivale a una frontera de sistema operativo. El preflight protege contra la opción local de acceso fuera de workspace conocida, pero no demuestra el aislamiento efectivo del proveedor. La integración autenticada y el ciclo E2E siguen sin verificar. P1.4 y P1.5 permanecen sin aprobación final.

## Seguimiento Windows — fixture de detección de reparse points (2026-11-13)

- CI de P1.5/P2.6 ejecutó la suite completa en Windows/Python 3.12 y reportó estos fallos: `test_plan_rejects_junction_at_worktree_storage_root` y `test_plan_rejects_windows_reparse_attribute_without_junction_api` (`ValueError not raised`). Linux/Python 3.11 y 3.12 pasaron; Windows/Python 3.11 quedó cancelado por la matriz.
- `plan()` resuelve el root de Git antes de derivar el directorio; las dos fixtures comparaban rutas sin canonicalizar. Ajusté solo esas comparaciones para normalizar rutas. El detector de producción no cambió.
- PASS CI — run [#281](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/43439961447), commit `c5d3f135fe65f98e80889a5aaaaaf700dbf45069`: 4/4 jobs Windows/Ubuntu × Python 3.11/3.12. PASS local — los dos casos focalizados, validador de skill, `compileall` y `git diff --check` en Windows/Python 3.14. Python 3.12 no está instalado localmente.
- La reproducción local adicional de `tests.test_integration_candidate` se canceló tras 17 de 65 casos; no equivale a suite completa. El CI terminó 684 pruebas en 1011.6 s con los dos fallos citados.
