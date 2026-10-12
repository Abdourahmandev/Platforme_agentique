"""Grant the coordinator read tools so native children can inherit them.

Requires the existing Souleiman connectors. No credential or session-store edits.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fnmatch
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('connectors', ROOT / 'infra/configure-souleiman-connectors.py')
connectors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connectors)
JOURNAL = connectors.PRIVATE / 'github-delegation-private.json'
SECTION = '\n## Acces GitHub en delegation\n'
GITHUB_READ = [
    'get_file_contents', 'get_commit', 'list_commits', 'list_branches',
    'list_issues', 'issue_read', 'list_pull_requests', 'pull_request_read',
    'actions_list', 'actions_get', 'get_job_logs',
]
CONTEXT_READ = ['resolve-library-id', 'query-docs']
READ_TOOLS = ['github__' + name for name in GITHUB_READ] + ['context7__' + name for name in CONTEXT_READ]
WRITE_TOOLS = ['github__issue_write', 'github__create_pull_request', 'github__update_pull_request']


def patch_for(current):
    servers = current.get('mcp', {}).get('servers', {})
    for server, names in [('github', GITHUB_READ), ('context7', CONTEXT_READ)]:
        exposed = servers.get(server, {}).get('toolFilter', {}).get('include', [])
        if not set(names).issubset(exposed):
            raise ValueError('Install and verify Souleiman connectors first')
    policy = current['agents']['entries']['asia']['tools']
    if any(fnmatch.fnmatchcase(name, pattern) for name in READ_TOOLS for pattern in policy.get('deny', [])):
        raise ValueError('A read tool is explicitly denied; reconcile policy before applying')
    if any(fnmatch.fnmatchcase(name, pattern) for name in WRITE_TOOLS for pattern in policy.get('allow', [])):
        raise ValueError('Asia already has a GitHub write grant; reconcile before applying')
    return {'agents': {'entries': {'asia': {'tools': {
        'allow': list(dict.fromkeys(policy.get('allow', []) + READ_TOOLS)),
    }}}}}


def append_section(current, source):
    section = SECTION + source.split(SECTION, 1)[1]
    if SECTION in current:
        if current.split(SECTION, 1)[1].strip() != section.split(SECTION, 1)[1].strip():
            raise RuntimeError('Existing delegation instructions differ; reconcile first')
        return current
    return current.rstrip() + '\n' + section


def save(journal):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    temp = JOURNAL.with_suffix('.tmp')
    temp.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(JOURNAL)


def preflight(journal, current, instructions):
    restore = connectors.restore_patch(current, journal['config_before'], journal['patch'])
    for agent, item in journal['instructions'].items():
        if instructions[agent] not in (item['before'], item['target']):
            raise RuntimeError('Instruction drift: inspect private journal before continuing')
    return restore


def deploy(journal, rollback=False):
    connectors.wait_healthy()
    actual = {agent: connectors.read_text(item['path']) for agent, item in journal['instructions'].items()}
    restore = preflight(journal, connectors.remote_json(connectors.CONFIG), actual)
    patch = restore if rollback else journal['patch']
    for dry in [True, False]:
        connectors.docker('exec', '-i', connectors.GATEWAY, 'node', 'dist/index.js',
                          'config', 'patch', '--stdin', *(['--dry-run', '--json'] if dry else []),
                          data=json.dumps(patch).encode(), timeout=90)
    for item in journal['instructions'].values():
        connectors.remote_write(item['path'], item['before' if rollback else 'target'])
    connectors.docker('exec', connectors.GATEWAY, 'node', 'dist/index.js', 'config', 'validate', timeout=90)
    journal['phase'] = 'rolled-back' if rollback else 'deployed'
    save(journal)
    print('Delegation settings restored.' if rollback else 'Read-only connector delegation configured; live test required.')


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    for option in ['apply', 'resume', 'rollback']:
        group.add_argument('--' + option, action='store_true')
    args = parser.parse_args()
    if os.environ.get('ASIA_TRAINING_CYCLE'):
        raise RuntimeError('Use the production runtime')
    if args.resume or args.rollback:
        journal = json.loads(JOURNAL.read_text(encoding='utf-8'))
        if args.rollback and journal['phase'] == 'rolled-back':
            print('Already rolled back.'); return
        if args.resume and journal['phase'] != 'prepared':
            raise RuntimeError('Only a prepared deployment can be resumed')
        deploy(journal, rollback=args.rollback); return
    if JOURNAL.exists():
        raise RuntimeError('Deployment journal exists; inspect it instead of replaying')
    current = connectors.remote_json(connectors.CONFIG)
    patch = patch_for(current)
    instructions = {}
    for agent in ['asia', 'developpement']:
        filename = connectors.BASE + '/workspaces/' + agent + '/AGENTS.md'
        before = connectors.read_text(filename)
        source = (ROOT / 'infra/agents' / agent / 'AGENTS.md').read_text(encoding='utf-8')
        instructions[agent] = {'path': filename, 'before': before, 'target': append_section(before, source)}
    connectors.docker('exec', '-i', connectors.GATEWAY, 'node', 'dist/index.js', 'config', 'patch',
                      '--stdin', '--dry-run', '--json', data=json.dumps(patch).encode(), timeout=90)
    if not args.apply:
        print('Delegation schema validated; runtime unchanged.'); return
    journal = {'at': datetime.now(timezone.utc).isoformat(), 'phase': 'prepared',
               'config_before': deepcopy(current), 'patch': patch, 'instructions': instructions}
    save(journal)
    deploy(journal)


if __name__ == '__main__':
    main()
