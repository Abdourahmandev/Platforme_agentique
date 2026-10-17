"""Encrypted Docker recovery point, with real isolated restoration checks.

OpenClaw's own backup command makes verified SQLite snapshots. PostgreSQL uses
pg_dump. This is a per-database consistent snapshot, not a distributed transaction.
The AES-GCM recovery key remains in AsiaBackup, outside this repository.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import tarfile
import time
import zipfile
import backup

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'AsiaDocker'
DOCKER = (r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker')
ENV = dict(os.environ, ASIA_RUNTIME_DIR=RUNTIME.as_posix())
COMPOSE = [DOCKER, 'compose', '-f', str(ROOT / 'infra/compose.yaml')]
PAPERCLIP = Path(os.environ['LOCALAPPDATA']) / 'AsiaPaperclip'
DORASSO = 'dorasso-hermes-1'
LEDGER = 'dorasso-ledger-1'
LEDGER_IMAGE = 'postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826'
LEDGER_ROLES = ('postgres', 'ledger_migrator', 'ledger_engine', 'ledger_essai', 'ledger_dorasso')
LOCAL = Path(os.environ['LOCALAPPDATA'])


def snapshot_paperclip(stage):
    """Optional deployment, but fail the backup if installed and unavailable."""
    if not (PAPERCLIP / 'deployment.json').exists():
        return
    target = stage / 'paperclip'
    target.mkdir()
    for source in PAPERCLIP.iterdir():
        if source.is_file() and not source.is_symlink() and source.suffix in {'.json', '.env'}:
            shutil.copy2(source, target / source.name)
    (target / 'postgres.dump').write_bytes(run([DOCKER, 'exec', 'asia-paperclip-postgres-1',
        'pg_dump', '-U', 'paperclip', '-d', 'paperclip', '-Fc']))
    (target / 'data.tar.gz').write_bytes(run([DOCKER, 'exec', 'asia-paperclip-paperclip-1',
        'tar', '-czf', '-', '-C', '/paperclip', '.']))


def snapshot_dorasso(stage):
    """Optional personal assistant (Hermes): its own consistent backup archive."""
    names = run([DOCKER, 'ps', '--filter', 'name=^' + DORASSO + '$', '--format', '{{.Names}}']).decode().split()
    if DORASSO not in names:
        return
    remote = '/tmp/dorasso-backup-' + secrets.token_hex(8) + '.zip'
    hermes = [DOCKER, 'exec', '-u', '1000', '-e', 'HOME=/opt/data', DORASSO]
    try:
        run(hermes + ['hermes', 'backup', '--output', remote, '--keep', '0'])
        (stage / 'dorasso').mkdir()
        (stage / 'dorasso' / 'hermes-backup.zip').write_bytes(run(hermes + ['cat', remote]))
    finally:
        run(hermes + ['rm', '-f', remote])


def ledger_installed():
    """Independent signs of an installation: secrets folder, container (any state) or volume.

    Any one of them means installed, so a damaged installation (folder removed, container
    stopped) makes the backup fail instead of silently omitting the accounting.
    """
    if os.path.lexists(LOCAL / 'Dorasso' / 'ledger'):
        return True
    containers = run([DOCKER, 'ps', '-a', '--filter', 'name=^' + LEDGER + '$', '--format', '{{.Names}}']).decode().split()
    volumes = run([DOCKER, 'volume', 'ls', '-q', '--filter', 'label=com.docker.compose.volume=dorasso-ledger']).decode().split()
    return bool(containers or volumes)


def real_dir(path):
    """A directory that must exist and must not be (or sit behind) a symbolic link."""
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError('Accounting directory missing or symbolic link: ' + path.name)
    return path


def snapshot_ledger(stage):
    """Dorasso's accounting database: consistent dump, roles, secrets and original documents.

    Absent installation: nothing to do. Installed but unavailable, a secret or a document
    directory missing, or any symbolic link: the backup fails rather than silently omitting
    the accounting. Ingestion contract: a document is written completely (temporary file,
    then atomic rename) before its reference is inserted in the database, and is never
    modified or deleted afterwards. The dump is taken first, so every document it references
    is present in the copy.
    """
    if not ledger_installed():
        return
    root = real_dir(LOCAL / 'Dorasso')
    secrets_dir = real_dir(root / 'ledger')
    store = real_dir(root / 'comptabilite')
    for sub in ('pieces', 'essai'):
        real_dir(store / sub)
    names = run([DOCKER, 'ps', '--filter', 'name=^' + LEDGER + '$', '--format', '{{.Names}}']).decode().split()
    if LEDGER not in names:
        raise RuntimeError('Dorasso accounting database is installed but not running')
    target = stage / 'dorasso-comptabilite'
    target.mkdir()
    (target / 'comptabilite.dump').write_bytes(run([DOCKER, 'exec', LEDGER, 'pg_dump', '-U', 'postgres',
                                                    '-d', 'comptabilite', '-Fc']))
    # Global objects (roles and their password hashes) are not part of pg_dump.
    (target / 'roles.sql').write_bytes(run([DOCKER, 'exec', LEDGER, 'pg_dumpall', '-U', 'postgres', '--roles-only']))
    (target / 'secrets').mkdir()
    for role in LEDGER_ROLES:
        item = secrets_dir / f'{role}.password'
        if item.is_symlink() or not item.is_file() or not item.read_text().strip():
            raise RuntimeError('Accounting secret missing, empty or symbolic link: ' + role)
        shutil.copy2(item, target / 'secrets' / item.name)
    for path in sorted(store.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Refused symbolic link in the accounting document store')
        relative = path.relative_to(store)
        if path.is_dir():
            (target / 'fichiers' / relative).mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            (target / 'fichiers' / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target / 'fichiers' / relative)
    for sub in ('pieces', 'essai'):
        (target / 'fichiers' / sub).mkdir(parents=True, exist_ok=True)


def ledger_sql(name, sql, database='comptabilite'):
    return run([DOCKER, 'exec', name, 'psql', '-X', '-U', 'postgres', '-d', database, '-v', 'ON_ERROR_STOP=1',
                '-Atc', sql]).decode().strip()


def restore_ledger_isolated(target):
    """Restore the recovery point into a throw-away cluster with no network.

    The live instance is never touched. Roles are recreated from roles.sql, the database
    with its own ACL (pg_restore --create); the instance-level revocations (postgres and
    template1 databases), which neither export carries, are reapplied as in a real
    recovery. Then the five backed-up passwords are checked by authentication and the
    complete isolation matrix (check-isolation.sh) is replayed on the restored copy.
    The throw-away cluster and its volume are always removed; a failed removal is an error.
    """
    name = 'dorasso-ledger-restore-' + secrets.token_hex(6)
    env = dict(ENV, POSTGRES_PASSWORD=secrets.token_urlsafe(24))
    work = Path(tempfile.mkdtemp(prefix='ledger-restore-'))
    try:
        run([DOCKER, 'run', '-d', '--name', name, '--network', 'none', '-e', 'POSTGRES_PASSWORD',
             '-e', 'POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256', LEDGER_IMAGE], env=env)
        for _ in range(60):
            logs = subprocess.run([DOCKER, 'logs', name], capture_output=True, env=ENV)
            ready = subprocess.run([DOCKER, 'exec', name, 'pg_isready', '-q', '-U', 'postgres'], capture_output=True, env=ENV)
            if b'init process complete' in logs.stdout + logs.stderr and ready.returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError('Throw-away accounting cluster did not start')
        # The bootstrap superuser already exists in the new cluster.
        roles = b'\n'.join(line for line in (target / 'roles.sql').read_bytes().splitlines()
                               if line.strip() != b'CREATE ROLE postgres;')
        run([DOCKER, 'exec', '-i', name, 'psql', '-X', '-q', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1'],
            data=roles)
        run([DOCKER, 'exec', '-i', name, 'pg_restore', '-U', 'postgres', '-d', 'postgres', '--create', '--exit-on-error'],
            data=(target / 'comptabilite.dump').read_bytes())
        ledger_sql(name, 'REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC; '
                         'REVOKE CONNECT, TEMPORARY ON DATABASE template1 FROM PUBLIC', database='postgres')
        owners = ledger_sql(name, "SELECT string_agg(nspname || ':' || pg_get_userbyid(nspowner), ',' ORDER BY nspname) "
                                  "FROM pg_namespace WHERE nspname IN ('ledger', 'essai')")
        if owners != 'essai:ledger_migrator,ledger:ledger_migrator':
            raise ValueError('Restored accounting schemas or owners are wrong')
        privileged = ledger_sql(name, "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'ledger\\_%' "
                                      "AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls)")
        members = ledger_sql(name, "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member "
                                   "WHERE r.rolname LIKE 'ledger\\_%'")
        app_roles = ledger_sql(name, "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'ledger\\_%'")
        acl = ledger_sql(name, "SELECT coalesce(datacl::text, '') FROM pg_database WHERE datname = 'comptabilite'")
        public = [item for item in acl.strip('{}').split(',') if item.startswith('=')]
        if privileged != '0' or members != '0' or app_roles != '4' or public or acl == '':
            raise ValueError('Restored accounting roles or database ACL are wrong')
        for role in LEDGER_ROLES:
            password = (target / 'secrets' / f'{role}.password').read_text().strip()
            run([DOCKER, 'exec', '-e', 'PGPASSWORD', name, 'psql', '-X', '-h', '127.0.0.1', '-U', role,
                 '-d', 'comptabilite', '-Atc', 'SELECT 1'], env=dict(ENV, PGPASSWORD=password))
        # Full positive and negative isolation matrix, with the backed-up passwords.
        (work / 'Dorasso').mkdir(mode=0o700)
        shutil.copytree(target / 'secrets', work / 'Dorasso' / 'ledger')
        check = Path(__file__).resolve().parent.parent / 'infra' / 'dorasso' / 'ledger' / 'check-isolation.sh'
        run(['bash', str(check)], env=dict(ENV, LOCALAPPDATA=str(work), LEDGER_CONTAINER=name))
        return owners
    finally:
        shutil.rmtree(work, ignore_errors=True)
        subprocess.run([DOCKER, 'rm', '-f', '-v', name], capture_output=True, env=ENV)
        left = subprocess.run([DOCKER, 'ps', '-a', '-q', '--filter', 'name=^' + name + '$'],
                              capture_output=True, env=ENV)
        if left.returncode or left.stdout.strip():
            raise RuntimeError('Throw-away accounting cluster could not be removed: ' + name)


def verify_ledger(base, restore):
    """Check the accounting recovery point; with restore, restore it into a throw-away cluster."""
    target = base / 'dorasso-comptabilite'
    if not target.exists():
        if ledger_installed():
            raise ValueError('Dorasso accounting database is installed but missing from the backup')
        return {'included': False}
    for name in ('comptabilite.dump', 'roles.sql'):
        if not (target / name).is_file():
            raise ValueError('Incomplete Dorasso accounting recovery point: ' + name)
    for role in LEDGER_ROLES:
        item = target / 'secrets' / f'{role}.password'
        if not item.is_file() or not item.read_text().strip():
            raise ValueError('Dorasso accounting secret missing from the recovery point: ' + role)
    for sub in ('pieces', 'essai'):
        if not (target / 'fichiers' / sub).is_dir():
            raise ValueError('Dorasso accounting documents missing from the recovery point')
    run([DOCKER, 'run', '--rm', '-i', '--network', 'none', '--entrypoint', 'pg_restore', LEDGER_IMAGE, '--list'],
        data=(target / 'comptabilite.dump').read_bytes())
    documents = sum(1 for p in (target / 'fichiers' / 'pieces').rglob('*') if p.is_file())
    result = {'included': True, 'documents': documents, 'restored': False}
    if restore:
        result.update(restored=True, schemas=restore_ledger_isolated(target))
    return result


def verify_dorasso(base):
    archive = base / 'dorasso' / 'hermes-backup.zip'
    if not archive.exists():
        return {'included': False}
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Dorasso backup archive is corrupt')
        names = z.namelist()
    for required in ('config.yaml', 'state.db'):
        if not any(n == required or n.endswith('/' + required) for n in names):
            raise ValueError('Incomplete Dorasso recovery point: ' + required)
    return {'included': True, 'files': len(names)}


def verify_paperclip(base, restore):
    target = base / 'paperclip'
    if not target.exists():
        return {'included': False}
    # owner-login.json only exists on installs that stored the owner's password.
    for name in ('deployment.json', 'paperclip.env', 'postgres.env',
                 'openclaw-before.json', 'postgres.dump', 'data.tar.gz'):
        if not (target / name).is_file():
            raise ValueError('Incomplete Paperclip recovery point: ' + name)
    # Extraction is confined to the already-private verification staging folder.
    with tarfile.open(target / 'data.tar.gz', 'r:gz') as archive:
        archive.extractall(target / 'restored-data', filter='data')
    if not (target / 'restored-data/instances/default').is_dir():
        raise ValueError('Paperclip data volume is incomplete')
    cmd = [DOCKER, 'exec', '-i', 'asia-paperclip-postgres-1']
    run(cmd + ['pg_restore', '--list'], data=(target / 'postgres.dump').read_bytes())
    result = {'included': True, 'volume_restored': True, 'postgres_restored': False}
    if restore:
        database = 'asia_paperclip_restore_' + secrets.token_hex(6)
        run(cmd + ['createdb', '-U', 'paperclip', database])
        try:
            run(cmd + ['pg_restore', '-U', 'paperclip', '-d', database, '--no-owner',
                       '--no-privileges', '--exit-on-error'], data=(target / 'postgres.dump').read_bytes())
            counts = run(cmd + ['psql', '-U', 'paperclip', '-d', database, '-Atc',
                "SELECT (SELECT count(*) FROM companies), (SELECT count(*) FROM agents), "
                "(SELECT count(*) FROM issues), (SELECT count(*) FROM issue_comments)"])
            companies, agents, issues, comments = map(int, counts.decode().strip().split('|'))
            if companies < 1 or agents < 3:
                raise ValueError('Paperclip company or agent data missing after restore')
            result.update(postgres_restored=True, companies=companies, agents=agents, issues=issues, comments=comments)
        finally:
            run(cmd + ['dropdb', '-U', 'paperclip', database])
    return result


def run(args, data=None, env=None):
    r = subprocess.run(args, input=data, capture_output=True, env=env or ENV)
    if r.returncode:
        (RUNTIME / 'docker-backup-error.log').write_bytes(r.stdout + r.stderr)
        raise RuntimeError('Docker backup/restore command failed; diagnostic output withheld.')
    return r.stdout


def compose(*args, data=None):
    return run(COMPOSE + list(args), data=data)


def remove_container_temp(filename):
    if not filename.startswith('/tmp/asia-backup-') or '/' in filename[len('/tmp/'):]:
        raise ValueError('Unsafe temporary path')
    compose('exec','-T','openclaw','node','-e',
            'require("fs").rmSync(process.argv[1],{recursive:true,force:true})',filename)


def copy_job_receipts(source,destination):
    # Receipts are recovery evidence, unlike the disposable job subdirectories.
    jobs=source/'jobs'
    if not jobs.is_dir() or jobs.is_symlink():return
    for receipt in jobs.iterdir():
        if re.fullmatch(r'[a-f0-9]{32}\.(started|result)\.json',receipt.name) and receipt.is_file() and not receipt.is_symlink():
            (destination/'jobs').mkdir(parents=True,exist_ok=True)
            shutil.copy2(receipt,destination/'jobs'/receipt.name)


def copy_approval_receipts(source, destination):
    # Keep native decision evidence without copying chat traces or CLI logs.
    for receipt in source.glob('telegram-approval-test*-private.json'):
        if re.fullmatch(r'telegram-approval-test(?:-[a-z0-9-]{1,40})?-private\.json', receipt.name) and receipt.is_file() and not receipt.is_symlink():
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(receipt, destination / receipt.name)


def snapshot_messagerie(stage):
    """Optional owner's messagerie and Notion bridge: env files, SQLite history, voice notes."""
    import sqlite3
    source = LOCAL / 'Messagerie'
    if (source / 'messagerie.env').exists():
        target = stage / 'messagerie'
        (target / 'data').mkdir(parents=True)
        shutil.copy2(source / 'messagerie.env', target / 'messagerie.env')
        for item in (source / 'data').iterdir():
            if item.is_symlink():
                continue
            if item.suffix == '.db':  # consistent copy of a live SQLite database
                with sqlite3.connect(f'file:{item}?mode=ro', uri=True) as db, sqlite3.connect(target / 'data' / item.name) as out:
                    db.backup(out)
            elif item.is_file() and not item.name.endswith(('-wal', '-shm')):
                shutil.copy2(item, target / 'data' / item.name)
            elif item.is_dir():
                shutil.copytree(item, target / 'data' / item.name, symlinks=False)
    for name in ('Notion', 'Jev'):  # bridge and pilot keys entered through the owner's secrets page
        folder = LOCAL / name
        if folder.is_dir():
            (stage / name.lower()).mkdir()
            for item in folder.glob('*.env'):
                shutil.copy2(item, stage / name.lower() / item.name)


def create():
    backup.private(backup.STATE)
    backup.private(backup.DEST)
    backup.key()  # Do not silently create a new key for an existing installation.
    stage = Path(tempfile.mkdtemp(prefix='stage-', dir=backup.STATE))
    remote = '/tmp/asia-backup-' + secrets.token_hex(8) + '.tar.gz'
    try:
        compose('exec','-T','openclaw','node','dist/index.js','backup','create',
                '--output',remote,'--verify','--json')
        (stage / 'openclaw.tar.gz').write_bytes(compose('exec','-T','openclaw','node','-e',
                'process.stdout.write(require("fs").readFileSync(process.argv[1]))',remote))
        (stage / 'litellm.dump').write_bytes(compose('exec','-T','postgres','pg_dump',
                '-U','litellm','-d','litellm','-Fc'))
        snapshot_paperclip(stage)
        snapshot_dorasso(stage)
        snapshot_ledger(stage)
        snapshot_messagerie(stage)
        # Include runtime env, original migration inputs and dedicated test device
        # credentials. Never include the recovery key in its own encrypted archive.
        private = stage / 'runtime'
        private.mkdir()
        for filename in ('litellm.env','openclaw.env','speaches.env','runtime-private.json','gateway-test-device.json',
                         'asia-handoff-private.json','telegram-add-developpement-private.json',
                         'telegram-add-recherche-private.json','delegation-private.json'):
            if (RUNTIME / filename).exists():
                shutil.copy2(RUNTIME / filename, private / filename)
        copy_approval_receipts(RUNTIME, private)
        shutil.copytree(RUNTIME / 'secrets', private / 'secrets')
        # Training keys, rollback journal and evaluation receipts remain private.
        # Large disposable job snapshots and dependency caches are reinstallable.
        if (RUNTIME / 'training').exists():
            training = private / 'training'
            training.mkdir()
            for source in (RUNTIME / 'training').glob('*.json'):
                shutil.copy2(source, training / source.name)
            copy_job_receipts(RUNTIME/'training',training)
            # Named cycles keep private receipts and an independently verified
            # native Gateway archive. Never copy job snapshots or dependency caches.
            for cycle in (RUNTIME / 'training/cycles').glob('cycle-*'):
                if not cycle.is_dir() or cycle.is_symlink():
                    continue
                destination = training / 'cycles' / cycle.name
                destination.mkdir(parents=True)
                for source in [*cycle.glob('*.json'), cycle / 'openclaw.tar.gz']:
                    if source.is_file() and not source.is_symlink():
                        shutil.copy2(source, destination / source.name)
                copy_job_receipts(cycle,destination)
        shutil.copy2(ROOT / 'infra/compose.yaml', stage / 'compose.yaml')
        for folder in ('gateway','infra','ops'):
            shutil.copytree(ROOT / folder, stage / 'code' / folder,
                            ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        hashes = {p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in stage.rglob('*') if p.is_file()}
        manifest = {'version':1,'kind':'asia-docker','created_at':datetime.now(timezone.utc).isoformat(),
                    'files':hashes,'source_commit':subprocess.check_output(
                        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())}
        (stage / 'manifest.json').write_text(json.dumps(manifest,indent=2))
        # Keep the ZIP outside its own input tree.
        package = stage / 'payload.zip'
        with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
            for name in [*hashes,'manifest.json']:
                z.write(stage / name,name)
        target = backup.DEST / ('docker-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-')+secrets.token_hex(4)+'.aes')
        partial = target.with_suffix('.partial')
        backup.encrypt(package,partial)
        partial.replace(target)
        return target
    finally:
        try:
            remove_container_temp(remote)
        finally:
            backup.safe_remove(stage)


def verify(archive, restore=False):
    stage = Path(tempfile.mkdtemp(prefix='stage-', dir=backup.STATE))
    remote = '/tmp/asia-backup-verify-' + secrets.token_hex(8) + '.tar.gz'
    target = '/tmp/asia-backup-restore-' + secrets.token_hex(8)
    try:
        backup.decrypt(archive,stage / 'payload.zip')
        with zipfile.ZipFile(stage / 'payload.zip') as z:
            for name in z.namelist():
                if not (stage / 'files' / name).resolve().is_relative_to((stage / 'files').resolve()):
                    raise ValueError('Unsafe archive member')
            z.extractall(stage / 'files')
        base = stage / 'files'
        manifest = json.loads((base / 'manifest.json').read_text())
        if manifest.get('kind') != 'asia-docker':
            raise ValueError('This is not a Docker recovery archive')
        for name,digest in manifest['files'].items():
            candidate = (base / name).resolve()
            if not candidate.is_relative_to(base.resolve()):
                raise ValueError('Unsafe manifest path')
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
                raise ValueError('Archive hash mismatch')
        runtime = json.loads((base / 'runtime/runtime-private.json').read_text())
        handoff = base / 'runtime/asia-handoff-private.json'
        if runtime.get('phase') == 'asia-pilot' and not handoff.exists():
            raise ValueError('Active Asia recovery point is missing its rollback journal')
        # docker cp creates root-owned files in /tmp; write as the service user
        # so verification and guaranteed cleanup retain the right permissions.
        compose('exec','-T','openclaw','node','-e',
                'require("fs").writeFileSync(process.argv[1],require("fs").readFileSync(0),{flag:"wx",mode:0o600})',
                remote,data=(base / 'openclaw.tar.gz').read_bytes())
        compose('exec','-T','openclaw','node','dist/index.js','backup','verify',remote,'--json')
        result = {'archive':str(archive),'files_verified':len(manifest['files']),
                  'handoff_journal_preserved':handoff.exists(),
                  'approval_receipts_verified':sum(bool(re.fullmatch(
                      r'runtime/telegram-approval-test(?:-[a-z0-9-]{1,40})?-private\.json',name))
                      for name in manifest['files']),
                  'training_receipts_verified':sum(bool(re.fullmatch(
                      r'runtime/training/(?:cycles/cycle-[1-9][0-9]{0,3}/)?jobs/[a-f0-9]{32}\.(?:started|result)\.json',name))
                      for name in manifest['files']),
                  'openclaw_native_verify':True,'openclaw_restored':False,'postgres_restored':False}
        if restore:
            compose('exec','-T','openclaw','node','dist/index.js','backup','restore',remote,
                    '--target',target,'--json')
            result['openclaw_restored'] = True
            database = 'asia_restore_check_' + secrets.token_hex(6)
            compose('exec','-T','postgres','createdb','-U','postgres',database)
            try:
                compose('exec','-T','postgres','pg_restore','-U','postgres','-d',database,
                        '--no-owner','--no-privileges','--exit-on-error',data=(base / 'litellm.dump').read_bytes())
                tables = int(compose('exec','-T','postgres','psql','-U','postgres','-d',database,'-Atc',
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"))
                if tables < 80:
                    raise ValueError('Incomplete database restore')
                result.update(postgres_restored=True,postgres_tables=tables)
            finally:
                compose('exec','-T','postgres','dropdb','-U','postgres',database)
        result['paperclip'] = verify_paperclip(base, restore)
        result['dorasso'] = verify_dorasso(base)
        result['dorasso_comptabilite'] = verify_ledger(base, restore)
        return result
    finally:
        try:
            remove_container_temp(remote)
            remove_container_temp(target)
        finally:
            backup.safe_remove(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--restore-check',action='store_true')
    args = parser.parse_args()
    backup.private(backup.STATE)
    archive = args.verify or create()
    result = verify(archive,args.restore_check)
    (RUNTIME / 'docker-backup-result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
