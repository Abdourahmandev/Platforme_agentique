"""Independent supervisor checks, run in the same isolated official Node image."""
import argparse
import json
import re
import subprocess
import uuid
from common import ROOT, STATE, NODE, DOCKER
from runner import command, snapshot

ALLOWED={'infra/task-outcome.mjs','infra/health-report.mjs','test/task-outcome.test.mjs','test/health-report.test.mjs'}


def files(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*')
        if p.is_file() and not any(x in p.parts for x in ['node_modules','dist','__pycache__'])}


def main(label,baseline):
    if not re.fullmatch(r'[a-z0-9-]+',label):raise ValueError('Invalid evaluation label')
    target=STATE/('evaluation-'+label)
    target.mkdir(exist_ok=False)
    digest=snapshot(target)
    before,after=files(STATE/'jobs'/baseline),files(target)
    changed=sorted(n for n in before.keys()|after.keys() if before.get(n)!=after.get(n))
    if not set(changed)<=ALLOWED:raise RuntimeError('Files outside the authorized scope changed: '+', '.join(changed))
    (target/'heldout.mjs').write_bytes((ROOT/'infra/training/heldout.mjs').read_bytes())
    job=uuid.uuid4().hex
    args=command({'agentId':'formation-developpement','jobId':job,'sessionKey':'agent:formation-developpement:supervisor-evaluation','operation':'node_tests'},target)
    args=args[:args.index(NODE)+1]+['node','--test','--test-reporter=tap','heldout.mjs']
    try:p=subprocess.run(args,capture_output=True,timeout=180)
    finally:subprocess.run([DOCKER,'rm','-f','asia-training-job-'+job],capture_output=True,timeout=20)
    output=(p.stdout+p.stderr).decode('utf-8',errors='replace')
    (STATE/('evaluation-'+label+'.log')).write_text(output,encoding='utf-8')
    result={'label':label,'jobId':job,'source_sha256':digest,'changed_files':changed,'exitCode':p.returncode,
        'checks':re.findall(r'^(?:not )?ok \d+ - .*$',output,re.M)}
    (STATE/('evaluation-'+label+'.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps(result));raise SystemExit(p.returncode)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('--baseline',required=True);args=p.parse_args()
    if not re.fullmatch(r'[a-f0-9]{32}',args.baseline):raise ValueError('Invalid baseline job id')
    main(args.label,args.baseline)
