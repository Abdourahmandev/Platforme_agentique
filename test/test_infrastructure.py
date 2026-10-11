"""Deployment boundary checks: fail CI on accidental exposure or shared identity."""
import json
from pathlib import Path
import re
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]


class InfrastructureTests(unittest.TestCase):
    def test_images_pinned_and_no_build_or_host_control(self):
        config=yaml.safe_load((ROOT/'infra/compose.yaml').read_text())
        for name,service in config['services'].items():
            with self.subTest(service=name):
                self.assertRegex(service['image'],r'@sha256:[a-f0-9]{64}$')
                self.assertNotIn('build',service)
                self.assertFalse(service.get('privileged',False))
                self.assertNotEqual(service.get('network_mode'),'host')
                self.assertNotIn('docker.sock',json.dumps(service.get('volumes',[])))
                for port in service.get('ports',[]):
                    self.assertTrue(port.startswith('127.0.0.1:'),'Published port must remain local')
        self.assertNotIn('ports',config['services']['postgres'])
        self.assertTrue(config['networks']['database']['internal'])

    def test_browser_cannot_mount_agent_secrets_or_other_workspaces(self):
        config=yaml.safe_load((ROOT/'infra/compose.yaml').read_text())
        browser=config['services']['playwright']
        self.assertNotIn('ports',browser)
        self.assertNotIn('env_file',browser)
        self.assertTrue(browser['read_only'])
        self.assertEqual(browser['user'],'1000:1000')
        self.assertEqual(len(browser['volumes']),1)
        self.assertEqual(browser['volumes'][0]['volume']['subpath'],'workspaces/asia')
        self.assertTrue(config['networks']['browser_control']['internal'])
        self.assertEqual(set(browser['networks']),{'browser_control','browser_egress'})

    def test_agent_boundary_and_authenticated_gateway(self):
        config=json.loads((ROOT/'infra/openclaw.example.json').read_text())
        agents=config['agents']['entries']
        self.assertEqual(len({a['workspace'] for a in agents.values()}),len(agents))
        self.assertEqual(len({a['agentDir'] for a in agents.values()}),len(agents))
        self.assertEqual(config['gateway']['auth']['mode'],'token')
        self.assertEqual(config['gateway']['auth']['token'],'${OPENCLAW_GATEWAY_TOKEN}')
        self.assertNotIn('*',config['gateway']['controlUi']['allowedOrigins'])
        self.assertTrue(config['tools']['fs']['workspaceOnly'])
        self.assertEqual(config['tools']['sessions']['visibility'],'agent')
        self.assertFalse(config['tools']['agentToAgent']['enabled'])
        self.assertFalse(config['channels']['telegram']['enabled'])
        self.assertEqual(config['bindings'],[])


if __name__=='__main__': unittest.main()
