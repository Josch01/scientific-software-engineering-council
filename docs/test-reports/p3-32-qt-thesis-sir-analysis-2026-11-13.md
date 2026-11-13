# P3.32 — Ajuste SIR de tesis desde el Centro de Control

**Estado:** implementado; [PR draft #73](https://github.com/Josch01/scientific-software-engineering-council/pull/73), apilado sobre P3.31. Incremento experimental.

## Resultado

- `PASS` — seleccionar explícitamente parámetros dinámicos, dominios, límites y perturbaciones; confirmar muestra modelo, serie, digest, paso RK4 y destino. Rechazar no inicia trabajo ni crea archivos.
- `PASS` — aceptación ejecuta el motor P3.31 en `QThread`, bloquea duplicados y cambio de proyecto, crea un directorio nuevo y abre el workspace en la ruta de resultados de la misma aplicación.
- `PASS` — las vistas de simulación, ajuste, sensibilidad y residuales consumen resultados reales del motor; el workspace también incluye configuración, bitácora con tiempos del worker, digests del código y observaciones seleccionadas. La revisión humana queda `PENDING`.
- `PASS` — fallo inyectado no carga resultados ni reutiliza la corrida previa; el JSON fuente permanece byte por byte idéntico.
- Incertidumbre `NOT_CALCULATED`; validez e identificabilidad `NOT_ASSESSED`.

## Verificación Windows

- `PASS` — motor, escritor, vistas y loader: 44 pruebas; 1 prueba omitida por la limitación de symlink de Windows.
- `PASS` — suites Qt de página SIR y Centro de Control juntas: 48 pruebas.
- `PASS` — `py_compile` y `git diff --check`.
- Una ejecución inicial dio una aserción interna intermitente de Chromium (`CalledOnValidBrowserThread`) porque los fixtures cerraban, pero no destruían, páginas WebEngine pendientes. El teardown ahora destruye las páginas en el hilo Qt y procesa `DeferredDelete`; la suite combinada completa pasa.
- Render visual nuevo del diálogo `NOT_RUN`: el backend Qt offscreen disponible dibujó tofu para todas las fuentes; esta captura no es evidencia visual válida. La interfaz base conserva la revisión de escritorio Windows 1440×920 de P3.29. QA visual Linux `NOT_RUN`.

## Alcance científico y pendientes

La integración solo usa fixtures sintéticos. El ajuste admite `d0`, `gamma` y coeficientes/frecuencias armónicos declarados; mantiene fijos condiciones iniciales, `q` y retardo. No incorpora solver, optimizador, incertidumbre ni análisis de identificabilidad nuevos. El ajuste no se puede cancelar de forma segura porque P3.31 no ofrece cancelación.

SIR y datos de la tesis del usuario: `NOT_RUN`. CLI/proveedor: `NOT_RUN`. No se hizo afirmación de validez matemática ni epidemiológica. Pendiente: QA visual del nuevo diálogo con el backend de escritorio real, QA Qt Linux y ejecutar el caso con datos reales solo después de autorización humana.
