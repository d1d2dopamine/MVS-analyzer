#!/usr/bin/env python3
"""Offline backup transport tests. Native calculation replay lives in BackupChecks.cs."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from test_colab import ROOT, m, ColabTests

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.folder = self.root / 'MVS_Backups'; self.folder.mkdir()
        env = patch.dict(os.environ, {'MVS_BACKUP_DIR': str(self.folder)}); env.start(); self.addCleanup(env.stop)
    def write(self, name='run.mvsbackup', kind='calibrate', job='a' * 64, corrupt=False, extra=None):
        path = self.folder / name; data = json.dumps({'OriginJob': job, 'Request': {'Kind': kind}}).encode()
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('backup.json', data)
            z.writestr('SHA256SUMS.txt', ('0' * 64 if corrupt else hashlib.sha256(data).hexdigest()) + '  backup.json\n')
            if extra: z.writestr(extra, 'invalid')
        return path
    def test_one_folder_for_all_modes(self):
        env = m.backup_process_environment(None, 'a' * 64)
        self.assertEqual(env['MVS_BACKUP_DIR'], str(self.folder)); self.assertEqual(env['MVS_BACKUP_JOB'], 'a' * 64)
    def test_changed_snapshot_is_readonly(self):
        path = self.write(); before = path.read_bytes(); item = m.changed_backup({}, 'standard', 'a' * 64)
        self.assertEqual(item[0], path.name); self.assertEqual(item[2], before); self.assertEqual(path.read_bytes(), before)
    def test_acknowledged_snapshot_is_not_resent(self):
        self.write(); name, stamp, _ = m.changed_backup({}, 'standard', 'a' * 64)
        self.assertIsNone(m.changed_backup({name: stamp}, 'standard', 'a' * 64))
    def test_new_snapshot_is_resent(self):
        self.write(); name, stamp, _ = m.changed_backup({}, 'standard', 'a' * 64)
        path = self.write(kind='analyze'); os.utime(path, ns=(stamp[0] + 1000000, stamp[0] + 1000000))
        self.assertIsNotNone(m.changed_backup({name: stamp}, 'standard', 'a' * 64))
    def test_other_job_is_not_sent(self):
        self.write(job='b' * 64); self.assertIsNone(m.changed_backup({}, 'standard', 'a' * 64))
    def test_other_mode_is_not_sent(self):
        self.write(kind='benchmark'); self.assertIsNone(m.changed_backup({}, 'standard', 'a' * 64)); self.assertIsNotNone(m.changed_backup({}, 'benchmark', 'a' * 64))
    def test_previous_snapshot_is_not_sent_as_current(self):
        self.write(name='run.previous.mvsbackup'); self.assertIsNone(m.changed_backup({}, 'standard', 'a' * 64))
    def test_corrupt_checksum_rejected(self):
        self.write(corrupt=True)
        with self.assertRaises(ValueError): m.changed_backup({}, 'standard', 'a' * 64)
    def test_extra_archive_paths_rejected(self):
        self.write(extra='../escape')
        with self.assertRaises(ValueError): m.changed_backup({}, 'standard', 'a' * 64)
    def workspace(self):
        w, _ = ColabTests().fixture(self.root); w.connection = 'http://127.0.0.1:12345/v1/' + 'a' * 64
        w.peer_capabilities = {'portable-backup-v1', 'status-retry-v1'}; return w
    def test_ack_only_after_successful_desktop_write(self):
        self.write(); w = self.workspace()
        with patch.object(m, 'browser_request', side_effect=ConnectionError('offline')), contextlib.redirect_stdout(io.StringIO()): self.assertFalse(w.send())
        self.assertFalse(getattr(w, '_backup_acknowledged', {}))
        with patch.object(m, 'browser_request', return_value={'ok': True}), contextlib.redirect_stdout(io.StringIO()): self.assertTrue(w.send())
        self.assertIn('run.mvsbackup', w._backup_acknowledged); self.assertNotIn('backupBase64', w.packet())
    def test_backup_read_error_does_not_stop_calculation(self):
        self.write(corrupt=True); w = self.workspace()
        with patch.object(m, 'browser_request', return_value={'ok': True}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(w.send())
        self.assertIn('Backup mirror unavailable', output.getvalue())
        self.assertFalse(getattr(w, '_backup_acknowledged', {}))

    def test_legacy_peer_never_receives_backup_payload(self):
        self.write(); w = self.workspace(); w.peer_capabilities = set(); self.assertNotIn('backupBase64', w.packet())
    def test_first_packet_contains_actual_zip(self):
        path = self.write(); self.assertEqual(base64.b64decode(self.workspace().packet()['backupBase64']), path.read_bytes())
    def test_empty_folder_does_not_write(self):
        self.assertIsNone(m.changed_backup({}, 'standard', 'a' * 64)); self.assertEqual(list(self.folder.iterdir()), [])
    def test_confirmation_before_calculation(self):
        self.assertIn('AddBackupCard(page)', (ROOT / 'Desktop/MainForm.Pages.cs').read_text())
        code = (ROOT / 'Desktop/MainForm.Backups.cs').read_text()
        self.assertIn('Загрузить бэкап и продолжить', code); self.assertIn('Продолжить с места, на котором остановились?', code)
        self.assertLess(code.index('MessageBoxButtons.YesNo'), code.index('BackupRunner.Run(')); self.assertIn('MessageBoxDefaultButton.Button2', code)
    def test_independent_determinism_passes(self):
        code = (ROOT / 'Benchmark/BenchmarkRunner.cs').read_text(); self.assertIn('"replay-first"', code); self.assertIn('"replay-second"', code)
    def test_whitelisted_operations_only(self):
        code = (ROOT / 'Infrastructure/BackupRunner.cs').read_text(); self.assertNotIn('Process.Start', code)
        for mode in ('benchmark', 'calibrate', 'analyze', 'variance', 'estimation', 'melsm'): self.assertIn('case "' + mode + '":', code)

if __name__ == '__main__': unittest.main(defaultTest='BackupTests', verbosity=2)
