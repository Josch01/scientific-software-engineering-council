"""SSEC development worktrees, communication, approvals and dry-run."""
import json
from dataclasses import replace
import os
import hashlib
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from scripts.execution_evidence import canonical_task_sha256, candidate_tree_sha256
from scripts.configuration import DEFAULT_CONFIG
from scripts.prepare_agents import choose_roles
from scripts.worktree_coordinator import plan,initialize,inspect,message,gate,load
from scripts.development_runner import (_cli_exit_code, execute, run_worker, _review_diff,
                                       _MAX_REVIEW_DIFF_BYTES, _persist_review_artifacts,
                                       _relative_metadata_path)
from scripts.agent_runtime import FakeRuntime, RuntimeCapabilities, RuntimeCapabilityStatus, RuntimeStatus
from scripts.provider_runtimes import GeminiRuntime

TASK={"task_id":"SSEC-TEST","kind":"build","request":"Implement a scientific solver",
      "domains":["numerical"],"languages":["python"],"interfaces":["cli"],
      "targets":["linux"],"risk":"R1","runtime":{}}
POLICY=dict(DEFAULT_CONFIG,provider_mode="both")

def task_with_checks():
    task=dict(TASK,domains=["general"],check_specs=[
        {"check_id":"unit_tests","argv":[sys.executable,"-P","-m","unittest","discover","-s","tests","-t",".","-v"],
         "cwd":".","timeout_seconds":20,"protocol":"unittest"},
        {"check_id":"static_analysis","argv":[sys.executable,"-c",
         "compile(open('solver.py',encoding='utf-8').read(),'solver.py','exec')"],
         "cwd":".","timeout_seconds":20,"protocol":"exit_code"},
    ])
    return task


class LocalPythonRuntime(GeminiRuntime):
    """Real local Python child process for offline integration tests; not provider E2E."""
    provider="local-python"

    def discover_capabilities(self):
        self._command=(sys.executable,)
        return RuntimeCapabilities("local-python",True,None,(),None,
                                   RuntimeCapabilityStatus.UNKNOWN)

    def build_argv(self,request):
        code=("from pathlib import Path;import json,sys;"
              "Path('solver.py').write_text('x=2\\n');"
              "print(json.dumps({'type':'init','session_id':'local-python-session'}));"
              "print(json.dumps({'type':'result','status':'success','stats':{}}));"
              "print('local diagnostic',file=sys.stderr)")
        return (sys.executable,"-c",code)

def git(root,*args):
    return subprocess.run(["git","-C",str(root),*args],check=True,
                          capture_output=True,text=True).stdout.strip()

class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"science"
        self.root.mkdir()
        git(self.root,"init","-b","main")
        git(self.root,"config","user.email","test@example.invalid")
        git(self.root,"config","user.name","SSEC Test")
        (self.root/"solver.py").write_text("x=1\n",encoding="utf-8")
        (self.root/".gitignore").write_text("__pycache__/\n",encoding="utf-8")
        tests=self.root/"tests"
        tests.mkdir()
        (tests/"__init__.py").write_text("",encoding="utf-8")
        (tests/"test_solver.py").write_text(
            "import unittest\nimport solver\n\n"
            "class SolverTests(unittest.TestCase):\n"
            "    def test_positive_value(self):\n"
            "        self.assertGreater(solver.x, 0)\n",encoding="utf-8")
        git(self.root,"add",".")
        git(self.root,"commit","-m","initial")

    def test_plan_is_read_only(self):
        x=plan(TASK,POLICY,self.root)
        self.assertEqual(x["status"],"PREVIEW_NOT_STARTED")
        self.assertEqual(len(git(self.root,"worktree","list","--porcelain").split("worktree ")),2)

    def test_plan_validates_role_owned_work_items_before_initializing(self):
        task=task_with_checks()
        roles,reviewers,_=choose_roles(task,POLICY)
        from tests.test_work_items import work_item
        task["work_items"]=[work_item(role,required_reviewers=reviewers) for role in roles]
        state=plan(task,POLICY,self.root)
        self.assertEqual(state["task_packet"]["work_items"],task["work_items"])
        for bad_items in (task["work_items"][:-1],
                          [dict(item,tests=["undeclared"]) for item in task["work_items"]]):
            with self.subTest(items=bad_items),self.assertRaises(ValueError):
                plan(dict(task,work_items=bad_items),POLICY,self.root)
        self.assertEqual(len(git(self.root,"worktree","list","--porcelain").split("worktree ")),2)

    def test_load_revalidates_work_items_even_with_recomputed_packet_digest(self):
        task=task_with_checks()
        roles,reviewers,_=choose_roles(task,POLICY)
        from tests.test_work_items import work_item
        task["work_items"]=[work_item(role,required_reviewers=reviewers) for role in roles]
        state=initialize(task,POLICY,self.root,apply=True)
        _,dest=load(self.root,task["task_id"])
        state["task_packet"]["work_items"][0]["dependencies"]=["unsupported"]
        state["task_sha256"]=canonical_task_sha256(state["task_packet"])
        (dest/"state.json").write_text(json.dumps(state),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"dependencies"):
            load(self.root,task["task_id"])

    def test_legacy_packet_loads_but_gate_explicitly_blocks_missing_work_items(self):
        initialize(TASK,POLICY,self.root,apply=True)
        state,_=load(self.root,TASK["task_id"])
        self.assertNotIn("work_items",state["task_packet"])
        result=gate(self.root,TASK["task_id"])
        self.assertEqual(result["status"],"BLOCKED")
        self.assertTrue(any("work_items" in reason for reason in result["blockers"]))

    def test_real_branches_are_independent(self):
        x=initialize(TASK,POLICY,self.root,apply=True)
        self.assertGreaterEqual(len(x["workers"]),2)
        first=Path(x["workers"][0]["path"])
        second=Path(x["workers"][1]["path"])
        (first/"solver.py").write_text("x=2\n",encoding="utf-8")
        self.assertEqual((second/"solver.py").read_text(),"x=1\n")
        self.assertEqual((self.root/"solver.py").read_text(),"x=1\n")
        self.assertTrue(inspect(self.root,TASK["task_id"])["base_unchanged"])
        self.assertFalse(git(self.root,"status","--porcelain"))

    def test_mailbox_rejects_worker_self_review(self):
        x=initialize(TASK,POLICY,self.root,apply=True)
        worker=x["workers"][0]["role"]
        with self.assertRaises(ValueError):
            message(self.root,TASK["task_id"],worker,"REVIEW_ACCEPTED","looks good")
        message(self.root,TASK["task_id"],worker,"WORKER_RESULT","work proposed")
        self.assertEqual(len(inspect(self.root,TASK["task_id"])["events"]),1)

    def test_mailbox_rejects_privileged_events_for_every_sender(self):
        state=initialize(TASK,POLICY,self.root,apply=True)
        senders=[w["role"] for w in state["workers"]]+state["review_roles"]
        for sender in senders:
            for kind in ("REVIEW_ACCEPTED","TEST_RESULT"):
                with self.subTest(sender=sender,kind=kind):
                    with self.assertRaises(ValueError):
                        message(self.root,TASK["task_id"],sender,kind,"unit_tests:PASS")
        self.assertEqual(inspect(self.root,TASK["task_id"])["events"],[])

    def test_gate_ignores_privileged_events_injected_into_mailbox(self):
        state=initialize(TASK,POLICY,self.root,apply=True)
        (Path(state["workers"][0]["path"])/"solver.py").write_text("x=2\n",encoding="utf-8")
        events=[{"sender":w["role"],"kind":"WORKER_RESULT","summary":"done"}
                for w in state["workers"]]
        events.extend({"sender":r,"kind":"REVIEW_ACCEPTED","summary":"accepted"}
                      for r in state["review_roles"])
        events.extend({"sender":state["workers"][0]["role"],"kind":"TEST_RESULT",
                       "summary":name+":PASS"} for name in state["required_evidence"])
        _,dest=load(self.root,TASK["task_id"])
        (dest/"mailbox.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events),encoding="utf-8")
        result=gate(self.root,TASK["task_id"])
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse(result["evidence_verified"])
        self.assertTrue(any("coordinator" in reason for reason in result["blockers"]))
        self.assertEqual(result["release_status"],"NOT_APPROVED")

    def test_gate_blocks_missing_checks_and_collisions(self):
        x=initialize(TASK,POLICY,self.root,apply=True)
        self.assertEqual(gate(self.root,TASK["task_id"])["status"],"BLOCKED")
        for w in x["workers"][:2]:
            (Path(w["path"])/"solver.py").write_text("x=100\n")
        result=gate(self.root,TASK["task_id"])
        self.assertIn("solver.py",result["collisions"])
        self.assertEqual(result["release_status"],"NOT_APPROVED")

    def test_wrong_task_or_dirty_source_rejected(self):
        (self.root/"newfile").write_text("dirty")
        with self.assertRaises(ValueError):
            plan(TASK,POLICY,self.root)
        (self.root/"newfile").unlink()
        with self.assertRaises(ValueError):
            plan(dict(TASK,task_id="../escape"),POLICY,self.root)

    def test_execute_requires_explicit_ack(self):
        initialize(TASK,POLICY,self.root,apply=True)
        self.assertEqual(execute(self.root,TASK["task_id"],TASK)["execution"],"PREVIEW_ONLY")
        with self.assertRaisesRegex(ValueError,"unmetered"):
            execute(self.root,TASK["task_id"],TASK,launch=True)

    def test_initialize_binds_complete_packet_revision_and_digest(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        self.assertEqual(state["task_packet"],task)
        self.assertEqual(state["task_sha256"],canonical_task_sha256(task))
        self.assertEqual(state["task_revision"],"revision-1")
        loaded,_=load(self.root,task["task_id"])
        self.assertEqual(loaded["task_packet"]["check_specs"],task["check_specs"])

    def test_execute_rejects_task_digest_drift_before_runtime_launch(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        changed=dict(task,request="a different request with the same id")
        calls=[]
        def runtime_factory(provider):
            calls.append(provider)
            return FakeRuntime((RuntimeStatus.SUCCEEDED,))
        with self.assertRaisesRegex(ValueError,"digest|packet"):
            execute(self.root,task["task_id"],changed,launch=True,cost_ack=True,
                    runtime_factory=runtime_factory)
        self.assertEqual(calls,[])

    def test_real_local_execution_runs_per_worker_checks_and_gate_stays_blocked(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,parallel=2,
                       minutes=1,runtime_factory=lambda provider: LocalPythonRuntime())
        self.assertEqual(report["process_execution"],"PROCESSES_FINISHED_UNREVIEWED")
        self.assertEqual(report["execution"],"REVIEW_INCOMPLETE",
                         {"checks":report["check_evidence"],"workers":report["results"]})
        self.assertEqual(report["release_status"],"NOT_APPROVED")
        evidence=report["check_evidence"]
        self.assertEqual({item["role"] for item in evidence},{w["role"] for w in state["workers"]})
        self.assertTrue(all(item["status"]=="PASSED" for item in evidence))
        self.assertEqual(len({item["manifest_path"] for item in evidence}),len(evidence))
        self.assertTrue(all(item["verified_process_check_ids"]==["unit_tests","static_analysis"]
                            for item in evidence))
        gate_result=gate(self.root,task["task_id"])
        self.assertEqual(gate_result["status"],"BLOCKED")
        self.assertTrue(gate_result["checks_verified"])
        self.assertFalse(gate_result["evidence_verified"])
        self.assertEqual(gate_result["release_status"],"NOT_APPROVED")
        self.assertEqual({item["role"] for item in gate_result["verified_process_check_ids"]},
                         {w["role"] for w in state["workers"]})

    def test_high_risk_process_checks_do_not_satisfy_other_evidence_obligations(self):
        task=task_with_checks()
        task.update(risk="R2",interfaces=["desktop_gui"],targets=["windows","linux"],
                    languages=["python","idl"])
        state=initialize(task,POLICY,self.root,apply=True)
        report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,parallel=4,
                       minutes=2,runtime_factory=lambda provider: LocalPythonRuntime())
        expected={"software_review","independent_review","security_audit","release_review",
                  "scientific_validation","gui_smoke","cross_platform","idl_integration"}
        self.assertEqual(report["execution"],"REVIEW_BLOCKED_INVOCATION_LIMIT",
                         {"check_evidence":report["check_evidence"],
                          "worker_results":report["results"]})
        self.assertEqual(set(report["pending_evidence_ids"]),expected)
        self.assertTrue(all(set(item["verified_process_check_ids"])==
                            {"unit_tests","static_analysis"} for item in report["check_evidence"]))
        gate_result=gate(self.root,task["task_id"])
        self.assertTrue(gate_result["checks_verified"])
        self.assertEqual(set(gate_result["pending_evidence_ids"]),expected)
        self.assertEqual(gate_result["status"],"BLOCKED")
        self.assertFalse(gate_result["evidence_verified"])
        self.assertEqual(gate_result["release_status"],"NOT_APPROVED")
        self.assertEqual(len(state["workers"]),len(report["check_evidence"]))

    def test_cli_exit_code_is_nonzero_while_review_is_incomplete(self):
        for execution in ("CHECKS_VERIFIED_AWAITING_REVIEW", "REVIEW_INCOMPLETE",
                          "REVIEW_BLOCKED", "REVIEW_BLOCKED_INVOCATION_LIMIT",
                          "REVIEW_FINDINGS_AWAITING_FIX"):
            with self.subTest(execution=execution):
                self.assertEqual(_cli_exit_code({"execution":execution}),2)
        self.assertEqual(_cli_exit_code({"execution":"PREVIEW_ONLY"}),0)

    def test_attempt_persistence_failure_prevents_successful_review_manifest(self):
        attempt={"schema_version":1,"task_id":"task-1","task_revision":"rev-1",
            "task_sha256":"a"*64,"base_commit":"b"*40,"worker_role":"worker",
            "reviewer_role":"independent_reviewer","requested_provider":"gemini",
            "runtime_run_id":"run-1","runtime_adapter_type":None,"identity":None,
            "status":"FAILED","review_independence":"UNVERIFIED_WITHOUT_PROVIDER_E2E",
            "started_at_utc":"2026-11-02T00:00:00Z",
            "finished_at_utc":"2026-11-02T00:00:01Z","error":"fixture failure"}
        attempt_path=self.root/"attempt.json"
        manifest_path=self.root/"manifest.json"
        with patch("scripts.development_runner._write_review_json",
                   side_effect=OSError("attempt storage unavailable")) as write_json, \
                patch("scripts.development_runner.validate_review_manifest") as validate_manifest:
            with self.assertRaisesRegex(OSError,"attempt storage unavailable"):
                _persist_review_artifacts(attempt,attempt_path,{"status":"PASSED"},
                                          manifest_path,self.root)

        write_json.assert_called_once()
        self.assertEqual(write_json.call_args.args[0],attempt_path)
        validate_manifest.assert_not_called()
        self.assertFalse(manifest_path.exists())

    def test_manifest_persistence_failure_marks_successful_attempt_failed(self):
        from scripts.development_runner import _write_review_json
        from scripts.review_evidence import validate_review_attempt
        identity={"task_id":"task-1","task_revision":"rev-1","task_sha256":"a"*64,
            "base_commit":"b"*40,"worker_role":"worker","candidate_tree_sha256":"c"*64,
            "diff_sha256":"d"*64,"check_manifest_sha256":"e"*64}
        attempt={"schema_version":1,"task_id":"task-1","task_revision":"rev-1",
            "task_sha256":"a"*64,"base_commit":"b"*40,"worker_role":"worker",
            "reviewer_role":"independent_review","requested_provider":"gemini",
            "runtime_run_id":"run-1","runtime_adapter_type":"scripts.provider_runtimes.GeminiRuntime",
            "identity":identity,"status":"REVIEW_REPORT_VALID",
            "review_independence":"UNVERIFIED_WITHOUT_PROVIDER_E2E",
            "started_at_utc":"2026-11-02T00:00:00Z",
            "finished_at_utc":"2026-11-02T00:00:01Z","error":None}
        attempt_path=self.root/"attempt.json"
        manifest_path=self.root/"manifest.json"
        def fail_manifest_write(path,data,**kwargs):
            if path==manifest_path:
                raise OSError("manifest storage unavailable")
            return _write_review_json(path,data,**kwargs)

        with patch("scripts.development_runner._write_review_json",
                   side_effect=fail_manifest_write):
            with patch("scripts.development_runner.validate_review_manifest",
                       return_value={"status":"PASSED"}):
                with self.assertRaisesRegex(OSError,"manifest storage unavailable"):
                    _persist_review_artifacts(attempt,attempt_path,{"status":"PASSED"},
                                              manifest_path,self.root)

        persisted=validate_review_attempt(json.loads(attempt_path.read_text(encoding="utf-8")))
        self.assertEqual(persisted["status"],"FAILED")
        self.assertIn("manifest storage unavailable",persisted["error"])
        self.assertFalse(manifest_path.exists())

    def test_relative_metadata_path_accepts_windows_short_path_alias(self):
        if os.name != "nt":
            self.skipTest("Windows short paths are specific to Windows")
        import ctypes

        metadata=self.root.parent/"metadata"
        metadata.mkdir()
        (metadata/"attempt.json").write_text("{}",encoding="utf-8")
        short_path=ctypes.create_unicode_buffer(32768)
        get_short_path=ctypes.WinDLL("kernel32",use_last_error=True).GetShortPathNameW
        get_short_path.argtypes=(ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32)
        get_short_path.restype=ctypes.c_uint32
        length=get_short_path(str(metadata),short_path,len(short_path))
        if not length or length>=len(short_path):
            self.skipTest("Windows short path lookup is unavailable")
        alias=Path(short_path.value)
        if os.path.normcase(os.path.abspath(alias))==os.path.normcase(os.path.abspath(metadata)):
            self.skipTest("this volume does not expose a distinct short path")

        self.assertEqual(_relative_metadata_path(alias/"attempt.json",metadata),"attempt.json")

    def test_review_diff_bounds_tracked_and_untracked_candidate_content(self):
        state={"base_commit":git(self.root,"rev-parse","HEAD")}
        worker={"path":str(self.root)}
        (self.root/"solver.py").write_text("x="+"1"*_MAX_REVIEW_DIFF_BYTES+"\n",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"bounded command output exceeds"):
            _review_diff(worker,state)

        (self.root/"solver.py").write_text("x=1\n",encoding="utf-8")
        for index in range(80):
            (self.root/f"untracked-{index:03}.txt").write_text("x"*16_000,encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"bounded review input size"):
            _review_diff(worker,state)

    def test_review_diff_disables_repository_textconv_filters(self):
        state={"base_commit":git(self.root,"rev-parse","HEAD")}
        marker=Path(self.tmp.name)/"textconv-marker.txt"
        script=Path(self.tmp.name)/"textconv_probe.py"
        script.write_text("from pathlib import Path\n"
                          f"Path({str(marker)!r}).write_text('executed')\n"
                          "print('converted')\n",encoding="utf-8")
        attributes=self.root/".git"/"info"/"attributes"
        attributes.write_text("*.py diff=ssec-probe\n",encoding="utf-8")
        git(self.root,"config","diff.ssec-probe.textconv",
            shlex.join([sys.executable,str(script)]))
        (self.root/"solver.py").write_text("x=2\n",encoding="utf-8")

        diff,_=_review_diff({"path":str(self.root)},state)

        self.assertIn("x=2",diff)
        self.assertFalse(marker.exists(),"repository textconv filter executed during review preparation")

    def test_pending_evidence_matches_task_and_policy_requirements(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        expected=set(state["required_evidence"]) - {"unit_tests","static_analysis","regression"}
        self.assertEqual(expected,{"software_review","independent_review"})

        report=execute(self.root,task["task_id"],task)
        self.assertEqual(set(report["pending_evidence_ids"]),expected)
        result=gate(self.root,task["task_id"])
        self.assertEqual(set(result["pending_evidence_ids"]),expected)

    def test_basic_policy_reports_software_review_without_inventing_other_obligations(self):
        task=task_with_checks()
        task["task_id"]="SSEC-BASIC-TEST"
        policy=dict(POLICY,audit_level="basic")
        state=initialize(task,policy,self.root,apply=True)
        expected={"software_review"}
        self.assertEqual(set(state["required_evidence"]) -
                         {"unit_tests","static_analysis","regression"},expected)

        report=execute(self.root,task["task_id"],task)
        self.assertEqual(set(report["pending_evidence_ids"]),expected)
        result=gate(self.root,task["task_id"])
        self.assertEqual(set(result["pending_evidence_ids"]),expected)

    def test_load_rejects_removed_policy_required_independent_review(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        self.assertIn("independent_reviewer",state["review_roles"])
        self.assertIn("independent_review",state["required_evidence"])

        persisted,metadata=load(self.root,task["task_id"])
        persisted["review_roles"].remove("independent_reviewer")
        persisted["required_evidence"].remove("independent_review")
        (metadata/"state.json").write_text(json.dumps(persisted),encoding="utf-8")

        with self.assertRaisesRegex(ValueError,"review roles|policy"):
            load(self.root,task["task_id"])

    def test_load_rejects_omitted_expected_implementation_worker(self):
        state=initialize(TASK,POLICY,self.root,apply=True)
        self.assertGreaterEqual(len(state["workers"]),2)

        persisted,metadata=load(self.root,TASK["task_id"])
        persisted["workers"].pop()
        (metadata/"state.json").write_text(json.dumps(persisted),encoding="utf-8")

        with self.assertRaisesRegex(ValueError,"worker"):
            load(self.root,TASK["task_id"])

    def test_gate_rejects_post_run_snapshot_tampering(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,parallel=2,
                       minutes=1,runtime_factory=lambda provider: LocalPythonRuntime())
        self.assertEqual(report["execution"],"REVIEW_INCOMPLETE",
                         report["check_evidence"])
        _,metadata=load(self.root,task["task_id"])
        evidence=next(item for item in report["check_evidence"]
                      if item["role"]==state["workers"][0]["role"])
        snapshot=(metadata/Path(evidence["manifest_path"])).parent/"snapshot"
        (snapshot/"post-run-tamper.txt").write_text("tampered archived snapshot\n",encoding="utf-8")

        result=gate(self.root,task["task_id"])

        self.assertFalse(result["checks_verified"])
        self.assertTrue(result["invalid_check_manifests"])
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse(result["evidence_verified"])
        self.assertEqual(result["release_status"],"NOT_APPROVED")

    def test_process_check_specs_cannot_claim_review_or_scientific_obligations(self):
        task=task_with_checks()
        task["risk"]="R2"
        task["check_specs"].append({"check_id":"independent_review","argv":[sys.executable,"-c","print('PASS')"],
                                    "cwd":".","timeout_seconds":20,"protocol":"exit_code"})
        with self.assertRaisesRegex(ValueError,"process check|obligation"):
            plan(task,POLICY,self.root)

    def test_gate_rejects_manifest_tampering_and_tracked_or_untracked_candidate_drift(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,parallel=2,
                       minutes=1,runtime_factory=lambda provider: LocalPythonRuntime())
        self.assertEqual(report["execution"],"REVIEW_INCOMPLETE",
                         {"checks":report["check_evidence"],"workers":report["results"]})

        _,metadata=load(self.root,task["task_id"])
        manifest=metadata/Path(report["check_evidence"][0]["manifest_path"])
        original=manifest.read_text(encoding="utf-8")
        data=json.loads(original)
        data["checks"][0]["argv"][0]="forged-worker-command"
        manifest.write_text(json.dumps(data),encoding="utf-8")
        result=gate(self.root,task["task_id"])
        self.assertFalse(result["checks_verified"])
        self.assertTrue(result["invalid_check_manifests"])
        self.assertEqual(result["release_status"],"NOT_APPROVED")
        manifest.write_text(original,encoding="utf-8")

        worker=next(w for w in state["workers"] if w["role"]==report["check_evidence"][0]["role"])
        folder=Path(worker["path"])
        baseline=candidate_tree_sha256(folder)
        (folder/"new-candidate.txt").write_text("untracked edit\n",encoding="utf-8")
        self.assertNotEqual(candidate_tree_sha256(folder),baseline)
        result=gate(self.root,task["task_id"])
        self.assertFalse(result["checks_verified"])
        self.assertIn(worker["role"],{item["role"] for item in result["invalid_check_manifests"]})
        (folder/"new-candidate.txt").unlink()
        (folder/"solver.py").write_text("x=99\n",encoding="utf-8")
        result=gate(self.root,task["task_id"])
        self.assertFalse(result["checks_verified"])
        self.assertIn(worker["role"],{item["role"] for item in result["invalid_check_manifests"]})

    def test_local_python_child_process_and_log_lifecycle_not_provider_e2e(self):
        x=initialize(TASK,POLICY,self.root,apply=True)

        result=execute(self.root,TASK["task_id"],TASK,launch=True,
                       cost_ack=True,parallel=1,minutes=1,
                       runtime_factory=lambda provider: LocalPythonRuntime())
        self.assertEqual(result["execution"],"NOT_RUN")
        self.assertEqual(result["process_execution"],"PROCESSES_FINISHED_UNREVIEWED")
        self.assertEqual((self.root/"solver.py").read_text(),"x=1\n")
        self.assertEqual((Path(x["workers"][0]["path"])/"solver.py").read_text(),"x=2\n")
        self.assertEqual(len(result["results"]),len(x["workers"]))
        for observed in result["results"]:
            self.assertEqual(observed["provider"],"local-python")
            self.assertEqual(observed["status"],"SUCCEEDED")
            self.assertEqual(observed["exit_code"],0)
            self.assertEqual(observed["provider_session_id"],"local-python-session")
            self.assertEqual(observed["observed_child_agent_ids"],())
            for name in ("stdout","stderr"):
                payload=Path(observed[name+"_path"]).read_bytes()
                self.assertEqual(observed[name+"_sha256"],hashlib.sha256(payload).hexdigest())
        self.assertFalse(gate(self.root,TASK["task_id"])["automatic_merge"])

    def test_reviewers_run_only_after_checks_and_fake_runtime_never_counts_as_review(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        fake_review_runtimes=[]
        factory_calls=[]
        def factory(provider):
            is_reviewer=len(factory_calls)>=len(state["workers"])
            factory_calls.append(("reviewer" if is_reviewer else "worker",provider))
            if not is_reviewer:
                return LocalPythonRuntime()
            if provider=="gemini":
                runtime=FakeRuntime((RuntimeStatus.SUCCEEDED,))
                fake_review_runtimes.append(runtime)
                return runtime
            return LocalPythonRuntime()

        report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,
                       parallel=1,minutes=2,runtime_factory=factory)

        self.assertEqual(report["check_status"],"CHECKS_VERIFIED_AWAITING_REVIEW")
        self.assertEqual(report["execution"],"REVIEW_INCOMPLETE")
        self.assertEqual(len(factory_calls),len(state["workers"])+
                         len(state["review_roles"]) * len(state["workers"]))
        self.assertEqual(sum(kind=="reviewer" for kind,_ in factory_calls),
                         len(state["review_roles"]) * len(state["workers"]))
        self.assertTrue(report["review_evidence"])
        self.assertTrue(all(item["status"]=="UNVERIFIED_RUNTIME_ADAPTER"
                            for item in report["review_evidence"]))
        from scripts.review_evidence import validate_review_manifest
        _,metadata=load(self.root,task["task_id"])
        for evidence in report["review_evidence"]:
            manifest_path=metadata/Path(evidence["manifest_path"])
            manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
            verified=validate_review_manifest(manifest,metadata)
            self.assertEqual(verified["status"],"FAILED")
            self.assertIsNone(verified["review_report"])
        self.assertTrue(all(runtime.invocations==[] for runtime in fake_review_runtimes))
        gate_result=gate(self.root,task["task_id"])
        self.assertTrue(gate_result["checks_verified"])
        self.assertEqual(gate_result["status"],"BLOCKED")
        self.assertFalse(gate_result["evidence_verified"])
        self.assertEqual(report["release_status"],"NOT_APPROVED")
        self.assertFalse(any(event["kind"]=="REVIEW_ACCEPTED"
                             for event in inspect(self.root,task["task_id"])["events"]))

    def test_review_persists_logical_modes_for_executable_baseline_without_provider_e2e(self):
        from scripts.review_evidence import validate_review_manifest
        path=self.root/"baseline.sh"
        path.write_bytes(b"#!/bin/sh\necho baseline\n")
        if os.name!="nt":
            path.chmod(path.stat().st_mode|0o100)
        git(self.root,"add","baseline.sh")
        git(self.root,"update-index","--chmod=+x","baseline.sh")
        git(self.root,"commit","-m","executable baseline")
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        calls=[]
        def factory(provider):
            is_reviewer=len(calls)>=len(state["workers"])
            calls.append(provider)
            return FakeRuntime((RuntimeStatus.SUCCEEDED,)) if is_reviewer else LocalPythonRuntime()
        report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,parallel=1,
                       minutes=2,runtime_factory=factory)
        self.assertEqual(report["check_status"],"CHECKS_VERIFIED_AWAITING_REVIEW")
        self.assertTrue(report["review_evidence"])
        _,metadata=load(self.root,task["task_id"])
        for result in report["review_evidence"]:
            manifest=json.loads((metadata/result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"],2)
            self.assertIn({"path":"baseline.sh","executable":True},manifest["snapshot_logical_modes"])
            self.assertEqual(validate_review_manifest(manifest,metadata)["status"],"FAILED")
            self.assertIsNone(manifest["review_report"])

    def test_failed_deterministic_check_prevents_any_reviewer_runtime(self):
        from scripts.check_runner import CheckRunResult
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        selected=[]
        with patch("scripts.development_runner.run_checks",
                   return_value=CheckRunResult("FAILED","failed-check",None,(),
                                               ("fixture failure",),None)):
            report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,
                           parallel=1,minutes=2,
                           runtime_factory=lambda provider:(selected.append(provider) or
                                                          LocalPythonRuntime()))

        self.assertEqual(report["check_status"],"NOT_RUN")
        self.assertEqual(report["review_evidence"],[])
        self.assertEqual(selected,[worker["provider"] for worker in state["workers"]])
        self.assertEqual(report["release_status"],"NOT_APPROVED")

    def test_cancelled_review_persists_attempt_without_candidate_identity(self):
        from scripts.development_runner import run_checks
        from scripts.review_evidence import validate_review_attempt
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        completed_checks=[0]
        def checks_then_cancel(*args,**kwargs):
            result=run_checks(*args,**kwargs)
            completed_checks[0]+=1
            if completed_checks[0]==len(state["workers"]):
                kwargs["stop_event"].set()
            return result
        with patch("scripts.development_runner.run_checks",side_effect=checks_then_cancel):
            report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,
                           parallel=1,minutes=2,runtime_factory=lambda provider:LocalPythonRuntime())

        self.assertEqual(report["check_status"],"CHECKS_VERIFIED_AWAITING_REVIEW")
        self.assertEqual(report["review_status"],"REVIEW_INCOMPLETE")
        self.assertTrue(report["review_evidence"])
        _,metadata=load(self.root,task["task_id"])
        for evidence in report["review_evidence"]:
            self.assertEqual(evidence["status"],"CANCELLED")
            self.assertIsNone(evidence["manifest_path"])
            attempt_path=metadata/Path(evidence["attempt_path"])
            attempt=validate_review_attempt(json.loads(attempt_path.read_text(encoding="utf-8")))
            self.assertEqual(attempt["status"],"CANCELLED")
            self.assertIsNone(attempt["identity"])

    def test_offline_provider_fixture_cannot_be_counted_as_review_evidence(self):
        task=task_with_checks()
        state=initialize(task,POLICY,self.root,apply=True)
        class FixtureGeminiRuntime(FakeRuntime):
            pass

        def factory(provider):
            return FixtureGeminiRuntime((RuntimeStatus.SUCCEEDED,)) if provider=="gemini" else LocalPythonRuntime()

        report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,
                       parallel=1,minutes=2,runtime_factory=factory)

        self.assertEqual(report["review_status"],"REVIEW_INCOMPLETE")
        self.assertEqual(report["execution"],"REVIEW_INCOMPLETE")
        self.assertTrue(all(item["status"]=="UNVERIFIED_RUNTIME_ADAPTER"
                            for item in report["review_evidence"]))
        from scripts.review_evidence import validate_review_manifest
        _,metadata=load(self.root,task["task_id"])
        for evidence in report["review_evidence"]:
            manifest=json.loads((metadata/evidence["manifest_path"]).read_text(encoding="utf-8"))
            self.assertTrue(manifest["runtime_adapter_type"].endswith(".FixtureGeminiRuntime"))
            self.assertEqual(validate_review_manifest(manifest,metadata)["status"],"FAILED")
            self.assertIsNone(manifest["review_report"])
        gate_result=gate(self.root,task["task_id"])
        self.assertEqual(gate_result["status"],"BLOCKED")
        self.assertFalse(gate_result["evidence_verified"])
        self.assertEqual(report["release_status"],"NOT_APPROVED")


class RuntimeRunnerTests(unittest.TestCase):
    """Offline orchestration contracts using FakeRuntime; never provider E2E."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.meta=self.root/"metadata"
        self.meta.mkdir()
        self.workers=[]
        for index,provider in enumerate(("codex","gemini")):
            folder=self.root/str(index)
            folder.mkdir()
            self.workers.append({"role":"worker_"+str(index),"provider":provider,
                                 "path":str(folder),"branch":"branch_"+str(index)})
        self.state={"status":"WORKTREES_READY_UNREVIEWED","mode":"both","workers":self.workers}
        self.state.update(task_id=TASK["task_id"],task_packet=TASK,
                          task_sha256=canonical_task_sha256(TASK),task_revision="revision-1",
                          base_commit="0"*40)
        _implementers,review_roles,required_evidence=choose_roles(TASK,POLICY)
        self.state.update(review_roles=review_roles,required_evidence=required_evidence)
        self.addCleanup(patch.stopall)
        patch("scripts.development_runner.load",return_value=(self.state,self.meta)).start()
        patch("scripts.development_runner.inspect",return_value={"base_unchanged":True,"source_clean":True}).start()
        patch("scripts.development_runner.git",side_effect=lambda folder,*args: "branch_"+folder.name).start()
        self.mailbox=patch("scripts.development_runner.message").start()

    def execute(self,**kwargs):
        return execute(self.root,TASK["task_id"],TASK,**kwargs)

    def test_preview_and_missing_ack_make_zero_runtime_calls(self):
        def forbidden(provider):
            self.fail("Preview/unacknowledged execution reached a runtime")
        self.assertEqual(self.execute(runtime_factory=forbidden)["execution"],"PREVIEW_ONLY")
        with self.assertRaisesRegex(ValueError,"unmetered"):
            self.execute(launch=True,runtime_factory=forbidden)
        self.assertFalse((self.meta/"dev-logs").exists())
        self.mailbox.assert_not_called()

    def test_persisted_provider_dispatch_for_codex_gemini_and_both(self):
        for providers in (("codex",),("gemini",),("codex","gemini")):
            selected=[]
            runtimes=[]
            self.state["workers"]=[dict(self.workers[i],provider=provider)
                                    for i,provider in enumerate(providers)]
            self.state["mode"]="both"  # persisted worker.provider is authoritative
            def factory(provider):
                selected.append(provider)
                runtime=FakeRuntime((RuntimeStatus.SUCCEEDED,))
                runtimes.append(runtime)
                return runtime
            report=self.execute(launch=True,cost_ack=True,runtime_factory=factory)
            self.assertEqual(selected,list(providers))
            self.assertEqual(report["execution"],"NOT_RUN")
            self.assertEqual(report["process_execution"],"PROCESSES_FINISHED_UNREVIEWED")
            self.assertEqual(report["check_status"],"NOT_RUN")
            for runtime in runtimes:
                request=next(value for method,value in runtime.invocations if method=="launch")
                self.assertEqual(request.task_id,TASK["task_id"])
                self.assertTrue(request.writable)
                self.assertTrue(request.cost_acknowledged)
                self.assertGreater(request.timeout_seconds,0)
                self.assertIn(("cleanup",next(value for method,value in runtime.invocations
                                             if method=="stream_or_collect")),runtime.invocations)
            self.assertEqual(report["release_status"],"NOT_APPROVED")
            self.assertTrue(all(result["provider"]=="fake" for result in report["results"]))

    def test_unavailable_and_unsupported_providers_never_fall_back(self):
        for provider in ("codex","gemini","unknown"):
            selected=[]
            self.state["workers"]=[dict(self.workers[0],provider=provider)]
            def factory(value):
                selected.append(value)
                return FakeRuntime((RuntimeStatus.UNAVAILABLE,))
            report=self.execute(launch=True,cost_ack=True,runtime_factory=factory)
            self.assertEqual(report["results"][0]["status"],"UNAVAILABLE")
            self.assertEqual(report["execution"],"NOT_RUN")
            self.assertEqual(report["process_execution"],"PARTIAL_OR_FAILED")
            self.assertEqual(selected,[] if provider=="unknown" else [provider])

    def test_global_process_failure_reports_checks_not_run_without_launching_them(self):
        task=task_with_checks()
        self.state.update(task_packet=task,task_sha256=canonical_task_sha256(task))
        runtimes={"codex":FakeRuntime((RuntimeStatus.FAILED,)),
                  "gemini":FakeRuntime((RuntimeStatus.SUCCEEDED,))}
        with patch("scripts.development_runner.run_checks") as run_checks:
            report=execute(self.root,task["task_id"],task,launch=True,cost_ack=True,parallel=2,
                           runtime_factory=lambda provider: runtimes[provider])
        run_checks.assert_not_called()
        self.assertEqual(report["execution"],"NOT_RUN")
        self.assertEqual(report["process_execution"],"PARTIAL_OR_FAILED")
        self.assertTrue(all(item["status"]=="NOT_RUN" for item in report["check_evidence"]))

    def test_timeout_calls_runtime_timeout_and_cleanup(self):
        self.state["workers"]=self.workers[:1]
        runtime=FakeRuntime()
        with patch("scripts.development_runner.time.monotonic",side_effect=[0,0,0,61]):
            report=self.execute(launch=True,cost_ack=True,minutes=1,
                                runtime_factory=lambda provider: runtime)
        self.assertEqual(report["results"][0]["status"],"TIMED_OUT")
        methods=[name for name,_ in runtime.invocations]
        self.assertIn("timeout",methods)
        self.assertIn("cleanup",methods)
        self.assertNotIn("cancel",methods)

    def test_stop_or_deadline_during_discovery_prevents_launch(self):
        for reason, expected in (("stop","CANCELLED"),("deadline","TIMED_OUT")):
            with self.subTest(reason=reason):
                entered=threading.Event()
                release=threading.Event()
                stop=threading.Event()
                clock=[0]
                output=[]
                errors=[]
                class BlockedDiscovery(FakeRuntime):
                    def discover_capabilities(inner):
                        entered.set()
                        if not release.wait(5):
                            raise AssertionError("Discovery was not released")
                        return super().discover_capabilities()
                runtime=BlockedDiscovery((RuntimeStatus.SUCCEEDED,))
                def worker():
                    try:
                        output.append(run_worker(self.workers[0],TASK,self.meta,60,stop,
                                                 lambda provider: runtime,True))
                    except BaseException as exc:
                        errors.append(exc)
                thread=threading.Thread(target=worker,daemon=True)
                with patch("scripts.development_runner.time.monotonic",side_effect=lambda: clock[0]):
                    thread.start()
                    try:
                        self.assertTrue(entered.wait(2),"Worker did not discover capabilities before launch")
                        if reason=="stop":
                            stop.set()
                        else:
                            clock[0]=61
                    finally:
                        release.set()
                        thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors,[])
                self.assertEqual(output[0]["status"],expected)
                self.assertNotIn("launch",[method for method,_ in runtime.invocations])

    def test_stop_during_guarded_spawn_is_recorded_then_worker_cancels_handle(self):
        from scripts import provider_runtimes
        self.state["workers"]=self.workers[:1]
        started=threading.Event()
        release=threading.Event()
        stopping=threading.Event()
        stopped=threading.Event()
        controls=[]
        results=[]
        errors=[]
        process=Mock(pid=123,returncode=-9)
        process.poll.return_value=None
        process.wait.return_value=-9
        containment=Mock(creationflags=0,requires_unreaped_root=False)
        containment.root_exited.side_effect=lambda value: value.poll() is not None
        containment.wait_for_root.side_effect=lambda value,timeout: value.wait(timeout=timeout)
        class ControlledRuntime(GeminiRuntime):
            def discover_capabilities(inner):
                inner._command=("offline-double",)
                return RuntimeCapabilities("offline-double",True,None,(),None,
                                           RuntimeCapabilityStatus.UNKNOWN)
            def launch(inner,request):
                controls.append(getattr(request,"launch_control",None))
                return super().launch(request)
        def spawn(*args,**kwargs):
            started.set()
            if not release.wait(5):
                raise AssertionError("Spawn barrier not released")
            return process
        def execute_worker():
            try:
                results.append(self.execute(launch=True,cost_ack=True,
                    runtime_factory=lambda provider: ControlledRuntime()))
            except BaseException as exc:
                errors.append(exc)
        def record_stop():
            stopping.set()
            try:
                controls[0].set()
            except BaseException as exc:
                errors.append(exc)
            finally:
                stopped.set()
        with patch.object(provider_runtimes.subprocess,"Popen",side_effect=spawn), \
                patch.object(provider_runtimes,"_terminate_tree",side_effect=lambda value: value.kill()), \
                patch.object(provider_runtimes,"_new_containment",return_value=containment):
            worker=threading.Thread(target=execute_worker,daemon=True)
            stopper=threading.Thread(target=record_stop,daemon=True)
            worker.start()
            try:
                self.assertTrue(started.wait(5))
                self.assertIsNotNone(controls[0],"Runner did not pass shared launch control")
                stopper.start()
                self.assertTrue(stopping.wait(5))
                self.assertFalse(stopped.wait(.05),"Stop was recorded inside in-progress guarded Popen")
            finally:
                release.set()
                if not controls or controls[0] is None:
                    process.poll.return_value=-9
                worker.join(5)
                if stopper.ident is not None:
                    stopper.join(5)
            self.assertFalse(worker.is_alive())
            self.assertFalse(stopper.is_alive())
        self.assertEqual(errors,[])
        self.assertTrue(stopped.is_set())
        self.assertEqual(results[0]["results"][0]["status"],"CANCELLED")
        process.kill.assert_called_once()

    def test_peer_failure_cancels_running_runtime_through_contract(self):
        launched=threading.Event()
        running=FakeRuntime()
        failing=FakeRuntime((RuntimeStatus.FAILED,))
        original_launch=running.launch
        def launch(request):
            handle=original_launch(request)
            launched.set()
            return handle
        running.launch=launch
        def factory(provider):
            if provider=="codex":
                self.assertTrue(launched.wait(5))
                return failing
            return running
        report=self.execute(launch=True,cost_ack=True,parallel=2,runtime_factory=factory)
        self.assertEqual({result["status"] for result in report["results"]},{"FAILED","CANCELLED"})
        self.assertIn("cancel",[name for name,_ in running.invocations])
        self.assertIn("cleanup",[name for name,_ in running.invocations])

    def test_runtime_observations_preserved_and_mailbox_has_no_acceptance_authority(self):
        self.state["workers"]=self.workers[:1]
        class ObservedRuntime(FakeRuntime):
            def stream_or_collect(inner,handle):
                return replace(super().stream_or_collect(handle),provider="local-double",
                    provider_session_id="parent-session",stdout_path=self.root/"observed-out",
                    stderr_path=self.root/"observed-err",stdout_sha256="real-out-hash",
                    stderr_sha256="real-err-hash",observed_child_agent_ids=("child-actual",),
                    started_at_utc="start",finished_at_utc="finish")
        report=self.execute(launch=True,cost_ack=True,
                            runtime_factory=lambda provider: ObservedRuntime((RuntimeStatus.SUCCEEDED,)))
        result=report["results"][0]
        self.assertEqual(result["status"],"SUCCEEDED")
        self.assertEqual(result["provider"],"local-double")
        self.assertEqual(result["provider_session_id"],"parent-session")
        self.assertEqual(result["observed_child_agent_ids"],("child-actual",))
        self.assertEqual(result["stdout_path"],str(self.root/"observed-out"))
        self.assertEqual(result["stderr_path"],str(self.root/"observed-err"))
        self.assertEqual(result["stdout_sha256"],"real-out-hash")
        self.assertEqual(result["stderr_sha256"],"real-err-hash")
        self.assertEqual(result["started_at_utc"],"start")
        self.assertEqual(result["finished_at_utc"],"finish")
        self.assertEqual(result["exit_code"],0)
        for call in self.mailbox.call_args_list:
            self.assertEqual(call.args[3],"WORKER_RESULT")
            self.assertNotIn("REVIEW_ACCEPTED",call.args)
            self.assertEqual(call.args[5],"")  # runtime log is outside task metadata
        self.assertEqual(report["release_status"],"NOT_APPROVED")

    def test_repeated_execution_mailbox_artifacts_identify_each_actual_log(self):
        self.state["workers"]=self.workers[:1]
        class LoggedRuntime(FakeRuntime):
            def launch(inner,request):
                request.stdout_path.write_text(request.run_id,encoding="utf-8")
                request.stderr_path.write_text("local fixture",encoding="utf-8")
                return super().launch(request)
        records=[]
        for _ in range(2):
            report=self.execute(launch=True,cost_ack=True,
                runtime_factory=lambda provider: LoggedRuntime((RuntimeStatus.SUCCEEDED,)))
            observed=report["results"][0]
            handoff=self.mailbox.call_args
            self.assertEqual(handoff.args[3],"WORKER_RESULT")
            artifact=handoff.args[5]
            self.assertFalse(Path(artifact).is_absolute())
            self.assertEqual((self.meta/artifact).resolve(),Path(observed["stdout_path"]).resolve())
            self.assertEqual((self.meta/artifact).read_text(),observed["run_id"])
            records.append(artifact)
        self.assertNotEqual(records[0],records[1])

    def test_unavailable_prelaunch_worker_has_no_nonexistent_mailbox_artifact(self):
        self.state["workers"]=self.workers[:1]
        class UnavailableRuntime(FakeRuntime):
            def discover_capabilities(inner):
                return replace(super().discover_capabilities(),available=False)
        runtime=UnavailableRuntime()
        report=self.execute(launch=True,cost_ack=True,runtime_factory=lambda provider: runtime)
        self.assertEqual(report["results"][0]["status"],"UNAVAILABLE")
        self.assertNotIn("launch",[name for name,_ in runtime.invocations])
        self.assertFalse(Path(report["results"][0]["stdout_path"]).exists())
        self.assertEqual(self.mailbox.call_args.args[3],"WORKER_RESULT")
        self.assertEqual(self.mailbox.call_args.args[5],"")
