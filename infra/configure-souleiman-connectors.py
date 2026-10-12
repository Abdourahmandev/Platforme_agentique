"""Configure official Context7/GitHub MCP endpoints for Souleiman only.

Credentials and rollback images stay in the existing private runtime directory.
No repository or Telegram messages are written by this installer.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'infra/training'))
from common import BASE, GATEWAY, PRIVATE, DOCKER, docker, node, remote_json, remote_write

JOURNAL = PRIVATE / 'souleiman-connectors-private.json'
ENV_FILE = PRIVATE / 'openclaw.env'
CONFIG = BASE + '/openclaw.json'
INSTRUCTIONS = BASE + '/workspaces/developpement/AGENTS.md'
ENV_NAME = 'SOULEIMAN_GITHUB_TOKEN'
TOOLS = ['context7__*', 'github__*']
GITHUB_TOOLS = [
    'get_file_contents', 'get_commit', 'list_commits', 'list_branches',
    'list_issues', 'issue_read', 'issue_write',
    'list_pull_requests', 'pull_request_read', 'create_pull_request', 'update_pull_request',
    'actions_list', 'actions_get', 'get_job_logs',
]
SECTION = '\n## Documentation et GitHub\n'


def patch_for(current):
    if 'developpement' not in current.get('agents', {}).get('entries', {}):
        raise ValueError('Souleiman is missing')
    policy = deepcopy(current['agents']['entries']['developpement'].get('tools', {}))
    policy['allow'] = list(dict.fromkeys(policy.get('allow', []) + TOOLS))
    policy['deny'] = [name for name in policy.get('deny', []) if name not in TOOLS]
    return {
        'tools': {'allow': list(dict.fromkeys(current['tools']['allow'] + TOOLS))},
        'agents': {'entries': {'developpement': {'tools': policy}}},
        'mcp': {'servers': {
            'context7': {
                'url': 'https://mcp.context7.com/mcp', 'transport': 'streamable-http',
                'connectionTimeoutMs': 20000, 'requestTimeoutMs': 45000,
                'toolFilter': {'include': ['resolve-library-id', 'query-docs']},
            },
            'github': {
                'url': 'https://api.githubcopilot.com/mcp/', 'transport': 'streamable-http',
                'headers': {'Authorization': 'Bearer ${' + ENV_NAME + '}',
                            'X-MCP-Toolsets': 'repos,issues,pull_requests,actions'},
                'connectionTimeoutMs': 20000, 'requestTimeoutMs': 45000,
                'toolFilter': {'include': GITHUB_TOOLS},
            },
        }},
    }


def github_token():
    # Use the existing normal Git authentication path; never print its output.
    result = subprocess.run(['git', '-c', 'credential.interactive=never', 'credential', 'fill'],
                            input=b'protocol=https\nhost=github.com\n\n', capture_output=True,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}, timeout=25)
    values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
    token = values.get('password', '')
    if result.returncode or not re.fullmatch(r'[A-Za-z0-9_]+', token):
        raise RuntimeError('GitHub authentication unavailable; connect Git on this PC first')
    return token


def save(journal):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    temporary = JOURNAL.with_suffix('.tmp')
    temporary.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(JOURNAL)


def read_text(filename):
    return node('process.stdout.write(require("fs").readFileSync(JSON.parse(require("fs").readFileSync(0))))', filename).decode()


def recreate():
    result = subprocess.run([DOCKER, 'compose', '-f', str(ROOT / 'infra/compose.yaml'),
                             'up', '-d', '--no-deps', 'openclaw'], capture_output=True,
                            env={**os.environ, 'ASIA_RUNTIME_DIR': PRIVATE.as_posix()}, timeout=420)
    if result.returncode:
        (PRIVATE / 'souleiman-connectors-error-private.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError('OpenClaw recreation failed; private diagnostic saved')
    wait_healthy()


def wait_healthy():
    # Startup can perform offline SQLite maintenance; config CLI writes must wait.
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        # /readyz checks gateway readiness directly; the bundled Docker probe
        # starts a separate CLI whose import can exceed its 5-second timeout.
        try:
            with urlopen('http://127.0.0.1:18789/readyz', timeout=5) as response:
                if response.status == 200 and json.load(response).get('ready') is True:
                    return
        except (URLError, TimeoutError, ValueError):
            pass
        time.sleep(3)
    raise RuntimeError('OpenClaw startup timed out; journal retained for resume or rollback')


def finish(journal):
    wait_healthy()
    # A partial run may already have applied the patch. Refuse conflicting changes.
    restore_patch(remote_json(CONFIG), journal['config_before'], journal['patch'])
    if ENV_FILE.read_text(encoding='utf-8') != journal['env_target']:
        raise RuntimeError('Environment drift before resume')
    actual = read_text(INSTRUCTIONS)
    reconcile_startup_notes(journal, actual)
    if actual not in (journal['instructions_before'], journal['instructions_target']):
        raise RuntimeError('Instruction drift before resume')
    docker('exec', '-i', GATEWAY, 'node', 'dist/index.js', 'config', 'patch', '--stdin',
           data=json.dumps(journal['patch']).encode(), timeout=90)
    remote_write(INSTRUCTIONS, journal['instructions_target'])
    docker('exec', GATEWAY, 'node', 'dist/index.js', 'config', 'validate', timeout=90)
    journal['phase'] = 'deployed'; save(journal)
    print('Souleiman connectors configured. Live checks are still required.')


def reconcile_startup_notes(journal, actual):
    # OpenClaw 2026.10.1 migrates retired TOOLS.md into AGENTS.md at startup.
    # Preserve that append and make rollback retain it as well. Other edits conflict.
    before = journal['instructions_before']
    if actual.startswith(before) and actual[len(before):].lstrip().startswith('## Tools\n\n### Local notes (migrated from TOOLS.md)'):
        journal['instructions_before_startup'] = before
        journal['instructions_before'] = actual
        journal['instructions_target'] = actual.rstrip() + '\n' + SECTION + journal['instructions_target'].split(SECTION, 1)[1]
        save(journal)


def restore_patch(current, before, target):
    """Restore only touched paths. Preserve unrelated changes; reject conflicts."""
    def walk(now, old, new):
        result = {}
        for key, expected in new.items():
            previous = old.get(key)
            actual = now.get(key)
            if isinstance(expected, dict) and isinstance(previous, dict):
                result[key] = walk(actual or {}, previous, expected)
            else:
                if actual not in (expected, previous):
                    raise RuntimeError('Configuration drift: inspect private journal before rollback')
                result[key] = previous
        return result
    return walk(current, before, target)


def rollback():
    journal = json.loads(JOURNAL.read_text(encoding='utf-8'))
    if journal['phase'] == 'rolled-back':
        print('Already rolled back.'); return
    wait_healthy()
    current = remote_json(CONFIG)
    patch = restore_patch(current, journal['config_before'], journal['patch'])
    actual_instructions = read_text(INSTRUCTIONS)
    actual_env = ENV_FILE.read_text(encoding='utf-8')
    if actual_instructions not in (journal['instructions_before'], journal['instructions_target']):
        raise RuntimeError('Instruction drift: inspect private journal before rollback')
    if actual_env not in (journal['env_before'], journal['env_target']):
        raise RuntimeError('Environment drift: inspect private journal before rollback')
    docker('exec', '-i', GATEWAY, 'node', 'dist/index.js', 'config', 'patch', '--stdin',
           data=json.dumps(patch).encode(), timeout=90)
    remote_write(INSTRUCTIONS, journal['instructions_before'])
    ENV_FILE.write_text(journal['env_before'], encoding='utf-8')
    recreate()
    journal['phase'] = 'rolled-back'; save(journal)
    print('Connector settings restored; conversations, tickets and budgets retained.')


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--rollback', action='store_true')
    group.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if os.environ.get('ASIA_TRAINING_CYCLE'):
        raise RuntimeError('Use the production runtime')
    if args.rollback:
        rollback(); return
    if args.resume:
        journal = json.loads(JOURNAL.read_text(encoding='utf-8'))
        if journal['phase'] != 'environment-written':
            raise RuntimeError('Only an environment-written deployment can be resumed')
        finish(journal); return
    if JOURNAL.exists():
        raise RuntimeError('Deployment journal exists; inspect it instead of replaying')
    current = remote_json(CONFIG)
    if any(name in current.get('mcp', {}).get('servers', {}) for name in ('context7', 'github')):
        raise RuntimeError('An existing connector must be reconciled before installation')
    env_before = ENV_FILE.read_text(encoding='utf-8')
    if re.search(r'^' + ENV_NAME + '=', env_before, re.M):
        raise RuntimeError('Existing GitHub environment binding must be reconciled')
    patch = patch_for(current)
    # Supply the already-authenticated value only through stdin for validation.
    token = github_token()
    validation = deepcopy(patch)
    validation['mcp']['servers']['github']['headers']['Authorization'] = 'Bearer ' + token
    docker('exec', '-i', GATEWAY, 'node', 'dist/index.js', 'config', 'patch', '--stdin', '--dry-run', '--json',
           data=json.dumps(validation).encode(), timeout=90)
    if not args.apply:
        print('Connector schema validated; runtime unchanged.'); return
    instructions_before = read_text(INSTRUCTIONS)
    if SECTION in instructions_before:
        raise RuntimeError('Connector instructions already present')
    source = (ROOT / 'infra/agents/developpement/AGENTS.md').read_text(encoding='utf-8')
    if SECTION not in source:
        raise RuntimeError('Connector instructions missing in repository')
    instructions_target = instructions_before.rstrip() + '\n' + SECTION + source.split(SECTION, 1)[1]
    env_target = env_before.rstrip() + '\n' + ENV_NAME + '=' + token + '\n'
    journal = {'at': datetime.now(timezone.utc).isoformat(), 'phase': 'prepared',
               'config_before': current, 'patch': patch, 'env_before': env_before, 'env_target': env_target,
               'instructions_before': instructions_before, 'instructions_target': instructions_target}
    save(journal)
    ENV_FILE.write_text(env_target, encoding='utf-8')
    journal['phase'] = 'environment-written'; save(journal)
    # A graceful recreation loads Compose's new environment without changing image or volume.
    recreate()
    finish(journal)


if __name__ == '__main__':
    main()
