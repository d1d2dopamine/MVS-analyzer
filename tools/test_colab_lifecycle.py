#!/usr/bin/env python3
"""Offline notebook lifecycle regressions; browser and desktop transport are simulated."""
import ast
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

from test_colab import ROOT, m
from test_colab_control import ControllerTests
from test_colab_connection import CODE, DummyWorkspace, bundle

NEW_CODE = CODE.replace('a' * 64, 'c' * 64)


def stub(connection=CODE, error=None):
    w = types.SimpleNamespace(connection=connection, connection_error=error,
                              controls_ready=False, desktop_control=True,
                              epoch='remembered', sequence=17, command_id='d' * 64,
                              cancel_exception=m.RunCancelled, phase='offline')
    w.activate = Mock(return_value=w)
    w.serve = Mock()
    w.calibrate = Mock()
    w.send = Mock(return_value=True)
    w.show_monitor = Mock()
    return w


class NotebookLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_first_run_prompts_once_without_reset_option(self):
        ns, w, prompt = {}, stub(), Mock(return_value=CODE)
        with patch.object(m, 'bootstrap_workspace', return_value=w) as boot:
            m.run_notebook_cell(ns, prompt=prompt)
        prompt.assert_called_once()
        self.assertIs(ns['mvs'], w)
        boot.assert_called_once_with(connection=CODE, ref='main', mode='standard', desktop_control=True, previous=None)
        w.activate.assert_called_once()
        w.serve.assert_called_once()
        w.calibrate.assert_not_called()

    def test_same_runtime_resumes_without_prompt(self):
        old, w, prompt = stub(), stub(), Mock(side_effect=AssertionError('Unexpected prompt'))
        with patch.object(m, 'bootstrap_workspace', return_value=w) as boot:
            m.run_notebook_cell({'mvs': old}, prompt=prompt)
        self.assertIs(boot.call_args.kwargs['previous'], old)
        self.assertEqual(boot.call_args.kwargs['connection'], CODE)
        prompt.assert_not_called()

    def test_bootstrap_preserves_epoch_sequence_and_command_after_stop(self):
        old = DummyWorkspace(CODE)
        old.epoch, old.sequence, old.command_id = 'same-epoch', 44, 'e' * 64
        with patch.object(m, 'Workspace', DummyWorkspace), patch.object(m, 'fetch_job_archive', return_value=bundle(include_runtime=False)):
            new = m.bootstrap_workspace(CODE, previous=old)
        self.assertEqual((new.epoch, new.sequence, new.command_id), ('same-epoch', 44, 'e' * 64))

    def test_active_controller_is_not_replaced(self):
        old = stub()
        old.controls_ready = True
        with patch.object(m, 'bootstrap_workspace') as boot:
            self.assertIs(m.run_notebook_cell({'mvs': old}, prompt=Mock()), old)
        boot.assert_not_called()
        self.assertTrue(old.controls_ready)

    def test_known_invalid_codes_request_fresh_code(self):
        for code in sorted(m.RECONNECT_ERROR_CODES):
            with self.subTest(error=code):
                old, new = stub(error=m.BridgeError(code, 'fresh code required')), stub(NEW_CODE)
                prompt = Mock(return_value=NEW_CODE)
                with patch.object(m, 'bootstrap_workspace', return_value=new):
                    m.run_notebook_cell({'mvs': old}, prompt=prompt)
                prompt.assert_called_once()
                new.serve.assert_called_once()

    def test_rejected_same_code_is_not_retried_or_taken_over(self):
        old = stub(error=m.BridgeError('runtime_conflict', 'owned'))
        with patch.object(m, 'bootstrap_workspace') as boot:
            m.run_notebook_cell({'mvs': old}, prompt=Mock(return_value=CODE))
        boot.assert_not_called()
        self.assertEqual(old.epoch, 'remembered')
        self.assertIn('NEW', self.output.getvalue())

    def test_revoked_code_during_bootstrap_prompts_then_recovers(self):
        old, new, ns = stub(), stub(NEW_CODE), {}
        ns['mvs'] = old
        failure = m.BridgeError('connection_revoked', 'revoked', 403)
        prompt = Mock(return_value=NEW_CODE)
        with patch.object(m, 'bootstrap_workspace', side_effect=[failure, new]) as boot:
            m.run_notebook_cell(ns, prompt=prompt)
        self.assertEqual(boot.call_count, 2)
        self.assertEqual(boot.call_args.kwargs['connection'], NEW_CODE)
        self.assertIs(ns['mvs'], new)
        new.serve.assert_called_once()

    def test_conflict_during_activation_prompts_and_recovers(self):
        failed, new = stub(), stub(NEW_CODE)
        failed.activate.side_effect = m.BridgeError('runtime_conflict', 'already owned', 409)
        ns, prompt = {}, Mock(side_effect=[CODE, NEW_CODE])
        with patch.object(m, 'bootstrap_workspace', side_effect=[failed, new]):
            m.run_notebook_cell(ns, prompt=prompt)
        self.assertIs(ns['mvs'], new)
        self.assertFalse(failed.controls_ready)
        failed.serve.assert_not_called()
        new.serve.assert_called_once()
        self.assertEqual(prompt.call_count, 2)

    def test_recovery_is_bounded(self):
        first, second = stub(), stub(NEW_CODE)
        for w in (first, second):
            w.activate.side_effect = m.BridgeError('runtime_conflict', 'owned', 409)
        prompt = Mock(side_effect=[CODE, NEW_CODE])
        with patch.object(m, 'bootstrap_workspace', side_effect=[first, second]) as boot:
            m.run_notebook_cell({}, prompt=prompt)
        self.assertEqual(boot.call_count, 2)
        self.assertEqual(prompt.call_count, 2)
        first.serve.assert_not_called()
        second.serve.assert_not_called()

    def test_network_failure_keeps_context_without_requesting_new_credentials(self):
        old, prompt = stub(), Mock(side_effect=AssertionError('Do not ask for another code'))
        with patch.object(m, 'bootstrap_workspace', side_effect=m.BridgeError('browser_unreachable', 'offline', 0, True)):
            ns = {'mvs': old}
            m.run_notebook_cell(ns, prompt=prompt)
        self.assertIs(ns['mvs'], old)
        self.assertEqual(old.connection, CODE)
        self.assertEqual(old.epoch, 'remembered')
        self.assertFalse(old.controls_ready)
        prompt.assert_not_called()

    def test_interrupted_activation_keeps_workspace_for_resume(self):
        w, ns = stub(), {}
        def interrupt():
            w.controls_ready = True
            w.sequence += 1
            raise KeyboardInterrupt()
        w.activate.side_effect = interrupt
        with patch.object(m, 'bootstrap_workspace', return_value=w):
            m.run_notebook_cell(ns, prompt=Mock(return_value=CODE))
        self.assertIs(ns['mvs'], w)
        self.assertFalse(w.controls_ready)
        self.assertEqual(w.sequence, 18)
        self.assertNotIn('Traceback', self.output.getvalue())
        w.serve.assert_not_called()

    def test_interrupted_prompt_does_not_destroy_previous_context(self):
        old = stub(error=m.BridgeError('connection_revoked', 'revoked'))
        ns = {'mvs': old}
        with patch.object(m, 'bootstrap_workspace') as boot:
            m.run_notebook_cell(ns, prompt=Mock(side_effect=KeyboardInterrupt()))
        boot.assert_not_called()
        self.assertIs(ns['mvs'], old)

    def test_cancel_exception_from_job_bound_module_is_handled(self):
        class JobCancellation(Exception):
            pass
        w = stub()
        w.cancel_exception = JobCancellation
        w.activate.side_effect = JobCancellation()
        with patch.object(m, 'bootstrap_workspace', return_value=w):
            m.run_notebook_cell({}, prompt=Mock(return_value=CODE))
        self.assertFalse(w.controls_ready)
        w.serve.assert_not_called()

    def test_real_scientific_errors_are_not_hidden(self):
        w = stub()
        w.activate.side_effect = m.CompatibilityError('wrong formula')
        with patch.object(m, 'bootstrap_workspace', return_value=w), self.assertRaisesRegex(m.CompatibilityError, 'wrong formula'):
            m.run_notebook_cell({}, prompt=Mock(return_value=CODE))
        self.assertEqual(w.phase, 'failed')
        w.serve.assert_not_called()

    def test_legacy_runtime_interrupt_is_clean_at_cell_boundary(self):
        w = stub()
        w.serve.side_effect = KeyboardInterrupt()
        with patch.object(m, 'bootstrap_workspace', return_value=w):
            m.run_notebook_cell({}, prompt=Mock(return_value=CODE))
        self.assertFalse(w.controls_ready)
        self.assertNotIn('Traceback', self.output.getvalue())

    def test_empty_code_uses_manual_calibration(self):
        w = stub('')
        with patch.object(m, 'bootstrap_workspace', return_value=w):
            m.run_notebook_cell({}, desktop_control=False, prompt=Mock(return_value=''))
        w.calibrate.assert_called_once()
        w.serve.assert_not_called()

    def test_switching_to_manual_mode_prompts_instead_of_silently_reusing_code(self):
        old, new, prompt = stub(), stub(''), Mock(return_value='')
        with patch.object(m, 'bootstrap_workspace', return_value=new):
            m.run_notebook_cell({'mvs': old}, desktop_control=False, prompt=prompt)
        prompt.assert_called_once()
        new.calibrate.assert_called_once()

    def test_generated_cells_call_automatic_runner_and_store_no_private_output(self):
        for name in ('MVS_Colab.ipynb', 'MVS_Colab_Benchmark.ipynb'):
            book = json.loads((ROOT / 'notebooks' / name).read_text())
            text = ''.join(book['cells'][0]['source'])
            self.assertNotIn('RESET_CONNECTION', text)
            self.assertIn('run_notebook_cell(globals()', text)
            tree = ast.parse(text)
            calls = [node for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
            self.assertEqual(calls[-1].value.func.id, 'run_notebook_cell')
            for cell in book['cells']:
                self.assertEqual(cell['outputs'], [])
                self.assertIsNone(cell['execution_count'])

    def test_real_activation_preserves_structured_runtime_conflict(self):
        with tempfile.TemporaryDirectory() as root, patch.object(m, 'notebook_url', return_value=''), patch.object(m, 'detect_runtime_label', return_value='CPU'):
            w = m.Workspace(root=root, connection=CODE, desktop_control=True)
            w._prefetched_archive = bundle(include_runtime=False, plan_change=None)
            conflict = m.BridgeError('runtime_conflict', 'owned', 409)
            with patch.object(m, 'browser_request', side_effect=conflict), patch.object(w, 'install_cli') as install:
                with self.assertRaises(m.BridgeError) as caught:
                    w.activate()
            self.assertEqual(caught.exception.code, 'runtime_conflict')
            self.assertFalse(w.controls_ready)
            install.assert_not_called()


class DownloadLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def fixture(self, root):
        w, state = ControllerTests().fixture(root)
        w.connection = CODE
        w.phase = 'complete'
        return w, state

    @contextlib.contextmanager
    def downloader(self, callback):
        colab = types.ModuleType('google.colab')
        colab.files = types.SimpleNamespace(download=callback)
        with patch.dict(sys.modules, {'google.colab': colab}):
            yield

    def test_transfer_runs_after_final_status_with_no_further_work(self):
        with tempfile.TemporaryDirectory() as root:
            w, state = self.fixture(root)
            before = w.state_path.read_bytes()
            events = []
            w.send = lambda **kw: events.append(('status', w.phase, w.controls_ready)) or True
            w.show_monitor = lambda: events.append(('monitor', w.phase))
            def transfer(path):
                self.assertFalse(w.controls_ready)
                self.assertEqual(w.phase, 'offline')
                self.assertIsNone(w._pending_download)
                self.assertEqual(w.state_path.read_bytes(), before)
                with zipfile.ZipFile(path) as z:
                    self.assertIsNone(z.testzip())
                    self.assertIn('calibration/calibration_state.json', z.namelist())
                    self.assertNotIn('data.csv', z.namelist())
                events.append(('browser', path))
            command = ControllerTests.command(w, 'download')
            with patch.object(m, 'browser_request', return_value=command) as request, patch.object(m.time, 'sleep') as sleep, self.downloader(transfer):
                w.serve()
            request.assert_called_once()
            sleep.assert_not_called()
            self.assertEqual(events[-1][0], 'browser')
            self.assertIn(('status', 'offline', False), events)
            self.assertEqual(m.strict_json(w.command_receipt(command['CommandId']))['phase'], 'complete')

    def test_download_receipt_prevents_replay_after_resume(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            command = ControllerTests.command(w, 'download')
            w.dispatch_command(command)
            path = w._pending_download
            w._pending_download = None
            w.command_id = ''
            self.assertFalse(w.dispatch_command(command))
            self.assertIsNone(w._pending_download)
            self.assertTrue(path.is_file())

    def test_interrupted_idle_controller_returns_without_traceback(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            with patch.object(m, 'browser_request', side_effect=KeyboardInterrupt()):
                w.serve()
            self.assertFalse(w.controls_ready)
            self.assertEqual(w.phase, 'offline')
            self.assertTrue(w.state_path.exists())
            self.assertNotIn('Traceback', self.output.getvalue())

    def test_interrupt_during_analysis_saves_cancelled_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            w.analyze = Mock(side_effect=KeyboardInterrupt())
            command = ControllerTests.command(w, 'analyze')
            with patch.object(m, 'browser_request', return_value=command):
                w.serve()
            self.assertFalse(w.controls_ready)
            self.assertEqual(m.strict_json(w.command_receipt(command['CommandId']))['phase'], 'cancelled')

    def test_browser_error_keeps_zip_and_prints_recovery_path(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            with self.downloader(Mock(side_effect=RuntimeError('browser blocked'))):
                path = w.download()
            self.assertTrue(path.exists())
            self.assertIn('Files', self.output.getvalue())
            self.assertIn('browser blocked', self.output.getvalue())

    def test_failure_to_send_final_status_does_not_block_download(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            def send(**kw):
                if w.phase == 'offline':
                    raise ConnectionError('lost final status')
                return True
            w.send = send
            transfer = Mock()
            with patch.object(m, 'browser_request', return_value=ControllerTests.command(w, 'download')), self.downloader(transfer):
                w.serve()
            transfer.assert_called_once()
            self.assertFalse(w.controls_ready)

    def test_failed_packaging_does_not_end_controller_as_success(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            w.state_path.unlink()
            with patch.object(m, 'browser_request', side_effect=[ControllerTests.command(w, 'download'), KeyboardInterrupt()]), patch.object(m.time, 'sleep'), self.downloader(Mock()) as unused:
                w.serve()
            self.assertEqual(m.strict_json(w.command_receipt('e' * 64))['phase'], 'failed')
            self.assertEqual(list(w.root.glob('MVS_results_*.zip')), [])

    def test_manual_download_remains_available(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            transfer = Mock()
            with self.downloader(transfer):
                path = w.download()
            transfer.assert_called_once_with(str(path))
            self.assertTrue(path.exists())

    def test_deferred_packaging_does_not_invoke_browser(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            transfer = Mock()
            with self.downloader(transfer):
                path = w.download(start_transfer=False)
            transfer.assert_not_called()
            self.assertTrue(path.exists())

    def test_two_download_cycles_can_reuse_same_ownership(self):
        with tempfile.TemporaryDirectory() as root:
            w, _ = self.fixture(root)
            original_epoch = w.epoch
            seen = []
            def status(**kw):
                w.sequence += 1
                seen.append((w.epoch, w.sequence))
                return True
            w.send = status
            transfer = Mock()
            for command_id in ('e' * 64, 'f' * 64):
                with patch.object(m, 'browser_request', return_value=ControllerTests.command(w, 'download', command_id)), self.downloader(transfer):
                    w.serve()
                self.assertFalse(w.controls_ready)
            self.assertEqual(transfer.call_count, 2)
            self.assertTrue(all(epoch == original_epoch for epoch, _ in seen))
            self.assertEqual(len(seen), len(set(seq for _, seq in seen)))


if __name__ == '__main__':
    unittest.main(defaultTest=('NotebookLifecycleTests', 'DownloadLifecycleTests'), verbosity=2)
