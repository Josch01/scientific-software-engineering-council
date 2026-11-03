# Release Gate

Separar estados: `IMPLEMENTED -> TESTED -> INDEPENDENTLY_REVIEWED -> SCIENTIFICALLY_REVIEWED(if relevant) -> READY_FOR_MANUAL_REVIEW -> RELEASED_BY_HUMAN`.

Requisitos básicos: `unit_tests`, `static_analysis`. Para auditoría/reforma: `regression`. Para R2/R3: `scientific_validation`, `independent_review`. Para GUI: `gui_smoke`. Para distribución Windows/Linux: `cross_platform`. Para IDL: `idl_integration` (si requerida, bloquea release sin entorno licenciado; se puede ofrecer entrega parcial Python). Para R2/R3: `security_audit`.

Los registros declarados de evidencia incluyen comando, código de salida, entorno, hora, ruta de log y SHA-256. El gate script conserva la validación de campos, rutas y hashes de logs, pero esas comprobaciones no acreditan quién ejecutó el proceso ni una revisión independiente. Un JSON no puede declarar su propia procedencia verificada: `provenance_verified` en la salida siempre es `false` mientras no exista el productor de evidencia de ejecución del coordinador.

En este incremento P1.1a, el script devuelve `BLOCKED` y exit code 2 incluso con logs de fixture cuyos hashes coinciden, `PASS` declarado y IDs de contexto distintos. Falta implementar y validar el registro canónico de ejecución; este endurecimiento contra declaraciones falsas no completa P1.1. La revisión humana y los gates de validez científica siguen siendo requisitos separados.

Se bloquea release ante: fallos, `NOT_RUN`, evidencias ausentes, revisión contradictoria, licencias incompatibles, drift de contrato/semántica, cambios no autorizados o plataforma destino no verificada.

Política de publicación: versionado semántico, changelog, hashes de builds, provenance de datos/commits, matriz de OS, rollback e instrucciones de actualización. Los CI en GitHub sólo validan la skill; no equivalen a probar aplicaciones ajenas.
