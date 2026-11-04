# P3.10 — dispatch de auditoría desde workspace verificado

> Incremento ejecutado de forma nativa y acotada. No se harán llamadas reales a proveedores.

**Objetivo:** solicitar auditoría de los recursos seleccionados de un `LoadedWorkspace` sin incluir otros archivos del proyecto.

**Arquitectura:** construir un task `audit` desde recursos validados, stage de bytes SHA-256 en una raíz temporal, ejecutar el supervisor con una lista explícita de archivos y guardar provenance en `run_summary.json`. La app pide confirmación humana y ejecuta en un worker thread.

## Revisión focal

- IDs desconocidos/duplicados, workspace falso, digest alterado, archivo vacío o selección fuera de límites falla antes de crear runtime.
- Un archivo ajeno al workspace no aparece en ningún snapshot de rol.
- Un runtime falso con exit 0 nunca produce aprobación ni claim de validez científica.
- Cancelación/timeout/fallo y excepción Tk muestran un estado terminal.

## Tareas

### 1. Contrato y bundle verificado

**Archivos:** módulo nuevo `scripts/scientific_workspace_audit.py`; tests focales.

- [x] Añadir tests RED para selección explícita, task/digest, exclusión por política runner y staging solo de bytes verificados.
- [x] Implementar un plan inmutable y construcción de task de auditoría con IDs/rutas/digests.
- [x] Verificar que el staging efímero no reabre rutas del manifiesto ni incluye archivos no seleccionados.

### 2. Supervisor confinado a snapshot temporal

**Archivos:** `scripts/run_agents.py`, tests de runner/provider.

- [x] Reutilizar `run_agents.execute` sin cambiar su escaneo global: crear una raíz temporal nueva con únicamente la allowlist y comprobar que el runner descubre exactamente ese conjunto. Persistir provenance en el resumen local.
- [x] Probar con proceso fake que cada especialista ve exclusivamente el bundle, y que éxito y fallo permanecen `NOT_APPROVED`.

### 3. UI con confirmación y resultados

**Archivos:** `scripts/scientific_workspace_app.py`, tests app.

- [x] Añadir acción de auditoría habilitada solo con workspace/proyecto verificado; mostrar recursos y coste no medido antes del ACK humano.
- [x] Ejecutar en background, exponer cancelación y publicar resultados/errores terminales que distinguen proceso de revisión y validez científica.
- [x] Mantener simulación/propuestas bloqueadas durante el run; callbacks de proyecto siguen sin ejecutarse.

### 4. Cierre

**Archivos:** feature matrix, informe P3.10, plan.

- [x] Ejecutar pruebas focales y suite de workspace/runner; `py_compile` y `git diff --check`.
- [x] Revisión independiente acotada; corregir los defectos importantes reproducibles.
- [x] Commit separado `9ba4123`, push y PR draft #34 apilado sobre #31. Registrar CI; no merge ni release.
