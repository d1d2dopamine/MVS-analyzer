#!/usr/bin/env python3
"""Offline controller regressions. Real local subprocesses; mocked Google/browser transport."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_colab import ColabTests, m


class ControllerTests(unittest.TestCase):
    def fixture(self, directory):
        workspace, state = ColabTests().fixture(directory)
        workspace.show_monitor = lambda: None
        workspace.send = lambda **kwargs: True
        workspace.refresh = lambda: None
        workspace.native_state_check = lambda: None
        return workspace, state

    @staticmethod
    def command(workspace, action="calibrate", identity="e" * 64):
        return {**workspace.plan, "Revision": m.REVISION, "CommandId": identity, "RequestedAction": action}

    def test_command_runs_once_on_repeated_poll(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            calls = []
            def calibrate():
                calls.append("calibrate")
                workspace.phase = "calibrated"
            workspace.calibrate = calibrate
            command = self.command(workspace)
            self.assertTrue(workspace.dispatch_command(command))
            self.assertFalse(workspace.dispatch_command(command))
            self.assertEqual(calls, ["calibrate"])
            self.assertEqual(workspace.percent, 100)
            self.assertEqual(m.ci(m.strict_json(workspace.command_receipt(command["CommandId"])), "phase"), "calibrated")

    def test_receipt_prevents_replay_after_controller_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            calls = []
            workspace.calibrate = lambda: calls.append("calibrate")
            command = self.command(workspace)
            workspace.dispatch_command(command)
            replacement = copy.copy(workspace)
            replacement.command_id = ""
            self.assertFalse(replacement.dispatch_command(command))
            self.assertEqual(calls, ["calibrate"])
            self.assertEqual(replacement.phase, "failed")  # Unconfirmed completion is not success.

    def test_acknowledgement_failure_never_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.send = lambda **kwargs: False
            workspace.calibrate = lambda: self.fail("Unacknowledged work was executed")
            with self.assertRaises(ConnectionError):
                workspace.dispatch_command(self.command(workspace))
            self.assertEqual(workspace.phase, "failed")

    def test_reconnect_prepare_does_not_recalibrate(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            checks = []
            workspace.native_state_check = lambda: checks.append("verified")
            workspace.calibrate = lambda: self.fail("Reconnect started calibration")
            workspace.analyze = lambda: self.fail("Reconnect started analysis")
            workspace.dispatch_command(self.command(workspace, "prepare"))
            self.assertEqual(checks, ["verified"])
            self.assertEqual(workspace.phase, "calibrated")

    def test_different_job_or_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            for changed in ({"Key": "f" * 64}, {"Revision": "ui-colab-2"}):
                with self.assertRaises(ValueError):
                    workspace.dispatch_command({**self.command(workspace), **changed})
            self.assertEqual(workspace.command_id, "")

    def test_unknown_and_unsafe_commands_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            for command in (self.command(workspace, "shell"), self.command(workspace, identity="../escape")):
                with self.assertRaises(ValueError):
                    workspace.dispatch_command(command)
            self.assertFalse((workspace.root / "escape").exists())

    def test_failed_command_never_reports_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            def fail():
                raise RuntimeError("model failed")
            workspace.analyze = fail
            with contextlib.redirect_stdout(io.StringIO()):
                workspace.dispatch_command(self.command(workspace, "analyze"))
            self.assertEqual(workspace.phase, "failed")
            self.assertIsNone(workspace.percent)
            self.assertIn("model failed", workspace.message)

    def test_cancel_has_its_own_acknowledgement_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            def cancel():
                workspace.command_id = "f" * 64
                raise m.RunCancelled()
            workspace.calibrate = cancel
            workspace.dispatch_command(self.command(workspace))
            self.assertEqual(workspace.phase, "cancelled")
            self.assertEqual(workspace.command_id, "f" * 64)
            for identity in ("e" * 64, "f" * 64):
                self.assertEqual(m.ci(m.strict_json(workspace.command_receipt(identity)), "phase"), "cancelled")

    def test_cancel_pending_command_without_starting_work(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.calibrate = lambda: self.fail("Cancelled queued command was run")
            workspace.dispatch_command(self.command(workspace, "cancel"))
            self.assertEqual(workspace.phase, "cancelled")

    def test_interrupted_cell_is_not_swallowed_by_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            def interrupt():
                raise KeyboardInterrupt()
            workspace.analyze = interrupt
            with self.assertRaises(KeyboardInterrupt):
                workspace.dispatch_command(self.command(workspace, "analyze"))
            self.assertEqual(workspace.phase, "cancelled")

    def test_runtime_controller_stops_after_bounded_connection_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.connection = "local-test"
            workspace.send = lambda **kwargs: False
            with patch.object(m.time, "sleep") as sleep, contextlib.redirect_stdout(io.StringIO()):
                workspace.serve(reconnect_attempts=3)
            self.assertFalse(workspace.controls_ready)
            self.assertEqual(workspace.phase, "offline")
            self.assertEqual(sleep.call_count, 2)

    def test_terminal_files_are_retried_after_a_lost_status(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.connection = "local-test"
            workspace.send = m.Workspace.send.__get__(workspace)
            packets = []
            def request(base, route, packet):
                packets.append(packet)
                if len(packets) == 1:
                    raise ConnectionError("temporary")
                return {"ok": True}
            with patch.object(m, "browser_request", request), contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(workspace.send(include_files=True))
                self.assertTrue(workspace._files_pending)
                self.assertTrue(workspace.send())
            self.assertTrue(all("calibrationBase64" in packet for packet in packets))
            self.assertLess(packets[0]["sequence"], packets[1]["sequence"])
            self.assertFalse(workspace._files_pending)

    def test_compatible_140_calibration_is_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, state = self.fixture(directory)
            state["AppVersion"] = "1.4.0"
            workspace.state_path.write_text(json.dumps(state))
            self.assertTrue(workspace.has_calibration())
            state["AppVersion"] = "0.0.0"
            workspace.state_path.write_text(json.dumps(state))
            self.assertFalse(workspace.has_calibration())

    def test_progress_is_parsed_from_real_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.dotnet = None
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workspace.run_process([sys.executable, "-u", "-c", "print(' 35%  Simulations — 35 / 100')"]), 0)
            self.assertEqual(workspace.percent, 35)
            self.assertIn("Simulations", workspace.message)
            workspace.progress_line("100% Saving state")
            self.assertEqual(workspace.percent, 99)
            workspace.progress_line("999% bogus")
            self.assertEqual(workspace.percent, 99)

    def test_nonzero_child_exit_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.dotnet = None
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "exit code 3"):
                workspace.run_process([sys.executable, "-c", "raise SystemExit(3)"])

    def test_cancel_terminates_real_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.dotnet = None
            processes = []
            real_popen = subprocess.Popen
            def popen(*args, **kwargs):
                child = real_popen(*args, **kwargs)
                processes.append(child)
                return child
            def cancel():
                raise m.RunCancelled()
            workspace.poll_cancel = cancel
            started = time.monotonic()
            with patch.object(m.subprocess, "Popen", popen), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(m.RunCancelled):
                workspace.run_process([sys.executable, "-u", "-c", "import time; print('started', flush=True); time.sleep(60)"])
            self.assertIsNotNone(processes[0].poll())
            self.assertLess(time.monotonic() - started, 8)

    def test_cancel_poll_checks_job_and_new_command(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.controls_ready = True
            workspace.connection = "local-test"
            workspace.command_id = "e" * 64
            with patch.object(m, "browser_request", return_value=self.command(workspace, "cancel", "f" * 64)):
                with self.assertRaises(m.RunCancelled):
                    workspace.poll_cancel()
            self.assertEqual(workspace.command_id, "f" * 64)
            self.assertEqual(workspace.phase, "cancelling")

    def test_refresh_never_silently_uses_wrong_or_unconfirmed_job(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.connection = "local-test"
            workspace.refresh = m.Workspace.refresh.__get__(workspace)
            with patch.object(m, "browser_request", side_effect=ConnectionError("offline")), self.assertRaises(ConnectionError):
                workspace.refresh()
            with patch.object(m, "browser_request", return_value={"Key": "f" * 64}), self.assertRaises(RuntimeError):
                workspace.refresh()

    def test_partial_results_are_not_downloaded(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.state_path.unlink()
            folder = workspace.folder / "analysis"
            folder.mkdir()
            (folder / "results.json").write_text("partial")
            with self.assertRaisesRegex(RuntimeError, "No outputs"):
                workspace.download()
            self.assertFalse(list(workspace.root.glob("MVS_results_*.zip")))

    def test_monitor_escapes_messages_and_never_displays_connection_code(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = self.fixture(directory)
            workspace.message = '<script>alert("unsafe")</script>'
            workspace.connection = "sensitive-connection"
            workspace.percent = 42
            html = workspace.monitor_html()
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html)
            self.assertNotIn(workspace.connection, html)
            self.assertIn('value="42"', html)

    def test_browser_request_has_timeout_and_validates_port_route(self):
        calls = []
        fake_output = type("Output", (), {"eval_js": staticmethod(lambda script, **kwargs: calls.append((script, kwargs)) or {"ok": True, "value": {}})})
        fake_colab = type("Colab", (), {"output": fake_output})
        with patch.dict(sys.modules, {"google.colab": fake_colab}):
            for port, route in ((0, "job"), (65536, "job"), (8123, "shell")):
                with self.assertRaises(ValueError):
                    m.browser_request(f"http://127.0.0.1:{port}/v1/" + "a" * 64, route)
            m.browser_request("http://127.0.0.1:8123/v1/" + "a" * 64, "request")
        self.assertEqual(calls[0][1]["timeout_sec"], 13)
        self.assertIn("AbortController", calls[0][0])
        self.assertIn("credentials: 'omit'", calls[0][0])


if __name__ == "__main__":
    # Only this suite, not the imported baseline fixture class.
    unittest.main(defaultTest="ControllerTests", verbosity=2)
