import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('souleiman_connectors', ROOT / 'infra/configure-souleiman-connectors.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConnectorTests(unittest.TestCase):
    def config(self):
        return {'agents': {'entries': {
            'developpement': {'tools': {'allow': ['read', 'asia_opencode_task'],
                                      'deny': ['exec', 'sessions_send', 'context7__*']}},
            'asia': {'tools': {'allow': ['tavily__*']}},
            'recherche': {'tools': {'allow': ['web_fetch']}},
        }}, 'tools': {'allow': ['read', 'asia_opencode_task']},
            'mcp': {'servers': {'tavily': {'url': 'https://example.com'}}},
            'channels': {'telegram': {'enabled': True}}}

    def test_patch_preserves_other_agents_and_windows_permissions(self):
        current = self.config(); before = json.dumps(current, sort_keys=True)
        change = module.patch_for(current)
        self.assertEqual(json.dumps(current, sort_keys=True), before)
        self.assertEqual(list(change['agents']['entries']), ['developpement'])
        self.assertNotIn('channels', change)
        self.assertNotIn('approvals', change)
        policy = change['agents']['entries']['developpement']['tools']
        self.assertIn('asia_opencode_task', policy['allow'])
        self.assertEqual(policy['deny'], ['exec', 'sessions_send'])
        self.assertNotIn('tavily', change['mcp']['servers'])

    def test_only_selected_github_operations_are_exposed(self):
        change = module.patch_for(self.config())
        tools = change['mcp']['servers']['github']['toolFilter']['include']
        for name in ['get_file_contents', 'actions_list', 'create_pull_request', 'issue_write']:
            self.assertIn(name, tools)
        for name in ['merge_pull_request', 'delete_file', 'push_files', 'create_repository',
                     'actions_run_trigger', 'add_issue_comment', 'pull_request_review_write']:
            self.assertNotIn(name, tools)
        self.assertNotIn('*', tools)
        self.assertEqual(change['mcp']['servers']['github']['headers']['Authorization'],
                         'Bearer ${SOULEIMAN_GITHUB_TOKEN}')

    def test_missing_agent_is_rejected(self):
        current = self.config(); del current['agents']['entries']['developpement']
        with self.assertRaises(ValueError): module.patch_for(current)

    def test_rollback_removes_new_servers_preserves_unrelated_config(self):
        before = self.config(); target = module.patch_for(before)
        # Simulate the native recursive config merge.
        def merge(a, b):
            result = json.loads(json.dumps(a))
            for k, v in b.items():
                result[k] = merge(result.get(k, {}), v) if isinstance(v, dict) else v
            return result
        current = merge(before, target)
        current['channels']['telegram']['newOption'] = 'keep'
        current['mcp']['servers']['another'] = {'url': 'https://example.org'}
        restore = module.restore_patch(current, before, target)
        self.assertNotIn('channels', restore)
        self.assertEqual(restore['mcp']['servers'], {'context7': None, 'github': None})
        self.assertEqual(restore['tools']['allow'], before['tools']['allow'])

    def test_rollback_refuses_changed_permission_list(self):
        before = self.config(); target = module.patch_for(before)
        current = json.loads(json.dumps(before))
        current['tools']['allow'].append('new_permission')
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            module.restore_patch(current, before, target)

    def test_rollback_accepts_partial_deployment(self):
        before = self.config(); target = module.patch_for(before)
        restore = module.restore_patch(before, before, target)
        self.assertEqual(restore['mcp']['servers'], {'context7': None, 'github': None})

    def test_startup_migration_preserves_private_device_notes_on_apply_and_rollback(self):
        before = '# Agent\n'
        actual = before + '\n## Tools\n\n### Local notes (migrated from TOOLS.md)\n\nPrivate device note\n'
        journal = {'instructions_before': before, 'instructions_target': before + module.SECTION + 'Connectors\n'}
        with patch.object(module, 'save'):
            module.reconcile_startup_notes(journal, actual)
        self.assertEqual(journal['instructions_before'], actual)
        self.assertIn('Private device note', journal['instructions_target'])
        self.assertEqual(journal['instructions_target'].count(module.SECTION), 1)

    def test_unrecognized_instruction_edit_is_not_rebased(self):
        journal = {'instructions_before': '# Agent\n', 'instructions_target': '# Agent\n' + module.SECTION + 'Connectors\n'}
        with patch.object(module, 'save') as save:
            module.reconcile_startup_notes(journal, '# Changed by owner\n')
        save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
