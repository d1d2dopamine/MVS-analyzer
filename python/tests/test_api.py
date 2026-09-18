from __future__ import annotations

import json
import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path

from mvs.engine import Engine, EngineCompatibilityError, InputError, ScientificDiagnostic
from mvs.models import Calibration


FAKE_CLI = r'''#!/usr/bin/env python3
import hashlib, json, os, pathlib, sys
args = sys.argv[1:]
command = args[0] if args else ""

def value(name):
    if name in args:
        i = args.index(name)
        return args[i+1] if i+1 < len(args) else None
    for token in args:
        if token.startswith(name + "="):
            return token.split("=", 1)[1]
    return None

def emit(code=0, status="completed", out=None, error=None, diagnostics=None):
    artifacts=[]
    manifest=None
    run_id=None
    if out:
        p=pathlib.Path(out)
        p.mkdir(parents=True, exist_ok=True)
        for f in sorted(p.iterdir()):
            if f.is_file():
                artifacts.append({"name": f.name, "path": str(f.resolve()), "sizeBytes": f.stat().st_size,
                                  "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
        for name in ("run_manifest.json", "benchmark_manifest.json"):
            q=p/name
            if q.exists():
                manifest=str(q.resolve())
                run_id=json.loads(q.read_text()).get("runId")
                break
    payload={"schemaVersion":"mvs-cli-result/v1","status":status,"command":command,"exitCode":code,
             "runId":run_id,"outputDirectory":str(pathlib.Path(out).resolve()) if out else None,
             "appVersion":"1.4.0","applicationVersion":"1.4.0","engineVersion":"1.6.0",
             "stateSchema":2,"cliProtocol":{"name":"mvs-cli","major":1,"capabilities":["json-result-v1"]},
             "formulaVersion":"test","formulaHash":"0"*64,"manifestPath":manifest,
             "artifacts":artifacts,"diagnostics":diagnostics or [],"error":error}
    print(json.dumps(payload))
    sys.exit(code)

if command == "version":
    emit()
if command == "calibrate":
    out=value("--out")
    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
    pathlib.Path(out,"calibration_state.json").write_text("{}")
    pathlib.Path(out,"calibration.csv").write_text("metric,power\nmean,0.8\n")
    emit(out=out)
if command == "analyze":
    out=pathlib.Path(value("--out"))/"run-1"
    out.mkdir(parents=True, exist_ok=True)
    (out/"run_manifest.json").write_text(json.dumps({"runId":"run-1","engineVersion":"1.6.0"}))
    (out/"results.csv").write_text("metric,verdict\nmean,candidate\n")
    emit(out=str(out))
if command == "variance":
    out=value("--out")
    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
    pathlib.Path(out,"variance_report.json").write_text("{}")
    emit(2,"diagnostic",out,diagnostics=[{"level":"warning","code":"scientific_diagnostic","message":"inspect report"}])
if command == "melsm" and value("--in") == "bad.csv":
    emit(1,"error",error={"type":"InvalidDataException","message":"bad input"})
emit()
'''


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.cli = root / "mvs-fake"
        self.cli.write_text(FAKE_CLI, encoding="utf-8")
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IEXEC)
        self.data = root / "data.csv"
        self.data.write_text("entity,group,value\na,A,1\n", encoding="utf-8")
        self.engine = Engine(self.cli)

    def tearDown(self):
        self.temp.cleanup()

    def test_calibrate_and_analyze_return_typed_results(self):
        calibration = self.engine.calibrate(self.data, output=Path(self.temp.name)/"cal", repetitions=100)
        self.assertIsInstance(calibration, Calibration)
        self.assertEqual(calibration.state_path.name, "calibration_state.json")
        analysis = self.engine.analyze(self.data, calibration=calibration, output=Path(self.temp.name)/"analysis")
        self.assertEqual(analysis.run_id, "run-1")
        self.assertEqual(analysis.read_csv("results.csv")[0]["verdict"], "candidate")
        self.assertEqual(analysis.manifest.data["engineVersion"], "1.6.0")
        analysis.verify_artifacts()

    def test_diagnostic_can_be_returned_or_raised(self):
        result = self.engine.variance(self.data, output=Path(self.temp.name)/"variance")
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.diagnostics[0].code, "scientific_diagnostic")
        with self.assertRaises(ScientificDiagnostic):
            self.engine.variance(self.data, output=Path(self.temp.name)/"variance2", allow_diagnostic=False)

    def test_incompatible_machine_schema_is_rejected(self):
        bad = Path(self.temp.name) / "mvs-bad-schema"
        bad.write_text(FAKE_CLI.replace("mvs-cli-result/v1", "mvs-cli-result/v99"), encoding="utf-8")
        bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
        with self.assertRaises(EngineCompatibilityError):
            Engine(bad)

    def test_input_errors_are_typed(self):
        with self.assertRaises(InputError):
            self.engine.melsm("bad.csv", output=Path(self.temp.name)/"melsm")


if __name__ == "__main__":
    unittest.main()
