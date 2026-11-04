# P3.9 — Propuestas de espacios científicos

**Estado:** prototipo experimental terminado en rama; el PR se abrirá como borrador y no se integrará. Los manifiestos cambian la disposición visual, no ejecutan código de agentes ni acreditan validez científica.

## Entrega

- La GUI **Revisar propuesta…** acepta un manifiesto JSON v1 dentro del proyecto, lo carga mediante el loader seguro y muestra un diff completo limitado a 64 KiB.
- La aprobación humana crea una copia nueva con JSON compacto canónico y nombre derivado del SHA-256 semántico; nunca sobrescribe el manifiesto fuente. Antes de escribir se vuelve a validar manifiesto, hashes de recursos y presupuesto de bytes. El rechazo no escribe.
- El loader retiene los bytes exactos del manifiesto obtenido en la apertura segura. Una colisión preexistente solo se reutiliza si corresponde al mismo manifiesto canónico y sus recursos verificados; una copia no canónica o distinta se rechaza sin sobrescribir.
- El diff y el título presentan caracteres Unicode invisibles como escapes JSON ASCII. Solo se componen tipos de componente registrados.
- `examples/sir_workspace_proposal.json` añade una vista de auditoría inerte a un fixture sintético; declara `NOT_ASSESSED` y `NOT_RUN`.

## Verificación

| Entorno | Actividad | Resultado |
|---|---|---|
| Windows 11, Python 3.14.0 | Grupo de pruebas `scientific_core`, observaciones, sensibilidad, optimización y workspace/loader/vistas/acciones/propuestas | PASS: 147 pruebas, 1 omitida por privilegio Windows de symlink. Log: [`windows-focused.log`](p3-workspace-proposals-2026-11-03-windows-focused.log). |
| Windows, Tkinter real | Smoke tests con ventana oculta: rechazo sin escritura, aprobación que actualiza la vista, drift entre preview y aprobación, y título/diff Unicode escapados | PASS; incluidos en las 147 pruebas. No se invocó proveedor. |
| Windows, Python 3.14.0 | `py_compile` en módulos y pruebas modificados; `git diff --check` | PASS. |
| Windows, CLI | `python scripts/scientific_workspace_app.py --check --project-root examples sir_workspace_proposal.json` | `VIEW_PREPARED`; 4 componentes, 3 secciones, 0 errores, 0 omitidos. |
| Docker/Linux, Python 3.14.0 | `python -m unittest discover -q`, imagen local existente `jerk-rpo-capd:6.1.0-python3.14.0`, raíz montada con el nombre canónico del skill | PASS: 458 pruebas, 10 omitidas, 141.851 s. Log: [`docker-full.log`](p3-workspace-proposals-2026-11-03-docker-full.log). |
| Docker/Linux, Python 3.14.0 | `python scripts/validate_skill.py`, raíz canónica | PASS: `VALID STRUCTURE`; no implica validez de software o ciencia. Log: [`docker-validate-skill.log`](p3-workspace-proposals-2026-11-03-docker-validate-skill.log). |

La primera llamada de suite Docker montó el checkout como `/workspace`; una prueba estructural falló porque el validador exige el nombre canónico de la raíz. Se repitió la suite montando el mismo checkout bajo `scientific-software-engineering-council` y pasó. No fue un defecto del código; la ejecución válida y su log se conservan arriba.

## Defectos reproducidos y corregidos

1. Un manifiesto válido de menos de 1 MiB se expandía al guardarse con indentación y luego excedía el límite del loader. La regresión falló antes de corregirlo. Ahora se prevalidan los bytes JSON compactos canónicos antes de crear el archivo.
2. La sanitización Tk transformaba caracteres invisibles distintos en `U+FFFD`, de modo que la revisión podía mostrar títulos diferentes como si fueran iguales. La regresión falló en el API y en el diálogo real. Ahora el diff y el título usan escapes JSON ASCII reversibles.
3. Un archivo preexistente con contenido JSON semánticamente igual pero bytes no canónicos podía aceptarse bajo un nombre SHA-256. La regresión falló antes de corregirlo. El loader conserva los bytes obtenidos en la misma apertura segura y la aprobación rechaza esa colisión sin modificarla.

Una revisión independiente de seguimiento confirmó estos tres cambios. La misma revisión identificó una carrera residual si un proceso local con acceso al padre sustituye la raíz del proyecto durante la aprobación. P3.9 exige una raíz y ancestros estables y confiables; el JSON de propuesta no puede causar la sustitución. No se afirma protección frente a un proceso hostil que controle ese directorio.

## Límites y estado científico

- La generación automática de la propuesta y la integración proveedor E2E están `NOT_RUN`.
- No se recibieron ecuaciones, parámetros ni datos del SIR del usuario; su simulación y auditoría permanecen `NOT_RUN`. El fixture sintético no acredita identificabilidad, ajuste ni validez matemática.
- El manifiesto solo selecciona renderers/componentes existentes. No permite plugins, callbacks ni código Python arbitrario. No hay identidad criptográfica del aprobador ni persistencia transaccional distribuida.
- La autenticación visual es confirmación local explícita. La revisión necesita que el usuario aporte el JSON bajo la raíz del proyecto.
- La carrera de reemplazo de raíz por proceso concurrente con control del directorio padre queda como riesgo residual documentado.

## PR y siguiente incremento

PR borrador apilado sobre P3.8; se añadirá su número/estado al cierre tras revisar CI. No hacer merge ni publicar release. El siguiente incremento autorizado pendiente es la única invocación real de AGY para P1.4; se mantiene sin consumir hasta ejecutar el E2E seguro. No se usarán más invocaciones de modelos sin nueva autorización.
