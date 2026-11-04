# Contribuir a SSEC

SSEC está en desarrollo experimental. Los cambios deben conservar evidencia verificable y los límites científicos/de seguridad del contrato maestro.

## Antes de cambiar código

1. Lee `docs/CODEX_MASTER_MISSION.md`, el estado relacionado de `docs/roadmap/FEATURE_MATRIX.md` y los contratos que tocarás.
2. Reproduce el problema o la prueba más pequeña pertinente. Define archivos y criterios de aceptación.
3. Trabaja en una rama aislada (`codex/<incremento>`) o worktree propio. No sobrescribas cambios de otra tarea.
4. Escribe una regresión específica antes de corregir comportamiento. No amplíes dependencias o seguridad fuera del riesgo demostrado.

## Dependencias

El núcleo/CLI se validan con Python 3.11 o posterior y biblioteca estándar. PySide6 y Qt WebEngine son opcionales; el repositorio aún no tiene lockfile para ellos. No instales, agregues ni actualices software externo sin aprobación. Una propuesta de dependencia debe incluir versión exacta, fuente, licencia, mantenimiento, motivo frente a la biblioteca estándar, pruebas y rollback.

No guardes credenciales, tokens, datos privados del usuario, resultados científicos confidenciales ni capturas sin autorización. No descargues o ejecutes skills de terceros durante tests.

## Verificación local

Ejecuta checks enfocados durante el cambio:

```bash
python scripts/validate_skill.py
python -m compileall -q scripts tests
python -m unittest tests.test_structure -v
```

Agrega la suite pertinente al área modificada, por ejemplo `tests.test_scientific_core`, `tests.test_scientific_workspace` o `tests.test_scientific_control_center_qt`. Antes de proponer una integración amplia, intenta la suite completa:

```bash
python -m unittest discover -s tests -v
```

Si una suite no termina en el entorno disponible, registra el tiempo observado y `NOT_RUN`; no la declares pasada. Para interfaces, registra si se probó en escritorio real, headless o solo mediante fixtures. CI cubre Windows/Ubuntu × Python 3.11/3.12; no reemplaza la evidencia local del frontend en la plataforma destino.

## Evidencia científica

Reporta por separado `SOFTWARE_VALIDITY`, `NUMERICAL_VALIDITY` y `SCIENTIFIC_VALIDITY`. Declara solver, tolerancias, unidades, configuración, procedencia y límites. Fixtures sintéticas sirven para probar contratos y reproducibilidad; no prueban adecuación científica, identificabilidad, causalidad ni validez de datos del usuario. Preserva literalmente estados como `STALLED`, `NOT_RUN`, `NOT_ASSESSED` y `NOT_CALCULATED`.

No afirmes que hashes autentican origen, que procesos CLI están aislados por el sistema operativo o que una salida de proveedor es revisión independiente sin evidencia correspondiente.

## Branches y pull requests

- Mantén un incremento por branch/PR y usa una base explícita cuando el cambio esté apilado.
- Describe comportamiento, archivos, comandos/entornos y límites. Adjunta artefactos visuales solo cuando corresponda.
- Distingue `PASS`, `FAIL`, `BLOCKED` y `NOT_RUN`; no sustituyas pruebas reales por mocks cuando el criterio exige runtime real.
- No hagas merge a `main`, publiques tags/releases, cambies licencia ni habilites auto-merge sin autorización del propietario.
- Antes de cerrar, comprueba que el PR corresponde a la rama y base previstas y que no incluye archivos de otras tareas.

## Licencia

El repositorio no contiene un archivo `LICENSE`; la decisión del propietario y los términos de contribución siguen pendientes. No infieras que el código puede redistribuirse o relicenciarse. Esa decisión debe resolverse antes de una release pública.
