"""Store one provider key in litellm.env, reading the value from stdin; never print it.

Usage: <key on stdin> | python infra/set-provider-key.py DEEPSEEK_API_KEY
Recreate the litellm container afterwards so it picks up the new value.
"""
import os
from pathlib import Path
import re
import sys

ALLOWED = {'DEEPSEEK_API_KEY', 'GEMINI_API_KEY'}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ALLOWED:
        raise SystemExit('Usage: set-provider-key.py ' + '|'.join(sorted(ALLOWED)))
    name = sys.argv[1]
    value = sys.stdin.read().strip().lstrip('﻿')
    if not value:
        raise SystemExit('Empty key; nothing changed.')
    # Same restriction as the runtime preparers' single-quoted dotenv encoding.
    if any(c in value for c in "\r\n'\\") or any(c.isspace() for c in value):
        raise SystemExit('Unsupported character in key; nothing changed.')
    path = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'AsiaDocker/litellm.env'
    text = path.read_text(encoding='utf-8')
    pattern = re.compile('^' + name + "=.*$", re.M)
    if not pattern.search(text):
        raise SystemExit(name + ' not found in litellm.env; nothing changed.')
    text = pattern.sub(lambda _: f"{name}='{value}'", text, count=1)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    temp.replace(path)
    print(f'{name} saved ({len(value)} characters).')


if __name__ == '__main__':
    main()
