import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agent_names', ROOT / 'infra/rename-agents.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AgentNamesTests(unittest.TestCase):
    def test_only_four_display_fields_change(self):
        config = {'agents': {'entries': {
            'asia': {'name': 'Asia', 'subagents': {'allowAgents': ['developpement', 'recherche']}},
            'developpement': {'name': 'Developpement', 'workspace': '/workspaces/developpement', 'tools': {'deny': ['exec']}},
            'recherche': {'name': 'Recherche', 'agentDir': '/agents/recherche', 'tools': {'allow': ['web_fetch']}}}},
            'channels': {'telegram': {'accounts': {
                'developpement': {'name': 'developpement', 'tokenFile': '/credentials/developpement.token'},
                'recherche': {'name': 'recherche', 'allowFrom': ['42']}}}},
            'bindings': [{'agentId': 'recherche', 'match': {'accountId': 'recherche'}}],
            'models': {'primary': 'litellm/asia-auto'}}
        original = json.loads(json.dumps(config))
        updated = module.renamed_config(config)
        self.assertEqual(config, original)
        for aid in module.SPECIALISTS:
            self.assertEqual(updated['agents']['entries'][aid]['name'], module.CATALOGUE[aid]['name'])
            updated['agents']['entries'][aid]['name'] = original['agents']['entries'][aid]['name']
            updated['channels']['telegram']['accounts'][aid]['name'] = original['channels']['telegram']['accounts'][aid]['name']
        self.assertEqual(updated, original)

    def test_roles_ids_and_old_aliases_remain_understandable(self):
        text = 'Tu es Developpement, identifiant `developpement`. Recherche lit les sources. La recherche web reste limitee.'
        updated = module.renamed_text(text, identity_note=True)
        self.assertIn('Tu es Souleiman, identifiant `developpement`', updated)
        self.assertIn('Saredo lit les sources', updated)
        self.assertIn('La recherche web reste limitee', updated)
        self.assertIn('nouveau nom de Recherche', updated)
        with self.assertRaises(ValueError):
            module.renamed_text(updated, identity_note=True)

    def test_installation_example_uses_catalogue_without_new_identities(self):
        cfg = json.loads((ROOT / 'infra/openclaw.example.json').read_text())
        self.assertEqual(set(cfg['agents']['entries']), {'asia', 'developpement', 'recherche'})
        for aid, entry in cfg['agents']['entries'].items():
            self.assertEqual(entry['name'], module.CATALOGUE[aid]['name'])
            self.assertTrue(entry['workspace'].endswith('/' + aid))

    def test_rollback_refuses_runtime_drift_before_any_external_write(self):
        filename = module.g.BASE + '/openclaw.json'
        saved = {'files': {filename: 'original'}}
        with patch.object(module, 'remote_text', return_value='changed-later'), \
             patch.object(module.c, 'read', return_value={'files': {filename: 'migration-target'}}), \
             patch.object(module.c, 'Client') as client, \
             patch.object(module.g, 'remote_write') as write:
            with self.assertRaises(AssertionError):
                module.rollback(saved)
            client.assert_not_called()
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
