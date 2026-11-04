# P3.11 — generación de propuestas de workspace

**Estado:** implementación local terminada; revisión independiente atendida; PR draft creado y CI pendiente. No se hizo merge ni se publicó una release.

## Capacidad

La GUI ofrece **Proponer cambios con IA**, objetivo libre y selección de recursos verificados. Tras confirmación explícita de posible consumo de cuota, el servicio prepara un snapshot temporal que incluye únicamente los bytes seleccionados y el contexto estructurado pertinente. La respuesta se acepta solo como JSON delimitado, se valida contra el contrato existente y se guarda como candidato `NOT_APPROVED`/`NOT_ASSESSED`. El flujo vuelve al diff completo y la aprobación humana ya implementados; esa aprobación guarda una copia canónica y no reemplaza el original. La importación manual JSON continúa disponible.

## Seguridad y decisión de proveedor

La revisión independiente señaló correctamente que el prompt y `writable=False` no impiden que un CLI ejecute comandos. El modo de Codex `--sandbox read-only` restringe escrituras, pero no deshabilita la ejecución de comandos. Para respetar el requisito de no ejecutar código generado, SSEC no invoca Codex en esta acción, incluso si está configurado o disponible; `provider_mode=both` solo considera Gemini.

Gemini solo se lanza cuando la CLI anuncia `--approval-mode plan` y `--admin-policy`, y no hay políticas administrativas del sistema que puedan desplazar la política temporal. Esa política deniega herramientas en general, deniega MCP, y permite únicamente `read_file`, `list_directory`, `glob` y `grep_search`. Cuando esas condiciones no se cumplen, la ejecución termina `PROVIDER_UNAVAILABLE` y no inicia el proceso de modelo. Esta garantía se limita a las políticas de herramientas del CLI; no se presenta como aislamiento de sistema operativo.

## Evidencia

- Plataforma local: Windows, Python 3.14.
- Comando: `python -m unittest tests.test_scientific_workspace_generation tests.test_scientific_workspace_proposals tests.test_scientific_workspace_audit tests.test_scientific_workspace_app tests.test_scientific_workspace_actions tests.test_scientific_workspace_loader tests.test_scientific_workspace_view tests.test_scientific_workspace tests.test_provider_runtimes -q`.
- Suite workspace/proveedor/GUI en Windows 10, Python 3.14: **158 tests, 0 fallos, 1 omitido**. La omisión es la aserción de contención por symlink que requiere un privilegio que Windows no concedió (`WinError 1314`).
- `py_compile` de módulos y pruebas modificados: **PASS**; `git diff --check`: **PASS**.
- Revisión independiente: el prompt y `writable=False` no garantizaban que el CLI careciera de ejecución. Se añadió política efectiva de herramientas solo lectura para Gemini y se bloqueó Codex en esta acción. La revisión no hizo llamada de modelo.
- La detección local sin modelo encontró Gemini CLI `0.64.0`, con `plan` y `--admin-policy`, y sin políticas administrativas estándar que desplacen la temporal. Esto acredita solo el sondeo de versión/ayuda, no una ejecución real del agente.
- Los tests usan runtimes falsos y propuestas deterministas. No se hizo llamada a Codex, Gemini ni AGY; la prueba E2E con proveedor real queda `NOT_RUN`.
- Ecuaciones, unidades, condiciones iniciales y observaciones del SIR del usuario no se han recibido; ese caso científico concreto permanece `NOT_RUN`.

## Limitaciones y próximos pasos

- Codex CLI queda pendiente para propuestas hasta que el adaptador pueda deshabilitar comandos y herramientas de escritura de forma comprobable.
- Gemini no se invoca si la política administrativa temporal no puede aplicarse con prioridad efectiva.
- SSEC no mide ni limita la cuota del proveedor. La confirmación informa el riesgo, pero no estima coste.
- La propuesta configura componentes reutilizables; no genera ni ejecuta código de modelo.
- No hay pruebas reales de proveedor, compatibilidad de cuenta, validez matemática, identificabilidad ni validez científica.
- PR draft P3.11 queda abierto; CI de plataforma queda pendiente de registrar.
