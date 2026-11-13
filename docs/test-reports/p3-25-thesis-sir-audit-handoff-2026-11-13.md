# P3.25 · Handoff del SIR de tesis a auditoría

## Resultado

- Una corrida SIR calculada con entradas sintéticas puede generar un bundle de
  auditoría con contrato v1 y referencias SHA-256. El loader seguro valida los
  recursos antes de abrirlo en el selector de especialistas del Centro de
  Control.
- El bundle conserva el modelo, la serie de observaciones seleccionada, el
  resultado y los bytes exactos del modelo/adaptador. No copia ni modifica el
  JSON de entrada o el PDF de tesis. La selección del bundle y el envío al
  proveedor tienen confirmaciones separadas.
- El E2E recorre el cálculo sintético, creación y validación del bundle, su
  apertura en Qt y el límite de despacho; el servicio del proveedor está
  parcheado y no recibe llamadas externas.

## Verificación

- `PASS` 183 pruebas en 12 módulos focalizados de Windows; log:
  `%TEMP%\ssec_p3_25_thesis_audit_tests.log`.
- `PASS` compilación local y `git diff --check`.
- `PASS` CI [run #249](https://github.com/Josch01/scientific-software-engineering-council/actions/runs/43398035456): 4/4 jobs Windows/Ubuntu × Python 3.11/3.12.
- No se instalaron paquetes ni se invocó Codex, Gemini/AGY u otro proveedor.

## Límites

- CLI/proveedor real, modelo y datos reales del usuario: `NOT_RUN`.
- Validez científica, identificabilidad e incertidumbre: `NOT_ASSESSED`.
- QA visual Linux local: `NOT_RUN`; CI verde no equivale a validación visual WebEngine en Linux.
- El resultado sintético demuestra integración de software, no evidencia
  científica del modelo de tesis.

## Decisiones y seguimiento

- Se reutilizan workspace v1, loader y selector/confirmación de auditoría
  existentes. La creación del bundle no implica aprobación de resultados.
- La siguiente entrega visual P3.26 se mantiene separada para revisión de UI.
- Sin merge a `main` ni release.
