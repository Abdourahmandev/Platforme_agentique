import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asia_handoff', ROOT / 'infra/activate-asia.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AsiaHandoffTests(unittest.TestCase):
    def test_retry_of_partial_rollback_preserves_new_windows_expenditure(self):
        with tempfile.TemporaryDirectory(prefix='asia-rollback-test-') as temp:
            runtime = Path(temp)
            journal = runtime / 'journal.json'
            journal.write_text(json.dumps({'status': 'applying', 'legacy': {'spend': 1, 'max_budget': 20}, 'opencode_base': 'http://127.0.0.1:4000/v1'}))
            services = Mock(legacy_key='synthetic-key', private={})
            services.team.return_value = {'spend': 3}
            services.key.return_value = {'spend': 7}  # Windows resumed during an earlier rollback attempt.
            with patch.object(module, 'JOURNAL', journal), patch.object(module, 'RUNTIME', runtime), patch.object(module, 'docker'), patch.object(module.subprocess, 'run', return_value=Mock(returncode=0)):
                module.rollback(services)
            update = next(call for call in services.api.call_args_list if call.args[:2] == ('old', '/key/update'))
            self.assertEqual(update.args[2]['spend'], 7)
            self.assertEqual(json.loads(journal.read_text())['status'], 'rolled-back')

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
        self.assertEqual(asia['execApprovals'], {'enabled': True, 'approvers': ['42'], 'target': 'dm', 'agentFilter': ['asia']})
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
