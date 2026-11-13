# P3.26 · Refresco visual del Centro de Control Qt

## Intent

Mejorar la legibilidad y acabado del Centro de Control científico para que el
usuario pueda orientarse entre proyectos, agentes, experimentos, auditorías,
código y resultados, e interpretar las gráficas con claridad.

## Enfoque

Se conserva la ventana y controles nativos PySide6, y se mejora el renderizador
local SVG de Qt WebEngine ya usado por las gráficas. La alternativa de convertir
toda la aplicación a WebView agregaría un segundo sistema de navegación y
puentes entre JS y Python; una reescritura Qt Quick reemplazaría flujos ya
funcionales. No se eligen porque no son necesarios para este refinamiento.

## Diseño aprobado por la instrucción del usuario

- Fondo carbón moderado `#27262E`, navegación `#2D2B35`, panel `#34323D` y panel
  elevado `#3D3B47`; texto principal `#F5F2FA` y secundario `#CDC8D5`.
- Acento violeta `#B99AFF` con estados de hover/foco visibles. Estados de
  éxito, advertencia y error conservan colores semánticos legibles.
- Series con colores distinguibles, leyenda accionable, nombre/unidad en ejes,
  tooltip local y patrón de línea además del color.
- Jerarquía/espaciado de controles consistente, estados hover/pressed/disabled
  legibles y animación breve de cambio de página y entrada de líneas.
- `SSEC_REDUCED_MOTION=1` y `prefers-reduced-motion: reduce` desactivan
  movimiento no esencial. Sin CDN, red, fuentes remotas ni código de proyecto.

## Alcance y límites

- No modifica modelos, algoritmos, datos, criterios científicos ni flujo de
  aprobación; las demostraciones serán sintéticas y claramente indicadas.
- Mantiene Qt nativo como fallback y WebEngine local cuando esté disponible.
- Verifica colores, foco/reducción de movimiento, CSP y render visual en
  Windows. CI comprobará Linux; las afirmaciones científicas siguen sin cambio.
