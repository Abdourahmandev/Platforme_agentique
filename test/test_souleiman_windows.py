import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('souleiman_windows', ROOT/'infra/configure-souleiman-windows.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WindowsAccessTests(unittest.TestCase):
    def config(self):
        return {'agents': {'entries': {'developpement': {'tools': {
            'allow': ['read', 'asia_ticket'], 'deny': ['exec', *module.TOOLS, 'sessions_send']}}}},
            'channels': {'telegram': {'accounts': {'developpement': {
                'dmPolicy': 'allowlist', 'allowFrom': ['123456789'], 'token': 'synthetic'}}}},
            'plugins': {'entries': {'asia-opencode': {'enabled': True}}},
            'approvals': {'plugin': {'enabled': True, 'mode': 'session', 'agentFilter': ['asia']}},
            'tools': {'allow': ['read', *module.TOOLS]}}

    def test_narrow_patch_preserves_unrelated_permissions_and_owner(self):
        current = self.config(); before = json.dumps(current, sort_keys=True)
        patch = module.patch_for(current)
        self.assertEqual(json.dumps(current, sort_keys=True), before)
        self.assertEqual(list(patch['agents']['entries']), ['developpement'])
        tools = patch['agents']['entries']['developpement']['tools']
        self.assertEqual(tools['deny'], ['exec', 'sessions_send'])
        self.assertIn('asia_ticket', tools['allow'])
        for name in module.TOOLS: self.assertIn(name, tools['allow'])
        account = patch['channels']['telegram']['accounts']['developpement']
        self.assertEqual(list(account), ['execApprovals'])
        self.assertEqual(account['execApprovals'], {'enabled': True, 'approvers': ['123456789'],
                                                 'target': 'dm', 'agentFilter': ['developpement']})
        self.assertEqual(patch['approvals']['plugin']['agentFilter'], ['asia', 'developpement'])

    def test_ambiguous_telegram_owner_fails_before_mutation(self):
        for owners in [[], ['*'], ['123', '456']]:
            current = self.config();current['channels']['telegram']['accounts']['developpement']['allowFrom'] = owners
            with self.assertRaises(ValueError):module.patch_for(current)

    def test_missing_approval_surface_or_bridge_fails_closed(self):
        current = self.config();current['approvals']['plugin']['enabled'] = False
        with self.assertRaises(ValueError):module.patch_for(current)
        current = self.config();current['plugins']['entries']['asia-opencode']['enabled'] = False
        with self.assertRaises(ValueError):module.patch_for(current)

    def test_rollback_refuses_drift_before_touching_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory)/'before.json'
            journal.write_text(json.dumps({'phase': 'deployed', 'before': {'config': 'before'}, 'target': {'config': 'after'}}))
            with patch.object(module, 'JOURNAL', journal), patch.object(module, 'idle'), \
                 patch.object(module, 'read_files', return_value={'config': 'newer change'}), \
                 patch.object(module, 'remote_write') as write, patch.object(module, 'reload_plugin') as reload:
                with self.assertRaisesRegex(RuntimeError, 'drift'):module.rollback()
                write.assert_not_called();reload.assert_not_called()

    def test_rollback_restores_files_without_erasing_task_journals(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory)/'before.json'
            journal.write_text(json.dumps({'phase': 'deployed', 'before': {'config': 'before', 'plugin': 'old'},
                                           'target': {'config': 'after', 'plugin': 'new'}}))
            with patch.object(module, 'JOURNAL', journal), patch.object(module, 'idle'), \
                 patch.object(module, 'read_files', return_value={'config': 'after', 'plugin': 'old'}), \
                 patch.object(module, 'remote_write') as write, patch.object(module, 'reload_plugin') as reload:
                module.rollback()
                self.assertEqual(write.call_count, 2)
                write.assert_any_call('config', 'before');write.assert_any_call('plugin', 'old')
                reload.assert_called_once()
                self.assertEqual(json.loads(journal.read_text())['phase'], 'rolled-back')
