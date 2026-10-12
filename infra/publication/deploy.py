"""Provision a private durable publisher, then explicitly enable its OpenClaw adapter.

Separate provision/install steps let storage and failure tests run before bot changes.
Credentials, journals and snapshots never enter the repository.
"""
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'infra/publication'
PRIVATE=Path(os.environ['LOCALAPPDATA'])/'AsiaPublication'
spec=importlib.util.spec_from_file_location('connectors',ROOT/'infra/configure-souleiman-connectors.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
IMAGE='node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20'
POSTGRES='asia-paperclip-postgres-1'

def save(name,value):
    PRIVATE.mkdir(parents=True,exist_ok=True)
    f=PRIVATE/name;t=f.with_suffix('.tmp');t.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');t.replace(f)

def compose(*args):
    r=subprocess.run([c.DOCKER,'compose','-f',str(SOURCE/'compose.yaml'),*args],capture_output=True,
                     env={**os.environ,'ASIA_PUBLICATION_DIR':PRIVATE.as_posix()},timeout=180)
    if r.returncode:
        (PRIVATE/'compose-private.log').write_bytes(r.stdout+r.stderr)
        raise RuntimeError('Compose failed; private diagnostic retained')

def sql(text):
    return c.docker('exec','-i',POSTGRES,'sh','-c','exec psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -At',data=text.encode(),timeout=60).decode()

def provision():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    config_file=PRIVATE/'config.json'
    if not config_file.exists():
        runtime=c.remote_json(c.CONFIG)
        tg=runtime['channels']['telegram']['accounts']['asia']
        token=tg.get('botToken')
        if tg.get('tokenFile')==c.BASE+'/credentials/telegram-asia.token':token=c.read_text(tg['tokenFile']).strip()
        if not isinstance(token,str) or ':' not in token:raise RuntimeError('Telegram token needs explicit local resolution')
        owner=str(tg['allowFrom'][0]);password=secrets.token_hex(24)
        cfg={'databaseUrl':'postgresql://asia_publication:'+quote(password)+'@asia-paperclip-postgres-1:5432/asia_publication',
             'databasePassword':password,'githubToken':c.github_token(),'telegramToken':token,'ownerId':owner,
             'ownerToken':secrets.token_hex(32),'agentTokens':{a:secrets.token_hex(32) for a in ['asia','developpement']},
             'allowedRepos':['Abdourahmandev/Simulateur_tax_qc','Abdourahmandev/asia-publication-tests'],
             'workerEnabled':True,'notificationsEnabled':True}
        save('config.json',cfg)
    cfg=json.loads(config_file.read_text(encoding='utf-8'))
    if 'asia_publication' not in sql("SELECT rolname FROM pg_roles WHERE rolname='asia_publication';").splitlines():
        sql("CREATE ROLE asia_publication LOGIN PASSWORD '"+cfg['databasePassword']+"';")
    for database in ['asia_publication','asia_publication_test']:
        if database not in sql("SELECT datname FROM pg_database WHERE datname='"+database+"';").splitlines():sql('CREATE DATABASE '+database+' OWNER asia_publication;')
    app=PRIVATE/'app';app.mkdir(exist_ok=True)
    for name in ['package.json','package-lock.json','core.mjs','store.mjs','github.mjs','server.mjs']:
        shutil.copy2(SOURCE/name,app/name)
    c.docker('run','--rm','-v',str(app)+':/app','-w','/app',IMAGE,'npm','ci','--omit=dev','--ignore-scripts',timeout=120)
    compose('up','-d','--force-recreate')
    print('Publisher provisioned. Verify health and storage tests before installing the agent adapter.')

def install(rollback=False):
    journal_file=PRIVATE/'adapter-before.json'
    if rollback:
        journal=json.loads(journal_file.read_text(encoding='utf-8'))
        if journal['phase']=='rolled-back':print('Already rolled back.');return
    elif journal_file.exists():
        journal=json.loads(journal_file.read_text(encoding='utf-8'))
        if journal['phase']=='deployed':raise RuntimeError('Adapter already deployed; inspect journal')
    else:
        current=c.remote_json(c.CONFIG)
        patch={'plugins':{'allow':list(dict.fromkeys(current['plugins']['allow']+['asia-publication'])),
                          'entries':{'asia-publication':{'enabled':True}}},
               'tools':{'allow':list(dict.fromkeys(current['tools']['allow']+['asia_publication']))},
               'agents':{'entries':{}}}
        instructions={}
        note=(SOURCE/'agent-instructions.md').read_text(encoding='utf-8')
        for agent in ['asia','developpement']:
            patch['agents']['entries'][agent]={'tools':{'allow':list(dict.fromkeys(current['agents']['entries'][agent]['tools']['allow']+['asia_publication']))}}
            filename=c.BASE+'/workspaces/'+agent+'/AGENTS.md';before=c.read_text(filename)
            if '## Publication documentaire durable' in before:raise RuntimeError('Instructions already installed without journal')
            instructions[agent]={'path':filename,'before':before,'target':before.rstrip()+'\n\n'+note}
        journal={'config_before':current,'patch':patch,'instructions':instructions,'phase':'prepared'}
        save('adapter-before.json',journal)
    restore=c.restore_patch(c.remote_json(c.CONFIG),journal['config_before'],journal['patch'])
    for item in journal['instructions'].values():
        if c.read_text(item['path']) not in [item['before'],item['target']]:raise RuntimeError('Instruction drift; reconcile before deployment')
    if not rollback:
        cfg=json.loads((PRIVATE/'config.json').read_text())
        creds={k:cfg[k] for k in ['ownerId','ownerToken','agentTokens']};creds['url']='http://publication:18820'
        c.remote_write(c.BASE+'/publication-control/credentials.json',json.dumps(creds))
        for source in (SOURCE/'plugin').iterdir():
            if source.is_file():c.remote_write(c.BASE+'/extensions/asia-publication/'+source.name,source.read_text(encoding='utf-8'))
    patch=restore if rollback else journal['patch']
    for dry in [True,False]:c.docker('exec','-i',c.GATEWAY,'node','dist/index.js','config','patch','--stdin',*(['--dry-run','--json'] if dry else []),data=json.dumps(patch).encode(),timeout=90)
    for item in journal['instructions'].values():c.remote_write(item['path'],item['before' if rollback else 'target'])
    c.docker('exec',c.GATEWAY,'node','dist/index.js','config','validate',timeout=90)
    if rollback:compose('stop')
    journal['phase']='rolled-back' if rollback else 'deployed';save('adapter-before.json',journal)
    print('Adapter restored; database and remote effects retained.' if rollback else 'Adapter installed; verify the Telegram owner command.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['provision','install','rollback','stop']);a=p.parse_args()
    if a.action=='provision':provision()
    elif a.action=='stop':compose('stop')
    else:install(a.action=='rollback')
