#!/usr/bin/env python3
"""Check the frozen CLI v1 surface and, optionally, smoke-run artifacts.

This checker does not compile or execute C#. It prevents accidental drift in the
public command surface and verifies deterministic identity fields in artifacts
that CI already produces with fixed inputs and seeds.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "cli-contract-v1.json"
PROGRAM = ROOT / "MvsAnalyzer.Cli" / "Program.cs"
README = ROOT / "README.md"
DOCS_README = ROOT / "docs" / "README.md"


def load_json(path: pathlib.Path):
    def invalid(value: str):
        raise ValueError(f"Nonstandard JSON literal in {path}: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def fail(message: str) -> None:
    raise AssertionError(message)


def check_static(contract: dict) -> None:
    assert contract["schemaVersion"] == 1
    assert contract["contractId"] == "mvs-cli-v1"
    machine = contract["machineResultSchema"]
    assert machine["id"] == "mvs-cli-result/v1"
    assert machine["statusByExitCode"] == {"0": "completed", "1": "error", "2": "diagnostic"}
    assert set(contract["exitCodes"]) == {"0", "1", "2"}

    expected_commands = {
        "calibrate", "analyze", "variance", "estimation", "melsm",
        "benchmark", "resume", "state-check", "version", "env",
    }
    commands = contract["commands"]
    assert set(commands) == expected_commands, "CLI command registry changed; update the contract deliberately"

    program = PROGRAM.read_text(encoding="utf-8")
    for name, spec in commands.items():
        if name not in program and name not in {"benchmark"}:
            fail(f"Command {name!r} is no longer visible in Program.cs")
        source_path = ROOT / spec["source"]
        assert source_path.is_file(), source_path
        source = source_path.read_text(encoding="utf-8")

        for alias in spec.get("aliases", []):
            assert alias in program, f"Alias {alias!r} disappeared from command dispatch"
        for flag in spec.get("required", []) + spec.get("allowed", []) + spec.get("forbiddenAfterCalibration", []):
            if flag not in source and flag not in program:
                fail(f"Flag {flag!r} for {name} is no longer visible in its implementation")
        for group in spec.get("requiredAnyOf", []):
            assert group and all(flag.startswith("-") for flag in group)
        for code in spec["exitCodes"]:
            assert code in (0, 1, 2)
        for artifact in spec.get("artifacts", []):
            assert artifact["policy"] in {"exact", "numeric", "mixed", "operational"}
            artifact_name = artifact["name"]
            if artifact_name not in source:
                extra_sources = [ROOT / "Infrastructure" / "OutputExporter.cs", ROOT / "Infrastructure" / "CalibrationPersistence.cs", ROOT / "Benchmark" / "BenchmarkReport.cs"]
                if not any(path.is_file() and artifact_name in path.read_text(encoding="utf-8") for path in extra_sources):
                    fail(f"Artifact {artifact_name!r} for {name} is no longer emitted by the recorded sources")

    usage_match = re.search(r"Exit codes:\s*0 completed, 1 input/runtime error or cancellation, 2 a numerical diagnostic", program)
    assert usage_match, "Human CLI help no longer documents the frozen exit-code meanings"

    for case in contract["canonicalCases"]:
        assert case["command"] in commands
        expected_exit = case["expectedExit"]
        values = expected_exit if isinstance(expected_exit, list) else [expected_exit]
        assert all(value in commands[case["command"]]["exitCodes"] for value in values)
        if case.get("input"):
            assert (ROOT / case["input"]).is_file(), f"Missing canonical input: {case['input']}"
        if case.get("dependsOn"):
            ids = {item["id"] for item in contract["canonicalCases"]}
            assert case["dependsOn"] in ids

    for path in (README, DOCS_README):
        text = path.read_text(encoding="utf-8")
        assert "CLI_PYTHON_ROADMAP.md" not in text, f"Temporary roadmap must not be linked from {path.relative_to(ROOT)}"


def find_analysis_folder(root: pathlib.Path) -> pathlib.Path:
    manifests = [p for p in (root / "analysis").rglob("run_manifest.json") if p.is_file()]
    assert manifests, "No analysis run_manifest.json found under artifacts/analysis"
    manifests.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
    return manifests[0].parent


def check_artifacts(contract: dict, artifacts: pathlib.Path) -> None:
    calibration = artifacts / "calibration"
    state_path = calibration / "calibration_state.json"
    assert state_path.is_file(), state_path
    state = load_json(state_path)

    identity = next(case for case in contract["canonicalCases"] if case["id"] == "calibrate-demo-three-groups")["scientificIdentity"]
    assert state["SchemaVersion"] == contract["stateSchemaVersion"]
    assert state["AppVersion"] == contract["applicationVersion"]
    assert state["EngineVersion"] == contract["engineVersion"]
    assert state["Dataset"] == identity["dataset"]
    assert state["Seed"] == identity["seed"]
    assert state["Repetitions"] == identity["repetitions"]
    assert len(state["Rows"]) == identity["metricCount"]
    assert len(state["DatasetHash"]) == 64
    assert len(state["SettingsHash"]) == 64
    assert len(state["FormulaHash"]) == 64
    assert len(state["PayloadHash"]) == 64

    for artifact in contract["commands"]["calibrate"]["artifacts"]:
        assert (calibration / artifact["name"]).is_file(), f"Missing calibration artifact {artifact['name']}"

    analysis = find_analysis_folder(artifacts)
    for artifact in contract["commands"]["analyze"]["artifacts"]:
        assert (analysis / artifact["name"]).is_file(), f"Missing analysis artifact {artifact['name']}"

    manifest = load_json(analysis / "run_manifest.json")
    results = load_json(analysis / "results.json")
    analyze_identity = next(case for case in contract["canonicalCases"] if case["id"] == "analyze-demo-three-groups")["scientificIdentity"]
    assert manifest["schemaVersion"] == contract["manifestSchemaVersion"]
    assert manifest["version"] == contract["applicationVersion"]
    assert manifest["engineVersion"] == contract["engineVersion"]
    assert manifest["inputData"]["sha256"] == state["DatasetHash"]
    assert manifest["calibration"]["seed"] == state["Seed"]
    assert manifest["calibration"]["repetitions"] == state["Repetitions"]
    assert manifest["decision"]["familySize"] == analyze_identity["familySize"]
    assert results["schemaVersion"] == contract["resultSchemaVersion"]
    assert len(results["rows"]) == analyze_identity["metricCount"]

    copied_state = (analysis / "calibration_state.json").read_bytes()
    assert copied_state == state_path.read_bytes(), "Analysis must preserve the exact calibration state bytes"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=pathlib.Path, help="Optional CI artifacts root containing calibration/ and analysis/")
    args = parser.parse_args()

    contract = load_json(CONTRACT)
    check_static(contract)
    if args.artifacts is not None:
        check_artifacts(contract, args.artifacts.resolve())
        print("CLI contract and canonical calibrate/analyze artifacts are consistent")
    else:
        print("CLI contract is internally consistent with the current source tree")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, ValueError) as error:
        print(f"CLI contract check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
