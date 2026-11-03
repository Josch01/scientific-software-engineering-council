# P1.4 — Revisión integrada y decisión humana

## Intent

Completar el ciclo operativo de P1 después de los checks del candidato compuesto: ejecutar reviewers independientes sobre el mismo candidato integrado y permitir que una persona registre una decisión explícita ligada a la evidencia exacta. La operación no hace commit, merge ni release.

## Goals

- Reutilizar el adaptador y parser de revisión existentes con una nueva invocación de reviewer en snapshot de solo lectura del candidato integrado.
- Aceptar exactamente el roster `state["review_roles"]`; cada reporte debe ligar task/revision/digest/base, candidate tree, diff y manifiesto de checks del último intento integrado.
- Persistir sesiones de runtime del `execute()` para impedir reutilizar sesiones observadas de workers, reviewers previos o intentos integrados anteriores.
- Guardar un bundle de revisión versionado y separado del manifiesto checked de integración. Debe enlazar integration ID, hash del manifiesto integrado, candidate tree, check path/hash, roster y manifests de reviewer con sus hashes.
- Hacer que `gate()` distinga checks verificados, revisión integrada y decisión humana. Una revisión completa PASS queda `NEEDS_HUMAN`; la decisión humana queda ligada al digest completo del bundle vigente.
- Registrar `APPROVE_FOR_MANUAL_INTEGRATION` o `REJECT` en una decisión inmutable que nombra el integration ID, bundle digest, check digest, candidate tree, operador declarado, motivo y timestamp.
- Revalidar latest integration, candidato, checks, bundle y decisión en cada lectura. Un intento nuevo/incompleto, drift o digest viejo invalida cualquier decisión previa.
- Aplicar guardas reparse/junction-aware antes de resolver, leer o escribir metadata.

## No goals

- No GUI, scheduler DAG, recuperación durable general ni catálogo de plugins.
- No fix loop autónomo: un finding requiere cambios por workers y una nueva integración con ID nuevo. Cada comando de review es un intento acotado y observable.
- No proveedor E2E durante CI/esta implementación; no llamar Codex/Gemini en este trabajo ni instalar dependencias.
- No autenticación criptográfica de la persona operadora, sandbox del sistema operativo, validez científica ni aprobación de release.
- No commit, merge, push de producto ni publicación de versión por la herramienta.

## Approaches

1. **Reusar `_review_one()` por comando explícito y envolver los resultados en un bundle integrado versionado — elegida.** Evita volver a ejecutar workers y conserva límites, snapshot, parser y adaptadores; requiere validar cuidadosamente el enlace al último integration ID.
2. **Añadir la review integrada automáticamente al final de `execute()`.** Se descarta porque el comando volvería a lanzar workers y mezclaría costos del proveedor con una operación de review independiente.
3. **Solicitar review manual fuera de SSEC y guardar un veredicto en mailbox.** Se descarta porque el mailbox no autentica el reviewer ni liga su dictamen a los checks del candidato compuesto.

## Contracts and states

- `runtime-sessions.json`, schema 1: task identity, execution ID, estado terminal, sesiones observadas por rol/provider, y sessions de reviewers de worker. Escritura atómica al completar `execute()`; ausencia/inconsistencia bloquea integrated review.
- `integration-review.json`, schema 1: attempt ID ordenable, integration ID, digest del manifiesto integrado, candidate tree, check manifest path/hash, roster exacto y reviewer manifest path/hash/estado/verdict/session por rol.
- `human-decision.json`, schema 1: decision ID, integración, digest del review bundle, check digest, candidate tree, decisión, operator declarado, reason y timestamp UTC. Archivo inmutable por integración.
- Estados de gate: `BLOCKED` para evidencia ausente/inválida o findings que pidan cambios; `CHANGES_REQUESTED` cuando el roster reporta `REQUEST_CHANGES`; `NEEDS_HUMAN` cuando el bundle actual tiene todos los PASS válidos y no hay decisión; `APPROVED_FOR_MANUAL_INTEGRATION` o `REJECTED_BY_HUMAN` solo con decisión vigente validada.
- Siempre `automatic_merge=false` y `release_status=NOT_APPROVED`. `evidence_verified` califica evidencia de software/review solamente; `SCIENTIFIC_VALIDITY` queda independiente.

## Safety and limits

Todos los paths de artefactos se validan con guardas para symlink, junction y cualquier reparse point antes de `resolve()`/I/O. Reviewers usan el adaptador concreto del proveedor, un runtime nuevo por rol, snapshot no writable, deadline/cancelación y límites de prompt/diff vigentes. Sesiones se comparan contra inventarios persistidos; un identificador diferente no demuestra por sí mismo independencia de cuenta o contexto. Los manifests y nombre de operador son evidencia local editable por quien puede escribir en el almacén, no firmas digitales. La UI visual y los resultados científicos no forman parte de este incremento.
