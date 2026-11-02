# Release Gate

Separar estados: `IMPLEMENTED -> TESTED -> INDEPENDENTLY_REVIEWED -> SCIENTIFICALLY_REVIEWED(if relevant) -> READY_FOR_MANUAL_REVIEW -> RELEASED_BY_HUMAN`.

Requisitos básicos: `unit_tests`, `static_analysis`. Para auditoría/reforma: `regression`. Para R2/R3: `scientific_validation`, `independent_review`. Para GUI: `gui_smoke`. Para distribución Windows/Linux: `cross_platform`. Para IDL: `idl_integration` (si requerida, bloquea release sin entorno licenciado; se puede ofrecer entrega parcial Python). Para R2/R3: `security_audit`.

Los registros de evidencia incluyen comando, código de salida, entorno, hora, ruta de log y SHA-256. El gate script valida que el registro coincide con archivos existentes y que los checks están declarados como `PASS`. Esto no prueba que el log sea auténtico ni que un test sea suficiente; se requiere revisión real.

Se bloquea release ante: fallos, `NOT_RUN`, evidencias ausentes, revisión contradictoria, licencias incompatibles, drift de contrato/semántica, cambios no autorizados o plataforma destino no verificada.

Política de publicación: versionado semántico, changelog, hashes de builds, provenance de datos/commits, matriz de OS, rollback e instrucciones de actualización. Los CI en GitHub sólo validan la skill; no equivalen a probar aplicaciones ajenas.
