"""Enable the existing Windows executor for Souleiman; preserve Asia's journal.

No Windows permissions, credentials, budgets or network settings are changed.
Before-images and mutation progress are private. Rollback refuses file drift.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'infra/training'))
from common import BASE, GATEWAY, PRIVATE, docker, node, remote_json, remote_write

JOURNAL = PRIVATE / 'souleiman-windows-private.json'
TOOLS = ['asia_opencode_task', 'asia_opencode_approve']


def patch_for(current):
    entry = current['agents']['entries']['developpement']
    account = current['channels']['telegram']['accounts']['developpement']
    owners = account.get('allowFrom', [])
    if account.get('dmPolicy') != 'allowlist' or len(owners) != 1 or not str(owners[0]).isdigit():
        raise ValueError('Souleiman needs exactly one allowlisted Telegram owner')
    if not current.get('plugins', {}).get('entries', {}).get('asia-opencode', {}).get('enabled'):
        raise ValueError('Configure the existing Asia Windows bridge first')
    policy = deepcopy(entry.get('tools', {}))
    policy['allow'] = list(dict.fromkeys(policy.get('allow', []) + TOOLS))
    policy['deny'] = [t for t in policy.get('deny', []) if t not in TOOLS]
    approvals = deepcopy(current.get('approvals', {}).get('plugin', {}))
    if approvals.get('enabled') is not True or approvals.get('mode') != 'session':
        raise ValueError('The native session approval surface must already be enabled')
    approvals['agentFilter'] = list(dict.fromkeys(approvals.get('agentFilter', ['asia']) + ['developpement']))
    telegram = deepcopy(account.get('execApprovals', {}))
    telegram.update(enabled=True, approvers=owners, target='dm', agentFilter=['developpement'])
    return {'agents': {'entries': {'developpement': {'tools': policy}}},
            'tools': {'allow': list(dict.fromkeys(current['tools']['allow'] + TOOLS))},
            'approvals': {'plugin': approvals},
            'channels': {'telegram': {'accounts': {'developpement': {'execApprovals': telegram}}}}}


def save(journal):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    temporary = JOURNAL.with_suffix('.tmp')
    temporary.write_text(json.dumps(journal, indent=2), encoding='utf-8')
    temporary.replace(JOURNAL)


def files():
    result = {BASE + '/extensions/asia-opencode/' + p.name: p.read_text(encoding='utf-8')
              for p in (ROOT / 'infra/opencode-bridge').iterdir() if p.suffix in ('.mjs', '.json')}
    for agent, names in [('asia', ['AGENTS.md']), ('developpement', ['AGENTS.md', 'PROCEDURES.md'])]:
        for name in names:
            result[BASE + '/workspaces/' + agent + '/' + name] = (ROOT / 'infra/agents' / agent / name).read_text(encoding='utf-8')
    return result


def read_files(names):
    return json.loads(node('const fs=require("fs"),v=JSON.parse(fs.readFileSync(0));'
        'console.log(JSON.stringify(Object.fromEntries(v.map(p=>[p,fs.readFileSync(p,"utf8")]))));', list(names)))


def idle():
    # Read only; never abort another user's task as part of deployment.
    result = docker('exec', GATEWAY, 'node', '--input-type=module', '-e',
        "import fs from 'node:fs';"
        "const {Bridge}=await import('/home/node/.openclaw/extensions/asia-opencode/bridge.mjs');"
        "const b=new Bridge({stateFile:'/home/node/.openclaw/asia-opencode/tasks.json',"
        "credentials:()=>JSON.parse(fs.readFileSync('/home/node/.openclaw/credentials/asia-opencode.json'))});"
        "const s=await b.request('/session/status');console.log(JSON.stringify(Object.values(s).every(x=>x.type==='idle')));")
    if json.loads(result) is not True:
        raise RuntimeError('An OpenCode task is active; finish it before changing the bridge')


def reload_plugin():
    docker('exec', GATEWAY, 'node', 'dist/index.js', 'config', 'validate', timeout=90)
    docker('exec', GATEWAY, 'node', 'dist/index.js', 'plugins', 'reload', 'asia-opencode', timeout=120)


def rollback():
    journal = json.loads(JOURNAL.read_text(encoding='utf-8'))
    if journal['phase'] == 'rolled-back':
        print('Already rolled back.'); return
    idle()
    current = read_files(journal['before'])
    for name, before in journal['before'].items():
        allowed = [before, journal['target'].get(name)]
        if current[name] not in allowed:
            raise RuntimeError('Runtime file drift: inspect the private snapshot before rollback')
    # Keep task/session/receipt journals and all spending history intact.
    for name, content in journal['before'].items():
        remote_write(name, content)
    reload_plugin()
    journal['phase'] = 'rolled-back'; save(journal)
    print('Previous policies and plugin restored; task histories retained.')


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if os.environ.get('ASIA_TRAINING_CYCLE'):
        raise RuntimeError('Use the production runtime, not a training cycle')
    if args.rollback:
        rollback(); return
    current = remote_json(BASE + '/openclaw.json')
    patch = patch_for(current)
    docker('exec', '-i', GATEWAY, 'node', 'dist/index.js', 'config', 'patch', '--stdin', '--dry-run', '--json',
           data=json.dumps(patch).encode(), timeout=90)
    if not args.apply:
        print('Windows access and Telegram approval patch validated. No runtime changes.'); return
    if JOURNAL.exists():
        raise RuntimeError('A deployment journal already exists; inspect it instead of replaying')
    idle()
    target = files()
    before = read_files([*target, BASE + '/openclaw.json'])
    journal = {'at': datetime.now(timezone.utc).isoformat(), 'phase': 'prepared', 'before': before, 'target': target}
    save(journal)
    for name, content in target.items():
        remote_write(name, content)
    journal['phase'] = 'files-written'; save(journal)
    docker('exec', '-i', GATEWAY, 'node', 'dist/index.js', 'config', 'patch', '--stdin',
           data=json.dumps(patch).encode(), timeout=90)
    # Save the actual serialized config, including native metadata, for drift detection.
    journal['target'].update(read_files([BASE + '/openclaw.json']))
    journal['phase'] = 'configured'; save(journal)
    reload_plugin()
    journal['phase'] = 'deployed'; save(journal)
    print('Souleiman Windows access deployed. Verify live operations and native approvals.')


if __name__ == '__main__':
    main()
