# IDL — Interactive Data Language (NV5)

La integración oficial es `IDL <-> Python Bridge` (`idlpy` / `PYTHON`). Determinar versión IDL y Python soportadas y licencia antes de diseñar tests/packaging. No afirmar que IDL está disponible sin detectarlo en el equipo.

- Priorizar una interfaz de funciones explícita para algoritmos con entradas/salidas tipadas y expectativas de shape.
- El bridge permite traducciones de arrays, pero examinar orden de memoria, casos degenerados, conversión de NaN/float64, referencias, tipos y excepciones.
- Para desacoplamiento fuerte o ejecución remota considerar ficheros intercambiables con esquema versionado; no asumir que todas las estructuras pasan sin pérdidas.
- Pruebas Python del esquema siempre. Pruebas de integración IDL sólo en equipo con instalación y licencia adecuadas; CI sin IDL debe registrar `NOT_RUN`, no `PASS`.
- Registrar diagnóstico de versión de IDL/Python, plataforma, PATH/configuración/variables y límites del bridge.

Documentación oficial: https://www.nv5geospatialsoftware.com/docs/Python.html y https://www.nv5geospatialsoftware.com/docs/pythontoidl.html
