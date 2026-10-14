"""Provision Paperclip for the three OpenClaw agents on a fresh install; never print secrets.

Uses a board API token approved by the owner in the browser (board-token.json).
Creates, once each: the project, a dedicated Ed25519 Gateway device, the three
openclaw_gateway agents (on demand only, 1 concurrent run, 12 runs/day) and their
API keys. Writes the private files expected by install-plugin.py. Re-running
resumes from deployment.json and never recreates an existing agent or key.
Usage: provision-linux.py "<company name>"
"""
import json
import os
from pathlib import Path
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import requests

ROOT = Path(__file__).resolve().parents[2]
LOCAL = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share')
PRIVATE = LOCAL / 'AsiaPaperclip'
RUNTIME = LOCAL / 'AsiaDocker'
API = 'http://127.0.0.1:3100/api'
PROJECT = 'Plateforme agentique'
ROLES = {'asia': 'ceo', 'developpement': 'engineer', 'recherche': 'researcher'}
HEARTBEAT = {'enabled': False, 'intervalSec': 0, 'wakeOnDemand': True, 'maxConcurrentRuns': 1, 'maxDailyRuns': 12}


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
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers['Authorization'] = 'Bearer ' + token

    def call(self, method, route, data=None):
        r = self.session.request(method, API + route, json=data, timeout=45)
        if not r.ok:
            (PRIVATE / 'api-error.log').write_text(r.text, encoding='utf-8')
            raise RuntimeError(f'Paperclip {method} {route}: HTTP {r.status_code}; diagnostic saved privately')
        return r.json() if r.content else None


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    board_token = read('board-token.json')
    board = Board(board_token['token'])
    state = read('deployment.json', {'agents': {}, 'public_url': None})
    env = dict(line.split('=', 1) for line in (PRIVATE / 'paperclip.env').read_text().splitlines() if '=' in line)
    state['public_url'] = env['PAPERCLIP_PUBLIC_URL'].strip("'")

    company = next((c for c in board.call('GET', '/companies') if c['name'] == sys.argv[1]), None)
    if not company:
        raise SystemExit('Company not found: ' + sys.argv[1])
    save('company.json', {'id': company['id'], 'name': company['name'], 'issuePrefix': company['issuePrefix']})
    save('owner.json', {'userId': board_token['userId']})

    project = read('project.json') or next(
        (p for p in board.call('GET', f"/companies/{company['id']}/projects") if p['name'] == PROJECT), None)
    if not project:
        project = board.call('POST', f"/companies/{company['id']}/projects", {
            'name': PROJECT, 'idempotencyKey': 'asia-platform-project',
            'description': 'Taches suivies pour Asia, Souleiman et Saredo.'})
    save('project.json', {'id': project['id'], 'name': project['name']})

    device = read('gateway-device.json')
    if not device:
        pem = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        device = {'devicePrivateKeyPem': pem}
        save('gateway-device.json', device)

    gateway_token = json.loads((RUNTIME / 'runtime-private.json').read_text())['gateway_token']
    catalogue = json.loads((ROOT / 'infra/agents/catalogue.json').read_text(encoding='utf-8'))
    existing = {a['name']: a for a in board.call('GET', f"/companies/{company['id']}/agents")}
    for name in ('asia', 'developpement', 'recherche'):  # Asia first: specialists report to her
        if name not in state['agents']:
            display = catalogue[name]['name']
            if display in existing:
                raise RuntimeError(f'Agent {display} exists but is not in deployment.json; review before continuing')
            agent = board.call('POST', f"/companies/{company['id']}/agents", {
                'name': display, 'role': ROLES[name], 'title': display,
                'reportsTo': None if name == 'asia' else state['agents']['asia']['id'],
                'capabilities': 'Agent OpenClaw ' + name,
                'adapterType': 'openclaw_gateway',
                'adapterConfig': {
                    'url': 'ws://openclaw:18789', 'authToken': gateway_token, 'agentId': name,
                    'sessionKeyStrategy': 'issue', 'role': 'operator', 'scopes': ['operator.read', 'operator.write'],
                    'disableDeviceAuth': False, 'devicePrivateKeyPem': device['devicePrivateKeyPem'],
                    'autoPairOnFirstConnect': False, 'timeoutSec': 240, 'paperclipApiUrl': 'http://paperclip:3100'},
                'runtimeConfig': {'heartbeat': HEARTBEAT},
                'permissions': {'canCreateAgents': False, 'canCreateSkills': False},
                'metadata': {'openclawAgentId': name}})
            state['agents'][name] = {'id': agent['id']}
            save('deployment.json', state)
        if not read(f'key-{name}.json'):
            key = board.call('POST', f"/agents/{state['agents'][name]['id']}/keys", {'name': 'asia-ticket-plugin'})
            save(f'key-{name}.json', {'id': key.get('id'), 'token': key['token']})
    save('deployment.json', state)
    print(json.dumps({'company': company['issuePrefix'], 'project': project['name'],
                      'agents': {n: v['id'] for n, v in state['agents'].items()}}))


if __name__ == '__main__':
    main()
