"""Workflow contract tests with explicit native doubles; real parity is separate."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from mvs.workflow import (WorkflowService, WorkflowError, canonical, digest, strict_json,
                          _new_json, MAX_JSON, READINESS)

STATE = {"Repetitions": 150, "Effect": 1.15, "Seed": 20260719, "Scenario": "location",
         "OutlierRate": .02, "MissingRate": 0, "Alpha": .05, "EquivalenceMargin": .147,
         "SplitCalibration": False, "Tracks": ["location"], "Processing": {"ImportProfile": ""},
         "SettingsHash": "synthetic-settings"}


class FakeService(WorkflowService):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = []; self.exit_code = 0; self.hook = None

    def _native(self, args, folder, cancel):
        self.calls.append(list(args))
        payload = {"schemaVersion": "mvs-cli-result/v1", "command": args[0], "exitCode": 0, "status": "completed",
                   "engineVersion": "1.6.2", "formulaVersion": "MVS-1.4.0", "formulaHash": "synthetic-formula",
                   "stateSchema": 2, "executionEnvironment": {"fingerprint": "synthetic-environment"}, "cliProtocol": {"name": "mvs-cli", "major": 1}, "error": None,
                   "diagnostics": []}
        if args[0] == "analyze":
            output = Path(args[args.index("--out") + 1]); output.mkdir()
            for name, data in [("run_manifest.json", b'{"synthetic":true}'), ("results.csv", b'x,y\n1,2\n')]:
                (output / name).write_bytes(data)
            payload.update(outputDirectory=str(output), manifestPath=str(output / "run_manifest.json"),
                           artifacts=[{"name": p.name, "path": str(p), "sizeBytes": p.stat().st_size, "sha256": digest(p.read_bytes())} for p in sorted(output.iterdir())],
                           exitCode=self.exit_code, status={0: "completed", 1: "error", 2: "diagnostic"}[self.exit_code])
        if self.hook: self.hook(args, folder, payload, cancel)
        return payload


@unittest.skipUnless(sys.platform.startswith("linux"), "new workflow Linux checkpoint")
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.inputs = self.root / "inputs"; self.inputs.mkdir()
        self.backend = self.root / "engine"; self.backend.mkdir(); self.exe = self.backend / "mvs"; self.exe.write_text("synthetic nonexecuted backend")
        (self.inputs / "data.csv").write_bytes(b"group,entity,value\na,1,2\n")
        (self.inputs / "state.json").write_bytes(canonical(STATE))
        self.service = FakeService(self.exe, self.inputs, self.root / "work")
        self.common = {"data": "data.csv", "calibration": "state.json"}

    def register(self, **changes):
        return self.service.dispatch("register_protocol", self.common | {"protocol_id": "p1", "question": "Synthetic scope", "prior_exposure": "unknown"} | changes)

    def run_one(self, **changes):
        return self.service.dispatch("run_analysis", self.common | {"run_id": "r1"} | changes)

    def assert_error(self, result, code=None):
        self.assertEqual(result["execution"]["status"], "error", result)
        self.assertEqual(result["scientificReadiness"], READINESS)
        if code: self.assertEqual(result["error"]["code"], code, result)

    def test_snapshots_are_private_without_changing_source_permissions(self):
        before = (self.inputs / "data.csv").stat().st_mode
        self.run_one()
        for name in ["input.csv", "calibration_state.json"]:
            self.assertEqual((self.root / "work/runs/r1" / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "work/runs/r1").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.inputs / "data.csv").stat().st_mode, before)

    def test_default_exploratory_and_verified_replay(self):
        first = self.run_one(); self.assertEqual(first["data"]["mode"], "exploratory")
        count = len(self.service.calls); stages = len(list((self.root / "work/staging").iterdir()))
        self.assertEqual(self.run_one(), first); self.assertEqual(len(self.service.calls), count)
        self.assertEqual(len(list((self.root / "work/staging").iterdir())), stages)
        self.assertFalse(first["data"]["confirmatoryCertified"])
        self.assertEqual(first["scientificReadiness"], READINESS)

    def test_frozen_and_immutable_amendment(self):
        record = self.register(); self.assertEqual(record["execution"]["status"], "completed", record)
        before = (self.root / "work/protocols/p1.json").read_bytes()
        self.assert_error(self.register(), "protocol_conflict")
        newer = self.register(protocol_id="p2", parent_protocol_id="p1")
        self.assertEqual(newer["data"]["content"]["parent"]["sha256"], record["data"]["sha256"])
        self.assertEqual((self.root / "work/protocols/p1.json").read_bytes(), before)
        result = self.run_one(mode="frozen", protocol_id="p1")
        self.assertTrue(result["data"]["localBindingVerified"], result)
        self.assertEqual(result["data"]["priorExposure"], "unknown")

    def test_native_state_check_uses_correct_flags(self):
        self.register()
        args = next(a for a in self.service.calls if a[0] == "state-check")
        self.assertIn("--calibration", args); self.assertIn("--in", args); self.assertNotIn("--normalize", args)

    def test_diagnostic_is_explicit_not_unqualified_success(self):
        self.service.exit_code = 2; result = self.run_one()
        self.assertEqual(result["execution"]["nativeExitCode"], 2)
        self.assertEqual(result["execution"]["outcome"], "completed_with_diagnostic")
        self.assertEqual(result["data"]["native"]["status"], "diagnostic")

    def test_record_and_result_hash_tampering(self):
        self.register(); p = self.root / "work/protocols/p1.json"; v = strict_json(p.read_bytes()); v["content"]["question"] = "changed"; p.write_bytes(canonical(v))
        self.assert_error(self.service.dispatch("get_protocol", {"protocol_id": "p1"}), "invalid_protocol")
        self.run_one(); p = self.root / "work/runs/r1/result.json"; p.write_bytes(b'{"result":null,"sha256":"wrong"}')
        self.assert_error(self.service.dispatch("get_run", {"run_id": "r1"}))

    def test_forged_reservation_digest_cannot_replay_different_request(self):
        self.run_one(); path = self.root / "work/runs/r1/request.json"; item = strict_json(path.read_bytes())
        (self.inputs / "data.csv").write_bytes(b"changed")
        item["requestSha256"] = digest(canonical(item["request"] | {"inputs": item["request"]["inputs"] | {"dataSha256": digest(b"changed")}}))
        path.write_bytes(canonical(item)); self.assert_error(self.run_one(), "invalid_request_record")

    def test_unknown_stored_result_schema_is_rejected(self):
        self.run_one(); path = self.root / "work/runs/r1/result.json"; item = strict_json(path.read_bytes())
        item["result"]["schemaVersion"] = "unknown"; item["sha256"] = digest(canonical(item["result"]))
        path.write_bytes(canonical(item))
        self.assert_error(self.service.dispatch("get_run", {"run_id": "r1"}), "invalid_result")

    def test_terminal_must_match_reservation(self):
        self.run_one(); path = self.root / "work/runs/r1/result.json"; item = strict_json(path.read_bytes())
        item["result"]["data"]["runId"] = "other"; item["sha256"] = digest(canonical(item["result"])); path.write_bytes(canonical(item))
        self.assert_error(self.service.dispatch("get_run", {"run_id": "r1"}), "invalid_result")

    def test_original_mutation_after_snapshot_does_not_change_consumed_bytes(self):
        expected = (self.inputs / "data.csv").read_bytes()
        def hook(args, folder, payload, cancel):
            if args[0] == "version": (self.inputs / "data.csv").write_bytes(b"changed original")
        self.service.hook = hook
        result = self.run_one(); self.assertEqual(result["execution"]["status"], "completed", result)
        self.assertEqual((self.root / "work/runs/r1/input.csv").read_bytes(), expected)

    def test_snapshot_mutation_never_completes(self):
        def hook(args, folder, payload, cancel):
            if args[0] == "analyze": (folder / "input.csv").write_bytes(b"changed snapshot")
        self.service.hook = hook; self.assert_error(self.run_one(), "snapshot_changed")

    def test_frozen_different_data_or_settings_never_analyzes(self):
        self.register(); initial = (self.inputs / "data.csv").read_bytes()
        (self.inputs / "data.csv").write_bytes(b"changed")
        self.assert_error(self.run_one(mode="frozen", protocol_id="p1"), "protocol_deviation")
        (self.inputs / "data.csv").write_bytes(initial)
        self.assert_error(self.run_one(mode="frozen", protocol_id="p1", allow_group_scoped_ids=True), "protocol_deviation")
        self.assertFalse(any(a[0] == "analyze" for a in self.service.calls))

    def test_native_error_is_terminal_and_never_rerun(self):
        self.service.exit_code = 1; result = self.run_one(); self.assert_error(result, "native_error")
        count = len(self.service.calls); self.assertEqual(self.run_one(), result); self.assertEqual(len(self.service.calls), count)

    def test_partial_reservation_is_incomplete_not_automatic_retry(self):
        (self.root / "work/runs/r1").mkdir()
        result = self.run_one(); self.assertEqual(result["execution"]["status"], "incomplete")
        self.assertFalse(result["data"]["automaticRerun"]); self.assertEqual(self.service.calls, [])

    def test_same_identifier_different_bytes_conflicts(self):
        self.run_one(); (self.inputs / "data.csv").write_bytes(b"other")
        self.assert_error(self.run_one(), "run_conflict")

    def test_unavailable_paths_and_special_files(self):
        (self.inputs / "link").symlink_to(self.inputs / "data.csv")
        os.mkfifo(self.inputs / "fifo")
        for name in ["../engine/mvs", str(self.inputs / "data.csv"), "link", "fifo", "missing", "a\\b"]:
            with self.subTest(name=name): self.assert_error(self.run_one(data=name))
        self.assertEqual(self.service.calls, [])

    def test_profile_and_invalid_value_types(self):
        (self.inputs / "state.json").write_bytes(canonical(STATE | {"Processing": {"ImportProfile": "external"}}))
        self.assert_error(self.register(), "unsupported_profile")
        for changes in [{"mode": "certified"}, {"force": True}, {"mode": "frozen"}, {"protocol_id": "p1"}, {"allow_group_scoped_ids": 1}, {"run_id": "../escape"}]:
            with self.subTest(changes=changes): self.assert_error(self.run_one(**changes))

    def test_nested_processing_case_and_duplicates(self):
        for processing in [{"IMPORTPROFILE": "installed"}, {"importprofile": "installed"}, {"ImportProfile": "", "IMPORTPROFILE": "installed"}]:
            (self.inputs / "state.json").write_bytes(canonical(STATE | {"Processing": processing}))
            self.assert_error(self.register())

    def test_nested_row_case_collision_is_rejected(self):
        (self.inputs / "state.json").write_bytes(canonical(STATE | {"Rows": [{"Metric": "median", "metric": "mean"}]}))
        self.assert_error(self.register(), "invalid_calibration")

    def test_amendment_predecessor_tampering_is_detected(self):
        self.register(); self.register(protocol_id="p2", parent_protocol_id="p1")
        path = self.root / "work/protocols/p1.json"; record = strict_json(path.read_bytes())
        record["content"]["question"] = "different"; record["sha256"] = digest(canonical(record["content"]))
        path.write_bytes(canonical(record))
        self.assert_error(self.service.dispatch("get_protocol", {"protocol_id": "p2"}), "invalid_protocol")

    def test_native_identity_malformed_is_controlled(self):
        for bad in [None, [], {"name": "wrong", "major": 1}, {"name": "mvs-cli", "major": True}]:
            with self.subTest(bad=bad):
                self.service.hook = lambda args, folder, payload, cancel: payload.update(cliProtocol=bad)
                self.assert_error(self.register())
        self.service.hook = lambda args, folder, payload, cancel: payload.pop("engineVersion", None)
        self.assert_error(self.register())

    def test_wrong_manifest_basename_is_not_sufficient(self):
        def hook(args, folder, payload, cancel):
            if args[0] == "analyze": payload["manifestPath"] = str(folder / "missing/run_manifest.json")
        self.service.hook = hook; self.assert_error(self.run_one(), "invalid_artifacts")

    def test_output_must_contain_verified_artifacts(self):
        def hook(args, folder, payload, cancel):
            if args[0] == "analyze": payload["outputDirectory"] = str(folder / "missing")
        self.service.hook = hook; self.assert_error(self.run_one(), "invalid_artifacts")

    def test_outside_artifact_is_not_read(self):
        def hook(args, folder, payload, cancel):
            if args[0] == "analyze": payload["artifacts"][0]["path"] = str(self.root / "outside-secret")
        self.service.hook = hook; self.assert_error(self.run_one(), "unsafe_artifact")

    def test_cancel_during_final_verification_commits_cancelled(self):
        event = threading.Event(); original = self.service._verify_artifacts
        def verify(*args): original(*args); event.set()
        with patch.object(self.service, "_verify_artifacts", side_effect=verify):
            result = self.service.dispatch("run_analysis", self.common | {"run_id": "r1"}, event)
        self.assertEqual(result["execution"]["status"], "cancelled")
        self.assertEqual(self.service.dispatch("get_run", {"run_id": "r1"}), result)

    def test_case_insensitive_calibration_keys(self):
        (self.inputs / "state.json").write_bytes(canonical({k.lower(): v for k, v in STATE.items()}))
        self.assertEqual(self.register()["execution"]["status"], "completed")

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for raw in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.assertRaises(ValueError): strict_json(raw)

    def test_atomic_commit_failure_is_reconcilable(self):
        path = self.root / "work/protocols/atomic.json"
        real = os.fsync; counter = 0
        def failure(fd):
            nonlocal counter
            counter += 1
            if counter == 2: raise OSError("directory fsync failed after commit")
            return real(fd)
        with patch("mvs.workflow.os.fsync", side_effect=failure):
            with self.assertRaises(OSError): _new_json(path, {"committed": True})
        self.assertEqual(strict_json(path.read_bytes()), {"committed": True})
        with self.assertRaises(FileExistsError): _new_json(path, {"committed": False})
        self.assertFalse(list(path.parent.glob('.pending-*')))

    def test_workspace_lock_and_quota_fail_closed(self):
        with self.service._compute(): self.assert_error(self.run_one(), "busy")
        with patch("mvs.workflow.MAX_WORKSPACE", 1): self.assert_error(self.run_one(), "storage_limit")

    def test_storage_scan_tolerates_retired_temp_but_rejects_surviving_special(self):
        import stat
        from unittest.mock import Mock
        retired = Mock(); retired.is_file.return_value = False; retired.is_dir.return_value = False
        retired.lstat.side_effect = FileNotFoundError("atomic exporter retired temp")
        special = Mock(); special.lstat.return_value.st_mode = stat.S_IFIFO
        with patch.object(Path, "rglob", return_value=iter([retired])), patch("mvs.workflow._safe_components"):
            self.service._storage_budget()
        with patch.object(Path, "rglob", return_value=iter([special])), patch("mvs.workflow._safe_components"):
            with self.assertRaises(WorkflowError) as caught: self.service._storage_budget()
        self.assertEqual(caught.exception.code, "unsafe_path")

    def test_platform_gate_is_explicit(self):
        with patch("mvs.workflow.sys.platform", "darwin"):
            with self.assertRaisesRegex(WorkflowError, "Linux and experimental Windows"):
                WorkflowService(self.exe, self.inputs, self.root / "unsupported")

    def test_workflow_cli_emits_utf8_independent_of_windows_codepage(self):
        import io
        from mvs.workflow_cli import main
        from mvs.workflow import envelope
        output = io.BytesIO(); stdout = io.TextIOWrapper(output, encoding="ascii")
        stdin = io.TextIOWrapper(io.BytesIO(b"{}"), encoding="ascii")
        expected = envelope({"question": "Исследование 雪"})
        with patch("mvs.workflow_cli.sys.stdout", stdout), patch("mvs.workflow_cli.sys.stdin", stdin), \
             patch("mvs.workflow_cli.WorkflowService") as service:
            service.return_value.dispatch.return_value = expected
            code = main(["--engine", "synthetic", "--read-root", "synthetic", "--work-root", "synthetic", "get_run"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue().decode("utf-8")), expected)
        stdout.detach()

    def test_windows_cleanup_timeout_is_structured_and_closes_job(self):
        class Child:
            closed = False
            returncode = 0
            def poll(self): return 0
            def terminate_tree(self): raise subprocess.TimeoutExpired("synthetic", 5)
            def close(self): self.closed = True
        child = Child(); folder = self.root / "native-cleanup"; folder.mkdir()
        with patch("mvs.workflow._windows", return_value=True), \
             patch("mvs.workflow._mkdir", side_effect=lambda p, **kw: p.mkdir(exist_ok=True)), \
             patch("mvs._windows_process.WindowsProcess", return_value=child):
            with self.assertRaises(WorkflowError) as caught:
                WorkflowService._native(self.service, ["version"], folder, threading.Event())
        self.assertEqual(caught.exception.code, "process_cleanup_timeout")
        self.assertTrue(child.closed)

    def test_windows_requires_native_appdata_capability_before_analysis(self):
        with patch("mvs.workflow._windows", return_value=True), \
             patch.object(self.service, "_bundle_hash", return_value="synthetic"):
            with self.assertRaises(WorkflowError) as caught:
                self.service._identity(self.root, threading.Event())
        self.assertEqual(caught.exception.code, "incompatible_engine")
        self.assertEqual([c[0] for c in self.service.calls], ["version"])

    def test_artifact_reread_is_reverified(self):
        self.run_one(); original = self.service._terminal
        def changed(folder):
            result = original(folder); (folder / 'output/results.csv').write_text('tampered'); return result
        with patch.object(self.service, "_terminal", side_effect=changed):
            self.assert_error(self.service.dispatch("read_artifact", {"run_id": "r1", "name": "results.csv"}), "invalid_artifacts")

    def test_unknown_native_exit_code_never_completes(self):
        script = self.backend / 'native-double'
        payload = {"schemaVersion": "mvs-cli-result/v1", "command": "version", "exitCode": 3, "status": None}
        script.write_text('#!' + sys.executable + '\nimport sys\nprint(' + repr(json.dumps(payload)) + ')\nsys.exit(3)\n'); script.chmod(0o700)
        service = WorkflowService(script, self.inputs, self.root / 'other-work')
        folder = self.root / 'native-output'; folder.mkdir()
        with self.assertRaises(WorkflowError) as error: service._native(['version'], folder, threading.Event())
        self.assertEqual(error.exception.code, 'native_protocol')

    def test_fast_stderr_overflow_is_rejected_after_exit(self):
        script = self.backend / 'native-double'
        payload = {"schemaVersion": "mvs-cli-result/v1", "command": "version", "exitCode": 0, "status": "completed"}
        script.write_text('#!' + sys.executable + '\nimport sys,json\nsys.stderr.write("x"*2100000)\nprint(' + repr(json.dumps(payload)) + ')\n'); script.chmod(0o700)
        service = WorkflowService(script, self.inputs, self.root / 'other-work')
        folder = self.root / 'native-output'; folder.mkdir()
        with self.assertRaises(WorkflowError) as error: service._native(['version'], folder, threading.Event())
        self.assertEqual(error.exception.code, 'output_limit')

    def test_two_cli_processes_launch_analysis_only_once(self):
        marker = self.root / 'launched.txt'
        script = """import hashlib,json,pathlib,sys,time
args=sys.argv[1:]; command=args[0]
p={"schemaVersion":"mvs-cli-result/v1","command":command,"exitCode":0,"status":"completed","engineVersion":"1.6.2","formulaVersion":"MVS-1.4.0","formulaHash":"synthetic-formula","stateSchema":2,"executionEnvironment":{"fingerprint":"synthetic-environment"},"cliProtocol":{"name":"mvs-cli","major":1},"diagnostics":[],"error":None}
if command=='analyze':
    with open(MARKER,'a') as f:f.write('launch\\n')
    time.sleep(.5)
    output=pathlib.Path(args[args.index('--out')+1]);output.mkdir()
    manifest=output/'run_manifest.json';manifest.write_text('{}')
    p.update(outputDirectory=str(output),manifestPath=str(manifest),artifacts=[dict(name=manifest.name,path=str(manifest),sizeBytes=2,sha256=hashlib.sha256(b'{}').hexdigest())])
print(json.dumps(p))
"""
        self.exe.write_text('#!' + sys.executable + '\nMARKER=' + repr(str(marker)) + '\n' + script)
        self.exe.chmod(0o700)
        argv=[sys.executable,'-m','mvs.workflow_cli','--engine',str(self.exe),'--read-root',str(self.inputs),'--work-root',str(self.root/'work'),'run_analysis']
        request=json.dumps(self.common | {'run_id':'r1'})
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
        first=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        try:
            first.stdin.write(request);first.stdin.close();first.stdin=None
            deadline=time.monotonic()+5
            while not marker.exists():
                if first.poll() is not None or time.monotonic()>deadline: self.fail('First process did not reach synthetic analysis')
                time.sleep(.01)
            second=subprocess.run(argv,input=request,text=True,capture_output=True,env=env,timeout=5)
            self.assertEqual(second.returncode,1,second.stdout)
            self.assertEqual(json.loads(second.stdout)['error']['code'],'busy')
            stdout,stderr=first.communicate(timeout=5)
            self.assertEqual(first.returncode,0,(stdout,stderr))
            self.assertEqual(json.loads(stdout)['execution']['status'],'completed')
            self.assertEqual(marker.read_text().splitlines(),['launch'])
        finally:
            if first.poll() is None: first.kill();first.wait(timeout=3)

    def test_cancel_reaps_owned_native_process(self):
        script = self.backend / 'native-double'
        script.write_text('#!' + sys.executable + '\nimport time,signal\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\ntime.sleep(30)\n'); script.chmod(0o700)
        service = WorkflowService(script, self.inputs, self.root / 'other-work')
        folder = self.root / 'native-output'; folder.mkdir(); event = threading.Event()
        timer = threading.Timer(.15, event.set); timer.start(); start = time.monotonic()
        try:
            with self.assertRaises(WorkflowError) as error: service._native(['version'], folder, event)
        finally: timer.cancel()
        self.assertEqual(error.exception.code, 'cancelled'); self.assertLess(time.monotonic()-start, 5)


if __name__ == '__main__': unittest.main()
