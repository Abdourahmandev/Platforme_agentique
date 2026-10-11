"""Controlled legacy handoff. Default is a non-mutating preflight.

--activate requires the Windows pause marker, stopped legacy processes and a
free supervisor lock. It centralizes the existing OpenCode consumer and the
OpenClaw agents on the same Docker LiteLLM budget. --rollback stops OpenClaw
before restoring the legacy consumer, carrying forward recorded expenditure.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ['LOCALAPPDATA'])
RUNTIME = LOCAL / 'AsiaDocker'
JOURNAL = RUNTIME / 'asia-handoff-private.json'
DOCKER = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
CONTAINER = 'asia-platform-staging-openclaw-1'
TEAM = 'asia-platform-staging'


def docker(*args, data=None, timeout=180):
    result = subprocess.run([DOCKER, *args], input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        (RUNTIME / 'asia-handoff-command-private.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError('Docker command failed; private diagnostic saved')
    return result.stdout


def cli(*args, data=None):
    return docker('exec', '-i', CONTAINER, 'node', 'dist/index.js', *args, data=data)


def current_config():
    return json.loads(docker('exec', CONTAINER, 'node', '-e',
                      'process.stdout.write(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"))'))


def patch_for(config, owner):
    if not str(owner).isdecimal() or int(owner) <= 0:
        raise ValueError('Invalid owner')
    channel = deepcopy(config['channels']['telegram'])
    if channel.get('accounts', {}).get('asia', {}).get('enabled'):
        raise ValueError('Asia is already enabled; refusing a repeated handoff')
    bindings = deepcopy(config.get('bindings', []))
    if any(b.get('agentId') == 'asia' or b.get('match', {}).get('accountId') == 'asia' for b in bindings):
        raise ValueError('Existing Asia route requires review')
    channel.setdefault('accounts', {})['asia'] = {
        'name': 'Asia', 'enabled': True,
        'tokenFile': '/home/node/.openclaw/credentials/telegram-asia.token',
        'dmPolicy': 'allowlist', 'allowFrom': [str(owner)], 'groupPolicy': 'disabled',
        'configWrites': False, 'joinIntro': False, 'mediaMaxMb': 20, 'streaming': {'mode': 'partial'},
        'execApprovals': {'enabled': True, 'approvers': [str(owner)], 'target': 'channel', 'agentFilter': ['asia']},
    }
    bindings.append({'type': 'route', 'agentId': 'asia', 'match': {'channel': 'telegram', 'accountId': 'asia'}})
    return {'channels': {'telegram': channel}, 'bindings': bindings}


def budget_cap(legacy):
    ceiling = float(legacy.get('max_budget') or 0)
    spent = float(legacy.get('spend') or 0)
    if ceiling <= 0 or ceiling > 20 or spent < 0 or spent >= ceiling:
        raise ValueError('Unexpected or exhausted legacy budget')
    # Team update does not accept spend. Keep the existing Docker ledger and
    # subtract legacy expenditure from the cap instead of resetting any spend.
    return round(ceiling - spent, 8)


def legacy_stopped():
    marker = LOCAL / 'OpenCodeTelegramSetup/migration-paused'
    runner = LOCAL / 'Programs/OpenCodeTelegram/run-bot.ps1'
    if not marker.exists() or 'Asia migration pause guard' not in runner.read_text(encoding='utf-8-sig'):
        return False
    # OpenProcess(QUERY_LIMITED_INFORMATION) works even for an elevated process.
    # An inaccessible or reused PID fails closed rather than proving absence.
    import ctypes
    runtime = json.loads((LOCAL / 'OpenCodeTelegramSetup/bot-runtime.json').read_text(encoding='utf-8-sig'))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    for field in ('SupervisorPID', 'BotPID'):
        handle = kernel.OpenProcess(0x1000, False, int(runtime[field]))
        if handle:
            kernel.CloseHandle(handle)
            return False
        if ctypes.get_last_error() != 87:  # ERROR_INVALID_PARAMETER: PID absent
            return False
    import msvcrt
    try:
        with (LOCAL / 'OpenCodeTelegramSetup/bot-supervisor.lock').open('a+b') as lock:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        return False
    return True


class Services:
    def __init__(self):
        self.private = json.loads((RUNTIME / 'runtime-private.json').read_text())
        self.legacy_key = (LOCAL / 'AsiaLiteLLM/agent.key').read_text().strip()
        self.masters = {'old': (LOCAL / 'AsiaLiteLLM/gateway.key').read_text().strip(), 'new': self.private['master_key']}
        self.code_auth = json.loads((LOCAL / 'OpenCodeWeb/server-secret.json').read_text())

    def api(self, target, path, payload=None, params=None):
        base = 'http://127.0.0.1:' + ('4000' if target == 'old' else '14000')
        try:
            response = requests.request('POST' if payload is not None else 'GET', base + path,
                      headers={'Authorization': 'Bearer ' + self.masters[target]}, json=payload, params=params, timeout=30)
            if not response.ok:
                raise RuntimeError(f'{target} {path}: HTTP {response.status_code}')
            return response.json()
        except requests.RequestException:
            raise RuntimeError('LiteLLM network operation failed') from None

    def code(self, path, patch=None):
        response = requests.request('PATCH' if patch is not None else 'GET', 'http://127.0.0.1:4096' + path,
                    auth=(self.code_auth['username'], self.code_auth['password']), json=patch, timeout=30)
        if not response.ok:
            raise RuntimeError(f'OpenCode {path}: HTTP {response.status_code}')
        return response.json()

    def key(self, target, key):
        return self.api(target, '/key/info', params={'key': key})['info']

    def team(self):
        return self.api('new', '/team/info', params={'team_id': TEAM})['team_info']


def rollback(services):
    if not JOURNAL.exists():
        raise RuntimeError('No handoff journal; refusing rollback against an unrelated state')
    journal = json.loads(JOURNAL.read_text())
    if journal.get('status') == 'rolled-back':
        raise RuntimeError('Rollback already completed')
    # Stopping the process is stronger than assuming that a hot reload worked.
    docker('stop', CONTAINER, timeout=390)
    team_spend = float(services.team().get('spend') or 0)
    old_spend = float(journal['legacy']['spend'] or 0)
    # Freeze Docker allowance before re-enabling the old allowance.
    services.api('new', '/team/update', {'team_id': TEAM, 'max_budget': max(team_spend, 0.00000001)})
    services.api('new', '/key/block', {'key': services.legacy_key})
    services.code('/global/config', {'provider': {'litellm': {'options': {'baseURL': journal['opencode_base']}}}})
    services.api('old', '/key/update', {'key': services.legacy_key, 'spend': old_spend + team_spend,
                                      'max_budget': journal['legacy']['max_budget']})
    services.api('old', '/key/unblock', {'key': services.legacy_key})
    # Remove the Asia binding while the container is stopped, using a temporary
    # compose process on the same persistent volume, with no network at all.
    # The regular service must remain stopped until this command succeeds.
    script = 'const fs=require("fs"),p="/state/openclaw.json",c=JSON.parse(fs.readFileSync(p));if(c.channels?.telegram?.accounts?.asia)c.channels.telegram.accounts.asia.enabled=false;c.bindings=(c.bindings||[]).filter(b=>b.match?.accountId!=="asia");fs.writeFileSync(p,JSON.stringify(c,null,2),{mode:0o600});'
    docker('run', '--rm', '--network', 'none', '--user', '1000:1000',
           '--mount', 'type=volume,src=asia-platform-staging_openclaw-state,dst=/state',
           '--entrypoint', 'node',
           'ghcr.io/openclaw/openclaw@sha256:97a692e91a99b514318dd43e7925dffdacfc7499f401f842912bf15ccbf083ff', '-e', script)
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(ROOT / 'infra/control-legacy-telegram.ps1'), '-Mode', 'Resume'],
                             capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Legacy restart failed; new consumer remains stopped')
    journal['status'] = 'rolled-back'
    JOURNAL.write_text(json.dumps(journal))
    services.private['phase'] = 'rollback-windows'
    (RUNTIME / 'runtime-private.json').write_text(json.dumps(services.private))
    print('Legacy bot restarted; OpenClaw stopped and its shared allowance frozen. Spending preserved.')


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--activate', action='store_true')
    action.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    services = Services()
    if args.rollback:
        rollback(services)
        return
    if JOURNAL.exists() or services.private.get('phase') != 'staging':
        raise RuntimeError('Existing handoff or non-staging runtime requires review')
    config = current_config()
    legacy_credentials = json.loads((LOCAL / 'OpenCodeTelegramSetup/bot-credentials.json').read_text(encoding='utf-8-sig'))
    token = (RUNTIME / 'secrets/asia.token').read_text().strip()
    if token != legacy_credentials['Token']:
        raise RuntimeError('Prepared Asia token differs from legacy identity')
    for method in ('getMe', 'getWebhookInfo'):
        try:
            response = requests.get('https://api.telegram.org/bot' + token + '/' + method, timeout=20)
            value = response.json()
            if not response.ok or not value.get('ok') or (method == 'getWebhookInfo' and value['result'].get('url')):
                raise RuntimeError('Telegram credential or webhook check failed')
        except requests.RequestException:
            raise RuntimeError('Telegram network validation failed') from None
    patch = patch_for(config, legacy_credentials['AllowedUserId'])
    raw = json.dumps(patch).encode()
    cli('config', 'patch', '--stdin', '--dry-run', '--json', data=raw)
    for report in ('asia-tools-test-result.json', 'mcp-transports-result.json', 'opencode-bridge-result.json'):
        report_path = RUNTIME / report
        if not report_path.exists() or not json.loads(report_path.read_text()).get('passed'):
            raise RuntimeError('Connector acceptance tests must pass first')
        if time.time() - report_path.stat().st_mtime > 24 * 3600:
            raise RuntimeError('Connector acceptance result is stale')
    legacy = services.key('old', services.legacy_key)
    if legacy.get('blocked'):
        raise RuntimeError('Legacy production key is already blocked; review its ownership first')
    cap = budget_cap(legacy)
    team = services.team()
    if float(team.get('spend') or 0) >= cap:
        raise RuntimeError('Combined budget already exhausted')
    imported = services.key('new', services.legacy_key)
    if not imported.get('blocked'):
        raise RuntimeError('Imported legacy key must still be quarantined')
    code = services.code('/global/config')
    old_base = code['provider']['litellm']['options']['baseURL']
    if old_base != 'http://127.0.0.1:4000/v1':
        raise RuntimeError('Unexpected legacy model endpoint')
    stopped = legacy_stopped()
    plan = {'asia_token_reused': True, 'developer_preserved': True, 'legacy_stopped': stopped,
            'docker_shared_cap_usd': cap, 'legacy_spend_preserved_usd': legacy['spend'],
            'opencode_destination': 'http://127.0.0.1:14000/v1', 'new_consumer_started': False}
    (RUNTIME / 'asia-handoff-plan.json').write_text(json.dumps(plan, indent=2))
    if not args.activate:
        print(json.dumps(plan))
        return
    if not stopped:
        raise RuntimeError('Stop the legacy supervisor with control-legacy-telegram.ps1 -Mode Pause first')
    if services.code('/session/status'):
        raise RuntimeError('OpenCode still has running tasks; wait for them before switching its provider')
    backup = json.loads((RUNTIME / 'docker-backup-result.json').read_text())
    if not backup.get('openclaw_native_verify') or not Path(backup['archive']).exists():
        raise RuntimeError('Verified recovery archive required')
    if time.time() - Path(backup['archive']).stat().st_mtime > 24 * 3600:
        raise RuntimeError('Recovery archive is older than 24 hours')
    journal = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'applying',
               'legacy': legacy, 'team': team, 'opencode_base': old_base, 'openclaw_before': config}
    JOURNAL.write_text(json.dumps(journal))
    try:
        services.api('old', '/key/block', {'key': services.legacy_key})
        services.api('new', '/team/update', {'team_id': TEAM, 'team_alias': 'Asia Platform', 'max_budget': cap})
        services.api('new', '/key/update', {'key': services.legacy_key, 'team_id': TEAM,
                                         'max_budget': 20, 'spend': legacy['spend']})
        services.api('new', '/key/unblock', {'key': services.legacy_key})
        for key in services.private['agent_keys'].values():
            services.api('new', '/key/update', {'key': key, 'max_budget': 20})
        services.code('/global/config', {'provider': {'litellm': {'options': {'baseURL': plan['opencode_destination']}}}})
        if services.code('/global/config')['provider']['litellm']['options']['baseURL'] != plan['opencode_destination']:
            raise RuntimeError('OpenCode provider change was not persisted')
        response = requests.get('http://127.0.0.1:14000/v1/models',
                                headers={'Authorization': 'Bearer ' + services.legacy_key}, timeout=20)
        if not response.ok or len(response.json().get('data', [])) != 34:
            raise RuntimeError('Transferred OpenCode key cannot access the model catalogue')
        docker('exec', '-i', CONTAINER, 'node', '-e',
               'require("fs").writeFileSync("/home/node/.openclaw/credentials/telegram-asia.token",require("fs").readFileSync(0),{mode:0o600})', data=token.encode())
        if not legacy_stopped():
            raise RuntimeError('Legacy ownership changed during handoff')
        cli('config', 'patch', '--stdin', data=raw)
        deadline = time.monotonic() + 90
        while True:
            status = json.loads(cli('channels', 'status', '--probe', '--channel', 'telegram', '--json'))
            rows = status.get('channelAccounts', {}).get('telegram', [])
            asia = next((r for r in rows if r.get('accountId') == 'asia'), {})
            developer = next((r for r in rows if r.get('accountId') == 'developpement'), {})
            if all(r.get('running') and r.get('probe', {}).get('ok') and not r.get('lastError') for r in (asia, developer)):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Telegram health verification failed')
            time.sleep(3)
        response = requests.post('http://127.0.0.1:18789/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + services.private['gateway_token'], 'x-openclaw-agent-id': 'asia'},
                    json={'model': 'openclaw', 'user': 'asia-handoff-check-' + str(time.time_ns()),
                          'messages': [{'role': 'user', 'content': 'Test technique : reponds uniquement ASIA_PRETE, sans outil.'}]}, timeout=190)
        if not response.ok or 'ASIA_PRETE' not in response.json().get('choices', [{}])[0].get('message', {}).get('content', ''):
            raise RuntimeError('Post-handoff Asia inference failed')
        journal['status'] = 'active'
        JOURNAL.write_text(json.dumps(journal))
        services.private['phase'] = 'asia-pilot'
        (RUNTIME / 'runtime-private.json').write_text(json.dumps(services.private))
        print('Asia and Developer connected. OpenCode and OpenClaw now share Docker LiteLLM accounting. Owner Telegram tests still required.')
    except Exception:
        rollback(services)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Request exceptions can contain a credential-bearing URL; no traceback.
        print('Handoff did not complete: ' + (str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__))
        sys.exit(1)
