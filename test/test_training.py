import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'infra/training'))
import runner
spec=importlib.util.spec_from_file_location('training_configure',ROOT/'infra/training/configure.py')
configure=importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


class TrainingTests(unittest.TestCase):
    def test_snapshot_paths_cannot_escape_or_use_windows_streams(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ['../secret','/secret','a/../../b','a\\b','C:/secret','test/x:stream']:
                with self.subTest(name=name),self.assertRaises(ValueError): runner.safe_file(Path(root),name)

    def test_executor_has_no_network_secrets_or_host_control(self):
        with tempfile.TemporaryDirectory() as root:
            req={'agentId':'formation-developpement','jobId':'a'*32,'sessionKey':'agent:formation-developpement:test','operation':'build'}
            args=runner.command(req,Path(root))
            for flag,value in [('--network','none'),('--memory','1g'),('--cpus','1'),('--pids-limit','128'),('--user','1000:1000')]:
                self.assertEqual(args[args.index(flag)+1],value)
            self.assertIn('--read-only',args)
            self.assertNotIn('docker.sock',' '.join(args))
            self.assertNotIn('--env-file',args)
            for bad in [{'agentId':'asia'},{'operation':'shell'},{'jobId':'../x'},{'sessionKey':'agent:asia:test'}]:
                with self.assertRaises(ValueError): runner.command(dict(req,**bad),Path(root))

    def test_training_patch_preserves_production_and_scopes_tools(self):
        before=json.loads((ROOT/'infra/openclaw.example.json').read_text())
        before['plugins']['allow']=['openai','microsoft']
        original=json.dumps(before,sort_keys=True)
        patch=configure.patch_for(before)
        self.assertEqual(original,json.dumps(before,sort_keys=True))
        self.assertNotIn('channels',patch)
        self.assertNotIn('bindings',patch)
        self.assertEqual(set(patch['agents']['entries']),set(configure.IDS))
        for role,entry in patch['agents']['entries'].items():
            self.assertEqual('training_run' in entry['tools']['allow'],role in ('formation-developpement','formation-asia'))
            self.assertEqual('tavily__tavily_search' in entry['tools']['allow'],role in ('formation-recherche','formation-asia'))
            self.assertIn('exec',entry['tools']['deny'])
            self.assertIn('asia_opencode_task',entry['tools']['deny'])
            self.assertEqual(bool(entry['subagents']['allowAgents']),role=='formation-asia')

    def test_procedure_promotion_restores_exact_previous_instructions(self):
        import promote
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); remote={}
            for role in ['asia','recherche','developpement']:
                d=root/'infra/agents'/role;d.mkdir(parents=True)
                for file,content in [('AGENTS.md','original '+role),('PROCEDURES.md','reviewed '+role)]:
                    (d/file).write_text(content)
                    remote[promote.BASE+'/workspaces/'+role+'/'+file]='live original '+role if file=='AGENTS.md' else None
            original=dict(remote)
            def delete(code,value):remote[value]=None
            with patch.object(promote,'ROOT',root),patch.object(promote,'JOURNAL',root/'journal.json'),patch.object(promote,'read_remote',side_effect=lambda p:remote[p]),patch.object(promote,'remote_write',side_effect=lambda p,v:remote.__setitem__(p,v)),patch.object(promote,'node',side_effect=delete):
                promote.install()
                key=promote.BASE+'/workspaces/asia/AGENTS.md'
                installed=remote[key];remote[key]='later user edit'
                with self.assertRaises(RuntimeError):promote.rollback()
                self.assertEqual(remote[key],'later user edit')
                remote[key]=installed;promote.rollback()
                self.assertEqual(remote,original)
                self.assertEqual((root/'infra/agents/asia/AGENTS.md').read_text(),'original asia')

    def test_backup_without_restore_evidence_stays_unknown(self):
        spec=importlib.util.spec_from_file_location('diagnose',ROOT/'infra/diagnose-platform.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'backup.aes';archive.write_text('fixture')
            report={'archive':str(archive)};now=archive.stat().st_mtime+3600
            self.assertIsNone(module.backup_observation(report,now)['verified'])
            report.update(openclaw_native_verify=True,openclaw_restored=True,postgres_restored=True)
            self.assertEqual(module.backup_observation(report,now),{'verified':True,'ageHours':1.0})
            report['postgres_restored']=False
            self.assertIs(module.backup_observation(report,now)['verified'],False)


if __name__=='__main__': unittest.main()
