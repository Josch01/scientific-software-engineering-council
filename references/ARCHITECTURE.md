# Arquitectura evolutiva

Priorizar modularidad por límites y contratos; no microservicios por defecto.

```text
apps/desktop_ui      -> application/service API
apps/cli             -> application/service API
application/         -> domain/core + ports
scientific_core/     -> modelos, solvers, objetivos, estimadores (sin GUI)
adapters/            -> filesystem, datasets, IDL, GPU, formatos
experiments/         -> presets, seeds, benchmarks, reports
qa/                  -> tests, fixtures, oráculos, baselines
```

Dirección de dependencias: GUI/CLI -> aplicación -> dominio; adaptadores implementan puertos. El núcleo no importa PySide6 ni IDL ni servicios de red. Definir especificaciones de entradas/salidas con tipos, unidad física, forma/dtype, semántica de tiempo, tolerancias y errores.

Elegir Python primero donde ya exista ecosistema NumPy/SciPy; IDL tiene adaptador propio, no una obligación universal. Añadir C++/Rust/Numba/JAX/PyTorch/Julia sólo tras perfiles y un requisito concreto. Rechazar mezcla accidental de backends, copias de arrays opacas o mutabilidad global.

Crear un ADR por decisión de arquitectura material: problema, alternativas, evidencia, decisión, tradeoffs, fecha y criterio de reversión. Mantener interfaces versionadas para evoluciones futuras y rutas de migración controladas.

Previo a agregar paralelismo: determinar si el cuello es Python, BLAS, I/O, GPU, solver o comunicación. Limitar oversubscription, preservar seeds reproducibles y analizar serialización/cancelación.
