# Catálogo opt-in de extensiones

El catálogo SSEC es un archivo JSON local y versionado. Se consulta únicamente cuando el usuario selecciona explícitamente una ruta y ejecuta `scripts/extension_catalog.py validate`. La versión inicial solo valida metadatos: no descarga, instala, importa ni ejecuta extensiones o skills.

```powershell
python scripts/extension_catalog.py validate examples/extension_catalog.json
```

La salida `VALID_METADATA_ONLY` acredita únicamente que el documento satisface el contrato v1. No declara confiable una extensión ni verifica el contenido remoto.

## Contrato v1

La raíz contiene exactamente `schema_version: 1` y `extensions`. Cada entrada requiere:

- `id`, `name` y versión estable `MAJOR.MINOR.PATCH`.
- `source.url` HTTPS sin credenciales/query/fragment, un `source.commit` Git completo de 40 caracteres y `source.sha256` del artefacto.
- `maintainer` y `license`, como declaraciones de metadatos. El validador no autentica al mantenedor ni interpreta la licencia.
- `capabilities` declaradas y `permissions` del conjunto explícito: `read_project`, `write_project`, `run_process`, `network`, `secrets_access`.
- `review` con estado `approved`, revisor distinto del mantenedor, fecha UTC y digest del informe.
- `rollback` con una versión, commit y SHA-256 anteriores distintos a la versión actual.

Se rechazan campos desconocidos, IDs repetidos o mal formados, versiones fuera del formato admitido, rollback que no sea de una versión anterior, pins mutables y entradas sin revisión o rollback. El lector limita el archivo a 1 MiB y el catálogo a 1000 entradas. El catálogo vacío de `examples/extension_catalog.json` es deliberado: todavía no hay una extensión de terceros aprobada.

## Límites de confianza y actualización

Los commits y digests fijan identificadores declarados; el digest no se contrasta con bytes remotos y no demuestra autoría, licencia, seguridad ni integridad de la revisión. Los campos de revisión tampoco tienen firma criptográfica. Antes de habilitar una futura instalación, una persona debe comprobar la fuente, el artefacto, la licencia, los permisos y la revisión por un canal independiente. Cualquier descarga, instalación, actualización o rollback necesita un flujo separado con aprobación explícita. No se admite autoejecución.

La lista de permisos es cerrada para esta versión. Agregar un permiso requiere una nueva revisión del contrato, documentación y pruebas de seguridad; no debe interpretarse como capacidad otorgada por el validador.
