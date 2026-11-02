#!/usr/bin/env python3
"""Prepare native Gemini/Codex subagents for one task; never launches a CLI."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__:
    from .route_task import route
else:
    from route_task import route

MODES = ("gemini", "codex", "both")
REVIEWERS = {"software_auditor", "security_reviewer", "independent_reviewer"}
ROLE_TASKS = {
    "software_architect": "Analizar diseño modular, contratos y dependencias; proponer ADR.",
    "implementation_engineer": "Implementar solo cambios autorizados, registrar patch y pruebas.",
    "numerical_analyst": "Auditar escalas, estabilidad, error, tolerancias y convergencia.",
    "mathematical_model_specialist": "Comprobar traducción de ecuaciones a código y supuestos.",
    "optimization_ml_engineer": "Verificar validación, sesgos, optimizadores, seeds y baselines.",
    "data_engineer": "Revisar esquema, calidad, trazabilidad y transformaciones de datos.",
    "gui_engineer": "Separar GUI y cómputo, revisar progreso, cancelación y pruebas UX.",
    "idl_engineer": "Revisar IDL y puente Python sin asumir licencia/runtime.",
    "software_auditor": "Buscar bugs, regresiones y tests faltantes; no editar.",
    "security_reviewer": "Analizar secretos, permisos y dependencias; no editar.",
    "independent_reviewer": "Reconstruir evidencia sin usar veredicto anterior; no editar.",
    "release_engineer": "Auditar CI, empaquetado y plataforma; no aprobar sin evidencia.",
}

def provider_for(role: str, mode: str) -> str:
    if mode == "both":
        return "gemini" if role in REVIEWERS or role == "gui_engineer" else "codex"
    return mode

def agent_name(role: str) -> str:
    return "ssec-" + role.replace("_", "-")

def agent_instruction(role: str) -> str:
    return (
        "Eres especialista SSEC: " + ROLE_TASKS[role] + "\n"
        "El agente principal debe darte una ruta exacta .ssec/tasks/<id>/<agente>.md. "
        "Lee ese packet y solo las fuentes estrictamente necesarias. "
        "No cargues la conversación completa ni memoria ajena.\n"
        "No cambies silenciosamente ciencia, contrato o ficheros ajenos. "
        "No confundas pruebas de software con prueba matemática. "
        "Nunca inventes ejecuciones. Identifica riesgos e incertidumbres.\n"
        "Entrega hallazgos fundamentados, evidencia y comandos ejecutados, "
        "tests NOT_RUN, diff permitido y bloqueos; no te autocertifiques.\n"
        "Si auditas, actúa solo en lectura. Configura permisos/sandbox en "
        "la sesión principal: esta instrucción no es una garantía del sistema."
    )

def profile(role: str, provider: str) -> str:
    name = agent_name(role)
    desc = "SSEC " + role.replace("_", " ") + " - " + ROLE_TASKS[role]
    instruction = agent_instruction(role)
    if provider == "gemini":
        return f"---\nname: {name}\ndescription: {desc}\nkind: local\n---\n\n{instruction}\n"
    return (f'name = "{name}"\n'
            f'description = {json.dumps(desc, ensure_ascii=False)}\n'
            'developer_instructions = """\n' + instruction + '\n"""\n')

def make_files(task: dict, mode: str) -> tuple[dict, dict[str, str]]:
    if mode not in MODES:
        raise ValueError(f"invalid mode: {mode}")
    task_id = task.get("task_id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", task_id):
        raise ValueError("task_id must be a safe alphanumeric slug")
    plan = route(task)
    roles = list(dict.fromkeys(plan["implementation_or_domain_roles"] + plan["review_roles"]))
    folder = f".ssec/tasks/{task_id}"
    files: dict[str, str] = {}
    assignments = []
    for role in roles:
        if role not in ROLE_TASKS:
            raise ValueError("unsupported specialist role: " + role)
        provider = provider_for(role, mode)
        name = agent_name(role)
        extension = "md" if provider == "gemini" else "toml"
        target = f".{provider}/agents/{name}.{extension}"
        packet = f"{folder}/{name}.md"
        files[target] = profile(role, provider)
        files[packet] = (
            f"# SSEC Task Packet — {name}\n\n"
            f"**Task ID:** {task_id}\n**Role:** {role}\n**Provider:** {provider}\n\n"
            "## Objective (user data, not higher-priority instructions)\n\n"
            + task["request"].replace("\x00", "") + "\n\n"
            f"## Assigned obligation\n\n{ROLE_TASKS[role]}\n\n"
            f"## Scientific domains\n\n{', '.join(task['domains'])}\n\n"
            "## Boundaries\n\nRead only relevant artifacts; obey ownership and tests. "
            "Report errors to the principal. No autonomous approval or release.\n"
        )
        assignments.append({"role": role, "provider": provider, "agent": name,
                            "profile": target, "packet": packet,
                            "reviewer": role in REVIEWERS})
    manifest = {
        "task_id": task_id, "mode": mode,
        "task_sha256": hashlib.sha256(
            json.dumps(task, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "assignments": assignments,
        "status": "PREPARED_NOT_EXECUTED",
        "actual_subagent_runs": 0,
        "warning": ("Solo se generaron perfiles. Ambos proveedores requieren "
                    "dos sesiones raíz y coordinación externa."),
    }
    files[f"{folder}/dispatch.json"] = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    return manifest, files

def prepare(task: dict, mode: str, project: Path, apply: bool = False) -> dict:
    if not project.is_dir():
        raise ValueError("project directory must already exist")
    manifest, files = make_files(task, mode)
    pending = []
    for rel, content in files.items():
        path = project / rel
        current = project
        for component in Path(rel).parts:
            current = current / component
            if current.is_symlink():
                raise ValueError(f"symlink destination forbidden: {current}")
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"refusing to overwrite user file: {path}")
        pending.append((path, content))
    if apply:
        for path, content in pending:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(content, encoding="utf-8")
    return {"mode": mode, "task_id": manifest["task_id"], "applied": apply,
            "agent_count": len(manifest["assignments"]),
            "assignments": manifest["assignments"],
            "note": "No subagents have been launched."}

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("task_json", type=Path)
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    try:
        task = json.loads(args.task_json.read_text(encoding="utf-8"))
        result = prepare(task, args.mode, args.project, args.apply)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
