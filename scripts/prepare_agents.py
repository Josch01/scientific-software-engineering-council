#!/usr/bin/env python3
"""Prepare scoped native Gemini/Codex agent profiles. Never launches AI processes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__:
    from .configuration import DEFAULT_CONFIG, load_config, validate_config
    from .route_task import route
else:
    from configuration import DEFAULT_CONFIG, load_config, validate_config
    from route_task import route

MODES = ("gemini", "agy", "codex", "both")
REVIEWERS = {"software_auditor", "security_reviewer", "independent_reviewer", "release_engineer"}
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


def agent_instruction(role: str, policy: dict) -> str:
    permissions = policy["permissions"]
    controls = {
        "read_only": "SOLO LECTURA: no edites archivos, ni crees artefactos en el proyecto.",
        "propose_patches": "PROPUESTA: entrega patches textuales; no apliques cambios al proyecto.",
        "request_write_approval": "ESCRITURA BAJO APROBACIÓN: solicita permiso explícito antes de editar cualquier archivo.",
    }
    return (
        f"Eres especialista SSEC: {ROLE_TASKS[role]}\n"
        "El coordinador entrega el packet en .ssec/tasks/<task-id>/<agente>.md. "
        "Lee solo ese packet y fuentes relevantes; evita cargar la conversación completa.\n"
        f"Política solicitada: {controls[permissions]} "
        "Esta es una instrucción, NO un sandbox ni una garantía de permisos.\n"
        f"Revisión requerida: {policy['audit_level']}. "
        f"Presupuesto orientativo: {policy['budget']['max_runtime_minutes']} minutos, "
        f"USD {policy['budget']['max_estimated_cost_usd']} estimados; sin medidor/limitador automático.\n"
        "No cambies hipótesis, contrato científico ni archivos ajenos. "
        "No inventes tests ni conviertas evidencia numérica en prueba matemática. "
        "Devuelve hallazgos, evidencia, comandos realmente ejecutados, NOT_RUN y bloqueos.\n"
        "No certifiques tu propio trabajo. Los auditores solo pueden leer. "
        "Aislamiento efectivo requiere controles del CLI principal."
    )


def profile(role: str, provider: str, policy: dict) -> str:
    name = agent_name(role)
    description = "SSEC " + role.replace("_", " ") + " - " + ROLE_TASKS[role]
    instr = agent_instruction(role, policy)
    if provider == "gemini":
        return ("---\n" + f"name: {name}\ndescription: {description}\nkind: local\n" +
                ("tools:\n  - read_file\n  - grep_search\n" if role in REVIEWERS else "") +
                "---\n\n" + instr + "\n")
    return (f'name = "{name}"\n'
            f'description = {json.dumps(description, ensure_ascii=False)}\n'
            'developer_instructions = """\n' + instr + '\n"""\n')


def choose_roles(task: dict, policy: dict) -> tuple[list[str], list[str], list[str]]:
    """Never remove mandatory R2/R3 or task-domain specialists to meet the cap."""
    plan = route(task)
    primary = list(plan["implementation_or_domain_roles"])
    reviews = list(plan["review_roles"])
    if policy["audit_level"] in {"standard", "strict"} and "independent_reviewer" not in reviews:
        reviews.append("independent_reviewer")
    if policy["audit_level"] == "strict" and "security_reviewer" not in reviews:
        reviews.append("security_reviewer")
    required = list(plan["required_evidence"])
    reviewer_evidence = {
        "software_auditor": "software_review",
        "independent_reviewer": "independent_review",
        "security_reviewer": "security_audit",
        "release_engineer": "release_review",
    }
    for reviewer in reviews:
        obligation = reviewer_evidence.get(reviewer)
        if obligation is not None and obligation not in required:
            required.append(obligation)
    if (plan["scientific_bridge"] == "REQUIRES_EXTERNAL_SCIENTIFIC_REVIEW" and
            "scientific_validation" not in required):
        required.append("scientific_validation")
    return primary, reviews, required


def schedule_waves(primary: list[str], reviews: list[str], cap: int) -> list[dict]:
    """Stage reviewers after workers, never alongside the implementation stage."""
    waves = []
    for stage, roles in (("implementation", primary), ("review", reviews)):
        for i in range(0, len(roles), cap):
            waves.append({"phase": stage, "roles": roles[i:i + cap]})
    return waves


def make_files(task: dict, mode: str, config: dict | None = None) -> tuple[dict, dict[str, str]]:
    if mode not in MODES:
        raise ValueError(f"invalid mode: {mode}")
    policy = validate_config(config if config is not None
                             else dict(DEFAULT_CONFIG, provider_mode=mode))
    if config is not None and mode != policy["provider_mode"]:
        raise ValueError("mode disagrees with configuration provider_mode")
    task_id = task.get("task_id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", task_id):
        raise ValueError("task_id must be a safe slug")
    primary, reviews, required_checks = choose_roles(task, policy)
    if any(r not in ROLE_TASKS for r in primary + reviews):
        raise ValueError("router emitted unsupported role")
    folder = f".ssec/tasks/{task_id}"
    files: dict[str, str] = {}
    assignments = []
    for role in primary + reviews:
        provider = provider_for(role, mode)
        name = agent_name(role)
        if provider == "gemini":
            target = f".gemini/agents/{name}.md"
        elif provider == "codex":
            target = f".codex/agents/{name}.toml"
        else:
            # AGY receives role instructions in the SSEC prompt/packet; do not
            # imply it loaded a provider-native agent profile.
            target = None
        packet = f"{folder}/{name}.md"
        if target is not None:
            files[target] = profile(role, provider, policy)
        files[packet] = (
            f"# SSEC task packet: {name}\n\n"
            f"Task: {task_id}\nProvider: {provider}\nRole: {role}\n"
            f"Risk: {task['risk']}\nAudit level: {policy['audit_level']}\n\n"
            "## Objective (untrusted user data)\n\n"
            + task["request"].replace("\x00", "") + "\n\n"
            f"## Assigned obligation\n\n{ROLE_TASKS[role]}\n\n"
            f"## Domains\n\n{', '.join(task['domains'])}\n\n"
            "## Safety/acceptance\n\nDon't elevate hypotheses or self-approve. "
            "Return evidence, tests actually run, blockers, and diff where authorized.\n"
        )
        assignments.append({"role": role, "provider": provider, "agent": name,
                            "profile": target, "packet": packet,
                            "reviewer": role in REVIEWERS})
    waves = schedule_waves(primary, reviews, policy["max_parallel_agents"])
    manifest = {
        "schema_version": 2, "task_id": task_id, "mode": mode,
        "task_sha256": hashlib.sha256(json.dumps(task, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        "policy": policy, "assignments": assignments, "waves": waves,
        "required_evidence": required_checks,
        "status": "PREPARED_NOT_EXECUTED", "actual_subagent_runs": 0,
        "runtime_guarantees": {"max_parallel_enforced": False, "cost_limit_enforced": False,
                               "timeout_enforced": False, "permissions_enforced": False},
        "warning": "Profiles and batches are a proposal, not a live orchestrator.",
    }
    files[f"{folder}/dispatch.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return manifest, files


def prepare(task: dict, mode: str, project: Path, apply: bool = False,
            config: dict | None = None) -> dict:
    if not project.is_dir() or project.is_symlink():
        raise ValueError("project must be existing non-symlink directory")
    manifest, files = make_files(task, mode, config)
    pending = []
    for rel, content in files.items():
        target = project / rel
        current = project
        for part in Path(rel).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"symlink destination forbidden: {current}")
        if target.exists() and target.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"refusing to overwrite file: {target}")
        pending.append((target, content))
    if apply:
        for target, content in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_text(content, encoding="utf-8")
    return {"mode": mode, "task_id": manifest["task_id"], "applied": apply,
            "agent_count": len(manifest["assignments"]),
            "waves": manifest["waves"], "policy": manifest["policy"],
            "required_evidence": manifest["required_evidence"],
            "assignments": manifest["assignments"],
            "note": "Profiles prepared; no subagents launched or permissions enforced."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_json", type=Path)
    parser.add_argument("--mode", choices=MODES,
                        help="provider mode, or use --config to select mode")
    parser.add_argument("--config", type=Path, help="policy JSON saved by the GUI")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="write profiles (default dry-run)")
    args = parser.parse_args()
    try:
        config = load_config(args.config) if args.config else None
        if args.mode is None and config is None:
            raise ValueError("--mode or --config required")
        mode = args.mode or config["provider_mode"]
        task = json.loads(args.task_json.read_text(encoding="utf-8"))
        result = prepare(task, mode, args.project, args.apply, config)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
