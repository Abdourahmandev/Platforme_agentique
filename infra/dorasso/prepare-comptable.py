"""Prepare Dorasso's accounting skill and closed read tool (Decidata_accoutant #9), read-only for Hermes.

Usage: python3 prepare-comptable.py <archive.tar of Decidata_accoutant main>

Builds ${DORASSO_DIR}/comptable/{app,skill} without printing any secret:
- app/dorasso/            the closed read tool (named queries only, role ledger_dorasso);
- app/lib/               psycopg[binary] for Hermes' Python (3.14), installed here, not in the image;
- app/dorasso-lecture    launcher: password through the environment, never on a command line;
- app/ledger_dorasso.password (0400): the read-only role, the only database secret Hermes gets;
- skill/SKILL.md         the "comptable-decidata" skill, mounted read-only in /opt/data/skills.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'Dorasso'
TARGET = ROOT / 'comptable'
TOOL = '/opt/dorasso-comptable/dorasso-lecture'
LAUNCHER = """#!/bin/sh
# Closed read tool for Dorasso: named queries only, read-only role ledger_dorasso.
set -eu
D=/opt/dorasso-comptable
PGPASSWORD="$(cat "$D/ledger_dorasso.password")"
export PGPASSWORD
export LEDGER_DSN="postgresql://ledger_dorasso@ledger:5432/comptabilite"
export PYTHONPATH="$D/lib:$D"
exec /opt/hermes/.venv/bin/python3 -m dorasso.outil_lecture "$@"
"""


def main(archive):
    for path in (ROOT, ROOT / 'ledger'):
        if path.is_symlink() or not path.is_dir():
            raise SystemExit(f'Refus : dossier absent ou lien symbolique {path}')
    work = Path(tempfile.mkdtemp(prefix='comptable-'))
    try:
        with tarfile.open(archive) as tar:
            members = [m for m in tar.getmembers() if m.name.startswith(('dorasso/', 'dorasso\\'))]
            tar.extractall(work, members=members, filter='data')
        new = TARGET.with_name('comptable.new')
        shutil.rmtree(new, ignore_errors=True)
        (new / 'app').mkdir(parents=True)
        (new / 'skill').mkdir()
        shutil.copytree(work / 'dorasso', new / 'app' / 'dorasso',
                        ignore=shutil.ignore_patterns('consignes', '__pycache__', '*.md'))
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-cache-dir', '--target',
                        str(new / 'app' / 'lib'), 'psycopg[binary]==3.2.10'], check=True)
        launcher = new / 'app' / 'dorasso-lecture'
        launcher.write_text(LAUNCHER)
        launcher.chmod(0o555)
        secret = new / 'app' / 'ledger_dorasso.password'
        shutil.copyfile(ROOT / 'ledger' / 'ledger_dorasso.password', secret)
        secret.chmod(0o400)
        skill = (work / 'dorasso' / 'consignes' / 'comptable-decidata' / 'SKILL.md').read_text(encoding='utf-8')
        old = 'python -m dorasso.outil_lecture REQUETE --date AAAA-MM-JJ --schema essai'
        if old not in skill:
            raise SystemExit('Refus : invocation de l outil introuvable dans SKILL.md')
        (new / 'skill' / 'SKILL.md').write_text(skill.replace(old, TOOL + ' REQUETE --date AAAA-MM-JJ'),
                                               encoding='utf-8')
        for path in new.rglob('*'):
            if path.is_dir():
                path.chmod(0o555)
            elif path != secret and path != launcher:
                path.chmod(0o444)
        new.chmod(0o700)
        old_dir = TARGET.with_name('comptable.old')
        shutil.rmtree(old_dir, ignore_errors=True)
        if TARGET.exists():
            TARGET.rename(old_dir)
        new.rename(TARGET)
        shutil.rmtree(old_dir, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f'Compétence comptable prête : {TARGET} (outil {TOOL}, rôle ledger_dorasso).')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
