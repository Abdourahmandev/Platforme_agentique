"""Real tool boundaries and isolated runtime, no model or Telegram calls."""
import json
import requests
from common import BASE, CONTROL, GATEWAY, STATE, docker, node, private_state, remote_write

FIXTURE = """import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';import os from 'node:os';
test('training runtime is isolated and bounded',()=>{
 assert.equal(process.getuid(),1000);
 assert.equal(fs.existsSync('/var/run/docker.sock'),false);
 assert.equal(fs.existsSync('/home/node/.openclaw'),false);
 assert.equal(Object.keys(process.env).some(k=>/API_KEY|TOKEN|PASSWORD/.test(k)),false);
 assert.equal(Object.values(os.networkInterfaces()).flat().every(n=>n.internal),true);
 assert.equal(fs.readFileSync('/sys/fs/cgroup/memory.max','utf8').trim(),'1073741824');
 assert.equal(fs.readFileSync('/sys/fs/cgroup/pids.max','utf8').trim(),'128');
 assert.throws(()=>fs.writeFileSync('/training-root-write','forbidden'));
});
"""


def main():
    headers={'Authorization':'Bearer '+private_state()['gateway_token']}
    checks={}
    def invoke(agent,op,session=None,extra=None):
        r=requests.post('http://127.0.0.1:18789/tools/invoke',headers=headers,json={
            'agentId':agent,'sessionKey':session or 'agent:'+agent+':runtime-preflight',
            'tool':'training_run','args':{'action':'start','operation':op} if extra is None else extra},timeout=45)
        return r.status_code,r.json()
    for agent in ['asia','recherche','developpement','formation-asia','formation-recherche']:
        code,value=invoke(agent,'build')
        checks[agent+'_executor_denied']=code==404 or (agent=='formation-asia' and not value.get('result',{}).get('details',{}).get('jobId') and ('reservee au specialiste' in json.dumps(value) or 'Unauthorized agent' in json.dumps(value)))
    target=BASE+'/workspaces/formation-developpement/repo/test/training-environment.test.mjs'
    remote_write(target,FIXTURE)
    try:
        for op in ['node_tests','python_tests','build']:
            code,result=invoke('formation-developpement',op)
            details=result.get('result',{}).get('details',{})
            (STATE/('preflight-'+op+'.json')).write_text(json.dumps(details))
            checks[op]=code==200 and details.get('status')=='passed' and details.get('exitCode')==0
            if op=='node_tests':
                checks['container_isolation']=checks[op] and 'training runtime is isolated and bounded' in details.get('output','')
            if not checks[op]:raise RuntimeError('Preflight '+op+' failed')
    finally:
        node('require("fs").unlinkSync(JSON.parse(require("fs").readFileSync(0)));',target)
    (STATE/'runtime-preflight.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks))
    if not all(checks.values()):raise RuntimeError('Runtime boundary failed')


if __name__=='__main__':main()
