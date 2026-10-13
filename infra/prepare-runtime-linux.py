"""Prepare a fresh Linux runtime (no Windows source to migrate); never print secrets.

Same layout as prepare-runtime.py, but every credential is generated here.
Provider keys start as placeholders: fill DEEPSEEK_API_KEY and GEMINI_API_KEY in
litellm.env, then recreate the litellm container. Telegram is not enabled.
"""
import json
import os
from pathlib import Path
import secrets
from urllib.parse import quote

PLACEHOLDER = 'A_REMPLIR'


def dotenv(values):
    # Compose dotenv single quoting preserves literal dollars in credentials.
    for value in values.values():
        if any(c in value for c in "\r\n'\\"):
            raise ValueError('Unsupported character in secret; refusing ambiguous dotenv encoding')
    return ''.join(f"{name}='{value}'\n" for name, value in values.items())


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)


def main():
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share')
    root = local / 'AsiaDocker'
    if (root / 'litellm.env').exists() or (root / 'runtime-private.json').exists():
        raise SystemExit('Runtime already initialized; refusing to replace credentials.')
    old = os.umask(0o077)
    try:
        (root / 'secrets').mkdir(parents=True, exist_ok=True)
        (root / 'openclaw').mkdir(exist_ok=True)
        root.chmod(0o700)
        password = secrets.token_hex(24)
        gateway_token = secrets.token_hex(32)
        speech_key = 'sk-local-' + secrets.token_hex(32)
        master_key = 'sk-' + secrets.token_hex(32)
        write_private(root / 'secrets/postgres-password', secrets.token_hex(32))
        write_private(root / 'runtime-private.json', json.dumps({
            'postgres_app_password': password, 'gateway_token': gateway_token,
            'master_key': master_key, 'speech_key': speech_key, 'phase': 'staging',
        }))
        write_private(root / 'openclaw.env', dotenv({'OPENCLAW_GATEWAY_TOKEN': gateway_token}))
        write_private(root / 'litellm.env', dotenv({
            'DEEPSEEK_API_KEY': PLACEHOLDER,
            'GEMINI_API_KEY': PLACEHOLDER,
            'LITELLM_MASTER_KEY': master_key,
            'DATABASE_URL': 'postgresql://litellm:' + quote(password, safe='') + '@postgres:5432/litellm',
            'LITELLM_SALT_KEY': 'sk-' + secrets.token_hex(32),
            'UI_USERNAME': 'admin',
            'UI_PASSWORD': secrets.token_urlsafe(24),
        }))
        write_private(root / 'speaches.env', dotenv({'API_KEY': speech_key}))
    finally:
        os.umask(old)
    print(f'Private runtime created in {root}. Fill provider keys in litellm.env. Telegram is not enabled.')


if __name__ == '__main__':
    main()
