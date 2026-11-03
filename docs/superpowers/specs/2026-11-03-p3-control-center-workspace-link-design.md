# P3.4 — abrir espacios científicos desde el supervisor

**Intención.** Unir la supervisión existente de SSEC con la vista científica P3.3 para que el usuario pueda abrir el espacio del proyecto activo desde el mismo Centro de Control.

**Estado actual.** `config_panel.py` crea la raíz Tk del supervisor. `scientific_workspace_app.py` puede cargar y mostrar manifiestos validados, pero siempre crea una segunda raíz Tk y vuelve a pedir la raíz del proyecto.

**Enfoques considerados.** (1) Ejecutar otra instancia de la app como proceso: mantiene aislamiento de interfaz, pero separa ventanas/configuración y duplica el event loop. (2) Abrir un `Toplevel` hijo usando la raíz del supervisor y la raíz del proyecto ya seleccionada: reutiliza los componentes y el loader; es la opción elegida para mantener una sola aplicación y no tocar el runtime de agentes. (3) Refactorizar todo el panel como una pestaña incrustada: permitiría una ventana única, pero amplía el cambio y modifica una interfaz que ya funciona.

**Alcance y restricciones.** Añadir un botón que abra la vista científica en un `Toplevel`, inicialmente explorando bajo el proyecto elegido; el loader mantiene la verificación de contención y SHA-256. La ventana continúa permitiendo elegir manifiesto/raíz si no hay un proyecto utilizable. La importación de Tk sigue siendo diferida; `--check` continúa headless. No se añade ejecución de proveedores, código de proyectos ni callbacks. El flujo de auditoría, DAG, persistencia y workers queda fuera de este incremento.

**Criterio de aceptación.** La vista abre desde el supervisor con el mismo root Tk padre, usa el proyecto actual como directorio inicial, y mantiene intactas la carga segura, la app independiente y las pruebas headless. Errores de manifiesto se muestran al usuario sin exponer ni ejecutar su contenido.
