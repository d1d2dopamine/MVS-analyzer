#!/usr/bin/env python3
"""Round32 test-only normal-tail comparison and fresh-process cost measurements.

No production algorithm is implemented here. A/B values come only from the two
independent native harnesses. This file supports analysis of retained evidence;
explicit --execute is required to start native processes. Failed cases remain in
all artifacts and make acceptance fail closed. See --help for invocation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import struct
import subprocess
import sys
import time
import threading
from typing import Any

import mpmath as mp
import numpy as np
import scipy

SCHEMA = "mvs-normal-tail-round32/v2"
PROTOCOL_SHA = "86d4f5e87b06e7755ce2c9f301ac23ae5d087c1817fb20a5c064e91e52f994b0"
AMENDMENT_SHA = "5b81f65830cee7a46a5f9096c7d053bb714a2e377f1d67f90259fd8e9e04c492"
VERSIONS = {"scipy": "1.17.0", "numpy": "2.3.5", "mpmath": "1.3.0"}
THROUGHPUT_Z = [0., .5, 1., 2., 3., 4., 6., 8., 10., 20., 30., 37., 38., 39., 40.]
mp.mp.dps = 250


class EvidenceError(RuntimeError):
    """Malformed, incomplete, stale or unbound evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    # Disallow duplicate JSON keys and non-standard NaN/Infinity numbers.
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def bad_constant(value):
        raise EvidenceError(f"nonstandard JSON number: {value}")
    return json.loads(path.read_text(), object_pairs_hook=pairs,
                      parse_constant=bad_constant)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n")


def bits(value: float) -> str:
    return struct.pack(">d", value).hex()


def from_bits(value: str) -> float:
    require(isinstance(value, str), "binary64 bits must be a string")
    value = value.lower().removeprefix("0x")
    require(len(value) == 16 and all(c in "0123456789abcdef" for c in value),
            f"invalid binary64 bits: {value}")
    return struct.unpack(">d", bytes.fromhex(value))[0]


def canonical_bits(value: str) -> str:
    return bits(from_bits(value))


def exact_float(value: float) -> mp.mpf:
    require(math.isfinite(value), "exact_float requires finite binary64")
    n, d = value.as_integer_ratio()
    return mp.mpf(n) / mp.mpf(d)


def decimal(value: mp.mpf | float | int) -> str:
    return mp.nstr(value, 90)


def finite_number(value: float) -> float | str:
    return value if math.isfinite(value) else str(value)


def nearest_rank(values: list[float], probability: float) -> float:
    require(bool(values), "quantile of empty sequence")
    require(all(math.isfinite(x) for x in values), "nonfinite timing value")
    require(0 < probability <= 1, "invalid quantile")
    return sorted(values)[math.ceil(probability * len(values)) - 1]


def summarize_times(values: list[float], expected_count: int) -> dict:
    require(len(values) == expected_count, "wrong timing observation count")
    require(all(math.isfinite(x) and x > 0 for x in values), "invalid timing")
    return {"n": len(values), "medianMs": statistics.median(values),
            "p95Ms": nearest_rank(values, .95), "minMs": min(values),
            "maxMs": max(values), "rangeMs": max(values) - min(values),
            "meanMs": statistics.mean(values),
            "stdevMs": statistics.stdev(values) if len(values) > 1 else 0.0}


def unique_by(rows: list[dict], key: str, expected: list[str] | None = None) -> dict:
    result = {}
    for row in rows:
        require(isinstance(row, dict) and key in row, f"missing row key {key}")
        item = row[key]
        require(item not in result, f"duplicate {key}: {item}")
        result[item] = row
    if expected is not None:
        require(set(result) == set(expected),
                f"{key} coverage mismatch; missing={sorted(set(expected)-set(result))}, "
                f"unexpected={sorted(set(result)-set(expected))}")
        require(len(expected) == len(set(expected)), "duplicate expected case")
    return result


def verify_bound_files(bindings: list[dict], root: Path) -> list[dict]:
    require(bool(bindings), "empty evidence binding list")
    seen = set()
    verified = []
    for item in bindings:
        require(set(item) >= {"path", "sha256"}, "incomplete file binding")
        name = item["path"]
        require(name not in seen, f"duplicate binding {name}")
        seen.add(name)
        path = Path(name)
        if not path.is_absolute():
            path = root / path
        require(path.is_file(), f"missing bound file: {path}")
        actual = sha256(path)
        require(actual == item["sha256"], f"binding mismatch: {path}")
        verified.append({"path": name, "sha256": actual, "bytes": path.stat().st_size})
    return verified


def accuracy(value_bits: str, h_probability: str, h_log: str, rounded_bits: str) -> dict:
    """Evaluate exact binary64 value against the frozen high-precision oracle."""
    value = from_bits(value_bits)
    h = mp.mpf(h_probability)
    log_h = mp.mpf(h_log)
    rounded = from_bits(rounded_bits)
    require(mp.isfinite(h) and h >= 0, "invalid H probability")
    require(math.isfinite(rounded) and 0 <= rounded <= 1, "invalid rounded H")
    failures = []
    result = {"valueBits": bits(value), "value": finite_number(value),
              "roundedReferenceBits": bits(rounded)}
    if not math.isfinite(value) or not 0 <= value <= 1:
        result.update({"region": "invalid", "failures": ["finite_unit_interval"], "pass": False})
        return result
    v = exact_float(value)
    absolute = abs(v - h)
    relative = absolute / h if h else (mp.mpf(0) if v == 0 else mp.inf)
    log_error = abs(mp.log(v) - log_h) if v > 0 else (mp.mpf(0) if h == 0 else mp.inf)
    result.update({"absoluteError": decimal(absolute), "relativeError": decimal(relative),
                   "absoluteLogError": decimal(log_error),
                   "roundedReferenceAbsoluteError": decimal(abs(v - exact_float(rounded)))})
    if rounded == 0:
        region = "rounded_zero"
        if value != 0:
            failures.append("rounded_zero_required")
    elif h >= mp.mpf("1e-8"):
        region = "central"
        if absolute > mp.mpf("2e-15"):
            failures.append("absolute_error_gt_2e-15")
    elif h >= mp.power(2, -1022):
        region = "normal_tail"
        if value == 0:
            failures.append("premature_zero")
        if relative > mp.mpf("2e-12"):
            failures.append("relative_error_gt_2e-12")
        if log_error > mp.mpf("2e-12"):
            failures.append("log_error_gt_2e-12")
    else:
        region = "subnormal_tail"
        if value <= 0:
            failures.append("positive_subnormal_required")
        if abs(v - exact_float(rounded)) > 8 * mp.power(2, -1074):
            failures.append("subnormal_error_gt_8_ulps")
    result.update({"region": region, "failures": failures, "pass": not failures,
                   "prematureZero": value == 0 and rounded > 0})
    return result


def reference_agreement(p100: str, p200: str, log100: str, log200: str,
                        rounded100: str, rounded200: str) -> dict:
    # The generator certifies nearest-even, including ties/subnormals. The driver
    # checks both independently saved precisions and their exact bound content.
    require(mp.mpf(p100) >= 0 and mp.mpf(p200) >= 0, "negative reference")
    delta = abs(mp.mpf(log100) - mp.mpf(log200))
    okay = canonical_bits(rounded100) == canonical_bits(rounded200) and delta < mp.mpf("1e-80")
    return {"pass": bool(okay), "sameRoundedBits": canonical_bits(rounded100) == canonical_bits(rounded200),
            "absoluteLogDifference": decimal(delta)}


def classify_decision(a: bool, b: bool, reference: bool | None) -> str:
    require(type(a) is bool and type(b) is bool, "decision is not boolean")
    if reference is None:
        return "unresolved"
    require(type(reference) is bool, "reference decision is not boolean")
    if b != reference:
        return "worsening" if a == reference else "both_incorrect"
    if a != b:
        return "improving"
    return "unchanged_correct"


def cost_gates(startup_a: list[float], startup_b: list[float],
               throughput_a: list[float], throughput_b: list[float],
               publish_a: int, publish_b: int) -> dict:
    require(len(startup_a) == len(startup_b) == 30, "startup requires all30 pairs")
    sa, sb = summarize_times(startup_a[1:], 29), summarize_times(startup_b[1:], 29)
    ta, tb = summarize_times(throughput_a, 30), summarize_times(throughput_b, 30)
    median_increment = sb["medianMs"] - sa["medianMs"]
    p95_increment = sb["p95Ms"] - sa["p95Ms"]
    median_limit = max(20., .1 * sa["medianMs"])
    p95_limit = max(50., .2 * sa["p95Ms"])
    ratio = tb["medianMs"] / ta["medianMs"]
    checks = {"publish_increment_lte_10MiB": publish_b - publish_a <= 10 * 1024 * 1024,
              "startup_median_budget": median_increment <= median_limit,
              "startup_p95_budget": p95_increment <= p95_limit,
              "throughput_median_ratio_lte_1_25": ratio <= 1.25}
    return {"startup": {"A": sa, "B": sb, "firstPairExcluded": True,
                         "medianIncrementMs": median_increment, "medianLimitMs": median_limit,
                         "p95IncrementMs": p95_increment, "p95LimitMs": p95_limit,
                         "pairedRatios": [b/a for a,b in zip(startup_a, startup_b)]},
            "throughput": {"A": ta, "B": tb, "medianBOverMedianA": ratio,
                           "pairedRatios": [b/a for a,b in zip(throughput_a, throughput_b)]},
            "publishBytes": {"A": publish_a, "B": publish_b, "increment": publish_b-publish_a},
            "checks": checks, "pass": all(checks.values())}


def retained_process(command: list[str], output_dir: Path, name: str,
                     timeout_seconds: float) -> dict:
    """One attempt; raw stdout/stderr and wall/exit status persisted before parsing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{name}.stdout"
    stderr_path = output_dir / f"{name}.stderr"
    meta_path = output_dir / f"{name}.process.json"
    require(not any(p.exists() for p in (stdout_path, stderr_path, meta_path)),
            f"refusing to overwrite retained process {name}")
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    error = None
    timeout = False
    code = None
    elapsed_ns = 0
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        start = time.perf_counter_ns()
        try:
            child = subprocess.Popen(command, stdout=out, stderr=err)
            def terminate_child():
                nonlocal timeout
                if child.poll() is None:
                    timeout = True
                    child.kill()
            watchdog = threading.Timer(timeout_seconds, terminate_child)
            watchdog.daemon = True
            watchdog.start()
            try:
                # Blocking wait, without subprocess timeout polling granularity.
                code = child.wait()
                elapsed_ns = time.perf_counter_ns() - start
            finally:
                watchdog.cancel()
                watchdog.join()
            if timeout:
                error = "child_timeout"
        except OSError as exc:
            elapsed_ns = time.perf_counter_ns() - start
            error = f"{type(exc).__name__}: {exc}"
    result = {"command": command, "startedUtc": started_utc,
              "wallNs": elapsed_ns, "wallMs": elapsed_ns / 1e6,
              "timeoutSeconds": timeout_seconds, "timedOut": timeout,
              "exitCode": code, "launchError": error,
              "stdout": stdout_path.name, "stderr": stderr_path.name,
              "stdoutSha256": sha256(stdout_path), "stderrSha256": sha256(stderr_path)}
    write_json(meta_path, result)
    return result


def parse_successful_process(meta: dict, output_dir: Path) -> dict:
    require(meta["exitCode"] == 0 and not meta["timedOut"] and meta["launchError"] is None,
            f"native process unsuccessful: {meta['command']}")
    path = output_dir / meta["stdout"]
    require(sha256(path) == meta["stdoutSha256"], "retained stdout hash mismatch")
    require(sha256(output_dir / meta["stderr"]) == meta["stderrSha256"], "retained stderr hash mismatch")
    value = read_json(path)
    require(isinstance(value, dict), "native output must be JSON object")
    return value


def round_mpf_bits(value: mp.mpf) -> str:
    """Explicit binary64 nearest-even conversion, including subnormal ties."""
    require(mp.isfinite(value) and value >= 0, "nonnegative finite rounding input required")
    if not value:
        return bits(0.)
    sign, mantissa, exponent, _ = value._mpf_
    numerator = mantissa << max(exponent, 0)
    denominator = 1 << max(-exponent, 0)
    e = numerator.bit_length() - denominator.bit_length()
    if (numerator < denominator << e) if e >= 0 else (numerator << -e < denominator):
        e -= 1
    shift = 1074 if e < -1022 else 52 - e
    n, d = ((numerator << shift, denominator) if shift >= 0 else
            (numerator, denominator << -shift))
    q, rem = divmod(n, d)
    q += (2 * rem > d) or (2 * rem == d and q % 2 == 1)
    if e < -1022:
        raw = q
    else:
        if q == 1 << 53:
            q >>= 1
            e += 1
        if e > 1023:
            return bits(math.inf)
        raw = ((e + 1023) << 52) | (q - (1 << 52))
    return f"{raw:016x}"


def fp_bits(record: dict) -> str:
    require(isinstance(record, dict), "floating point record must be an object")
    value = from_bits(record["bits"])
    kind = ("nan" if math.isnan(value) else "positive_infinity" if value == math.inf else
            "negative_infinity" if value == -math.inf else "finite")
    require(record["kind"] == kind, "floating point bits/kind mismatch")
    if math.isfinite(value):
        require(type(record["value"]) in (float, int) and record["value"] == value,
                "floating point bits/value mismatch")
        require(bits(float(record["roundTrip"])) == bits(value), "floating point roundTrip mismatch")
    else:
        require(record["value"] is None, "nonfinite number must have null JSON value")
    return bits(value)


def validate_h(h: dict) -> dict:
    one, two = h["precision100"], h["precision200"]
    result = reference_agreement(one["p"], two["p"], one["logP"], two["logP"],
                                 one["roundedBits"], two["roundedBits"])
    require(h["established"] is True and result["pass"], "high-precision reference not established")
    for item in (one, two):
        require(round_mpf_bits(mp.mpf(item["p"])) == canonical_bits(item["roundedBits"]),
                "reference probability rounded-bits mismatch")
    require(canonical_bits(h["roundedBits"]) == canonical_bits(two["roundedBits"]),
            "reference selected rounded bits mismatch")
    return result


def h_accuracy(value_bits: str, h: dict) -> dict:
    validate_h(h)
    two = h["precision200"]
    return accuracy(value_bits, two["p"], two["logP"], h["roundedBits"])


def validate_reference_grid(inputs: dict, references: dict, policy: dict) -> None:
    require(inputs["schema"] == "mvs-normal-tail-input/v1", "wrong grid schema")
    require(references["schema"] == "mvs-normal-tail-reference/v1", "wrong reference schema")
    require(policy["schema"] == "mvs-normal-tail-policy-input/v1", "wrong policy input schema")
    alphas = [bits(x) for x in (.001, .01, .05, .1, .2)]
    require(inputs["alphaBits"] == alphas and inputs["familySize"] == 12, "changed family/alphas")
    expected = {bits(k / 16): set() for k in range(641)}
    expected.update({bits(2. ** k): set() for k in (-52,-40,-30,-20,-10)})
    expected.update({bits(37 + k / 1024): set() for k in range(2049)})
    roots = references["roots"]
    require(len(roots) == 7, "requires five decision and two underflow roots")
    require(sorted(r["alphaBits"] for r in roots if r["alphaBits"] is not None) == sorted(alphas),
            "wrong root alpha coverage")
    require({r["kind"] for r in roots if r["alphaBits"] is None} ==
            {"half_min_subnormal", "normal_transition"}, "wrong underflow root coverage")
    for root in roots:
        one, two = root["precision100"], root["precision200"]
        require(one["roundedBits"] == two["roundedBits"] == root["roundedBits"],
                "root precision rounded-bits disagreement")
        for item in (one, two):
            require(round_mpf_bits(mp.mpf(item["root"])) == item["roundedBits"], "root rounding mismatch")
        z0 = from_bits(root["roundedBits"])
        values = [z0]
        for direction in (-math.inf, math.inf):
            current = z0
            for _ in range(16):
                current = math.nextafter(current, direction)
                values.append(current)
        for offset in (1e-12,1e-10,1e-8,1e-6):
            for sign in (-1,1):
                center = z0 + sign * offset
                values.append(center)
                for direction in (-math.inf, math.inf):
                    current = center
                    for _ in range(2):
                        current = math.nextafter(current, direction)
                        values.append(current)
        for value in values:
            expected.setdefault(bits(value), set())
            if root["alphaBits"] is not None:
                expected[bits(value)].add(root["alphaBits"])
    require([x["zBits"] for x in inputs["points"]] == sorted(expected, key=from_bits),
            "grid differs from full frozen rule reconstruction")
    point_map = unique_by(inputs["points"], "id")
    reference_map = unique_by(references["points"], "id", list(point_map))
    for point_id, point in point_map.items():
        require(set(point["thresholds"]) == expected[point["zBits"]], "threshold memberships differ")
        ref = reference_map[point_id]
        require(ref["zBits"] == point["zBits"], "reference/input z mismatch")
        validate_h(ref["h"])
        require(point["referenceRoundedPBits"] == ref["h"]["roundedBits"], "input/reference rounding mismatch")
    specials = {"special_+zero": (bits(0.), "one"), "special_-zero": (bits(-0.), "one"),
                "special_+infinity": (bits(math.inf), "zero"),
                "special_-infinity": (bits(-math.inf), "reject"),
                "special_quiet_nan": ("7ff8000000000000", "reject"),
                "special_negative_epsilon": (bits(-2.**-52), "reject"),
                "special_negative_one": (bits(-1.), "reject"),
                "special_maximum_finite": ("7fefffffffffffff", "zero")}
    require({r["id"]: (r["zBits"],r["expected"]) for r in inputs["specials"]} == specials,
            "special-domain coverage mismatch")
    unique_by(inputs["specials"], "id", list(specials))
    unique_by(references["rankCases"], "id", [r["id"] for r in inputs["rankCases"]])
    require(len(inputs["rankCases"]) == 165, "requires 53 frozen+112 deterministic rank cases")
    for rank in references["rankCases"]:
        for kind in ("hExactRankZ", "hRoundedRankZ"):
            if kind in rank:
                validate_h(rank[kind])
    unique_by(policy["cases"], "id")
    expected_policy = {}
    for p in inputs["points"]:
        for alpha in alphas:
            expected_policy[f"{p['id']}_alpha_{alpha}"] = (p["referenceRoundedPBits"], alpha, 12)
    for rank in references["rankCases"]:
        for kind in ("hExactRankZ", "hRoundedRankZ"):
            if kind in rank:
                for alpha in alphas:
                    expected_policy[f"{rank['id']}_{kind}_alpha_{alpha}"] = (rank[kind]["roundedBits"], alpha, 12)
    require({p["id"]: (p["rawPBits"], p["alphaBits"], p["familySize"]) for p in policy["cases"]} ==
            expected_policy, "reference-policy input coverage/value mismatch")


def validate_identity(identity: dict, expected: dict, variant: str) -> None:
    require(identity.get("experimental") is True and identity.get("variant") == variant,
            "native variant/experimental identity mismatch")
    required = {"sourceTreeSha256", "sourceAnalysisSha256", "variantAnalysisSha256", "programSourceSha256",
                "buildManifestSha256", "coreDllSha256", "harnessDllSha256", "formulaHash", "formulaVersion",
                "engineVersion", "decisionPolicy", "runtime", "architecture", "mathNetVersion",
                "mathNetDllSha256", "mathNetPackageSha256"}
    require(set(expected) >= required, "incomplete expected native identity")
    for key, value in expected.items():
        require(identity.get(key) == value, f"native identity mismatch {variant}.{key}")


def validate_native(output: dict, mode: str, variant: str, expected_identity: dict,
                    input_path: Path, expected_inputs: list[dict]) -> dict:
    schemas = {"scalar": "mvs-normal-tail-scalar/v1", "rank": "mvs-normal-tail-ranks/v1",
               "policy": "mvs-normal-tail-policy/v1"}
    require(output["schema"] == schemas[mode], "native mode schema mismatch")
    validate_identity(output["identity"], expected_identity, variant)
    require(output["inputSha256"] == sha256(input_path), "native input hash mismatch")
    rows = unique_by(output["rows"], "id", [r["id"] for r in expected_inputs])
    for inp in expected_inputs:
        row = rows[inp["id"]]
        require(row["input"] == inp, "native echoed input mismatch")
        if mode == "scalar":
            require(fp_bits(row["z"]) == inp["zBits"], "native scalar z mismatch")
            if inp.get("expected") == "reject":
                require(row.get("status") == "rejected_domain" and row.get("candidateInvoked") is False and
                        "p" not in row, "invalid domain was evaluated")
                continue
            require(row.get("status") == "evaluated" and row.get("candidateInvoked") is True,
                    "valid scalar was not evaluated")
            fp_bits(row["p"])
            expected_alphas = inp.get("thresholds", [])
        elif mode == "rank":
            require(row["method"] == inp["method"], "rank method mismatch")
            require(row["nativeZStatus"] == "not_exposed_by_unchanged_api", "native z provenance mismatch")
            fp_bits(row["p"])
            expected_alphas = [bits(x) for x in (.001,.01,.05,.1,.2)]
        else:
            require(fp_bits(row["rawP"]) == inp["rawPBits"], "policy rawP mismatch")
            require(fp_bits(row["alpha"]) == inp["alphaBits"], "policy alpha mismatch")
            require(row["familySize"] == inp["familySize"] == 12, "policy family mismatch")
            fp_bits(row["adjustedP"])
            require(type(row["reject"]) is bool, "policy result must be boolean")
            continue
        decisions = unique_by(row["decisions"], "alphaBits", expected_alphas)
        for decision in decisions.values():
            require(decision["familySize"] == 12, "native decision family mismatch")
            fp_bits(decision["adjustedP"])
            require(type(decision["reject"]) is bool, "native decision must be boolean")
    return rows


def compare_decision(point_id: str, alpha_bits: str, a: dict, b: dict,
                     reference: dict, h: dict, scope: str) -> dict:
    alpha = from_bits(alpha_bits)
    mathematical = bool(mp.mpf(h["precision200"]["p"]) * 12 < exact_float(alpha))
    classification = classify_decision(a["reject"], b["reject"], reference["reject"])
    return {"id": point_id, "scope": scope, "alphaBits": alpha_bits, "familySize": 12,
            "A": a, "B": b, "referencePolicy": reference,
            "mathematicalReject": mathematical,
            "policyRoundingDiscrepancy": reference["reject"] != mathematical,
            "changed": a["reject"] != b["reject"], "classification": classification,
            "candidateMatchesPolicy": b["reject"] == reference["reject"]}


def compare_scalar(inputs: dict, references: dict, native: dict, policies: dict) -> dict:
    refs = unique_by(references["points"], "id")
    results, decisions, monotonicity = [], [], []
    previous = None
    for inp in inputs["points"]:
        key = inp["id"]
        ref = refs[key]
        a, b = native["A"][key], native["B"][key]
        evaluations = {"A": h_accuracy(a["p"]["bits"], ref["h"]),
                       "B": h_accuracy(b["p"]["bits"], ref["h"]),
                       "S": h_accuracy(fp_bits(ref["scipy"]["p"]), ref["h"])}
        s_log = from_bits(fp_bits(ref["scipy"]["logP"]))
        evaluations["S"]["directLogSfAbsoluteError"] = decimal(
            abs(exact_float(s_log) - mp.mpf(ref["h"]["precision200"]["logP"]))) if math.isfinite(s_log) else "inf"
        row = {"id": key, "zBits": inp["zBits"], "z": inp["z"], "tags": inp["tags"],
               "thresholds": inp["thresholds"], "reference": ref, "evaluations": evaluations,
               "nativeA": a["p"], "nativeB": b["p"]}
        b_value = from_bits(b["p"]["bits"])
        if previous is not None and (not math.isfinite(b_value) or b_value > previous["value"]):
            monotonicity.append({"previousId": previous["id"], "currentId": key,
                                 "previousBits": previous["bits"], "currentBits": b["p"]["bits"]})
        previous = {"id": key, "value": b_value, "bits": b["p"]["bits"]}
        if from_bits(inp["zBits"]) == 0 and b_value != 1:
            row["evaluations"]["B"]["failures"].append("exact_at_zero")
            row["evaluations"]["B"]["pass"] = False
        results.append(row)
        ad, bd = unique_by(a["decisions"], "alphaBits"), unique_by(b["decisions"], "alphaBits")
        for alpha in inp["thresholds"]:
            policy_id = f"{key}_alpha_{alpha}"
            rp = policies["A"][policy_id]
            decisions.append(compare_decision(key, alpha,
                {"rawP": a["p"], **ad[alpha]}, {"rawP": b["p"], **bd[alpha]},
                {"rawP": rp["rawP"], "adjustedP": rp["adjustedP"], "reject": rp["reject"]},
                ref["h"], "threshold_acceptance"))
    specials = []
    for inp in inputs["specials"]:
        key = inp["id"]
        a, b = native["A"][key], native["B"][key]
        if inp["expected"] == "reject":
            passed = a["status"] == b["status"] == "rejected_domain"
        else:
            expected = 1. if inp["expected"] == "one" else 0.
            passed = from_bits(b["p"]["bits"]) == expected
        specials.append({"input": inp, "A": a, "B": b, "candidatePass": passed,
                         "note": "Actual A retained; exact-at-zero acceptance applies only to B."})
    central = [r for r in results if mp.mpf(r["reference"]["h"]["precision200"]["p"]) >= mp.mpf("1e-8")]
    max_a = max(mp.mpf(r["evaluations"]["A"]["absoluteError"]) for r in central)
    max_b = max(mp.mpf(r["evaluations"]["B"].get("absoluteError", "inf")) for r in central)
    improvement = max_b * 10 <= max_a
    premature_a = [r["id"] for r in results if r["evaluations"]["A"].get("prematureZero")]
    premature_b = [r["id"] for r in results if r["evaluations"]["B"].get("prematureZero")]
    failures = [{"id": r["id"], "zBits": r["zBits"], "region": r["evaluations"]["B"]["region"],
                 "failures": r["evaluations"]["B"]["failures"]}
                for r in results if not r["evaluations"]["B"]["pass"]]
    checks = {"all_candidate_numeric_gates": not failures,
              "candidate_monotone_nonincreasing": not monotonicity,
              "special_domain_and_underflow": all(s["candidatePass"] for s in specials),
              "max_absolute_error_improved_at_least_10x": bool(improvement),
              "all_A_premature_zeros_eliminated": not premature_b,
              "all_threshold_B_decisions_match_policy": all(d["candidateMatchesPolicy"] for d in decisions)}
    return {"rows": results, "specials": specials, "decisions": decisions,
            "candidateFailures": failures, "monotonicityViolations": monotonicity,
            "centralMaxAbsoluteError": {"A": decimal(max_a), "B": decimal(max_b),
                                        "improvementFactor": decimal(max_a/max_b) if max_b else "inf"},
            "prematureZeros": {"A": premature_a, "B": premature_b},
            "scipyDiagnosticFailureIds": [r["id"] for r in results if not r["evaluations"]["S"]["pass"]],
            "checks": checks, "pass": all(checks.values())}


def compare_ranks(inputs: dict, references: dict, native: dict, policies: dict) -> dict:
    refs = unique_by(references["rankCases"], "id")
    rows, decisions, invariance = [], [], []
    for inp in inputs["rankCases"]:
        key = inp["id"]
        a, b = native["A"][key], native["B"][key]
        ref = refs[key]
        row = {"id": key, "input": inp, "reference": ref, "A": a, "B": b,
               "nativeZStatus": "not_exposed_by_unchanged_api", "failures": []}
        if inp["origin"] == "frozen-fixture":
            expected = inp["fixtureExpectedP"]
            tolerance = 2e-7 if inp["method"] == "mann_whitney" else 2e-10
            checks = {}
            for variant, item in (("A",a),("B",b)):
                value = from_bits(item["p"]["bits"])
                checks[variant] = math.isnan(value) if expected is None else (
                    math.isfinite(value) and abs(value - expected) <= tolerance)
                if not checks[variant]:
                    row["failures"].append(f"frozen_fixture_{variant}")
            row["existingFixtureRegression"] = {"expectedP": expected, "unchangedAbsoluteTolerance": tolerance,
                                                  "checks": checks, "pass": all(checks.values())}
            if inp["fixtureReference"] == "mvs-declared-policy" and expected is not None:
                for variant, item in (("A",a),("B",b)):
                    if from_bits(item["p"]["bits"]) != expected:
                        row["failures"].append(f"declared_policy_exact_{variant}")
        if inp["method"] == "kruskal_wallis":
            row["negativeControlBitwiseEqual"] = a["p"]["bits"] == b["p"]["bits"]
            if not row["negativeControlBitwiseEqual"]:
                row["failures"].append("KW_negative_control_bits_differ")
        if "hExactRankZ" in ref:
            row["accuracyExactMathematicalZ"] = {v: h_accuracy(item["p"]["bits"], ref["hExactRankZ"])
                                                 for v,item in (("A",a),("B",b))}
            row["accuracyRoundedInputZ"] = {v: h_accuracy(item["p"]["bits"], ref["hRoundedRankZ"])
                                            for v,item in (("A",a),("B",b))}
            row["scipyVsExactMathematicalZ"] = h_accuracy(fp_bits(ref["scipy"]["p"]), ref["hExactRankZ"])
            if not row["accuracyExactMathematicalZ"]["B"]["pass"]:
                row["failures"].append("B_end_to_end_unresolved_exact_rank_H_discrepancy")
            ad, bd = unique_by(a["decisions"],"alphaBits"), unique_by(b["decisions"],"alphaBits")
            for alpha in inputs["alphaBits"]:
                rp = policies["A"][f"{key}_hExactRankZ_alpha_{alpha}"]
                decision = compare_decision(key, alpha,
                    {"rawP":a["p"], **ad[alpha]}, {"rawP":b["p"], **bd[alpha]},
                    {"rawP":rp["rawP"], "adjustedP":rp["adjustedP"], "reject":rp["reject"]},
                    ref["hExactRankZ"], "native_rank_diagnostic")
                decisions.append(decision)
                if not decision["candidateMatchesPolicy"]:
                    row["failures"].append(f"B_rank_decision_mismatch_{alpha}")
        if inp["origin"] == "deterministic-variant":
            original_id = f"mw_n{inp['n']}_{inp['family']}_original"
            equal = {v: native[v][key]["p"]["bits"] == native[v][original_id]["p"]["bits"] for v in ("A","B")}
            check = {"id": key, "originalId": original_id, "bitwiseEqual": equal, "pass": all(equal.values())}
            invariance.append(check)
            if not check["pass"]:
                row["failures"].append("deterministic_metamorphic_bitwise_failure")
        row["pass"] = not row["failures"]
        rows.append(row)
    return {"rows": rows, "decisions": decisions, "metamorphicChecks": invariance,
            "failures": [{"id":r["id"],"failures":r["failures"]} for r in rows if not r["pass"]],
            "pass": all(r["pass"] for r in rows)}


def validate_policy_parity(policies: dict) -> None:
    require(set(policies["A"]) == set(policies["B"]), "policy output ID mismatch")
    for key, a in policies["A"].items():
        b = policies["B"][key]
        require(a == b, f"unchanged DecisionPolicy differs between variants at {key}")


def expected_checksum(scalar_rows: dict) -> str:
    values = [from_bits(scalar_rows[f"z_{bits(z)}"]["p"]["bits"]) for z in THROUGHPUT_Z]
    accumulator = 0.
    for i in range(100000):
        accumulator += values[i % len(values)]
    return bits(accumulator)


def validate_performance_output(output: dict, mode: str, variant: str, identity: dict,
                                startup_p_bits: str, checksum_bits: str) -> float | None:
    if mode == "startup":
        require(output["schema"] == "mvs-normal-tail-startup/v1", "wrong startup schema")
        require(output["experimental"] is True and output["variant"] == variant, "startup identity mismatch")
        require(output["sourceTreeSha256"] == identity["sourceTreeSha256"], "startup source mismatch")
        require(output["valid"] is True, "startup result invalid")
        require(fp_bits(output["p"]) == startup_p_bits, "startup fixed-pair p differs from correctness run")
        return None
    require(output["schema"] == "mvs-normal-tail-throughput/v1", "wrong throughput schema")
    validate_identity(output["identity"], identity, variant)
    require(output["warmupCalls"] == output["measuredCalls"] == 100000, "wrong throughput workload")
    require(output["zBits"] == [bits(x) for x in THROUGHPUT_Z], "wrong throughput z-order")
    require(fp_bits(output["checksum"]) == fp_bits(output["warmupChecksum"]) == checksum_bits,
            "throughput checksum differs from fixed scalar evaluations")
    ticks, frequency = output["elapsedTicks"], output["stopwatchFrequency"]
    require(type(ticks) is int and type(frequency) is int and ticks > 0 and frequency > 0,
            "invalid throughput stopwatch")
    require(output["elapsedSeconds"] == ticks / frequency, "throughput elapsed conversion mismatch")
    return 1000 * ticks / frequency


def prepare_config(args) -> None:
    out = Path(args.config).resolve()
    require(not out.exists(), "config already exists; freeze is write-once")
    build_dir, ref_dir = Path(args.native_build_dir).resolve(), Path(args.reference_dir).resolve()
    protocol, amendment = Path(args.protocol).resolve(), Path(args.amendment).resolve()
    require(sha256(protocol) == PROTOCOL_SHA, "original protocol hash mismatch")
    require(sha256(amendment) == AMENDMENT_SHA, "amendment hash mismatch")
    build_path = build_dir / "build-manifest.json"
    build = read_json(build_path)
    copies = read_json(build_dir / "variant-copy-verification.json")
    verified = read_json(build_dir / "inspection-verification.json")
    reference_manifest = read_json(ref_dir / "reference-manifest.json")
    require(verified["passed"] is True and verified["numericModesExecuted"] is False,
            "native preparation not verified or candidates already read")
    require(build["numericModesExecutedByPreparation"] is False, "native preparation evaluated candidates")
    require(build["publish"] == {"configuration":"Release", "runtimeIdentifier":"linux-x64",
            "frameworkDependent":True,"selfContained":False,"singleFile":False,"trimmed":False,
            "readyToRun":False,"nativeProvider":False}, "publish settings mismatch")
    require(build["sdkRequired"] == "8.0.425" and build["runtimeRequired"] == "8.0.31", "runtime mismatch")
    require(build["package"]["id"] == "MathNet.Numerics" and build["package"]["version"] == "5.0.0",
            "wrong package")
    require(copies["buildManifestSha256"] == sha256(build_path), "copy verification build binding mismatch")
    require(copies["variants"]["A"]["changedPaths"] == [] and
            set(copies["variants"]["B"]["changedPaths"]) == {"Core/AnalysisEngine.cs","MvsAnalyzer.Core/MvsAnalyzer.Core.csproj"},
            "unexpected native source differences")
    require(reference_manifest["protocol"]["sha256"] == PROTOCOL_SHA and
            reference_manifest["amendment"]["sha256"] == AMENDMENT_SHA and
            reference_manifest["hEstablished"] is True, "reference manifest not frozen/established")
    require(reference_manifest["environment"]["versions"] == VERSIONS, "reference environment mismatch")
    bindings = {}
    def bind(path: Path, expected: str | None = None):
        path = path.resolve()
        actual = sha256(path)
        require(expected is None or actual == expected, f"preparation file binding mismatch: {path}")
        bindings[str(path)] = actual
    for p in (protocol,amendment,build_path,build_dir/"variant-copy-verification.json",
              build_dir/"inspection-verification.json",build_dir/"candidate-expression.diff",
              build_dir/"candidate-project.diff",build_dir/"dotnet-info.txt",ref_dir/"reference-manifest.json",
              Path(__file__),Path(__file__).with_name("test_normal_tail_comparison.py")):
        bind(p)
    for name, expected in reference_manifest["files"].items():
        bind(ref_dir/name, expected)
    for key in ("generator","fixtures","sourceManifest"):
        if key in reference_manifest:
            item = reference_manifest[key]
            bind(Path(item["path"]), item["sha256"])
    package = build_dir/"packages"/"mathnet.numerics.5.0.0.nupkg"
    bind(package,build["package"]["sha256"])
    # Preserve the externally prepared package/license evidence without changing it.
    package_dir = build_dir.parent/"packages"
    for p in sorted(package_dir.iterdir()):
        if p.is_file():
            bind(p)
    source_root = Path(build["sourceRoot"])
    identities, variants = {}, {}
    for variant in ("A","B"):
        inspection_path = build_dir/variant/"inspection.json"
        inventory_path = build_dir/variant/"publish-inventory.json"
        bind(inspection_path, verified["variants"][variant]["inspectionSha256"])
        bind(inventory_path, verified["variants"][variant]["publishInventorySha256"])
        identity = read_json(inspection_path)["identity"]
        publish = build_dir/variant/"publish"
        inventory = read_json(inventory_path)
        files = unique_by(inventory["files"],"path")
        require(set(files) == {str(p.relative_to(publish)) for p in publish.rglob("*") if p.is_file()},
                "publish inventory completeness mismatch")
        require(inventory["totalBytes"] == sum(r["bytes"] for r in files.values()), "publish bytes sum mismatch")
        for name,item in files.items():
            bind(publish/name,item["sha256"])
            require((publish/name).stat().st_size == item["bytes"], "publish byte count mismatch")
        expected_fields = {"sourceTreeSha256":build["sourceTreeSha256"],
            "sourceAnalysisSha256":build["sourceFiles"]["Core/AnalysisEngine.cs"],
            "variantAnalysisSha256":copies["variants"][variant]["sourceAnalysisSha256"],
            "programSourceSha256":build["templateHashes"]["Program.cs"],
            "buildManifestSha256":sha256(build_path),"coreDllSha256":files["MvsAnalyzer.Core.dll"]["sha256"],
            "harnessDllSha256":files["MvsAnalyzer.Core.Tests.dll"]["sha256"],
            "formulaVersion":"MVS-1.4.0", "formulaHash":"10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c",
            "decisionPolicy":"all-metrics-bonferroni-v1", "runtime":".NET 8.0.31", "architecture":"X64",
            "engineVersion":identity["engineVersion"], "mathNetVersion":"5.0.0.0" if variant=="B" else None,
            "mathNetDllSha256":build["package"]["assetSha256"] if variant=="B" else None,
            "mathNetPackageSha256":build["package"]["sha256"]}
        validate_identity(identity,expected_fields,variant)
        for name, original_hash in build["sourceFiles"].items():
            if Path(name).suffix in (".cs", ".csproj", ".props", ".targets"):
                bind(source_root/name,original_hash)
                copied = build_dir/variant/"source"/name
                expected = (copies["variants"][variant]["sourceAnalysisSha256"] if name=="Core/AnalysisEngine.cs" else
                            copies["variants"][variant]["sourceProjectSha256"] if name=="MvsAnalyzer.Core/MvsAnalyzer.Core.csproj" else original_hash)
                bind(copied,expected)
        bind(build_dir/variant/"harness"/"Program.cs",build["templateHashes"]["Program.cs"])
        bind(build_dir/variant/"harness"/"BuildIdentity.g.cs")
        identities[variant] = identity
        variants[variant] = {"command": [str(Path(args.dotnet).resolve()), str(publish/"MvsAnalyzer.Core.Tests.dll")],
                             "publishBytes": inventory["totalBytes"], "publishInventory": str(inventory_path)}
    bind(Path(args.dotnet))
    config = {"schema": SCHEMA, "createdUtc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
              "scope":"test-only; production unchanged; scientific NO-GO remains",
              "protocolSha256":PROTOCOL_SHA,"amendmentSha256":AMENDMENT_SHA,
              "referenceDirectory":str(ref_dir),"nativeBuildDirectory":str(build_dir),
              "identities":identities,"variants":variants,
              "bindings":[{"path":p,"sha256":s} for p,s in sorted(bindings.items())],
              "environment":{"versions":VERSIONS,"python":sys.version,"platform":platform.platform(),
                             "machine":platform.machine(),"executable":sys.executable,
                             "variables":{k:os.environ.get(k) for k in ("DOTNET_ROOT","DOTNET_PROCESSOR_COUNT","OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS")}},
              "workload":{"startupPairs":30,"startupSummaryExcludeFirstPair":True,"startupTimeoutSeconds":10,
                          "throughputPairs":30,"throughputWarmupCalls":100000,"throughputMeasuredTotalCalls":100000,
                          "throughputZBits":[bits(z) for z in THROUGHPUT_Z],"throughputTimeoutSeconds":30,
                          "order":"AB then BA alternating","p95":"nearest-rank ceil(.95*n)",
                          "measureStartup":"Popen launch through blocking wait successful exit; independent watchdog",
                          "correctnessTimeoutSeconds":30},
              "thresholds":{"centralAbsolute":"2e-15","normalRelative":"2e-12","normalLog":"2e-12",
                            "subnormalQuanta":8,"improvementMinimum":10,"publishIncrementBytes":10485760,
                            "startupMedianMs":20,"startupMedianFraction":.1,"startupP95Ms":50,
                            "startupP95Fraction":.2,"throughputMedianRatio":1.25},
              "nativeCandidateOutputsRead":False}
    load_references(config)
    write_json(out,config)
    print(json.dumps({"config":str(out),"sha256":sha256(out),"bindings":len(bindings),"nativeInvoked":False}))


def load_references(config: dict) -> tuple[dict,dict,dict]:
    ref_dir = Path(config["referenceDirectory"])
    inputs = read_json(ref_dir/"grid-inputs.json")
    references = read_json(ref_dir/"references.json")
    policy = read_json(ref_dir/"reference-policy-inputs.json")
    validate_reference_grid(inputs,references,policy)
    return inputs,references,policy


def verify_config(config_path: Path) -> dict:
    config = read_json(config_path)
    require(config["schema"] == SCHEMA, "wrong frozen config schema")
    require(config["protocolSha256"] == PROTOCOL_SHA and config["amendmentSha256"] == AMENDMENT_SHA,
            "frozen protocol pins mismatch")
    require({"scipy":scipy.__version__,"numpy":np.__version__,"mpmath":mp.__version__} == VERSIONS,
            "running Python library environment differs from frozen versions")
    require(config["environment"]["variables"] ==
            {k:os.environ.get(k) for k in config["environment"]["variables"]}, "execution environment variables changed")
    verify_bound_files(config["bindings"],config_path.parent)
    return config


def collect_correctness(config: dict, out: Path) -> None:
    require(not (out/"correctness-processes.json").exists(), "correctness evidence already exists")
    ref_dir, raw = Path(config["referenceDirectory"]), out/"raw"
    processes, errors = {}, []
    for mode in ("scalar","rank","policy"):
        input_path = ref_dir/("reference-policy-inputs.json" if mode=="policy" else "grid-inputs.json")
        for variant in ("A","B"):
            name = f"correctness-{mode}-{variant}"
            command = config["variants"][variant]["command"]+[mode,str(input_path)]
            meta = retained_process(command,raw,name,30)
            processes[name] = meta
            write_json(out/"correctness-processes.json",processes)
            if meta["exitCode"] != 0 or meta["timedOut"] or meta["launchError"]:
                errors.append({"name":name,"reason":"native_process_failed","process":meta})
    if errors:
        write_json(out/"blockers.json",errors)
        raise EvidenceError("correctness process failure; all raw failures retained")


def read_correctness(config: dict, out: Path, inputs: dict, policy_inputs: dict) -> tuple[dict,dict,dict]:
    ref_dir, raw = Path(config["referenceDirectory"]), out/"raw"
    processes = read_json(out/"correctness-processes.json")
    require(set(processes) == {f"correctness-{mode}-{v}" for mode in ("scalar","rank","policy") for v in ("A","B")},
            "incomplete correctness process set")
    mode_rows = {"scalar":{},"rank":{},"policy":{}}
    for mode in mode_rows:
        input_path = ref_dir/("reference-policy-inputs.json" if mode=="policy" else "grid-inputs.json")
        expected = (inputs["points"]+inputs["specials"] if mode=="scalar" else
                    inputs["rankCases"] if mode=="rank" else policy_inputs["cases"])
        for variant in ("A","B"):
            name = f"correctness-{mode}-{variant}"
            meta = processes[name]
            require(meta == read_json(raw/f"{name}.process.json"), "process record copy differs")
            require(meta["command"] == config["variants"][variant]["command"]+[mode,str(input_path)],
                    "wrong retained correctness command")
            result = parse_successful_process(meta,raw)
            mode_rows[mode][variant] = validate_native(result,mode,variant,config["identities"][variant],input_path,expected)
    validate_policy_parity(mode_rows["policy"])
    return mode_rows["scalar"],mode_rows["rank"],mode_rows["policy"]


def collect_cost(config: dict, out: Path, scalar: dict, ranks: dict) -> dict:
    require(not (out/"cost-processes.json").exists(), "cost evidence already exists; no partial rerun")
    raw = out/"raw"
    processes = []
    checksum = {v:expected_checksum(scalar[v]) for v in ("A","B")}
    start_p = {v:ranks[v]["mw_n8_separated_original"]["p"]["bits"] for v in ("A","B")}
    # No reference calculations, builds or tests occur inside these two timing runs.
    for mode,timeout in (("startup",10),("throughput",30)):
        for pair in range(30):
            order = ("A","B") if pair%2==0 else ("B","A")
            for variant in order:
                name = f"cost-{mode}-pair{pair:02d}-{variant}"
                meta = retained_process(config["variants"][variant]["command"]+[mode],raw,name,timeout)
                row = {"mode":mode,"pair":pair,"order":"".join(order),"variant":variant,"process":meta,
                       "valid":False,"validationError":None,"batchMs":None}
                try:
                    output = parse_successful_process(meta,raw)
                    row["batchMs"] = validate_performance_output(output,mode,variant,config["identities"][variant],
                                                                  start_p[variant],checksum[variant])
                    row["valid"] = True
                except (EvidenceError,KeyError,TypeError,ValueError) as exc:
                    row["validationError"] = f"{type(exc).__name__}: {exc}"
                processes.append(row)
                write_json(out/"cost-processes.json",processes)
    return summarize_cost(config,out,scalar,ranks)


def summarize_cost(config: dict, out: Path, scalar: dict, ranks: dict) -> dict:
    processes = read_json(out/"cost-processes.json")
    expected = [(m,p,v) for m in ("startup","throughput") for p in range(30) for v in (("A","B") if p%2==0 else ("B","A"))]
    require([(r["mode"],r["pair"],r["variant"]) for r in processes] == expected, "cost process coverage/order mismatch")
    checksum = {v:expected_checksum(scalar[v]) for v in ("A","B")}
    start_p = {v:ranks[v]["mw_n8_separated_original"]["p"]["bits"] for v in ("A","B")}
    times = {m:{"A":[],"B":[]} for m in ("startup","throughput")}
    failures = []
    for row in processes:
        mode,variant,pair = row["mode"],row["variant"],row["pair"]
        name = f"cost-{mode}-pair{pair:02d}-{variant}"
        meta = row["process"]
        require(meta == read_json(out/"raw"/f"{name}.process.json"), "cost raw process metadata mismatch")
        require(meta["command"] == config["variants"][variant]["command"]+[mode], "cost command mismatch")
        try:
            output = parse_successful_process(meta,out/"raw")
            batch = validate_performance_output(output,mode,variant,config["identities"][variant],start_p[variant],checksum[variant])
            require(row["valid"] is True and row["validationError"] is None and row["batchMs"] == batch,
                    "cost validity record disagrees with retained output")
            times[mode][variant].append(meta["wallMs"] if mode=="startup" else batch)
        except (EvidenceError,KeyError,TypeError,ValueError) as exc:
            failures.append({"mode":mode,"pair":pair,"variant":variant,"error":str(exc)})
    if failures:
        result = {"status":"FAIL","pass":False,"failures":failures,
                  "reason":"Missing/invalid observations prohibit selective aggregation; all120 child attempts retained."}
    else:
        result = cost_gates(times["startup"]["A"],times["startup"]["B"],times["throughput"]["A"],times["throughput"]["B"],
                            config["variants"]["A"]["publishBytes"],config["variants"]["B"]["publishBytes"])
        result.update({"status":"PASS" if result["pass"] else "FAIL","failures":[],"observationsMs":times})
    result.update({"processCount":len(processes),"startupPairs":30,"throughputPairs":30,
                   "coldStartClaim":False,"windowsCompatibility":"UNVERIFIED; linux harness only",
                   "scope":"framework-dependent Release linux-x64 harness dependency cost, not Windows application size"})
    return result


def write_scalar_csv(path: Path, scalar: dict) -> None:
    fields = ["id","zBits","z","region","rBits","aBits","bBits","sBits","aAbsoluteError","bAbsoluteError",
              "sAbsoluteError","aRelativeError","bRelativeError","sRelativeError","aLogError","bLogError",
              "sLogError","sDirectLogSfError","bPass","bFailures"]
    with path.open("w",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for row in scalar["rows"]:
            a,b,s = (row["evaluations"][v] for v in ("A","B","S"))
            writer.writerow({"id":row["id"],"zBits":row["zBits"],"z":repr(row["z"]),"region":b["region"],
                "rBits":b["roundedReferenceBits"],"aBits":a["valueBits"],"bBits":b["valueBits"],"sBits":s["valueBits"],
                "aAbsoluteError":a.get("absoluteError"),"bAbsoluteError":b.get("absoluteError"),"sAbsoluteError":s.get("absoluteError"),
                "aRelativeError":a.get("relativeError"),"bRelativeError":b.get("relativeError"),"sRelativeError":s.get("relativeError"),
                "aLogError":a.get("absoluteLogError"),"bLogError":b.get("absoluteLogError"),"sLogError":s.get("absoluteLogError"),
                "sDirectLogSfError":s.get("directLogSfAbsoluteError"),"bPass":b["pass"],"bFailures":";".join(b["failures"])})


def summarize_results(config: dict, scalar: dict, ranks: dict, cost: dict | None) -> dict:
    decision_rows = scalar["decisions"]+ranks["decisions"]
    regions = {}
    for row in scalar["rows"]:
        region = row["evaluations"]["B"]["region"]
        group = regions.setdefault(region,{"count":0,"A_fails":0,"B_fails":0,"S_fails":0})
        group["count"] += 1
        for variant in ("A","B","S"):
            group[f"{variant}_fails"] += not row["evaluations"][variant]["pass"]
    decisions = {"thresholdCount":len(scalar["decisions"]),
        "thresholdCandidateMismatchCount":sum(not d["candidateMatchesPolicy"] for d in scalar["decisions"]),
        "rankDiagnosticCount":len(ranks["decisions"]),
        "rankCandidateMismatchCount":sum(not d["candidateMatchesPolicy"] for d in ranks["decisions"]),
        "changedCount":sum(d["changed"] for d in decision_rows),
        "changedClassificationCounts":{c:sum(d["changed"] and d["classification"]==c for d in decision_rows)
                                       for c in ("improving","worsening","both_incorrect","unresolved")},
        "policyRoundingDiscrepancyCount":sum(d["policyRoundingDiscrepancy"] for d in decision_rows)}
    correctness_pass = scalar["pass"] and ranks["pass"]
    acceptance = ("NO-GO" if not correctness_pass else "PENDING_COST" if cost is None else
                  "REQUIRES_SEPARATE_ENGINEERING_DECISION" if not cost["pass"] else
                  "ELIGIBLE_FOR_SEPARATE_IMPLEMENTATION_PROPOSAL")
    return {"schema":SCHEMA,"candidateOutcome":acceptance,"scientificStatus":"NO-GO unchanged",
            "productionActivated":False,"candidateNumericalAndDecisionPass":correctness_pass,
            "numericFailureIsTerminalInformativeOutcome":True,
            "counts":{"scalar":len(scalar["rows"]),"specials":len(scalar["specials"]),"ranks":len(ranks["rows"])},
            "scalarRegions":regions,"scalarChecks":scalar["checks"],
            "scalarCandidateFailureCount":len(scalar["candidateFailures"]),
            "rankFailureCount":len(ranks["failures"]),"rankFailures":ranks["failures"],
            "centralMaxAbsoluteError":scalar["centralMaxAbsoluteError"],
            "prematureZeroCounts":{v:len(scalar["prematureZeros"][v]) for v in ("A","B")},
            "monotonicityViolationCount":len(scalar["monotonicityViolations"]),"decisions":decisions,
            "cost":cost if cost is not None else {"status":"UNMEASURED","pass":None},
            "compatibility":{"Windows":"UNVERIFIED; deliberately deferred", "measuredPublication":"linux-x64 harness only"},
            "referenceDiagnostic":{"scipyFailureCount":len(scalar["scipyDiagnosticFailureIds"]),
                "explanation":"S/H disagreements are retained, never resolved by majority vote. Separate direct norm.logsf is diagnostic, not a replacement for log(returned p)."},
            "provenance":{"protocolSha256":config["protocolSha256"],"amendmentSha256":config["amendmentSha256"],
                          "sourceTreeSha256":config["identities"]["A"]["sourceTreeSha256"],
                          "formulaVersion":config["identities"]["A"]["formulaVersion"],
                          "formulaHash":config["identities"]["A"]["formulaHash"]}}


def write_report(out: Path, summary: dict, scalar: dict, ranks: dict) -> None:
    lines = ["# Round32 isolated normal-tail experiment", "", f"Candidate outcome: **{summary['candidateOutcome']}**.",
             "Scientific status: **NO-GO unchanged**. Production remains unchanged; this experiment cannot activate B.", "",
             "## Fixed evidence", "", f"- Scalar inputs: {summary['counts']['scalar']}; domain specials: {summary['counts']['specials']}; actual native rank cases: {summary['counts']['ranks']}.",
             f"- Candidate scalar failures: {summary['scalarCandidateFailureCount']}; rank failures: {summary['rankFailureCount']}.",
             f"- Threshold B/reference-policy mismatches: {summary['decisions']['thresholdCandidateMismatchCount']} of {summary['decisions']['thresholdCount']}.",
             f"- A/B changed decisions: {summary['decisions']['changedCount']}; every change is retained in changed-decisions.json.",
             f"- Policy/mathematical rounding discrepancies: {summary['decisions']['policyRoundingDiscrepancyCount']}.",
             f"- Premature zeros: A={summary['prematureZeroCounts']['A']}, B={summary['prematureZeroCounts']['B']}.",
             f"- Candidate monotonicity violations: {summary['monotonicityViolationCount']}.", "", "## Candidate criteria", ""]
    lines.extend(f"- {'PASS' if value else 'FAIL'}: {name}" for name,value in summary["scalarChecks"].items())
    lines += [f"- {'PASS' if ranks['pass'] else 'FAIL'}: native rank regression, strict end-to-end accuracy, declared policies, KW bitwise control and deterministic transformations.",
              "", "## Central absolute error", "",
              f"- Maximum A error: {summary['centralMaxAbsoluteError']['A']}",
              f"- Maximum B error: {summary['centralMaxAbsoluteError']['B']}",
              f"- Improvement factor: {summary['centralMaxAbsoluteError']['improvementFactor']}",
              "", "## Cost", "", f"Status: {summary['cost']['status']}."]
    cost = summary["cost"]
    if "checks" in cost:
        lines.extend(f"- {'PASS' if value else 'FAIL'}: {name}" for name,value in cost["checks"].items())
        lines += [f"- Publish increment: {cost['publishBytes']['increment']} bytes.",
                  f"- Startup median A/B: {cost['startup']['A']['medianMs']:.6f}/{cost['startup']['B']['medianMs']:.6f} ms.",
                  f"- Startup nearest-rank p95 A/B: {cost['startup']['A']['p95Ms']:.6f}/{cost['startup']['B']['p95Ms']:.6f} ms.",
                  f"- Throughput median B / median A: {cost['throughput']['medianBOverMedianA']:.9f}."]
    lines += ["", "Startup uses 30 fresh paired launches in alternating AB/BA order; first pair retained and excluded from n=29 summaries. Each of the separate 30 throughput pairs uses fresh processes, 100,000 warmup and 100,000 measured total calls. p95 uses nearest rank. These are warm-file-cache repeated launches, not a cold-start claim.",
              "", "## Interpretation and retained failures", "",
              "A invokes the actual private NormalCdf; native MW is called in both variants. B changes one final return expression in an external source copy. Native internal z is not observed. Exact-rank mathematical z and rounded independent z are distinct reference diagnostics; discrepancies never justify wider tolerances.",
              "", "SciPy ordinary p and separate logsf diagnostics are retained independently. Direct logsf is not substituted for the strict log of returned p gate. High precision is independently saved at 100 and 200 decimal digits, with explicit nearest-even binary64 conversion. Maximum finite and +infinity are separate domain/underflow checks.",
              "", "Signed zeros remain separate. Actual A zero values are preserved; exact-at-zero is a B acceptance criterion. Every threshold-neighborhood candidate decision is checked against the actual unchanged DecisionPolicy fed rounded H, including unchanged but incorrect A/B decisions.",
              "", "Windows compatibility is UNVERIFIED. Publication measurements are for the isolated framework-dependent Release linux-x64 harness, not the Windows application. Numerical failure is an informative terminal outcome; no tuning, threshold changes or selective retries are authorized.",
              "", "## Artifacts", "", "- scalar-results.json and scalar-results.csv: every point, bits, H/S/native errors and failures.",
              "- rank-results.json: every native MW/KW case, frozen regression and transformations.",
              "- decisions.json and changed-decisions.json: raw/adjusted values, actual policies, mathematical decisions and classifications.",
              "- cost-processes.json, cost-results.json and raw/: retained stdout/stderr, exits, timeouts, wall time and batch checksums.",
              "- frozen-config.json: exact bindings, algorithms, versions and workload settings."]
    (out/"report.md").write_text("\n".join(lines)+"\n")


def analyze(config: dict, out: Path) -> dict:
    inputs,references,policy_inputs = load_references(config)
    scalar_native,rank_native,policies = read_correctness(config,out,inputs,policy_inputs)
    scalar = compare_scalar(inputs,references,scalar_native,policies)
    ranks = compare_ranks(inputs,references,rank_native,policies)
    cost = summarize_cost(config,out,scalar_native,rank_native) if (out/"cost-processes.json").exists() else None
    write_json(out/"scalar-results.json",scalar)
    write_scalar_csv(out/"scalar-results.csv",scalar)
    write_json(out/"rank-results.json",ranks)
    decisions = scalar["decisions"]+ranks["decisions"]
    write_json(out/"decisions.json",decisions)
    write_json(out/"changed-decisions.json",[d for d in decisions if d["changed"]])
    if cost is not None:
        write_json(out/"cost-results.json",cost)
    summary = summarize_results(config,scalar,ranks,cost)
    write_json(out/"summary.json",summary)
    write_report(out,summary,scalar,ranks)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action",required=True)
    prepare = sub.add_parser("prepare",help="Freeze configuration only; never invoke candidates")
    prepare.add_argument("--config",required=True)
    prepare.add_argument("--native-build-dir",required=True)
    prepare.add_argument("--reference-dir",required=True)
    prepare.add_argument("--protocol",required=True)
    prepare.add_argument("--amendment",required=True)
    prepare.add_argument("--dotnet",required=True)
    for name in ("verify","correctness","cost","analyze"):
        child = sub.add_parser(name)
        child.add_argument("--config",required=True)
        child.add_argument("--config-sha256",required=True,help="Externally recorded freeze hash")
        if name != "verify":
            child.add_argument("--output",required=True)
        if name in ("correctness","cost"):
            child.add_argument("--execute",action="store_true",help="Explicitly invoke reviewed native candidates")
        if name == "cost":
            child.add_argument("--exclusive-cpu-slot",action="store_true",help="Lead confirms all builds/heavy tests stopped")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            prepare_config(args)
            return 0
        config_path = Path(args.config).resolve()
        require(sha256(config_path) == args.config_sha256,"externally recorded config SHA mismatch")
        config = verify_config(config_path)
        if args.action == "verify":
            load_references(config)
            print(json.dumps({"verified":True,"nativeInvoked":False,"configSha256":args.config_sha256}))
            return 0
        out = Path(args.output).resolve()
        if args.action == "correctness":
            require(args.execute,"candidate invocation requires explicit --execute and lead GO")
            require(not out.exists(),"correctness output directory must not exist")
            out.mkdir(parents=True)
            write_json(out/"frozen-config.json",config)
            write_json(out/"run-binding.json",{"configSha256":args.config_sha256,"configPath":str(config_path)})
            load_references(config)
            collect_correctness(config,out)
        else:
            require(read_json(out/"run-binding.json")["configSha256"] == args.config_sha256,"run/config binding mismatch")
            require(read_json(out/"frozen-config.json") == config,"run frozen config changed")
        if args.action == "cost":
            require(args.execute and args.exclusive_cpu_slot,"cost requires explicit execution and exclusive CPU slot")
            inputs,_,policy = load_references(config)
            scalar,ranks,_ = read_correctness(config,out,inputs,policy)
            collect_cost(config,out,scalar,ranks)
        summary = analyze(config,out)
        print(json.dumps({"summary":str(out/"summary.json"),"candidateOutcome":summary["candidateOutcome"],
                          "scalarFailureCount":summary["scalarCandidateFailureCount"],
                          "thresholdDecisionMismatchCount":summary["decisions"]["thresholdCandidateMismatchCount"],
                          "rankFailureCount":summary["rankFailureCount"],"costStatus":summary["cost"]["status"]}))
        return 0
    except (EvidenceError,KeyError,TypeError,ValueError,OSError) as exc:
        error = {"status":"BLOCKED","error":f"{type(exc).__name__}: {exc}","candidateOutcome":"NO_RECOMMENDATION",
                 "scientificStatus":"NO-GO unchanged","rawFailuresPreserved":True}
        if getattr(args,"output",None) and Path(args.output).is_dir():
            write_json(Path(args.output)/"execution-blocker.json",error)
        print(json.dumps(error),file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
