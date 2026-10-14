"""Copy the live Windows LiteLLM database into an EMPTY Docker database.

The source remains online and untouched. Re-running against any existing target
database fails before changing it. No credentials appear in process arguments.
"""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ['LOCALAPPDATA'])
RUNTIME = LOCAL / 'AsiaDocker'
DOCKER = (r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker')
ENV = dict(os.environ, ASIA_RUNTIME_DIR=RUNTIME.as_posix())
COMPOSE = [DOCKER, 'compose', '-f', str(ROOT / 'infra/compose.yaml')]


def run(args, data=None, env=None):
    result = subprocess.run(args, input=data, capture_output=True, env=env or ENV)
    if result.returncode:
        raise RuntimeError('Migration command failed; output withheld to protect database credentials.')
    return result.stdout


def sql(query, database='postgres', user='postgres'):
    return run(COMPOSE + ['exec', '-T', 'postgres', 'psql', '-U', user, '-d', database,
                          '-v', 'ON_ERROR_STOP=1', '-At'], query.encode()).decode().strip()


def main():
    if sql("SELECT 1 FROM pg_database WHERE datname='litellm'"):
        raise SystemExit('Target database exists; refusing to overwrite it.')
    private = json.loads((RUNTIME / 'runtime-private.json').read_text())
    password = private['postgres_app_password']
    if not re.fullmatch(r'[a-f0-9]{48}', password):
        raise ValueError('Unexpected generated password format')
    source_creds = json.loads((LOCAL / 'AsiaPostgreSQL/credentials.json').read_text())
    dump = RUNTIME / 'windows-litellm.dump'
    pg_bin = LOCAL / 'Programs/AsiaPostgreSQL/pgsql/bin'
    run([str(pg_bin / 'pg_dump.exe'), '-h', '127.0.0.1', '-p', '55432', '-U', 'postgres',
         '-d', 'litellm', '-Fc', '-f', str(dump)], env=dict(os.environ, PGPASSWORD=source_creds['admin']))
    sql("CREATE ROLE litellm LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '" + password + "';")
    sql('CREATE DATABASE litellm OWNER litellm;')
    run(COMPOSE + ['exec', '-T', 'postgres', 'pg_restore', '-U', 'litellm', '-d', 'litellm',
                   '--no-owner', '--no-privileges', '--exit-on-error'], dump.read_bytes())
    tables = int(sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'", 'litellm'))
    if tables < 80:
        raise RuntimeError('Incomplete restored schema')
    result = {'postgres_tables': tables, 'source_unchanged': True, 'restore': 'passed'}
    (RUNTIME / 'database-migration-result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
