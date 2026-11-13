# P3.21 — Acción Qt para ejecutar análisis SIR

## Objetivo y límites

Agregar al Centro de Control una acción humana para ejecutar el análisis declarativo SIR ya implementado en P3.20 y cargar el workspace resultante en la misma aplicación. Debe reutilizar `build_analysis_workspace` y sus contratos; no introduce algoritmos, proveedores de IA ni ejecución de código del proyecto. Los ejemplos y resultados siguen siendo sintéticos: incertidumbre `NOT_CALCULATED`/`NOT_ASSESSED`, SIR particular del usuario `NOT_RUN`.

## Decisiones

- **Ejecución:** trabajador Qt en segundo plano. Se descarta llamar el builder sincrónicamente porque puede congelar la interfaz. Se descarta subprocess como capa adicional porque el builder local ya valida entradas y registra procedencia.
- **Cancelación:** el cálculo existente no ofrece cancelación segura; no se mostrará una cancelación ficticia. La ventana impedirá cambiar de proyecto o cerrarse durante la ejecución y comunicará el estado real.
- **Confirmación:** antes de iniciar se presentarán el modelo, configuración, observaciones, parámetros y destino; `No` será la opción predeterminada. Confirmar indica que se añadirán resultados al proyecto.
- **Salida:** solo un subdirectorio nuevo o vacío, contenido bajo la raíz del proyecto. No se sobrescriben los recursos originales ni una ejecución previa. El manifiesto se carga de nuevo con la raíz original del proyecto para conservar la vista unificada con supervisor y workspace.
- **Presentación:** estado indeterminado mientras trabaja; al terminar se verifica/carga el workspace y se navega a Resultados. Los errores se muestran como errores y no se cambia la selección activa.
- **Compatibilidad Windows:** los JSON de entrada con hashes exactos deben conservar sus bytes durante el checkout; se aplicará `-text` solo al fixture sintético afectado.

## Alternativas visuales consideradas

1. Botón con confirmación y salida seleccionable, integrado en la página Workspace — elegido por ser una acción de proyecto auditable y mantener visibles los controles existentes.
2. Automatización al abrir el fixture — descartada: ejecutaría cómputo sin aprobación y confundiría abrir con ejecutar.
3. Acción de CLI solamente — descartada para este incremento porque ya existe en P3.20 y no satisface la ejecución directa desde el Centro de Control.

## Aceptación

- Rechazar no escribe resultados ni cambia de workspace.
- Aceptar ejecuta el motor real fuera del hilo GUI, genera una salida reproducible sin reemplazar entradas y carga en el mismo Centro de Control resultados de ajuste, sensibilidad y residuos.
- Un error se muestra y no se trata como éxito ni recupera resultados anteriores.
- Una segunda ejecución concurrente se bloquea; una salida existente no se sobrescribe.
- La incertidumbre y el SIR particular conservan estados no evaluados/no ejecutados.
- Hay pruebas Qt para aceptar, rechazar, fallo y carga; la suite afectada de Windows pasa con hashes de bytes estables.

## Riesgo conocido

El builder actual no reporta progreso fraccional ni acepta una señal de cancelación. Esta acción muestra actividad indeterminada y no ofrece cancelar. Añadir cancelación cooperativa requeriría cambios al motor que no son necesarios ni seguros para este primer flujo.
