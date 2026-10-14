"""Append each atelier agent's role to its Paperclip-managed instructions (AGENTS.md).

Paperclip seeds a default execution contract in the entry file; it is kept as is.
The role from infra/agents/<slug>/PAPERCLIP.md goes between markers, so a rerun
replaces only that section. An agent without a managed entry starts from the
default contract of another atelier agent. Never prints secrets.
"""
import json
import os
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'AsiaPaperclip'
API = 'http://127.0.0.1:3100/api'
BEGIN, END = '<!-- decidata-role:begin -->', '<!-- decidata-role:end -->'
ROLES = {'developpement': 'infra/agents/developpement/PAPERCLIP.md', 'maryam': 'infra/agents/maryam/PAPERCLIP.md'}


def main():
    state = json.loads((PRIVATE / 'deployment.json').read_text())
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + json.loads((PRIVATE / 'board-token.json').read_text())['token']

    def entry(agent_id):
        r = session.get(f'{API}/agents/{agent_id}/instructions-bundle/file', params={'path': 'AGENTS.md'}, timeout=30)
        return r.json() if r.ok else None

    current = {slug: entry(state['agents'][slug]['id']) for slug in ROLES}
    defaults = [c['content'].split(BEGIN)[0].rstrip() for c in current.values() if c and c.get('content')]
    for slug, path in ROLES.items():
        existing = current[slug]
        base = existing['content'].split(BEGIN)[0].rstrip() if existing and existing.get('content') else defaults[0]
        role = (ROOT / path).read_text(encoding='utf-8').strip()
        content = f'{base}\n\n{BEGIN}\n{role}\n{END}\n'
        revision = (existing or {}).get('revision') or {}
        body = {'path': 'AGENTS.md', 'content': content,
                'baseRevisionId': revision.get('id') if isinstance(revision, dict) else revision}
        r = session.put(f"{API}/agents/{state['agents'][slug]['id']}/instructions-bundle/file", json=body, timeout=30)
        if not r.ok:
            raise SystemExit(f'{slug}: HTTP {r.status_code} {r.text[:300]}')
        print(f'{slug}: instructions de role deployees ({len(content)} caracteres)')


if __name__ == '__main__':
    main()
