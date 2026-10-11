"""Delegation must not widen peer access, inherit private chat, or reset policy."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('LOCALAPPDATA', tempfile.gettempdir())
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('delegation', ROOT / 'infra/configure-delegation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def merge(base, patch):
    result = deepcopy(base)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            result[key] = merge(result.get(key, {}), value)
        else:
            result[key] = deepcopy(value)
    return result


class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'infra/openclaw.example.json').read_text())
        self.config['agents']['entries']['asia']['tools'] = {'allow': ['read', 'asia_opencode_task']}
        self.config['agents']['entries']['recherche']['tools'] = {'allow': ['read', 'web_fetch'], 'deny': ['exec']}
        self.config['tools']['media'] = {'audio': {'enabled': True}}
        self.config['channels']['telegram'] = {'enabled': True, 'accounts': {'asia': {'enabled': True}}}

    def test_only_asia_can_delegate_to_the_two_specialists(self):
        config = merge(self.config, module.patch_for(self.config))
        self.assertFalse(config['tools']['agentToAgent']['enabled'])
        self.assertEqual(config['tools']['sessions']['visibility'], 'tree')
        self.assertFalse(config['tools']['swarm']['enabled'])
        for agent, entry in config['agents']['entries'].items():
            if agent == 'asia':
                self.assertEqual(entry['subagents']['allowAgents'], ['developpement', 'recherche'])
                self.assertIn('sessions_spawn', entry['tools']['allow'])
                self.assertIn('asia_opencode_task', entry['tools']['allow'])
            else:
                self.assertEqual(entry['subagents']['allowAgents'], [])
                self.assertTrue(set(module.COMMUNICATION).issubset(entry['tools']['deny']))
                self.assertFalse(set(module.COMMUNICATION) & set(entry['tools']['allow']))
        self.assertIn('exec', config['agents']['entries']['recherche']['tools']['deny'])
        self.assertEqual(config['agents']['defaults']['subagents']['maxSpawnDepth'], 1)
        self.assertEqual(config['agents']['defaults']['subagents']['maxConcurrent'], 1)

    def test_rollback_restores_policy_without_replacing_channels_or_audio(self):
        original = deepcopy(self.config)
        activated = merge(self.config, module.patch_for(self.config))
        restored = merge(activated, module.rollback_patch(original))
        self.assertEqual(restored, original)
        self.assertEqual(self.config, original)
        self.assertNotIn('channels', module.patch_for(self.config))
        self.assertNotIn('media', module.patch_for(self.config)['tools'])

    def test_explicit_asia_denial_is_not_silently_overridden(self):
        self.config['agents']['entries']['asia']['tools']['deny'] = ['sessions_spawn']
        with self.assertRaisesRegex(ValueError, 'explicit orchestration denial'):
            module.patch_for(self.config)


if __name__ == '__main__':
    unittest.main()
