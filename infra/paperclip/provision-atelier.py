"""Wire the atelier into Paperclip: secrets, SSH environment, Souleiman and Maryam.

Never prints secrets. Resumable: existing secrets, environment and agents are
reused (recorded in deployment.json). Requires board-token.json, the atelier
SSH key and LiteLLM keys under $LOCALAPPDATA/Atelier.
- Secrets (Paperclip-managed, encrypted): atelier SSH private key, one LiteLLM
  key per coding agent.
- Environment "Atelier": SSH to atelier:2222 as node, /work, pinned host key.
- Souleiman (developer) and Maryam (QA, new): opencode_local in the atelier,
  on demand only, 1 run at a time, 12 runs/day. Maryam reviews with Gemini,
  a different model family from Souleiman's DeepSeek.
"""
import json
import os
from pathlib import Path
import subprocess
import requests

LOCAL = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share')
PRIVATE = LOCAL / 'AsiaPaperclip'
ATELIER = LOCAL / 'Atelier'
API = 'http://127.0.0.1:3100/api'
# OpenCode in Paperclip runs uses a per-run config dir, so the LiteLLM provider is
# injected by the adapter from PAPERCLIP_OPENCODE_PROVIDERS ({env:...} resolved server-side).
PROVIDERS = json.dumps({'litellm': {
    'npm': '@ai-sdk/openai-compatible', 'name': 'LiteLLM (DeepSeek / Gemini)',
    'options': {'baseURL': 'http://litellm:4000/v1', 'apiKey': '{env:LITELLM_API_KEY}'},
    'models': {m: {'name': m} for m in ('asia-pro', 'asia-rapide', 'gemini-3.8-flash', 'gemini-3.1-pro-preview')}}})
HEARTBEAT = {'enabled': False, 'intervalSec': 0, 'wakeOnDemand': True, 'maxConcurrentRuns': 1, 'maxDailyRuns': 24}
AGENTS = {
    'developpement': {'name': 'Souleiman', 'role': 'engineer', 'model': 'litellm/asia-pro', 'key': 'souleiman',
                      # DeepSeek Pro is slow: a full lot (code + tests + PR) needs more than 20 minutes.
                      'timeoutSec': 2700},
    'maryam': {'name': 'Maryam', 'role': 'qa', 'model': 'litellm/gemini-3.8-flash', 'key': 'maryam'},
    # Paperclip refuses to resume a failed OpenClaw (legacy) run on a ticket; atelier runs can be retried.
    'recherche': {'name': 'Saredo', 'role': 'researcher', 'model': 'litellm/gemini-3.8-flash', 'key': 'saredo'},
}


def read(name, default=None):
    path = PRIVATE / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save(name, value):
    temp = PRIVATE / (name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    temp.replace(PRIVATE / name)


class Board:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers['Authorization'] = 'Bearer ' + read('board-token.json')['token']

    def call(self, method, route, data=None):
        r = self.s.request(method, API + route, json=data, timeout=60)
        if not r.ok:
            (PRIVATE / 'api-error.log').write_text(r.text, encoding='utf-8')
            raise RuntimeError(f'Paperclip {method} {route}: HTTP {r.status_code}; diagnostic saved privately')
        return r.json() if r.content else None


def host_key():
    out = subprocess.run(['docker', 'exec', 'asia-paperclip-paperclip-1', 'ssh-keyscan', '-t', 'ed25519',
                          '-p', '2222', 'atelier'], capture_output=True, text=True, timeout=30).stdout
    lines = [l for l in out.splitlines() if l.startswith('[atelier]:2222 ssh-ed25519 ')]
    if len(lines) != 1:
        raise RuntimeError('Cannot read the atelier SSH host key')
    return lines[0]


def main():
    board = Board()
    company = read('company.json')
    state = read('deployment.json')
    atelier = state.setdefault('atelier', {})
    secrets = atelier.setdefault('secrets', {})
    litellm = json.loads((ATELIER / 'litellm-keys.json').read_text())
    wanted = {'ATELIER_SSH_KEY': (ATELIER / 'paperclip_ed25519').read_text(),
              'LITELLM_KEY_SOULEIMAN': litellm['souleiman'], 'LITELLM_KEY_MARYAM': litellm['maryam'],
              'LITELLM_KEY_SAREDO': litellm['saredo']}
    existing = {s['name']: s['id'] for s in board.call('GET', f"/companies/{company['id']}/secrets")}
    for name, value in wanted.items():
        if name not in secrets:
            secrets[name] = existing.get(name) or board.call('POST', f"/companies/{company['id']}/secrets", {
                'name': name, 'value': value, 'description': 'Atelier (provision-atelier.py)'})['id']
            save('deployment.json', state)

    if 'environmentId' not in atelier:
        env = board.call('POST', f"/companies/{company['id']}/environments", {
            'name': 'Atelier', 'description': 'Conteneur SSH isole : Git, Node, Python, OpenCode via LiteLLM',
            'driver': 'ssh', 'config': {
                'host': 'atelier', 'port': 2222, 'username': 'node', 'remoteWorkspacePath': '/work',
                'privateKeySecretRef': {'type': 'secret_ref', 'secretId': secrets['ATELIER_SSH_KEY']},
                'knownHosts': host_key(), 'strictHostKeyChecking': True}})
        atelier['environmentId'] = env['id']
        save('deployment.json', state)

    for slug, spec in AGENTS.items():
        adapter = {'model': spec['model'], 'timeoutSec': spec.get('timeoutSec', 1200), 'graceSec': 30,
                   'env': {'LITELLM_API_KEY': {'type': 'secret_ref',
                                               'secretId': secrets['LITELLM_KEY_' + spec['key'].upper()]},
                           'PAPERCLIP_OPENCODE_PROVIDERS': {'type': 'plain', 'value': PROVIDERS}}}
        body = {'adapterType': 'opencode_local', 'adapterConfig': adapter,
                'defaultEnvironmentId': atelier['environmentId'], 'runtimeConfig': {'heartbeat': HEARTBEAT}}
        if slug in state['agents']:  # existing agent: (re)apply the atelier adapter settings
            board.call('PATCH', f"/agents/{state['agents'][slug]['id']}", body)
            state['agents'][slug]['atelier'] = True
        else:
            agent = board.call('POST', f"/companies/{company['id']}/agents", dict(body, **{
                'name': spec['name'], 'role': spec['role'], 'title': 'QA / relectrice',
                'reportsTo': state['agents']['asia']['id'], 'capabilities': 'Relecture de PR et tests',
                'permissions': {'canCreateAgents': False, 'canCreateSkills': False},
                'metadata': {'environment': 'atelier'}}))
            state['agents'][slug] = {'id': agent['id'], 'atelier': True}
        save('deployment.json', state)
    print(json.dumps({'environment': atelier['environmentId'],
                      'agents': {k: v['id'] for k, v in state['agents'].items()}}))


if __name__ == '__main__':
    main()
