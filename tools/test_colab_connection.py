#!/usr/bin/env python3
"""Offline connection regressions: real helper/cache/files/JavaScript; simulated Colab/network.

These tests do NOT claim a live Google session, native Windows execution or future
Google API compatibility. Native protocol/socket tests are in Core.Tests.
"""
import base64
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from test_colab import ColabTests, ROOT, m
from test_colab_control import ControllerTests

BANNER = "MVS Analyzer 1.4.0 | engine 1.6.0 | formula MVS-1.4.0\nFormula SHA256: 10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c\nUI/Colab revision: ui-colab-3\n"
CODE = "http://127.0.0.1:49321/v1/" + "a" * 64
PLAN = {"Key": "b" * 64, "Kind": "standard", "AppVersion": "1.4.0", "EngineVersion": "1.6.0",
        "FormulaHash": m.FORMULA_HASH, "StateSchema": 2, "Revision": "ui-colab-3"}
IDENTITY = {"appVersion": "1.4.0", "engineVersion": "1.6.0", "formulaHash": m.FORMULA_HASH, "stateSchema": 2,
            "cliProtocol": {"name": "mvs-cli", "major": 1, "capabilities": ["calibrate", "analyze", "state-check", "variance", "melsm", "estimation", "benchmark"]}}


def bundle(code=None, descriptor_change=None, plan_change=None, wire=None, include_runtime=True):
    if code is None:
        code = b'MVS_BOOTSTRAP_API = 1\nclass Workspace:\n    def __init__(self, **kwargs): self.options = kwargs\n'
    if isinstance(code, str):
        code = code.encode()
    wire = wire or m.wire_descriptor()
    plan = {**PLAN, "Transport": wire, **(plan_change or {})}
    descriptor = {"schema": 1, "bootstrapApi": 1, "path": "runtime/mvs_colab.py", "sha256": hashlib.sha256(code).hexdigest(),
                  "transport": wire, "appVersion": "1.4.0", "engineVersion": "1.6.0", "formulaHash": m.FORMULA_HASH, "stateSchema": 2,
                  **(descriptor_change or {})}
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as z:
        z.writestr("colab_job.json", json.dumps(plan if include_runtime else PLAN))
        if include_runtime:
            z.writestr("runtime/manifest.json", json.dumps(descriptor))
            z.writestr("runtime/mvs_colab.py", code)
    return memory.getvalue()


@contextlib.contextmanager
def browser(callback):
    output = types.SimpleNamespace(eval_js=callback)
    modules = {"google": types.ModuleType("google"), "google.colab": types.ModuleType("google.colab")}
    modules["google.colab"].output = output
    with patch.dict(sys.modules, modules):
        yield


class DummyWorkspace:
    protocol = "ui-colab-3"
    wire_major = 1
    def __init__(self, connection="", **kwargs):
        self.connection, self.options = connection, kwargs
        self.epoch, self.sequence, self.command_id, self.url = "new-epoch", 0, "", ""
        self.controls_ready = False


class ConnectionTests(unittest.TestCase):
    def test_exact_reported_banner_survives_notebook_ui_revision_changes(self):
        for revision in ("ui-colab-2", "ui-colab-4", "ui-colab-80", "a-new-UI-label"):
            with self.subTest(revision=revision), patch.object(m, "REVISION", revision):
                result = m.validate_cli_identity(BANNER, PLAN)
                self.assertEqual(result["formulaHash"], m.FORMULA_HASH)

    def test_missing_or_changed_cli_ui_label_is_not_a_scientific_mismatch(self):
        for text in (BANNER.split("UI/Colab")[0], BANNER.replace("ui-colab-3", "new-design-2028")):
            self.assertTrue(m.validate_cli_identity(text, PLAN)["legacy"])

    def test_version_prefixes_and_wrong_formula_are_rejected(self):
        for text in (BANNER.replace("1.4.0 |", "1.4.0.99 |"), BANNER.replace("engine 1.6.0", "engine 1.6.0-beta"),
                     BANNER.replace(m.FORMULA_HASH, "f" * 64), "prefix 1.4.0 1.6.0 " + m.FORMULA_HASH):
            with self.subTest(text=text[:60]), self.assertRaises(m.CompatibilityError):
                m.validate_cli_identity(text, PLAN)

    def test_structured_cli_accepts_additive_fields(self):
        data = {**IDENTITY, "uiRevision": "next-ui", "futureOptionalField": {"value": True}}
        self.assertEqual(m.validate_cli_identity(json.dumps(data), PLAN)["engineVersion"], "1.6.0")

    def test_structured_cli_fields_are_case_insensitive(self):
        data = {key.upper(): value for key, value in IDENTITY.items()}
        self.assertEqual(m.ci(m.validate_cli_identity(json.dumps(data), PLAN), "appVersion"), "1.4.0")

    def test_state_schema_must_be_exact_integer(self):
        for value in (1, 3, 2.0, True, "2", None):
            with self.subTest(value=value), self.assertRaises(m.CompatibilityError):
                m.validate_cli_identity(json.dumps({**IDENTITY, "stateSchema": value}), PLAN)

    def test_structured_scientific_mismatches_are_not_bypassed(self):
        for key, value in (("appVersion", "1.5.0"), ("engineVersion", "1.7.0"), ("formulaHash", "0" * 64)):
            with self.subTest(key=key), self.assertRaises(m.CompatibilityError):
                m.validate_cli_identity(json.dumps({**IDENTITY, key: value}), PLAN)

    def test_breaking_cli_command_contract_is_rejected(self):
        for contract in ({"name": "mvs-cli", "major": 2}, {"name": "mvs-cli", "major": True}, {"name": "other", "major": 1}, None):
            with self.subTest(contract=contract), self.assertRaises(m.CompatibilityError):
                m.validate_cli_identity(json.dumps({**IDENTITY, "cliProtocol": contract}), PLAN)

    def test_missing_cli_command_is_rejected(self):
        identity = copy.deepcopy(IDENTITY)
        identity["cliProtocol"]["capabilities"].remove("state-check")
        with self.assertRaisesRegex(m.CompatibilityError, "state-check"):
            m.validate_cli_identity(json.dumps(identity), PLAN)

    def test_dedicated_scientific_method_requires_its_command(self):
        identity = copy.deepcopy(IDENTITY)
        identity["cliProtocol"]["capabilities"].remove("benchmark")
        with self.assertRaisesRegex(m.CompatibilityError, "benchmark"):
            m.validate_cli_identity(json.dumps(identity), {**PLAN, "Kind": "benchmark"})

    def test_unknown_new_release_cannot_use_the_legacy_banner_adapter(self):
        with self.assertRaisesRegex(m.CompatibilityError, "structured"):
            m.validate_cli_identity(BANNER.replace("1.4.0", "1.5.0"), {**PLAN, "AppVersion": "1.5.0"})

    def test_malformed_cli_json_does_not_fall_back_to_substrings(self):
        for text in ('{"appVersion":"1.4.0"', '{}', '[]', 'not a version'):
            with self.subTest(text=text), self.assertRaises(m.CompatibilityError):
                m.validate_cli_identity(text, PLAN)

    def test_forty_additive_transport_revisions_remain_compatible(self):
        for minor in range(40):
            with self.subTest(minor=minor):
                wire = {**m.wire_descriptor(), "minor": minor, "optionalFutureField": minor}
                features = m.negotiate_transport({"Transport": wire, "Revision": f"future-ui-{minor}"})
                self.assertIn("commands-v1", features)

    def test_breaking_transport_updates_are_rejected(self):
        for changed in ({"major": 2}, {"minimumPeerMinor": 1}, {"minor": -1}, {"major": True}, {"name": "another-product"}):
            with self.subTest(changed=changed), self.assertRaises(m.CompatibilityError):
                m.negotiate_transport({"Transport": {**m.wire_descriptor(), **changed}})

    def test_only_known_explicit_legacy_wire_is_accepted(self):
        self.assertEqual(m.negotiate_transport({"Revision": "ui-colab-3"}), set())
        for plan in ({}, {"Revision": "ui-colab-2"}, {"Revision": "ui-colab-99"}, {"Revision": "ui-colab-3", "Transport": None}):
            with self.subTest(plan=plan), self.assertRaises(m.CompatibilityError):
                m.negotiate_transport(plan)

    def test_capability_shapes_and_required_features_are_checked(self):
        for values in ([], "commands-v1", ["commands-v1", 123], ["job-zip-v1", "commands-v1"]):
            with self.subTest(values=values), self.assertRaises(m.CompatibilityError):
                m.negotiate_transport({"Transport": {**m.wire_descriptor(), "capabilities": values}})

    def test_forty_job_bound_controller_updates_use_the_new_helper(self):
        for minor in range(40):
            with self.subTest(minor=minor):
                source = f'MVS_BOOTSTRAP_API=1\nclass Workspace:\n    revision={minor}\n'
                kind = m.job_runtime_type(bundle(source, wire={**m.wire_descriptor(), "minor": minor},
                                                plan_change={"Revision": f"ui-{minor + 10}"}), DummyWorkspace)
                self.assertEqual(kind.revision, minor)

    def test_real_shipped_helper_loads_from_a_verified_job(self):
        source = (ROOT / "notebooks/mvs_colab.py").read_bytes()
        runtime = m.job_runtime_type(bundle(source), DummyWorkspace)
        self.assertEqual(runtime.cancel_exception.__name__, "RunCancelled")
        self.assertTrue(callable(runtime.activate))
        self.assertTrue(callable(runtime.serve))

    def test_legacy_desktop_job_uses_embedded_controller(self):
        self.assertIs(m.job_runtime_type(bundle(include_runtime=False), DummyWorkspace), DummyWorkspace)

    def test_changed_runtime_bytes_are_never_executed(self):
        with self.assertRaisesRegex(m.CompatibilityError, "checksum"):
            m.job_runtime_type(bundle('raise AssertionError("CORRUPT CODE EXECUTED")', {"sha256": "0" * 64}), DummyWorkspace)

    def test_unknown_bootstrap_manifests_are_not_silently_accepted(self):
        for changed in ({"schema": 2}, {"schema": True}, {"bootstrapApi": 2}, {"path": "../unsafe.py"}, {"transport": None}):
            with self.subTest(changed=changed), self.assertRaises(m.CompatibilityError):
                m.job_runtime_type(bundle('raise AssertionError("UNSUPPORTED CODE EXECUTED")', changed), DummyWorkspace)

    def test_runtime_job_scientific_identity_must_match(self):
        for changed in ({"engineVersion": "1.7.0"}, {"formulaHash": "f" * 64}, {"stateSchema": None}):
            with self.subTest(changed=changed), self.assertRaises(m.CompatibilityError):
                m.job_runtime_type(bundle(descriptor_change=changed), DummyWorkspace)

    def test_runtime_declared_interface_is_verified(self):
        for source in ('MVS_BOOTSTRAP_API=2\nclass Workspace: pass', 'MVS_BOOTSTRAP_API=1\nWorkspace="not a controller"'):
            with self.assertRaises(m.CompatibilityError):
                m.job_runtime_type(bundle(source), DummyWorkspace)

    def test_duplicate_bundle_paths_are_rejected(self):
        memory = io.BytesIO(bundle())
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(memory, "a") as z:
                z.writestr("runtime/mvs_colab.py", "bad")
        with self.assertRaisesRegex(m.CompatibilityError, "duplicate"):
            m.job_runtime_type(memory.getvalue(), DummyWorkspace)

    def test_bootstrap_fetches_the_job_only_once_and_preserves_ownership(self):
        old = DummyWorkspace(CODE)
        old.epoch, old.sequence, old.command_id = "known-runtime", 19, "c" * 64
        archive = bundle(include_runtime=False)
        with patch.object(m, "Workspace", DummyWorkspace), patch.object(m, "fetch_job_archive", return_value=archive) as fetch:
            new = m.bootstrap_workspace(CODE, previous=old)
        fetch.assert_called_once_with(CODE)
        self.assertEqual(new._prefetched_archive, archive)
        self.assertEqual((new.epoch, new.sequence, new.command_id), (old.epoch, old.sequence, old.command_id))

    def test_new_code_cannot_inherit_an_old_runtime_generation(self):
        old = DummyWorkspace(CODE)
        old.epoch, old.sequence = "old-runtime", 123
        with patch.object(m, "Workspace", DummyWorkspace), patch.object(m, "fetch_job_archive", return_value=bundle(include_runtime=False)):
            new = m.bootstrap_workspace(CODE.replace("a" * 64, "b" * 64), previous=old)
        self.assertEqual((new.epoch, new.sequence), ("new-epoch", 0))

    def test_running_controller_must_be_stopped_before_bootstrap(self):
        old = DummyWorkspace(CODE)
        old.controls_ready = True
        with patch.object(m, "fetch_job_archive") as fetch, self.assertRaises(RuntimeError):
            m.bootstrap_workspace(CODE, previous=old)
        fetch.assert_not_called()

    def test_job_download_rejects_damaged_base64(self):
        with patch.object(m, "browser_request", return_value={"archive": "not base64 !"}), self.assertRaises(ValueError):
            m.fetch_job_archive(CODE)

    def test_transient_get_is_retried_with_a_bounded_budget(self):
        replies = iter([{"ok": False, "status": 0}, {"ok": False, "status": 503}, {"ok": True, "value": {"ready": True}}])
        calls = []
        def evaluate(script, **kwargs):
            calls.append((script, kwargs))
            return next(replies)
        with browser(evaluate), patch.object(m.time, "sleep") as sleep:
            self.assertEqual(m.browser_request(CODE, "request"), {"ready": True})
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(all(call[1]["timeout_sec"] == 13 for call in calls))

    def test_revoked_code_stops_retries_and_provides_actionable_diagnostic(self):
        calls = []
        def evaluate(script, **kwargs):
            calls.append(script)
            return {"ok": False, "status": 403}
        with browser(evaluate), patch.object(m.time, "sleep") as sleep, self.assertRaises(m.BridgeError) as error:
            m.browser_request(CODE, "job")
        self.assertEqual(len(calls), 1)
        self.assertEqual(error.exception.code, "connection_revoked")
        self.assertFalse(error.exception.retryable)
        self.assertIn("fresh code", str(error.exception))
        sleep.assert_not_called()

    def test_protocol_and_output_errors_are_not_treated_as_outages(self):
        for status, code in ((426, "incompatible_transport"), (409, "runtime_conflict"), (400, "invalid_payload"), (413, "payload_too_large")):
            with self.subTest(status=status), browser(lambda *a, **k: {"ok": False, "status": status, "error": {"code": code, "message": "specific reason"}}), self.assertRaises(m.BridgeError) as error:
                m.browser_request(CODE, "request")
            self.assertEqual(error.exception.code, code)
            self.assertFalse(error.exception.retryable)

    def test_legacy_post_is_not_automatically_replayed(self):
        calls = []
        def evaluate(script, **kwargs):
            calls.append(script)
            return {"ok": False, "status": 0}
        with browser(evaluate), self.assertRaises(m.BridgeError):
            m.browser_request(CODE, "status", {"sequence": 1})
        self.assertEqual(len(calls), 1)

    def test_negotiated_post_retry_reuses_identical_bytes(self):
        calls = []
        def evaluate(script, **kwargs):
            calls.append(script)
            return {"ok": False, "status": 0} if len(calls) == 1 else {"ok": True, "value": {"ok": True, "duplicate": True}}
        with browser(evaluate), patch.object(m.time, "sleep"):
            reply = m.browser_request(CODE, "status", {"sequence": 12, "phase": "ready"}, attempts=3)
        self.assertTrue(reply["duplicate"])
        self.assertEqual(calls[0], calls[1])

    def test_private_code_is_redacted_from_browser_exceptions(self):
        with browser(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fetch failed: " + CODE))), patch.object(m.time, "sleep"), self.assertRaises(m.BridgeError) as error:
            m.browser_request(CODE, "request")
        self.assertNotIn("a" * 64, str(error.exception))
        self.assertIn("local-network", str(error.exception))

    def test_endpoint_validation_precedes_browser_access(self):
        for code, route in (("https://example.com/v1/" + "a" * 64, "job"), (CODE, "shell"), (CODE.replace("127.0.0.1", "localhost"), "job")):
            with self.subTest(code=code[:30]), self.assertRaises(ValueError):
                m.browser_request(code, route)

    def test_corrupt_files_are_not_hidden_behind_not_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = ColabTests().fixture(directory)
            workspace.connection = CODE
            with patch.object(workspace, "packet", side_effect=ValueError("corrupt output")), patch.object(m, "browser_request") as transport:
                with self.assertRaisesRegex(ValueError, "corrupt output"):
                    workspace.send(include_files=True)
            transport.assert_not_called()
            self.assertTrue(workspace._files_pending)

    def test_send_uses_new_retry_capability_but_keeps_legacy_label(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = ColabTests().fixture(directory)
            workspace.connection = CODE
            workspace.peer_capabilities = {"status-retry-v1"}
            with patch.object(m, "REVISION", "future-ui-80"), patch.object(m, "browser_request", return_value={"ok": True}) as transport:
                self.assertTrue(workspace.send())
            args, kwargs = transport.call_args
            self.assertEqual(args[2]["revision"], "ui-colab-3")
            self.assertEqual(args[2]["transport"]["major"], 1)
            self.assertEqual(kwargs, {"attempts": 3})

    def test_controller_recovers_after_more_than_three_failures_without_duplicate_work(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = ControllerTests().fixture(directory)
            workspace.connection = CODE
            executed = []
            def calculate():
                executed.append("calibrate")
                workspace.phase = "calibrated"
            workspace.calibrate = calculate
            command = ControllerTests.command(workspace)
            events = iter([m.BridgeError("timeout", "temporary", retryable=True)] * 5 + [command, command, m.BridgeError("connection_revoked", "stop", 403, False)])
            def request(*args, **kwargs):
                event = next(events)
                if isinstance(event, Exception):
                    raise event
                return event
            with patch.object(m, "browser_request", request), patch.object(m.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
                workspace.serve()
            self.assertEqual(executed, ["calibrate"])
            self.assertTrue(workspace.state_path.exists())
            self.assertTrue(workspace.command_receipt(command["CommandId"]).exists())
            self.assertEqual(workspace.connection_error.code, "connection_revoked")

    def test_controller_permanent_error_does_not_wait_for_retry_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _ = ControllerTests().fixture(directory)
            workspace.connection = CODE
            workspace.connection_error = m.BridgeError("incompatible_transport", "update", 426, False)
            workspace.send = lambda **kwargs: False
            with patch.object(m.time, "sleep") as sleep, contextlib.redirect_stdout(io.StringIO()):
                workspace.serve()
            sleep.assert_not_called()
            self.assertFalse(workspace.controls_ready)

    def make_builder(self, directory):
        workspace, _ = ColabTests().fixture(directory)
        workspace.dotnet = Path(sys.executable)
        source = workspace.root / "sources" / "test-source"
        source.mkdir(parents=True)
        calls = []
        def publish(command):
            calls.append(command)
            out = Path(command[command.index("-o") + 1])
            out.mkdir(parents=True)
            for name, content in (("mvs.dll", "verified-binary"), ("mvs.deps.json", "{}"), ("mvs.runtimeconfig.json", "{}")):
                (out / name).write_text(content)
        workspace.run_process = publish
        return workspace, source, calls

    def test_cache_is_validated_and_reused_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, source, calls = self.make_builder(directory)
            saved = workspace.state_path.read_bytes()
            with patch.object(m.subprocess, "check_output", return_value=BANNER), contextlib.redirect_stdout(io.StringIO()):
                workspace.prepare_cli_binary(source, "d" * 64)
                workspace.prepare_cli_binary(source, "d" * 64)
            self.assertEqual(len(calls), 1)
            self.assertEqual(workspace.state_path.read_bytes(), saved)
            self.assertTrue(m.cli_cache_valid(source / "colab-publish", "d" * 64))

    def test_tampered_cached_binary_is_rebuilt_once(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, source, calls = self.make_builder(directory)
            with patch.object(m.subprocess, "check_output", return_value=BANNER), contextlib.redirect_stdout(io.StringIO()):
                workspace.prepare_cli_binary(source, "d" * 64)
                workspace.dll.write_text("partial stale binary")
                workspace.prepare_cli_binary(source, "d" * 64)
                workspace.prepare_cli_binary(source, "d" * 64)
            self.assertEqual(len(calls), 2)
            self.assertEqual(workspace.dll.read_text(), "verified-binary")

    def test_wrong_cached_cli_identity_is_rebuilt_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, source, calls = self.make_builder(directory)
            with patch.object(m.subprocess, "check_output", return_value=BANNER), contextlib.redirect_stdout(io.StringIO()):
                workspace.prepare_cli_binary(source, "d" * 64)
            with patch.object(m.subprocess, "check_output", side_effect=[BANNER.replace("engine 1.6.0", "engine 9.0.0"), BANNER]), contextlib.redirect_stdout(io.StringIO()):
                workspace.prepare_cli_binary(source, "d" * 64)
            self.assertEqual(len(calls), 2)

    def test_failed_build_preserves_old_files_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, source, calls = self.make_builder(directory)
            previous = source / "colab-publish"
            previous.mkdir()
            (previous / "mvs.dll").write_text("old version preserved")
            saved = workspace.state_path.read_bytes()
            with patch.object(workspace, "inspect_cli", side_effect=m.CompatibilityError("wrong formula")), self.assertRaises(m.CompatibilityError):
                workspace.prepare_cli_binary(source, "d" * 64)
            self.assertEqual((previous / "mvs.dll").read_text(), "old version preserved")
            self.assertEqual(workspace.state_path.read_bytes(), saved)
            self.assertEqual(list(source.glob("colab-build-*")), [])
            self.assertEqual(len(calls), 1)

    def test_source_cache_is_compared_to_the_exact_embedded_payload(self):
        source_zip = ROOT / "Assets/colab-cli-source.zip"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            self.assertFalse(m.source_bundle_valid(source_zip, source))
            m.safe_extract(source_zip, source)
            self.assertTrue(m.source_bundle_valid(source_zip, source))
            target = source / "MvsAnalyzer.Cli/Program.cs"
            target.write_text("damaged source")
            self.assertFalse(m.source_bundle_valid(source_zip, source))
            m.safe_extract(source_zip, source)
            self.assertTrue(m.source_bundle_valid(source_zip, source))

    @unittest.skipUnless(shutil.which("node"), "Node is needed to execute the generated browser JavaScript")
    def test_real_generated_javascript_preserves_structured_errors_and_security_options(self):
        scripts = []
        def evaluate(script, **kwargs):
            scripts.append(script)
            runner = "const options=[]; global.fetch=async (url,opt)=>{options.push(opt); return {ok:false,status:426,json:async()=>({error:{code:'incompatible_transport',message:'update',retryable:false}})};};\n(async()=>{const reply=await eval(" + json.dumps(script) + ");console.log(JSON.stringify({reply,options}));})().catch(e=>{console.error(e);process.exit(1)});"
            data = json.loads(subprocess.check_output(["node", "-e", runner], text=True, timeout=5))
            self.assertEqual(data["options"][0]["credentials"], "omit")
            self.assertEqual(data["options"][0]["redirect"], "error")
            self.assertEqual(data["options"][0]["cache"], "no-store")
            return data["reply"]
        with browser(evaluate), self.assertRaises(m.BridgeError) as error:
            m.browser_request(CODE, "request")
        self.assertEqual(error.exception.code, "incompatible_transport")
        self.assertEqual(len(scripts), 1)

    def test_generated_notebooks_have_a_bootstrap_and_no_saved_private_output(self):
        for name in ("MVS_Colab.ipynb", "MVS_Colab_Benchmark.ipynb"):
            notebook = json.loads((ROOT / "notebooks" / name).read_text())
            code = "\n".join("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code")
            self.assertIn("mvs = bootstrap_workspace(", code)
            self.assertIn('getattr(_mvs_error, "code", "") in {"connection_revoked"', code)
            self.assertNotIn(CODE, code)
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    self.assertEqual(cell["outputs"], [])
                    self.assertIsNone(cell["execution_count"])
                    compile("".join(cell["source"]), name, "exec")

    def test_only_explicit_connection_files_were_removed_from_original_byte_pins(self):
        pins = json.loads((ROOT / "validation/ui-patch-baseline.json").read_text())
        self.assertEqual(set(pins["intentionallyChangedConnectionFiles"]), {"Infrastructure/ColabSession.cs", "MvsAnalyzer.Cli/Program.cs", "SharedSources.props", "MvsAnalyzer.csproj"})
        self.assertEqual(len(pins["sha256"]), 30)
        self.assertIn("MvsAnalyzer.Cli/HeadlessRun.cs", pins["sha256"])
        for path, expected in pins["sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path)


if __name__ == "__main__":
    unittest.main(defaultTest="ConnectionTests", verbosity=2)
