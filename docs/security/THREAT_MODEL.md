# Modelo de amenazas SSEC

**Fecha:** 2026-11-04  
**Alcance:** skill portable, CLI local, supervisión multiagente, worktrees, contratos de workspace científico y aplicación Qt opcional. Este documento registra controles observados; no es una auditoría de seguridad independiente ni certificación.

## Activos y límites de confianza

- **Activos:** código y datos del proyecto, credenciales locales, archivos seleccionados para proveedores, estado de los trabajos, manifiestos, logs, resultados científicos y decisiones humanas.
- **Entrada no confiable:** prompts, repositorios y archivos del usuario, propuestas de agentes, mensajes de workers, metadatos de extensiones y evidencia declarada.
- **Proveedor local:** Codex/Gemini u otro CLI ejecutado con la cuenta y permisos del usuario. La interfaz local no constituye aislamiento; el prompt y los recursos seleccionados pueden transmitirse al proveedor y el consumo de cuota no se puede limitar con precisión desde SSEC.
- **Worktree y proceso:** los worktrees separan cambios de archivos y detectan conflictos, pero los procesos siguen usando permisos del usuario. No son un sandbox del sistema operativo.
- **Frontera de evidencia:** los logs y JSON viven en el equipo y pueden modificarse por quien tenga acceso. SHA-256 detecta diferencias respecto al hash registrado, no autentica autor, proceso ni contexto.
- **Frontera científica:** una ejecución reproducible es evidencia de software/numerics bajo su configuración; no demuestra adecuación del modelo, identificabilidad, incertidumbre válida ni verdad científica.

## Amenazas y controles observados

| Amenaza | Control/evidencia existente | Límite residual |
|---|---|---|
| Un worker falsifica `TEST_PASS`, revisión o aprobación | El coordinador filtra eventos privilegiados; las pruebas rechazan auto-revisión y eventos falsos (`tests/test_development_worktrees.py`). | El sistema no autentica criptográficamente identidades locales ni un usuario que pueda editar el mismo estado. |
| Cambios concurrentes o proyecto de origen modificado | Los worktrees y validaciones comparan la base, el estado dirty y colisiones (`tests/test_development_worktrees.py`). | No protegen contra un usuario con control del host ni sustituyen revisión de cada diff. |
| Rutas fuera de la raíz, symlinks o recursos alterados | El loader vuelve a comprobar contención y digest antes de leer recursos (`tests/test_scientific_workspace_loader.py`). | La creación de symlinks en Windows depende de permisos; esa ruta queda `NOT_RUN` cuando el fixture recibe `WinError 1314`. Los hashes no prueban procedencia. |
| Secretos en snapshots o datos enviados al proveedor | El snapshot excluye secretos conocidos (`test_snapshot_excludes_known_secrets` en `tests/test_runner.py`); la UI de propuesta requiere confirmación antes de invocar al proveedor. | No hay escáner exhaustivo de secretos. La confirmación no demuestra que el usuario entendió cada archivo ni limita cuota/costo. |
| CLI ausente, colgado, cancelado o con procesos hijos | Hay estados explícitos para CLI ausente y pruebas de timeout, cancelación y limpieza de procesos (`tests/test_runner.py`, `tests/test_provider_runtimes.py`). | El comportamiento depende de OS/proveedor; no afirma terminación absoluta ante todos los fallos del host. |
| Código de agente ejecutado como parte de un workspace científico | La acción ejecuta solo callbacks registrados por el host y exige confirmación humana (`tests/test_scientific_workspace_actions.py`); las propuestas de agente muestran diff y requieren aprobación (`tests/test_scientific_workspace_qt_proposals.py`). | No existe runner aislado para código generado. No importar ni ejecutar callbacks de proyecto sin revisión humana. |
| Extensión maliciosa | El catálogo P4.2 valida solo metadatos; no descarga, instala, importa ni ejecuta extensiones. | Los pins, licencia y revisión son declaraciones, no firmas ni autenticación del maintainer (`docs/test-reports/p4-extension-catalog-2026-11-04.md`). |
| Evidencia inventada usada para liberar | `scripts/release_gate.py` bloquea evidencia auto-declarada mientras falte procedencia canónica; las pruebas cubren hashes, rutas y contextos declarados (`tests/test_release_gate.py`). | Revisión integral independiente del código, escaneos automatizados y benchmarks de tres proyectos: `NOT_RUN`. El gate no es un attestor criptográfico. |
| Resultado científico sobreinterpretado | Contratos y vistas conservan estados como `STALLED`, `NOT_ASSESSED` y `NOT_CALCULATED`; fixture SIR sintético reproducible. | El SIR y datos del usuario no se han recibido; validez científica, identificabilidad e incertidumbre permanecen `NOT_ASSESSED`. |

## Revisión y respuesta

El informe P4.4 registra las pruebas y límites concretos. Una revisión independiente acotada comprobó la consistencia documental de ese informe sin revisar toda la base de código. Por tanto, la revisión integral de seguridad sigue `NOT_RUN`; no se debe usar este modelo como autorización de release.

Ante un hallazgo reproducible de acceso a recursos no autorizados, ejecución automática de código, falso PASS o aprobación no humana, se bloquea la función afectada hasta corregirlo. Las limitaciones restantes se conservan como `NOT_RUN`/`UNVERIFIED` y se resuelven antes de afirmar que una plataforma o uso está listo.
