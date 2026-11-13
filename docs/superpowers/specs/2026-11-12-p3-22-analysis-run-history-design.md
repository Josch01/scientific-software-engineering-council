# P3.22 — Historial de corridas SIR

**Fecha:** 2026-11-12

## Intención

Permitir volver a resultados científicos previamente calculados desde el Centro de Control, distinguiendo con claridad una corrida histórica de una ejecución recién completada.

## Alcance

- Mostrar bitácoras P3.21 ordenadas por fecha, con identificador, estado y referencia al workspace de resultados.
- Permitir abrir solo corridas exitosas; volver a cargar el workspace mediante el loader seguro existente y comparar su SHA-256 con la bitácora antes de actualizar las vistas.
- Mostrar fallos, registros inválidos y resultados ausentes como no abribles, con un motivo breve.
- Etiquetar la vista cargada como histórica y conservar la navegación/proyecto actual.

## Decisiones y límites

- Se reutilizan el formato de bitácora P3.21, load_scientific_workspace y build_workspace_view_model; no se recalcula ni modifica ningún resultado. Solo se acepta la salida exacta generated/sir-analysis/<run_id>/workspace.json.
- Se examinan como máximo las 100 bitácoras más recientes, de hasta 65 536 bytes cada una, bajo generated/sir-analysis-runs; se rechazan enlaces/reparse points y JSON inválido. El loader vuelve a comprobar contención, recursos y hashes al abrir.
- Las bitácoras no están firmadas; el SHA-256 coteja el manifiesto cargado con el valor registrado, pero no certifica autenticidad ni validez científica.
- No se agregan CLI, proveedor, algoritmo científico, edición/borrado de logs ni scheduler. Las corridas del SIR del usuario siguen NOT_RUN; incertidumbre sigue NOT_CALCULATED y validez NOT_ASSESSED.

## Verificación

Pruebas deterministas para historial válido/fallido/dañado, rechazo de digest cambiado y flujo Qt que abre historial sin presentarlo como corrida nueva. No se ejecuta código de proyecto.
