# P1.4 — smoke real del adaptador AGY (2026-11-03)

## Alcance

Una única solicitud no modificadora por `AgyRuntime` validó la invocación local de `agy` y el parseo de su envelope JSON. No ejecutó el coordinador P1.4, no revisó un candidato de integración y no demuestra independencia de reviewer, identidad de cuenta, subagentes nativos o aislamiento efectivo. No se realizó una segunda llamada.

## Evidencia

| Campo | Resultado |
|---|---|
| CLI | `agy` 1.4.12 |
| Runtime | `AgyRuntime`, `writable=False`, `cost_acknowledged=True`, timeout 120 s |
| Proyecto | Temporal y vacío; tras la llamada seguía sin archivos |
| Entorno hijo | Se retiraron nombres de variables API key y variables de credenciales/proyecto Google; no se usó una API key |
| Resultado | `SUCCEEDED`, exit code 0, una vuelta, duración 5.673008 s |
| Sesión | `83a4c117-465c-4383-b6d5-16d1f2e65633` |
| Respuesta observada | `SSEC-AGY-P1.4-OK` |
| SHA-256 stdout | `04349b6639115c7e058f2f6d57ff7913789b1c7f639f899ede5ad7fa14aa947f` |
| SHA-256 stderr | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (vacío) |
| Estado de sandbox/delegación nativa | `UNKNOWN` |
| Uso de tokens/cuota | `NOT_RECORDED` por la CLI |
| Limpieza temporal | Sin error |

El registro conserva metadatos y hashes, no el transcript completo. Los resultados validan solo el protocolo de invocación del adaptador. La ejecución real previa con `GeminiRuntime`/`gemini` 0.64.0 falló con exit 41 y no se reintentó; se mantiene documentada en el [informe P1.4](p1-integrated-review-human-decision-2026-11-03.md). El reviewer integrado real sigue `NOT_RUN`.

## Límites de seguridad

`--mode=plan` y `--sandbox` son opciones solicitadas al proveedor, no evidencia de que el proceso careciera de permisos de escritura. Por ello el reporte no afirma aislamiento de archivos y el adaptador conserva `sandbox_effective=None`. No se observó modificación del proyecto temporal vacío, lo cual solo describe esta corrida.

La CLI reporta `conversation_id` y respuesta, pero esos campos no autentican identidad de cuenta ni el contexto del modelo. El consumo de cuota no fue informado y no se estimó.
