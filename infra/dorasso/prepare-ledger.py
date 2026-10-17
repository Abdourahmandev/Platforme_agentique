"""Prepare the private files of Dorasso's accounting database and document store.

Creates, without ever printing a secret:
- ~/.local/share/Dorasso/ledger/<role>.password (0600, host user): used by the
  operator's tools (check-isolation.sh) and later by the engine and connectors;
- ~/.local/share/Dorasso/ledger/container/<role>.password (0400, owned by the
  postgres user of the pinned image): the Docker secrets read by init-roles.sh;
- ~/.local/share/Dorasso/comptabilite/pieces (original documents, write-once)
  and .../essai (dry-run files), 0700.
Existing passwords are never regenerated; permissions are re-asserted on every run.
Requires sudo for the container copies (ownership by the image's postgres user).
"""
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'Dorasso'
IMAGE = 'postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826'
ROLES = ('postgres', 'ledger_migrator', 'ledger_engine', 'ledger_essai', 'ledger_dorasso')


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def postgres_ids():
    """uid and gid of the postgres user inside the pinned image (not assumed)."""
    out = subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'sh', IMAGE, '-c', 'id -u postgres; id -g postgres'],
                         check=True, capture_output=True, text=True).stdout.split()
    uid, gid = int(out[0]), int(out[1])
    if uid == 0 or gid == 0:
        raise SystemExit('Refus : utilisateur postgres de l image inattendu (root).')
    return uid, gid


def main():
    secrets_dir = private_dir(ROOT / 'ledger')
    for role in ROLES:
        target = secrets_dir / f'{role}.password'
        if not target.exists():
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(32))
        os.chmod(target, 0o600)
        if not target.read_text().strip():
            raise SystemExit(f'Refus : secret vide {target.name}')
    uid, gid = postgres_ids()
    container = secrets_dir / 'container'
    subprocess.run(['sudo', 'install', '-d', '-m', '0755', str(container)], check=True)
    for role in ROLES:
        # Numeric ids: the image's postgres user does not exist on the host.
        copy = str(container / f'{role}.password')
        subprocess.run(['sudo', 'install', '-m', '0400', str(secrets_dir / f'{role}.password'), copy], check=True)
        subprocess.run(['sudo', 'chown', f'{uid}:{gid}', copy], check=True)
    for sub in ('pieces', 'essai'):
        private_dir(ROOT / 'comptabilite' / sub)
    print(f'Base comptable : {len(ROLES)} secrets prets (copies conteneur pour uid {uid}), stockage des pieces pret.')


if __name__ == '__main__':
    main()
