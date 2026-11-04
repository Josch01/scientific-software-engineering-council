# P3.17 — integrar análisis existentes con el SIR declarativo

## Intención

Probar que un workspace SIR puede mostrar resultados calculados por los contratos P2 existentes, con unidades y archivos de contexto verificables. El usuario todavía no ha entregado su SIR ni datos experimentales; el ejemplo nuevo será sintético, reproducible y no afirmará validez científica.

## Alcance

- Exponer el SIR v1 de tasas constantes como `OdeProblem` parametrizado, conservando una única implementación de la ecuación cerrada. El RHS usará beta/gamma del mapa de parámetros solo en esta ruta explícita; `solve_sir_model` seguirá usando los perfiles declarados sin cambios de comportamiento.
- Añadir una orquestación pequeña que reutilice `fit_least_squares`, `parameter_sensitivities`, `evaluate_observations` y el solver RK4. No añadirá optimizadores, estimadores ni métricas nuevos; sus límites y extremos de sensibilidad deben permanecer en el dominio de tasas no negativas.
- Generar desde un modelo y observaciones sintéticos un `workspace.json` con simulación, ajuste, sensibilidad local y residuales calculados por `scientific_core`.
- Permitir `context_refs` opcionales en ajuste/sensibilidad. El loader resuelve referencias tipadas y verificadas; las vistas derivan unidades solo de un contrato SIR validado y muestran digests de los artefactos enlazados.
- Probar la composición con vistas PySide6/WebEngine y el fallback nativo existente.

## No objetivos y límites

- No ejecutar código del proyecto ni código producido por agentes.
- No calcular incertidumbre, identificabilidad práctica ni validez científica. La incertidumbre permanece `NOT_ASSESSED / NOT_CALCULATED`.
- No inferir ruido o datos empíricos: las observaciones demo se generan de una simulación SIR conocida y se etiquetan como exactas y sintéticas.
- El puente de análisis admite inicialmente tasas `beta` y `gamma` constantes. Los perfiles por tramos siguen siendo simulables, pero el ajuste/sensibilidad de sus nudos queda pendiente hasta decidir una parametrización explícita.
- Los digests confirman igualdad de bytes con el manifiesto; los enlaces de contexto y los hashes, por sí solos, no prueban la derivación matemática de un resultado.
- No se agrega todavía un botón de ajuste en Qt. Este incremento entrega APIs reutilizables y una demostración visual calculada; la ejecución interactiva y la integración del supervisor pertenecen al siguiente paso P3.

## Enfoques considerados

1. **Adaptador de SIR en `scientific_core` + builder de demostración.** Reutiliza una sola implementación de las ecuaciones y los algoritmos existentes, permite testear resultados sin UI y mantiene PySide como consumidor de contratos. **Elegido** por ser el cambio mínimo que prueba el puente científico y la vista completa.
2. **Poner el ajuste dentro de Qt.** Se descarta aquí porque mezclaría composición numérica y UI y haría más difícil reutilizar el motor en la skill/CLI.
3. **Guardar JSON sintético escrito a mano.** Se descarta porque mostraría el layout, pero no probaría que los resultados provienen realmente de la simulación, ajuste, sensibilidad y evaluación existentes.

## Diseño

`SirModelDefinition.to_ode_problem()` solo acepta perfiles constantes y devuelve `OdeProblem` con parámetros beta/gamma. `SirModelDefinition.rhs()` conserva los perfiles cuando el mapa recibido está vacío (ruta de simulación declarativa); cuando la API parametrizada entrega exactamente beta y gamma, usa esos valores y rechaza tasas negativas. Ambas rutas llaman el mismo cuerpo de ecuaciones. `analyze_sir_parameters(...)` compone ajuste acotado, sensibilidad local y evaluación de observaciones al punto ajustado, devolviendo los objetos versionados existentes. Valida la solución SIR para el candidato de cada evaluación de ajuste y para las trayectorias centrales/perturbadas de sensibilidad; rechaza configuraciones fuera del dominio de tasas y conserva las validaciones de unidades del dataset.

El manifiesto mantiene cada resultado como único `resource_refs` principal. Los componentes `fit_summary` y `sensitivity_plot` pueden tener opcionalmente `config.context_refs: string[]`; esos IDs deben existir, ser únicos y distintos del resultado. `fit_summary` acepta como contexto hasta un `model_spec` y un `observations`; `sensitivity_plot` acepta hasta un `model_spec`. Los validadores de workspace y de propuestas aplican la misma regla. La vista carga bytes ya verificados, valida el modelo SIR de contexto y deriva `time_unit`, unidades de estado y unidades de parámetros desde ese modelo. Los digests de los recursos primarios y de contexto se muestran como bytes verificados, no como prueba criptográfica de que el cálculo use esos datos. Si no hay contexto SIR válido, las etiquetas continúan como no suministradas.

El builder determinista genera una simulación de tasas constantes, extrae observaciones en tiempos de la malla, ajusta beta/gamma desde valores iniciales distintos, calcula sensibilidad con perturbaciones explícitas y evalúa residuales del modelo ajustado. Los resultados se serializan con los `to_dict()` existentes; la UI se abre desde el manifiesto y muestra recursos y hashes enlazados.

## Validación

Pruebas numéricas de recuperación frente a parámetros sintéticos conocidos, sensibilidad no nula, residuales y unidades; pruebas de rechazo para perfiles temporales no soportados, unidades incompatibles y referencias mal tipadas; reconstrucción byte-reproducible del demo; renderizado Qt de métricas, unidades y procedencia. El modelo SIR del usuario, identificabilidad y validez científica siguen `NOT_RUN` / `NOT_ASSESSED`.
