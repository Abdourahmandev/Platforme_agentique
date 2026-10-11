"""Adding a live bot must preserve the existing identities and fail closed."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('LOCALAPPDATA', tempfile.gettempdir())
spec = importlib.util.spec_from_file_location('telegram_addition', Path(__file__).parents[1] / 'infra/add-telegram-account.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TelegramAdditionTests(unittest.TestCase):
    def setUp(self):
        self.config = {'agents': {'entries': {'asia': {}, 'developpement': {}, 'recherche': {}}},
            'channels': {'telegram': {'enabled': True, 'accounts': {
                'asia': {'enabled': True, 'execApprovals': {'enabled': True}},
                'developpement': {'enabled': True}}}},
            'bindings': [{'type': 'route', 'agentId': a, 'match': {'channel': 'telegram', 'accountId': a}}
                         for a in ('asia', 'developpement')]}

    def test_addition_preserves_accounts_and_routes_with_owner_only_access(self):
        original = deepcopy(self.config)
        patch = module.patch_for(self.config, 'recherche', 42)
        self.assertEqual(self.config, original)
        accounts = patch['channels']['telegram']['accounts']
        self.assertEqual(set(accounts), {'recherche'})
        self.assertEqual(accounts['recherche']['allowFrom'], ['42'])
        self.assertEqual(accounts['recherche']['dmPolicy'], 'allowlist')
        self.assertEqual(accounts['recherche']['groupPolicy'], 'disabled')
        self.assertFalse(accounts['recherche']['configWrites'])
        self.assertEqual(patch['bindings'][:-1], original['bindings'])
        self.assertEqual(patch['bindings'][-1]['agentId'], 'recherche')

    def test_existing_account_or_binding_cannot_be_overwritten(self):
        for mode in ('account', 'binding'):
            with self.subTest(mode=mode):
                config = deepcopy(self.config)
                if mode == 'account':
                    config['channels']['telegram']['accounts']['recherche'] = {'enabled': False}
                else:
                    config['bindings'].append({'agentId': 'recherche', 'match': {'channel': 'telegram', 'accountId': 'previous'}})
                with self.assertRaisesRegex(ValueError, 'Existing'):
                    module.patch_for(config, 'recherche', 42)
        with self.assertRaisesRegex(ValueError, 'handoff'):
            module.patch_for(self.config, 'asia', 42)

    def test_rollback_only_disables_added_bot_preserving_other_routes(self):
        config = deepcopy(self.config)
        config['bindings'] += [
            {'agentId': 'recherche', 'match': {'channel': 'telegram', 'accountId': 'recherche'}},
            {'agentId': 'recherche', 'match': {'channel': 'other', 'accountId': 'recherche'}}]
        rollback = module.disable_patch(config, 'recherche')
        self.assertEqual(rollback['channels']['telegram']['accounts'], {'recherche': {'enabled': False}})
        self.assertEqual(rollback['bindings'], [*self.config['bindings'], config['bindings'][-1]])


if __name__ == '__main__':
    unittest.main()
