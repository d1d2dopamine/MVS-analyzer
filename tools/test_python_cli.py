#!/usr/bin/env python3
"""Cross-interface smoke test: use the Python API against a real built MVS CLI."""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

import mvs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", required=True, type=pathlib.Path)
    parser.add_argument("--artifacts", required=True, type=pathlib.Path)
    args = parser.parse_args()

    engine = mvs.Engine(args.cli.resolve())
    calibration_dir = args.artifacts / "calibration"
    state_path = calibration_dir / "calibration_state.json"
    if not state_path.is_file():
        raise AssertionError(f"Missing CLI calibration fixture: {state_path}")

    out = args.artifacts / "python-analysis"
    if out.exists():
        shutil.rmtree(out)
    result = engine.analyze(
        ROOT / "examples" / "demo_three_groups.csv",
        calibration=calibration_dir,
        output=out,
    )
    manifest = result.manifest
    if manifest is None:
        raise AssertionError("Python analysis did not expose run_manifest.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if result.engine_version != state["EngineVersion"]:
        raise AssertionError("Python result and calibration use different engine versions")
    if manifest.data["inputData"]["sha256"] != state["DatasetHash"]:
        raise AssertionError("Python wrapper changed the scientific input identity")
    if len(result.read_csv("results.csv")) != len(state["Rows"]):
        raise AssertionError("Python/CLI result registry size differs from calibration")
    print("Python/CLI parity smoke passed:", result.output_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
