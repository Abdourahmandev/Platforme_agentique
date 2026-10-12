import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('github_delegation', ROOT / 'infra/configure-github-delegation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DelegationTests(unittest.TestCase):
    def config(self):
        return {'agents': {'entries': {
            'asia': {'tools': {'allow': ['read', 'sessions_spawn', 'asia_opencode_task'], 'deny': ['exec']}},
            'developpement': {'tools': {'allow': ['github__*', 'context7__*']}},
            'recherche': {'tools': {'allow': ['read', 'web_fetch']}},
        }}, 'mcp': {'servers': {
            'github': {'toolFilter': {'include': module.GITHUB_READ + ['issue_write']}},
            'context7': {'toolFilter': {'include': module.CONTEXT_READ}},
        }}}

    def test_parent_grants_exact_reads_without_writes_or_other_agent_changes(self):
        current = self.config(); before = deepcopy(current)
        patch = module.patch_for(current)
        self.assertEqual(current, before)
        self.assertEqual(set(patch), {'agents'})
        self.assertEqual(set(patch['agents']['entries']), {'asia'})
        policy = patch['agents']['entries']['asia']['tools']
        self.assertEqual(set(policy), {'allow'})
        added = set(policy['allow']) - set(current['agents']['entries']['asia']['tools']['allow'])
        self.assertEqual(added, set(module.READ_TOOLS))
        self.assertFalse(set(module.WRITE_TOOLS) & added)
        self.assertTrue(all('*' not in name for name in added))
        self.assertIn('asia_opencode_task', policy['allow'])

    def test_missing_connector_is_rejected(self):
        current = self.config(); del current['mcp']['servers']['github']
        with self.assertRaisesRegex(ValueError, 'connectors first'):
            module.patch_for(current)

    def test_explicit_denies_are_not_bypassed(self):
        current = self.config()
        current['agents']['entries']['asia']['tools']['deny'].append('github__*')
        with self.assertRaisesRegex(ValueError, 'explicitly denied'):
            module.patch_for(current)

    def test_existing_write_grant_requires_reconciliation(self):
        current = self.config()
        current['agents']['entries']['asia']['tools']['allow'].append('github__*')
        with self.assertRaisesRegex(ValueError, 'write grant'):
            module.patch_for(current)

    def test_append_keeps_private_notes_and_is_idempotent(self):
        before = '# Agent\n\n## Tools\nPrivate device notes\n'
        source = '# Agent\n' + module.SECTION + 'Connector instructions\n'
        target = module.append_section(before, source)
        self.assertTrue(target.startswith(before))
        self.assertEqual(module.append_section(target, source), target)
        with self.assertRaisesRegex(RuntimeError, 'differ'):
            module.append_section(target, source + 'Concurrent edit\n')

    def journal(self):
        before = self.config()
        return {'config_before': before, 'patch': module.patch_for(before), 'instructions': {
            'asia': {'before': '# Before', 'target': '# After'},
            'developpement': {'before': '# Before dev', 'target': '# After dev'},
        }}

    def test_rollback_preserves_unrelated_changes_and_accepts_partial_apply(self):
        journal = self.journal(); current = deepcopy(journal['config_before'])
        current['agents']['entries']['asia']['tools']['allow'] = journal['patch']['agents']['entries']['asia']['tools']['allow']
        current['channels'] = {'telegram': {'enabled': True}}
        current['agents']['entries']['recherche']['tools']['allow'].append('new_tool')
        restore = module.preflight(journal, current, {'asia': '# After', 'developpement': '# Before dev'})
        self.assertEqual(set(restore), {'agents'})
        self.assertEqual(set(restore['agents']['entries']), {'asia'})
        self.assertEqual(restore['agents']['entries']['asia']['tools']['allow'],
                         journal['config_before']['agents']['entries']['asia']['tools']['allow'])

    def test_rollback_refuses_permission_drift(self):
        journal = self.journal(); current = deepcopy(journal['config_before'])
        current['agents']['entries']['asia']['tools']['allow'].append('new_tool')
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            module.preflight(journal, current, {'asia': '# After', 'developpement': '# After dev'})

    def test_preflight_detects_instruction_drift_before_mutation(self):
        journal = self.journal()
        with self.assertRaisesRegex(RuntimeError, 'Instruction drift'):
            module.preflight(journal, journal['config_before'], {'asia': '# After', 'developpement': '# User edit'})


if __name__ == '__main__':
    unittest.main()
