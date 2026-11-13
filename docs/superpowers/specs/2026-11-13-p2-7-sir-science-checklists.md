# P2.7 — Checklists científicas para modelos SIR

## Problema y objetivo

P2.6 selecciona especialistas por dominio y exige `scientific_validation`, pero los perfiles generados solo contienen remisiones generales. Un SIR mencionado explícitamente debe recibir comprobaciones breves y separadas sobre formulación/unidades, error numérico, identificabilidad y límites de las conclusiones.

## Enfoques considerados

- **A. Checklist condicional por rol (seleccionado):** `prepare_agents` agrega solo el bloque correspondiente a los perfiles científicos de una tarea que nombra SIR/SEIR o un modelo epidemiológico compartimental; la skill portable documenta el mismo límite. No cambia la selección de roles ni el esquema.
- **B. Checklist en todo perfil:** sencillo, pero consume contexto en tareas no epidemiológicas.
- **C. Nuevo rol o esquema de router:** permitiría controlar más granularidad, pero duplica el catálogo y no es necesario para el primer caso SIR.

## Comprobaciones

- `mathematical_model_specialist`: ecuaciones explícitas; definición, unidad y escala temporal de estados/parámetros; consistencia dimensional de cada lado de las EDO; condiciones iniciales y supuestos. No asumir conservación de `S+I+R` en variantes modificadas.
- `numerical_analyst`: método, malla/paso, tolerancias y versión; evidencia de refinamiento de paso o comparación de referencia; separar error numérico de RMSE de ajuste; revisar positividad/invariantes solo si se derivan de las ecuaciones declaradas.
- `identifiability_specialist`: distinguir identificabilidad estructural y práctica; ligar parámetros y observables al diseño de muestreo/ruido; buscar simetrías/confusión; sensibilidad local o RMSE bajo no prueban identificabilidad ni unicidad.
- `dynamical_systems_specialist`: limitar estabilidad y trayectoria a las ecuaciones, parámetros y horizonte analizados; una simulación no demuestra capacidad predictiva, causalidad ni validez epidemiológica.

Las listas son preguntas de revisión, no algoritmos ni evidencia. Si faltan ecuaciones/datos, indicar `NOT_RUN` para cálculos y `NOT_ASSESSED` para claims científicos; pedir únicamente los insumos faltantes.

## Alcance y aceptación

- Detectar SIR/SEIR/modelo compartimental por texto explícito de la solicitud y agregar la checklist solo a los perfiles científicos existentes que hayan sido seleccionados.
- Mantener los perfiles de tareas no SIR y el esquema/routing P2.6 sin cambios.
- Incluir las mismas cuatro distinciones en la skill portable para uso directo con Codex/Gemini.
- Probar los perfiles generados en los modos existentes, la exclusión en tareas no SIR y el contenido de la skill.

No se añaden cálculos, modelos, solvers ni resultados científicos. El SIR particular del usuario continúa `NOT_RUN`.
