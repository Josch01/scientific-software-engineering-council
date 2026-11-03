# Diseño P3.3: espacio científico dinámico en Tkinter

## Intención

Dar una primera interfaz de escritorio que abra un proyecto científico desde el manifiesto versionado, use exclusivamente los bytes capturados por el loader P3.2 y configure secciones/vistas a partir del manifiesto. El mismo núcleo debe servir para proyectos distintos sin código de interfaz por modelo.

## Objetivos

- Conservar la definición validada del manifiesto en `LoadedWorkspace`, sin volver a abrir el manifiesto.
- Mostrar secciones y componentes con un registro cerrado de renderers aprobados.
- Representar simulaciones conocidas como gráficas con tabla de datos visible; representar observaciones con unidades y procedencia.
- Mostrar formatos sin contrato de renderer como JSON/texto acotado e inerte.
- Ofrecer CLI `--check` sin GUI para CI y CLI de escritorio para uso local.
- No agregar dependencias externas ni ejecutar Python, callbacks, HTML u otros artefactos cargados.

## No objetivos

- No implementar un runner, scheduler o flujo de agentes desde la GUI.
- No inferir ecuaciones o parámetros que no estén en el modelo entregado.
- No afirmar precisión, identificabilidad, validez matemática o validez científica por renderizar o graficar un artefacto.
- No completar el caso SIR específico mientras falten ecuaciones, unidades, condiciones iniciales y datos.

## Enfoques considerados

1. **Tkinter + registro fijo de componentes (elegido):** reutiliza la base GUI existente y la biblioteca estándar; mantiene estable el núcleo, funciona con el manifiesto y no instala paquetes. Cada renderer recibe bytes verificados y produce solo controles/datos declarados.
2. **Aplicación web embebida:** más flexibilidad visual y ecosistema de gráficas, a cambio de un runtime/dependencias y puente local que no hacen falta para el primer ciclo.
3. **Vistas generadas por código de agentes:** máxima flexibilidad, pero requiere aislamiento efectivo y revisión de código ejecutable; contradice la política del prototipo.

## Arquitectura elegida

El loader agregará una copia recursivamente inmutable del manifiesto ya validado al resultado capturado. Una capa de presentación pura transformará esa definición y los bytes de `LoadedResource` en modelos de vista limitados. La app Tkinter compondrá pestañas por sección y widgets mediante un mapa fijo `component type -> renderer`. Las vistas de simulación admitirán únicamente el contrato de salida v1 de `scientific_core`; observaciones usarán su parser de contrato. Otros recursos se mostrarán como JSON/texto plano truncado, sin interpretación ni ejecución.

La GUI destacará el estado como artefactos cargados/digests coincidentes y mostrará que representación gráfica no equivale a evaluación científica. Los controles conservarán orden de teclado y foco visible; las gráficas incluirán tabla textual de datos y leyenda, con marcas de series distintas además de color.

Límites iniciales de vista: 100 componentes en la ventana, 1 MiB por recurso JSON, 2 MiB de JSON únicos por espacio, preview JSON de 32 KiB, código/texto de 256 KiB, 1.000 filas visibles y 5 series en la gráfica. La tabla conserva todas las series configuradas; los recortes se anuncian y los bytes originales permanecen sin modificar.

## Decisiones abiertas al implementador

- `--check` valida carga, decodificación segura y despacho de todos los componentes sin inicializar Tk.
- El primer incremento no ejecutará callbacks ni implementará vistas interactivas de análisis; la incertidumbre seguirá siendo un resumen del artefacto que exista.
- La interfaz visual real queda `NOT_RUN` si el entorno no permite abrir una ventana; no se sustituye por un test simulado.

