"""Prove that a spent TEAM blocks multiple keys whose own budgets remain free.

Only an ephemeral, uniquely named fixture team is modified. Existing teams, keys
and spend values are never reset. Both fixture keys and team are deleted finally.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import requests

ROOT=Path(os.environ['LOCALAPPDATA'])/'AsiaDocker'
state=json.loads((ROOT/'runtime-private.json').read_text())
if state.get('phase')!='staging': raise SystemExit('Staging only')
BASE='http://127.0.0.1:14000'
ADMIN={'Authorization':'Bearer '+state['master_key']}
team='migration-budget-'+uuid.uuid4().hex
keys=[]
checks=[]


def post(path,data):
    r=requests.post(BASE+path,headers=ADMIN,json=data,timeout=20)
    if not r.ok: raise RuntimeError(f'Fixture API {path}: HTTP {r.status_code}')
    return r.json()


try:
    post('/team/new',{'team_id':team,'models':['asia-rapide'],'max_budget':0.001,'budget_duration':'30d'})
    for _ in range(2):
        keys.append(post('/key/generate',{'team_id':team,'models':['asia-rapide'],'max_budget':1,'duration':'5m'})['key'])
    # The public team update schema cannot set spend. Seed a spent balance only
    # in this fresh fixture, then refresh it through the normal update endpoint.
    query='UPDATE "LiteLLM_TeamTable" SET spend=1 WHERE team_id=\''+team+'\';'
    p=subprocess.run([(r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker'),'exec','-i',
        'asia-platform-staging-postgres-1','psql','-U','postgres','-d','litellm','-v','ON_ERROR_STOP=1'],
        input=query.encode(),capture_output=True)
    if p.returncode: raise RuntimeError('Cannot seed team budget fixture')
    post('/team/update',{'team_id':team,'max_budget':0.001})
    for key in keys:
        r=requests.post(BASE+'/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={
            'model':'asia-rapide','messages':[{'role':'user','content':'Budget test: this call must be blocked.'}],'max_tokens':1,
        },timeout=20)
        checks.append({'http':r.status_code,'passed':r.status_code==422 and r.json().get('error',{}).get('type')=='budget_exceeded'})
finally:
    if keys: post('/key/delete',{'keys':keys})
    post('/team/delete',{'team_ids':[team]})
result={'shared_team_budget':checks,'passed':len(checks)==2 and all(c['passed'] for c in checks)}
(ROOT/'team-budget-test-result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
sys.exit(0 if result['passed'] else 1)
