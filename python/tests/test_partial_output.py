"""Round33 failure-evidence tests; synthetic peers, not scientific parity."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mvs.engine import Engine, EngineError, InputError, MvsError, ScientificDiagnostic
from mvs.models import AnalysisResult, Artifact, BaseResult, Calibration
from mvs.workflow import WorkflowService, canonical, digest


SCOPE = "current_invocation_successful_writes"


def identity(command="version"):
    return {"schemaVersion": "mvs-cli-result/v1", "command": command,
            "status": "completed", "exitCode": 0, "engineVersion": "synthetic-engine",
            "formulaVersion": "synthetic-formula", "formulaHash": "0" * 64,
            "stateSchema": 2, "executionEnvironment": {"fingerprint": "synthetic-environment"},
            "cliProtocol": {"name": "mvs-cli", "major": 1}}


def process(payload, returncode=None):
    return subprocess.CompletedProcess([], payload["exitCode"] if returncode is None else returncode,
                                       json.dumps(payload), "")


def partial_payload(output):
    saved = output / "results.csv"
    return identity("analyze") | {
        "status": "error", "exitCode": 1, "outputDirectory": str(output), "manifestPath": None,
        "runId": None, "artifacts": [{"name": saved.name, "path": str(saved),
                                      "sizeBytes": saved.stat().st_size, "sha256": digest(saved.read_bytes())}],
        "partialOutput": {"status": "incomplete", "scope": SCOPE,
                          "attemptedPath": str(output / "run_manifest.json"),
                          "unverifiedPaths": [str(output / "retired.csv")]},
        "error": {"type": "IOException", "message": "synthetic export failure"}}


class PartialApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.output = self.root / "output"; self.output.mkdir()
        (self.output / "results.csv").write_bytes(b"metric,value\nmean,2\n")
        (self.output / "stale.json").write_text('{"old":true}', encoding="utf-8")
        self.cli = self.root / "synthetic-mvs"; self.cli.write_text("synthetic fixture", encoding="utf-8")
        with patch("mvs.engine.subprocess.run", return_value=process(identity())):
            self.engine = Engine(self.cli)

    def call(self):
        return self.engine.analyze("synthetic.csv", calibration="synthetic.json", output=self.output)

    def test_exception_constructor_remains_backward_compatible(self):
        for args in [(), ("message",), ("first", "second")]:
            error = MvsError(*args)
            self.assertEqual(error.args, args)
            self.assertEqual(str(error), str(RuntimeError(*args)))
            self.assertIsNone(error.result)

    def test_engine_and_input_errors_retain_typed_result_and_original_message(self):
        for native_type, expected in [("IOException", EngineError), ("InvalidDataException", InputError)]:
            with self.subTest(native_type=native_type):
                payload = partial_payload(self.output)
                payload["error"]["type"] = native_type
                with patch("mvs.engine.subprocess.run", return_value=process(payload)):
                    with self.assertRaises(expected) as caught: self.call()
                error = caught.exception
                self.assertEqual(str(error), "synthetic export failure")
                self.assertIsInstance(error.result, AnalysisResult)
                self.assertEqual(error.result.raw, payload)
                self.assertEqual((error.result.status, error.result.exit_code), ("error", 1))
                self.assertEqual(error.result.artifact("results.csv"), self.output / "results.csv")
                self.assertEqual(error.result.read_csv("results.csv"), [{"metric": "mean", "value": "2"}])
                self.assertIsNone(error.result.manifest)

    def test_old_native_error_also_exposes_parsed_result(self):
        payload = identity("analyze") | {"status": "error", "exitCode": 1,
                                        "error": {"type": "IOException", "message": "old error"}}
        with patch("mvs.engine.subprocess.run", return_value=process(payload)):
            with self.assertRaises(EngineError) as caught: self.call()
        self.assertIsInstance(caught.exception.result, BaseResult)
        self.assertEqual(str(caught.exception), "old error")
        self.assertNotIn("partialOutput", caught.exception.result.raw)

    def test_unparsed_launch_and_json_failures_have_no_result(self):
        with patch("mvs.engine.subprocess.run", side_effect=OSError("synthetic launch failure")):
            with self.assertRaises(EngineError) as caught: self.call()
        self.assertIsNone(caught.exception.result)
        with patch("mvs.engine.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "invalid", "")):
            with self.assertRaises(EngineError) as caught: self.call()
        self.assertIsNone(caught.exception.result)

    def test_exit_disagreement_keeps_already_parsed_result(self):
        payload = partial_payload(self.output)
        with patch("mvs.engine.subprocess.run", return_value=process(payload, returncode=0)):
            with self.assertRaisesRegex(EngineError, "disagrees") as caught: self.call()
        self.assertEqual(caught.exception.result.raw, payload)

    def test_failed_result_never_falls_back_to_unlisted_stale_files(self):
        result = BaseResult("analyze", "error", 1, self.output, None, "synthetic", "synthetic", None,
                            (Artifact("results.csv", self.output / "results.csv"),))
        for name in ["stale.json", str(self.output / "stale.json")]:
            with self.subTest(name=name):
                with self.assertRaises(FileNotFoundError): result.artifact(name)
        for status, code in [("completed", 0), ("diagnostic", 2)]:
            with self.subTest(status=status):
                self.assertEqual(replace(result, status=status, exit_code=code).artifact("stale.json"),
                                 self.output / "stale.json")
        diagnostic = ScientificDiagnostic("inspect", replace(result, status="diagnostic", exit_code=2))
        self.assertEqual(str(diagnostic), "inspect")
        self.assertEqual(diagnostic.result.exit_code, 2)

    def test_failed_result_cannot_copy_stale_directory_as_completed_output(self):
        result = BaseResult("analyze", "error", 1, self.output, None, "synthetic", "synthetic", None)
        target = self.root / "failed-copy"
        with self.assertRaisesRegex(ValueError, "incomplete output"):
            result.copy_to(target)
        self.assertFalse(target.exists())
        for status, code in [("completed", 0), ("diagnostic", 2)]:
            destination = self.root / status
            self.assertEqual(replace(result, status=status, exit_code=code).copy_to(destination), destination)
            self.assertEqual((destination / "stale.json").read_bytes(), (self.output / "stale.json").read_bytes())

    def test_failed_calibration_result_cannot_reuse_stale_state_for_analysis(self):
        (self.output / "calibration_state.json").write_bytes(b'{"old":true}')
        calibration = Calibration("calibrate", "error", 1, self.output, None, "synthetic", "synthetic", None)
        for status, code in [("error", 1), ("error", 0), ("completed", 1), ("diagnostic", 1)]:
            with self.subTest(status=status, code=code), patch("mvs.engine.subprocess.run") as run:
                failed = replace(calibration, status=status, exit_code=code)
                with self.assertRaisesRegex(InputError, "failed calibration") as caught:
                    self.engine.analyze("synthetic.csv", calibration=failed, output=self.root / "rejected")
                self.assertIs(caught.exception.result, failed)
                run.assert_not_called()
                self.assertFalse((self.root / "rejected").exists())
        for status, code in [("completed", 0), ("diagnostic", 2)]:
            with self.subTest(status=status), patch("mvs.engine.subprocess.run", return_value=process(identity("analyze"))) as run:
                self.engine.analyze("synthetic.csv", calibration=replace(calibration, status=status, exit_code=code),
                                    output=self.root / "accepted")
                run.assert_called_once()


class PartialService(WorkflowService):
    """Explicit native double with only current-invocation writes advertised."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []; self.hook = None

    def _native(self, args, folder, cancel):
        self.calls.append(args[0])
        payload = identity(args[0])
        if args[0] == "analyze":
            output = Path(args[args.index("--out") + 1]) / "selected-run"
            output.mkdir(parents=True)
            (output / "results.csv").write_bytes(b"metric,value\nmean,2\n")
            (output / "stale.json").write_bytes(b'{"old":true}')
            # A failing target can be a directory and must never be read as success.
            (output / "run_manifest.json").mkdir()
            payload = partial_payload(output)
            # These details must never reach portable workflow/MCP responses.
            payload["runId"] = str(folder / "private-run-id")
            payload["error"]["message"] = "Failure at " + str(folder / "private-error")
            payload["diagnostics"] = [{"message": str(folder / "private-diagnostic")}]
            if self.hook: self.hook(payload, output)
        return payload


@unittest.skipUnless(sys.platform.startswith("linux"), "Synthetic local Linux workflow fixtures")
class PartialWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.inputs = self.root / "inputs"; self.inputs.mkdir()
        self.backend = self.root / "engine"; self.backend.mkdir()
        self.cli = self.backend / "mvs"; self.cli.write_text("synthetic fixture", encoding="utf-8")
        (self.inputs / "data.csv").write_bytes(b"entity,group,value\na,A,1\n")
        (self.inputs / "state.json").write_bytes(b'{"Processing":{}}')
        self.service = PartialService(self.cli, self.inputs, self.root / "work")
        self.request = {"run_id": "partial", "data": "data.csv", "calibration": "state.json"}

    def run_one(self):
        return self.service.dispatch("run_analysis", self.request)

    def assert_private(self, result):
        portable = canonical(result).decode("utf-8")
        self.assertNotIn(str(self.root), portable)
        for sensitive in ["private-run-id", "private-error", "private-diagnostic", "outside-secret",
                          "attemptedPath", "unverifiedPaths", "outputDirectory", "manifestPath", '"path"']:
            self.assertNotIn(sensitive, portable)
        return portable

    def test_failed_receipt_keeps_only_verified_names_sizes_and_hashes(self):
        result = self.run_one()
        self.assertEqual(result["execution"], {"status": "error", "nativeExitCode": 1, "outcome": "error"})
        self.assertEqual(result["error"]["code"], "native_error")
        self.assertEqual(result["data"]["partialOutput"], {
            "status": "incomplete", "scope": SCOPE, "attemptedName": "run_manifest.json",
            "unverifiedNames": ["retired.csv"],
            "artifacts": [{"name": "results.csv", "sizeBytes": 20, "sha256": digest(b"metric,value\nmean,2\n")}]})
        self.assert_private(result)
        self.assertNotIn("stale.json", canonical(result).decode("utf-8"))
        self.assertTrue(result["data"]["partialEvidenceRetained"])
        receipt = self.root / "work/runs/partial/result.json"
        self.assertEqual(json.loads(receipt.read_bytes())["result"], result)

    def test_failed_receipt_replay_is_idempotent_and_does_not_enable_artifact_reads(self):
        result = self.run_one(); calls = list(self.service.calls)
        self.assertEqual(self.run_one(), result)
        self.assertEqual(self.service.dispatch("get_run", {"run_id": "partial"}), result)
        self.assertEqual(self.service.calls, calls)
        read = self.service.dispatch("read_artifact", {"run_id": "partial", "name": "results.csv"})
        self.assertEqual(read["error"]["code"], "incomplete_run")
        self.assert_private(read)

    def test_empty_successful_write_list_and_missing_uncertain_targets_are_allowed(self):
        def mutate(payload, output):
            payload["artifacts"] = []
            payload["partialOutput"]["attemptedPath"] = None
        self.service.hook = mutate
        result = self.run_one()
        self.assertEqual(result["execution"]["nativeExitCode"], 1)
        self.assertEqual(result["data"]["partialOutput"]["artifacts"], [])
        self.assertIsNone(result["data"]["partialOutput"]["attemptedName"])
        self.assertEqual(result["data"]["partialOutput"]["unverifiedNames"], ["retired.csv"])

    def test_new_verified_manifest_is_valid_but_never_exposes_native_run_id(self):
        def mutate(payload, output):
            manifest = output / "run_manifest.json"; manifest.rmdir(); manifest.write_bytes(b'{}')
            payload["manifestPath"] = str(manifest)
            payload["artifacts"].append({"name": manifest.name, "path": str(manifest),
                                         "sizeBytes": 2, "sha256": digest(b'{}')})
            payload["partialOutput"]["attemptedPath"] = None
        self.service.hook = mutate
        result = self.run_one()
        self.assertEqual([a["name"] for a in result["data"]["partialOutput"]["artifacts"]],
                         ["results.csv", "run_manifest.json"])
        self.assert_private(result)

    def test_unknown_metadata_is_omitted_and_artifact_read_limit_is_retained(self):
        def mutate(payload, output):
            payload["partialOutput"]["unexpected"] = str(self.root / "outside-secret")
            payload["artifacts"][0]["unexpected"] = str(self.root / "outside-secret")
        self.service.hook = mutate
        result = self.run_one()
        self.assertEqual(result["execution"]["nativeExitCode"], 1)
        self.assertNotIn("unexpected", self.assert_private(result))
        self.request["run_id"] = "bounded"
        with patch("mvs.workflow.MAX_ARTIFACT", 1):
            result = self.run_one()
        self.assertEqual(result["error"]["code"], "invalid_file")
        self.assertNotIn("partialOutput", result["data"])

    def test_old_native_error_without_partial_metadata_preserves_old_receipt(self):
        self.service.hook = lambda payload, output: payload.pop("partialOutput")
        result = self.run_one()
        self.assertEqual(result["execution"]["status"], "error")
        self.assertIsNone(result["execution"]["nativeExitCode"])
        self.assertEqual(set(result["data"]), {"runId", "inputs", "partialEvidenceRetained"})
        self.assertEqual(result["error"], {"code": "native_error", "message":
                         "Native analysis failed; local diagnostics and partial artifacts are retained."})
        self.assertEqual(self.run_one(), result)

    def test_malformed_or_escaping_partial_metadata_fails_closed(self):
        outside = self.root / "outside-secret"; outside.write_bytes(b"secret")
        cases = {
            "null_partial": lambda p, o: p.update(partialOutput=None),
            "wrong_scope": lambda p, o: p["partialOutput"].update(scope="all_files"),
            "wrong_status": lambda p, o: p["partialOutput"].update(status="completed"),
            "missing_attempted": lambda p, o: p["partialOutput"].pop("attemptedPath"),
            "bad_unverified": lambda p, o: p["partialOutput"].update(unverifiedPaths="secret"),
            "bad_artifacts": lambda p, o: p.update(artifacts={}),
            "output_escape": lambda p, o: p.update(outputDirectory=str(self.root)),
            "output_snapshot": lambda p, o: p.update(outputDirectory=str(o.parent.parent)),
            "artifact_escape": lambda p, o: p["artifacts"][0].update(path=str(outside)),
            "attempted_escape": lambda p, o: p["partialOutput"].update(attemptedPath=str(outside)),
            "unverified_escape": lambda p, o: p["partialOutput"].update(unverifiedPaths=[str(outside)]),
            "traversal": lambda p, o: p["artifacts"][0].update(path=str(o / ".." / "selected-run" / "results.csv")),
            "nested_target": lambda p, o: p["partialOutput"].update(attemptedPath=str(o / "nested/file.csv")),
            "null_target": lambda p, o: p["partialOutput"].update(unverifiedPaths=[None]),
            "nul_target": lambda p, o: p["partialOutput"].update(attemptedPath="\x00"),
            "backslash_name": lambda p, o: p["partialOutput"].update(attemptedPath=str(o / "private\\file.csv")),
            "artifact_name": lambda p, o: p["artifacts"][0].update(name="../outside-secret"),
            "artifact_type": lambda p, o: p.update(artifacts=[None]),
            "artifact_path_type": lambda p, o: p["artifacts"][0].update(path=1),
            "size_mismatch": lambda p, o: p["artifacts"][0].update(sizeBytes=1),
            "bool_size": lambda p, o: p["artifacts"][0].update(sizeBytes=True),
            "hash_mismatch": lambda p, o: p["artifacts"][0].update(sha256="0" * 64),
            "duplicate": lambda p, o: p["artifacts"].append(dict(p["artifacts"][0])),
            "attempted_is_success": lambda p, o: p["partialOutput"].update(attemptedPath=str(o / "results.csv")),
            "unverified_is_success": lambda p, o: p["partialOutput"].update(unverifiedPaths=[str(o / "results.csv")]),
            "missing_manifest": lambda p, o: p.update(manifestPath=str(o / "run_manifest.json")),
            "modified_file": lambda p, o: (o / "results.csv").write_bytes(b"changed"),
            "missing_file": lambda p, o: (o / "results.csv").unlink(),
        }
        for index, (name, mutate) in enumerate(cases.items()):
            with self.subTest(name=name):
                self.request["run_id"] = f"bad{index}"
                self.service.hook = mutate
                result = self.run_one()
                self.assertEqual(result["execution"]["status"], "error", result)
                self.assertNotIn("partialOutput", result["data"])
                self.assertNotEqual(result["error"]["code"], "native_error")
                self.assert_private(result)
                calls = list(self.service.calls)
                self.assertEqual(self.run_one(), result)
                self.assertEqual(self.service.calls, calls)

    def test_symlinks_and_nonregular_successes_are_rejected_without_reading(self):
        outside = self.root / "outside-secret"; outside.write_bytes(b"secret")
        def symlink(payload, output):
            path = output / "results.csv"; path.unlink(); path.symlink_to(outside)
        def directory(payload, output):
            path = output / "results.csv"; path.unlink(); path.mkdir()
        def fifo(payload, output):
            path = output / "results.csv"; path.unlink(); os.mkfifo(path)
        for index, mutate in enumerate([symlink, directory, fifo]):
            with self.subTest(kind=index):
                self.request["run_id"] = f"special{index}"
                self.service.hook = mutate
                result = self.run_one()
                self.assertEqual(result["execution"]["status"], "error")
                self.assertNotIn("partialOutput", result["data"])
                self.assert_private(result)
                # Remove only the disposable obstruction before the next quota scan.
                path = self.root / f"work/runs/special{index}/output/selected-run/results.csv"
                if index == 1: path.rmdir()
                else: path.unlink()

    def test_real_synthetic_process_preserves_partial_error_through_api_and_workflow(self):
        script = f'''#!{sys.executable}
import hashlib, json, pathlib, sys
args = sys.argv[1:]
payload = {identity()!r}
payload["command"] = args[0]
if args[0] == "analyze":
    output = pathlib.Path(args[args.index("--out") + 1]) / "selected-run"
    output.mkdir(parents=True)
    saved = output / "results.csv"
    saved.write_bytes(b"x,y\\n1,2\\n")
    payload.update(status="error", exitCode=1, outputDirectory=str(output), manifestPath=None, runId=None,
        artifacts=[{{"name": saved.name, "path": str(saved), "sizeBytes": saved.stat().st_size,
                     "sha256": hashlib.sha256(saved.read_bytes()).hexdigest()}}],
        partialOutput={{"status": "incomplete", "scope": {SCOPE!r},
                       "attemptedPath": str(output / "run_manifest.json"), "unverifiedPaths": []}},
        error={{"type": "IOException", "message": "synthetic failure"}})
print(json.dumps(payload))
sys.exit(payload["exitCode"])
'''
        self.cli.write_text(script, encoding="utf-8"); self.cli.chmod(0o700)
        engine = Engine(self.cli)
        with self.assertRaises(EngineError) as caught:
            engine.analyze("synthetic.csv", calibration="synthetic.json", output=self.root / "api-output")
        self.assertIsInstance(caught.exception.result, AnalysisResult)
        self.assertEqual(caught.exception.result.artifacts[0].name, "results.csv")
        service = WorkflowService(self.cli, self.inputs, self.root / "real-work")
        result = service.dispatch("run_analysis", self.request)
        self.assertEqual(result["execution"], {"status": "error", "nativeExitCode": 1, "outcome": "error"})
        self.assertEqual(result["data"]["partialOutput"]["artifacts"][0]["name"], "results.csv")
        self.assert_private(result)
        self.assertEqual(service.dispatch("run_analysis", self.request), result)

    @unittest.skipUnless(importlib.util.find_spec("mcp") is not None, "requires optional official MCP SDK")
    def test_mcp_failed_receipt_is_sanitized_and_stays_an_error(self):
        from test_mcp_server import Wire
        server = ("import sys, anyio\n"
                  f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
                  "from test_partial_output import PartialService\n"
                  "from mvs.mcp_server import serve_stdio\n"
                  "anyio.run(serve_stdio, PartialService(*sys.argv[1:]))\n")
        wire = Wire(self.root, [sys.executable, "-u", "-c", server, str(self.cli),
                               str(self.inputs), str(self.root / "mcp-work")])
        try:
            wire.initialize()
            reply = wire.call("run_analysis", self.request)
            self.assertTrue(reply["isError"])
            result = reply["structuredContent"]
            self.assertEqual(json.loads(reply["content"][0]["text"]), result)
            self.assertEqual(result["execution"]["nativeExitCode"], 1)
            self.assertEqual(result["data"]["partialOutput"]["artifacts"][0]["name"], "results.csv")
            self.assert_private(result)
            replay = wire.call("get_run", {"run_id": "partial"})
            self.assertTrue(replay["isError"])
            self.assertEqual(replay["structuredContent"], result)
            denied = wire.call("read_artifact", {"run_id": "partial", "name": "results.csv"})
            self.assertTrue(denied["isError"])
            self.assertEqual(denied["structuredContent"]["error"]["code"], "incomplete_run")
        finally:
            wire.close()


if __name__ == "__main__":
    unittest.main()
