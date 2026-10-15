"""Opt-in real Win32 acceptance gates; never emulate Windows on a Linux host.

Run on Windows: python -m unittest discover -s python/tests -p test_windows_workflow.py -v
All writes and spawned processes belong to a TemporaryDirectory fixture.
Native/MCP acceptance is tools/test_windows_workflow.py (see its --help).
"""
from __future__ import annotations
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src"


def env():
    return dict(os.environ, PYTHONPATH=str(SOURCE) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def eventually(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.03)
    raise AssertionError("Owned fixture did not reach expected state before deadline")


@unittest.skipUnless(sys.platform == "win32", "Requires actual Windows Win32/NTFS runtime")
class WindowsFilesystemTests(unittest.TestCase):
    def setUp(self):
        from mvs import _windows_files
        self.fs = _windows_files
        self.tmp = tempfile.TemporaryDirectory(prefix="mvs-win-gate-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def child(self, code, *args):
        return subprocess.run([sys.executable, "-c", code, *map(str, args)],
                              env=env(), capture_output=True, text=True, timeout=15)

    def test_lock_excludes_same_and_other_process(self):
        path = self.root / "gate.lock"
        with self.fs.lock(path):
            with self.assertRaises(self.fs.BusyError):
                with self.fs.lock(path):
                    self.fail("Same-process lock overlap admitted")
            result = self.child("from mvs._windows_files import lock,BusyError; import sys\ntry:\n with lock(sys.argv[1]): pass\nexcept BusyError: sys.exit(23)", path)
            self.assertEqual(result.returncode, 23, result.stderr)
        with self.fs.lock(path):
            pass

    def test_lock_handle_not_inherited(self):
        path = self.root / "gate.lock"
        sleeper = None
        try:
            with self.fs.lock(path):
                sleeper = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(20)"], close_fds=False)
            result = self.child("from mvs._windows_files import lock; import sys\nwith lock(sys.argv[1]): pass", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(sleeper.poll())
        finally:
            if sleeper is not None:
                sleeper.terminate(); sleeper.wait(timeout=5)

    def test_two_writers_publish_complete_immutable_record(self):
        path = self.root / "record.json"
        start = self.root / "start"
        code = '''import json,pathlib,sys,time
from mvs._windows_files import commit_json_bytes
path,start=map(pathlib.Path,sys.argv[1:3]); deadline=time.monotonic()+10
while not start.exists():
 if time.monotonic()>deadline: raise TimeoutError('barrier')
 time.sleep(.005)
try: commit_json_bytes(path,json.dumps({'writer':sys.argv[3],'payload':sys.argv[3]*200000}).encode())
except FileExistsError: sys.exit(17)
'''
        children = [subprocess.Popen([sys.executable, "-c", code, str(path), str(start), token], env=env(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) for token in ("A", "B")]
        try:
            start.touch()
            deadline = time.monotonic() + 15
            observed = []
            while any(c.poll() is None for c in children):
                if time.monotonic() > deadline:
                    self.fail("Publication race exceeded deadline")
                if path.exists():
                    # A visible final name must always contain a complete JSON record.
                    observed.append(json.loads(self.fs.read_regular(path, 1000000)))
                time.sleep(.002)
            codes = [c.wait(timeout=2) for c in children]
            self.assertEqual(sorted(codes), [0, 17], [c.stderr.read().decode() for c in children])
            final = json.loads(self.fs.read_regular(path, 1000000))
            self.assertEqual(final["payload"], final["writer"] * 200000)
            self.assertTrue(all(item == final for item in observed))
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                self.fs.commit_json_bytes(path, b'{"replacement":true}')
            self.assertEqual(path.read_bytes(), before)
        finally:
            for child in children:
                if child.poll() is None: child.kill()
                child.wait(timeout=5)
                child.stderr.close()

    def test_snapshot_no_overwrite_and_bounded_read(self):
        path = self.root / "snapshot"
        self.fs.snapshot_bytes(path, b"original")
        with self.assertRaises(FileExistsError): self.fs.snapshot_bytes(path, b"changed")
        self.assertEqual(self.fs.read_regular(path, 8), b"original")
        with self.assertRaises((ValueError, OSError)): self.fs.read_regular(path, 7)

    def test_reject_windows_aliases(self):
        cases = [r"\\server\share\record", r"\\?\C:\record", r"\\.\NUL",
                 str(self.root / "file:stream"), str(self.root / "trailing."),
                 str(self.root / "trailing "), str(self.root / "NUL"),
                 str(self.root / "CON.txt"), str(self.root / "COM1"), str(self.root / "LPT9.txt")]
        for value in cases:
            with self.subTest(path=value), self.assertRaises((ValueError, OSError)):
                self.fs.validate_path(Path(value))

    def test_reject_junction(self):
        target = self.root / "target"; target.mkdir()
        junction = self.root / "junction"
        result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            with self.assertRaises((ValueError, OSError)):
                self.fs.validate_path(junction / "record.json")
        finally:
            junction.rmdir()  # Remove only our junction, never traverse its target.

    def test_existing_broad_acl_workspace_is_rejected_without_repair(self):
        folder = self.root / "ordinary"; folder.mkdir()
        # A normal inherited ACL must not be silently changed by this backend.
        script = "(Get-Acl -LiteralPath $env:MVS_ACL_TEST_PATH).Sddl"
        def descriptor():
            r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                env=dict(os.environ, MVS_ACL_TEST_PATH=str(folder)), capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()
        before = descriptor()
        with self.assertRaises(ValueError): self.fs.private_mkdir(folder, exist_ok=True)
        self.assertEqual(descriptor(), before)
        private = self.root / "owned"; self.fs.private_mkdir(private)
        self.fs.private_mkdir(private, exist_ok=True)

    def test_private_workspace_acl(self):
        folder = self.root / "private"
        self.fs.private_mkdir(folder)
        # PowerShell returns numeric SIDs and inheritance flags, independent of locale.
        script = "$a=Get-Acl -LiteralPath $env:MVS_ACL_TEST_PATH; [pscustomobject]@{Protected=$a.AreAccessRulesProtected;User=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; Rules=@($a.Access|ForEach-Object{[pscustomobject]@{Sid=$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value;Inherited=$_.IsInherited;Type=$_.AccessControlType.ToString()}})}|ConvertTo-Json -Depth 4 -Compress"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env=dict(os.environ, MVS_ACL_TEST_PATH=str(folder)), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        acl = json.loads(result.stdout)
        self.assertTrue(acl["Protected"])
        rules = acl["Rules"]
        self.assertTrue(rules)
        self.assertTrue(all(not rule["Inherited"] for rule in rules))
        self.assertTrue(all(rule["Type"] != "Allow" or rule["Sid"] in {acl["User"], "S-1-5-18"} for rule in rules))
        self.assertTrue(any(rule["Type"] == "Allow" and rule["Sid"] == acl["User"] for rule in rules))
        self.fs.private_mkdir(folder, exist_ok=True)  # Existing private ACL is accepted.


@unittest.skipUnless(sys.platform == "win32", "Requires actual Windows Job Object runtime")
class WindowsProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mvs-job-gate-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        self.kernel.OpenProcess.restype = ctypes.c_void_p
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.kernel.WaitForSingleObject.restype = ctypes.c_ulong
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel.TerminateProcess.restype = ctypes.c_int

    def tree(self):
        script = self.root / "tree.py"
        script.write_text("import pathlib,subprocess,sys,time,os\nroot=pathlib.Path(sys.argv[1])\nchild=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n(root/'pids.tmp').write_text(__import__('json').dumps([os.getpid(),child.pid]));(root/'pids.tmp').replace(root/'pids.json')\ntime.sleep(60)\n")
        return script

    def owned_handles(self):
        marker = self.root / "pids.json"
        eventually(lambda: marker.exists() and marker.stat().st_size > 0)
        # Open handles while processes are alive, so PID reuse cannot fake cleanup.
        handles = []
        for pid in json.loads(marker.read_text()):
            handle = self.kernel.OpenProcess(0x00100000 | 0x0001, False, pid)
            self.assertTrue(handle, ctypes.get_last_error())
            handles.append(handle)
            self.addCleanup(self.cleanup_owned_handle, handle)
        return handles

    def cleanup_owned_handle(self, handle):
        # Failure cleanup targets the retained handle to this fixture process,
        # never an enumerated process name or a possibly recycled PID.
        try:
            if self.kernel.WaitForSingleObject(handle, 0) == 258:
                self.kernel.TerminateProcess(handle, 1)
                self.kernel.WaitForSingleObject(handle, 5000)
        finally:
            self.kernel.CloseHandle(handle)

    def assert_terminated(self, handles):
        for handle in handles:
            self.assertEqual(self.kernel.WaitForSingleObject(handle, 10000), 0, "Owned descendant survived job termination")

    def test_cancel_kills_child_and_grandchild(self):
        from mvs._windows_process import WindowsProcess
        with (self.root / "stdout").open("wb") as out, (self.root / "stderr").open("wb") as err:
            child = WindowsProcess([sys.executable, str(self.tree()), str(self.root)], cwd=self.root, env=env(), stdout=out, stderr=err)
            try:
                handles = self.owned_handles()
                child.terminate_tree(); child.wait(timeout=5)
                self.assert_terminated(handles)
            finally:
                child.close()

    def test_coordinator_death_closes_job_and_descendants(self):
        script = self.tree()
        code = '''from mvs._windows_process import WindowsProcess
import pathlib,sys,time
root=pathlib.Path(sys.argv[1])
with (root/'stdout').open('wb') as out,(root/'stderr').open('wb') as err:
 child=WindowsProcess([sys.executable,sys.argv[2],str(root)],cwd=root,env=__import__('os').environ,stdout=out,stderr=err)
 time.sleep(60)
'''
        coordinator = subprocess.Popen([sys.executable, "-c", code, str(self.root), str(script)], env=env())
        try:
            handles = self.owned_handles()
            coordinator.kill(); coordinator.wait(timeout=5)
            self.assert_terminated(handles)
        finally:
            if coordinator.poll() is None: coordinator.kill()
            coordinator.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
