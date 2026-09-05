#!/usr/bin/env python3
"""Offline controller tests and static C# UI contracts, not a WinForms runtime test."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from test_colab import m

ROOT = Path(__file__).resolve().parents[1]

def source(name):
    return (ROOT / 'Desktop' / name).read_text(encoding='utf-8')

class UiPatchChecks(unittest.TestCase):
    def test_scientific_sources_unchanged(self):
        for name, expected in json.loads((ROOT / 'validation/ui-patch-baseline.json').read_text())['sha256'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_sidebar_and_page_removed(self):
        for old in ['AddNav("colab"', 'case "colab"', '["colab"]']:
            self.assertNotIn(old, source('MainForm.cs'))
        self.assertFalse((ROOT / 'Desktop/MainForm.ColabPanel.cs').exists())

    def test_single_modeless_window_and_timer_lifetime(self):
        window = source('MainForm.ColabWindow.cs')
        self.assertIn('ColabControlForm : Form', source('ColabControlForm.cs'))
        self.assertIn('ShowInTaskbar = true', source('ColabControlForm.cs'))
        for contract in ['colabWindow == null || colabWindow.IsDisposed', 'window.Show(this)', 'window.FormClosed', 'timer.Stop(); timer.Dispose()']:
            self.assertIn(contract, window)
        self.assertNotIn('Navigate("colab")', window)

    def test_local_work_preserves_managed_enabled(self):
        for name in ['MainForm.cs', 'MainForm.Science.cs', 'MainForm.Benchmark.cs']:
            self.assertNotIn('Enabled = false;', source(name))
            self.assertIn('RunLocalTaskAsync(progress, async () =>', source(name))
        for contract in ['ShowDialog(owner)', 'if (IsDisposed || Disposing) return;', 'if (running && !completing)']:
            self.assertIn(contract, source('ProgressDialog.cs'))

    def test_measured_buttons_and_disabled_palette(self):
        self.assertIn('return new ThemedButton', source('MainForm.cs'))
        self.assertIn('ActionButtonPanel.ArrangeButtons', source('MainForm.Layout.cs'))
        self.assertIn('child.SizeChanged', source('MainForm.Layout.cs'))
        self.assertIn('new SolidBrush(DisabledBackColor)', source('ThemedButton.cs'))
        self.assertIn('DisabledTextColor', source('ThemedButton.cs'))

    def test_old_job_can_be_stopped_after_changing_data(self):
        code = source('MainForm.ColabWindow.cs').split('private void RunColabPanelAction(string action)', 1)[1].split('private string ConnectionCode', 1)[0]
        self.assertLess(code.index('if (action is "cancel" or "download")'), code.index('plan.Kind == "standard"'))
        self.assertIn('Sessions.QueueAction(key, action)', code)

    def test_extra_method_command_routing(self):
        code = source('MainForm.Remote.cs')
        self.assertLess(code.index('action = NormalizeColabAction(action, kind)'), code.index('Sessions.Launch(key, action)'))
        self.assertIn('action == kind || action == "analyze"', code)
        for kind in ['variance', 'melsm', 'estimation', 'benchmark']:
            self.assertIn('"' + kind + '"', code.split('internal static string NormalizeColabAction', 1)[1])

    def test_runtime_switch_is_not_faked(self):
        code = source('MainForm.ColabWindow.cs')
        self.assertIn('Выбор ускорителя подтверждается в Colab.', code)
        self.assertIn('This MVS .NET engine uses CPU, not GPU/TPU', code)
        self.assertNotIn('Sessions.QueueAction(key, "runtime")', code)

    def test_notebook_version_and_control_option(self):
        self.assertIn('desktop_control=DESKTOP_CONTROL', (ROOT / 'tools/build_notebooks.py').read_text())
        for name in ['MVS_Colab.ipynb', 'MVS_Colab_Benchmark.ipynb']:
            book = json.loads((ROOT / 'notebooks' / name).read_text())
            self.assertEqual(book['metadata']['mvs']['appVersion'], '1.4.0')
            self.assertEqual(book['metadata']['mvs']['revision'], 'ui-colab-3')
            self.assertIn('desktop_control=DESKTOP_CONTROL', ''.join(book['cells'][0]['source']))

    def test_real_cpu_and_memory_reporting(self):
        with patch.object(m.os, 'cpu_count', return_value=4), patch.object(m.shutil, 'which', return_value=None), patch.object(m.Path, 'read_text', return_value='MemTotal: 16777216 kB\n'), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(m.detect_runtime_label(), 'CPU: 4 · RAM: 16.0 GiB')

    def test_gpu_name_is_observed(self):
        with patch.object(m.os, 'cpu_count', return_value=2), patch.object(m.shutil, 'which', return_value='/usr/bin/nvidia-smi'), patch.object(m.Path, 'read_text', return_value=''), patch.object(m.subprocess, 'check_output', return_value='Tesla T4\nTesla T4\n') as call, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(m.detect_runtime_label(), 'CPU: 2 · GPU: Tesla T4')
            self.assertEqual(call.call_args.kwargs['timeout'], 2)

    def test_missing_or_timed_out_probe_is_nonfatal(self):
        for error in [OSError(), subprocess.TimeoutExpired('nvidia-smi', 2)]:
            with patch.object(m.os, 'cpu_count', return_value=None), patch.object(m.shutil, 'which', return_value='nvidia-smi'), patch.object(m.Path, 'read_text', side_effect=OSError()), patch.object(m.subprocess, 'check_output', side_effect=error), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(m.detect_runtime_label(), 'CPU: 1')

    def test_hardware_report_omits_private_addresses(self):
        with patch.object(m.shutil, 'which', return_value=None), patch.object(m.Path, 'read_text', return_value=''), patch.dict(os.environ, {'COLAB_TPU_ADDR': 'private-runtime-address'}, clear=True):
            label = m.detect_runtime_label()
            self.assertIn('TPU runtime', label)
            self.assertNotIn('private-runtime-address', label)
            self.assertLessEqual(len(label), 200)

    def test_preparation_can_be_cancelled(self):
        plan = {'Key': 'a' * 64, 'Kind': 'benchmark', 'Revision': m.REVISION, 'DatasetHash': 'synthetic', 'SettingsHash': '', 'Repetitions': 0, 'Arguments': [], 'RequestedAction': 'prepare'}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('colab_job.json', json.dumps(plan))
        with tempfile.TemporaryDirectory() as folder, patch.object(m, 'notebook_url', return_value=''), patch.object(m, 'detect_runtime_label', return_value='CPU: 2'), patch.object(m, 'browser_request', return_value={'archive': base64.b64encode(archive.getvalue()).decode()}):
            workspace = m.Workspace(root=folder, connection='test-code', desktop_control=True)
            seen = []
            workspace.send = lambda **kwargs: seen.append((workspace.phase, workspace.controls_ready)) or True
            def cancel():
                self.assertTrue(workspace.controls_ready)
                raise m.RunCancelled()
            workspace.install_cli = cancel
            with self.assertRaises(m.RunCancelled):
                workspace.activate()
            self.assertIn(('preparing', True), seen)
            self.assertEqual(seen[-1], ('cancelled', False))

if __name__ == '__main__':
    unittest.main(verbosity=2)
