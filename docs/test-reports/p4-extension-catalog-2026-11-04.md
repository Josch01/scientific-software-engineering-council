# P4.2 — Catálogo opt-in de extensiones

**Estado:** `EXPERIMENTAL`. Se implementó el contrato JSON v1 y un CLI local de validación de metadatos. No hay instalaciones, descargas ni ejecución de código.

## Cambios

- `scripts/extension_catalog.py` valida pins HTTPS + commit completo + SHA-256 declarado, versión estable, mantenedor, licencia declarada, capacidades, permisos enumerados, revisión aprobada con digest y rollback a una versión menor.
- Rechaza claves desconocidas, referencias no fijadas, URLs con credenciales/puerto inválido, revisión del mismo mantenedor, IDs duplicados y catálogos mayores de 1 MiB / 1000 entradas.
- El CLI `python scripts/extension_catalog.py validate <archivo>` solo lee JSON local y devuelve `VALID_METADATA_ONLY`.
- `examples/extension_catalog.json` está vacío intencionalmente; no se han aprobado extensiones de terceros.
- `scripts/validate_skill.py` ahora verifica el nombre canónico del paquete y funciona desde worktrees con nombres de directorio propios.

## Verificación

- Prueba TDD inicial para rechazar rollback más nuevo: falló antes del arreglo y pasó después.
- Prueba TDD inicial para URL con puerto inválido: falló antes del arreglo y pasó después.
- La revisión independiente reprodujo tres defectos P2: claves JSON duplicadas, timestamp UTC no canónico y `RecursionError` en JSON anidado. Las tres regresiones fallaron antes del arreglo y pasaron después; la re-revisión confirmó que quedan corregidas sin hallazgos P0–P2 residuales en estos casos.
- Windows, Python 3.14.0: `python -m unittest tests.test_structure tests.test_extension_catalog -v` — **14/14 OK**.
- `python scripts/validate_skill.py` desde el worktree — **PASS** tras fijar la comparación con el nombre canónico de la skill.
- `python scripts/extension_catalog.py validate examples/extension_catalog.json` — **PASS**, `VALID_METADATA_ONLY: 0 extension(s)`.
- `python -m compileall -q scripts tests` y `git diff --check` — se repetirán antes del commit.
- Re-revisión independiente: `python -m unittest tests.test_extension_catalog -v` — **13/13 OK**; confirmó los tres arreglos.
- CI remoto de este PR: pendiente.

## Límites

Los commits y SHA son declaraciones; no se contrastan con artefactos descargados ni prueban procedencia. El estado de revisión no está firmado y el texto de licencia no se interpreta. No se crea una extensión ejecutable ni un instalador. El resultado no autoriza instalación: esa función requerirá un flujo separado con decisión humana y validación de código.
