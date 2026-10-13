"""Create the empty LiteLLM database for a fresh install (no Windows source).

Counterpart of migrate-database.py: same role and database, no data copied.
LiteLLM creates its schema on first start. Refuses to touch an existing database.
"""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'AsiaDocker'
ENV = dict(os.environ, ASIA_RUNTIME_DIR=RUNTIME.as_posix())
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'infra/compose.yaml')]


def sql(query, database='postgres'):
    result = subprocess.run(COMPOSE + ['exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', database,
                                       '-v', 'ON_ERROR_STOP=1', '-At'],
                            input=query.encode(), capture_output=True, env=ENV)
    if result.returncode:
        raise RuntimeError('Database command failed; output withheld to protect credentials.')
    return result.stdout.decode().strip()


def main():
    if sql("SELECT 1 FROM pg_database WHERE datname='litellm'"):
        raise SystemExit('Target database exists; refusing to overwrite it.')
    password = json.loads((RUNTIME / 'runtime-private.json').read_text())['postgres_app_password']
    if not re.fullmatch(r'[a-f0-9]{48}', password):
        raise ValueError('Unexpected generated password format')
    sql("CREATE ROLE litellm LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '" + password + "';")
    sql('CREATE DATABASE litellm OWNER litellm;')
    print(json.dumps({'database': 'litellm', 'created': True}))


if __name__ == '__main__':
    main()
