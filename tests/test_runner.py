"""Real process simulation without provider access or network."""
from __future__ import annotations
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.run_agents import command_for, execute, files_to_copy, plan
from scripts.configuration import DEFAULT_CONFIG

ROOT=Path(__file__).resolve().parents[1]
TASK=json.loads((ROOT/'examples/seir_desktop_audit.json').read_text(encoding='utf-8'))

class RunnerTests(unittest.TestCase):
    def test_preview_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp)
            (project/'main.py').write_text('print(1)')
            result=execute(TASK, dict(DEFAULT_CONFIG,provider_mode='both'),project)
            self.assertEqual(result['execution'],'PREVIEW_ONLY')
            self.assertFalse((project/'.ssec').exists())
            self.assertGreater(result['agent_count'],1)

    def test_audit_only(self):
        task=dict(TASK,kind='build')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                execute(task,DEFAULT_CONFIG,Path(tmp))

    def test_safe_commands(self):
        cmd=command_for('codex','audit',Path('/tmp/sample'))
        self.assertEqual(cmd[1:4],['exec','--sandbox','read-only'])
        self.assertIn("--skip-git-repo-check", cmd)
        self.assertEqual(command_for('gemini','audit',Path('/tmp/sample'))[-2:],['-p','audit'])
        with self.assertRaises(ValueError):
            command_for('sh','rm -rf .',Path('/tmp/sample'))

    def test_snapshot_excludes_known_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('a=1')
            (root/'.env').write_text('TOKEN=SECRET')
            (root/'private.key').write_text('SECRET')
            (root/'.git').mkdir()
            (root/'.git/config').write_text('SECRET')
            selected=[str(relative) for _,relative in files_to_copy(root)]
            self.assertEqual(selected,['src.py'])

    def test_needs_cost_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('a=1')
            with self.assertRaisesRegex(ValueError,'unmetered'):
                execute(TASK,DEFAULT_CONFIG,root,execute_clis=True)

    def test_missing_cli_blocks_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('a=1')
            with patch('scripts.run_agents.shutil.which',return_value=None):
                report=execute(TASK,dict(DEFAULT_CONFIG,max_parallel_agents=1),root,
                               execute_clis=True,accept_unmetered_cost=True)
            self.assertEqual(report['execution'],'PARTIAL_OR_FAILED')
            self.assertEqual(len(report['results']),1)
            self.assertEqual(report['results'][0]['status'],'LAUNCH_FAILED')
            self.assertTrue((Path(report['log_dir'])/'run_summary.json').exists())
            self.assertEqual((root/'src.py').read_text(),'a=1')

    def test_fake_cli_executes_all_waves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('important=1')
            c=dict(DEFAULT_CONFIG, provider_mode='both', max_parallel_agents=2)
            def cmd(provider,prompt,cwd):
                return [sys.executable,'-c','import sys; print("fake-agent-ok"); sys.exit(0)']
            with patch('scripts.run_agents.shutil.which',return_value=sys.executable), \
                 patch('scripts.run_agents.command_for',side_effect=cmd):
                report=execute(TASK,c,root,execute_clis=True,accept_unmetered_cost=True)
            self.assertEqual(report['execution'],'PROCESSES_COMPLETED_NOT_AUDITED')
            self.assertEqual(len(report['results']),report['agent_count'])
            self.assertTrue(all(x['status']=='EXIT_ZERO_UNREVIEWED' for x in report['results']))
            self.assertEqual((root/'src.py').read_text(),'important=1')
            self.assertFalse((root/'.codex').exists())

    def test_fake_cli_timeout_and_abort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('a=1')
            # Tight fake deadline: patch monotonic only for deadline calculation is more fragile;
            # instead use a real child and a global event injected into a single run.
            import threading
            from scripts.run_agents import run_one
            config=dict(DEFAULT_CONFIG)
            m,profiles=__import__('scripts.prepare_agents',fromlist=['make_files']).make_files(TASK,'gemini',config)
            agent=m['assignments'][0]
            with patch('scripts.run_agents.shutil.which',return_value=sys.executable), \
                 patch('scripts.run_agents.command_for',return_value=[sys.executable,'-c','import time;time.sleep(3)']):
                import time
                result=run_one(agent,TASK['task_id'],files_to_copy(root),profiles,root,
                               time.monotonic()+0.25,threading.Event())
            self.assertEqual(result['status'],'TIMED_OUT')

if __name__=='__main__': unittest.main()
