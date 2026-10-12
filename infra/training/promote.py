"""Install reviewed production procedures with a compare-and-restore journal."""
import argparse
import json
import re
from datetime import datetime, timezone
from common import BASE, CYCLE, PRIVATE, ROOT, STATE, node, remote_write

JOURNAL=STATE/'promotion.json'
LINE='\n\nLis PROCEDURES.md pour les methodes de travail validees lors du cycle de formation supervisee.\n'


def read_remote(name):
    return json.loads(node('const fs=require("fs"),p=JSON.parse(fs.readFileSync(0));console.log(JSON.stringify(fs.existsSync(p)?fs.readFileSync(p,"utf8"):null));',name))


def install():
    if JOURNAL.exists():raise RuntimeError('Existing promotion journal; inspect before changing instructions')
    changes=[]
    for role in ['asia','recherche','developpement']:
        for name in ['AGENTS.md','PROCEDURES.md']:
            local=ROOT/'infra/agents'/role/name
            remote=BASE+'/workspaces/'+role+'/'+name
            before=read_remote(remote)
            local_before=local.read_text(encoding='utf-8')
            if name=='AGENTS.md':
                if before is None:raise RuntimeError('Missing production instructions')
                after=before+LINE if LINE.strip() not in before else before
                local_after=local_before+LINE if LINE.strip() not in local_before else local_before
            else:after=local_after=local_before
            changes.append(dict(local=str(local),remote=remote,before=before,after=after,local_before=local_before,local_after=local_after))
    j={'status':'prepared','at':datetime.now(timezone.utc).isoformat(),'changes':changes}
    JOURNAL.write_text(json.dumps(j,indent=2))
    for change in changes:
        if read_remote(change['remote'])!=change['before']:raise RuntimeError('Production file changed; inspect journal')
        remote_write(change['remote'],change['after'])
        __import__('pathlib').Path(change['local']).write_text(change['local_after'],encoding='utf-8')
    for change in changes:
        if read_remote(change['remote'])!=change['after']:raise RuntimeError('Promotion verification failed')
    j['status']='applied';JOURNAL.write_text(json.dumps(j,indent=2))
    print(json.dumps({'procedures_applied':3,'verified_files':len(changes),'permissions_changed':False}))


def rollback():
    j=json.loads(JOURNAL.read_text())
    # Check every live file before changing any; do not overwrite later edits.
    from pathlib import Path
    for c in j['changes']:
        if read_remote(c['remote']) not in (c['before'],c['after']):raise RuntimeError('Live instructions changed since promotion')
        if Path(c['local']).read_text(encoding='utf-8') not in (c['local_before'],c['local_after']):raise RuntimeError('Local instructions changed since promotion')
    for c in j['changes']:
        if c['before'] is None:
            node('const fs=require("fs"),p=JSON.parse(fs.readFileSync(0));if(fs.existsSync(p))fs.unlinkSync(p);',c['remote'])
        else:remote_write(c['remote'],c['before'])
        Path(c['local']).write_text(c['local_before'],encoding='utf-8')
    j['status']='rolled-back';JOURNAL.write_text(json.dumps(j,indent=2))
    print('Previous production instructions restored')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['apply','rollback']);p.add_argument('--revision');args=p.parse_args()
    if CYCLE:raise SystemExit('Unset ASIA_TRAINING_CYCLE before promoting reviewed production procedures')
    if args.revision:
        if not re.fullmatch(r'cycle-[1-9][0-9]{0,3}',args.revision):raise SystemExit('Invalid procedure revision')
        JOURNAL=PRIVATE/'training/cycles'/args.revision/'promotion.json'
        if not JOURNAL.parent.is_dir():raise SystemExit('Unknown cycle; no procedure promotion')
    install() if args.action=='apply' else rollback()
