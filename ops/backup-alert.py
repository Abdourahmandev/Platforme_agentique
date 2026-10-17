"""Telegram alert to the owner when the nightly backup fails, is incomplete or is stale.

Modes:
  failure   backup service failed (systemd OnFailure)
  offsite   local recovery point valid but the off-site copy failed
  check     watchdog: alert if the last verified backup is older than 36 hours
  test      one test message, to prove the alert path works

Sent by Asia's bot to the single owner of Asia's Telegram allowlist. The owner id is
read from OpenClaw once and cached (0600). The message carries no secret and no data.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.parse
import urllib.request

LOCAL = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share')
RUNTIME = LOCAL / 'AsiaDocker'
TOKEN = RUNTIME / 'secrets' / 'asia.token'
OWNER = RUNTIME / 'secrets' / 'owner-telegram.id'
LAST_SUCCESS = RUNTIME / 'scheduled-backup-last-success.json'
OPENCLAW = 'asia-platform-staging-openclaw-1'
MAX_AGE = timedelta(hours=36)


def owner_id():
    if OWNER.is_file() and not OWNER.is_symlink():
        value = OWNER.read_text().strip()
    else:
        script = ('const c=JSON.parse(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"));'
                  'process.stdout.write(JSON.stringify(c.channels.telegram.accounts.asia.allowFrom||[]))')
        ids = json.loads(subprocess.run(['docker', 'exec', OPENCLAW, 'node', '-e', script],
                                        check=True, capture_output=True, text=True).stdout)
        if len(ids) != 1:
            raise SystemExit('Refus : la liste Telegram d Asia doit contenir un seul proprietaire')
        value = str(ids[0])
        fd = os.open(OWNER, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(value)
    if not value.isdecimal():
        raise SystemExit('Refus : identifiant Telegram invalide')
    return value


def last_success():
    try:
        return datetime.fromisoformat(json.loads(LAST_SUCCESS.read_text())['completed_at'].replace('Z', '+00:00'))
    except (OSError, ValueError, KeyError):
        return None


def send(text):
    token = TOKEN.read_text().strip()
    body = urllib.parse.urlencode({'chat_id': owner_id(), 'text': text}).encode()
    with urllib.request.urlopen('https://api.telegram.org/bot' + token + '/sendMessage', data=body, timeout=20) as r:
        if not json.load(r).get('ok'):
            raise SystemExit('Telegram a refuse le message')


def main(mode):
    now = datetime.now(timezone.utc)
    last = last_success()
    since = last.strftime('%Y-%m-%d %H:%M UTC') if last else 'inconnue'
    host = socket.gethostname()
    if mode == 'failure':
        text = (f'⚠️ Sauvegarde nocturne EN ÉCHEC sur {host} ({now:%Y-%m-%d %H:%M} UTC).\n'
                f'Dernière sauvegarde vérifiée : {since}.\nDétail : journalctl -u asia-backup.service')
    elif mode == 'offsite':
        text = (f'⚠️ Sauvegarde locale valide sur {host}, mais la copie HORS SITE a échoué '
                f'({now:%Y-%m-%d %H:%M} UTC).')
    elif mode == 'check':
        if last and now - last <= MAX_AGE:
            return
        text = (f'⚠️ Aucune sauvegarde vérifiée depuis plus de 36 h sur {host}.\n'
                f'Dernière sauvegarde vérifiée : {since}.')
    elif mode == 'test':
        text = f'✅ Test de l alerte de sauvegarde ({host}). Dernière sauvegarde vérifiée : {since}.'
    else:
        raise SystemExit('Mode inconnu : failure, offsite check ou test')
    send(text)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '')
