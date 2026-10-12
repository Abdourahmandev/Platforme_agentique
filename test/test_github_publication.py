import importlib.util
from copy import deepcopy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('github_publication', ROOT / 'infra/configure-github-publication.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicationTests(unittest.TestCase):
    def config(self):
        return {'agents': {'entries': {
            'asia': {'tools': {'allow': ['read', 'asia_opencode_task'] + module.delegation.READ_TOOLS,
                               'deny': ['exec']}},
            'developpement': {'tools': {'allow': ['github__*']}},
            'recherche': {'tools': {'allow': ['read']}},
        }}, 'mcp': {'servers': {'github': {'toolFilter': {'include': ['create_pull_request']}}}},
            'channels': {'telegram': {'enabled': True}}}

    def test_only_adds_exact_pr_creation_to_asia_and_is_idempotent(self):
        current = self.config(); before = deepcopy(current)
        patch = module.patch_for(current)
        self.assertEqual(current, before)
        self.assertEqual(patch, {'agents': {'entries': {'asia': {'tools': {
            'allow': before['agents']['entries']['asia']['tools']['allow'] + [module.TOOL]}}}}})
        current['agents']['entries']['asia']['tools']['allow'] = patch['agents']['entries']['asia']['tools']['allow']
        self.assertEqual(module.patch_for(current), patch)

    def test_does_not_override_explicit_denial(self):
        current = self.config()
        current['agents']['entries']['asia']['tools']['deny'].append('github__*')
        with self.assertRaisesRegex(ValueError, 'explicitly denied'):
            module.patch_for(current)

    def test_requires_existing_connector(self):
        current = self.config(); del current['mcp']
        with self.assertRaisesRegex(ValueError, 'does not expose'):
            module.patch_for(current)

    def test_preserves_private_notes_and_updates_both_agents(self):
        for agent, replacements in module.REPLACEMENTS.items():
            old, new = next(iter(replacements.items()))
            before = '# Agent\n' + old + '\n\nPrivate device notes\n'
            source = '# Source\n' + module.SECTION + 'Publication instructions\n'
            target = module.instructions_for(agent, before, source)
            self.assertIn('Private device notes', target)
            self.assertIn(new, target)
            self.assertNotIn(old, target)
            self.assertEqual(module.instructions_for(agent, target, source), target)

    def test_detects_instruction_drift(self):
        source = '# Source\n' + module.SECTION + 'Instructions\n'
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            module.instructions_for('asia', '# User changed instructions', source)
        new = next(iter(module.REPLACEMENTS['asia'].values()))
        with self.assertRaisesRegex(RuntimeError, 'differ'):
            module.instructions_for('asia', new + module.SECTION + 'Concurrent edit', source)

    def journal(self):
        before = self.config()
        return {'config_before': before, 'patch': module.patch_for(before),
                'instructions': {'asia': {'before': 'Before', 'target': 'After'}}}

    def test_rollback_removes_creation_but_preserves_reads_and_unrelated_changes(self):
        journal = self.journal(); current = deepcopy(journal['config_before'])
        current['agents']['entries']['asia']['tools']['allow'] = journal['patch']['agents']['entries']['asia']['tools']['allow']
        current['channels']['telegram']['new_setting'] = True
        restore = module.delegation.preflight(journal, current, {'asia': 'After'})
        expected = journal['config_before']['agents']['entries']['asia']['tools']['allow']
        self.assertEqual(restore, {'agents': {'entries': {'asia': {'tools': {'allow': expected}}}}})

    def test_rollback_refuses_policy_and_instruction_drift(self):
        journal = self.journal(); current = deepcopy(journal['config_before'])
        current['agents']['entries']['asia']['tools']['allow'].append('new_tool')
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            module.delegation.preflight(journal, current, {'asia': 'After'})
        with self.assertRaisesRegex(RuntimeError, 'Instruction drift'):
            module.delegation.preflight(journal, journal['config_before'], {'asia': 'User edit'})


if __name__ == '__main__':
    unittest.main()
