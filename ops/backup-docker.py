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
import zipfile
import backup

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'AsiaDocker'
DOCKER = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
ENV = dict(os.environ, ASIA_RUNTIME_DIR=RUNTIME.as_posix())
COMPOSE = [DOCKER, 'compose', '-f', str(ROOT / 'infra/compose.yaml')]


def run(args, data=None):
    r = subprocess.run(args, input=data, capture_output=True, env=ENV)
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
        # Include runtime env, original migration inputs and dedicated test device
        # credentials. Never include the recovery key in its own encrypted archive.
        private = stage / 'runtime'
        private.mkdir()
        for filename in ('litellm.env','openclaw.env','speaches.env','runtime-private.json','gateway-test-device.json',
                         'asia-handoff-private.json','telegram-add-developpement-private.json',
                         'telegram-add-recherche-private.json','delegation-private.json'):
            if (RUNTIME / filename).exists():
                shutil.copy2(RUNTIME / filename, private / filename)
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
