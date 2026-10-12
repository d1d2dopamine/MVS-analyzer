"""Wrapper boundary regressions, not native-engine scientific verification.

POSIX fixtures exercise real OS launches and the real constructor handshake using
a synthetic protocol peer. Mocked failures cover portable errno/protocol cases.
"""

from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mvs.engine import (
    Engine,
    EngineCompatibilityError,
    EngineError,
    EngineNotFoundError,
    InputError,
    MvsError,
    ScientificDiagnostic,
)


def response(command="version", **changes):
    payload = {
        "schemaVersion": "mvs-cli-result/v1",
        "cliProtocol": {"name": "mvs-cli", "major": 1},
        "engineVersion": "synthetic-test-engine",
        "command": command,
        "status": "completed",
        "exitCode": 0,
    }
    payload.update(changes)
    return subprocess.CompletedProcess([], payload["exitCode"], json.dumps(payload), "")


class EngineErrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mvs-engine-errors-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cli = self.root / "synthetic-mvs"

    def write_cli(self, before_emit=""):
        # Only this disposable test fixture receives executable permissions.
        self.cli.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "command = sys.argv[1]\n"
            "assert sys.argv[-2:] == ['--json', '--quiet']\n"
            + before_emit
            + f"payload = {json.loads(response().stdout)!r}\n"
            "payload['command'] = command\n"
            "print(json.dumps(payload))\n",
            encoding="utf-8",
        )
        self.cli.chmod(0o700)
        return self.cli

    def mock_engine(self):
        self.cli.write_text("synthetic fixture", encoding="utf-8")
        with patch("mvs.engine.subprocess.run", return_value=response()):
            return Engine(self.cli)

    def assert_context(self, exc, command="version"):
        self.assertIsInstance(exc, MvsError)
        self.assertIn(str(self.cli), str(exc))
        self.assertIn(repr(command), str(exc))

    @unittest.skipUnless(os.name == "posix", "POSIX executable script fixture")
    def test_real_constructor_version_handshake(self):
        engine = Engine(self.write_cli())
        self.assertEqual(engine.executable, str(self.cli))
        self.assertEqual(engine.identity.command, "version")
        self.assertEqual(engine.identity.engine_version, "synthetic-test-engine")
        result = engine.estimation(output=self.root / "output")
        self.assertEqual((result.command, result.exit_code), ("estimation", 0))

    def test_missing_explicit_executable(self):
        with self.assertRaises(EngineNotFoundError) as caught:
            Engine(self.cli)
        self.assert_context(caught.exception)

    def test_missing_path_discovery(self):
        with patch.dict(os.environ, {"MVS_CLI": ""}), \
                patch("mvs.engine.shutil.which", return_value=None) as which:
            with self.assertRaises(EngineNotFoundError) as caught:
                Engine()
        which.assert_called_once_with("mvs")
        self.assertIn("'mvs'", str(caught.exception))
        self.assertIn("'version'", str(caught.exception))

    def test_explicit_command_name_still_uses_path_lookup(self):
        with patch("mvs.engine.Path.exists", return_value=False), \
                patch("mvs.engine.shutil.which", return_value=str(self.cli)) as which, \
                patch("mvs.engine.subprocess.run", return_value=response()):
            engine = Engine("synthetic-mvs-command")
        which.assert_called_once_with("synthetic-mvs-command")
        self.assertEqual(engine.executable, str(self.cli))

    def test_existing_explicit_path_keeps_precedence(self):
        self.cli.write_text("synthetic fixture", encoding="utf-8")
        with patch.dict(os.environ, {"MVS_CLI": "another-engine"}), \
                patch("mvs.engine.shutil.which") as which, \
                patch("mvs.engine.subprocess.run", return_value=response()):
            engine = Engine(self.cli)
        which.assert_not_called()
        self.assertEqual(engine.executable, str(self.cli))

    def test_environment_executable_is_still_used(self):
        self.cli.write_text("synthetic fixture", encoding="utf-8")
        with patch.dict(os.environ, {"MVS_CLI": str(self.cli)}), \
                patch("mvs.engine.subprocess.run", return_value=response()):
            engine = Engine()
        self.assertEqual(engine.executable, str(self.cli))

    @unittest.skipUnless(os.name == "posix", "POSIX executable permissions")
    def test_real_nonexecutable_file(self):
        self.cli.write_text("synthetic fixture", encoding="utf-8")
        self.cli.chmod(0o600)
        with self.assertRaises(EngineError) as caught:
            Engine(self.cli)
        self.assertIsInstance(caught.exception.__cause__, PermissionError)
        self.assert_context(caught.exception)

    @unittest.skipUnless(os.name == "posix", "POSIX directory launch behavior")
    def test_real_directory_is_not_an_engine(self):
        self.cli.mkdir()
        with self.assertRaises(EngineError) as caught:
            Engine(self.cli)
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assert_context(caught.exception)

    @unittest.skipUnless(os.name == "posix", "POSIX executable format")
    def test_real_invalid_executable_format(self):
        self.cli.write_text("synthetic fixture without a shebang\n", encoding="utf-8")
        self.cli.chmod(0o700)
        with self.assertRaises(EngineError) as caught:
            Engine(self.cli)
        self.assertEqual(caught.exception.__cause__.errno, errno.ENOEXEC)
        self.assert_context(caught.exception)

    @unittest.skipUnless(os.name == "posix", "POSIX executable script fixture")
    def test_real_executable_disappears_after_successful_constructor(self):
        engine = Engine(self.write_cli())
        self.cli.unlink()
        with self.assertRaises(EngineNotFoundError) as caught:
            engine.estimation(output=self.root / "output")
        self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)
        self.assert_context(caught.exception, "estimation")

    @unittest.skipUnless(os.name == "posix", "POSIX executable permissions")
    def test_real_executable_loses_permission_after_successful_constructor(self):
        engine = Engine(self.write_cli())
        self.cli.chmod(0o600)
        with self.assertRaises(EngineError) as caught:
            engine.estimation(output=self.root / "output")
        self.assertIsInstance(caught.exception.__cause__, PermissionError)
        self.assert_context(caught.exception, "estimation")

    @unittest.skipUnless(os.name == "posix", "POSIX executable script fixture")
    def test_real_invalid_utf8_during_constructor(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                self.write_cli(f"sys.{stream}.buffer.write(bytes([255]))\n")
                with self.assertRaises(EngineError) as caught:
                    Engine(self.cli)
                self.assertIsInstance(caught.exception.__cause__, UnicodeDecodeError)
                self.assertIn("UTF-8", str(caught.exception))
                self.assert_context(caught.exception)

    @unittest.skipUnless(os.name == "posix", "POSIX executable script fixture")
    def test_real_invalid_utf8_after_successful_constructor(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                self.write_cli(
                    "if command != 'version':\n"
                    f"    sys.{stream}.buffer.write(bytes([255]))\n"
                )
                engine = Engine(self.cli)
                with self.assertRaises(EngineError) as caught:
                    engine.estimation(output=self.root / "output")
                self.assertIsInstance(caught.exception.__cause__, UnicodeDecodeError)
                self.assert_context(caught.exception, "estimation")

    def test_resolution_os_errors_keep_type_cause_and_context(self):
        self.cli.write_text("synthetic fixture", encoding="utf-8")
        for target in ("Path.exists", "Path.resolve", "shutil.which"):
            for code in (errno.ENOENT, errno.EACCES, errno.EIO):
                with self.subTest(target=target, errno=code):
                    failure = OSError(code, "synthetic resolution failure", str(self.cli))
                    expected = EngineNotFoundError if code == errno.ENOENT else EngineError
                    with patch.dict(os.environ, {"MVS_CLI": ""}), \
                            patch(f"mvs.engine.{target}", side_effect=failure), \
                            patch("mvs.engine.subprocess.run") as run:
                        with self.assertRaises(expected) as caught:
                            Engine(None if target == "shutil.which" else self.cli)
                    run.assert_not_called()
                    self.assertIs(caught.exception.__cause__, failure)
                    self.assertIn("'version'", str(caught.exception))
                    self.assertIn(str(self.cli), str(caught.exception))

    def test_launch_os_errors_keep_type_cause_and_command(self):
        engine = self.mock_engine()
        for command in ("version", "estimation"):
            for code in (errno.ENOENT, errno.EACCES, errno.ENOEXEC, errno.ENOMEM, errno.EIO):
                with self.subTest(command=command, errno=code):
                    failure = OSError(code, "synthetic launch failure", str(self.cli))
                    expected = EngineNotFoundError if code == errno.ENOENT else EngineError
                    with patch("mvs.engine.subprocess.run", side_effect=failure):
                        with self.assertRaises(expected) as caught:
                            if command == "version":
                                Engine(self.cli)
                            else:
                                engine.estimation(output=self.root / "output")
                    self.assertIs(caught.exception.__cause__, failure)
                    self.assert_context(caught.exception, command)

    def test_programming_errors_are_not_wrapped(self):
        engine = self.mock_engine()
        for target in ("Path.exists", "subprocess.run"):
            for error_type in (ValueError, TypeError):
                with self.subTest(target=target, error_type=error_type):
                    failure = error_type("synthetic programming failure")
                    with patch(f"mvs.engine.{target}", side_effect=failure):
                        with self.assertRaises(error_type) as caught:
                            if target == "Path.exists":
                                Engine(self.cli)
                            else:
                                engine.estimation(output=self.root)
                    self.assertIs(caught.exception, failure)

    def test_os_error_outside_process_boundary_is_not_wrapped(self):
        engine = self.mock_engine()
        failure = OSError(errno.EIO, "synthetic parser failure")
        with patch("mvs.engine.subprocess.run", return_value=response("estimation")), \
                patch("mvs.engine.json.loads", side_effect=failure):
            with self.assertRaises(OSError) as caught:
                engine.estimation(output=self.root / "output")
        self.assertIs(caught.exception, failure)

    def test_structured_input_error_mapping_is_preserved(self):
        engine = self.mock_engine()
        for error_type in ("ArgumentException", "InvalidDataException", "FileNotFoundException", "FormatException"):
            with self.subTest(error_type=error_type):
                process = response("estimation", exitCode=1, status="error",
                                   error={"type": error_type, "message": "synthetic invalid input"})
                with patch("mvs.engine.subprocess.run", return_value=process):
                    with self.assertRaisesRegex(InputError, "synthetic invalid input"):
                        engine.estimation(output=self.root / "output")

    def test_structured_engine_error_mapping_is_preserved(self):
        engine = self.mock_engine()
        process = response("estimation", exitCode=1, status="error",
                           error={"type": "InvalidOperationException", "message": "synthetic engine error"})
        with patch("mvs.engine.subprocess.run", return_value=process):
            with self.assertRaisesRegex(EngineError, "synthetic engine error"):
                engine.estimation(output=self.root / "output")

    def test_native_argument_out_of_range_is_an_input_error(self):
        # Actual variance --min-measurements 1 serializes the concrete subclass
        # name rather than ArgumentException (round-18 pre-fix evidence).
        engine = self.mock_engine()
        process = response("variance", exitCode=1, status="error",
                           error={"type": "ArgumentOutOfRangeException",
                                  "message": "The minimum measurement count is out of range."})
        with patch("mvs.engine.subprocess.run", return_value=process):
            with self.assertRaisesRegex(InputError, "out of range"):
                engine.variance("synthetic.csv", output=self.root / "output", min_measurements=1)

    def test_scientific_diagnostic_mapping_is_preserved(self):
        engine = self.mock_engine()
        process = response("estimation", exitCode=2, status="diagnostic",
                           diagnostics=[{"code": "synthetic", "message": "inspect synthetic result"}])
        with patch("mvs.engine.subprocess.run", return_value=process):
            result = engine.estimation(output=self.root / "output")
            self.assertEqual((result.exit_code, result.status), (2, "diagnostic"))
            with self.assertRaises(ScientificDiagnostic) as caught:
                engine.estimation(output=self.root / "output", allow_diagnostic=False)
        self.assertEqual(caught.exception.result.raw, result.raw)
        self.assertEqual(str(caught.exception), "inspect synthetic result")

    def test_invalid_status_pair_is_still_rejected(self):
        engine = self.mock_engine()
        with patch("mvs.engine.subprocess.run", return_value=response("estimation", status="error")):
            with self.assertRaises(EngineCompatibilityError):
                engine.estimation(output=self.root / "output")

    def test_process_exit_mismatch_is_still_rejected(self):
        engine = self.mock_engine()
        process = response("estimation")
        process.returncode = 1
        with patch("mvs.engine.subprocess.run", return_value=process):
            with self.assertRaisesRegex(EngineError, "disagrees with JSON exitCode"):
                engine.estimation(output=self.root / "output")


if __name__ == "__main__":
    unittest.main()
