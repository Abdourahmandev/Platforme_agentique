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


if __name__=='__main__': unittest.main()
