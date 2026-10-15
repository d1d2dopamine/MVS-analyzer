"""Fail-closed local-NTFS primitives for the Windows workflow backend.

This module is importable on non-Windows hosts, but its operations are not.
Security boundary: a trusted Windows host and trusted account owning the workspace.
Component checks are not a race-proof namespace sandbox against that account or
an administrator. Windows integration, crash and adversarial tests are required;
Linux import/compile tests cannot establish the Windows durability guarantees.

API references:
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw
https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-string-format
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
from contextlib import contextmanager
from functools import lru_cache
import ntpath
import os
import re
import uuid


class BusyError(OSError):
    """The persistent workflow lock is already open by another process."""


_REPARSE = 0x400
_DIRECTORY = 0x10
_OPEN_REPARSE = 0x00200000
_BACKUP = 0x02000000
_READ = 0x80000000
_WRITE = 0x40000000
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$", re.I)


class _Info(ctypes.Structure):
    _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME),
                ("accessed", w.FILETIME), ("written", w.FILETIME),
                ("volume", w.DWORD), ("size_high", w.DWORD),
                ("size_low", w.DWORD), ("links", w.DWORD),
                ("index_high", w.DWORD), ("index_low", w.DWORD)]


class _SA(ctypes.Structure):
    _fields_ = [("length", w.DWORD), ("descriptor", ctypes.c_void_p),
                ("inherit", w.BOOL)]


class _ACL(ctypes.Structure):
    _fields_ = [("revision", w.BYTE), ("reserved", w.BYTE),
                ("size", w.WORD), ("count", w.WORD), ("reserved2", w.WORD)]


class _API:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows file backend requires Windows")
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.a = ctypes.WinDLL("advapi32", use_last_error=True)
        ptr = ctypes.c_void_p
        dwordp = ctypes.POINTER(w.DWORD)
        def bind(dll, name, args, result):
            fn = getattr(dll, name)
            fn.argtypes, fn.restype = args, result
            setattr(self, name, fn)
        bind(self.k, "CreateFileW", [w.LPCWSTR, w.DWORD, w.DWORD, ptr, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE)
        bind(self.k, "CloseHandle", [w.HANDLE], w.BOOL)
        bind(self.k, "GetFileAttributesW", [w.LPCWSTR], w.DWORD)
        bind(self.k, "GetFileInformationByHandle", [w.HANDLE, ctypes.POINTER(_Info)], w.BOOL)
        bind(self.k, "GetFileType", [w.HANDLE], w.DWORD)
        bind(self.k, "ReadFile", [w.HANDLE, ptr, w.DWORD, dwordp, ptr], w.BOOL)
        bind(self.k, "WriteFile", [w.HANDLE, ptr, w.DWORD, dwordp, ptr], w.BOOL)
        bind(self.k, "FlushFileBuffers", [w.HANDLE], w.BOOL)
        bind(self.k, "MoveFileExW", [w.LPCWSTR, w.LPCWSTR, w.DWORD], w.BOOL)
        bind(self.k, "DeleteFileW", [w.LPCWSTR], w.BOOL)
        bind(self.k, "CreateDirectoryW", [w.LPCWSTR, ptr], w.BOOL)
        bind(self.k, "GetDriveTypeW", [w.LPCWSTR], w.UINT)
        bind(self.k, "GetVolumeInformationW", [w.LPCWSTR, w.LPWSTR, w.DWORD, dwordp, dwordp, dwordp, w.LPWSTR, w.DWORD], w.BOOL)
        bind(self.k, "QueryDosDeviceW", [w.LPCWSTR, w.LPWSTR, w.DWORD], w.DWORD)
        bind(self.k, "GetCurrentProcess", [], w.HANDLE)
        bind(self.k, "LocalFree", [ptr], ptr)
        bind(self.a, "OpenProcessToken", [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)], w.BOOL)
        bind(self.a, "GetTokenInformation", [w.HANDLE, ctypes.c_int, ptr, w.DWORD, dwordp], w.BOOL)
        bind(self.a, "ConvertSidToStringSidW", [ptr, ctypes.POINTER(w.LPWSTR)], w.BOOL)
        bind(self.a, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [w.LPCWSTR, w.DWORD, ctypes.POINTER(ptr), dwordp], w.BOOL)
        bind(self.a, "GetNamedSecurityInfoW", [w.LPCWSTR, ctypes.c_int, w.DWORD, ctypes.POINTER(ptr), ctypes.POINTER(ptr), ctypes.POINTER(ptr), ctypes.POINTER(ptr), ctypes.POINTER(ptr)], w.DWORD)
        bind(self.a, "GetSecurityDescriptorControl", [ptr, ctypes.POINTER(w.WORD), dwordp], w.BOOL)
        bind(self.a, "GetAce", [ptr, w.DWORD, ctypes.POINTER(ptr)], w.BOOL)
        bind(self.a, "IsValidSid", [ptr], w.BOOL)


@lru_cache(maxsize=1)
def _api():
    return _API()


def _error(path=None, code=None):
    error = ctypes.WinError(ctypes.get_last_error() if code is None else code)
    if path is not None:
        error.filename = os.fspath(path)
    return error


def _check(ok, path=None):
    if not ok:
        raise _error(path)


def _lexical(path):
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or "\0" in raw:
        raise ValueError("A nonempty text path is required")
    raw = raw.replace("/", "\\")
    if raw.startswith("\\"):
        raise ValueError("UNC, device and root-relative paths are forbidden")
    drive, tail = ntpath.splitdrive(raw)
    if drive and (not re.fullmatch(r"[A-Za-z]:", drive) or not tail.startswith("\\")):
        raise ValueError("Drive-relative and device paths are forbidden")
    for part in tail.split("\\"):
        if not part:
            continue
        if part in (".", "..") or part.endswith((".", " ")):
            raise ValueError("Ambiguous path component")
        if any(ord(c) < 32 or c in '<>:"|?*' for c in part):
            raise ValueError("Invalid path component or alternate data stream")
        if _RESERVED.fullmatch(part.split(".", 1)[0].rstrip(" ")):
            raise ValueError("Reserved Windows filename")
    absolute = ntpath.abspath(raw)
    if len(absolute) >= 248:
        raise ValueError("Long paths are not supported by this backend")
    return absolute


def validate_path(path):
    """Reject aliases/reparse points and require a directly mounted fixed NTFS disk."""
    name = _lexical(path)
    api = _api()
    drive, tail = ntpath.splitdrive(name)
    if not re.fullmatch(r"[A-Za-z]:", drive):
        raise ValueError("A local drive is required")
    root = drive + "\\"
    if api.GetDriveTypeW(root) != 3:  # DRIVE_FIXED
        raise ValueError("Only fixed local NTFS volumes are supported")
    device = ctypes.create_unicode_buffer(32768)
    _check(api.QueryDosDeviceW(drive, device, len(device)), name)
    if not re.fullmatch(r"\\Device\\HarddiskVolume[0-9]+", device.value, re.I):
        raise ValueError("Drive aliases and redirected drives are unsupported")
    filesystem = ctypes.create_unicode_buffer(64)
    _check(api.GetVolumeInformationW(root, None, 0, None, None, None, filesystem, len(filesystem)), name)
    if filesystem.value.upper() != "NTFS":
        raise ValueError("Only NTFS is supported")
    current = root
    components = [p for p in tail.split("\\") if p]
    for component in [None] + components:
        if component is not None:
            current = ntpath.join(current, component)
        attributes = api.GetFileAttributesW(current)
        if attributes == 0xFFFFFFFF:
            code = ctypes.get_last_error()
            if code in (2, 3):
                break
            raise _error(current, code)
        if attributes & _REPARSE:
            raise ValueError("Reparse points are forbidden")
        if current != name and not attributes & _DIRECTORY:
            raise ValueError("A parent component is not a directory")
    return name


@contextmanager
def _handle(path, access, sharing, disposition, security=None):
    api = _api()
    handle = api.CreateFileW(path, access, sharing, security, disposition,
                             _OPEN_REPARSE | _BACKUP, None)
    if handle == _INVALID_HANDLE:
        raise _error(path)
    try:
        yield handle
    finally:
        _check(api.CloseHandle(handle), path)


def _info(handle):
    api = _api()
    info = _Info()
    _check(api.GetFileInformationByHandle(handle, ctypes.byref(info)))
    if api.GetFileType(handle) != 1 or info.attributes & (_REPARSE | _DIRECTORY):
        raise ValueError("A regular disk file is required")
    if info.links != 1:
        raise ValueError("Hard-linked files are forbidden")
    size = (info.size_high << 32) | info.size_low
    identity = (info.volume, info.index_high, info.index_low, info.attributes,
                info.links, size, info.created.dwHighDateTime, info.created.dwLowDateTime,
                info.written.dwHighDateTime, info.written.dwLowDateTime)
    return size, identity


def read_regular(path, limit):
    """Read a bounded file while denying all concurrent write/delete opens."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("Invalid file size limit")
    name = validate_path(path)
    api = _api()
    with _handle(name, _READ, 1, 3) as handle:  # SHARE_READ, OPEN_EXISTING
        size, before = _info(handle)
        if size > limit:
            raise ValueError("File exceeds size limit")
        chunks, total = [], 0
        while True:
            capacity = min(1024 * 1024, limit - total + 1)
            buffer = ctypes.create_string_buffer(capacity)
            count = w.DWORD()
            _check(api.ReadFile(handle, buffer, capacity, ctypes.byref(count), None), name)
            if not count.value:
                break
            total += count.value
            if total > limit:
                raise ValueError("File exceeds size limit")
            chunks.append(buffer.raw[:count.value])
        if _info(handle)[1] != before or total != size:
            raise ValueError("File changed during read")
        return b"".join(chunks)


def _write(handle, data, path):
    if not isinstance(data, bytes):
        raise TypeError("File contents must be bytes")
    api = _api()
    offset = 0
    while offset < len(data):
        chunk = data[offset:offset + 1024 * 1024]
        buffer = ctypes.create_string_buffer(chunk)
        count = w.DWORD()
        _check(api.WriteFile(handle, buffer, len(chunk), ctypes.byref(count), None), path)
        if not count.value:
            raise OSError("WriteFile made no progress")
        offset += count.value
    _check(api.FlushFileBuffers(handle), path)


def snapshot_bytes(path, data):
    """Create a durable new file; never truncate or replace an existing path."""
    name = validate_path(path)
    with _handle(name, _WRITE, 0, 1) as handle:  # CREATE_NEW
        _info(handle)
        _write(handle, data, name)


def commit_json_bytes(path, data):
    """Flush a same-directory temporary file, then publish without replacement.

    MoveFileExW uses WRITE_THROUGH only. There is deliberately no copy, replace,
    or non-atomic fallback. This is not a claim of power-loss proof publication.
    """
    name = validate_path(path)
    temporary = ntpath.join(ntpath.dirname(name), ".mvs-" + uuid.uuid4().hex + ".tmp")
    created = False
    try:
        with _handle(validate_path(temporary), _WRITE, 0, 1) as handle:
            created = True
            _info(handle)
            _write(handle, data, temporary)
        validate_path(name)
        _check(_api().MoveFileExW(temporary, name, 0x8), name)  # WRITE_THROUGH
        created = False
    finally:
        if created:
            # Delete only this operation's unpredictable temporary name. Failure
            # is fail-closed; a leftover can be inspected, never reused.
            _check(_api().DeleteFileW(temporary), temporary)


@contextmanager
def lock(path):
    """Acquire a persistent exclusive handle once, without waiting or unlinking."""
    name = validate_path(path)
    api = _api()
    handle = api.CreateFileW(name, _READ | _WRITE, 0, None, 4,
                             _OPEN_REPARSE | _BACKUP, None)  # OPEN_ALWAYS
    if handle == _INVALID_HANDLE:
        code = ctypes.get_last_error()
        if code in (32, 33):
            raise BusyError("Workspace is busy") from _error(name, code)
        raise _error(name, code)
    try:
        _info(handle)
        yield
    finally:
        _check(api.CloseHandle(handle), name)


def _sid_text(sid):
    api = _api()
    if not sid or not api.IsValidSid(sid):
        raise ValueError("Invalid security identifier")
    text = w.LPWSTR()
    _check(api.ConvertSidToStringSidW(sid, ctypes.byref(text)))
    try:
        return text.value
    finally:
        api.LocalFree(ctypes.cast(text, ctypes.c_void_p))


def _current_sid():
    api = _api()
    token = w.HANDLE()
    _check(api.OpenProcessToken(api.GetCurrentProcess(), 0x8, ctypes.byref(token)))
    try:
        size = w.DWORD()
        result = api.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if result or ctypes.get_last_error() != 122 or not size.value:
            raise OSError("Cannot size current-user token")
        buffer = ctypes.create_string_buffer(size.value)
        _check(api.GetTokenInformation(token, 1, buffer, size.value, ctypes.byref(size)))
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        return _sid_text(sid)
    finally:
        _check(api.CloseHandle(token))


def _verify_private(name, user):
    """Accept only a protected DACL granting access to this user and SYSTEM."""
    api = _api()
    owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    result = api.GetNamedSecurityInfoW(name, 1, 5, ctypes.byref(owner), None,
                                      ctypes.byref(dacl), None, ctypes.byref(descriptor))
    if result:
        raise _error(name, result)
    try:
        if _sid_text(owner) not in (user, "S-1-5-18") or not dacl:
            raise ValueError("Workspace must have a private owner and non-null DACL")
        control, revision = w.WORD(), w.DWORD()
        _check(api.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)))
        if not control.value & 0x1000:  # SE_DACL_PROTECTED
            raise ValueError("Existing workspace ACL must disable inheritance")
        acl = ctypes.cast(dacl, ctypes.POINTER(_ACL)).contents
        allowed_user = False
        for index in range(acl.count):
            ace = ctypes.c_void_p()
            _check(api.GetAce(dacl, index, ctypes.byref(ace)))
            header = (w.BYTE * 4).from_address(ace.value)
            ace_size = header[2] | (header[3] << 8)
            if header[0] not in (0, 1) or ace_size < 12:
                raise ValueError("Unsupported workspace ACL entry")
            sid = _sid_text(ace.value + 8)
            if header[0] == 0:
                if sid not in (user, "S-1-5-18"):
                    raise ValueError("Workspace grants access to another identity")
                if sid == user and not header[1] & 0x8:  # not INHERIT_ONLY
                    allowed_user = True
        if not allowed_user:
            raise ValueError("Workspace does not grant access to the current user")
    finally:
        api.LocalFree(descriptor)


def private_mkdir(path, parents=False, exist_ok=False):
    """Create directories with explicit protected current-user/SYSTEM-only ACLs.

    Existing directories are never chmod'ed or granted additional rights. The
    requested directory must already satisfy this strict ACL or the call fails.
    Missing ancestors requested by parents=True get the same explicit ACL.
    """
    name = validate_path(path)
    api, user = _api(), _current_sid()
    attributes = api.GetFileAttributesW(name)
    if attributes != 0xFFFFFFFF:
        if not exist_ok:
            raise FileExistsError(name)
        if attributes & _REPARSE or not attributes & _DIRECTORY:
            raise ValueError("Workspace is not a plain directory")
        _verify_private(name, user)
        return
    code = ctypes.get_last_error()
    if code not in (2, 3):
        raise _error(name, code)
    parent = ntpath.dirname(name)
    if parents:
        parent_attributes = api.GetFileAttributesW(parent)
        if parent_attributes == 0xFFFFFFFF:
            code = ctypes.get_last_error()
            if code not in (2, 3):
                raise _error(parent, code)
            private_mkdir(parent, parents=True, exist_ok=True)
    descriptor = ctypes.c_void_p()
    # OI/CI propagate private access to ordinary subsequently created children;
    # P blocks inherited grants from a broadly accessible parent directory.
    sddl = f"O:{user}D:P(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)"
    _check(api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None), name)
    try:
        security = _SA(ctypes.sizeof(_SA), descriptor, False)
        if not api.CreateDirectoryW(name, ctypes.byref(security)):
            code = ctypes.get_last_error()
            if code != 183 or not exist_ok:
                raise _error(name, code)
        validate_path(name)
        attributes = api.GetFileAttributesW(name)
        if attributes == 0xFFFFFFFF:
            raise _error(name)
        if not attributes & _DIRECTORY:
            raise ValueError("Workspace is not a directory")
        _verify_private(name, user)
    finally:
        api.LocalFree(descriptor)
