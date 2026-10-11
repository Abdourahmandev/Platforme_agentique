"""Recovery failures must fail closed and leave no decrypted material behind."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('LOCALAPPDATA', tempfile.gettempdir())
spec = importlib.util.spec_from_file_location('backup', Path(__file__).parents[1] / 'ops/backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


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


if __name__ == '__main__':
    unittest.main()
