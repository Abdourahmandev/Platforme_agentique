"""Add a specialist's Telegram bot to a live Gateway, preserving other accounts.

Tokens must already exist under the private runtime/secrets directory. Default
is a validated dry run; --activate adds the consumer. Asia uses its separate
legacy handoff procedure. No Telegram messages or getUpdates requests are sent.
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

spec = importlib.util.spec_from_file_location('telegram_setup', Path(__file__).with_name('configure-telegram.py'))
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
RUNTIME = setup.RUNTIME


def current_config():
    return json.loads(setup.run(['node', '-e',
        'process.stdout.write(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"))']))


def patch_for(config, agent, owner):
    if agent not in ('developpement', 'recherche'):
        raise ValueError('Only specialist accounts can be added; Asia requires its handoff')
    if not str(owner).isdecimal() or int(owner) <= 0:
        raise ValueError('Invalid owner')
    if agent not in config.get('agents', {}).get('entries', {}):
        raise ValueError('Agent must be configured first')
    channel = config.get('channels', {}).get('telegram', {})
    if not channel.get('enabled'):
        raise ValueError('Use the staging initializer for the first Telegram account')
    if agent in channel.get('accounts', {}):
        raise ValueError('Existing account requires review; refusing overwrite')
    bindings = deepcopy(config.get('bindings', []))
    if any(b.get('agentId') == agent or b.get('match', {}).get('accountId') == agent for b in bindings):
        raise ValueError('Existing agent binding requires review')
    account = {'name': setup.NAMES[agent], 'enabled': True,
        'tokenFile': '/home/node/.openclaw/credentials/telegram-' + agent + '.token',
        'dmPolicy': 'allowlist', 'allowFrom': [str(owner)], 'groupPolicy': 'disabled',
        'configWrites': False, 'joinIntro': False, 'mediaMaxMb': 20,
        'streaming': {'mode': 'partial'}}
    bindings.append({'type': 'route', 'agentId': agent,
                     'match': {'channel': 'telegram', 'accountId': agent}})
    # config patch merges object fields; only the bindings array is replaced.
    return {'channels': {'telegram': {'accounts': {agent: account}}}, 'bindings': bindings}


def disable_patch(config, agent):
    return {'channels': {'telegram': {'accounts': {agent: {'enabled': False}}}},
            'bindings': [b for b in config.get('bindings', [])
                         if not (b.get('match', {}).get('channel') == 'telegram'
                                 and b.get('match', {}).get('accountId') == agent)]}


def apply_patch(patch, dry_run=False):
    args = ['node', 'dist/index.js', 'config', 'patch', '--stdin']
    if dry_run:
        args += ['--dry-run', '--json']
    return setup.run(args, json.dumps(patch).encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', required=True, choices=['developpement', 'recherche'])
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    state = json.loads((RUNTIME / 'runtime-private.json').read_text())
    if state.get('phase') not in ('staging', 'asia-pilot'):
        raise RuntimeError('Runtime is not available for activation')
    if state.get('phase') == 'asia-pilot':
        handoff = json.loads((RUNTIME / 'asia-handoff-private.json').read_text())
        if handoff.get('status') != 'active':
            raise RuntimeError('Incomplete Asia handoff requires review first')
    legacy = json.loads((Path(os.environ['LOCALAPPDATA']) /
                        'OpenCodeTelegramSetup/bot-credentials.json').read_text(encoding='utf-8-sig'))
    before = current_config()
    patch = patch_for(before, args.agent, legacy['AllowedUserId'])
    token = (RUNTIME / 'secrets' / (args.agent + '.token')).read_text().strip()
    bot = setup.telegram(token, 'getMe')
    if not bot.get('is_bot') or str(bot['id']) == legacy['Token'].split(':')[0]:
        raise RuntimeError('This identity cannot be used for a specialist')
    if setup.telegram(token, 'getWebhookInfo').get('url'):
        raise RuntimeError('Existing webhook requires ownership review')
    for existing in (RUNTIME / 'secrets').glob('*.token'):
        if existing.stem != args.agent and existing.read_text().strip().split(':')[0] == str(bot['id']):
            raise RuntimeError('This bot is already assigned to another agent')
    initial_status = json.loads(setup.cli('channels', 'status', '--probe', '--channel', 'telegram', '--json'))
    for row in initial_status.get('channelAccounts', {}).get('telegram', []):
        if str(row.get('probe', {}).get('bot', {}).get('id')) == str(bot['id']):
            raise RuntimeError('This bot is already running in the Gateway')
    apply_patch(patch, dry_run=True)
    if not args.activate:
        print(json.dumps({'validated': True, 'agent': args.agent, 'username': bot['username'], 'activated': False}))
        return
    journal_path = RUNTIME / ('telegram-add-' + args.agent + '-private.json')
    if journal_path.exists():
        raise RuntimeError('Previous activation journal requires review')
    if current_config() != before:
        raise RuntimeError('Gateway configuration changed during validation; retry after review')
    journal = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'applying', 'before': before}
    journal_path.write_text(json.dumps(journal))
    try:
        setup.run(['node', '-e',
            'const fs=require("fs"),v=JSON.parse(fs.readFileSync(0));'
            'fs.writeFileSync(v.path,v.token,{mode:0o600});'],
            json.dumps({'path': patch['channels']['telegram']['accounts'][args.agent]['tokenFile'], 'token': token}).encode())
        apply_patch(patch)
        expected = {a for a, c in before['channels']['telegram']['accounts'].items() if c.get('enabled', True)} | {args.agent}
        deadline = time.monotonic() + 150
        while True:
            status = json.loads(setup.cli('channels', 'status', '--probe', '--channel', 'telegram', '--json'))
            rows = {r['accountId']: r for r in status.get('channelAccounts', {}).get('telegram', [])}
            if all(rows.get(a, {}).get('running') and rows[a].get('probe', {}).get('ok')
                   and not rows[a].get('lastError') for a in expected):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Telegram account health check failed')
            time.sleep(3)
        after = current_config()
        if str(rows[args.agent].get('probe', {}).get('bot', {}).get('id')) != str(bot['id']):
            raise RuntimeError('Unexpected Telegram identity after activation')
        if after['channels']['telegram']['accounts'].get(args.agent) != patch['channels']['telegram']['accounts'][args.agent]:
            raise RuntimeError('Unexpected access policy for the added account')
        for account, value in before['channels']['telegram']['accounts'].items():
            if after['channels']['telegram']['accounts'].get(account) != value:
                raise RuntimeError('An existing account changed during activation')
        if after.get('bindings') != patch['bindings']:
            raise RuntimeError('Unexpected account binding after activation')
        journal['status'] = 'active'
        journal_path.write_text(json.dumps(journal))
        result = {'activated': True, 'agent': args.agent, 'username': bot['username'],
                  'healthy_accounts': sorted(expected), 'existing_accounts_preserved': True,
                  'checked_at': datetime.now(timezone.utc).isoformat()}
        (RUNTIME / ('telegram-' + args.agent + '-result.json')).write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    except Exception:
        # Only suspend the added consumer. Preserve existing bots and any
        # unrelated changes made since the initial snapshot.
        apply_patch(disable_patch(current_config(), args.agent))
        journal['status'] = 'disabled-after-error'
        journal_path.write_text(json.dumps(journal))
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Account activation did not complete: ' +
              (str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__))
        sys.exit(1)
