"""Operator fault injection: orphaned job and bounded output, no model calls.

Prepare while the runner is stopped, restart it, then verify. This simulates
the durable state left by a crash; it does not crash the production Gateway.
"""
import argparse
import json
import subprocess
import time
import uuid
from common import BASE, CONTROL, DOCKER, NODE, STATE, docker, node, remote_json, remote_write


def prepare():
    if not (STATE/'stop').exists():raise RuntimeError('Stop the runner before preparing the orphan fixture')
    job=uuid.uuid4().hex
    req={'jobId':job,'agentId':'formation-developpement','sessionKey':'agent:formation-developpement:orphan-fixture','operation':'node_tests'}
    docker('run','-d','--rm','--init','--name','asia-training-job-'+job,'--label','asia.training=true',
        '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000',
        '--memory','64m','--cpus','1','--pids-limit','32',NODE,'node','-e','setInterval(()=>{},1000)')
    remote_write(CONTROL+'/'+job+'.request.json',json.dumps(req))
    remote_write(CONTROL+'/'+job+'.started.json',json.dumps({'started_at':time.time(),'injected':True}))
    (STATE/'recovery-fixture.json').write_text(json.dumps(req))
    print(json.dumps({'orphan_prepared':job}))


def verify():
    req=json.loads((STATE/'recovery-fixture.json').read_text());job=req['jobId']
    result=remote_json(CONTROL+'/'+job+'.result.json')
    alive=subprocess.run([DOCKER,'inspect','asia-training-job-'+job],capture_output=True,timeout=5).returncode==0
    checks={'unknown_after_restart':result['status']=='unknown_after_restart','container_removed':not alive,'not_replayed':not (STATE/'jobs'/job).exists()}
    if not all(checks.values()):raise RuntimeError('Orphan recovery failed')
    (STATE/'recovery-preflight.json').write_text(json.dumps({'jobId':job,**checks},indent=2))
    print(json.dumps(checks))


def flood():
    job=uuid.uuid4().hex
    fixture=BASE+'/workspaces/formation-developpement/repo/test/training-flood.test.mjs'
    remote_write(fixture,"import {test} from 'node:test';test('output quota fixture',()=>{process.stdout.write('x'.repeat(3*1024*1024));});")
    try:
        remote_write(CONTROL+'/'+job+'.request.json',json.dumps({'jobId':job,'agentId':'formation-developpement','sessionKey':'agent:formation-developpement:flood-fixture','operation':'node_tests'}))
        for _ in range(60):
            exists=json.loads(node('const fs=require("fs"),p=JSON.parse(fs.readFileSync(0));console.log(JSON.stringify(fs.existsSync(p)));',CONTROL+'/'+job+'.result.json'))
            if exists:break
            time.sleep(1)
        result=remote_json(CONTROL+'/'+job+'.result.json')
        checks={'status':result['status'],'bounded_log':(STATE/'jobs'/(job+'.log')).stat().st_size<=2*1024*1024,
            'bounded_reply':len(result.get('output','').encode('utf-8'))<=18000}
        if checks['status']!='output_limit' or not checks['bounded_log'] or not checks['bounded_reply']:raise RuntimeError('Output quota failed')
        (STATE/'output-preflight.json').write_text(json.dumps({'jobId':job,**checks},indent=2))
        print(json.dumps(checks))
    finally:node('require("fs").unlinkSync(JSON.parse(require("fs").readFileSync(0)));',fixture)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','flood']);a=p.parse_args()
    {'prepare':prepare,'verify':verify,'flood':flood}[a.action]()
