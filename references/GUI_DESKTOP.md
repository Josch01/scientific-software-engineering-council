# GUI para Windows/Linux

Por defecto evaluar PySide6 (Qt for Python) para UI de escritorio; escoger otro framework sólo por necesidades claras o base existente. Separar `scientific_core` de `desktop_ui`; Qt nunca debe definir las ecuaciones científicas.

Flujo esperado: proyecto/experimento -> parámetros validados -> estimación de coste -> iniciar -> progreso, logs, pausas/cancelación -> tablas/plots -> comparación -> exportación reproducible.

- No ejecutar ODE, training o búsquedas grandes en el event loop; usar threads/processes con señales, mensajes y política de cancelación; evitar tocar widgets desde workers.
- Controlar BLAS/OpenMP/process pools y recursos GPU; impedir que un pool y una GUI multipliquen el CPU sin control.
- Para datasets grandes: paginación, lazy-load, decimación gráfica sin cambiar los datos reales.
- Visualización: ejes, unidades, leyendas, incertidumbre y separación entre datos y simulaciones.
- Configuración y resultados exportables/importables (JSON/CSV/HDF5/Parquet según necesidad), IDs, hashes, versión, seeds, tolerancias.
- Validación de UX: accesibilidad, teclado, pantallas DPI, Linux/Windows, modo oscuro si sirve, mensajes accionables, reconexión tras error.
- `pyside6-deploy` es opción oficial de packaging; probar ejecutables en runners/VM de cada OS, no inferir portabilidad sólo por compilar Linux.

Documentación actual: https://doc.qt.io/qtforpython-6/ y https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html
