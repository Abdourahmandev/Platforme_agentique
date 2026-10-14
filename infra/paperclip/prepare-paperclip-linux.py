"""Prepare the private Paperclip runtime for a fresh Linux install; never print secrets.

Writes postgres.env and paperclip.env under $LOCALAPPDATA/AsiaPaperclip (0700/0600).
Refuses to replace an existing runtime. Usage:
    prepare-paperclip-linux.py https://rass-server.example.ts.net
"""
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import quote, urlparse


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
    if len(sys.argv) != 2 or urlparse(sys.argv[1]).scheme != 'https':
        raise SystemExit('Usage: prepare-paperclip-linux.py https://<tailscale-name>')
    public = sys.argv[1].rstrip('/')
    host = urlparse(public).hostname
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share')
    root = local / 'AsiaPaperclip'
    if (root / 'paperclip.env').exists() or (root / 'postgres.env').exists():
        raise SystemExit('Paperclip runtime already initialized; refusing to replace credentials.')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    password = secrets.token_hex(24)
    write_private(root / 'postgres.env', dotenv({
        'POSTGRES_USER': 'paperclip', 'POSTGRES_PASSWORD': password, 'POSTGRES_DB': 'paperclip'}))
    write_private(root / 'paperclip.env', dotenv({
        'DATABASE_URL': 'postgres://paperclip:' + quote(password, safe='') + '@postgres:5432/paperclip',
        'BETTER_AUTH_SECRET': secrets.token_hex(32),
        'PAPERCLIP_AGENT_JWT_SECRET': secrets.token_hex(32),
        'PAPERCLIP_TOOL_ACTION_SIGNING_SECRET': secrets.token_hex(32),
        'PAPERCLIP_SECRETS_MASTER_KEY': secrets.token_hex(32),
        'PAPERCLIP_PUBLIC_URL': public,
        'PAPERCLIP_AUTH_PUBLIC_BASE_URL': public,
        'BETTER_AUTH_TRUSTED_ORIGINS': public,
        # Tailscale name for the owner; container names for OpenClaw's internal calls.
        'PAPERCLIP_ALLOWED_HOSTNAMES': ','.join([host, 'paperclip', 'localhost', '127.0.0.1']),
    }))
    print(f'Private Paperclip runtime created in {root} for {public}.')


if __name__ == '__main__':
    main()
