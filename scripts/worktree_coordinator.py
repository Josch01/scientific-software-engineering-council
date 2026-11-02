#!/usr/bin/env python3
"""SSEC local worktree coordinator. No automatic commit, merge, push or release."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

if __package__:
    from .configuration import DEFAULT_CONFIG, validate_config, load_config, config_path
    from .prepare_agents import choose_roles, provider_for
    from .route_task import validate_task
else:
    from configuration import DEFAULT_CONFIG, validate_config, load_config, config_path
    from prepare_agents import choose_roles, provider_for
    from route_task import validate_task

KINDS = {"build","debug","refactor","optimize","migrate"}
EVENTS = {"WORKER_RESULT","REVIEW_FINDING","REQUEST_CHANGES","BLOCKED"}

def git(root, *args, check=True):
    proc = subprocess.run(["git","-C",str(root),*args], text=True, encoding="utf-8",
                          errors="replace", capture_output=True, timeout=30)
    if check and proc.returncode:
        raise ValueError("Git failure: " + proc.stderr.strip()[:400])
    return proc.stdout.strip()

def repository(project, clean=False):
    if not project.is_dir() or project.is_symlink():
        raise ValueError("project must be a directory, not a symlink")
    root = Path(git(project,"rev-parse","--show-toplevel")).resolve()
    if root != project.resolve():
        raise ValueError("provide the root of the Git repository")
    if git(root,"rev-parse","--is-bare-repository") != "false":
        raise ValueError("bare repository unsupported")
    if clean and git(root,"status","--porcelain","--untracked-files=all"):
        raise ValueError("source Git checkout must be clean")
    return root

def directory(root, task_id):
    if not isinstance(task_id,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",task_id):
        raise ValueError("unsafe task_id")
    base = root.parent / ("." + root.name + "-ssec-worktrees")
    if base.is_symlink() or (base / ".ssec-state").is_symlink():
        raise ValueError("symlinked coordinator directory not permitted")
    path = base / ".ssec-state" / task_id
    if path.is_symlink():
        raise ValueError("task metadata symlink forbidden")
    return path

def plan(task, policy, project):
    validate_task(task)
    policy = validate_config(policy)
    if task["kind"] not in KINDS:
        raise ValueError("only build/debug/refactor/optimize/migrate supported")
    if policy["permissions"] == "read_only":
        raise ValueError("read-only policy cannot create development worktrees")
    root = repository(project, clean=True)
    directory(root,task["task_id"])
    base = git(root,"rev-parse","HEAD")
    impl, reviewers, evidence = choose_roles(task,policy)
    parent = root.parent / ("." + root.name + "-ssec-worktrees")
    if parent.is_symlink():
        raise ValueError("worktree storage symlink forbidden")
    workers=[]
    for role in dict.fromkeys(impl):
        branch = "ssec/" + task["task_id"] + "/" + role.replace("_","-")
        git(root,"check-ref-format","--branch",branch)
        path = parent / task["task_id"] / role
        if path.exists() or path.is_symlink():
            raise FileExistsError("existing worktree: " + str(path))
        if git(root,"for-each-ref","--format=%(refname)","refs/heads/"+branch):
            raise ValueError("branch already exists: " + branch)
        workers.append({"role":role,"provider":provider_for(role,policy["provider_mode"]),
                        "branch":branch,"path":str(path)})
    return {"task_id":task["task_id"],"project_root":str(root),"base_commit":base,
            "mode":policy["provider_mode"],"workers":workers,"review_roles":reviewers,
            "required_evidence":evidence,"status":"PREVIEW_NOT_STARTED",
            "auto_merge":False,"note":"Git worktrees share metadata; they are NOT OS sandboxes."}

def initialize(task, policy, project, apply=False):
    state = plan(task,policy,project)
    if not apply:
        return state
    root = Path(state["project_root"])
    dest = directory(root,task["task_id"])
    if dest.exists():
        raise FileExistsError("task already initialized")
    for worker in state["workers"]:
        path = Path(worker["path"])
        path.parent.mkdir(parents=True,exist_ok=True)
        git(root,"worktree","add","-b",worker["branch"],str(path),state["base_commit"])
    dest.mkdir(parents=True,exist_ok=False)
    state["status"] = "WORKTREES_READY_UNREVIEWED"
    state["created_at_unix"] = time.time()
    (dest/"state.json").write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (dest/"mailbox.jsonl").write_text("",encoding="utf-8")
    return state

def load(project, task_id):
    root = repository(project)
    dest = directory(root,task_id)
    if (dest/"state.json").is_symlink():
        raise ValueError("metadata symlink forbidden")
    state=json.loads((dest/"state.json").read_text(encoding="utf-8"))
    if state["task_id"] != task_id or state["project_root"] != str(root):
        raise ValueError("task belongs to a different project")
    return state,dest

def message(project, task_id, sender, kind, summary, artifact=""):
    state,dest=load(project,task_id)
    roles={w["role"] for w in state["workers"]}
    reviewers=set(state["review_roles"])
    if kind not in EVENTS or sender not in roles | reviewers:
        raise ValueError("unknown role or event type")
    if not isinstance(summary,str) or not 1 <= len(summary) <= 12000:
        raise ValueError("invalid summary")
    if not isinstance(artifact,str) or len(artifact)>300 or any(c in artifact for c in "\r\n\x00"):
        raise ValueError("invalid artifact reference")
    if kind in {"REVIEW_FINDING","REQUEST_CHANGES"} and sender not in reviewers:
        raise ValueError("only reviewers can submit review findings or change requests")
    if kind == "WORKER_RESULT" and sender not in roles:
        raise ValueError("reviewers cannot impersonate workers")
    event={"id":uuid.uuid4().hex,"task_id":task_id,"time":time.time(),
           "sender":sender,"kind":kind,"summary":summary,"artifact":artifact}
    path=dest/"mailbox.jsonl"
    if path.is_symlink():
        raise ValueError("mailbox symlink forbidden")
    with path.open("a",encoding="utf-8") as f:
        f.write(json.dumps(event,ensure_ascii=False)+"\n")
    return event

def inspect(project,task_id):
    state,dest=load(project,task_id)
    root=Path(state["project_root"])
    results=[]
    for w in state["workers"]:
        folder=Path(w["path"])
        if not folder.is_dir() or folder.is_symlink():
            results.append({"role":w["role"],"error":"worktree missing"})
            continue
        if git(folder,"symbolic-ref","--short","HEAD") != w["branch"]:
            results.append({"role":w["role"],"error":"unexpected branch"})
            continue
        changed=git(folder,"diff","--name-only",state["base_commit"]).splitlines()
        untracked=git(folder,"ls-files","--others","--exclude-standard").splitlines()
        diff=git(folder,"diff","--binary",state["base_commit"])
        results.append({"role":w["role"],"branch":w["branch"],
                        "changed_files":sorted(set(changed+untracked)),
                        "diff_sha256":hashlib.sha256((diff+"\n"+"\n".join(untracked)).encode()).hexdigest(),
                        "has_changes":bool(changed or untracked),
                        "diff_check":git(folder,"diff","--check",state["base_commit"],check=False)})
    events=[json.loads(line) for line in (dest/"mailbox.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return {"task_id":task_id,"workers":results,"events":events,
            "base_unchanged":git(root,"rev-parse","HEAD")==state["base_commit"],
            "source_clean":not bool(git(root,"status","--porcelain","--untracked-files=all")),
            "release_status":"NOT_APPROVED"}

def gate(project,task_id):
    state,_=load(project,task_id)
    status=inspect(project,task_id)
    # Mailbox content is untrusted. A coordinator evidence producer is not yet implemented.
    errors=["coordinator-verified test and review evidence is unavailable"]
    if not status["base_unchanged"] or not status["source_clean"]:
        errors.append("original checkout changed since initialization")
    seen={}
    for w in status["workers"]:
        if w.get("error") or w.get("diff_check"):
            errors.append(w["role"]+": invalid worktree or diff")
        for path in w.get("changed_files",[]):
            seen.setdefault(path,[]).append(w["role"])
    overlaps={k:v for k,v in seen.items() if len(v)>1}
    if overlaps: errors.append("overlapping changed paths")
    if not seen: errors.append("no candidate changes")
    events=status["events"]
    for w in state["workers"]:
        if not any(e["sender"]==w["role"] and e["kind"]=="WORKER_RESULT" for e in events):
            errors.append("no handoff: "+w["role"])
    if any(e["kind"] in {"BLOCKED","REQUEST_CHANGES"} for e in events):
        errors.append("unresolved objections")
    return {"status":"BLOCKED",
            "blockers":errors,"collisions":overlaps,"automatic_merge":False,
            "evidence_verified":False,"release_status":"NOT_APPROVED",
            "note":"Mailbox claims cannot authorize test success or review acceptance; coordinator evidence is required."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for op in ("plan","init"):
        x=sub.add_parser(op)
        x.add_argument("task_json",type=Path)
        x.add_argument("--project",type=Path,required=True)
        x.add_argument("--config",type=Path)
        if op=="init": x.add_argument("--apply",action="store_true",required=True)
    for op in ("status","gate"):
        x=sub.add_parser(op)
        x.add_argument("--project",type=Path,required=True)
        x.add_argument("--task-id",required=True)
    x=sub.add_parser("message")
    x.add_argument("--project",type=Path,required=True)
    x.add_argument("--task-id",required=True)
    x.add_argument("--sender",required=True)
    x.add_argument("--kind",choices=sorted(EVENTS),required=True)
    x.add_argument("--summary",required=True)
    x.add_argument("--artifact",default="")
    a=p.parse_args()
    try:
        if a.command in ("plan","init"):
            path=a.config or config_path(a.project)
            policy=load_config(path) if path.is_file() else dict(DEFAULT_CONFIG)
            task=json.loads(a.task_json.read_text(encoding="utf-8"))
            data=initialize(task,policy,a.project,apply=(a.command=="init"))
        elif a.command=="status":
            data=inspect(a.project,a.task_id)
        elif a.command=="gate":
            data=gate(a.project,a.task_id)
        else:
            data=message(a.project,a.task_id,a.sender,a.kind,a.summary,a.artifact)
    except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(data,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    sys.exit(main())
