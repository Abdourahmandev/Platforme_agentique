"""Native Asia -> specialist tasks, with isolated context and parent completion.

Ordinary cross-agent messaging stays disabled. Only Asia receives orchestration
tools. Default validates; --apply saves a private before-image; --rollback restores
only the managed policies and agent instructions, never tokens or accounting.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'AsiaDocker'
JOURNAL = RUNTIME / 'delegation-private.json'
ORCHESTRATION = ['agents_list', 'sessions_spawn', 'sessions_yield', 'subagents']
COMMUNICATION = ORCHESTRATION + ['sessions_send', 'conversations_send', 'conversations_turn', 'message']
spec = importlib.util.spec_from_file_location('telegram_setup', ROOT / 'infra/configure-telegram.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def run(*args, data=None):
    return setup.run(list(args), data)


def current_config():
    return json.loads(run('node', '-e', 'process.stdout.write(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"))'))


def patch_for(config):
    entries = config['agents']['entries']
    if not {'asia', 'developpement', 'recherche'}.issubset(entries):
        raise ValueError('The three configured agents are required')
    global_allow = list(config['tools']['allow'])
    policies = {}
    for agent, entry in entries.items():
        tools = deepcopy(entry.get('tools', {}))
        allow = list(tools.get('allow', global_allow))
        if agent == 'asia':
            tools['allow'] = list(dict.fromkeys(allow + ORCHESTRATION))
            if set(tools.get('deny', [])) & set(ORCHESTRATION):
                raise ValueError('Asia has an explicit orchestration denial; review before changing')
        else:
            tools['allow'] = [name for name in allow if name not in COMMUNICATION]
            tools['deny'] = list(dict.fromkeys(tools.get('deny', []) + COMMUNICATION))
        policies[agent] = {'tools': tools,
                          'subagents': {'allowAgents': ['developpement', 'recherche'] if agent == 'asia' else []}}
    child_denials = config.get('tools', {}).get('subagents', {}).get('tools', {}).get('deny', [])
    return {'tools': {
        'allow': list(dict.fromkeys(global_allow + ORCHESTRATION)),
        'agentToAgent': {'enabled': False}, 'sessions': {'visibility': 'tree'},
        'subagents': {'tools': {'deny': list(dict.fromkeys(child_denials + COMMUNICATION))}},
        'swarm': {'enabled': False}},
        'agents': {'defaults': {'subagents': {'allowAgents': [], 'maxSpawnDepth': 1,
            'maxConcurrent': 1, 'maxChildrenPerAgent': 2, 'runTimeoutSeconds': 180,
            'archiveAfterMinutes': 60}}, 'entries': policies}}


def rollback_patch(config):
    # Explicit nulls remove fields that did not exist before this change.
    return {'tools': {key: deepcopy(config['tools'].get(key))
                      for key in ('allow', 'agentToAgent', 'sessions', 'subagents', 'swarm')},
        'agents': {'defaults': {'subagents': deepcopy(config['agents']['defaults'].get('subagents'))},
                   'entries': {agent: {key: deepcopy(entry.get(key)) for key in ('tools', 'subagents')}
                               for agent, entry in config['agents']['entries'].items()}}}


def cli_patch(patch, dry=False):
    args = ['node', 'dist/index.js', 'config', 'patch', '--stdin']
    if dry:
        args += ['--dry-run', '--json']
    return run(*args, data=json.dumps(patch).encode())


def write_instructions(instructions):
    run('node', '-e', 'const fs=require("fs"),v=JSON.parse(fs.readFileSync(0));'
        'for(const [a,s] of Object.entries(v))fs.writeFileSync("/home/node/.openclaw/workspaces/"+a+"/AGENTS.md",s,{mode:0o600});',
        data=json.dumps(instructions).encode())


def restore(journal):
    cli_patch(journal['rollback'])
    write_instructions(journal['instructions'])
    journal['status'] = 'rolled-back'
    JOURNAL.write_text(json.dumps(journal))


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if args.rollback:
        journal = json.loads(JOURNAL.read_text())
        if journal.get('status') == 'rolled-back':
            raise RuntimeError('Delegation already rolled back')
        restore(journal)
        print('Delegation policy and instructions restored. Telegram identities and budgets preserved.')
        return
    before = current_config()
    patch = patch_for(before)
    cli_patch(patch, dry=True)
    cli_patch(rollback_patch(before), dry=True)
    if not args.apply:
        print('Delegation and rollback configurations validated; no change applied.')
        return
    if JOURNAL.exists():
        raise RuntimeError('Existing delegation journal requires review')
    backup = json.loads((RUNTIME / 'docker-backup-result.json').read_text())
    archive = Path(backup['archive'])
    if not backup.get('openclaw_native_verify') or not archive.exists() or time.time() - archive.stat().st_mtime > 86400:
        raise RuntimeError('A verified recovery point less than 24 hours old is required')
    if current_config() != before:
        raise RuntimeError('Configuration changed during validation; retry after review')
    instructions = json.loads(run('node', '-e',
        'const fs=require("fs");console.log(JSON.stringify(Object.fromEntries(["asia","developpement","recherche"].map(a=>[a,fs.readFileSync("/home/node/.openclaw/workspaces/"+a+"/AGENTS.md","utf8")]))));'))
    journal = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'applying',
               'rollback': rollback_patch(before), 'instructions': instructions}
    JOURNAL.write_text(json.dumps(journal))
    try:
        write_instructions({a: (ROOT / 'infra/agents' / a / 'AGENTS.md').read_text(encoding='utf-8') for a in instructions})
        cli_patch(patch)
        run('node', 'dist/index.js', 'config', 'validate')
        after = current_config()
        if after.get('channels') != before.get('channels') or after.get('bindings') != before.get('bindings'):
            raise RuntimeError('Telegram settings changed unexpectedly')
        journal['status'] = 'active'
        JOURNAL.write_text(json.dumps(journal))
        print('Asia delegation enabled. Specialist cross-messaging and recursive delegation denied. Live tests required.')
    except Exception:
        restore(journal)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Delegation configuration failed: ' +
              (str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__))
        sys.exit(1)
