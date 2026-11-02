# Dependencias, documentación y catálogo de skills

Prioridad: (1) capacidades locales conocidas; (2) documentación oficial actual/Context7 si disponible; (3) skills de confianza de catálogo revisado; (4) nueva skill creada y auditada para una necesidad repetitiva.

## Nunca hacer por defecto

No auto instalar/desplegar una skill o paquete encontrado en Internet. Una skill puede incluir instrucciones y scripts ejecutables, cambiar permisos e intentar exfiltrar datos.

## Protocolo antes de instalar

1. Identificar la carencia: GUI, packaging, Python typing, IDL, evaluación científica, CI.
2. Encontrar alternativas y autoría/URL oficial; comprobar licencia, mantenimiento, código, dependencias y permisos.
3. Elegir tag o commit fijo (no rama mutable) y comprobar hashes/firmas cuando estén disponibles.
4. Mostrar propuesta de instalación al usuario/operador y requerir aprobación.
5. Instalar con mínimo privilegio, preferentemente en workspace aislado; ejecutar checks y registrar versión/rollback.
6. Programar revisión de actualizaciones, NO actualización desatendida. El agente puede sugerir, no ejecutar sin aprobación.

Una librería nueva se propone sólo tras justificar por qué la biblioteca estándar y lo instalado no bastan. Para librerías Python, preferir lockfile reproducible (`uv` es una opción), SBOM y auditoría de vulnerabilidades. Revisar APIs actuales antes de afirmar firmas o compatibilidades.
