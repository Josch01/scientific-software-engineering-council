#!/usr/bin/env python3
"""SSEC local worktree coordinator. No automatic commit, merge, push or release."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

if __package__:
    from .configuration import DEFAULT_CONFIG, validate_config, load_config, config_path
    from .prepare_agents import choose_roles, provider_for
    from .route_task import validate_task, required_checks, route
    from .execution_evidence import canonical_task_sha256, candidate_tree_sha256, validate_check_specs
    from .check_runner import read_check_manifest
else:
    from configuration import DEFAULT_CONFIG, validate_config, load_config, config_path
    from prepare_agents import choose_roles, provider_for
    from route_task import validate_task, required_checks, route
    from execution_evidence import canonical_task_sha256, candidate_tree_sha256, validate_check_specs
    from check_runner import read_check_manifest

KINDS = {"build","debug","refactor","optimize","migrate"}
EVENTS = {"WORKER_RESULT","REVIEW_FINDING","REQUEST_CHANGES","BLOCKED"}
STATE_SCHEMA_VERSION = 2
PROCESS_CHECK_IDS = frozenset({"unit_tests","static_analysis","regression"})

def check_requirements(task, policy_evidence=None):
    """Separate executable process checks from non-process acceptance obligations."""
    required=set(required_checks(task))
    if policy_evidence is not None:
        if type(policy_evidence) is not list or any(type(item) is not str or not item for item in policy_evidence):
            raise ValueError("initialized required_evidence must be a list of nonempty strings")
        required.update(policy_evidence)
    specs=validate_check_specs(task)
    process_required=required & PROCESS_CHECK_IDS
    pending_evidence=required - PROCESS_CHECK_IDS
    unsupported={spec.check_id for spec in specs if spec.check_id not in PROCESS_CHECK_IDS}
    return process_required,pending_evidence,unsupported

def _reject_nonprocess_check_specs(task):
    _,_,unsupported=check_requirements(task)
    if unsupported:
        raise ValueError("check_specs cannot represent evidence obligations: "+
                         ", ".join(sorted(unsupported)))

def _task_revision(task):
    revision=task.get("task_revision",task.get("revision","revision-1"))
    if type(revision) is not str or not revision or "\x00" in revision:
        raise ValueError("task revision must be a nonempty NUL-free string")
    return revision

def _task_packet(task):
    validate_task(task)
    digest=canonical_task_sha256(task)
    packet=json.loads(json.dumps(task,ensure_ascii=False,allow_nan=False))
    return packet,digest,_task_revision(packet)

def _write_state(dest,state):
    path=dest/"state.json"
    temporary=dest/(".state.json."+uuid.uuid4().hex+".partial")
    try:
        with temporary.open("x",encoding="utf-8") as stream:
            stream.write(json.dumps(state,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()

def _validate_state_packet(state,task_id):
    if type(state.get("schema_version")) is not int or state["schema_version"]!=STATE_SCHEMA_VERSION:
        raise ValueError("unsupported task metadata schema")
    packet=state.get("task_packet")
    if type(packet) is not dict or packet.get("task_id")!=task_id:
        raise ValueError("task metadata contract packet is missing or mismatched")
    validate_task(packet)
    digest=canonical_task_sha256(packet)
    if type(state.get("task_sha256")) is not str or state["task_sha256"]!=digest:
        raise ValueError("task metadata packet digest mismatch")
    if state.get("task_revision")!=_task_revision(packet):
        raise ValueError("task metadata revision mismatch")
    review_roles=state.get("review_roles")
    if type(review_roles) is not list or any(type(role) is not str for role in review_roles):
        raise ValueError("task metadata review roles are invalid")
    expected_evidence=set(required_checks(packet))
    reviewer_evidence={"software_auditor":"software_review",
                       "independent_reviewer":"independent_review",
                       "security_reviewer":"security_audit",
                       "release_engineer":"release_review"}
    expected_evidence.update(reviewer_evidence[role] for role in review_roles
                             if role in reviewer_evidence)
    if route(packet)["scientific_bridge"]=="REQUIRES_EXTERNAL_SCIENTIFIC_REVIEW":
        expected_evidence.add("scientific_validation")
    required_evidence=state.get("required_evidence")
    if (type(required_evidence) is not list or
            any(type(item) is not str or not item for item in required_evidence) or
            len(required_evidence)!=len(set(required_evidence))):
        raise ValueError("task metadata required_evidence is invalid")
    if set(required_evidence)!=expected_evidence:
        raise ValueError("task metadata required_evidence differs from task and review policy")

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
    packet,task_digest,task_revision=_task_packet(task)
    _reject_nonprocess_check_specs(packet)
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
    return {"schema_version":STATE_SCHEMA_VERSION,"task_packet":packet,
            "task_sha256":task_digest,"task_revision":task_revision,
            "task_id":task["task_id"],"project_root":str(root),"base_commit":base,
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
    _write_state(dest,state)
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
    _validate_state_packet(state,task_id)
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

def _discover_check_manifests(metadata):
    root=metadata/"check-runs"
    paths=[]
    errors=[]
    if not root.exists() and not root.is_symlink():
        return paths,errors
    if root.is_symlink() or not root.is_dir():
        return paths,[{"path":"check-runs","error":"check-run root is not a regular directory"}]
    try:
        for execution in root.iterdir():
            if execution.is_symlink() or not execution.is_dir():
                errors.append({"path":execution.relative_to(metadata).as_posix(),
                               "error":"execution entry is not a regular directory"})
                continue
            for role in execution.iterdir():
                if role.is_symlink() or not role.is_dir():
                    errors.append({"path":role.relative_to(metadata).as_posix(),
                                   "error":"worker entry is not a regular directory"})
                    continue
                manifest=role/"manifest.json"
                if manifest.exists() or manifest.is_symlink():
                    paths.append(manifest)
    except OSError as exc:
        errors.append({"path":"check-runs","error":f"could not inspect check runs: {exc}"})
    return paths,errors

def _manifest_matches_task(path,metadata,state,worker,current_tree,specs):
    relative=path.relative_to(metadata)
    parts=relative.parts
    if len(parts)!=4 or parts[0]!="check-runs" or parts[2]!=worker["role"] or parts[3]!="manifest.json":
        raise ValueError("manifest path does not identify this worker's check run")
    cursor=metadata
    for part in parts:
        cursor=cursor/part
        if cursor.is_symlink():
            raise ValueError("manifest path contains a symlink")
    manifest=read_check_manifest(path,metadata)
    if manifest["execution_id"]!=parts[1]:
        raise ValueError("manifest execution id does not match its metadata path")
    for field,expected in (
        ("task_id",state["task_id"]),
        ("task_revision",state["task_revision"]),
        ("task_sha256",state["task_sha256"]),
        ("base_commit",state["base_commit"]),
        ("worker_role",worker["role"]),
        ("worker_branch",worker["branch"]),
        ("candidate_tree_sha256",current_tree),
    ):
        if manifest[field]!=expected:
            raise ValueError(f"manifest {field} does not match initialized candidate")
    prefix=f"check-runs/{parts[1]}/{worker['role']}/"
    if manifest["snapshot"] is None or manifest["snapshot"]["path"]!=prefix+"snapshot":
        raise ValueError("manifest snapshot is outside its worker run directory")
    items={item["check_id"]:item for item in manifest["checks"]}
    if set(items)!={spec.check_id for spec in specs}:
        raise ValueError("manifest check IDs do not match initialized check specs")
    for spec in specs:
        item=items[spec.check_id]
        if (item["argv"]!=list(spec.argv) or item["cwd"]!=spec.cwd or
                float(item["timeout_seconds"])!=spec.timeout_seconds or item["protocol"]!=spec.protocol):
            raise ValueError(f"manifest command for {spec.check_id} differs from initialized check spec")
        for stream in ("stdout","stderr"):
            if item[f"{stream}_path"]!=prefix+f"{spec.check_id}.{stream}":
                raise ValueError(f"{spec.check_id} {stream} path is outside its worker run directory")
    return manifest

def gate(project,task_id):
    state,metadata=load(project,task_id)
    status=inspect(project,task_id)
    errors=[]
    packet=state["task_packet"]
    specs=validate_check_specs(packet)
    required,pending_evidence,unsupported_specs=check_requirements(packet,state["required_evidence"])
    configured={spec.check_id for spec in specs if spec.check_id in PROCESS_CHECK_IDS}
    missing_specs=required-configured
    paths,invalid_manifests=_discover_check_manifests(metadata)
    if unsupported_specs:
        invalid_manifests.append({"path":"task/check_specs",
            "error":"non-process evidence obligations cannot be executed as check specs",
            "check_ids":sorted(unsupported_specs)})
    parsed=[]
    for path in paths:
        try:
            relative=path.relative_to(metadata)
            data=read_check_manifest(path,metadata)
            if len(relative.parts)!=4 or relative.parts[0]!="check-runs" or relative.parts[3]!="manifest.json":
                raise ValueError("manifest is outside the canonical check-run layout")
            if data["execution_id"]!=relative.parts[1] or data["worker_role"]!=relative.parts[2]:
                raise ValueError("manifest identity does not match its metadata path")
            parsed.append((path,data))
        except (OSError,ValueError,TypeError,KeyError) as exc:
            invalid_manifests.append({"path":path.relative_to(metadata).as_posix(),"error":str(exc)})

    verified=[]
    missing=[]
    for worker in state["workers"]:
        role=worker["role"]
        worker_status=next((item for item in status["workers"] if item["role"]==role),{})
        folder=Path(worker["path"])
        try:
            if worker_status.get("error"):
                raise ValueError(worker_status["error"])
            current_tree=candidate_tree_sha256(folder)
        except (OSError,ValueError) as exc:
            current_tree=None
            invalid_manifests.append({"path":f"worker:{role}","role":role,
                                      "error":f"candidate tree invalid: {exc}"})
        worker_valid=[]
        for path,_manifest in parsed:
            if path.parent.name!=role:
                continue
            try:
                manifest=_manifest_matches_task(path,metadata,state,worker,current_tree,specs)
                if manifest["status"]=="PASSED":
                    worker_valid.append((manifest,sorted(item["check_id"] for item in manifest["checks"])))
            except (OSError,ValueError,TypeError,KeyError) as exc:
                invalid_manifests.append({"path":path.relative_to(metadata).as_posix(),
                                          "role":role,"error":str(exc)})
        if worker_valid:
            manifest,ids=max(worker_valid,key=lambda item:(item[0]["finished_at_utc"],item[0]["execution_id"]))
            process_ids=sorted(set(ids)&PROCESS_CHECK_IDS)
            verified.append({"role":role,"execution_id":manifest["execution_id"],
                             "verified_process_check_ids":process_ids})
            ids=process_ids
        else:
            ids=[]
        not_verified=sorted(required-set(ids))
        if not_verified:
            missing.append({"role":role,"missing_process_check_ids":not_verified})
        if missing_specs:
            for item in missing:
                if item["role"]==role:
                    item["missing_spec_ids"]=sorted(missing_specs)
            if not not_verified:
                missing.append({"role":role,"missing_process_check_ids":[],
                                "missing_spec_ids":sorted(missing_specs)})
    checks_verified=bool(state["workers"]) and not missing and not unsupported_specs
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
    if not checks_verified:
        errors.append("deterministic check evidence is missing, incomplete, or invalid")
    # Deterministic checks cannot replace an independent review or authorize release.
    errors.append("coordinator cannot infer non-process review or release acceptance from deterministic checks")
    events=status["events"]
    for w in state["workers"]:
        if not any(e["sender"]==w["role"] and e["kind"]=="WORKER_RESULT" for e in events):
            errors.append("no handoff: "+w["role"])
    if any(e["kind"] in {"BLOCKED","REQUEST_CHANGES"} for e in events):
        errors.append("unresolved objections")
    return {"status":"BLOCKED","blockers":errors,"collisions":overlaps,
            "automatic_merge":False,"checks_verified":checks_verified,
            "verified_process_check_ids":verified,"missing_process_checks":missing,
            "pending_evidence_ids":sorted(pending_evidence),
            "invalid_check_manifests":invalid_manifests,
            "evidence_verified":False,"release_status":"NOT_APPROVED",
            "note":"Verified worker checks apply only to their separate candidates; mailbox claims cannot establish review or release approval."}

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
