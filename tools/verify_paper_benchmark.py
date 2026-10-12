#!/usr/bin/env python3
"""Verify historical paper evidence, not scientific success or source authenticity.

The default target remains engine 1.6.0. --check-source is a fail-fast, static
identity preflight; it does not prove that a revision reproduces the old run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath

EXPECTED = {
    "protocolVersion": "MVS-BENCH-1.2.0",
    "protocolHash": "b81be4a1a86e8ba4b013eb63b75256d16e439fb824e7fa68efae5f28e48de268",
    "profile": "full", "seed": 20260904,
    "appVersion": "1.4.0", "engineVersion": "1.6.0",
    "formulaVersion": "MVS-1.4.0",
    "formulaHash": "10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c",
}
BUDGETS = dict(primary=1000, grid=250, calibration=1000, stability=120, determinism=60)
THRESHOLDS = dict(alpha=.05, cherryPickFprPass=.15, mvsFprPass=.075, mvsFprFail=.1,
                  powerLossPass=.07, powerLossFail=.15, tauPass=.7, tauFail=.4,
                  topOneAgreementPass=.6)
REQUIRED = frozenset("benchmark_choices.csv benchmark_metrics.csv benchmark_protocol.txt "
                     "benchmark_report.md benchmark_stability.csv benchmark_summary.csv "
                     "benchmark_verdicts.csv".split())
PROCEDURES = tuple("cherry_pick bonferroni fixed_median fixed_cv mvs_pilot mvs_strict "
                   "mvs_lenient mvs_registry_corrected".split())
METRICS = tuple("median standard_deviation coefficient_of_variation mad iqr normalized_mad "
                "normalized_iqr mean rms range geometric_mean trimmed_mean_20".split())
HEX = re.compile(r"[0-9a-fA-F]{64}\Z")
# CSV and manifest numerics are independently rounded to six decimal places.
ROUNDING = 1.000001e-6


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def finite(value):
        result = float(value)
        require(math.isfinite(result), f"non-finite JSON number: {value}")
        return result

    def invalid(value):
        raise ValueError(f"invalid JSON constant: {value}")

    result = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                        parse_constant=invalid, parse_float=finite)
    require(type(result) is dict, f"JSON object required: {path.name}")
    return result


def integer(value, label):
    require(type(value) is int and value >= 0, f"nonnegative integer required: {label}")
    return value


def csv_integer(value, label):
    require(type(value) is str and re.fullmatch(r"0|[1-9][0-9]*", value),
            f"invalid CSV integer: {label}")
    return int(value)


def number(value, label):
    require(type(value) in (int, float, str) and value != "", f"number required: {label}")
    result = float(value)
    require(math.isfinite(result), f"finite number required: {label}")
    return result


def exact_fields(actual, expected, label):
    require(type(actual) is dict, f"object required: {label}")
    for key, value in expected.items():
        got = actual.get(key)
        correct_type = type(got) is type(value) if type(value) is not float else type(got) in (int, float)
        require(correct_type and got == value, f"{label}.{key} is {got!r}, expected {value!r}")


def conditions():
    """Frozen synthetic plan from BENCH-1.2.0; do not infer it from an artifact."""
    result = {}

    def add(name, stage, mode="none", effect=1., contamination=0.,
            design="gait_stride_like", shape="heavy_tail", planned=250):
        result[name] = dict(stage=stage, design=design, shape=shape, mode=mode,
                            effect=effect, contamination=contamination, planned=planned)

    add("primary_null", "primary", planned=1000)
    for tag in (100, 102, 105, 110, 120):
        add(f"power_location_{tag}", "power", "location", tag / 100)
    for tag in (102, 105, 110, 120, 130):
        add(f"power_dispersion_{tag}", "power", "dispersion", tag / 100)
    for tag in (2, 5, 10):
        add(f"robust_null_{tag}", "robust", contamination=tag / 100)
    for shape in ("normal", "lognormal"):
        add(f"shape_{shape}_null", "shape", shape=shape)
    add("design_voice_null", "shape", design="voice_jitter_like", shape="lognormal")
    add("design_voice_location_105", "shape", "location", 1.05,
        design="voice_jitter_like", shape="lognormal")
    add("determinism_replay", "determinism", planned=60)
    return result


CONDITIONS = conditions()


def safe_file(folder, name):
    require(type(name) is str and bool(name), "empty/non-string artifact filename")
    parts = name.split("/")
    require(not any(part in ("", ".", "..") for part in parts)
            and not any(c in name for c in "\\:") and not any(ord(c) < 32 for c in name)
            and not PurePosixPath(name).is_absolute(), f"unsafe artifact path: {name!r}")
    path = folder
    for part in parts:
        path = path / part
        require(not path.is_symlink(), f"symlink artifact path: {name}")
    require(path.is_file() and path.resolve().is_relative_to(folder.resolve()),
            f"artifact file is missing or unsafe: {name}")
    return path


def read_csv(folder, name, required):
    with safe_file(folder, name).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        rows = list(reader)
        fields = reader.fieldnames
    require(fields is not None and len(fields) == len(set(fields))
            and set(required) <= set(fields), f"missing/duplicate CSV columns: {name}")
    require(all(None not in row and None not in row.values() for row in rows),
            f"malformed CSV row: {name}")
    return rows


def indexed(rows, keys, label):
    require(type(rows) is list, f"array required: {label}")
    result = {}
    for row in rows:
        require(type(row) is dict and all(type(row.get(k)) is str for k in keys),
                f"missing/string identity required: {label}")
        key = tuple(row[k] for k in keys)
        require(key not in result, f"duplicate {label} row: {key}")
        result[key] = row
    return result


def rate(value, count, denominator, label):
    if denominator == 0:
        require(value == "", f"unavailable rate must be blank: {label}")
    else:
        require(abs(number(value, label) - count / denominator) <= .500001e-6,
                f"rate/count mismatch: {label}")


def check_tables(folder, manifest, records):
    summaries = indexed(read_csv(folder, "benchmark_summary.csv",
        "condition stage design shape mode effect contamination source planned completed failed procedure rejections rate".split()),
        ("condition", "procedure"), "summary")
    require(set(summaries) == {(c, p) for c in CONDITIONS for p in PROCEDURES},
            "summary conditions/procedures are incomplete or unexpected")
    for (condition, procedure), row in summaries.items():
        expected, record = CONDITIONS[condition], records[(condition,)]
        for key in ("stage", "design", "shape", "mode"):
            require(row[key] == expected[key], f"summary identity mismatch: {condition}/{key}")
        for key in ("effect", "contamination"):
            require(number(row[key], key) == expected[key], f"summary setting mismatch: {condition}/{key}")
        require(row["source"] == "synthetic", f"unexpected data source: {condition}")
        for key, value in dict(planned=expected["planned"], completed=record["completed"], failed=record["failed"]).items():
            require(csv_integer(row[key], key) == value, f"summary count mismatch: {condition}/{key}")
        rejected = csv_integer(row["rejections"], "rejections")
        require(rejected <= record["completed"], f"rejections exceed completed: {condition}/{procedure}")
        rate(row["rate"], rejected, record["completed"], f"{condition}/{procedure}")

    metrics = indexed(read_csv(folder, "benchmark_metrics.csv",
        "condition metric completed rejections rate".split()), ("condition", "metric"), "metric")
    require(set(metrics) == {(c, m) for c in CONDITIONS for m in METRICS},
            "metric conditions/registry are incomplete or unexpected")
    for (condition, metric), row in metrics.items():
        completed = records[(condition,)]["completed"]
        require(csv_integer(row["completed"], "completed") == completed, "metric completed mismatch")
        rejected = csv_integer(row["rejections"], "rejections")
        require(rejected <= completed, "metric rejections exceed completed")
        rate(row["rate"], rejected, completed, f"{condition}/{metric}")

    choices = indexed(read_csv(folder, "benchmark_choices.csv",
        "condition procedure metric count share".split()), ("condition", "procedure", "metric"), "choice")
    totals = {key: 0 for key in summaries}
    for (condition, procedure, metric), row in choices.items():
        require((condition, procedure) in totals and metric in METRICS + ("none",), "unknown choice identity")
        count = csv_integer(row["count"], "choice count")
        require(count > 0, "zero-count choice row is not part of the historical format")
        totals[(condition, procedure)] += count
        rate(row["share"], count, records[(condition,)]["completed"], "choice share")
    require(all(total == records[(key[0],)]["completed"] for key, total in totals.items()),
            "choice totals do not match completed replications")

    stability = manifest["stability"]
    require(type(stability) is dict, "stability object required")
    splits = integer(stability.get("splits"), "stability.splits")
    failed = integer(stability.get("failed"), "stability.failed")
    require(splits + failed == BUDGETS["stability"], "incomplete stability accounting")
    rows = read_csv(folder, "benchmark_stability.csv", ("split", "kendall_tau"))
    require(len(rows) == splits, "stability CSV count mismatch")
    tau = []
    for index, row in enumerate(rows, 1):
        require(csv_integer(row["split"], "split") == index, "stability ordinal mismatch")
        value = number(row["kendall_tau"], "kendall_tau")
        require(-1 <= value <= 1, "Kendall tau outside [-1,1]")
        tau.append(value)
    tau.sort()
    for key, quantile in (("medianTau", .5), ("lowerQuartileTau", .25)):
        if not tau:
            require(stability.get(key) is None, f"unavailable stability {key} must be null")
        else:
            position = (len(tau) - 1) * quantile
            low, high = math.floor(position), math.ceil(position)
            expected = tau[low] + (tau[high] - tau[low]) * (position - low)
            require(abs(number(stability.get(key), key) - expected) <= ROUNDING,
                    f"stability {key} does not match CSV")
    if splits == 0:
        require(stability.get("topOneAgreement") is None, "unavailable agreement must be null")
    else:
        agreement = number(stability.get("topOneAgreement"), "topOneAgreement")
        require(0 <= agreement <= 1 and abs(agreement - round(agreement * splits) / splits) <= .500001e-6,
                "invalid top-one agreement/count")

    fields = ("id", "result", "threshold", "observed", "question")
    verdicts = indexed(manifest.get("verdicts"), ("id",), "verdict")
    csv_verdicts = indexed(read_csv(folder, "benchmark_verdicts.csv", fields), ("id",), "verdict CSV")
    require(set(verdicts) == {(x,) for x in "ABCDE"} == set(csv_verdicts), "missing/unexpected verdicts")
    for key, verdict in verdicts.items():
        require(all(type(verdict.get(field)) is str and verdict[field] == csv_verdicts[key][field]
                    for field in fields), f"verdict CSV mismatch: {key}")
        require(verdict["result"] in ("pass", "fail", "inconclusive"), "unknown verdict result")
    results = {v["result"] for v in verdicts.values()}
    overall = "no-go" if "fail" in results else "conditional" if "inconclusive" in results else "go"
    require(manifest.get("overall") == overall, "overall result is inconsistent with verdicts")


def validate(root):
    root = Path(root).absolute()
    require(root.is_dir() and not root.is_symlink(), "artifact root must be a real directory")
    root = root.resolve()
    manifests = list(root.rglob("benchmark_manifest.json"))
    require(len(manifests) == 1, f"expected exactly one benchmark_manifest.json, found {len(manifests)}")
    folder = manifests[0].parent
    cursor = root
    for part in folder.relative_to(root).parts:
        cursor /= part
        require(not cursor.is_symlink(), "symlink directory in artifact path")
    manifest = strict_json(safe_file(folder, "benchmark_manifest.json"))
    exact_fields(manifest, dict(EXPECTED, kind="mvs-benchmark", protocolUnchanged=True,
                               protocolHashFrozen=EXPECTED["protocolHash"]), "manifest")
    files = manifest.get("files")
    require(type(files) is list and all(type(name) is str for name in files), "manifest.files array required")
    require(len(files) == len(set(files)) and REQUIRED <= set(files), "missing/duplicate required manifest files")
    checked = set()
    for line in safe_file(folder, "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        require(match is not None, "malformed SHA256SUMS.txt line")
        digest, name = match.groups()
        target = safe_file(folder, name)
        require(name not in checked, f"duplicate checksum target: {name}")
        require(sha256(target) == digest.lower(), f"checksum mismatch: {name}")
        checked.add(name)
    require((set(files) | {"benchmark_manifest.json"}) <= checked, "manifest or listed file is not covered by checksums")
    for name in files:
        require(safe_file(folder, name).stat().st_size > 0, f"empty artifact file: {name}")
    require(sha256(folder / "benchmark_protocol.txt") == EXPECTED["protocolHash"], "protocol text hash mismatch")
    exact_fields(manifest.get("replications"), BUDGETS, "replications")
    require(set(manifest["replications"]) == set(BUDGETS), "unexpected replication budget")
    exact_fields(manifest.get("thresholds"), THRESHOLDS, "thresholds")
    records = indexed(manifest.get("conditions"), ("id",), "condition")
    require(set(records) == {(c,) for c in CONDITIONS}, "all 19 frozen synthetic conditions are required")
    for (name,), record in records.items():
        expected = CONDITIONS[name]
        exact_fields(record, {key: value for key, value in expected.items() if key != "planned"}, name)
        completed = integer(record.get("completed"), name + ".completed")
        failed = integer(record.get("failed"), name + ".failed")
        require(completed + failed == expected["planned"], f"incomplete replication accounting: {name}")
        require(type(record.get("digest")) is str and HEX.fullmatch(record["digest"]), f"invalid decision digest: {name}")
    replay = manifest.get("determinism")
    require(type(replay) is dict, "determinism object required")
    require(all(type(replay.get(k)) is str and HEX.fullmatch(replay[k]) for k in ("first", "second")), "invalid replay digests")
    require(type(replay.get("identical")) is bool and replay["identical"] == (replay["first"] == replay["second"]), "inconsistent replay identity")
    require(replay["first"] == records[("determinism_replay",)]["digest"], "first replay digest mismatch")
    check_tables(folder, manifest, records)
    replay_verdict = next(v["result"] for v in manifest["verdicts"] if v["id"] == "E")
    require(replay_verdict == ("pass" if replay["identical"] else "fail"), "replay verdict does not match digests")
    resume = folder / "backup_resume.json"
    if resume.exists() or resume.is_symlink():
        require("backup_resume.json" in checked and "backup_resume.json" in files,
                "resume provenance is not declared and checksummed")
        provenance = strict_json(safe_file(folder, "backup_resume.json"))
        environments = provenance.get("environments")
        require(type(environments) is list and bool(environments)
                and all(type(value) is str and bool(value) for value in environments), "invalid resume environments")
        require(len(set(environments)) == 1, "benchmark resumed across different arithmetic environments")
        require(environments[0] == manifest.get("environmentHash"), "resume environment differs from manifest")
    return folder, manifest


def source_constant(root, path, name):
    text = (root / path).read_text(encoding="utf-8-sig")
    expression = r'^\s*public const string ' + re.escape(name) + r'\s*=\s*((?:"(?:[^"\\]|\\.)*"\s*(?:\+\s*)?)+);'
    matches = re.findall(expression, text, re.MULTILINE)
    require(len(matches) == 1, f"cannot uniquely read source constant {path}:{name}")
    return "".join(json.loads(token) for token in re.findall(r'"(?:[^"\\]|\\.)*"', matches[0]))


def check_source(root):
    root = Path(root)
    release = "Core/ScientificInfrastructure.cs"
    actual = dict(appVersion=source_constant(root, release, "Version"),
                  engineVersion=source_constant(root, release, "EngineVersion"),
                  formulaVersion=source_constant(root, "Infrastructure/OutputExporter.cs", "FormulaVersion"),
                  protocolVersion=source_constant(root, "Benchmark/BenchmarkProtocol.cs", "Version"))
    for path, constant, key in (("Infrastructure/OutputExporter.cs", "FormulaSpecification", "formulaHash"),
                                ("Benchmark/BenchmarkProtocol.cs", "Specification", "protocolHash")):
        actual[key] = hashlib.sha256(source_constant(root, path, constant).encode()).hexdigest()
    require(actual == {key: EXPECTED[key] for key in actual},
            "source identity does not match historical paper target (app 1.4.0 / engine 1.6.0 / frozen formula and protocol); "
            f"found app {actual['appVersion']} / engine {actual['engineVersion']}. "
            "Select a separately verified historical source revision before running this workflow. "
            "Current development evidence must be verified separately; do not change the historical gate.")
    require(source_constant(root, "Benchmark/BenchmarkProtocol.cs", "FrozenHash") == EXPECTED["protocolHash"],
            "source frozen protocol hash mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, help="artifact directory (default: current directory)")
    parser.add_argument("--check-source", type=Path, metavar="ROOT", help="check source identity without running a benchmark")
    args = parser.parse_args(argv)
    if args.root is not None and args.check_source is not None:
        parser.error("artifact directory and --check-source are mutually exclusive")
    try:
        if args.check_source is not None:
            check_source(args.check_source)
            print("historical paper source identity preflight passed (static identity only)")
        else:
            folder, manifest = validate(args.root or Path.cwd())
            print("paper benchmark artifact verified (integrity/completeness, not scientific certification)")
            print(f"  result:   {manifest['overall']}")
            print(f"  protocol: {manifest['protocolVersion']} / {manifest['protocolHash'][:16]}...")
            print(f"  app:      {manifest['appVersion']}  engine: {manifest['engineVersion']}")
            print(f"  profile:  {manifest['profile']}  seed: {manifest['seed']}")
            print(f"  folder:   {folder}")
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, csv.Error, RecursionError, OverflowError) as error:
        print(f"paper benchmark verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
