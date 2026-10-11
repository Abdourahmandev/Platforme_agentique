"""Prepare an isolated Windows-to-Docker migration; never print secrets.

Only creates a fresh runtime. Does not stop services, enable Telegram or overwrite
an existing runtime. Provider credentials and the database encryption salt are
copied from the working Windows installation.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
from urllib.parse import quote


def main():
    local = Path(os.environ['LOCALAPPDATA'])
    root = local / 'AsiaDocker'
    if (root / 'litellm.env').exists() or (root / 'runtime-private.json').exists():
        raise SystemExit('Runtime already initialized; refusing to replace credentials.')
    secret_dir = root / 'secrets'
    secret_dir.mkdir(parents=True, exist_ok=True)
    who = subprocess.check_output(['whoami'], text=True).strip()
    subprocess.run(['icacls', str(root), '/inheritance:r', '/grant:r',
                    who + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                   check=True, stdout=subprocess.DEVNULL)
    db = json.loads((local / 'AsiaLiteLLM/database.json').read_text())
    auth = json.loads((Path.home() / '.local/share/opencode/auth.json').read_text())
    password = secrets.token_hex(24)
    values = {
        'DEEPSEEK_API_KEY': auth['deepseek']['key'],
        'GEMINI_API_KEY': (local / 'AsiaLiteLLM/gemini.key').read_text().strip(),
        'LITELLM_MASTER_KEY': 'sk-' + secrets.token_hex(32),
        'DATABASE_URL': 'postgresql://litellm:' + quote(password, safe='') + '@postgres:5432/litellm',
        'LITELLM_SALT_KEY': db['salt_key'],
        'UI_USERNAME': db['ui_username'],
        'UI_PASSWORD': db['ui_password'],
    }
    # Compose dotenv single quoting preserves literal dollars in credentials.
    def dotenv(values):
        for value in values.values():
            if any(c in value for c in "\r\n'\\"):
                raise ValueError('Unsupported character in secret; refusing ambiguous dotenv encoding')
        return ''.join(f"{name}='{value}'\n" for name, value in values.items())
    encoded = dotenv(values)
    gateway_token = secrets.token_hex(32)
    speech_key = 'sk-local-' + secrets.token_hex(32)
    (root / 'openclaw').mkdir(exist_ok=True)
    (secret_dir / 'postgres-password').write_text(secrets.token_hex(32), encoding='ascii')
    (root / 'runtime-private.json').write_text(json.dumps({
        'postgres_app_password': password, 'gateway_token': gateway_token,
        'master_key': values['LITELLM_MASTER_KEY'], 'speech_key': speech_key, 'phase': 'staging',
    }), encoding='utf-8')
    (root / 'openclaw.env').write_text(dotenv({'OPENCLAW_GATEWAY_TOKEN': gateway_token}), encoding='utf-8')
    (root / 'litellm.env').write_text(encoded, encoding='utf-8')
    (root / 'speaches.env').write_text(dotenv({'API_KEY': speech_key}), encoding='utf-8')
    print('Private staging runtime created. Telegram is not enabled.')


if __name__ == '__main__':
    main()
