# P2 — enrutamiento explícito para modelos ODE

## Objetivo

Cuando una tarea declare el dominio `ode`, el router debe seleccionar tanto `ode_model_specialist` como `numerical_analyst`, además de los roles generales que ya corresponden por tipo de tarea. Esto hace explícita la revisión de formulación del modelo diferencial y de validez numérica en solicitudes SIR.

## Alcance

- Añadir el dominio cerrado `ode` a `scripts/route_task.py`.
- Asignar siempre `ode_model_specialist` para ese dominio y sumar `ode` a los dominios que requieren `numerical_analyst`.
- Documentar el contrato en la skill portable y el router.
- Mantener separados los roles de formulación ODE y revisión matemática de claims: `ode` por sí solo no afirma identificabilidad, estabilidad ni validez científica.
- Cubrir selección de roles y ausencia de sobre-enrutamiento de revisión científica con prueba determinista.

## Fuera de alcance

No se cambia el solver, el contrato SIR, el runtime multiagente, el despacho de proveedores ni los claims científicos. PDE, inferencia de parámetros y otros dominios permanecen sin cambios.

## Aceptación

Una tarea R1 con `domains: ["ode"]` produce `implementation_engineer`, `ode_model_specialist` y `numerical_analyst`; conserva `CONDITIONAL_ON_CLAIMS` y no exige `scientific_validation` ni `independent_review`. Una auditoría mantiene su modo de solo lectura. Las pruebas de routing y el validador portable pasan.
