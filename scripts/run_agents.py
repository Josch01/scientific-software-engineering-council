#!/usr/bin/env python3
"""SSEC v0.2 audit runner: real CLI processes, isolated disposable snapshots, no merges.

This is NOT a scientific certification, billing meter, or OS-grade security boundary.
Never invokes shell strings or unapproved executables; audit-only for first release.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

if __package__:
    from .configuration import DEFAULT_CONFIG, config_path, load_config, validate_config
    from .prepare_agents import make_files, prepare
    from .route_task import validate_task
else:
    from configuration import DEFAULT_CONFIG, config_path, load_config, validate_config
    from prepare_agents import make_files, prepare
    from route_task import validate_task

MAX_SOURCE_BYTES = 60 * 1024 * 1024
MAX_FILE_BYTES = 15 * 1024 * 1024
SKIP_DIRS = {".git", ".ssec", ".venv", "venv", "node_modules", "__pycache__",
             ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build",
             ".codex", ".gemini", ".agents", ".idea", ".vscode", ".next", ".cache"}
SKIP_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
              "credentials.json", "service-account.json", ".npmrc", ".pypirc"}
SKIP_EXTS = {".key", ".pem", ".p12", ".pfx", ".sqlite", ".db", ".zip", ".tar",
             ".7z", ".gz", ".parquet", ".pkl"}
STATUS = {"EXIT_ZERO_UNREVIEWED", "CLI_FAILED", "TIMED_OUT", "CANCELLED", "LAUNCH_FAILED"}

def files_to_copy(project: Path) -> list[tuple[Path, Path]]:
    """Fail closed on oversized workspaces; exclude obvious secrets/caches/symlinks."""
    result = []
    total = 0
    for base, dirs, files in os.walk(project, followlinks=False):
        here = Path(base)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and
                         not (here / d).is_symlink())
        for name in sorted(files):
            source = here / name
            if (source.is_symlink() or name in SKIP_NAMES or
                name.startswith(".env.") or name.endswith((".secret", ".token")) or
                source.suffix.lower() in SKIP_EXTS):
                continue
            size = source.stat().st_size
            if size > MAX_FILE_BYTES:
                raise ValueError(f"source exceeds per-file limit: {source}")
            total += size
            if total > MAX_SOURCE_BYTES:
                raise ValueError("source exceeds 60 MiB snapshot limit; narrow the project")
            result.append((source, source.relative_to(project)))
    if not result:
        raise ValueError("no auditable source files remain after exclusions")
    return result

def copy_snapshot(files: list[tuple[Path, Path]], destination: Path) -> None:
    for src, rel in files:
        dest = destination / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():  # refuse TOCTOU swap
            raise ValueError("source became a symlink")
        shutil.copyfile(src, dest)

def selected_gemini_cli() -> str:
    """Select the Gemini-compatible local CLI without fallback on invalid config."""
    value = os.environ.get("SSEC_GEMINI_CLI", "gemini")
    if value not in {"gemini", "agy"}:
        raise ValueError("SSEC_GEMINI_CLI must be 'gemini' or 'agy'")
    return value


def command_for(provider: str, prompt: str, cwd: Path) -> list[str]:
    if provider == "codex":
        return ["codex", "exec", "--sandbox", "read-only", "--json",
                "--skip-git-repo-check",
                "--cd", str(cwd), prompt]
    if provider == "gemini":
        if selected_gemini_cli() == "agy":
            return ["agy", "--sandbox", "--settings", '{"agentMode":""}',
                    "--output-format", "json", "--prompt", prompt]
        return ["gemini", "--sandbox", "--approval-mode", "default",
                "--output-format", "json", "-p", prompt]
    raise ValueError("unsupported provider")

def make_prompt(agent: dict, task_id: str) -> str:
    return (
        f"Actúa como {agent['agent']} en una auditoría SSEC SOLO LECTURA. "
        f"Lee el archivo {agent['packet']} dentro del workspace. "
        "No edites, no instales dependencias, no solicites credenciales ni abras "
        "rutas externas al snapshot. Tu resultado se reporta al supervisor; "
        "no declares aceptación de software ni prueba científica. "
        "Describe evidencias y comandos realmente ejecutados, errores, "
        "limitaciones y verificaciones NOT_RUN. "
        f"ID de misión: {task_id}. "
        "Si el packet requiere otros cambios, propone parches sin aplicarlos."
    )

def _terminate_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            result = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, shell=False, timeout=8, check=False)
            if result.returncode != 0:
                raise OSError(f"taskkill returned {result.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            proc.kill()
            raise OSError(f"Tree termination UNVERIFIED ({exc}); direct-process kill attempted") from exc
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            proc.kill()
            raise OSError("Process-group termination UNVERIFIED; direct-process kill attempted") from exc

def run_one(agent: dict[str, Any], task_id: str,
            source_files: list[tuple[Path, Path]], profiles: dict[str, str],
            run_dir: Path, deadline: float, stop: threading.Event,
            cancel_file: Path | None = None,
            on_started: Callable[[str], None] | None = None) -> dict[str, Any]:
    started = time.time()
    name = agent["agent"]
    logs = run_dir / "logs"
    logs.mkdir(exist_ok=True, parents=True)
    logpath = logs / f"{name}.stdout"
    errpath = logs / f"{name}.stderr"
    result = {"agent": name, "provider": agent["provider"], "cli_binary": None,
              "role": agent["role"],
              "status": "LAUNCH_FAILED", "exit_code": None,
              "stdout_log": str(logpath.relative_to(run_dir)),
              "stderr_log": str(errpath.relative_to(run_dir)),
              "started_at_unix": started, "duration_seconds": 0}
    try:
        with tempfile.TemporaryDirectory(prefix="ssec-agent-") as temp:
            workspace = Path(temp)
            copy_snapshot(source_files, workspace)
            # Always regenerate profiles from trusted SSEC, NOT from source project.
            for rel in (agent["profile"], agent["packet"]):
                target = workspace / rel
                target.parent.mkdir(exist_ok=True, parents=True)
                target.write_text(profiles[rel], encoding="utf-8")
            cmd = command_for(agent["provider"], make_prompt(agent, task_id), workspace)
            executable_name = cmd[0]
            result["cli_binary"] = executable_name
            executable = shutil.which(executable_name)
            if not executable:
                result["error"] = f"{executable_name} CLI not found in PATH"
                return result
            cmd[0] = executable
            flags = 0
            if os.name == "nt":
                flags = subprocess.CREATE_NEW_PROCESS_GROUP
            with logpath.open("wb") as output, errpath.open("wb") as error:
                if on_started is not None:
                    on_started("STARTING")
                proc = subprocess.Popen(cmd, cwd=workspace, shell=False,
                                        stdout=output, stderr=error,
                                        stdin=subprocess.DEVNULL, creationflags=flags,
                                        start_new_session=(os.name != "nt"))
                if on_started is not None:
                    on_started("RUNNING")
                while proc.poll() is None:
                    if stop.is_set() or (cancel_file is not None and cancel_file.exists()):
                        stop.set()
                        _terminate_tree(proc)
                        result["status"] = "CANCELLED"
                        break
                    if time.monotonic() >= deadline:
                        stop.set()
                        _terminate_tree(proc)
                        result["status"] = "TIMED_OUT"
                        break
                    time.sleep(0.15)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _terminate_tree(proc)
                    result["status"] = "TIMED_OUT"
                result["exit_code"] = proc.returncode
                if result["status"] not in {"CANCELLED", "TIMED_OUT"}:
                    result["status"] = ("EXIT_ZERO_UNREVIEWED" if proc.returncode == 0
                                        else "CLI_FAILED")
    except (OSError, ValueError) as exc:
        result["error"] = str(exc)
    finally:
        result["duration_seconds"] = round(time.time() - started, 2)
    return result

def plan(task: dict, config: dict) -> dict:
    validate_task(task)
    config = validate_config(config)
    if task["kind"] != "audit":
        raise ValueError("v0.2 runner executes ONLY audits; build/debug still plan-only")
    manifest, profiles = make_files(task, config["provider_mode"], config)
    return {"manifest": manifest, "profiles": profiles}

def _safe_reports_dir(project: Path) -> Path:
    folder = project / ".ssec" / "runs"
    for part in (project / ".ssec", folder):
        if part.is_symlink():
            raise ValueError("cannot write run logs through a symlink")
    return folder

def execute(task: dict, config: dict, project: Path,
            *, execute_clis: bool = False,
            accept_unmetered_cost: bool = False,
            cancel_file: Path | None = None,
            progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict:
    """Synchronous runner: shared deadline; skip further waves after any failures.

    Dry-run does not create files or invoke CLIs. Billing USD is never enforced.
    """
    if not project.is_dir() or project.is_symlink():
        raise ValueError("project must be existing non-symlink directory")
    p = plan(task, config)
    manifest = p["manifest"]
    summary = {"task_id": task["task_id"], "mode": config["provider_mode"],
               "execution": "PREVIEW_ONLY", "waves": manifest["waves"],
               "agent_count": len(manifest["assignments"]),
               "enforced": {"concurrent_top_level_processes": True,
                            "global_wall_clock_deadline": True,
                            "billing_usd": False,
                            "original_workspace_writes": False,
                            "os_grade_isolation": False},
               "results": [], "release_status": "NOT_APPROVED"}
    if not execute_clis:
        return summary
    if not accept_unmetered_cost:
        raise ValueError("billing is NOT metered: explicitly pass --accept-unmetered-cost")
    files = files_to_copy(project)
    folder = _safe_reports_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = folder / run_id
    run_dir.mkdir()
    stop = threading.Event()
    deadline = time.monotonic() + config["budget"]["max_runtime_minutes"] * 60
    assignment_by_role = {a["role"]: a for a in manifest["assignments"]}
    progress_lock = threading.Lock()
    role_states = {
        assignment["agent"]: {"agent": assignment["agent"],
                              "role": assignment["role"],
                              "provider": assignment["provider"],
                              "status": "NOT_STARTED"}
        for assignment in manifest["assignments"]
    }

    def emit_progress() -> None:
        if progress_callback is None:
            return
        event = {"schema_version": 1, "run_id": run_id,
                 "task_id": task["task_id"], "execution": summary["execution"],
                 "completed": len(summary["results"]),
                 "total": len(manifest["assignments"]),
                 "release_status": "NOT_APPROVED",
                 "roles": [dict(row) for row in role_states.values()]}
        try:
            progress_callback(event)
        except Exception:
            # Observability failures must not change execution or approval state.
            pass

    def update_status(agent_id: str, status: str) -> None:
        with progress_lock:
            role_states[agent_id]["status"] = status
            emit_progress()

    summary["execution"] = "STARTED"
    summary["run_id"] = run_id
    summary["log_dir"] = str(run_dir)
    summary["max_runtime_minutes"] = config["budget"]["max_runtime_minutes"]
    try:
        emit_progress()
        for wave in manifest["waves"]:
            if cancel_file is not None and cancel_file.exists():
                stop.set()
            if stop.is_set():
                break
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(config["max_parallel_agents"], len(wave["roles"]))
            ) as pool:
                futures = [pool.submit(
                    run_one, assignment_by_role[role], task["task_id"],
                    files, p["profiles"], run_dir, deadline, stop, cancel_file,
                    lambda status, agent_id=assignment_by_role[role]["agent"]:
                        update_status(agent_id, status)
                ) for role in wave["roles"]]
                for future in concurrent.futures.as_completed(futures):
                    entry = future.result()
                    with progress_lock:
                        summary["results"].append(entry)
                        role_states[entry["agent"]]["status"] = entry["status"]
                        emit_progress()
                    (run_dir / "progress.json").write_text(
                        json.dumps({"task_id": task["task_id"],
                                    "done": len(summary["results"]),
                                    "total": len(manifest["assignments"]),
                                    "latest": {"role": entry["role"],
                                               "status": entry["status"]}},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
                    if entry["status"] != "EXIT_ZERO_UNREVIEWED":
                        stop.set()
            if stop.is_set():
                break
    except KeyboardInterrupt:
        stop.set()
        summary["execution"] = "INTERRUPTED"
    else:
        complete = len(summary["results"]) == len(manifest["assignments"])
        passed = all(x["status"] == "EXIT_ZERO_UNREVIEWED" for x in summary["results"])
        summary["execution"] = ("PROCESSES_COMPLETED_NOT_AUDITED" if complete and passed
                                else "PARTIAL_OR_FAILED")
    emit_progress()
    summary["note"] = ("Exit 0 means CLI exited normally, NOT that audit passed; "
                       "review each log manually. Cost limits are only advisory.")
    (run_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_json", type=Path)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--config", type=Path,
                        help="defaults to project/.ssec/config.json when it exists")
    parser.add_argument("--mode", choices=("gemini", "codex", "both"))
    parser.add_argument("--execute", action="store_true",
                        help="launch real CLIs in ephemeral snapshots; otherwise dry-run")
    parser.add_argument("--cancel-file", type=Path,
                        help="optional file that cancels all active processes when created")
    parser.add_argument("--accept-unmetered-cost", action="store_true",
                        help="acknowledge that real provider cost is not reliably metered")
    parser.add_argument("--emit-progress-jsonl", action="store_true",
                        help="emit versioned SSEC_PROGRESS JSON Lines events on stdout")
    args = parser.parse_args()
    try:
        config_file = args.config or config_path(args.project)
        config = load_config(config_file) if config_file.is_file() else dict(DEFAULT_CONFIG)
        if args.mode:
            config["provider_mode"] = args.mode
        config = validate_config(config)
        task = json.loads(args.task_json.read_text(encoding="utf-8"))
        progress_callback = None
        if args.emit_progress_jsonl:
            progress_callback = lambda event: print(
                "SSEC_PROGRESS " + json.dumps(event, ensure_ascii=False,
                                               separators=(",", ":")),
                flush=True)
        report = execute(task, config, args.project, execute_clis=args.execute,
                         accept_unmetered_cost=args.accept_unmetered_cost,
                         cancel_file=args.cancel_file,
                         progress_callback=progress_callback)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["execution"] in {"PREVIEW_ONLY", "PROCESSES_COMPLETED_NOT_AUDITED"} else 2

if __name__ == "__main__":
    sys.exit(main())
