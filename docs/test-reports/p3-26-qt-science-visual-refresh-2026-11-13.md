# P3.26 · Refresco visual del Centro de Control Qt

## Resultado

- Tema carbón moderado/morado más claro, aplicado con tokens compartidos a la
  ventana, workspace, controles y gráficas. Acciones primarias, hover, pressed,
  disabled y foco quedan diferenciados.
- WebEngine conserva su SVG local, CSP sin red y fallback QPainter. La leyenda
  muestra las series con color y patrón de línea; la gráfica permite alternar
  series y consultar puntos con mouse o flechas. La animación de entrada y la
  transición de página respetan movimiento reducido.
- La captura de demostración usa exclusivamente el workspace SIR sintético ya
  existente: [Centro de Control, 1440×920](assets/p3-26-qt-control-center-synthetic.png).

## Verificación

- `PASS` 69 pruebas focalizadas en Windows, incluidos shell, workspace, gráfico
  nativo, WebEngine local y tecla-flecha con valores sintéticos. Log:
  `%TEMP%\ssec_p3_26_qt_final_tests.log`.
- `PASS` compilación de módulos y pruebas modificados; `git diff --check`.
- `PASS` WebEngine muestra fondo `#34323d` y serie `#c6a7ff`; flecha derecha
  informa el punto sintético `t=1`, observado `8`, simulado `9`.
- `PASS` captura Qt nativa con Segoe UI existente del sistema; no se instalaron
  fuentes ni dependencias. El render offscreen no registra fuentes solo, por lo
  que se cargó Segoe UI en el proceso de captura.

## Límites

- Linux/CI pendientes al abrir el PR. La captura usa el fallback nativo porque
  el compositor WebEngine offscreen no produce una imagen utilizable en este
  entorno; WebEngine sí pasa su prueba de carga/render local e interacción.
- Modelo y datos reales de tesis: `NOT_RUN`; validez, identificabilidad e
  incertidumbre: `NOT_ASSESSED`. El screenshot no afirma nada científico.
- No se ejecutaron modelos proveedores ni se alteró el motor científico.

## Decisiones

- Se conserva PySide6 para el shell y Qt WebEngine local para gráficas; no se
  duplica la app en HTML/JS ni se agrega infraestructura.
- El mismo catálogo semántico de patrones se comparte con las gráficas Qt
  nativas, para no depender solo del color.
- Sin merge a `main` ni release.
