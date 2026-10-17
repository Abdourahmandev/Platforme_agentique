"""Prepare the private files of Dorasso's accounting database and document store.

Creates, once and without ever printing a secret:
- ~/.local/share/Dorasso/ledger/<role>.password (0600) for postgres and the four roles;
- ~/.local/share/Dorasso/comptabilite/pieces (original documents) and .../essai (dry-run files), 0700.
Existing files are never overwritten.
"""
import os
import secrets
from pathlib import Path

ROOT = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'Dorasso'
ROLES = ('postgres', 'ledger_migrator', 'ledger_engine', 'ledger_essai', 'ledger_dorasso')


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def main():
    secrets_dir = private_dir(ROOT / 'ledger')
    for role in ROLES:
        target = secrets_dir / f'{role}.password'
        if not target.exists():
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(32))
    for sub in ('pieces', 'essai'):
        private_dir(ROOT / 'comptabilite' / sub)
    print(f'Base comptable : {len(ROLES)} secrets prets dans {secrets_dir}, stockage des pieces pret.')


if __name__ == '__main__':
    main()
