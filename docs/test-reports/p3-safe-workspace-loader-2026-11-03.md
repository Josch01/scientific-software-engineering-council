# P3.2 loader seguro de recursos de espacios científicos

**Estado:** implementación experimental, suite enfocada y revisión independiente completas; CI de la rama pendiente. No se construyó GUI ni se ejecutó un modelo SIR.

## Implementación

`load_scientific_workspace(project_root, manifest_relative_path)` reutiliza el parser estricto del manifiesto P3.1, abre el manifiesto y sus recursos relativos al root seleccionado, exige un SHA-256 declarado por recurso y devuelve `LoadedResource.content` como bytes inmutables solo después de que el digest coincida. Un error en cualquier recurso aborta toda la operación; los resultados no ofrecen una ruta que el consumidor tenga que reabrir.

En POSIX abre cada segmento desde descriptores relativos con `O_NOFOLLOW` y `O_NONBLOCK`, y rechaza todo archivo que no sea regular. En Windows rechaza symlinks/reparse points observados y comprueba la ruta final del mismo handle ya abierto; normaliza prefijos de ruta extendida/UNC y usa `commonpath` por componentes. El CLI imprime solo metadatos y el digest, nunca el contenido. El acceso está limitado a 16 MiB por recurso y 64 MiB total; la API permite reducir, no aumentar, esos límites.

El digest comprueba igualdad de bytes respecto al manifiesto recibido; no autentica al productor ni protege contra la sustitución coordinada del manifiesto y los datos. El loader mantiene los recursos inertes: no importa ni ejecuta código, interpreta CSV, renderiza vistas ni otorga una evaluación científica.

## Verificación

| Entorno | Comando | Resultado |
|---|---|---|
| Windows, Python 3.14.0 | `python -m unittest tests.test_scientific_workspace tests.test_scientific_workspace_loader -q` | PASS, 23 tests; 1 omitido por `WinError 1314` al crear el fixture symlink |
| Docker/Linux, `python:3.14.0-bookworm` | Mismo comando | PASS, 23 tests |
| Windows, Python 3.14.0 | `py_compile` de validador, loader y tests; `git diff --check` | PASS |
| Docker/Linux, Python 3.14.0, root montado como `/scientific-software-engineering-council` | `python -m unittest discover -s tests -q` | PASS, 373 tests; 6 omitidos; 130.821 s |
| Revisión independiente de seguridad | Diseño, parser, loader y tests | Sin hallazgos críticos/importantes reproducibles |

El intento inicial de suite Linux montó el root como `/workspace`; `test_structure` falló porque el bundle SSEC exige que el directorio coincida con el nombre del skill. El test pasó al repetir el mismo árbol con su nombre canónico. La suite completa Windows local quedó `NOT_RUN`: la primera ejecución desde el worktree comparte esa condición de nombre y la segunda, desde una copia temporal con nombre canónico, fue interrumpida sin resultado. Los tests Windows enfocados pasaron; la matriz CI de rama aún debe cubrir la suite completa.

La prueba local de escape por symlink en Windows también queda `NOT_RUN` por `WinError 1314`; Linux sí ejecutó y pasó el caso. No se inició un ciclo de cambios de privilegios.

## Límites y siguiente paso

- Integración de datos/matemática SIR `NOT_RUN`: el usuario aún no cuenta con ecuaciones, unidades, condiciones iniciales ni datos.
- El loader solo verifica archivos regular-bounded; no parsea el formato ni prueba consistencia entre artefactos.
- POSIX requiere `dir_fd`, `O_NOFOLLOW` y `O_NONBLOCK`; si faltan, rechaza la carga.
- No hay GUI, ejecución aislada, recuperación de cargas interrumpidas ni verificación de procedencia firmada.
- P3.1 y P3.2 siguen en PRs borrador apilados; no se hizo merge.

Antes de ampliar otro componente, confirmar si es necesario para el caso integral SIR.
