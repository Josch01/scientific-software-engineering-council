# Instalación y primeros usos (v0.1.0)

Esta versión es una **skill de instrucciones, plantillas y verificadores deterministas**. No lanza agentes reales por sí sola.

## Gemini CLI (instalación desde GitHub)

Según la documentación oficial de Gemini CLI, instala el repositorio en tu perfil de usuario:

```bash
gemini skills install https://github.com/Josch01/scientific-software-engineering-council.git
gemini skills list
```

Se solicitará confirmación de seguridad. Para un proyecto particular, utiliza `--scope workspace` según la versión de Gemini CLI que tengas instalada. Dentro de Gemini, utiliza `/skills list` y `/skills reload` para verificar el descubrimiento.

Documentación oficial: https://geminicli.com/docs/cli/skills/

## Codex y otros agentes compatibles

La skill sigue la estructura portable `SKILL.md`. En entornos Codex que descubran skills en `.agents/skills/`, puedes clonar este repositorio dentro de esa ruta. Por ejemplo, desde la raíz del proyecto:

```bash
mkdir -p .agents/skills
git clone https://github.com/Josch01/scientific-software-engineering-council.git .agents/skills/scientific-software-engineering-council
```

En Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path .agents/skills | Out-Null
git clone https://github.com/Josch01/scientific-software-engineering-council.git .agents/skills/scientific-software-engineering-council
```

Ajusta la ruta si tu cliente/proveedor utiliza otro directorio de skills; revisa sus mecanismos de confianza y activación. La existencia del directorio no garantiza que el runtime habilite ejecución de subagentes.

Información general: https://agentskills.io/specification

## Probar localmente sin agentes

Requiere Python >= 3.11, sin dependencias adicionales:

```bash
python scripts/validate_skill.py
python -m unittest discover -s tests -v
python scripts/route_task.py examples/seir_desktop_audit.json
python scripts/release_gate.py --task examples/seir_desktop_audit.json --evidence examples/release_evidence_not_run.json
```

El comando de release debe terminar con código 2 (bloqueo intencional por falta de evidencia real).

## Primera auditoría sugerida

> Activa `scientific-software-engineering-council` para auditar este repositorio científico en modo sólo lectura. Comienza con inventario, mapa de dependencias, identificación de errores numéricos/algorítmicos y riesgos GUI, sin modificar código. Entrega un plan con roles y test cases; separa hipótesis científicas de defectos de software. No declares pruebas ejecutadas que no se realizaron.

## Alcance y limitaciones

- `route_task.py` propone roles y evidencias; **no los ejecuta**.
- `release_gate.py` comprueba formato y hashes de logs, **no certifica** verdad científica ni independencia real.
- Para trabajo con IDL se necesita instalación/licencia adecuada; sin ella se marca `NOT_RUN`.
- Construcciones de GUI Windows/Linux y agentes reales requieren sus entornos correspondientes.

## Hojas de ruta

- [v0.2 Orquestación multiagente](https://github.com/Josch01/scientific-software-engineering-council/issues/1)
- [v0.3 Módulos científicos](https://github.com/Josch01/scientific-software-engineering-council/issues/2)
- [v0.4 GUI e IDL](https://github.com/Josch01/scientific-software-engineering-council/issues/3)
- [v1.0 Benchmarks, dependencias y releases](https://github.com/Josch01/scientific-software-engineering-council/issues/4)
