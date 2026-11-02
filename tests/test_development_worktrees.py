"""SSEC development worktrees, communication, approvals and dry-run."""
import json
from dataclasses import replace
import hashlib
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from scripts.configuration import DEFAULT_CONFIG
from scripts.worktree_coordinator import plan,initialize,inspect,message,gate,load
from scripts.development_runner import execute,run_worker
from scripts.agent_runtime import FakeRuntime, RuntimeCapabilities, RuntimeCapabilityStatus, RuntimeStatus
from scripts.provider_runtimes import GeminiRuntime

TASK={"task_id":"SSEC-TEST","kind":"build","request":"Implement a scientific solver",
      "domains":["numerical"],"languages":["python"],"interfaces":["cli"],
      "targets":["linux"],"risk":"R1","runtime":{}}
POLICY=dict(DEFAULT_CONFIG,provider_mode="both")

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
        git(self.root,"add",".")
        git(self.root,"commit","-m","initial")

    def test_plan_is_read_only(self):
        x=plan(TASK,POLICY,self.root)
        self.assertEqual(x["status"],"PREVIEW_NOT_STARTED")
        self.assertEqual(len(git(self.root,"worktree","list","--porcelain").split("worktree ")),2)

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

    def test_local_python_child_process_and_log_lifecycle_not_provider_e2e(self):
        x=initialize(TASK,POLICY,self.root,apply=True)
        state, meta=load(self.root,TASK["task_id"])
        state["workers"]=state["workers"][:1]
        (meta/"state.json").write_text(json.dumps(state),encoding="utf-8")

        class LocalPythonRuntime(GeminiRuntime):
            """Actual local Python process/log check, never a provider session."""
            provider="local-python"

            def discover_capabilities(self):
                self._command=(sys.executable,)
                return RuntimeCapabilities("local-python",True,None,(),None,
                                           RuntimeCapabilityStatus.UNKNOWN)

            def build_argv(self,request):
                code=("from pathlib import Path;import json,sys;"
                      "Path('solver.py').write_text('x=8\\n');"
                      "print(json.dumps({'type':'init','session_id':'local-python-session'}));"
                      "print(json.dumps({'type':'result','status':'success','stats':{}}));"
                      "print('local diagnostic',file=sys.stderr)")
                return (sys.executable,"-c",code)

        result=execute(self.root,TASK["task_id"],TASK,launch=True,
                       cost_ack=True,parallel=1,minutes=1,
                       runtime_factory=lambda provider: LocalPythonRuntime())
        self.assertEqual(result["execution"],"PROCESSES_FINISHED_UNREVIEWED")
        self.assertEqual((self.root/"solver.py").read_text(),"x=1\n")
        self.assertEqual((Path(x["workers"][0]["path"])/"solver.py").read_text(),"x=8\n")
        self.assertEqual(len(result["results"]),1)
        observed=result["results"][0]
        self.assertEqual(observed["provider"],"local-python")
        self.assertEqual(observed["status"],"SUCCEEDED")
        self.assertEqual(observed["exit_code"],0)
        self.assertEqual(observed["provider_session_id"],"local-python-session")
        self.assertEqual(observed["observed_child_agent_ids"],())
        for name in ("stdout","stderr"):
            payload=Path(observed[name+"_path"]).read_bytes()
            self.assertEqual(observed[name+"_sha256"],hashlib.sha256(payload).hexdigest())
        self.assertFalse(gate(self.root,TASK["task_id"])["automatic_merge"])


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
            self.assertEqual(report["execution"],"PROCESSES_FINISHED_UNREVIEWED")
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
            self.assertEqual(report["execution"],"PARTIAL_OR_FAILED")
            self.assertEqual(selected,[] if provider=="unknown" else [provider])

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
                patch.object(provider_runtimes,"_new_containment",return_value=Mock(creationflags=0)):
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
