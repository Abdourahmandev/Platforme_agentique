import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asia_tools', ROOT / 'infra/configure-asia-tools.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AsiaToolsTests(unittest.TestCase):
    def test_explicit_plugin_allowlist_keeps_the_local_audio_adapter(self):
        current = json.loads((ROOT / 'infra/openclaw.example.json').read_text())
        current['tools']['media'] = {'models': [{'provider': 'openai', 'model': 'local-whisper'}]}
        patch = module.patch_for(current)
        self.assertIn('openai', patch['plugins']['allow'])
        self.assertTrue(patch['plugins']['entries']['openai']['enabled'])
        self.assertNotIn('media', patch['tools'])

    def test_new_tools_are_scoped_and_existing_policies_survive(self):
        current = json.loads((ROOT / 'infra/openclaw.example.json').read_text())
        current['agents']['entries']['developpement']['tools'] = {'allow': ['read'], 'deny': ['write']}
        current['agents']['entries']['asia']['tools'] = {'deny': ['exec']}
        before = json.dumps(current, sort_keys=True)
        patch = module.patch_for(current)
        self.assertEqual(json.dumps(current, sort_keys=True), before)
        self.assertNotIn('channels', patch)
        self.assertNotIn('bindings', patch)
        self.assertNotIn('google-workspace', patch['mcp']['servers'])
        for agent, entry in patch['agents']['entries'].items():
            if agent == 'asia':
                self.assertIn('asia-memory__*', entry['tools']['allow'])
                self.assertIn('exec', entry['tools']['deny'])
            else:
                self.assertIn('asia-memory__*', entry['tools']['deny'])
                self.assertIn('tavily__*', entry['tools']['deny'])
        developer = patch['agents']['entries']['developpement']['tools']
        self.assertEqual(developer['allow'], ['read'])
        self.assertIn('write', developer['deny'])
        self.assertFalse(patch['browser']['enabled'])
        self.assertIn('playwright__*', patch['agents']['entries']['asia']['tools']['allow'])
        self.assertIn('--offline', patch['mcp']['servers']['asia-memory']['args'])


if __name__ == '__main__':
    unittest.main()
