#!/usr/bin/env python3
"""Cross-interface smoke test: use the Python API against a real built MVS CLI."""
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

import mvs  # noqa: E402


CSV_NUMERIC = {
    "range", "global_p", "effect_cliffs_delta", "effect_low", "effect_high", "equivalence_p",
    "mde", "calibrated_fpr", "calibrated_power", "robustness", "repeatability", "coverage",
    "mvs_score", "adjusted_p", "equivalence_low", "equivalence_high",
}
CSV_VECTORS = {"track_powers", "track_scores", "track_mdes"}


def strict_json(path: pathlib.Path):
    def invalid(value):
        raise ValueError(f"Nonstandard JSON literal in {path}: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def compare_value(expected, actual, absolute: float, relative: float, location: str = "$") -> None:
    """Recursive scientific equality: order/null/status/counts exact, floats tolerant."""
    if type(expected) in (int, float) and type(actual) in (int, float):
        if type(expected) is int and type(actual) is int:
            equal = expected == actual
        else:
            equal = (math.isfinite(expected) and math.isfinite(actual)
                     and math.isclose(expected, actual, abs_tol=absolute, rel_tol=relative))
        if not equal:
            raise AssertionError(f"{location}: scientific number differs: {expected!r} != {actual!r}")
    elif isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            raise AssertionError(f"{location}: field set differs")
        for key in expected:
            compare_value(expected[key], actual[key], absolute, relative, f"{location}.{key}")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            raise AssertionError(f"{location}: row/vector length differs")
        for index, (left, right) in enumerate(zip(expected, actual)):
            compare_value(left, right, absolute, relative, f"{location}[{index}]")
    elif type(expected) is not type(actual) or expected != actual:
        raise AssertionError(f"{location}: status/identity/unavailability differs: {expected!r} != {actual!r}")


def scientific_manifest(manifest: dict) -> dict:
    # These root fields describe the individual execution, not its scientific result.
    return {key: value for key, value in manifest.items() if key not in {"created", "runId", "files"}}


def read_results_csv(path: pathlib.Path) -> tuple[list[str], list[dict]]:
    def number(value):
        if value == "":
            return None
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"Nonfinite CSV number in {path}: {value}")
        return result
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        if not fields or len(set(fields)) != len(fields):
            raise ValueError(f"Missing/duplicate CSV columns: {path}")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV row: {path}")
            rows.append({key: number(value) if key in CSV_NUMERIC else
                         [number(x) for x in value.split('|')] if key in CSV_VECTORS else value
                         for key, value in row.items()})
    if not rows:
        raise ValueError(f"Empty results CSV: {path}")
    return fields, rows


def compare_analysis(expected: pathlib.Path, actual: pathlib.Path, absolute: float, relative: float) -> None:
    for name in ["results.json", "run_manifest.json"]:
        left, right = strict_json(expected / name), strict_json(actual / name)
        if name == "run_manifest.json":
            left, right = scientific_manifest(left), scientific_manifest(right)
        compare_value(left, right, absolute, relative, name)
    left_fields, left_rows = read_results_csv(expected / "results.csv")
    right_fields, right_rows = read_results_csv(actual / "results.csv")
    if left_fields != right_fields:
        raise AssertionError("results.csv: column order differs")
    compare_value(left_rows, right_rows, absolute, relative, "results.csv")
    # These diagnostics contain counts and categorical reasons only: compare exactly.
    left_fields, left_rows = read_results_csv(expected / "metric_availability.csv")
    right_fields, right_rows = read_results_csv(actual / "metric_availability.csv")
    if left_fields != right_fields:
        raise AssertionError("metric_availability.csv: column order differs")
    compare_value(left_rows, right_rows, 0, 0, "metric_availability.csv")
    if (expected / "calibration_state.json").read_bytes() != (actual / "calibration_state.json").read_bytes():
        raise AssertionError("CLI/Python calibration state bytes differ")


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
        raise FileExistsError(f"Parity output already exists; retain it and choose a fresh artifacts directory: {out}")
    manifests = list((args.artifacts / "analysis").rglob("run_manifest.json"))
    if len(manifests) != 1:
        raise AssertionError("Expected exactly one canonical CLI analysis; use a fresh artifacts directory")
    result = engine.analyze(
        ROOT / "examples" / "demo_three_groups.csv",
        calibration=calibration_dir,
        output=out,
    )
    manifest = result.manifest
    if manifest is None:
        raise AssertionError("Python analysis did not expose run_manifest.json")
    state = strict_json(state_path)
    if result.engine_version != state["EngineVersion"]:
        raise AssertionError("Python result and calibration use different engine versions")
    if manifest.data["inputData"]["sha256"] != state["DatasetHash"]:
        raise AssertionError("Python wrapper changed the scientific input identity")
    if len(result.read_csv("results.csv")) != len(state["Rows"]):
        raise AssertionError("Python/CLI result registry size differs from calibration")
    result.verify_artifacts()
    tolerance = strict_json(ROOT / "validation" / "cli-contract-v1.json")["numericTolerance"]
    compare_analysis(manifests[0].parent, result.output_directory,
                     tolerance["sameEnvironmentAbsolute"], tolerance["relative"])
    print("Python/CLI scientific parity passed: all result rows, CSV, scientific manifest and state:", result.output_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
