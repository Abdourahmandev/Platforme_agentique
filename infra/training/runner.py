"""Operator-owned queue consumer. Agents never receive Docker or host shell access."""
import argparse
import base64
import hashlib
import json
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


def process(request):
    validate(request)
    job = request['jobId']
    target = STATE / 'jobs' / job
    target.mkdir(parents=True, exist_ok=False)
    remote_write(CONTROL + '/' + job + '.started.json', json.dumps({'started_at': time.time()}))
    result = {'jobId': job, 'operation': request['operation'], 'status': 'failed', 'exitCode': None}
    try:
        cancelled = json.loads(node('const fs=require("fs");console.log(JSON.stringify(fs.existsSync(JSON.parse(fs.readFileSync(0)))));', CONTROL + '/' + job + '.cancel'))
        if cancelled:
            result['status'] = 'cancelled'
            return result
        result['source_sha256'] = snapshot(target)
        args = command(request, target)
        # Logs go to a bounded container lifetime, then only a tail is returned.
        with (STATE / 'jobs' / (job + '.log')).open('wb') as log:
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output_limit=threading.Event()
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
                    try:
                        p.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        p.kill()
                    break
                time.sleep(1)
            result['exitCode'] = p.wait(timeout=15)
            reader.join(timeout=5)
            if output_limit.is_set() and result['status']=='failed':result['status']='output_limit'
        if result['status'] == 'failed' and result['exitCode'] == 0:
            result['status'] = 'passed'
        result['output'] = (STATE / 'jobs' / (job + '.log')).read_bytes()[-18000:].decode('utf-8', errors='replace')
    except Exception as e:
        result['error'] = type(e).__name__
    finally:
        subprocess.run([DOCKER, 'rm', '-f', 'asia-training-job-' + job], capture_output=True, timeout=20)
        result['finished_at'] = time.time()
        remote_write(CONTROL + '/' + job + '.result.json', json.dumps(result))
        (STATE / 'jobs' / (job + '.result.json')).write_text(json.dumps(result))
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
            if entry['started']:
                # A previous consumer may have died after submitting the job.
                # Stop its known container; never silently replay an uncertain job.
                subprocess.run([DOCKER, 'rm', '-f', 'asia-training-job-' + request['jobId']], capture_output=True, timeout=20)
                remote_write(CONTROL + '/' + request['jobId'] + '.result.json', json.dumps({
                    'jobId': request['jobId'], 'status': 'unknown_after_restart', 'exitCode': None}))
            else:
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
