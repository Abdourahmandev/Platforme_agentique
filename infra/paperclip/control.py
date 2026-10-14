"""Local operator client. Credentials and API diagnostics stay outside Git."""
import json
import os
from pathlib import Path
import subprocess
import requests

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = Path(os.environ['LOCALAPPDATA']) / 'AsiaPaperclip'
DOCKER = (r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker')
BASE = os.environ.get('ASIA_PAPERCLIP_URL', 'https://desktop-ep5nvk0.taild656dc.ts.net:10443')


def read(name):
    return json.loads((PRIVATE / name).read_text(encoding='utf-8'))


def save(name, value):
    target = PRIVATE / name
    temp = target.with_suffix(target.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)


def docker(*args, data=None, timeout=120):
    result = subprocess.run([DOCKER, *args], input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        (PRIVATE / 'docker-error.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError('Docker operation failed; diagnostic saved privately')
    return result.stdout


class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers['Origin'] = BASE

    def request(self, method, route, data=None):
        response = self.session.request(method, BASE + '/api' + route, json=data, timeout=45)
        if not response.ok:
            (PRIVATE / 'api-error.log').write_text(response.text, encoding='utf-8')
            raise RuntimeError(f'Paperclip {method} {route}: HTTP {response.status_code}; diagnostic saved privately')
        return response.json() if response.content else None

    def login(self):
        creds = read('owner-login.json')
        self.request('POST', '/auth/sign-in/email', {'email':creds['email'], 'password':creds['password']})
        return self
