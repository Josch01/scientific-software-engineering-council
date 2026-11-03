"""Real process simulation without provider access or network."""
from __future__ import annotations
import copy
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.run_agents import command_for, execute, files_to_copy, main, plan
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

    def test_progress_callback_reports_live_roles_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('a=1')
            events=[]
            c=dict(DEFAULT_CONFIG,provider_mode='both',max_parallel_agents=2)
            command=lambda provider,prompt,cwd: [
                sys.executable,'-c','import time; time.sleep(0.05)'
            ]
            with patch('scripts.run_agents.shutil.which',return_value=sys.executable), \
                 patch('scripts.run_agents.command_for',side_effect=command):
                report=execute(
                    TASK,c,root,execute_clis=True,accept_unmetered_cost=True,
                    progress_callback=events.append,
                )

        self.assertEqual(events[0]['schema_version'],1)
        self.assertTrue(all(item['status']=='NOT_STARTED' for item in events[0]['roles']))
        self.assertTrue(any(
            item['status']=='RUNNING'
            for event in events for item in event['roles']
        ))
        final=events[-1]
        self.assertEqual(final['execution'],report['execution'])
        self.assertEqual(final['release_status'],'NOT_APPROVED')
        self.assertTrue(all(item['status']=='EXIT_ZERO_UNREVIEWED' for item in final['roles']))

    def test_progress_jsonl_cli_flag_emits_complete_versioned_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('a=1')
            task_path=root/'task.json'
            task_path.write_text(json.dumps(TASK),encoding='utf-8')
            args=[str(task_path),'--project',str(root),'--mode','gemini',
                  '--execute','--accept-unmetered-cost','--emit-progress-jsonl']
            output=io.StringIO()
            command=lambda provider,prompt,cwd: [sys.executable,'-c','pass']
            with patch('scripts.run_agents.shutil.which',return_value=sys.executable), \
                 patch('scripts.run_agents.command_for',side_effect=command), \
                 patch('sys.argv',['run_agents.py',*args]), \
                 contextlib.redirect_stdout(output):
                exit_code=main()

        lines=[line for line in output.getvalue().splitlines() if line.startswith('SSEC_PROGRESS ')]
        self.assertEqual(exit_code,0)
        self.assertGreater(len(lines),1)
        events=[json.loads(line.removeprefix('SSEC_PROGRESS ')) for line in lines]
        self.assertTrue(all(event['schema_version']==1 for event in events))
        self.assertEqual(events[-1]['release_status'],'NOT_APPROVED')

    def test_progress_jsonl_is_opt_in_and_default_cli_output_stays_plain_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            task_path=root/'task.json'
            task_path.write_text(json.dumps(TASK),encoding='utf-8')
            output=io.StringIO()
            with patch('sys.argv',['run_agents.py',str(task_path),'--project',str(root)]), \
                 contextlib.redirect_stdout(output):
                exit_code=main()

        self.assertEqual(exit_code,0)
        self.assertNotIn('SSEC_PROGRESS ',output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['execution'],'PREVIEW_ONLY')

    def test_progress_keeps_later_roles_not_started_after_failed_wave(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src.py').write_text('a=1')
            events=[]
            c=dict(DEFAULT_CONFIG,provider_mode='both',max_parallel_agents=2)
            command=lambda provider,prompt,cwd: [sys.executable,'-c','import sys; sys.exit(7)']
            with patch('scripts.run_agents.shutil.which',return_value=sys.executable), \
                 patch('scripts.run_agents.command_for',side_effect=command):
                report=execute(
                    TASK,c,root,execute_clis=True,accept_unmetered_cost=True,
                    progress_callback=events.append,
                )

        final=events[-1]
        self.assertEqual(report['execution'],'PARTIAL_OR_FAILED')
        self.assertTrue(any(item['status']=='NOT_STARTED' for item in final['roles']))
        self.assertEqual(final['release_status'],'NOT_APPROVED')

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
