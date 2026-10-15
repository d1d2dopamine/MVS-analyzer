"""Bounded local workflow, not a statistical engine or external registrar.

Linux and experimental Windows local NTFS workflow. The configured host, backend and workspace owner
are trusted; cooperating clients cannot overwrite records or escape path roots.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any

SCHEMA = "mvs-workflow-result/v1"
PROTOCOL_SCHEMA = "mvs-local-protocol/v1"
READINESS = {"scope": "project_release_readiness", "status": "no_go",
             "basis": "MVS-BENCH-1.2.0 development", "independentConfirmatoryValidation": False}
EXPOSURES = {"unknown", "previously_inspected", "not_inspected_declared"}
MAX_JSON = 2 * 1024 * 1024
MAX_INPUT = 100 * 1024 * 1024
MAX_CALIBRATION = 16 * 1024 * 1024
MAX_ARTIFACT = 32 * 1024 * 1024
MAX_WORKSPACE = 512 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


class WorkflowError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(data: bytes | str) -> Any:
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("Duplicate JSON key")
            result[k] = v
        return result
    def constant(_):
        raise ValueError("Nonfinite JSON number")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds supported bounds") from exc


def envelope(data=None, *, status="completed", native_exit=None, error=None):
    return {"schemaVersion": SCHEMA, "execution": {"status": status, "nativeExitCode": native_exit,
            "outcome": "completed_with_diagnostic" if status == "completed" and native_exit == 2 else status},
            "scientificReadiness": dict(READINESS), "data": data, "error": error}


def _id(value: Any) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise WorkflowError("invalid_id", "Identifiers require 1–64 ASCII letters, digits, hyphens or underscores.")
    return value


def _fields(params, required, optional=()):
    if not isinstance(params, dict) or set(params) - set(required) - set(optional) or set(required) - set(params):
        raise WorkflowError("invalid_request", "Missing or unknown request fields.")
    if len(canonical(params)) > 32768:
        raise WorkflowError("request_too_large", "Request exceeds 32 KiB.")


def _bool(value):
    if type(value) is not bool:
        raise WorkflowError("invalid_request", "Boolean settings must be JSON booleans.")
    return value


def _windows():
    return sys.platform == "win32"


def _mkdir(path, *, parents=False, exist_ok=False):
    if _windows():
        from ._windows_files import private_mkdir
        private_mkdir(path, parents=parents, exist_ok=exist_ok)
    else:
        path.mkdir(mode=0o700, parents=parents, exist_ok=exist_ok)


def _safe_components(path: Path):
    if _windows():
        from ._windows_files import validate_path
        try: validate_path(path)
        except ValueError as exc: raise WorkflowError("unsafe_path", "Windows workflow requires unaliased local NTFS paths without reparse points.") from exc
        return
    for node in (path, *path.parents):
        if node.is_symlink():
            raise WorkflowError("unsafe_path", "Symbolic links are not supported in workflow paths.")


def _read_regular(path: Path, limit: int) -> bytes:
    _safe_components(path)
    if _windows():
        from ._windows_files import read_regular
        return read_regular(path, limit)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise WorkflowError("input_unavailable", "Required local file is unavailable.") from exc
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise WorkflowError("invalid_file", "Only bounded regular files are supported.")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise WorkflowError("input_changed", "Input changed during snapshot capture or exceeded its limit.")
    return data


def _snapshot_bytes(path: Path, data: bytes):
    if _windows():
        from ._windows_files import snapshot_bytes
        return snapshot_bytes(path, data)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def _new_json(path: Path, value: Any):
    """Commit one complete file without replacing an existing record."""
    _safe_components(path.parent)
    if _windows():
        from ._windows_files import commit_json_bytes
        return commit_json_bytes(path, canonical(value))
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)  # Atomic no-replace commit on the supported local filesystem.
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)  # Only the temporary file created by this call.


class WorkflowService:
    def __init__(self, engine, read_root, work_root, timeout_seconds=120):
        if not (sys.platform.startswith("linux") or _windows()):
            raise WorkflowError("unsupported_platform", "This local workflow supports Linux and experimental Windows 10+ local NTFS only.")
        if _windows():
            import struct
            if struct.calcsize("P") != 8:
                raise WorkflowError("unsupported_platform", "Windows workflow requires a 64-bit Python interpreter.")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
            raise WorkflowError("invalid_limit", "Timeout must be an integer between 1 and 3600 seconds.")
        self.timeout = timeout_seconds
        if _windows():
            for supplied in (engine, read_root, work_root):
                _safe_components(supplied)  # Validate raw spelling before pathlib can normalize aliases.
        self.engine = Path(engine).absolute()
        self.read_root = Path(read_root).absolute()
        self.work_root = Path(work_root).absolute()
        for path in (self.engine, self.read_root, self.work_root): _safe_components(path)
        if not self.engine.is_file() or not self.read_root.is_dir():
            raise WorkflowError("invalid_configuration", "Configure an existing engine file and read directory.")
        self.engine = self.engine.resolve(); self.read_root = self.read_root.resolve(); self.work_root = self.work_root.resolve()
        if self.read_root == self.work_root or self.read_root in self.work_root.parents or self.work_root in self.read_root.parents:
            raise WorkflowError("invalid_configuration", "Read and work roots must be disjoint.")
        config = {"schemaVersion": "mvs-workspace/v1", "readRoot": str(self.read_root), "engine": str(self.engine)}
        _mkdir(self.work_root, parents=True, exist_ok=True)
        marker = self.work_root / "workspace.json"
        if not marker.exists():
            if any(self.work_root.iterdir()):
                raise WorkflowError("invalid_workspace", "New workspace must be empty.")
            try: _new_json(marker, config)
            except FileExistsError: pass
        if strict_json(_read_regular(marker, MAX_JSON)) != config:
            raise WorkflowError("invalid_workspace", "Workspace belongs to a different configuration.")
        for name in ("protocols", "runs", "staging"):
            path = self.work_root / name; _safe_components(path); _mkdir(path, exist_ok=True)

    def dispatch(self, operation, params, cancel_event=None):
        cancel = cancel_event or threading.Event()
        try:
            methods = {"register_protocol": self.register_protocol, "get_protocol": self.get_protocol,
                       "run_analysis": self.run_analysis, "get_run": self.get_run, "read_artifact": self.read_artifact}
            if operation not in methods:
                raise WorkflowError("unknown_operation", "Unknown workflow operation.")
            if cancel.is_set(): raise WorkflowError("cancelled", "Operation cancelled before execution.")
            return methods[operation](params, cancel)
        except WorkflowError as exc:
            return envelope(status="cancelled" if exc.code == "cancelled" else "error", error={"code": exc.code, "message": str(exc)})
        except (ValueError, TypeError, UnicodeError, KeyError, AttributeError):
            return envelope(status="error", error={"code": "invalid_json", "message": "Invalid JSON or unsupported value type."})
        except OSError:
            return envelope(status="error", error={"code": "storage_error", "message": "Local storage operation failed; inspect retained workspace state."})

    @contextmanager
    def _compute(self):
        if _windows():
            from ._windows_files import lock, BusyError
            try:
                with lock(self.work_root / "engine.lock"): yield
            except BusyError as exc: raise WorkflowError("busy", "Another computation is active in this workspace.") from exc
            return
        import fcntl
        path = self.work_root / "engine.lock"; _safe_components(path)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise WorkflowError("unsafe_path", "Invalid workspace lock.")
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise WorkflowError("busy", "Another computation is active in this workspace.") from exc
            yield
        finally: os.close(fd)

    def _input(self, relative, limit):
        if not isinstance(relative, str) or not relative or "\x00" in relative or "\\" in relative:
            raise WorkflowError("unsafe_path", "Use a nonempty relative input path.")
        if _windows():
            # The public request format stays slash-separated and relative on every OS.
            if ":" in relative or relative.startswith("/"):
                raise WorkflowError("unsafe_path", "Windows input aliases and alternate streams are unsupported.")
        path = Path(relative)
        if path.is_absolute() or any(p in (".", "..") for p in path.parts):
            raise WorkflowError("unsafe_path", "Input paths must stay inside the configured read root.")
        full = self.read_root / path; _safe_components(full)
        if not full.resolve().is_relative_to(self.read_root):
            raise WorkflowError("unsafe_path", "Input escaped the configured read root.")
        return _read_regular(full, limit)

    def _capture(self, params):
        data = self._input(params["data"], MAX_INPUT)
        calibration = self._input(params["calibration"], MAX_CALIBRATION)
        state = strict_json(calibration)
        if not isinstance(state, dict): raise WorkflowError("invalid_calibration", "Calibration must be a JSON object.")
        pending = [(state, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 64: raise WorkflowError("invalid_calibration", "Calibration nesting exceeds 64 levels.")
            if isinstance(value, dict):
                if len({k.casefold() for k in value}) != len(value):
                    raise WorkflowError("invalid_calibration", "Ambiguous case-insensitive calibration keys.")
                pending.extend((v, depth + 1) for v in value.values())
            elif isinstance(value, list): pending.extend((v, depth + 1) for v in value)
        keys = {k.casefold(): k for k in state}
        if len(keys) != len(state): raise WorkflowError("invalid_calibration", "Ambiguous case-insensitive calibration keys.")
        # Native deserialization is case-insensitive; snapshots retain their original bytes.
        state = {k: state[keys[k.casefold()]] for k in ("Repetitions", "Effect", "Seed", "Scenario", "OutlierRate", "MissingRate", "Alpha", "EquivalenceMargin", "SplitCalibration", "Tracks", "Processing", "SettingsHash") if k.casefold() in keys}
        processing = state.get("Processing", {})
        if not isinstance(processing, dict): raise WorkflowError("invalid_calibration", "Invalid calibration processing metadata.")
        processing_keys = {k.casefold(): k for k in processing}
        if len(processing_keys) != len(processing):
            raise WorkflowError("invalid_calibration", "Ambiguous case-insensitive processing keys.")
        if processing.get(processing_keys.get("importprofile", ""), ""):
            raise WorkflowError("unsupported_profile", "Installed import profiles are outside this frozen workflow scope.")
        return data, calibration, state

    def _storage_budget(self, extra=0):
        total = 0; count = 0
        for path in self.work_root.rglob("*"):
            _safe_components(path)
            try:
                entry = path.lstat()
            except FileNotFoundError:
                # Native atomic exporters may retire a temporary after enumeration.
                # Missing bytes consume no quota; surviving special files still fail.
                continue
            if stat.S_ISREG(entry.st_mode):
                count += 1; total += entry.st_size
            elif not stat.S_ISDIR(entry.st_mode):
                raise WorkflowError("unsafe_path", "Special files are not supported in workspace storage.")
            if count > 10000 or total + extra > MAX_WORKSPACE:
                raise WorkflowError("storage_limit", "Workspace quota reached; use a new workspace or explicitly archive completed work.")

    def _stage(self, params):
        data, calibration, state = self._capture(params)
        self._storage_budget(2 * (len(data) + len(calibration)) + 2 * MAX_JSON)
        folder = self.work_root / "staging" / uuid.uuid4().hex; _mkdir(folder)
        _snapshot_bytes(folder / "input.csv", data)
        _snapshot_bytes(folder / "calibration_state.json", calibration)
        return folder, {"dataSha256": digest(data), "calibrationSha256": digest(calibration)}, state

    def _verify_inputs(self, folder, hashes):
        actual = {"dataSha256": digest(_read_regular(folder / "input.csv", MAX_INPUT)),
                  "calibrationSha256": digest(_read_regular(folder / "calibration_state.json", MAX_CALIBRATION))}
        if actual != hashes: raise WorkflowError("snapshot_changed", "Consumed input snapshots no longer match their recorded bytes.")

    def _bundle_hash(self):
        paths = [self.engine] + sorted(p for p in self.engine.parent.iterdir() if p != self.engine and p.suffix in {".dll", ".json", ".so"})
        values = {p.name: digest(_read_regular(p, 64 * 1024 * 1024)) for p in paths}
        return digest(canonical(values))

    def _native(self, args, folder, cancel):
        if cancel.is_set(): raise WorkflowError("cancelled", "Operation cancelled before native execution.")
        for name in ("home", "data", "config", "tmp", "backups"):
            _mkdir(folder / name, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "DOTNET_ROOT", "LANG", "LC_ALL"}}
        if _windows():
            # Windows loader/runtime requires these OS paths; do not inherit arbitrary MVS settings.
            for key in ("SystemRoot", "WINDIR"):
                if key in os.environ: env[key] = os.environ[key]
        env.update(HOME=str(folder / "home"), XDG_DATA_HOME=str(folder / "data"), XDG_CONFIG_HOME=str(folder / "config"),
                   TMPDIR=str(folder / "tmp"), TMP=str(folder / "tmp"), TEMP=str(folder / "tmp"),
                   MVS_APPDATA_ROOT=str(folder / "data"), MVS_DISABLE_BACKUPS="1", MVS_BACKUP_DIR=str(folder / "backups"), DOTNET_PROCESSOR_COUNT="2", DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_EnableDiagnostics="0")
        tag = uuid.uuid4().hex
        stdout, stderr = folder / (tag + ".stdout.json"), folder / (tag + ".stderr.txt")
        with stdout.open("xb") as out, stderr.open("xb") as err:
            if _windows():
                from ._windows_process import WindowsProcess
                child = WindowsProcess([str(self.engine), *args, "--json", "--quiet"], cwd=folder, env=env, stdout=out, stderr=err)
            else:
                child = subprocess.Popen([str(self.engine), *args, "--json", "--quiet"], cwd=folder, env=env,
                                         stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            reason = None; started = time.monotonic()
            try:
                while child.poll() is None:
                    if cancel.is_set(): reason = "cancelled"
                    elif time.monotonic() - started > self.timeout: reason = "timeout"
                    elif stdout.stat().st_size > MAX_JSON or stderr.stat().st_size > MAX_JSON: reason = "output_limit"
                    try: self._storage_budget()
                    except WorkflowError as exc: reason = exc.code
                    if reason: break
                    time.sleep(.05)
            finally:
                if _windows():
                    try:
                        child.terminate_tree()
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired as exc:
                        raise WorkflowError("process_cleanup_timeout", "Owned Windows process tree did not finish within its cleanup bound; evidence retained.") from exc
                    finally: child.close()
                else:
                    if child.poll() is None:
                        try: os.killpg(child.pid, signal.SIGINT)
                        except ProcessLookupError: pass
                        try: child.wait(timeout=2)
                        except subprocess.TimeoutExpired: pass
                    # The session was created by this call; never signal a caller's group.
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    child.wait(timeout=2)
            if reason: raise WorkflowError(reason, "Native operation cancelled or exceeded its execution limit; partial evidence retained.")
        if cancel.is_set(): raise WorkflowError("cancelled", "Cancellation received before result acceptance.")
        if stdout.stat().st_size > MAX_JSON or stderr.stat().st_size > MAX_JSON:
            raise WorkflowError("output_limit", "Native output exceeded its size limit.")
        payload = strict_json(_read_regular(stdout, MAX_JSON))
        if not isinstance(payload, dict) or payload.get("schemaVersion") != "mvs-cli-result/v1" or payload.get("command") != args[0]:
            raise WorkflowError("native_protocol", "Native response identity is incompatible.")
        code = payload.get("exitCode")
        if type(code) is not int or code not in {0, 1, 2} or code != child.returncode or payload.get("status") != {0: "completed", 1: "error", 2: "diagnostic"}.get(code):
            raise WorkflowError("native_protocol", "Native status and process exit disagree.")
        return payload

    def _identity(self, folder, cancel):
        before = self._bundle_hash(); version = self._native(["version"], folder, cancel)
        if _windows() and version.get("localAppDataOverride") != "MVS_APPDATA_ROOT/v1":
            raise WorkflowError("incompatible_engine", "Windows workflow requires a native engine advertising isolated application-data support.")
        protocol = version.get("cliProtocol")
        if (version["exitCode"] != 0 or not isinstance(protocol, dict)
                or protocol.get("name") != "mvs-cli" or type(protocol.get("major")) is not int or protocol["major"] != 1
                or any(not isinstance(version.get(k), str) or not version[k] for k in ("engineVersion", "formulaVersion", "formulaHash"))
                or type(version.get("stateSchema")) is not int
                or not isinstance(version.get("executionEnvironment"), dict)
                or not isinstance(version["executionEnvironment"].get("fingerprint"), str)
                or not version["executionEnvironment"]["fingerprint"]):
            raise WorkflowError("incompatible_engine", "Native CLI identity could not be established.")
        if before != self._bundle_hash(): raise WorkflowError("engine_changed", "Configured engine bundle changed during identity check.")
        return {k: version[k] for k in ("engineVersion", "formulaVersion", "formulaHash", "stateSchema")} | {"bundleSha256": before, "environmentFingerprint": version["executionEnvironment"]["fingerprint"]}

    def _validated_state(self, folder, cancel):
        result = self._native(["state-check", "--calibration", str(folder / "calibration_state.json"), "--in", str(folder / "input.csv")], folder, cancel)
        if result["exitCode"] != 0:
            raise WorkflowError("invalid_calibration", "Native calibration validation failed; no analysis was launched.")

    def _record(self, protocol_id, seen=()):
        if protocol_id in seen or len(seen) >= 64:
            raise WorkflowError("invalid_protocol", "Protocol amendment chain is cyclic or too long.")
        path = self.work_root / "protocols" / (_id(protocol_id) + ".json")
        record = strict_json(_read_regular(path, MAX_JSON))
        if not isinstance(record, dict) or set(record) != {"content", "sha256"}:
            raise WorkflowError("invalid_protocol", "Malformed local protocol record.")
        content = record["content"]
        if not isinstance(content, dict) or content.get("schemaVersion") != PROTOCOL_SCHEMA or content.get("protocolId") != protocol_id or record["sha256"] != digest(canonical(content)):
            raise WorkflowError("invalid_protocol", "Protocol schema, identifier or content hash mismatch.")
        required = {"schemaVersion", "protocolId", "createdUtc", "question", "priorExposure", "claimScope", "inputs", "engine", "allowGroupScopedIds", "parent", "settings", "calibrationPreexisted"}
        if set(content) != required or content["priorExposure"] not in EXPOSURES or type(content["allowGroupScopedIds"]) is not bool:
            raise WorkflowError("invalid_protocol", "Unsupported protocol content.")
        if not isinstance(content["inputs"], dict) or set(content["inputs"]) != {"dataSha256", "calibrationSha256"}:
            raise WorkflowError("invalid_protocol", "Invalid protocol input binding.")
        if (not isinstance(content["question"], str) or not 1 <= len(content["question"]) <= 2000
                or content["claimScope"] != "existing_exploratory_entity_summary_analysis; not confirmatory certification"
                or not isinstance(content["engine"], dict) or set(content["engine"]) != {"engineVersion", "formulaVersion", "formulaHash", "stateSchema", "bundleSha256", "environmentFingerprint"}
                or not isinstance(content["settings"], dict) or content["calibrationPreexisted"] is not True
                or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in content["inputs"].values())):
            raise WorkflowError("invalid_protocol", "Protocol content is outside the supported schema.")
        if not isinstance(content["createdUtc"], str) or datetime.fromisoformat(content["createdUtc"]).tzinfo is None:
            raise WorkflowError("invalid_protocol", "Protocol timestamp must include a time zone; it is not an external timestamp.")
        parent = content["parent"]
        if parent is not None:
            if not isinstance(parent, dict) or set(parent) != {"protocolId", "sha256"}:
                raise WorkflowError("invalid_protocol", "Invalid amendment reference.")
            previous = self._record(parent["protocolId"], (*seen, protocol_id))
            if previous["sha256"] != parent["sha256"]:
                raise WorkflowError("invalid_protocol", "Amendment predecessor hash does not match.")
        return record

    def register_protocol(self, params, cancel):
        _fields(params, {"protocol_id", "data", "calibration", "prior_exposure", "question"}, {"parent_protocol_id", "allow_group_scoped_ids"})
        ident = _id(params["protocol_id"]); allow = _bool(params.get("allow_group_scoped_ids", False))
        if params["prior_exposure"] not in EXPOSURES or not isinstance(params["question"], str) or not 1 <= len(params["question"]) <= 2000:
            raise WorkflowError("invalid_request", "Declare prior exposure and a question of 1–2000 characters.")
        path = self.work_root / "protocols" / (ident + ".json")
        if path.exists(): raise WorkflowError("protocol_conflict", "Protocol identifier already exists; use a new amendment identifier.")
        parent = None
        if "parent_protocol_id" in params:
            if params["parent_protocol_id"] == ident: raise WorkflowError("invalid_parent", "Protocol cannot amend itself.")
            old = self._record(params["parent_protocol_id"])
            parent = {"protocolId": params["parent_protocol_id"], "sha256": old["sha256"]}
        with self._compute():
            folder, hashes, state = self._stage(params)
            identity = self._identity(folder, cancel); self._validated_state(folder, cancel); self._verify_inputs(folder, hashes)
            if identity["bundleSha256"] != self._bundle_hash():
                raise WorkflowError("engine_changed", "Native bundle changed before protocol commit.")
            content = {"schemaVersion": PROTOCOL_SCHEMA, "protocolId": ident, "createdUtc": datetime.now(timezone.utc).isoformat(),
                       "question": params["question"], "priorExposure": params["prior_exposure"],
                       "claimScope": "existing_exploratory_entity_summary_analysis; not confirmatory certification",
                       "inputs": hashes, "engine": identity, "allowGroupScopedIds": allow, "parent": parent, "calibrationPreexisted": True,
                       "settings": {k: state[k] for k in ("Repetitions", "Effect", "Seed", "Scenario", "OutlierRate", "MissingRate", "Alpha", "EquivalenceMargin", "SplitCalibration", "Tracks", "Processing", "SettingsHash")}}
            if cancel.is_set(): raise WorkflowError("cancelled", "Registration cancelled before commit.")
            record = {"content": content, "sha256": digest(canonical(content))}
            try: _new_json(path, record)
            except FileExistsError as exc: raise WorkflowError("protocol_conflict", "Protocol identifier already exists.") from exc
            return envelope(record)

    def get_protocol(self, params, cancel):
        _fields(params, {"protocol_id"}); return envelope(self._record(params["protocol_id"]))

    def _run_path(self, run_id):
        path = self.work_root / "runs" / _id(run_id); _safe_components(path)
        return path

    def _terminal(self, folder):
        wrapper = strict_json(_read_regular(folder / "result.json", MAX_JSON))
        if not isinstance(wrapper, dict) or set(wrapper) != {"result", "sha256"} or wrapper["sha256"] != digest(canonical(wrapper["result"])):
            raise WorkflowError("invalid_result", "Stored workflow result is inconsistent.")
        result = wrapper["result"]
        if (not isinstance(result, dict) or result.get("schemaVersion") != SCHEMA
                or result.get("scientificReadiness") != READINESS or not isinstance(result.get("execution"), dict)
                or result["execution"].get("status") not in {"completed", "error", "cancelled"}):
            raise WorkflowError("invalid_result", "Unsupported stored result envelope.")
        execution = result["execution"]
        if execution["status"] == "completed" and (type(execution.get("nativeExitCode")) is not int or execution["nativeExitCode"] not in {0, 2}):
            raise WorkflowError("invalid_result", "Invalid stored native completion code.")
        reservation = self._reservation(folder)
        data = result.get("data")
        if not isinstance(data, dict) or data.get("runId") != folder.name:
            raise WorkflowError("invalid_result", "Stored result run identity is inconsistent.")
        if result.get("execution", {}).get("status") == "completed":
            request = reservation["request"]
            bound_protocol = data.get("protocol")
            if (data.get("inputs") != request["inputs"] or data.get("mode") != request["mode"]
                    or data.get("engine") != reservation["engine"]
                    or (bound_protocol.get("sha256") if isinstance(bound_protocol, dict) else None) != request["protocolSha256"]):
                raise WorkflowError("invalid_result", "Stored result does not match its immutable request binding.")
            self._verify_artifacts(folder, data["native"])
            self._verify_inputs(folder, data["inputs"])
        return result

    def _reservation(self, folder):
        item = strict_json(_read_regular(folder / "request.json", MAX_JSON))
        if (not isinstance(item, dict) or set(item) != {"schemaVersion", "requestSha256", "request", "engine"}
                or item["schemaVersion"] != "mvs-run-request/v1" or item["requestSha256"] != digest(canonical(item["request"]))):
            raise WorkflowError("invalid_request_record", "Stored request schema or content hash mismatch.")
        return item

    def _verify_artifacts(self, folder, payload):
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise WorkflowError("invalid_artifacts", "Completed analysis must expose verified artifacts.")
        for key in ("outputDirectory", "manifestPath"):
            value = payload.get(key)
            if not isinstance(value, str): raise WorkflowError("invalid_artifacts", "Native output identity is missing.")
            path = Path(value); path = path if path.is_absolute() else self.work_root / path
            _safe_components(path)
            if not path.resolve().is_relative_to(folder.resolve()):
                raise WorkflowError("unsafe_artifact", "Native output escaped the run directory.")
        output = Path(payload["outputDirectory"])
        output = output if output.is_absolute() else self.work_root / output
        if not output.is_dir(): raise WorkflowError("invalid_artifacts", "Native output directory does not exist.")
        manifest_path = Path(payload["manifestPath"])
        manifest_path = manifest_path if manifest_path.is_absolute() else self.work_root / manifest_path
        names = set(); verified_paths = set()
        for item in artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise WorkflowError("invalid_artifacts", "Invalid native artifact record.")
            path = Path(item["path"]); path = path if path.is_absolute() else self.work_root / path
            _safe_components(path)
            if path.resolve().parent != output.resolve() or path.name != item.get("name") or path.name in names:
                raise WorkflowError("unsafe_artifact", "Invalid or duplicate native artifact path.")
            names.add(path.name); verified_paths.add(path.resolve()); raw = _read_regular(path, MAX_ARTIFACT)
            if type(item.get("sizeBytes")) is not int or len(raw) != item["sizeBytes"] or digest(raw) != item.get("sha256"):
                raise WorkflowError("invalid_artifacts", "Native artifact size or hash mismatch.")
        if manifest_path.resolve() not in verified_paths: raise WorkflowError("invalid_artifacts", "Manifest is absent from verified artifacts.")

    def run_analysis(self, params, cancel):
        _fields(params, {"run_id", "data", "calibration"}, {"mode", "protocol_id", "allow_group_scoped_ids"})
        run_id = _id(params["run_id"]); mode = params.get("mode", "exploratory")
        allow = _bool(params.get("allow_group_scoped_ids", False))
        if mode not in {"exploratory", "frozen"} or (mode == "frozen") != ("protocol_id" in params):
            raise WorkflowError("invalid_mode", "Frozen mode requires a protocol; exploratory mode cannot claim one.")
        protocol = self._record(params["protocol_id"]) if mode == "frozen" else None
        with self._compute():
            folder = self._run_path(run_id)
            if folder.exists():
                data, calibration, _ = self._capture(params)
                hashes = {"dataSha256": digest(data), "calibrationSha256": digest(calibration)}
                staged = None
            else:
                staged, hashes, _ = self._stage(params)
            request = {"mode": mode, "inputs": hashes, "allowGroupScopedIds": allow, "protocolSha256": protocol["sha256"] if protocol else None}
            request_hash = digest(canonical(request)); folder = self._run_path(run_id)
            if folder.exists():
                if not (folder / "request.json").exists():
                    return envelope({"runId": run_id, "state": "in_progress_or_interrupted", "automaticRerun": False}, status="incomplete")
                reservation = self._reservation(folder)
                if reservation.get("requestSha256") != request_hash:
                    raise WorkflowError("run_conflict", "Run identifier is bound to a different request or input bytes.")
                if (folder / "result.json").exists(): return self._terminal(folder)
                return envelope({"runId": run_id, "state": "in_progress_or_interrupted", "automaticRerun": False}, status="incomplete")
            identity = self._identity(staged, cancel); self._validated_state(staged, cancel)
            if protocol and (protocol["content"]["inputs"] != hashes or protocol["content"]["engine"] != identity or protocol["content"]["allowGroupScopedIds"] != allow):
                raise WorkflowError("protocol_deviation", "Inputs, native identity or declared settings differ from the frozen protocol; no analysis launched.")
            try: _mkdir(folder)
            except FileExistsError as exc: raise WorkflowError("run_conflict", "Run identifier was reserved concurrently.") from exc
            _new_json(folder / "request.json", {"schemaVersion": "mvs-run-request/v1", "requestSha256": request_hash,
                                               "request": request, "engine": identity})
            # Only private snapshots are passed to the native process.
            _snapshot_bytes(folder / "input.csv", _read_regular(staged / "input.csv", MAX_INPUT))
            _snapshot_bytes(folder / "calibration_state.json", _read_regular(staged / "calibration_state.json", MAX_CALIBRATION))
            try:
                self._verify_inputs(folder, hashes)
                args = ["analyze", "--in", str(folder / "input.csv"), "--calibration", str(folder / "calibration_state.json"), "--out", str(folder / "output")]
                if allow: args.append("--allow-group-scoped-ids")
                payload = self._native(args, folder, cancel)
                self._verify_inputs(folder, hashes)
                if identity["bundleSha256"] != self._bundle_hash(): raise WorkflowError("engine_changed", "Native bundle changed during execution.")
                if payload["exitCode"] == 1: raise WorkflowError("native_error", "Native analysis failed; local diagnostics and partial artifacts are retained.")
                self._verify_artifacts(folder, payload)
                # Keep the native scientific metadata, but make managed paths portable.
                for key in ("outputDirectory", "manifestPath"):
                    payload[key] = str(Path(payload[key]).relative_to(self.work_root))
                for artifact in payload["artifacts"]:
                    artifact["path"] = str(Path(artifact["path"]).relative_to(self.work_root))
                result = envelope({"runId": run_id, "mode": mode, "protocol": {"protocolId": params["protocol_id"], "sha256": protocol["sha256"]} if protocol else None,
                                   "inputs": hashes, "engine": identity, "localBindingVerified": True, "confirmatoryCertified": False,
                                   "priorExposure": protocol["content"]["priorExposure"] if protocol else "unknown", "native": payload}, native_exit=payload["exitCode"])
            except WorkflowError as exc:
                result = envelope({"runId": run_id, "inputs": hashes, "partialEvidenceRetained": True},
                                  status="cancelled" if exc.code == "cancelled" else "error", error={"code": exc.code, "message": str(exc)})
            except (OSError, ValueError, TypeError, UnicodeError):
                result = envelope({"runId": run_id, "partialEvidenceRetained": True}, status="error",
                                  error={"code": "invalid_native_result", "message": "Native response or local storage failed validation; evidence retained."})
            if cancel.is_set() and result["execution"]["status"] == "completed":
                result = envelope({"runId": run_id, "inputs": hashes, "partialEvidenceRetained": True}, status="cancelled",
                                  error={"code": "cancelled", "message": "Cancellation received before completion commit."})
            _new_json(folder / "result.json", {"result": result, "sha256": digest(canonical(result))})
            return result

    def get_run(self, params, cancel):
        _fields(params, {"run_id"}); folder = self._run_path(params["run_id"])
        if not folder.is_dir(): raise WorkflowError("run_not_found", "Run identifier was not found.")
        if (folder / "result.json").exists(): return self._terminal(folder)
        return envelope({"runId": params["run_id"], "state": "in_progress_or_interrupted", "automaticRerun": False}, status="incomplete")

    def read_artifact(self, params, cancel):
        _fields(params, {"run_id", "name"}); folder = self._run_path(params["run_id"])
        name = params["name"]
        if not isinstance(name, str) or Path(name).name != name or Path(name).suffix.lower() not in {".json", ".csv", ".txt"}:
            raise WorkflowError("invalid_artifact", "Request a named text artifact, not an arbitrary path.")
        result = self._terminal(folder)
        if result["execution"]["status"] != "completed": raise WorkflowError("incomplete_run", "Only completed verified artifacts can be read.")
        matches = [a for a in result["data"]["native"]["artifacts"] if a["name"] == name]
        if len(matches) != 1: raise WorkflowError("artifact_not_found", "Named artifact was not found.")
        item = matches[0]; raw = _read_regular(self.work_root / item["path"], 65536)
        if len(raw) != item["sizeBytes"] or digest(raw) != item["sha256"]:
            raise WorkflowError("invalid_artifacts", "Artifact changed while reading.")
        return envelope({"runId": params["run_id"], "name": name, "sha256": digest(raw), "text": raw.decode("utf-8-sig")})
