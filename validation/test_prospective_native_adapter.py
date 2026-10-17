"""Reproducible bounded-input native checks; never run a valid engineering request.

Enable with MVS_PROSPECTIVE_NATIVE=/absolute/path/MvsAnalyzer.Core.Tests.dll.
DOTNET optionally selects the dotnet executable. No build or restore is performed.
MVS_PROSPECTIVE_NATIVE_EVIDENCE optionally names a new evidence directory; native
stdout/stderr and case results are retained there without overwriting old evidence.
Without an explicit native DLL these tests report the native class as skipped.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "mvs-prospective-adapter-envelope-v1"
PROTOCOL = "round55-prospective-adapter-engineering-v1"
REQUEST_SHA = "6aed9dd4fb65af09414db6b245edfe29173b72521807fa3dafa4008ef396e440"
COUNT_SCOPE = "adapter_entry_calls_only_nested_production_calls_not_instrumented"
ZERO_COUNTS = dict.fromkeys((
    "fixtureMaterializationCount", "buildCallCount", "runCallCount", "legacyCallCount",
    "completenessCallCount", "payloadSerializationCount", "directGenerateCallCount", "directFitCallCount",
), 0)
REQUEST = {
    "schemaVersion": 1, "protocolId": PROTOCOL, "mode": "engineering-fixed-fixture",
    "status": "frozen", "fixtureId": "round50-fixed-2x16x40-v1", "seed": 52000000,
    "repetitions": 100, "referenceReplications": 199, "withinEffect": 2,
    "betweenEffect": 2, "alpha": 0.05, "calls": 1, "wallCapSeconds": 180,
}


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def input_cases():
    """Return all bounded validation cases without starting any native process."""
    base = canonical(REQUEST)
    cases = []

    def add(name, raw, accepted=False, args=None, env=None):
        cases.append((name, raw, accepted, args, env or {}))

    add("canonical", base, True)
    add("max_16KiB", base + b" " * (16384 - len(base)), True)
    add("over_16KiB", base + b" " * (16385 - len(base)))
    add("empty", b"")
    add("malformed", b"{")
    add("array", b"[]")
    add("duplicate", base.replace(b'"alpha":0.05', b'"alpha":0.05,"alpha":0.05'))
    add("escaped_duplicate", base.replace(b'"alpha":0.05', b'"alpha":0.05,"\\u0061lpha":0.05'))
    add("unknown", base.replace(b"{", b'{"observations":[],', 1))
    add("nonfinite", base.replace(b"0.05", b"NaN"))
    add("numeric_overflow", base.replace(b"0.05", b"1e999"))
    add("bad_utf8", base.replace(b"frozen", b"fro\xffzen"))
    add("trailing_json", base + b"{}")
    add("comment", base + b"// comment")
    add("depth", b'{"nested":' + b"[" * 10 + b"0" + b"]" * 10 + b"}")
    for key, value in REQUEST.items():
        changed = dict(REQUEST)
        changed[key] = value + "-changed" if isinstance(value, str) else value + 1
        add("mutate_" + key, canonical(changed))
        missing = dict(REQUEST)
        del missing[key]
        add("missing_" + key, canonical(missing))
    for key in ("schemaVersion", "seed", "alpha"):
        changed = dict(REQUEST)
        changed[key] = True
        add("boolean_" + key, canonical(changed))
    add("wrong_sha", base, args=["validate-only", "FILE", "0" * 64])
    add("uppercase_sha", base, args=["validate-only", "FILE", sha(base).upper()])
    add("unknown_cli_mode", base, args=["study", "FILE", "HASH"])
    add("missing_args", base, args=["validate-only"])
    add("identity_extra_args", base, args=["identity", "FILE", "HASH"])
    add("missing_backup_env", base, env={"MVS_DISABLE_BACKUPS": None})
    add("wrong_backup_env", base, env={"MVS_DISABLE_BACKUPS": "0"})
    add("missing_cpu_env", base, env={"DOTNET_PROCESSOR_COUNT": None})
    add("two_cpu_env", base, env={"DOTNET_PROCESSOR_COUNT": "2"})
    # This is the only engineering-mode command admitted by this test suite.
    # It is statically guarded below against the exact frozen request hash.
    add("engineering_noncanonical", base + b" ", args=["engineering", "FILE", "HASH"])
    return cases


class NativeRequestContractTests(unittest.TestCase):
    def test_request_matches_frozen_probe_and_hash(self):
        probe = json.loads((ROOT / "validation/prospective-cost-probe-v1.json").read_bytes())
        self.assertEqual(probe["request"], REQUEST)
        self.assertEqual(sha(canonical(REQUEST)), REQUEST_SHA)
        self.assertEqual(probe["request_canonical_sha256"], REQUEST_SHA)
        self.assertIn(REQUEST_SHA, (ROOT / "validation/prospective_adapter/Program.cs").read_text())

    def test_case_generator_cannot_launch_valid_engineering(self):
        cases = input_cases()
        self.assertEqual(len(cases), 54)
        self.assertEqual(len({row[0] for row in cases}), 54)
        engineering = [row for row in cases if row[3] and row[3][0] == "engineering"]
        self.assertEqual(len(engineering), 1)
        for _, raw, accepted, _, _ in engineering:
            self.assertFalse(accepted)
            self.assertNotEqual(sha(raw), REQUEST_SHA)


@unittest.skipUnless(os.environ.get("MVS_PROSPECTIVE_NATIVE"), "Set MVS_PROSPECTIVE_NATIVE for zero-compute native checks")
class NativeZeroComputeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dll = Path(os.environ["MVS_PROSPECTIVE_NATIVE"]).resolve(strict=True)
        cls.dotnet = os.environ.get("DOTNET") or shutil.which("dotnet")
        if not cls.dotnet:
            raise RuntimeError("Explicit native testing requires DOTNET or dotnet on PATH")
        evidence = os.environ.get("MVS_PROSPECTIVE_NATIVE_EVIDENCE")
        cls.temp = None
        if evidence:
            cls.evidence = Path(evidence).resolve()
            cls.evidence.mkdir(parents=True, exist_ok=False)
        else:
            cls.temp = tempfile.TemporaryDirectory(prefix="mvs-prospective-zero-compute-")
            cls.evidence = Path(cls.temp.name)
        cls.env = dict(os.environ, MVS_DISABLE_BACKUPS="1", DOTNET_PROCESSOR_COUNT="1")

    @classmethod
    def tearDownClass(cls):
        if cls.temp is not None:
            cls.temp.cleanup()

    def invoke(self, name, args, raw=None, overrides=None):
        if raw is not None:
            path = self.evidence / (name + ".request")
            path.write_bytes(raw)
            args = [str(path) if arg == "FILE" else sha(raw) if arg == "HASH" else arg for arg in args]
        # Fail before Popen if a future test edit accidentally admits real computation.
        if args and args[0] == "engineering":
            self.assertIsNotNone(raw)
            self.assertNotEqual(sha(raw), REQUEST_SHA)
            self.assertEqual(args[-1], sha(raw))
        env = dict(self.env)
        for key, value in (overrides or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        result = subprocess.run([self.dotnet, str(self.dll), *args], env=env, capture_output=True, timeout=8)
        (self.evidence / (name + ".stdout.jsonl")).write_bytes(result.stdout)
        (self.evidence / (name + ".stderr.jsonl")).write_bytes(result.stderr)
        return result

    def assert_envelope(self, row):
        self.assertEqual(row["schema"], SCHEMA)
        self.assertEqual(row["protocolId"], PROTOCOL)
        self.assertEqual(row["operationCounts"], ZERO_COUNTS)
        self.assertEqual(row["operationCountScope"], COUNT_SCOPE)

    def test_identity_is_zero_compute_and_binds_sources(self):
        result = self.invoke("identity", ["identity"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result.stderr)
        row = json.loads(result.stdout)
        self.assert_envelope(row)
        self.assertEqual(row["kind"], "identity")
        self.assertEqual(row["frozenEngineeringRequestSha256"], REQUEST_SHA)
        self.assertEqual(row["adapterScope"], "test_only_fixed_fixture_no_general_study_execution")
        sources = row["identity"]["sourceSha256"]
        self.assertEqual(len(sources), 14)
        self.assertEqual(len(row["adapterSourceSha256"]), 2)
        for path, digest in {**sources, **row["adapterSourceSha256"]}.items():
            self.assertEqual(sha((ROOT / path).read_bytes()), digest, path)
        self.assertEqual(sha(self.dll.read_bytes()), row["identity"]["harnessAssembly"]["sha256"])
        self.assertEqual(sha(self.dll.with_name("MvsAnalyzer.Core.dll").read_bytes()), row["identity"]["coreAssembly"]["sha256"])

    def test_all_validation_cases_fail_closed_without_compute(self):
        report = []
        for name, raw, accepted, args, overrides in input_cases():
            with self.subTest(case=name):
                result = self.invoke(name, args or ["validate-only", "FILE", "HASH"], raw, overrides)
                self.assertEqual(result.returncode, 0 if accepted else 2, (name, result.stderr))
                row = json.loads(result.stdout if accepted else result.stderr)
                self.assert_envelope(row)
                self.assertFalse(row["completed"])
                if accepted:
                    self.assertFalse(result.stderr)
                    self.assertEqual(row["kind"], "request_validated")
                    self.assertFalse(row["computationInvoked"])
                else:
                    self.assertFalse(result.stdout)
                    self.assertEqual(row["kind"], "adapter_error")
                    self.assertEqual(row["status"], "technical_failure")
                    self.assertFalse(row["partialNativeWork"])
                    self.assertEqual(set(row["exception"]), {"type", "message", "stack", "inner"})
                    self.assertTrue(row["exception"]["type"])
                    self.assertTrue(row["exception"]["stack"])
                if name == "engineering_noncanonical":
                    self.assertEqual(row["exception"]["message"], "Engineering mode requires the exact pinned request bytes.")
                report.append({"case": name, "exitCode": result.returncode, "operationCounts": row["operationCounts"], "completed": False})
        (self.evidence / "cases.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
