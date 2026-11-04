# Router

## Intake

Identificar `kind`, `domains[]`, `languages[]`, `interfaces[]`, `targets[]`, `risk`, disponibilidad real de contextos, licencias y acceso al repo. Reglas:

- Tarea de software simple: implementador/revisor puntual y checks mecánicos.
- Auditoría: auditor de software antes de cualquier cambio, especialista sólo si existe superficie del dominio.
- Dominio `ode`: `ode_model_specialist` para formulación del sistema y `numerical_analyst` para integración, tolerancias, error e invariantes. Los claims de identificabilidad, estabilidad o prueba se enrutan aparte; declarar ODE no los afirma.
- PDE no tiene todavía un dominio/ruta específica implementada; no inferir soporte de enrutamiento a partir de `ode`.
- Optimización, inferencia o ML: especialista del algoritmo + revisión de validez numérica.
- Identificabilidad, estructura, simetrías o prueba matemática: puente con skill científica sólo para evaluación de claims.
- GUI escritorio: ingeniero de GUI y pruebas de interacción/asíncronas.
- IDL: ingeniero IDL, verificación de versión/licencia/bridge y conversión de shapes.
- Release Windows/Linux: release engineer y matrices de builds y smoke tests en ambos SO.
- Seguridad y dependencias externas: auditor de seguridad.

Secuencia: `INTAKE -> INVENTORY -> ADR -> TASK_PACKET -> IMPLEMENT -> DETERMINISTIC_TESTS -> ADVERSARIAL_REVIEW -> SCIENTIFIC_REVIEW_IF_NEEDED -> RELEASE_GATE`. Para auditoría inicial: `INTAKE -> INVENTORY -> TRIAGE -> REPRODUCE -> ROOT_CAUSE -> PLAN`; no corregir automáticamente.

Los nombres de proveedores (Codex, Gemini, otros) no otorgan autoridad. No más agentes de los que justifique el riesgo; no contar pases dentro de un contexto único como independencia real.
