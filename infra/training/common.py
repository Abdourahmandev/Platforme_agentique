"""Private training state and bounded, non-shell Docker transport."""
import json
import os
import re
from pathlib import Path
import subprocess
import time
import requests

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = Path(os.environ.get('LOCALAPPDATA', '/tmp')) / 'AsiaDocker'
CYCLE = os.environ.get('ASIA_TRAINING_CYCLE', '')
if CYCLE and not re.fullmatch(r'cycle-[1-9][0-9]{0,3}', CYCLE):
    raise ValueError('Invalid training cycle; expected cycle-N')
STATE = PRIVATE / 'training' / 'cycles' / CYCLE if CYCLE else PRIVATE / 'training'
DOCKER = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker'
GATEWAY = 'asia-training-' + CYCLE if CYCLE else 'asia-platform-staging-openclaw-1'
BASE = '/home/node/.openclaw'
CONTROL = BASE + '/training-control'
IDS = ['formation-asia', 'formation-developpement'] if CYCLE else ['formation-asia', 'formation-recherche', 'formation-developpement']
TEAM = 'asia-platform-staging'
NODE = 'node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20'
PYTHON = 'python@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641'


def docker(*args, data=None, timeout=120):
    p = subprocess.run([DOCKER, *args], input=data, capture_output=True, timeout=timeout)
    if p.returncode:
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / 'transport-error.log').write_bytes(p.stdout + p.stderr)
        raise RuntimeError('Docker operation failed; private diagnostic saved')
    return p.stdout


def node(code, value=None):
    return docker('exec', '-i', GATEWAY, 'node', '-e', code,
                  data=None if value is None else json.dumps(value).encode())


def remote_json(filename):
    return json.loads(node('process.stdout.write(require("fs").readFileSync(JSON.parse(require("fs").readFileSync(0))))', filename))


def remote_write(filename, content):
    node('const fs=require("fs"),p=require("path"),v=JSON.parse(fs.readFileSync(0));'
         'fs.mkdirSync(p.dirname(v.path),{recursive:true,mode:0o700});'
         'fs.writeFileSync(v.path+".tmp",v.text,{mode:0o600});fs.renameSync(v.path+".tmp",v.path);',
         {'path': filename, 'text': content})


def private_state():
    return json.loads((PRIVATE / 'runtime-private.json').read_text())


def api(path, payload=None, params=None):
    headers = {'Authorization': 'Bearer ' + private_state()['master_key']}
    r = requests.request('GET' if payload is None else 'POST', 'http://127.0.0.1:14000' + path,
                         headers=headers, json=payload, params=params, timeout=25)
    if not r.ok:
        raise RuntimeError(f'LiteLLM {path}: HTTP {r.status_code}')
    return r.json()


def envfile(name):
    return {k.strip(): v.strip().strip('"').strip("'") for k, v in
            (line.split('=', 1) for line in (PRIVATE / name).read_text().splitlines()
             if '=' in line and not line.lstrip().startswith('#'))}


def balances(include_search=True):
    result = {}
    for name, file, key, url in [
        ('deepseek', 'litellm.env', 'DEEPSEEK_API_KEY', 'https://api.deepseek.com/user/balance'),
        ('tavily', 'openclaw.env', 'ASIA_TAVILY_API_KEY', 'https://api.tavily.com/usage'),
    ]:
        if name=='tavily' and not include_search:
            continue
        # /usage is rate-limited independently of search. A short-lived verified
        # snapshot plus the tool quota avoids hammering this read-only endpoint.
        cache=STATE/'balance-cache.json'
        if name=='tavily' and cache.exists():
            saved=json.loads(cache.read_text())
            if 0<=time.time()-saved['fetched_at']<300:
                result[name]=saved['tavily']
                continue
        r = requests.get(url, headers={'Authorization': 'Bearer ' + envfile(file)[key]},
                         timeout=20, allow_redirects=False)
        if r.status_code != 200:
            raise RuntimeError(f'{name} balance unavailable: HTTP {r.status_code}')
        value = r.json()
        result[name] = value['balance_infos'] if name == 'deepseek' else value['account']
        if name=='tavily':
            STATE.mkdir(parents=True,exist_ok=True)
            cache.write_text(json.dumps({'fetched_at':time.time(),'tavily':result[name]}))
    return result
