# SSEC Panel local — configuración de proveedores y especialistas

## Propósito

Permitir configurar **Gemini solo, Codex solo o ambos** desde una GUI local (Tkinter, estándar Python) en Windows y Linux. El panel no instala paquetes, no invoca proveedores, ni modifica proyectos sin una acción explícita del usuario.

## Abrir el panel

Desde la carpeta de la skill, con Python 3.11 o superior:

```bash
python scripts/config_panel.py
```

En Linux, instalar `python3-tk` cuando el Python local no tenga Tkinter. Se necesita una sesión gráfica. El comando `python scripts/config_panel.py --check` prueba el modelo de configuración sin abrir ventanas ni requerir Tkinter.

1. Selecciona el directorio local de tu proyecto (existente).
2. Selecciona el Task Packet JSON de trabajo (hay un ejemplo SEIR).
3. Elige proveedor: `gemini`, `codex`, `both` o `agy`.
4. Fija el **máximo simultáneo** de subagentes (1–12). No elimina expertos obligatorios: los organiza por tandas (`waves`) y los auditores quedan después de implementación.
5. Elige permisos **solicitados**: `read_only`, `propose_patches` o `request_write_approval`.
6. Especifica presupuesto **orientativo**: minutos y coste estimado en USD.
7. Auditoría `basic`, `standard` o `strict`: con R2/R3 nunca se elimina la revisión científica/seguridad indispensable; strict añade revisión de seguridad e independencia aun para riesgo bajo.
8. **Previsualizar** sin cambiar archivos; **Guardar configuración** escribe `.ssec/config.json` solo al confirmarlo; **Preparar perfiles** genera perfiles del proveedor y `.ssec/tasks/` según el modo. Cada acción tiene su confirmación cuando corresponde.

Si un perfil o packet existe y difiere, se detiene sin sobreescribir. Usa un `task_id` nuevo para una misión nueva o retira manualmente perfiles viejos tras auditarlos; no se eliminan automáticamente.

### Usar una configuración guardada sin GUI

```bash
python scripts/prepare_agents.py examples/seir_desktop_audit.json --config /ruta/proyecto/.ssec/config.json --project /ruta/proyecto
python scripts/prepare_agents.py examples/seir_desktop_audit.json --config /ruta/proyecto/.ssec/config.json --project /ruta/proyecto --apply
```

Si se pasa `--mode` y `--config`, deben coincidir.

## Alcance real: seguridad y presupuesto

- El modo `agy` usa AGY para workers y Codex para reviewers; sus perfiles de worker solo permiten herramientas de archivo. Las propuestas de workspace no usan AGY.
- El **máximo paralelo** determina *tandas del plan*, NO limita hilos reales de Codex/Gemini/AGY. El coordinador futuro deberá aplicar límites nativos de cada proveedor y registrar ejecuciones.
- Los **permisos del panel son instrucciones**, no permisos efectivos del SO ni del CLI. En Codex los subagentes heredan la política del agente principal. La política deberá implementarse en la raíz/sandbox.
- El coste y tiempo son **presupuestos indicativos**: sin integración con métricas reales ni mecanismo para detener procesos, no hay garantías de límite de consumo.
- `PREPARED_NOT_EXECUTED` es intencional: un archivo creado no significa que haya corrido un agente, auditoría o prueba científica.
- `read_only` solicita trabajo sin escritura; no ejecuta código de forma aislada.
- Configuración y packets pueden incluir texto privado; no los subas a repositorios públicos sin revisar.
- No declaramos validación visual real de la ventana en CI: se valida la lógica sin pantalla en Windows/Linux y debe hacerse un smoke manual en los escritorios de destino.

## Próximas integraciones

El panel separa configuración, confirmación de ejecución y supervisión. Sus etiquetas de progreso reflejan estados de procesos y nunca equivalen a aprobación ni a sandbox efectivo.

## Ejecutar una auditoría real (v0.2-dev.3)

Botón **4 · Ejecutar auditoría**: exige `kind=audit`, solicita confirmación explícita del gasto no medido, guarda la configuración y ejecuta el runner en un proceso independiente. Botón **Cancelar**: crea una señal que el runner comprueba mientras espera a sus procesos. El panel no permite ejecución real de tareas `build` o `debug` todavía. Consulte `references/RUNNER.md` para límites y logs.

Durante la ejecución, la barra y tabla muestran estados por especialista a partir de eventos JSONL schema v1 del runner; el registro de texto combinado permanece visible. `EXIT_ZERO_UNREVIEWED` es solo una salida de proceso normal y la interfaz conserva `NOT_APPROVED`. El parser ignora líneas mal formadas, versiones desconocidas y eventos que reclamen aprobación.
