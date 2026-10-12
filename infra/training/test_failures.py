"""Exercise real cancellation/deadline on a disposable hanging test, not a bot."""
import json
import subprocess
import time
import uuid
import requests
from common import BASE, CONTROL, DOCKER, STATE, node, private_state, remote_json, remote_write

FIXTURE=BASE+'/workspaces/formation-developpement/repo/test/training-hang.test.mjs'


def exists(path):
    return json.loads(node('console.log(JSON.stringify(require("fs").existsSync(JSON.parse(require("fs").readFileSync(0)))));',path))


def run_case(cancel):
    job=uuid.uuid4().hex
    session='agent:formation-developpement:failure-preflight-'+job
    remote_write(FIXTURE,"import {test} from 'node:test';test('injected slow command',async()=>{await new Promise(r=>setTimeout(r,600000));});")
    remote_write(CONTROL+'/'+job+'.request.json',json.dumps({'jobId':job,'agentId':'formation-developpement','sessionKey':session,'operation':'node_tests'}))
    try:
        for _ in range(30):
            p=subprocess.run([DOCKER,'inspect','--format','{{.State.Running}}','asia-training-job-'+job],capture_output=True,text=True,timeout=5)
            if p.returncode==0 and p.stdout.strip()=='true':break
            time.sleep(1)
        else:raise RuntimeError('Failure fixture never started')
        # Snapshot is now inside its own disposable directory. Later jobs stay clean.
        node('require("fs").unlinkSync(JSON.parse(require("fs").readFileSync(0)));',FIXTURE)
        if cancel:
            r=requests.post('http://127.0.0.1:18789/tools/invoke',headers={'Authorization':'Bearer '+private_state()['gateway_token']},
                json={'agentId':'formation-developpement','sessionKey':session,'tool':'training_run','args':{'action':'cancel','jobId':job}},timeout=20)
            if r.status_code!=200:raise RuntimeError('Cancel rejected')
        deadline=time.monotonic()+205
        while time.monotonic()<deadline and not exists(CONTROL+'/'+job+'.result.json'):time.sleep(2)
        result=remote_json(CONTROL+'/'+job+'.result.json')
        expected='cancelled' if cancel else 'timed_out'
        if result['status']!=expected:raise RuntimeError('Incorrect failure classification')
        p=subprocess.run([DOCKER,'inspect','asia-training-job-'+job],capture_output=True,timeout=5)
        if p.returncode==0:raise RuntimeError('Cancelled container still exists')
        return {'jobId':job,'status':result['status'],'container_removed':True,'exitCode':result['exitCode']}
    finally:
        if exists(FIXTURE):node('require("fs").unlinkSync(JSON.parse(require("fs").readFileSync(0)));',FIXTURE)


if __name__=='__main__':
    result={}
    for cancel in [False,True]:
        key='cancel' if cancel else 'timeout'
        result[key]=run_case(cancel)
        print(json.dumps({key:result[key]}),flush=True)
    (STATE/'failure-preflight.json').write_text(json.dumps(result,indent=2))
