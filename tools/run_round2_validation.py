#!/usr/bin/env python3
"""Reproduce round 2 checks with logs; exit 2 if native verification is unavailable."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


class ValidationRun:
    def __init__(self, output: Path):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.checks: list[dict] = []

    def run(self, name: str, command: list[str], expected: tuple[int, ...] = (0,)) -> bool:
        log = self.output / f"{len(self.checks) + 1:02}-{name}.log"
        print(f"Running {name}", flush=True)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "python/src"), MVS_DISABLE_BACKUPS="1")
        try:
            with log.open("w", encoding="utf-8") as output:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, check=False)
            passed = result.returncode in expected
            self.checks.append({"name": name, "status": "passed" if passed else "failed",
                                "command": command, "exitCode": result.returncode, "expectedExit": list(expected), "log": log.name})
        except OSError as error:
            passed = False
            self.checks.append({"name": name, "status": "failed", "command": command, "reason": str(error), "log": log.name})
        print(f"  {'PASS' if passed else 'FAIL'} {name}", flush=True)
        return passed

    def skip_native(self, reason: str) -> None:
        recorded = {check["name"] for check in self.checks}
        for name in ["native-core-tests", "cli-build", "real-calibration", "real-analysis", "real-output-integrity",
                     "real-cli-contract", "cli-python-numerical-parity", "real-export-score-check", "invalid-numeric-rejected"]:
            if name not in recorded:
                self.checks.append({"name": name, "status": "not_run", "reason": reason})

    def finish(self) -> int:
        failed = any(check["status"] == "failed" for check in self.checks)
        incomplete = any(check["status"] == "not_run" for check in self.checks)
        code = 1 if failed else 2 if incomplete else 0
        report = {"schema": "mvs-round2-verification/v1", "status": "failed" if failed else "incomplete" if incomplete else "passed",
                  "exitCode": code, "created": datetime.now(timezone.utc).isoformat(), "checks": self.checks,
                  "scope": "Software/numerical checks, not independent scientific certification or a compiled release."}
        path = self.output / "verification.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Round 2 {report['status']}; report: {path}", flush=True)
        return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New output directory; refuses existing directories")
    parser.add_argument("--python-only", action="store_true", help="Run independent/static checks only; always incomplete (exit 2)")
    parser.add_argument("--dotnet", default="dotnet", help=".NET 8 SDK executable name/path")
    args = parser.parse_args(argv)
    output = args.output or ROOT / "artifacts" / ("round2-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    run = ValidationRun(output)
    py = sys.executable
    commands = [
        ("independent-regressions", [py, "-m", "unittest", "discover", "-s", "validation", "-p", "test_*.py", "-v"]),
        ("rank-fixture-reference", [py, "validation/rank_test_reference.py", "--check"]),
        ("python-wrapper", [py, "-m", "unittest", "discover", "-s", "python/tests", "-v"]),
        ("parity-runner-regressions", [py, "tools/test_round2.py"]),
        ("backups", [py, "tools/test_backups.py"]),
        ("source-regressions", [py, "tools/test_source.py"]),
        ("source-contracts", [py, "tools/check_source.py"]),
        ("cli-contract", [py, "tools/check_cli_contract.py"]),
        ("csharp-structure-only", [py, "tools/check_csharp_structure.py"]),
        ("notebook-consistency", [py, "tools/build_notebooks.py", "--check"]),
        ("independent-identities", [py, "validation/reference_numerics.py"]),
    ]
    passed = True
    for name, command in commands:
        passed = run.run(name, command) and passed
    dotnet = shutil.which(args.dotnet)
    if not passed or args.python_only or dotnet is None:
        reason = "Independent/static prerequisite failed" if not passed else "Requested Python-only run" if args.python_only else ".NET SDK executable unavailable"
        run.skip_native(reason)
        return run.finish()
    publish = run.output / "cli"
    artifacts = run.output / "artifacts"
    native = [
        ("native-core-tests", [dotnet, "run", "--project", "MvsAnalyzer.Core.Tests/MvsAnalyzer.Core.Tests.csproj", "-c", "Release"]),
        ("cli-build", [dotnet, "publish", "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj", "-c", "Release", "-o", str(publish)]),
        ("real-calibration", [dotnet, str(publish / "mvs.dll"), "calibrate", "--in", "examples/demo_three_groups.csv", "--out", str(artifacts / "calibration"), "--repetitions", "150", "--seed", "20260719"]),
        ("real-analysis", [dotnet, str(publish / "mvs.dll"), "analyze", "--in", "examples/demo_three_groups.csv", "--calibration", str(artifacts / "calibration"), "--out", str(artifacts / "analysis")]),
        ("real-output-integrity", [py, "tools/check_outputs.py", str(artifacts)]),
        ("real-cli-contract", [py, "tools/check_cli_contract.py", "--artifacts", str(artifacts)]),
    ]
    for name, command in native:
        if not run.run(name, command):
            run.skip_native(f"Native prerequisite {name} failed; dependent checks not run")
            return run.finish()
    # The Python Engine accepts an executable, not a 'dotnet DLL' command list.
    # Framework-dependent publish emits a native apphost; use that exact apphost.
    cli = publish / ("mvs.exe" if os.name == "nt" else "mvs")
    if not run.run("cli-python-numerical-parity", [py, "tools/test_python_cli.py", "--cli", str(cli), "--artifacts", str(artifacts)]):
        run.checks.append({"name": "real-export-score-check", "status": "not_run", "reason": "CLI/Python parity failed"})
        return run.finish()
    exports = sorted(artifacts.rglob("results.csv"))
    if not exports:
        run.checks.append({"name": "real-export-score-check", "status": "failed", "reason": "No real CLI exports found"})
    for index, path in enumerate(exports):
        run.run(f"real-export-score-{index + 1}", [py, "validation/analyze_results.py", str(path), "--draws", "20"])
    # Invalid explicit numeric arguments must fail, rather than silently default.
    run.run("invalid-numeric-rejected", [dotnet, str(publish / "mvs.dll"), "calibrate", "--in", "examples/demo_three_groups.csv", "--out", str(artifacts / "invalid"), "--repetitions", "not-a-number"], expected=(1,))
    return run.finish()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Round 2 preflight failed: {error}", file=sys.stderr)
        raise SystemExit(1)
