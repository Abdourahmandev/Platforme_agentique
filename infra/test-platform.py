"""Non-destructive live checks. --inference authorizes small paid test calls.

Only synthetic sessions are used; no Telegram messages are sent. A short-lived
budget fixture is deleted even when a check fails. Results contain no credentials.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid
import requests

RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'AsiaDocker'
BASE = 'http://127.0.0.1:14000'
GATEWAY = 'http://127.0.0.1:18789'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inference', action='store_true')
    args = parser.parse_args()
    private = json.loads((RUNTIME / 'runtime-private.json').read_text())
    if private.get('phase') != 'staging':
        raise SystemExit('These fixtures are restricted to staging.')
    admin = {'Authorization': 'Bearer ' + private['master_key']}
    checks = {}
    def check(name, passed, **details):
        checks[name] = {'passed': bool(passed), **details}
        print(json.dumps({name: checks[name]}), flush=True)
    def admin_post(path, data):
        r = requests.post(BASE + path, headers=admin, json=data, timeout=30)
        if not r.ok:
            raise RuntimeError(f'Administrative fixture {path}: HTTP {r.status_code}')
        return r.json()
    def spend(key):
        r = requests.get(BASE + '/key/info', headers=admin, params={'key': key}, timeout=15)
        if not r.ok:
            raise RuntimeError('Cannot read key accounting')
        return float(r.json()['info'].get('spend') or 0)
    try:
        r = requests.get(BASE + '/health/readiness', headers=admin, timeout=20)
        check('litellm_ready', r.status_code == 200, http=r.status_code)
        r = requests.get(BASE + '/v1/models', timeout=10)
        check('litellm_requires_auth', r.status_code in (401,403), http=r.status_code)
        r = requests.get(BASE + '/v1/models', headers={'Authorization':'Bearer invalid'}, timeout=10)
        check('invalid_key_rejected', r.status_code in (401,403), http=r.status_code)
        for agent, key in private['agent_keys'].items():
            headers = {'Authorization': 'Bearer ' + key}
            r = requests.get(BASE + '/v1/models', headers=headers, timeout=15)
            count = len(r.json().get('data', [])) if r.ok else 0
            check(agent + '_catalogue', r.ok and count == 34, count=count)
            r = requests.get(BASE + '/key/list', headers=headers, timeout=10)
            check(agent + '_admin_denied', r.status_code in (401,403), http=r.status_code)
            r = requests.post(BASE + '/v1/chat/completions', headers=headers, json={
                'model':'migration-nonexistent-model','messages':[{'role':'user','content':'test'}],
            }, timeout=10)
            check(agent + '_unknown_model_denied', r.status_code in (400,401,403), http=r.status_code)
        fixture = admin_post('/key/generate', {
            'key_alias':'migration-budget-fixture','models':['asia-rapide'],
            'max_budget':0.001,'spend':1,'duration':'5m',
        })['key']
        try:
            r = requests.post(BASE + '/v1/chat/completions', headers={'Authorization':'Bearer '+fixture},
                              json={'model':'asia-rapide','messages':[{'role':'user','content':'Must be blocked'}]}, timeout=15)
            error_type = r.json().get('error',{}).get('type')
            check('exhausted_key_blocked', r.status_code == 422 and error_type == 'budget_exceeded', http=r.status_code)
        finally:
            admin_post('/key/delete', {'keys':[fixture]})
        r = requests.post(GATEWAY + '/v1/chat/completions', json={'model':'openclaw','messages':[]}, timeout=10)
        check('openclaw_requires_auth', r.status_code in (401,403), http=r.status_code)
        if args.inference:
            for agent,key in private['agent_keys'].items():
                before = spend(key)
                r = requests.post(GATEWAY + '/v1/chat/completions', headers={
                    'Authorization':'Bearer '+private['gateway_token'],
                    'x-openclaw-agent-id':agent,
                }, json={'model':'openclaw','user':'migration-check-'+uuid.uuid4().hex,
                         'messages':[{'role':'user','content':'Test technique : donne uniquement ton identifiant stable, sans autre texte.'}]}, timeout=190)
                content = r.json().get('choices',[{}])[0].get('message',{}).get('content','') if r.ok else ''
                check(agent + '_inference_identity', r.ok and agent in content.lower(), http=r.status_code)
                after = spend(key)
                for _ in range(8):
                    if after > before:
                        break
                    time.sleep(3)
                    after = spend(key)
                check(agent + '_cost_attribution', after > before, cost_delta=round(after-before,8))
    except Exception as exc:
        check('suite_completed', False, error_type=type(exc).__name__)
    finally:
        result = {'checks':checks,'passed': bool(checks) and all(v['passed'] for v in checks.values()),
                  'inference_enabled':args.inference}
        (RUNTIME / 'platform-test-result.json').write_text(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
