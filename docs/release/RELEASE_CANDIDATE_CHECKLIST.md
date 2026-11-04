# Checklist de candidato de release SSEC

**Estado de este snapshot (2026-11-04): `PARTIAL`; release 1.0: `BLOCKED`; `RC_READY`: no.** Esta checklist prepara una revisión humana. No crea tags, publica artefactos ni aprueba el merge.

## 1. Código y reproducibilidad

- [ ] Registrar commit exacto, ramas/PRs, entorno, comandos y logs con SHA-256.
- [ ] Validar estructura y compilar fuentes/tests; ejecutar suites unitarias, integración y regresión pertinentes sobre el candidato exacto.
- [ ] CI verde para cada plataforma/versión que se declare compatible; documentar las plataformas no probadas como `NOT_RUN`.
- [ ] Revisar diffs, conflictos, cancelación/reintentos y fallos terminales; no permitir aprobación automática ni revisión propia.
- [ ] Probar una invocación real por proveedor únicamente con autorización vigente y el CLI disponible. Fixtures/mocks no sustituyen esta evidencia.
- [ ] Probar la interfaz Qt en cada plataforma objetivo; un test headless no equivale a inspección visual.

## 2. Seguridad y dependencias

- [ ] Revisión independiente integral de seguridad con alcance, commit y hallazgos documentados.
- [ ] Escaneos de secretos, dependencias y vulnerabilidades con herramientas y versiones declaradas; conservar resultados y falsos positivos.
- [ ] Confirmar pins de GitHub Actions y dependencias, origen, licencias, política de actualización y rollback.
- [ ] Generar SBOM/provenance para los artefactos que se distribuyan, o justificar por qué no corresponde.
- [ ] No descargar, instalar ni ejecutar extensiones de terceros sin revisión y autorización explícitas.
- [ ] Completar el [modelo de amenazas](../security/THREAT_MODEL.md) para cambios de alcance; resolver o aceptar formalmente los riesgos del candidato.

## 3. Benchmarks y afirmaciones científicas

- [ ] Ejecutar benchmarks reproducibles en tres proyectos de referencia: defecto numérico conocido, GUI/concurrencia defectuosa y problema ML/datos o identificabilidad.
- [ ] Para cada caso registrar oráculo, commit/digest, defectos hallados y omitidos, falsos positivos, regresiones, cobertura, entorno y tiempo/costo medible.
- [ ] Separar `SOFTWARE_VALIDITY`, `NUMERICAL_VALIDITY` y `SCIENTIFIC_VALIDITY`.
- [ ] No inferir verdad matemática, unicidad, identificabilidad, incertidumbre, causalidad ni validez empírica a partir de tests o ajuste.
- [ ] No declarar validado el SIR particular hasta recibir sus ecuaciones, unidades, condiciones iniciales y datos. El fixture sintético demuestra reproducibilidad de software, no validez científica.

## 4. Gobernanza, instalación y aprobación

- [ ] El propietario decide licencia y términos de contribución; agregar una licencia solo tras esa decisión.
- [ ] Revisar instrucciones de instalación/actualización, compatibilidad, requisitos opcionales de Qt, troubleshooting, changelog y reversión.
- [ ] Completar el informe maestro con fases, evidencia, `NOT_RUN`/`BLOCKED`, hallazgos, riesgos y decisiones pendientes.
- [ ] El propietario revisa los riesgos y aprueba explícitamente el candidato, la licencia y la publicación.
- [ ] No hacer merge a `main`, crear tags ni publicar releases hasta recibir autorización explícita.

## Bloqueos conocidos de este snapshot

- Issue #5: licencia y términos de contribución pendientes de decisión del propietario; no existe `LICENSE`.
- Escaneos automatizados de secretos/dependencias/vulnerabilidades y benchmark de tres proyectos: `NOT_RUN`; no se instalaron herramientas y no hay proyectos de referencia autorizados en este incremento.
- Revisión independiente integral del sistema P4.4: `NOT_RUN`; solo se revisó de forma independiente la consistencia de su informe.
- Integración real de proveedores desde la app, GUI Qt Linux y SIR/datos del usuario: `NOT_RUN` según sus informes P3.
- El gate de release permanece cerrado si la procedencia canónica de ejecución no puede verificarse; no aceptar JSON auto-declarado como sustituto.

Reevaluar cada casilla contra el commit candidato. Una casilla pendiente deja el candidato en `PARTIAL`, `CONDITIONAL` o `BLOCKED` según su impacto; no etiquetar `RC_READY` ni `SCIENTIFICALLY_CERTIFIED` por inferencia.
