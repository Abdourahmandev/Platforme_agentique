"""Enable PR creation from an existing branch; keep shell approvals unchanged."""
import argparse
from datetime import datetime, timezone
import fnmatch
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('delegation', ROOT / 'infra/configure-github-delegation.py')
delegation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delegation)
connectors = delegation.connectors
JOURNAL = connectors.PRIVATE / 'github-publication-private.json'
TOOL = 'github__create_pull_request'
SECTION = '\n## Publication des PR\n'
REPLACEMENTS = {
    'asia': {
        'Tu ne disposes pas des outils GitHub de modification ; une mission deleguee ne peut pas obtenir plus de droits que toi.':
        'Tu peux aussi ouvrir une PR demandee avec github__create_pull_request sur une branche deja poussee. Les outils MCP de modification de fichiers, de modification des issues et de fusion ne sont pas exposes pour toi. Une mission deleguee ne peut pas obtenir plus de droits que toi.',
    },
    'developpement': {
        "Les outils issue_write, create_pull_request et update_pull_request restent disponibles uniquement dans ta conversation directe ; l'heritage des droits d'Asia ne les autorise pas dans une mission deleguee.":
        "Une nouvelle mission d'Asia peut aussi utiliser create_pull_request sur une branche deja poussee, si la publication est demandee. Les outils issue_write et update_pull_request restent reserves a ta conversation directe.",
    },
}


def patch_for(current):
    if 'create_pull_request' not in current.get('mcp', {}).get('servers', {}).get('github', {}).get('toolFilter', {}).get('include', []):
        raise ValueError('Existing GitHub connector does not expose PR creation')
    policy = current['agents']['entries']['asia']['tools']
    if any(fnmatch.fnmatchcase(TOOL, p) for p in policy.get('deny', [])):
        raise ValueError('PR creation is explicitly denied; reconcile before applying')
    return {'agents': {'entries': {'asia': {'tools': {
        'allow': list(dict.fromkeys(policy.get('allow', []) + [TOOL])),
    }}}}}


def instructions_for(agent, current, source):
    for old, new in REPLACEMENTS[agent].items():
        if current.count(old) == 1:
            current = current.replace(old, new)
        elif new not in current:
            raise RuntimeError('Instruction drift: expected delegation paragraph missing')
    section = SECTION + source.split(SECTION, 1)[1]
    if SECTION in current:
        if current.split(SECTION, 1)[1].strip() != section.split(SECTION, 1)[1].strip():
            raise RuntimeError('Publication instructions differ; reconcile before applying')
        return current
    return current.rstrip() + '\n' + section


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    for option in ['apply', 'resume', 'rollback']:
        group.add_argument('--' + option, action='store_true')
    args = parser.parse_args()
    if os.environ.get('ASIA_TRAINING_CYCLE'):
        raise RuntimeError('Use the production runtime')
    # Reuse the tested narrow-patch and instruction drift checks with a distinct journal.
    delegation.JOURNAL = JOURNAL
    if args.resume or args.rollback:
        journal = json.loads(JOURNAL.read_text(encoding='utf-8'))
        if args.rollback and journal['phase'] == 'rolled-back':
            print('Already rolled back.'); return
        if args.resume and journal['phase'] != 'prepared':
            raise RuntimeError('Only a prepared deployment can be resumed')
        delegation.deploy(journal, rollback=args.rollback); return
    if JOURNAL.exists():
        raise RuntimeError('Deployment journal exists; inspect it instead of replaying')
    current = connectors.remote_json(connectors.CONFIG)
    patch = patch_for(current)
    instructions = {}
    for agent in REPLACEMENTS:
        filename = connectors.BASE + '/workspaces/' + agent + '/AGENTS.md'
        before = connectors.read_text(filename)
        source = (ROOT / 'infra/agents' / agent / 'AGENTS.md').read_text(encoding='utf-8')
        instructions[agent] = {'path': filename, 'before': before, 'target': instructions_for(agent, before, source)}
    connectors.docker('exec', '-i', connectors.GATEWAY, 'node', 'dist/index.js', 'config', 'patch',
                      '--stdin', '--dry-run', '--json', data=json.dumps(patch).encode(), timeout=90)
    if not args.apply:
        print('PR publication schema validated; runtime unchanged.'); return
    journal = {'at': datetime.now(timezone.utc).isoformat(), 'phase': 'prepared',
               'config_before': current, 'patch': patch, 'instructions': instructions,
               'deployed_message': 'PR creation enabled; verify on an explicitly requested PR.'}
    delegation.save(journal)
    delegation.deploy(journal)


if __name__ == '__main__':
    main()
