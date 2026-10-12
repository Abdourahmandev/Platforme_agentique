"""Prepare/apply/stop training without changing production identities or budgets."""
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import subprocess
import time
from common import BASE, CONTROL, GATEWAY, IDS, NODE, PRIVATE, PYTHON, ROOT, STATE, TEAM, api, balances, docker, node, remote_json, remote_write
from common import CYCLE

JOURNAL = STATE / 'journal.json'
COMM = ['agents_list','sessions_spawn','sessions_yield','subagents','sessions_send','conversations_send','conversations_turn','message']


def patch_for(current):
    entries = {}
    for agent in IDS:
        role = agent.removeprefix('formation-')
        allow = ['read','write','edit','web_fetch','session_status','sessions_list','sessions_history']
        deny = ['exec','process','browser','playwright__*','asia-memory__*','asia_opencode_task','asia_opencode_approve']
        if role == 'asia':
            allow += COMM[:4]
            # OpenClaw children inherit the parent's effective tool catalog.
            # Asia must carry these descriptors; plugin execution guards still
            # reserve them to the two specialists (including HTTP invocation).
            allow += ['training_run','tavily__tavily_search','tavily__tavily_extract']
            deny += ['tavily__tavily_map','tavily__tavily_crawl','sessions_send','conversations_send','conversations_turn','message']
        elif role == 'recherche':
            allow += ['tavily__tavily_search','tavily__tavily_extract']
            deny += COMM + ['training_run','tavily__tavily_map','tavily__tavily_crawl']
        else:
            allow += ['training_run']
            deny += COMM + ['tavily__*']
        entries[agent] = {'name': 'Formation ' + role, 'workspace': BASE + '/workspaces/' + agent,
            'agentDir': BASE + '/agents/' + agent + '/agent', 'model': {'primary':'litellm/asia-rapide'},
            'tools': {'allow':allow,'deny':deny},
            'subagents': {'allowAgents': IDS[1:] if role == 'asia' else []}}
    return {'agents':{'entries':entries},
        'tools':{'allow':list(dict.fromkeys(current['tools']['allow'] + ['training_run']))},
        'plugins':{'allow':list(dict.fromkeys(current['plugins']['allow'] + ['asia-training'])),
                   'entries':{'asia-training':{'enabled':True}}}}


def patch(value, dry=False):
    args = ['exec','-i',GATEWAY,'node','dist/index.js','config','patch','--stdin']
    if dry:
        args += ['--dry-run','--json']
    docker(*args, data=json.dumps(value).encode())


def save(j):
    STATE.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(j, indent=2))


def instructions(role, improved=False):
    text = (ROOT / 'infra/agents' / role / 'AGENTS.md').read_text(encoding='utf-8')
    text = text.replace('`asia`','`formation-asia`').replace('`recherche`','`formation-recherche`').replace('`developpement`','`formation-developpement`')
    if role == 'asia':
        # Drop host execution instructions: training has no Windows bridge.
        text = text.split('Pour executer une tache sur Windows')[0]
        text = text.replace('pas encore raccordes','raccordes pour la formation').replace('ne peut pas executer de commandes','peut lancer les tests via training_run')
    if role == 'developpement':
        text = text.replace("Pendant la migration, l'execution de commandes et OpenCode/ACP ne sont pas encore actives.",
            'Tu peux modifier repo/ puis lancer les tests et la compilation avec training_run. Le shell general reste interdit.')
    if role == 'recherche':
        text = text.replace('la recherche web et les connecteurs additionnels restent a valider',
            'Tavily search et extract sont disponibles pour la formation')
    text += '\n\nFORMATION : ton identifiant est formation-' + role + '. Tes essais sont separes de Telegram. '
    text += 'Lis PROJECT.md pour le contexte. N\'utilise pas de donnees personnelles. Ne change jamais de modele. '
    text += 'Les instructions de formation priment sur les descriptions historiques de capacites ci-dessus. '
    text += 'Recherche : Tavily basic, maximum 5 resultats et 3 URL par appel, aucune recherche avancee. '
    text += 'Developpement : travaille uniquement dans repo/ ; training_run accepte node_tests, python_tests ou build. '
    text += 'N\'ecris jamais une nouvelle consigne comme preuve de test. Cite le jobId et le vrai code de sortie. '
    text += 'Decouvre les outils via tool_search, puis tool_describe avant tool_call.\n'
    if improved:
        text += '\nLis PLAYBOOK.md avant toute mission.\n'
    return text


def seed():
    files = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    files = [f for f in files if f and not f.startswith(('.github/','documentation/formation/'))
             and f not in ('infra/training/heldout.mjs','infra/training/curriculum.json')]
    for agent in IDS:
        role = agent.removeprefix('formation-')
        remote_write(BASE + '/workspaces/' + agent + '/AGENTS.md', instructions(role))
        remote_write(BASE + '/workspaces/' + agent + '/PROJECT.md',
            '# Plateforme de reference\n\n' + (ROOT/'README.md').read_text(encoding='utf-8') +
            '\n\n' + (ROOT/'documentation/revue-et-tests.md').read_text(encoding='utf-8') +
            '\n\n' + (ROOT/'documentation/delegation.md').read_text(encoding='utf-8'))
    payload = [[f,base64.b64encode((ROOT/f).read_bytes()).decode()] for f in files]
    node('const fs=require("fs"),p=require("path"),v=JSON.parse(fs.readFileSync(0)),root="' + BASE + '/workspaces/formation-developpement/repo";'
         'for(const [name,data] of v){const dest=p.join(root,name);fs.mkdirSync(p.dirname(dest),{recursive:true});fs.writeFileSync(dest,Buffer.from(data,"base64"));}',payload)
    for source in (ROOT/'infra/training/plugin').iterdir():
        if source.is_file():
            remote_write(BASE + '/extensions/asia-training/' + source.name, source.read_text(encoding='utf-8'))


def dependencies():
    # Trusted bootstrap only: locked dependencies, separate from the agent-modifiable repo.
    deps = STATE/'bootstrap'
    deps.mkdir(parents=True, exist_ok=True)
    for name in ['package.json','package-lock.json']:
        (deps/name).write_bytes((ROOT/name).read_bytes())
    for volume in ['asia-training-node-deps','asia-training-python-deps']:
        docker('volume','create',volume)
    docker('run','--rm','--memory','512m','--cpus','1','--cap-drop','ALL','--security-opt','no-new-privileges',
        '--mount',f'type=bind,source={deps.resolve()},target=/bootstrap,readonly',
        '--mount','type=volume,source=asia-training-node-deps,target=/deps',NODE,
        'sh','-c','cp /bootstrap/package*.json /tmp/; cd /tmp; npm ci --ignore-scripts --no-audit --no-fund && cp -a node_modules/. /deps/',timeout=240)
    docker('run','--rm','--memory','512m','--cpus','1','--cap-drop','ALL','--security-opt','no-new-privileges',
        '--mount','type=volume,source=asia-training-python-deps,target=/deps',PYTHON,
        'python','-m','pip','install','--no-cache-dir','--target','/deps',
        'cryptography==46.0.3','requests==2.32.5','PyYAML==6.0.3',timeout=240)


def migrate_credentials():
    """The pinned OpenClaw requires exclusive maintenance for JSON -> SQLite auth."""
    before=remote_json(BASE+'/openclaw.json')
    compose=[__import__('common').DOCKER,'compose','-f',str(ROOT/'infra/compose.yaml')]
    env=dict(os.environ,ASIA_RUNTIME_DIR=PRIVATE.as_posix())
    p=subprocess.run(compose+['stop','openclaw'],env=env,capture_output=True,timeout=380)
    if p.returncode: raise RuntimeError('Gateway graceful stop failed')
    code=1
    try:
        p=subprocess.run(compose+['run','--rm','--no-deps','openclaw','node','dist/index.js',
            'doctor','--fix','--non-interactive','--no-workspace-suggestions'],env=env,capture_output=True,timeout=180)
        (STATE/'credential-migration.log').write_bytes(p.stdout+p.stderr)
        code=p.returncode
    finally:
        p=subprocess.run(compose+['up','-d','--no-deps','openclaw'],env=env,capture_output=True,timeout=180)
        if p.returncode: raise RuntimeError('Gateway restart failed')
    for _ in range(180):
        if docker('inspect','--format','{{.State.Health.Status}}',GATEWAY).decode().strip()=='healthy': break
        time.sleep(2)
    else: raise RuntimeError('Gateway health did not recover')
    if code: raise RuntimeError('Credential migration failed; private diagnostic saved')
    after=remote_json(BASE+'/openclaw.json')
    comparable=deepcopy(after)
    comparable['wizard']=deepcopy(before.get('wizard',{}))
    comparable['plugins']['allow']=[x for x in comparable['plugins']['allow']
        if x!='telegram' or x in before['plugins']['allow']]
    if comparable!=before:
        raise RuntimeError('Doctor changed unrelated config; review before proceeding')
    return after


def apply():
    if CYCLE:
        raise RuntimeError('Use isolated.py prepare for a named cycle; legacy apply is disabled')
    if JOURNAL.exists():
        raise RuntimeError('Existing training journal; inspect before reapplying')
    backup=json.loads((PRIVATE/'docker-backup-result.json').read_text())
    if not all(backup.get(k) for k in ['openclaw_native_verify','openclaw_restored','postgres_restored']):
        raise RuntimeError('Verified restore point required')
    if time.time()-__import__('pathlib').Path(backup['archive']).stat().st_mtime>86400:
        raise RuntimeError('Recovery point older than 24 hours')
    before=remote_json(BASE+'/openclaw.json')
    if any(a in before['agents']['entries'] for a in IDS):
        raise RuntimeError('Training identity already exists')
    balance=balances()
    credit=next(float(b['total_balance']) for b in balance['deepseek'] if b['currency']=='USD')
    team=api('/team/info',params={'team_id':TEAM})['team_info']
    cap=round(min(4.0,credit-0.25,float(team['max_budget'])-float(team.get('spend') or 0)),6)
    if cap<=0:
        raise RuntimeError('Insufficient confirmed credit')
    if balance['tavily']['plan_limit']-balance['tavily']['plan_usage']<40:
        raise RuntimeError('Insufficient included search credits')
    j={'status':'preparing','created_at':datetime.now(timezone.utc).isoformat(),
       'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
       'before':before,'balance_before':balance,'budget_usd':cap,'keys':{},'user':'formation-'+str(int(time.time()))}
    save(j)
    seed()
    remote_write(CONTROL+'/control.json',json.dumps({'active':True,'searchCalls':0}))
    delta=patch_for(before)
    patch(delta,dry=True)
    api('/user/new',{'user_id':j['user'],'user_role':'internal_user','auto_create_key':False})
    api('/team/member_add',{'team_id':TEAM,'max_budget_in_team':cap,'member':{'role':'user','user_id':j['user']}})
    for agent in IDS:
        key=api('/key/generate',{'key_alias':agent,'user_id':j['user'],'team_id':TEAM,
            'models':['asia-rapide'],'key_type':'llm_api','allowed_routes':['/chat/completions','/v1/chat/completions','/models','/v1/models'],
            'max_budget':cap,'duration':'24h','rpm_limit':20,'max_parallel_requests':1,
            'metadata':{'purpose':'training','agent_id':agent}})['key']
        j['keys'][agent]=key
        save(j)
        remote_write(BASE+'/agents/'+agent+'/agent/auth-profiles.json',json.dumps({
            'version':1,'profiles':{'litellm:default':{'type':'api_key','provider':'litellm','key':key}},'order':{'litellm':['litellm:default']}}))
    before=migrate_credentials()
    delta=patch_for(before)
    if remote_json(BASE+'/openclaw.json')!=before:
        raise RuntimeError('Configuration changed during preparation')
    patch(delta)
    after=remote_json(BASE+'/openclaw.json')
    for k in ['channels','bindings']:
        if before.get(k)!=after.get(k):
            raise RuntimeError('Production identity changed')
    for a in ['asia','developpement','recherche']:
        if before['agents']['entries'][a]!=after['agents']['entries'][a]:
            raise RuntimeError('Production policy changed')
    j['status']='active'
    save(j)
    print(json.dumps({'training_active':True,'budget_usd':cap,'deepseek_balance_usd':credit,'production_preserved':True}))


def stop(rollback=False):
    j=json.loads(JOURNAL.read_text())
    control=remote_json(CONTROL+'/control.json')
    control['active']=False
    remote_write(CONTROL+'/control.json',json.dumps(control))
    node('const fs=require("fs"),r=JSON.parse(fs.readFileSync(0));for(const n of fs.readdirSync(r)){'
         r'if(/^[a-f0-9]{32}\.request\.json$/.test(n)&&!fs.existsSync(r+"/"+n.replace(".request.",".result.")))'
         'fs.writeFileSync(r+"/"+n.replace(".request.json",".cancel"),"");}',CONTROL)
    for key in j['keys'].values():
        api('/key/block',{'key':key})
    (STATE/'stop').write_text('stop')
    j['status']='stopped'
    save(j)
    if rollback:
        current=remote_json(BASE+'/openclaw.json')
        # The pinned Gateway requires its explicit agent-deletion lifecycle;
        # config patch deliberately rejects silently dropping roster entries.
        # Even deleteFiles=false purges native session rows, so require a fresh
        # verified encrypted backup before retiring the temporary identities.
        backup=json.loads((PRIVATE/'docker-backup-result.json').read_text())
        if not all(backup.get(k) is True for k in ['openclaw_native_verify','openclaw_restored','postgres_restored']):
            raise RuntimeError('Verified backup required before retiring training profiles')
        archive=__import__('pathlib').Path(backup['archive'])
        latest=max([datetime.fromisoformat(j['created_at']).timestamp()]+[p.stat().st_mtime for p in STATE.glob('*-history.json')])
        if archive.stat().st_mtime<latest or time.time()-archive.stat().st_mtime>86400:
            raise RuntimeError('Create and restore-check a fresh backup before retiring profiles; keys already blocked')
        if any(b.get('agentId') in IDS for b in current.get('bindings',[])):
            raise RuntimeError('A training identity has a channel binding; review before retiring it')
        for agent in IDS:
            if agent in remote_json(BASE+'/openclaw.json')['agents']['entries']:
                raw=docker('exec',GATEWAY,'node','dist/index.js','gateway','call','agents.delete',
                    '--params',json.dumps({'agentId':agent,'deleteFiles':False}),'--timeout','90000','--json')
                (STATE/('retired-'+agent+'.json')).write_bytes(raw)
                if agent in remote_json(BASE+'/openclaw.json')['agents']['entries']:
                    raise RuntimeError('Training profile remains after explicit deletion')
        # Preserve unrelated changes made after installation.
        current=remote_json(BASE+'/openclaw.json')
        patch({'tools':{'allow':[x for x in current['tools']['allow'] if x!='training_run']},
            'plugins':{'allow':[x for x in current['plugins']['allow'] if x!='asia-training'],
                'entries':{'asia-training':None}}})
    j['status']='rolled-back' if rollback else 'stopped'
    save(j)
    print(json.dumps({'status':j['status'],'keys_blocked':True,'accounting_preserved':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['dependencies','apply','stop','rollback','balances'])
    args=p.parse_args()
    if CYCLE and args.action not in ('balances','dependencies'):
        raise SystemExit('Use isolated.py for named cycles; legacy lifecycle is disabled')
    try:
        if args.action=='dependencies': dependencies();print('Dependencies prepared')
        elif args.action=='apply': apply()
        elif args.action=='balances': print(json.dumps(balances()))
        else: stop(args.action=='rollback')
    except Exception as e:
        if args.action=='apply' and JOURNAL.exists():
            try: stop(rollback=True)
            except Exception: print('Automatic rollback incomplete; inspect private training journal before retrying')
        print('Training setup failed: '+(str(e) if isinstance(e,(RuntimeError,ValueError)) else type(e).__name__))
        raise SystemExit(1)
