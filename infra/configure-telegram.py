"""Prepare account bindings without ever starting a second production consumer.

Default: validate the proposed configuration without enabling a consumer.
--activate: requires tokens for the selected agents, owner allowlist, no webhooks.
--agent: select one or more agents without requiring the other bot credentials.
--reuse-existing-asia: prepare the existing Asia identity instead of a test bot.
--owner-id: owner allowlist for a fresh install without the legacy Windows bot files.
Its activation remains blocked here until the controlled legacy handoff is done.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import requests

RUNTIME=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')/'AsiaDocker'
DOCKER=(r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker')
EXEC=[DOCKER,'exec','-i','asia-platform-staging-openclaw-1']
ACCOUNTS={'asia-test':'asia','developpement':'developpement','recherche':'recherche'}
NAMES={key:value['name'] for key,value in json.loads((Path(__file__).parent/'agents/catalogue.json').read_text(encoding='utf-8')).items()}


def run(args,data=None):
    p=subprocess.run(EXEC+args,input=data,capture_output=True,timeout=120)
    if p.returncode:
        (RUNTIME/'telegram-configuration-error.log').write_bytes(p.stdout+p.stderr)
        raise RuntimeError('Telegram configuration failed; private diagnostic saved')
    return p.stdout


def cli(*args):
    return run(['node','dist/index.js',*args])


def telegram(token,method):
    try:
        r=requests.get('https://api.telegram.org/bot'+token+'/'+method,timeout=20)
        if r.ok and r.json().get('ok'): return r.json()['result']
    except (requests.RequestException,ValueError): pass
    # Exceptions containing a Telegram URL would expose the token.
    raise RuntimeError('Telegram credential or network validation failed')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--activate',action='store_true')
    parser.add_argument('--reuse-existing-asia',action='store_true')
    parser.add_argument('--agent',action='append',choices=['asia','developpement','recherche'],
                        help='Select an agent; repeat to select several. Defaults to all three.')
    parser.add_argument('--owner-id',help='Telegram user id allowed to message the bots (fresh install).')
    args=parser.parse_args()
    selected_accounts=({'asia':'asia','developpement':'developpement','recherche':'recherche'}
                       if args.reuse_existing_asia else ACCOUNTS)
    if args.agent:
        selected_accounts={account:agent for account,agent in selected_accounts.items() if agent in args.agent}
    state=json.loads((RUNTIME/'runtime-private.json').read_text())
    if state.get('phase')!='staging': raise RuntimeError('Staging initializer only')
    # A fresh install has no legacy Windows consumer to hand off from.
    legacy_path=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')/'OpenCodeTelegramSetup/bot-credentials.json'
    legacy=json.loads(legacy_path.read_text()) if legacy_path.exists() else None
    if not legacy and not args.owner_id: raise RuntimeError('No legacy bot files: pass --owner-id')
    owner=str(args.owner_id or legacy['AllowedUserId'])
    if not owner.isdecimal() or int(owner)<=0: raise RuntimeError('Invalid owner allowlist')
    current=json.loads(run(['node','-e','process.stdout.write(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"))']))
    if current.get('channels',{}).get('telegram',{}).get('enabled'):
        raise RuntimeError('Telegram already active; refusing to replace live bindings')
    if current.get('bindings'): raise RuntimeError('Existing bindings require a reviewed merge')
    accounts={}
    tokens={}
    ids=set()
    for account,agent in selected_accounts.items():
        path=RUNTIME/'secrets'/(account+'.token')
        if args.activate:
            if not path.exists(): raise RuntimeError('Missing token for '+account+'; run set-telegram-token.ps1')
            token=path.read_text().strip()
            bot=telegram(token,'getMe')
            if legacy and str(bot['id'])==legacy['Token'].split(':')[0]:
                raise RuntimeError('The existing Asia bot requires a controlled legacy handoff. This staging initializer does not stop its supervisor or authorize a second consumer.')
            if bot['id'] in ids: raise RuntimeError('Each agent must have a distinct Telegram bot')
            if telegram(token,'getWebhookInfo').get('url'):
                raise RuntimeError('A supplied bot already has a webhook; resolve its ownership first')
            ids.add(bot['id']);tokens[account]=token
        accounts[account]={'name':NAMES[agent],'enabled':True,
            'tokenFile':'/home/node/.openclaw/credentials/telegram-'+account+'.token',
            'dmPolicy':'allowlist','allowFrom':[owner],'groupPolicy':'disabled',
            'configWrites':False,'joinIntro':False,'mediaMaxMb':20,
            'streaming':{'mode':'partial'}}
    channel={'enabled':True,'dmPolicy':'allowlist','allowFrom':[owner],
             'groupPolicy':'disabled','configWrites':False,'accounts':accounts}
    bindings=[{'type':'route','agentId':agent,'match':{'channel':'telegram','accountId':account}}
              for account,agent in selected_accounts.items()]
    # Schema validation has no network consumer or configuration side effect.
    for key,value in (('bindings',bindings),('channels.telegram',channel)):
        cli('config','set',key,json.dumps(value),'--strict-json','--dry-run')
    if not args.activate:
        print(f'{len(accounts)} account/agent binding(s) validated. Telegram remains disabled; no tokens required for this dry run.')
        return
    run(['node','-e',
        'const fs=require("fs"),p="/home/node/.openclaw/credentials",v=JSON.parse(fs.readFileSync(0));'
        'fs.mkdirSync(p,{recursive:true,mode:0o700});'
        'for(const [a,t] of Object.entries(v))fs.writeFileSync(p+"/telegram-"+a+".token",t,{mode:0o600});'],json.dumps(tokens).encode())
    try:
        cli('config','set','bindings',json.dumps(bindings),'--strict-json')
        cli('config','set','channels.telegram',json.dumps(channel),'--strict-json')
        cli('config','validate')
    except Exception:
        cli('config','set','channels.telegram.enabled','false','--strict-json')
        raise
    print(f'{len(accounts)} staged Telegram bot(s) configured: '+', '.join(accounts)+'. Wait for gateway/channel health, then test from the owner account.')


if __name__=='__main__':
    main()
