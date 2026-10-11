import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asia_handoff', ROOT / 'infra/activate-asia.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AsiaHandoffTests(unittest.TestCase):
    def current(self):
        config = json.loads((ROOT / 'infra/openclaw.example.json').read_text())
        config['channels']['telegram'] = {'enabled': True, 'accounts': {'developpement': {'enabled': True, 'custom': 'preserve'}}}
        config['bindings'] = [{'type': 'route', 'agentId': 'developpement', 'match': {'channel': 'telegram', 'accountId': 'developpement'}}]
        return config

    def test_merge_preserves_developer_and_rejects_second_handoff(self):
        current = self.current()
        before = json.dumps(current, sort_keys=True)
        patch = module.patch_for(current, '42')
        self.assertEqual(json.dumps(current, sort_keys=True), before)
        self.assertEqual(patch['channels']['telegram']['accounts']['developpement'], current['channels']['telegram']['accounts']['developpement'])
        self.assertEqual(patch['bindings'][0], current['bindings'][0])
        asia = patch['channels']['telegram']['accounts']['asia']
        self.assertEqual(asia['allowFrom'], ['42'])
        self.assertEqual(asia['groupPolicy'], 'disabled')
        self.assertNotIn('botToken', asia)
        with self.assertRaisesRegex(ValueError, 'already enabled'):
            module.patch_for(patch, '42')

    def test_conflicting_binding_and_invalid_owner_refused(self):
        current = self.current()
        current['bindings'].append({'agentId': 'asia', 'match': {'accountId': 'wrong'}})
        with self.assertRaises(ValueError): module.patch_for(current, '42')
        with self.assertRaises(ValueError): module.patch_for(self.current(), '*')

    def test_budget_keeps_prior_spend_and_never_creates_second_envelope(self):
        self.assertAlmostEqual(module.budget_cap({'max_budget': 20, 'spend': 1.75}), 18.25)
        self.assertEqual(module.budget_cap({'max_budget': 10, 'spend': 0}), 10)
        for budget in ({'max_budget': 0}, {'max_budget': 30}, {'max_budget': 20, 'spend': 20}, {'max_budget': 20, 'spend': -1}):
            with self.subTest(budget=budget), self.assertRaises(ValueError): module.budget_cap(budget)


if __name__ == '__main__': unittest.main()
