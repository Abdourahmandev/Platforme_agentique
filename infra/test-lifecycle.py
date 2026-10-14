"""Stop/recreate only the idle staging stack; prove Windows rollback and persistence.

Refuses any enabled Telegram consumer. No volumes are removed and no production
service is stopped. Run while no other staging tests or configuration writes run.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['LOCALAPPDATA'])/'AsiaDocker'
DOCKER = (r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker')
COMPOSE = [DOCKER, 'compose', '-f', str(ROOT/'infra/compose.yaml'), '--profile', 'audio']
ENV = dict(os.environ, ASIA_RUNTIME_DIR=RUNTIME.as_posix())


def compose(*args):
    p = subprocess.run(COMPOSE+list(args), env=ENV, capture_output=True, timeout=660)
    if p.returncode:
        (RUNTIME/'lifecycle-error.log').write_bytes(p.stdout+p.stderr)
        raise RuntimeError('Lifecycle command failed; diagnostic retained in private runtime')
    return p.stdout


def main():
    state = json.loads((RUNTIME/'runtime-private.json').read_text())
    if state.get('phase') != 'staging':
        raise RuntimeError('This disruption test is restricted to staging')
    raw = compose('exec','-T','openclaw','node','-e',
        'process.stdout.write(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"))')
    config = json.loads(raw)
    if config.get('channels',{}).get('telegram',{}).get('enabled'):
        raise RuntimeError('Stop: Telegram is enabled; schedule a separate maintenance window')
    checks = {}
    def check(name, passed):
        checks[name] = {'passed':bool(passed)}
        print(json.dumps({name:checks[name]}),flush=True)
        if not passed: raise RuntimeError(name+' failed')
    def snapshot():
        # Hash only workspace documents, not databases changing during startup.
        documents = compose('exec','-T','openclaw','node','-e',
            'const fs=require("fs"),p="/home/node/.openclaw/workspaces",o={};'
            'for(const a of ["asia","developpement","recherche"])for(const n of fs.readdirSync(p+"/"+a))'
            'if(fs.statSync(p+"/"+a+"/"+n).isFile())o[a+"/"+n]=require("crypto").createHash("sha256").update(fs.readFileSync(p+"/"+a+"/"+n)).digest("hex");'
            'process.stdout.write(JSON.stringify(o))')
        accounting = {}
        for agent,key in state['agent_keys'].items():
            r = requests.get('http://127.0.0.1:14000/key/info',headers={'Authorization':'Bearer '+state['master_key']},params={'key':key},timeout=30)
            if not r.ok: raise RuntimeError('Cannot read persisted accounting')
            info = r.json()['info']
            accounting[agent] = {k:info.get(k) for k in ('team_id','max_budget','spend')}
        return {'documents':json.loads(documents),'accounting':accounting}
    def wait_database():
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:
                r=requests.get('http://127.0.0.1:14000/health/readiness',headers={'Authorization':'Bearer '+state['master_key']},timeout=5)
                if r.ok: return True
            except requests.RequestException: pass
            time.sleep(2)
        return False
    stopped=False
    try:
        before=snapshot()
        p=subprocess.run(['node',str(ROOT/'infra/test-gateway.mjs')],capture_output=True,timeout=90)
        check('baseline_gateway',p.returncode==0)
        sessions_before=json.loads((RUNTIME/'gateway-test-result.json').read_text())['sessions_list']['count']
        check('baseline_sessions_exist',sessions_before>0)
        check('workspace_documents_exist',len(before['documents'])>=6)
        compose('restart','postgres')
        check('database_reconnect',wait_database())
        check('database_persistence',snapshot()['accounting']==before['accounting'])
        compose('stop')
        stopped=True
        r=requests.get('http://127.0.0.1:3210/api/bootstrap',timeout=15)
        check('windows_rollback_available',r.ok and r.json().get('healthy') is True)
        r=requests.get('http://127.0.0.1:4000/health/liveliness',timeout=10)
        check('windows_litellm_available',r.ok)
        compose('up','-d','--force-recreate','--wait','--wait-timeout','300',
                'postgres','litellm','openclaw','speaches')
        stopped=False
        after=snapshot()
        check('workspace_persistence',after['documents']==before['documents'])
        check('agent_accounting_persistence',after['accounting']==before['accounting'])
        # Paired device + persistent histories are checked by the real WS client.
        p=subprocess.run(['node',str(ROOT/'infra/test-gateway.mjs')],capture_output=True,timeout=90)
        check('paired_device_and_sessions_survive',p.returncode==0)
        sessions_after=json.loads((RUNTIME/'gateway-test-result.json').read_text())['sessions_list']['count']
        check('session_count_preserved',sessions_after==sessions_before)
    except Exception as exc:
        checks['suite_completed']={'passed':False,'error_type':type(exc).__name__}
        print('Lifecycle validation failed; inspect the private result.',flush=True)
    finally:
        # Recover the candidate after a failed assertion, without touching Windows.
        if stopped:
            try: compose('up','-d','--wait','--wait-timeout','300','postgres','litellm','openclaw','speaches')
            except Exception: checks['candidate_recovery']={'passed':False}
        result={'checks':checks,'passed':all(c['passed'] for c in checks.values())}
        (RUNTIME/'lifecycle-test-result.json').write_text(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    sys.exit(main())
