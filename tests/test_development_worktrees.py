"""SSEC development worktrees, communication, approvals and dry-run."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.configuration import DEFAULT_CONFIG
from scripts.worktree_coordinator import plan,initialize,inspect,message,gate,load
from scripts.development_runner import execute,command_for

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

    def test_fake_cli_processes_do_not_change_source(self):
        x=initialize(TASK,POLICY,self.root,apply=True)
        def command(provider,prompt,folder):
            return [sys.executable,"-c","from pathlib import Path;Path('solver.py').write_text('x=8\\n')"]
        with patch("scripts.development_runner.shutil.which",return_value=sys.executable), \
             patch("scripts.development_runner.command_for",side_effect=command):
            result=execute(self.root,TASK["task_id"],TASK,launch=True,
                           cost_ack=True,parallel=2,minutes=1)
        self.assertEqual(result["execution"],"PROCESSES_FINISHED_UNREVIEWED")
        self.assertEqual((self.root/"solver.py").read_text(),"x=1\n")
        self.assertEqual(len(result["results"]),len(x["workers"]))
        self.assertFalse(gate(self.root,TASK["task_id"])["automatic_merge"])

    def test_expected_cli_flags(self):
        self.assertIn("workspace-write",command_for("codex","code",self.root))
        self.assertIn("--sandbox",command_for("gemini","code",self.root))
        with self.assertRaises(ValueError):
            command_for("sh","shell",self.root)
