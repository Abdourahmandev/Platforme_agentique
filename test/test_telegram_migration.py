"""Reusing Asia's identity must not authorize a duplicate Telegram consumer."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('LOCALAPPDATA',tempfile.gettempdir())
spec=importlib.util.spec_from_file_location('configure_telegram',Path(__file__).parents[1]/'infra/configure-telegram.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TelegramMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.local=Path(self.temp.name)
        self.runtime=self.local/'AsiaDocker'
        (self.runtime/'secrets').mkdir(parents=True)
        (self.runtime/'runtime-private.json').write_text(json.dumps({'phase':'staging'}))
        (self.local/'OpenCodeTelegramSetup').mkdir()
        (self.local/'OpenCodeTelegramSetup/bot-credentials.json').write_text(json.dumps({
            'Token':'123456:fixture-only','AllowedUserId':42}))
        (self.runtime/'secrets/asia.token').write_text('123456:fixture-only')
        for context in (patch.object(module,'RUNTIME',self.runtime),
                        patch.dict(os.environ,{'LOCALAPPDATA':str(self.local)})):
            context.start();self.addCleanup(context.stop)

    def test_explicit_reuse_does_not_bypass_duplicate_consumer_guard(self):
        with patch('sys.argv',['configure-telegram.py','--reuse-existing-asia','--activate']), \
             patch.object(module,'run',return_value=b'{"channels":{},"bindings":[]}') as run, \
             patch.object(module,'telegram',return_value={'id':123456}), \
             patch.object(module,'cli') as cli:
            with self.assertRaisesRegex(RuntimeError,'controlled legacy handoff'):
                module.main()
            cli.assert_not_called()
            # Only the read of existing configuration occurred; no token write.
            self.assertEqual(run.call_count,1)

    def test_reuse_dry_run_binds_asia_without_contacting_or_activating_telegram(self):
        with patch('sys.argv',['configure-telegram.py','--reuse-existing-asia']), \
             patch.object(module,'run',return_value=b'{"channels":{},"bindings":[]}'), \
             patch.object(module,'telegram') as telegram, \
             patch.object(module,'cli') as cli:
            module.main()
            telegram.assert_not_called()
            calls=cli.call_args_list
            self.assertTrue(calls)
            self.assertTrue(all('--dry-run' in c.args for c in calls))
            bindings=json.loads(calls[0].args[3])
            self.assertEqual(bindings[0]['match']['accountId'],'asia')
            self.assertEqual(bindings[0]['agentId'],'asia')

    def test_developer_activation_needs_no_other_tokens_or_bindings(self):
        (self.runtime/'secrets/developpement.token').write_text('234567:developer-fixture')
        def telegram(token,method):
            self.assertEqual(token,'234567:developer-fixture')
            return {'id':234567} if method=='getMe' else {'url':''}
        with patch('sys.argv',['configure-telegram.py','--agent','developpement','--activate']), \
             patch.object(module,'run',return_value=b'{"channels":{},"bindings":[]}') as run, \
             patch.object(module,'telegram',side_effect=telegram), \
             patch.object(module,'cli') as cli:
            module.main()
            for call in cli.call_args_list:
                if call.args[:3]==('config','set','bindings'):
                    bindings=json.loads(call.args[3])
                    self.assertEqual([b['agentId'] for b in bindings],['developpement'])
                if call.args[:3]==('config','set','channels.telegram'):
                    channel=json.loads(call.args[3])
                    self.assertEqual(set(channel['accounts']),{'developpement'})
                    self.assertEqual(channel['groupPolicy'],'disabled')
                    self.assertEqual(channel['allowFrom'],['42'])
            written=json.loads(run.call_args_list[-1].args[1])
            self.assertEqual(set(written),{'developpement'})

    def test_active_configuration_is_not_overwritten(self):
        with patch('sys.argv',['configure-telegram.py','--agent','developpement','--activate']), \
             patch.object(module,'run',return_value=b'{"channels":{"telegram":{"enabled":true}},"bindings":[]}'), \
             patch.object(module,'telegram') as telegram, \
             patch.object(module,'cli') as cli:
            with self.assertRaisesRegex(RuntimeError,'already active'):
                module.main()
            telegram.assert_not_called()
            cli.assert_not_called()


if __name__=='__main__': unittest.main()
