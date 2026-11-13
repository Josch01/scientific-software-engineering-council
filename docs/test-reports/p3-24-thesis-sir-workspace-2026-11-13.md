# P3.24 · Espacio SIR de tesis en el Centro de Control

Estado: implementación local en Windows; PR draft pendiente.

## Entrega

- Añade la ruta «SIR de tesis» con diseño carbón/morado del Centro de Control,
  paneles separados para configuración y resultados, y ajuste de tamaño con
  divisor.
- Importa el JSON local con lectura acotada y solo lectura. Muestra semanas,
  serie, nombre del archivo y SHA-256; conserva la ruta completa en tooltip.
- Solicita todos los parámetros explícitamente, confirma antes de simular y usa
  el evaluador SIR P2.5 en un `QThread`.
- Presenta observado/predicho y estados SIR en pestañas, con unidades y
  procedencia. El WebEngine local sigue disponible; el fallback Qt nativo se
  conserva. Las tablas redondean solo el texto visible a 6 cifras significativas;
  el valor exacto permanece en `UserRole` y tooltip.
- No añade algoritmos de ajuste ni estima incertidumbre.

## Verificación

- `PASS` 121 pruebas focalizadas de Qt, WebEngine, motor y contratos; 0 fallos,
  0 errores, 0 omitidas. Log completo en `%TEMP%\ssec_p3_24_gui_focused_tests.log`.
- `PASS` compilación de los módulos modificados y `git diff --check`.
- `PASS` demostración visual con fixture sintético y fallback QPainter:
  [comparación observado/predicho](assets/p3-24-thesis-sir-workspace-synthetic.png),
  [estados SIR](assets/p3-24-thesis-sir-states-synthetic.png).
- Las pruebas WebEngine verifican la gráfica local, sus restricciones de acceso,
  colores y movimiento reducido. La captura offscreen usa QPainter porque el
  compositor WebEngine no produjo una imagen en este entorno sin GPU.

## Límites

- Ecuaciones tomadas de la tesis y contrato implementado; ejecución con el JSON
  y parámetros reales: `NOT_RUN`. El usuario aún no ha aprobado esa ejecución ni
  declarado los valores explícitos que requiere esta pantalla.
- Validez científica, identificabilidad e incertidumbre: `NOT_ASSESSED`.
- Proveedor real desde la aplicación, GUI visual Linux y auditoría especialista
  iniciada desde este workspace: `NOT_RUN`.
- Sin paquetes instalados ni invocaciones de modelo. El fixture/screenshot no
  representa datos de la tesis ni constituye evidencia científica.

## Decisiones

- El motor, los contratos y las reglas de confirmación permanecen independientes
  de la presentación Qt.
- Qt WebEngine usa el renderizador local existente; sin disponibilidad se muestra
  el fallback nativo. No se usan CDN, recursos remotos ni código de proyecto.
- La salida calculada se elimina al cambiar datos o parámetros; el archivo fuente
  no puede sobrescribirse al exportar.

Rama: `codex/p3-24-thesis-sir-control-center`. Sin merge a `main` ni release.
