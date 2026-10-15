"""Portable contracts plus Windows-only ABI/native smoke checks.

Skipped native checks are not evidence that Windows runtime works.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from mvs._windows_process import (
    WindowsProcess, _environment, _STARTUPINFO, _STARTUPINFOEX,
    _PROCESS_INFORMATION, _BASIC_LIMIT, _EXTENDED_LIMIT, _ACCOUNTING,
)


class EnvironmentContract(unittest.TestCase):
    def test_unicode_preserves_system_root_and_terminates(self):
        self.assertEqual(_environment({"z": "雪", "SystemRoot": r"C:\Windows", "A": "a=b"}),
                         "A=a=b\0SystemRoot=C:\\Windows\0z=雪\0\0")
        self.assertEqual(_environment({}), "\0\0")
        self.assertNotIn("SystemRoot", _environment({"A": "value"}))

    def test_rejects_invalid_environment(self):
        for env in ({"a": "x", "A": "y"}, {"": "x"}, {"x=y": "z"},
                    {"x": "a\0b"}, {"a\0b": "x"}, {"x": 1}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                _environment(env)

    def test_platform_or_invalid_request_guard(self):
        if os.name == "nt":
            with self.assertRaises(ValueError):
                WindowsProcess([], ".", {}, None, None)
        else:
            with self.assertRaises(OSError):
                WindowsProcess(["anything"], ".", {}, None, None)

    def test_bounded_wait_and_cached_exit(self):
        process = object.__new__(WindowsProcess)
        process._lock = threading.RLock()
        process._job = process._process = None
        process.args = ["mock"]
        process.returncode = 259  # Real exit code 259 must not be mistaken for STILL_ACTIVE.
        self.assertEqual(process.wait(0), 259)
        process.poll = lambda: None
        with self.assertRaises(subprocess.TimeoutExpired):
            process.wait(0)
        for timeout in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                process.wait(timeout)


@unittest.skipUnless(os.name == "nt" and ctypes.sizeof(ctypes.c_void_p) == 8,
                     "Requires real Windows x64; not validated by Linux tests")
class WindowsNativeContract(unittest.TestCase):
    def test_abi_sizes(self):
        self.assertEqual(ctypes.sizeof(_STARTUPINFO), 104)
        self.assertEqual(ctypes.sizeof(_STARTUPINFOEX), 112)
        self.assertEqual(ctypes.sizeof(_PROCESS_INFORMATION), 24)
        self.assertEqual(ctypes.sizeof(_BASIC_LIMIT), 64)
        self.assertEqual(ctypes.sizeof(_EXTENDED_LIMIT), 144)
        self.assertEqual(ctypes.sizeof(_ACCOUNTING), 48)

    def test_native_unicode_arguments_environment_and_exit(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "stdout"
            with output.open("wb") as out, (Path(root) / "stderr").open("wb") as err:
                env = dict(os.environ, MVS_TEST_VALUE="雪")
                code = "import os,sys; assert sys.argv[1] == 'a b\\\"c'; assert os.environ['MVS_TEST_VALUE'] == '雪'; print('ok'); sys.exit(2)"
                proc = WindowsProcess([sys.executable, "-c", code, 'a b"c'], root, env, out, err)
                try:
                    self.assertGreater(proc.pid, 0)
                    self.assertEqual(proc.wait(10), 2)
                    proc.terminate_tree()  # Must also work after leader exits.
                    self.assertEqual(proc.returncode, 2)
                finally:
                    proc.close()
                    proc.close()
            self.assertEqual(output.read_text().strip(), "ok")

    def test_descendant_termination_after_leader_exit(self):
        # A surviving grandchild must remain in the job after the leader exits.
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "stdout"
            with output.open("wb") as out, open(os.devnull, "wb") as err:
                code = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(p.pid,flush=True)"
                proc = WindowsProcess([sys.executable, "-c", code], root, dict(os.environ), out, err)
                child = None
                try:
                    self.assertEqual(proc.wait(10), 0)
                    child = kernel.OpenProcess(0x00100000, False, int(output.read_text().strip()))
                    self.assertTrue(child)
                    self.assertEqual(kernel.WaitForSingleObject(child, 0), 258)
                    proc.terminate_tree()
                    self.assertEqual(kernel.WaitForSingleObject(child, 5000), 0)
                finally:
                    proc.close()
                    if child:
                        kernel.CloseHandle(child)

    def test_native_timeout_and_termination(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.devnull, "wb") as out:
                proc = WindowsProcess([sys.executable, "-c", "import time; time.sleep(60)"],
                                      root, dict(os.environ), out, out)
                try:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        proc.wait(0.01)
                    proc.terminate_tree()
                    self.assertIsNotNone(proc.poll())
                finally:
                    proc.close()


if __name__ == "__main__":
    unittest.main()
