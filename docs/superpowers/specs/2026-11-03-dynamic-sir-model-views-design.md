# P3.8 — vistas reutilizables para ecuaciones y parámetros SIR

El primer workspace dinámico ya selecciona `equation_view`, `parameter_table` y `simulation_plot` por manifest, pero las dos primeras vistas presentan JSON sin estructurar. P3.8 especializa esos componentes para el único contrato científico implementado (`sir_frequency_dependent_v1`), conservando un fallback JSON inerte para otros tipos de modelo.

`equation_view` presenta el conjunto de ecuaciones cerrado, estados, unidades declaradas y balance de población. `parameter_table` presenta condiciones iniciales, intervalo, solver, tasas constantes y nudos de los perfiles lineales. Ambas vistas se derivan del `SirModelDefinition` validado; no aceptan texto de fórmulas arbitrario ni ejecutan contenido del proyecto. Un SIR inválido produce un error visible en ese componente.

El esquema del manifest y el núcleo Tk permanecen estables. Una persona o agente puede configurar las vistas enumeradas en el manifest; el loader verifica los recursos como hasta ahora. Los resultados del ejemplo siguen siendo sintéticos y no justifican claims científicos.

**No incluye:** SEIR, AST simbólico, edición/persistencia del manifest, código agente, ajuste o incertidumbre, ni cambios al solver.
