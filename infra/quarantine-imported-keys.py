"""Disable copied Windows virtual keys in staging, retaining only staged agents.

Historical spending and rows are preserved. No request modifies Windows LiteLLM.
The cloned database is not an additional production budget or authentication realm.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import requests

RUNTIME=Path(os.environ['LOCALAPPDATA'])/'AsiaDocker'
DOCKER=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'


def main():
    state=json.loads((RUNTIME/'runtime-private.json').read_text())
    if state.get('phase')!='staging': raise RuntimeError('Staging only')
    protected={hashlib.sha256(k.encode()).hexdigest() for k in [state['master_key'],*state.get('agent_keys',{}).values()]}
    result=subprocess.run([DOCKER,'exec','asia-platform-staging-postgres-1','psql',
        '-U','postgres','-d','litellm','-Atc','SELECT token FROM "LiteLLM_VerificationToken" WHERE blocked IS NOT TRUE'],
        capture_output=True,timeout=20)
    if result.returncode: raise RuntimeError('Cannot inventory imported keys')
    count=0
    for token in result.stdout.decode().splitlines():
        if token in protected: continue
        r=requests.post('http://127.0.0.1:14000/key/block',
            headers={'Authorization':'Bearer '+state['master_key']},json={'key':token},timeout=20)
        if not r.ok: raise RuntimeError('Cannot quarantine an imported key')
        count+=1
    legacy=(Path(os.environ['LOCALAPPDATA'])/'AsiaLiteLLM/agent.key').read_text().strip()
    r=requests.get('http://127.0.0.1:14000/v1/models',headers={'Authorization':'Bearer '+legacy},timeout=15)
    denied=r.status_code in (401,403)
    r=requests.get('http://127.0.0.1:4000/v1/models',headers={'Authorization':'Bearer '+legacy},timeout=15)
    production_ok=r.ok
    result={'newly_blocked_keys':count,'legacy_key_denied_in_staging':denied,'legacy_key_works_in_production':production_ok}
    (RUNTIME/'key-quarantine-result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    if not denied or not production_ok: raise RuntimeError('Key isolation validation failed')


if __name__=='__main__': main()
