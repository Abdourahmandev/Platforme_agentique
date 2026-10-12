"""Recovery failures must fail closed and leave no decrypted material behind."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

os.environ.setdefault('LOCALAPPDATA', tempfile.gettempdir())
spec = importlib.util.spec_from_file_location('backup', Path(__file__).parents[1] / 'ops/backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
docker_spec = importlib.util.spec_from_file_location('backup_docker', Path(__file__).parents[1] / 'ops/backup-docker.py')
backup_docker = importlib.util.module_from_spec(docker_spec)
with patch.dict(sys.modules, {'backup': backup}):
    docker_spec.loader.exec_module(backup_docker)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = self.root / 'source'
        self.source.write_bytes(os.urandom(2_100_000))
        self.archive = self.root / 'archive.aes'
        self.target = self.root / 'restored'
        self.keypatch = patch.object(backup, 'key', return_value=b'k' * 32)
        self.keypatch.start()
        self.addCleanup(self.keypatch.stop)
        backup.encrypt(self.source, self.archive)

    def test_roundtrip_multiple_blocks(self):
        backup.decrypt(self.archive, self.target)
        self.assertEqual(self.source.read_bytes(), self.target.read_bytes())

    def test_corruption_removes_plaintext(self):
        data = bytearray(self.archive.read_bytes())
        data[100] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaises(Exception):
            backup.decrypt(self.archive, self.target)
        self.assertFalse(self.target.exists())

    def test_short_or_truncated_archive(self):
        original = self.archive.read_bytes()
        for size in (0, 5, 17, 32, 50, len(original) - 1):
            with self.subTest(size=size):
                self.archive.write_bytes(original[:size])
                with self.assertRaises(Exception):
                    backup.decrypt(self.archive, self.target)
                self.assertFalse(self.target.exists())

    def test_never_overwrite_existing_destination(self):
        self.target.write_text('keep')
        with self.assertRaises(FileExistsError):
            backup.decrypt(self.archive, self.target)
        self.assertEqual(self.target.read_text(), 'keep')

    def test_cleanup_confined_to_staging(self):
        with patch.object(backup, 'STATE', self.root):
            with self.assertRaises(RuntimeError):
                backup.safe_remove(self.root)
            stage = self.root / 'stage-test'
            stage.mkdir()
            item = stage / 'readonly'
            item.write_text('x')
            item.chmod(0o444)
            backup.safe_remove(stage)
            self.assertFalse(stage.exists())

    def test_pilot_archive_without_rollback_journal_is_rejected(self):
        # Hashes alone cannot prove recovery: this archive is structurally
        # intact but lacks the state needed to return its active bot to Windows.
        payload = self.root / 'incomplete.zip'
        files = {'runtime/runtime-private.json': b'{"phase":"asia-pilot"}'}
        manifest = {'kind': 'asia-docker', 'files': {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        with zipfile.ZipFile(payload, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr('manifest.json', json.dumps(manifest))
        with patch.object(backup, 'STATE', self.root), \
             patch.object(backup, 'decrypt', side_effect=lambda source, target: shutil.copyfile(payload, target)), \
             patch.object(backup_docker, 'compose') as compose, \
             patch.object(backup_docker, 'remove_container_temp'):
            with self.assertRaisesRegex(ValueError, 'rollback journal'):
                backup_docker.verify(self.archive)
            compose.assert_not_called()
        self.assertEqual(list(self.root.glob('stage-*')), [])

    def test_training_receipts_survive_without_copying_snapshots_or_logs(self):
        state=self.root/'training';jobs=state/'jobs';jobs.mkdir(parents=True)
        job='a'*32
        for name in [job+'.started.json',job+'.result.json',job+'.log','unrelated.json']:
            (jobs/name).write_text('{"evidence":true}')
        snapshot=jobs/job;snapshot.mkdir();(snapshot/'secret.json').write_text('disposable')
        destination=self.root/'archive-training'
        backup_docker.copy_job_receipts(state,destination)
        self.assertEqual(sorted(p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()),
                         ['jobs/'+job+'.result.json','jobs/'+job+'.started.json'])
        self.assertEqual((destination/'jobs'/(job+'.result.json')).read_text(),'{"evidence":true}')


if __name__ == '__main__':
    unittest.main()
