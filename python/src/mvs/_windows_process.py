"""Stdlib Windows process-tree owner. Requires Windows 10+ JOB_LIST support.

Job assignment is atomic with creation, with no post-start assignment fallback.
Native ABI and process-tree behaviour must additionally be tested on Windows.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes as w
import math
import os
import subprocess
import threading
import time

SIZE_T = ctypes.c_size_t


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR),
                ("lpDesktop", w.LPWSTR), ("lpTitle", w.LPWSTR),
                ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD),
                ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD),
                ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                ("dwFlags", w.DWORD), ("wShowWindow", w.WORD),
                ("cbReserved2", w.WORD), ("lpReserved2", ctypes.POINTER(w.BYTE)),
                ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE)]


class _STARTUPINFOEX(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFO), ("lpAttributeList", w.LPVOID)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE),
                ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", w.DWORD),
                ("MinimumWorkingSetSize", SIZE_T), ("MaximumWorkingSetSize", SIZE_T),
                ("ActiveProcessLimit", w.DWORD), ("Affinity", SIZE_T),
                ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC_LIMIT), ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", SIZE_T), ("JobMemoryLimit", SIZE_T),
                ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T)]


class _ACCOUNTING(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", w.DWORD), ("TotalProcesses", w.DWORD),
                ("ActiveProcesses", w.DWORD), ("TotalTerminatedProcesses", w.DWORD)]


def _kernel():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": (w.HANDLE, [w.LPVOID, w.LPCWSTR]),
        "SetInformationJobObject": (w.BOOL, [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]),
        "QueryInformationJobObject": (w.BOOL, [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)]),
        "GetCurrentProcess": (w.HANDLE, []),
        "DuplicateHandle": (w.BOOL, [w.HANDLE, w.HANDLE, w.HANDLE, ctypes.POINTER(w.HANDLE), w.DWORD, w.BOOL, w.DWORD]),
        "InitializeProcThreadAttributeList": (w.BOOL, [w.LPVOID, w.DWORD, w.DWORD, ctypes.POINTER(SIZE_T)]),
        "UpdateProcThreadAttribute": (w.BOOL, [w.LPVOID, w.DWORD, SIZE_T, w.LPVOID, SIZE_T, w.LPVOID, ctypes.POINTER(SIZE_T)]),
        "DeleteProcThreadAttributeList": (None, [w.LPVOID]),
        "CreateProcessW": (w.BOOL, [w.LPCWSTR, w.LPWSTR, w.LPVOID, w.LPVOID, w.BOOL, w.DWORD, w.LPVOID, w.LPCWSTR, ctypes.POINTER(_STARTUPINFOEX), ctypes.POINTER(_PROCESS_INFORMATION)]),
        "WaitForSingleObject": (w.DWORD, [w.HANDLE, w.DWORD]),
        "GetExitCodeProcess": (w.BOOL, [w.HANDLE, ctypes.POINTER(w.DWORD)]),
        "TerminateJobObject": (w.BOOL, [w.HANDLE, w.UINT]),
        "CloseHandle": (w.BOOL, [w.HANDLE]),
    }
    for name, (result, args) in signatures.items():
        fn = getattr(k, name)
        fn.restype, fn.argtypes = result, args
    return k


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def _environment(env):
    """Unicode environment, preserving caller variables without injection."""
    entries, seen = [], set()
    for key, value in env.items():
        if (not isinstance(key, str) or not isinstance(value, str) or not key
                or "=" in key or "\0" in key or "\0" in value):
            raise ValueError("Invalid Windows environment entry")
        folded = key.upper()
        if folded in seen:
            raise ValueError("Duplicate case-insensitive environment key")
        seen.add(folded)
        entries.append((key, value))
    entries.sort(key=lambda item: item[0].upper())
    return "\0".join(key + "=" + value for key, value in entries) + "\0\0"


class WindowsProcess:
    """Popen-like owner of one non-inheritable kill-on-close job.

    stdout/stderr must be open files with fileno(). close() kills descendants
    even when the original process has exited; callers should close in finally.
    """
    def __init__(self, argv, cwd, env, stdout, stderr):
        self._lock = threading.RLock()
        self._job = self._process = None
        self.returncode = self.pid = None
        self.args = list(argv)
        if os.name != "nt":
            raise OSError("WindowsProcess requires Windows 10 or newer")
        import msvcrt
        if not self.args or any(not isinstance(arg, str) or "\0" in arg for arg in self.args):
            raise ValueError("argv must contain non-NUL strings")
        cwd = os.fspath(cwd)
        if not isinstance(cwd, str) or "\0" in cwd:
            raise ValueError("cwd must be a non-NUL Unicode path")
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(self.args))
        environment = ctypes.create_unicode_buffer(_environment(env))
        self._k = k = _kernel()
        duplicates = []
        attributes = None
        initialized = False
        info = _PROCESS_INFORMATION()
        try:
            self._job = _check(k.CreateJobObjectW(None, None))
            limits = _EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
            _check(k.SetInformationJobObject(self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            current = k.GetCurrentProcess()
            with open(os.devnull, "rb") as stdin:
                for stream in (stdin, stdout, stderr):
                    target = w.HANDLE()
                    _check(k.DuplicateHandle(current, msvcrt.get_osfhandle(stream.fileno()),
                                             current, ctypes.byref(target), 0, True, 2))
                    duplicates.append(target.value)
            size = SIZE_T()
            # The sizing call is expected to return ERROR_INSUFFICIENT_BUFFER.
            if k.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size)) or ctypes.get_last_error() != 122:
                raise OSError("Cannot size Windows process attribute list")
            attributes = ctypes.create_string_buffer(size.value)
            _check(k.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(size)))
            initialized = True
            inherited = (w.HANDLE * 3)(*duplicates)
            jobs = (w.HANDLE * 1)(self._job)
            # PROC_THREAD_ATTRIBUTE_HANDLE_LIST and PROC_THREAD_ATTRIBUTE_JOB_LIST.
            _check(k.UpdateProcThreadAttribute(attributes, 0, 0x00020002,
                                               inherited, ctypes.sizeof(inherited), None, None))
            _check(k.UpdateProcThreadAttribute(attributes, 0, 0x0002000D,
                                               jobs, ctypes.sizeof(jobs), None, None))
            startup = _STARTUPINFOEX()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput, startup.StartupInfo.hStdError = duplicates
            startup.lpAttributeList = ctypes.cast(attributes, w.LPVOID)
            # EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT.
            # No shell, breakaway flag, or post-start job assignment.
            _check(k.CreateProcessW(self.args[0], command, None, None, True,
                                    0x00080000 | 0x00000400, environment, cwd,
                                    ctypes.byref(startup), ctypes.byref(info)))
            self._process = info.hProcess
            self.pid = info.dwProcessId
        except BaseException:
            self.close()
            raise
        finally:
            if info.hThread:
                k.CloseHandle(info.hThread)
            if initialized:
                k.DeleteProcThreadAttributeList(attributes)
            for handle in duplicates:
                k.CloseHandle(handle)

    def poll(self):
        with self._lock:
            if self.returncode is not None:
                return self.returncode
            if self._process is None:
                raise ValueError("Process handle is closed")
            result = self._k.WaitForSingleObject(self._process, 0)
            if result == 258:  # WAIT_TIMEOUT
                return None
            if result != 0:  # WAIT_OBJECT_0
                raise ctypes.WinError(ctypes.get_last_error())
            code = w.DWORD()
            _check(self._k.GetExitCodeProcess(self._process, ctypes.byref(code)))
            self.returncode = code.value
            return self.returncode

    def wait(self, timeout=None):
        if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
            raise ValueError("timeout must be finite and nonnegative")
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            result = self.poll()
            if result is not None:
                return result
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise subprocess.TimeoutExpired(self.args, timeout)
            time.sleep(0.01 if remaining is None else min(0.01, remaining))

    def terminate_tree(self):
        """Terminate all job members and allow at most five seconds for exit."""
        with self._lock:
            if self._job is None:
                return
            _check(self._k.TerminateJobObject(self._job, 1))
        deadline = time.monotonic() + 5.0
        while True:
            with self._lock:
                if self._job is None:
                    return
                accounting = _ACCOUNTING()
                _check(self._k.QueryInformationJobObject(self._job, 1, ctypes.byref(accounting),
                                                        ctypes.sizeof(accounting), None))
                # Job accounting may reach zero before the original process
                # handle is signaled. Both conditions are required before the
                # caller can treat cleanup as complete and inspect its exit code.
                if not accounting.ActiveProcesses and self.poll() is not None:
                    return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(self.args, 5.0)
            time.sleep(min(0.01, remaining))

    def close(self):
        """Release owned handles; closing the job kills remaining members."""
        with self._lock:
            if self._job is not None:
                self._k.CloseHandle(self._job)
                self._job = None
            if self._process is not None:
                self._k.CloseHandle(self._process)
                self._process = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
