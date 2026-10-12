"""Real runner/process failures against an isolated persistent queue, no inference.

The queue lives in a small official Node container instead of starting a second
OpenClaw runtime on this 12 GiB PC. Killing it breaks the exact docker-exec/file
transport used by the runner. This is not a crash test of OpenClaw's model loop.
Use a fresh ASIA_TRAINING_CYCLE; never operates on the production container.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from common import BASE, CONTROL, CYCLE, DOCKER, GATEWAY, NODE, ROOT, STATE, docker, remote_json, remote_write
from isolated import production_snapshot


def save(name,value):
    (STATE/name).write_text(json.dumps(value,indent=2),encoding='utf-8')


def wait_for(predicate,seconds=30):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.25)
    raise RuntimeError('Fixture did not reach its expected checkpoint')


def require_fixture():
    journal=json.loads((STATE/'journal.json').read_text())
    if journal.get('kind')!='runner-fault-fixture' or journal.get('status')!='active':
        raise RuntimeError('An active, dedicated fault fixture is required')
    details=json.loads(docker('inspect',GATEWAY))[0]
    if details['Config'].get('Labels',{}).get('asia.training.fault')!='true':
        raise RuntimeError('Refusing to interrupt a non-fixture container')


def prepare():
    if (STATE/'journal.json').exists():raise RuntimeError('Existing cycle evidence; choose a fresh number')
    STATE.mkdir(parents=True,exist_ok=True)
    save('journal.json',{'kind':'runner-fault-fixture','status':'active','keys':{},'budget_usd':0,
        'production_before':production_snapshot(),'created_at':time.time()})
    volume=GATEWAY+'-queue'
    docker('volume','create',volume)
    docker('run','--rm','--network','none','--user','0:0','--cap-drop','ALL','--cap-add','CHOWN',
        '--mount',f'type=volume,source={volume},target=/state',NODE,'node','-e',
        'require("fs").chmodSync("/state",0o700);require("fs").chownSync("/state",1000,1000);')
    start_fixture(volume)
    print(json.dumps({'fixture':GATEWAY,'inference_enabled':False,'memory_limit_mib':64}))


def start_fixture(volume):
    docker('run','-d','--init','--name',GATEWAY,'--label','asia.training.fault=true','--restart','no',
        '--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges',
        '--memory','64m','--cpus','0.5','--pids-limit','32',
        '--mount',f'type=volume,source={volume},target={BASE}',NODE,'node','-e','setInterval(()=>{},1000)')
    remote_write(CONTROL+'/control.json',json.dumps({'active':True,'mutationPaths':[]}))


def launch(request,publish_failure=False):
    # Python arguments are passed directly, never through a shell. The trusted
    # fault hook cuts the real transport at precisely the final publication.
    code='import sys,json;sys.path.insert(0,"infra/training");import runner;from common import docker,GATEWAY\n'
    if publish_failure:
        code+='original=runner.remote_write\ndef fail_at_publish(p,v):\n if p.endswith(".result.json"): docker("kill",GATEWAY)\n return original(p,v)\nrunner.remote_write=fail_at_publish\n'
    code+='print(json.dumps(runner.process(json.loads(sys.argv[1]))))'
    log=(STATE/(request['jobId']+'-consumer.log')).open('wb')
    p=subprocess.Popen([sys.executable,'-X','utf8','-c',code,json.dumps(request)],cwd=ROOT,
        stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return p,log


def one_case(label,mode,expect_fixed):
    if (STATE/(label+'.json')).exists():raise RuntimeError('Case evidence already exists; choose a fresh cycle')
    request={'jobId':uuid.uuid4().hex,'agentId':'formation-developpement',
        'sessionKey':'agent:formation-developpement:fault-'+label,'operation':'node_tests'}
    job=request['jobId'];target=STATE/'jobs'/job
    source="import{test}from'node:test';import fs from'node:fs';test('single effect fixture',async()=>{fs.appendFileSync('effects.txt','once\\n');"
    if mode!='publication':source+="await new Promise(r=>setTimeout(r,100000));"
    source+='});'
    remote_write(BASE+'/workspaces/formation-developpement/repo/test/fault.test.mjs',source)
    remote_write(CONTROL+'/'+job+'.request.json',json.dumps(request))
    p,log=launch(request,mode=='publication')
    try:
        wait_for(lambda:(target/'effects.txt').exists())
        snapshot_mtime=target.stat().st_mtime_ns
        if mode=='transport':docker('kill',GATEWAY)
        elif mode=='consumer':p.kill()
        p.wait(timeout=45)
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=10)
        log.close()
    local=STATE/'jobs'/(job+'.result.json')
    initial=json.loads(local.read_text()) if local.exists() else None
    if mode in ('transport','publication'):docker('start',GATEWAY)
    # Preserve the failed baseline, then reconcile it without executing again.
    consumer=subprocess.run([sys.executable,'-X','utf8','infra/training/runner.py','--seconds','3'],cwd=ROOT,
        capture_output=True,timeout=30)
    (STATE/(label+'-recovery.log')).write_bytes(consumer.stdout+consumer.stderr)
    result=remote_json(CONTROL+'/'+job+'.result.json')
    alive=subprocess.run([DOCKER,'inspect','asia-training-job-'+job],capture_output=True,timeout=5).returncode==0
    checks={'single_effect':(target/'effects.txt').read_text()=='once\n','no_replay':target.stat().st_mtime_ns==snapshot_mtime,
        'container_removed':not alive,'runner_recovered':consumer.returncode==0}
    if expect_fixed:
        expected='passed' if mode=='publication' else 'unknown_after_restart' if mode=='consumer' else 'unknown_after_transport'
        checks.update(durable_local_receipt=local.exists(),correct_outcome=result['status']==expected,
            original_receipt_preserved=(mode=='consumer' or initial==json.loads(local.read_text())),
            request_bound=bool(result.get('request_sha256')))
    else:checks['baseline_receipt_lost']=initial is None
    evidence={'jobId':job,'mode':mode,'consumer_exit':p.returncode,'local_before_recovery':initial,
              'remote_after_recovery':result,'checks':checks}
    save(label+'.json',evidence)
    print(json.dumps({'case':label,'jobId':job,'checks':checks}),flush=True)
    if not all(checks.values()):raise RuntimeError('Fault case failed; evidence retained: '+label)


def limit_case(mode):
    label='limit-'+mode
    if (STATE/(label+'.json')).exists():raise RuntimeError('Case evidence already exists; choose a fresh cycle')
    request={'jobId':uuid.uuid4().hex,'agentId':'formation-developpement',
        'sessionKey':'agent:formation-developpement:'+label,'operation':'node_tests'}
    job=request['jobId'];target=STATE/'jobs'/job
    source="import{test}from'node:test';import fs from'node:fs';test('limit fixture',async()=>{fs.writeFileSync('effects.txt','once\\n');"
    source+="process.stdout.write('x'.repeat(3*1024*1024));" if mode=='output' else "await new Promise(r=>setTimeout(r,600000));"
    source+='});'
    remote_write(BASE+'/workspaces/formation-developpement/repo/test/fault.test.mjs',source)
    remote_write(CONTROL+'/'+job+'.request.json',json.dumps(request))
    p,log=launch(request);start=time.monotonic()
    try:
        wait_for(lambda:(target/'effects.txt').exists())
        if mode=='cancel':remote_write(CONTROL+'/'+job+'.cancel','operator fault fixture')
        p.wait(timeout=210 if mode=='deadline' else 40)
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=10)
        log.close()
    result=remote_json(CONTROL+'/'+job+'.result.json')
    local=json.loads((STATE/'jobs'/(job+'.result.json')).read_text())
    expected={'cancel':'cancelled','deadline':'timed_out','output':'output_limit'}[mode]
    alive=subprocess.run([DOCKER,'inspect','asia-training-job-'+job],capture_output=True,timeout=5).returncode==0
    checks={'correct_outcome':result['status']==expected,'container_removed':not alive,
        'durable_local_receipt':local==result,'consumer_succeeded':p.returncode==0,
        'bounded_log':(STATE/'jobs'/(job+'.log')).stat().st_size<=2*1024*1024,
        'bounded_reply':len(result.get('output','').encode('utf-8'))<=18000}
    elapsed=time.monotonic()-start
    if mode=='deadline':checks['real_deadline']=180<=elapsed<=220
    save(label+'.json',{'jobId':job,'elapsed_seconds':elapsed,'status':result['status'],'checks':checks})
    print(json.dumps({'case':label,'jobId':job,'elapsed_seconds':elapsed,'checks':checks}),flush=True)
    if not all(checks.values()):raise RuntimeError('Execution limit failed; evidence retained: '+label)


def close():
    j=json.loads((STATE/'journal.json').read_text())
    if j.get('kind')!='runner-fault-fixture':raise RuntimeError('Not a fault-test fixture')
    docker('stop','--time','2',GATEWAY)
    j.update(status='stopped',production_unchanged=production_snapshot()==j['production_before'])
    save('journal.json',j)
    print(json.dumps({'fixture_stopped':True,'production_unchanged':j['production_unchanged']}))
    if not j['production_unchanged']:raise RuntimeError('Production changed during the test window; review required')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','baseline','verify','limits','close']);a=p.parse_args()
    if not CYCLE:raise SystemExit('Fresh named cycle required; production tests are forbidden')
    if a.action=='prepare':prepare()
    else:
        require_fixture()
        if a.action=='close':close()
        elif a.action=='baseline':one_case('baseline-transport','transport',False)
        elif a.action=='limits':
            for mode in ['cancel','output','deadline']:limit_case(mode)
        else:
            for label,mode in [('transport-fixed','transport'),('publication-fixed','publication'),('consumer-crash','consumer')]:
                one_case(label,mode,True)
