"""Operator-owned queue consumer. Agents never receive Docker or host shell access."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from common import BASE, CONTROL, DOCKER, GATEWAY, NODE, PYTHON, STATE, docker, node, remote_write

OPS = {'node_tests': (NODE, ['node', '--test']),
       'python_tests': (PYTHON, ['python', '-m', 'unittest', 'discover', '-s', 'test', '-p', 'test_*.py', '-v']),
       'build': (NODE, ['node', 'build.mjs'])}


def validate(request):
    if request.get('agentId') != 'formation-developpement':
        raise ValueError('Unknown agent')
    if not re.fullmatch(r'[a-f0-9]{32}', request.get('jobId', '')):
        raise ValueError('Invalid job id')
    if request.get('operation') not in OPS:
        raise ValueError('Operation forbidden')
    if not request.get('sessionKey', '').startswith('agent:formation-developpement:'):
        raise ValueError('Invalid session')


def safe_file(root, name):
    if '\\' in name or ':' in name or not name or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Invalid snapshot path')
    result = (root / name).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Snapshot path escape')
    return result


def snapshot(target):
    # Export only ordinary files from this agent's repo; never follow symlinks.
    files = json.loads(node('const fs=require("fs"),path=require("path"),root=JSON.parse(fs.readFileSync(0));'
        'let size=0,out=[];function walk(dir){for(const n of fs.readdirSync(dir)){'
        'if([".git","node_modules","dist","__pycache__"].includes(n))continue;'
        'const p=path.join(dir,n),s=fs.lstatSync(p);if(s.isSymbolicLink())throw Error("symlink refused");'
        'if(s.isDirectory())walk(p);else if(s.isFile()){size+=s.size;if(size>33554432||out.length>=1000)throw Error("snapshot quota");'
        'out.push([path.relative(root,p).split(path.sep).join("/"),fs.readFileSync(p).toString("base64")]);}}}walk(root);console.log(JSON.stringify(out));',
        BASE + '/workspaces/formation-developpement/repo'))
    digest = hashlib.sha256()
    for name, data in sorted(files):
        p = safe_file(target, name)
        raw = base64.b64decode(data, validate=True)
        digest.update(name.encode() + b'\0' + raw)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    return digest.hexdigest()


def command(request, target):
    validate(request)
    image, cmd = OPS[request['operation']]
    if request['operation'] == 'node_tests':
        tests = sorted(p.name for p in (target / 'test').glob('*.test.mjs'))
        if not tests:
            raise ValueError('No Node tests')
        cmd = cmd + ['test/' + name for name in tests]
    args = [DOCKER, 'run', '--rm', '--init', '--name', 'asia-training-job-' + request['jobId'],
        '--label', 'asia.training=true', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--user', '1000:1000', '--memory', '1g', '--memory-swap', '1g',
        '--cpus', '1', '--pids-limit', '128', '--tmpfs', '/tmp:rw,size=268435456,mode=1777',
        '--workdir', '/workspace', '--env', 'HOME=/tmp', '--env', 'LOCALAPPDATA=/tmp',
        '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'PYTHONPATH=/deps',
        '--mount', 'type=bind,source=' + str(target.resolve()) + ',target=/workspace',
        '--mount', 'type=volume,source=asia-training-node-deps,target=/workspace/node_modules,readonly',
        '--mount', 'type=volume,source=asia-training-python-deps,target=/deps,readonly', image, *cmd]
    return args


def heartbeat():
    remote_write(CONTROL + '/heartbeat.json', json.dumps({'timestamp': int(time.time() * 1000)}))


def request_digest(request):
    validate(request)
    return hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def durable_write(filename,value):
    """Commit a local receipt before any network publication; never replace evidence."""
    filename.parent.mkdir(parents=True,exist_ok=True)
    if filename.exists():
        if json.loads(filename.read_text(encoding='utf-8'))!=value:
            raise ValueError('Conflicting durable receipt; manual reconciliation required')
        return
    temporary=filename.with_suffix(filename.suffix+'.tmp')
    with temporary.open('w',encoding='utf-8') as f:
        json.dump(value,f)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(filename)


def publish_result(request,result):
    digest=request_digest(request)
    if result.get('jobId')!=request['jobId'] or result.get('request_sha256')!=digest:
        raise ValueError('Receipt does not belong to this exact request')
    durable_write(STATE/'jobs'/(request['jobId']+'.result.json'),result)
    # A failed publication is allowed to stop the consumer. The next explicitly
    # started consumer republishes this receipt, never its underlying command.
    remote_write(CONTROL+'/'+request['jobId']+'.result.json',json.dumps(result))


def remove_job(job):
    """Best-effort cleanup whose failure must not erase the execution receipt."""
    try:
        removed=subprocess.run([DOCKER,'rm','-f','asia-training-job-'+job],capture_output=True,timeout=20)
        return removed.returncode==0 or b'No such container:' in removed.stderr
    except (OSError,subprocess.TimeoutExpired):
        return False


def recover(request,remote_started):
    """Return true when existing evidence was reconciled without running a command."""
    job=request['jobId'];digest=request_digest(request)
    local=STATE/'jobs'/(job+'.result.json')
    if local.exists():
        publish_result(request,json.loads(local.read_text(encoding='utf-8')))
        return True
    marker=STATE/'jobs'/(job+'.started.json')
    if marker.exists():
        if json.loads(marker.read_text())['request_sha256']!=digest:
            raise ValueError('Changed request after execution began')
    if marker.exists() or remote_started:
        cleaned=remove_job(job)
        result={'jobId':job,'operation':request['operation'],
            'request_sha256':digest,'status':'unknown_after_restart','exitCode':None,
            'finished_at':time.time()}
        if not cleaned:result['cleanup_unconfirmed']=True
        publish_result(request,result)
        return True
    return False


def process(request):
    validate(request)
    job = request['jobId']
    target = STATE / 'jobs' / job
    target.mkdir(parents=True, exist_ok=False)
    started={'started_at':time.time(),'request_sha256':request_digest(request)}
    durable_write(STATE/'jobs'/(job+'.started.json'),started)
    result = {'jobId': job, 'operation': request['operation'], 'status': 'failed', 'exitCode': None,
              'request_sha256':started['request_sha256']}
    p=None;reader=None;log=None
    output_limit=threading.Event()
    try:
        remote_write(CONTROL + '/' + job + '.started.json', json.dumps(started))
        cancelled = json.loads(node('const fs=require("fs");console.log(JSON.stringify(fs.existsSync(JSON.parse(fs.readFileSync(0)))));', CONTROL + '/' + job + '.cancel'))
        if cancelled:
            result['status'] = 'cancelled'
            return result
        result['source_sha256'] = snapshot(target)
        args = command(request, target)
        # Keep the writer alive until the process and drain thread stop, including
        # when queue access fails halfway through execution.
        log=(STATE / 'jobs' / (job + '.log')).open('wb')
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        def drain():
            count=0
            while chunk:=p.stdout.read(8192):
                remaining=max(0,2*1024*1024-count)
                log.write(chunk[:remaining])
                count+=len(chunk)
                if count>2*1024*1024:output_limit.set()
        reader=threading.Thread(target=drain,daemon=True)
        reader.start()
        deadline = time.monotonic() + 180
        while p.poll() is None:
            heartbeat()
            cancelled = json.loads(node('const fs=require("fs"),v=JSON.parse(fs.readFileSync(0));console.log(JSON.stringify(fs.existsSync(v)));', CONTROL + '/' + job + '.cancel'))
            too_large = output_limit.is_set()
            if cancelled or time.monotonic() >= deadline or too_large:
                subprocess.run([DOCKER, 'kill', 'asia-training-job-' + job], capture_output=True, timeout=15)
                result['status'] = 'cancelled' if cancelled else 'timed_out' if not too_large else 'output_limit'
                try:p.wait(timeout=15)
                except subprocess.TimeoutExpired:p.kill()
                break
            time.sleep(1)
        result['exitCode'] = p.wait(timeout=15)
        reader.join(timeout=5)
        if output_limit.is_set() and result['status']=='failed':result['status']='output_limit'
        if result['status'] == 'failed' and result['exitCode'] == 0:
            result['status'] = 'passed'
    except Exception as e:
        if p is not None:result['status']='unknown_after_transport'
        result['error'] = type(e).__name__
    finally:
        if not remove_job(job):result['cleanup_unconfirmed']=True
        try:
            if p is not None:
                try:p.wait(timeout=15)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
                if reader:reader.join(timeout=5)
                if reader and reader.is_alive():
                    result['output_incomplete']=True
                else:
                    if p.stdout:p.stdout.close()
                    if log:log.close()
            elif log:log.close()
            if log:
                result['output']=(STATE/'jobs'/(job+'.log')).read_bytes()[-18000:].decode('utf-8',errors='replace')
        except (OSError,subprocess.TimeoutExpired):
            result['cleanup_unconfirmed']=True
        finally:
            result['finished_at'] = time.time()
            publish_result(request,result)
    return result


def serve(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not (STATE / 'stop').exists():
        heartbeat()
        batch = json.loads(node('const fs=require("fs"),r=JSON.parse(fs.readFileSync(0));'
            r'const pending=fs.readdirSync(r).filter(n=>/^[a-f0-9]{32}\.request\.json$/.test(n)&&!fs.existsSync(r+"/"+n.replace(".request.",".result.")));'
            'console.log(JSON.stringify(pending.map(n=>({request:JSON.parse(fs.readFileSync(r+"/"+n)),started:fs.existsSync(r+"/"+n.replace(".request.",".started."))}))));', CONTROL))
        for entry in batch:
            if (STATE / 'stop').exists():
                break
            request = entry['request']
            validate(request)
            if not recover(request,entry['started']):
                print(json.dumps({k: v for k, v in process(request).items() if k != 'output'}), flush=True)
        time.sleep(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=3600)
    args = parser.parse_args()
    # Exclusive host lock prevents two consumers. Reclaimed automatically on exit.
    import msvcrt
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'runner.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        serve(args.seconds)
