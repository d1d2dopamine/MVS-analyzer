#!/usr/bin/env python3
"""Independent real-Windows native/workflow/official-MCP acceptance driver.

Example (PowerShell, after building CLI and canonical 150-repetition calibration):
  $env:MVS_TEST_CLI='C:\\mvs\\cli\\mvs.exe'
  $env:MVS_TEST_CALIBRATION='C:\\mvs\\calibration\\calibration_state.json'
  python tools/test_windows_workflow.py --artifacts C:\\mvs\\acceptance
CLI/calibration may instead be given with --cli/--calibration. Artifacts must not
exist. Use short local NTFS paths (<248 characters), never a personal workspace.
Runs are finite and synthetic; parity does not establish scientific validity.
On Linux this driver emits an explicit skip and does not claim Windows evidence.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python/src"), str(ROOT / "tools")]
from test_python_cli import compare_analysis


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def readiness(value):
    assert value["scientificReadiness"]["status"] == "no_go", value


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cli", type=Path, default=os.environ.get("MVS_TEST_CLI"))
    parser.add_argument("--calibration", type=Path, default=os.environ.get("MVS_TEST_CALIBRATION"))
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        print(json.dumps({"status": "skipped", "reason": "Requires actual Windows Win32/NTFS runtime", "windowsRuntimeValidated": False}))
        return
    if args.cli is None or args.calibration is None:
        parser.error("--cli/MVS_TEST_CLI and --calibration/MVS_TEST_CALIBRATION are required on Windows")
    cli, calibration = args.cli.resolve(strict=True), args.calibration.resolve(strict=True)
    root = args.artifacts.absolute(); root.mkdir(parents=True, exist_ok=False)
    inputs = root / "in"; inputs.mkdir()
    work = root / "w"
    shutil.copyfile(ROOT / "examples/demo_three_groups.csv", inputs / "input.csv")
    shutil.copyfile(calibration, inputs / "state.json")
    original = {p.name: sha(p) for p in inputs.iterdir()}
    direct_data = root / "direct-data"; direct_data.mkdir()
    poison = root / "inherited-data"; poison.mkdir()
    sentinel = poison / "sentinel"; sentinel.write_bytes(b"must not change")
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "python/src"), DOTNET_PROCESSOR_COUNT="2",
                       DOTNET_EnableDiagnostics="0", MVS_DISABLE_BACKUPS="1", MVS_BACKUP_DIR=str(root / "backups"),
                       MVS_APPDATA_ROOT=str(direct_data), LOCALAPPDATA=str(poison), APPDATA=str(poison))
    calls = []

    def invoke(label, command, request=None, expected=0, extra_env=None):
        result = subprocess.run(command, input=None if request is None else json.dumps(request),
                                capture_output=True, text=True, encoding="utf-8", cwd=root,
                                env=environment | (extra_env or {}), timeout=180)
        (root / (label + ".stdout.json")).write_text(result.stdout, encoding="utf-8")
        (root / (label + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
        calls.append({"label": label, "exit": result.returncode})
        assert result.returncode == expected, (label, result.returncode, result.stderr, result.stdout)
        value = json.loads(result.stdout); readiness(value)
        return value

    version = invoke("version", [str(cli), "version", "--json", "--quiet"])
    assert version["localAppDataOverride"] == "MVS_APPDATA_ROOT/v1"
    native = invoke("native", [str(cli), "analyze", "--in", str(inputs / "input.csv"), "--calibration", str(inputs / "state.json"), "--out", str(root / "native"), "--json", "--quiet"])
    assert native["execution"]["completed"] is True
    assert (direct_data / "MVS_Analyzer" / "run_journal.jsonl").is_file(), "Native appdata override was not exercised"
    direct_before = {str(p.relative_to(direct_data)): sha(p) for p in direct_data.rglob("*") if p.is_file()}
    base = [sys.executable, "-m", "mvs.workflow_cli", "--engine", str(cli), "--read-root", str(inputs), "--work-root", str(work), "--timeout-seconds", "120"]
    source = {"data": "input.csv", "calibration": "state.json"}
    registration = invoke("register", base + ["register_protocol"], source | {"protocol_id": "protocol1", "prior_exposure": "previously_inspected", "question": "Synthetic Windows runtime parity"})
    assert registration["execution"]["status"] == "completed"
    exploratory = invoke("exploratory", base + ["run_analysis"], source | {"run_id": "exploratory"})
    frozen_args = source | {"run_id": "frozen", "mode": "frozen", "protocol_id": "protocol1"}
    frozen = invoke("frozen", base + ["run_analysis"], frozen_args)

    def check_run(value):
        readiness(value)
        assert value["execution"]["status"] == "completed", value
        assert not value["data"]["confirmatoryCertified"]
        compare_analysis(Path(native["outputDirectory"]), work / value["data"]["native"]["outputDirectory"], 1e-12, 1e-10)

    check_run(exploratory); check_run(frozen)
    assert invoke("replay", base + ["run_analysis"], frozen_args) == frozen
    conflict = invoke("conflict", base + ["register_protocol"], source | {"protocol_id": "protocol1", "prior_exposure": "unknown", "question": "Do not overwrite"}, expected=1)
    assert conflict["error"]["code"] == "protocol_conflict"
    original_state = (inputs / "state.json").read_bytes()
    try:
        (inputs / "state.json").write_bytes(original_state + b"\n")
        deviation = invoke("deviation", base + ["run_analysis"], frozen_args | {"run_id": "deviation"}, expected=1)
        assert deviation["error"]["code"] == "protocol_deviation"
    finally:
        (inputs / "state.json").write_bytes(original_state)

    async def wire():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        config = StdioServerParameters(command=sys.executable, args=["-m", "mvs.mcp_server", "--engine", str(cli), "--read-root", str(inputs), "--work-root", str(work), "--timeout-seconds", "120"], env=environment)
        with (root / "mcp.stderr.txt").open("w", encoding="utf-8") as err:
            async with stdio_client(config, errlog=err) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    response = await session.call_tool("get_run", {"run_id": "frozen"})
                    assert not response.isError and response.structuredContent == frozen
                    response = await session.call_tool("run_analysis", frozen_args | {"run_id": "mcp-frozen"})
                    assert not response.isError, response
                    check_run(response.structuredContent)
                    (root / "mcp-frozen.json").write_text(json.dumps(response.structuredContent, indent=2), encoding="utf-8")
                    return {"protocolVersion": initialized.protocolVersion, "cliReplayExact": True, "freshRunParity": True}

    async def bounded_wire():
        return await asyncio.wait_for(wire(), timeout=180)

    mcp = asyncio.run(bounded_wire())
    assert all(sha(inputs / name) == value for name, value in original.items())
    assert list(poison.iterdir()) == [sentinel] and sentinel.read_bytes() == b"must not change"
    assert {str(p.relative_to(direct_data)): sha(p) for p in direct_data.rglob("*") if p.is_file()} == direct_before, "Workflow inherited caller's appdata destination"
    # Every workflow journal must be inside its owned staging run's data directory.
    journals = list(work.rglob("run_journal.jsonl"))
    assert journals, "Workflow native appdata/journal override was not exercised"
    assert all("data" in p.relative_to(work).parts for p in journals)
    result = {"status": "passed", "platform": sys.platform, "windowsRuntimeValidated": True,
              "scientificReadiness": "NO-GO retained", "calls": calls, "mcp": mcp,
              "appdataIsolation": True, "immutableReplay": True, "frozenDeviationRejected": True,
              "artifactFileCount": sum(p.is_file() for p in root.rglob("*")),
              "limits": ["Synthetic same-engine parity, not independent scientific validation.",
                         "Windows Server CI is not evidence of a Windows 11 desktop run."]}
    (root / "acceptance-results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
