#!/usr/bin/env python3
"""Reproduce a versioned exported MVS score and explore its weight sensitivity.

Current runs require run_manifest.json (auto-detected beside results.csv).
Without a manifest, select a formula and its parameters explicitly. Historical
five-component analysis is opt-in and is not a verification of the current engine.
Only numpy is required. Rank diagnostics use average ranks and Kendall tau-b.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

FORMULA_VERSION = "MVS-1.4.0"
FORMULA_SHA256 = "10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c"
LEGACY_FORMULA = "legacy-five-component"
CURRENT = np.array([0.5, 0.5])
LEGACY_WEIGHTS = np.array([0.30, 0.25, 0.20, 0.15, 0.10])


def false_alarm_component(fpr: float, local_alpha: float) -> float:
    """Current formula uses local_alpha = alpha / fixed registry family size."""
    return math.exp(-max(0.0, fpr - local_alpha) / local_alpha)


def resolve_formula(results, manifest=None, formula=None, alpha=None, family_size=None):
    """Return (formula, alpha, family_size, provenance); never guess run settings."""
    candidate = Path(manifest) if manifest else Path(results).with_name("run_manifest.json")
    if manifest or candidate.exists():
        with candidate.open(encoding="utf-8-sig") as fh:
            doc = json.load(fh)
        try:
            spec = doc["formula"]
            version = spec["version"]
            specification = spec["specification"]
            digest = spec["hash"]
            decision = doc["decision"]
            run_alpha = decision["alpha"]
            run_size = decision["familySize"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Incomplete formula/decision metadata in run manifest") from exc
        if version != FORMULA_VERSION or digest != FORMULA_SHA256:
            raise ValueError(f"Unsupported formula: {version!r}; this is not evidence of a bad export")
        if not isinstance(specification, str) or hashlib.sha256(specification.encode()).hexdigest() != digest:
            raise ValueError("Formula specification/hash mismatch in manifest")
        validate_parameters(run_alpha, run_size)
        calibration_alpha = doc.get("calibration", {}).get("alpha", run_alpha)
        if calibration_alpha != run_alpha:
            raise ValueError("Calibration and decision alpha disagree")
        if "files" in doc:
            records = doc["files"]
            if not isinstance(records, list):
                raise ValueError("Manifest files must be a list")
            matches = [r for r in records if isinstance(r, dict) and r.get("FileName") == Path(results).name]
            if len(matches) != 1 or matches[0].get("sha256") != hashlib.sha256(Path(results).read_bytes()).hexdigest():
                raise ValueError("Results CSV does not match its manifest file checksum")
        if formula is not None and formula != version:
            raise ValueError("Explicit formula disagrees with manifest")
        if alpha is not None and alpha != run_alpha:
            raise ValueError("Explicit alpha disagrees with manifest")
        if family_size is not None and family_size != run_size:
            raise ValueError("Explicit family size disagrees with manifest")
        return version, run_alpha, run_size, f"manifest: {candidate}"
    if formula is None or alpha is None:
        raise ValueError("No manifest: provide --formula and --alpha explicitly")
    if formula not in (FORMULA_VERSION, LEGACY_FORMULA):
        raise ValueError(f"Unsupported formula: {formula!r}")
    if formula == FORMULA_VERSION and family_size is None:
        raise ValueError("Current formula without a manifest also requires --family-size")
    if formula == LEGACY_FORMULA and family_size is not None:
        raise ValueError("Historical five-component formula uses alpha, not alpha/family-size")
    validate_parameters(alpha, family_size if formula == FORMULA_VERSION else 1)
    return formula, alpha, family_size, "explicit parameters; run metadata unverified"


def validate_parameters(alpha, family_size):
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and strictly between 0 and 1")
    if isinstance(family_size, bool) or not isinstance(family_size, int) or family_size < 1:
        raise ValueError("family size must be a positive integer")


def read_results(path: str, alpha: float, family_size: int | None = None,
                 formula: str = FORMULA_VERSION):
    if formula == FORMULA_VERSION:
        validate_parameters(alpha, family_size)
        local_alpha = alpha / family_size
        if local_alpha == 0:
            raise ValueError("alpha/family-size underflows to zero")
    elif formula == LEGACY_FORMULA:
        validate_parameters(alpha, 1)
        local_alpha = alpha
    else:
        raise ValueError(f"Unsupported formula: {formula!r}")
    metrics, comps, reported = [], [], []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"metric", "calibrated_power", "calibrated_fpr", "mvs_score"}
        if formula == LEGACY_FORMULA:
            required.update(("robustness", "repeatability", "coverage"))
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        for line, row in enumerate(reader, 2):
            raw_status = row.get("applicable", "true")
            if not isinstance(raw_status, str):
                raise ValueError(f"Row {line}: missing applicable status")
            status = raw_status.strip().lower()
            if status in ("false", "0"):
                continue
            if status not in ("true", "1"):
                raise ValueError(f"Row {line}: invalid applicable status")
            keys = ["calibrated_power", "calibrated_fpr", "mvs_score"]
            if formula == LEGACY_FORMULA:
                keys += ["robustness", "repeatability", "coverage"]
            try:
                values = [float(row[k]) for k in keys]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Row {line}: missing or invalid numerical value") from exc
            if not all(math.isfinite(v) for v in values):
                raise ValueError(f"Row {line}: nonfinite numerical value")
            power, fpr, score = values[:3]
            if not 0 <= score <= 100 or any(not 0 <= v <= 1 for v in [power, fpr] + values[3:]):
                raise ValueError(f"Row {line}: component or score outside its valid range")
            name = (row["metric"] or "").strip()
            if not name or name in metrics:
                raise ValueError(f"Row {line}: empty or duplicate metric")
            metrics.append(name)
            comps.append([power, false_alarm_component(fpr, local_alpha)] + values[3:])
            reported.append(score)
    if not metrics:
        raise ValueError("No usable applicable rows in results CSV")
    return metrics, np.array(comps), np.array(reported)


def score_with(weights: np.ndarray, comps: np.ndarray, *, legacy: bool = False) -> np.ndarray:
    """Weighted geometric mean; current zero components give exactly zero."""
    weights, comps = np.asarray(weights, dtype=float), np.asarray(comps, dtype=float)
    if comps.ndim != 2 or weights.ndim != 1 or comps.shape[1] != len(weights):
        raise ValueError("Weight and component dimensions disagree")
    if not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError("Weights must be finite, nonnegative and sum to one")
    if not np.isfinite(comps).all() or (comps < 0).any() or (comps > 1).any():
        raise ValueError("Components must be finite and between zero and one")
    active = weights > 0
    safe = np.clip(comps[:, active], 1e-9, None) if legacy else comps[:, active]
    with np.errstate(divide="ignore"):
        scores = 100.0 * np.exp(np.log(safe) @ weights[active])
    if not legacy:
        scores[np.any(comps[:, active] == 0, axis=1)] = 0
    return scores


def average_ranks(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Ranks require a finite one-dimensional array")
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + 1 + j) / 2
        i = j
    return ranks


def rank_inputs(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or b.ndim != 1 or a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Rank diagnostics require equal-length finite vectors")
    return a, b


def kendall_tau(a: np.ndarray, b: np.ndarray) -> float:
    """Kendall tau-b, including ties in the denominator."""
    a, b = rank_inputs(a, b)
    con = dis = ties_a = ties_b = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            da, db = np.sign(a[i] - a[j]), np.sign(b[i] - b[j])
            if da == 0 and db == 0:
                continue
            if da == 0:
                ties_a += 1
            elif db == 0:
                ties_b += 1
            elif da == db:
                con += 1
            else:
                dis += 1
    denom = math.sqrt((con + dis + ties_a) * (con + dis + ties_b))
    return (con - dis) / denom if denom else float("nan")


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    a, b = rank_inputs(a, b)
    if len(a) < 2:
        return float("nan")
    ra, rb = average_ranks(a), average_ranks(b)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt(float((ra * ra).sum() * (rb * rb).sum()))
    return float((ra * rb).sum() / denom) if denom else float("nan")


def rank_order_centroid(n: int) -> np.ndarray:
    return np.array([sum(1.0 / k for k in range(i + 1, n + 1)) / n for i in range(n)])


def top_names(metrics, scores):
    return ", ".join(metrics[i] for i in np.flatnonzero(scores == scores.max()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", help="path to results.csv")
    ap.add_argument("--manifest", help="defaults to sibling run_manifest.json when present")
    ap.add_argument("--formula", choices=(FORMULA_VERSION, LEGACY_FORMULA))
    ap.add_argument("--alpha", type=float, help="explicit alpha if no manifest; otherwise must match")
    ap.add_argument("--family-size", type=int, help="fixed registry size, never inferred from usable rows")
    ap.add_argument("--draws", type=int, default=5000)
    ap.add_argument("--concentration", type=float, default=50.0)
    ap.add_argument("--seed", type=int, default=20260823)
    args = ap.parse_args()
    if args.draws < 1 or not math.isfinite(args.concentration) or args.concentration <= 0 or args.seed < 0:
        ap.error("draws and concentration must be positive; seed must be nonnegative")
    try:
        formula, alpha, size, provenance = resolve_formula(
            args.results, args.manifest, args.formula, args.alpha, args.family_size)
        metrics, comps, reported = read_results(args.results, alpha, size, formula)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    legacy = formula == LEGACY_FORMULA
    weights = LEGACY_WEIGHTS if legacy else CURRENT
    recomputed = score_with(weights, comps, legacy=legacy)
    worst = float(np.max(np.abs(recomputed - reported)))
    print(f"# Score diagnostics — {Path(args.results).name}\n")
    print(f"Formula: {formula}; alpha: {alpha}; family size: {size}; metrics: {len(metrics)}")
    print(f"Parameters: {provenance}\n")
    print("## 1. Formula reproduction\n")
    print(f"Largest |recomputed - reported|: {worst:.6f}")
    print("Formula check: " + ("PASS" if worst <= 0.01 else "FAIL"))
    print("Tolerance 0.01 score units. A hash checks identity, not scientific validity.\n")
    print("## 2. Exploratory weighting schemes\n")
    print("Alternative weights are sensitivity diagnostics, not a proposed change to the frozen formula.\n")
    schemes = {"published weights": weights, "equal weights": np.full(len(weights), 1 / len(weights)),
               "rank-order centroid": rank_order_centroid(len(weights)),
               "power only": np.array([1.0] + [0.0] * (len(weights) - 1))}
    print("| Scheme | Top metrics including ties | Kendall tau-b vs published |")
    print("|---|---|---|")
    for label, w in schemes.items():
        s = score_with(w, comps, legacy=legacy)
        print(f"| {label} | {top_names(metrics, s)} | {kendall_tau(recomputed, s):+.3f} |")
    print("\n## 3. Dirichlet weight sensitivity\n")
    rng = np.random.default_rng(args.seed)
    draws = rng.dirichlet(weights * args.concentration, size=args.draws)
    scores = np.array([score_with(w, comps, legacy=legacy) for w in draws])
    base_top = recomputed == recomputed.max()
    tops = scores == scores.max(axis=1, keepdims=True)
    overlap = np.mean(np.any(tops[:, base_top], axis=1))
    print(f"Draws: {args.draws}; concentration: {args.concentration}")
    print(f"At least one published top metric remains tied for top: {100 * overlap:.1f}%")
    ranks = np.array([average_ranks(-s) for s in scores])
    current_ranks = average_ranks(-recomputed)
    print("\n| Metric | Published average rank | Rank range | Share tied for top |")
    print("|---|---|---|---|")
    for i in np.argsort(-recomputed, kind="stable"):
        print(f"| {metrics[i]} | {current_ranks[i]:g} | {ranks[:, i].min():g}-{ranks[:, i].max():g} | {100 * tops[:, i].mean():.1f}% |")
    print("\n## 4. Association with power\n")
    print(f"Spearman(score, power): {spearman(recomputed, comps[:, 0]):+.3f}")
    print(f"Kendall tau-b(score, power): {kendall_tau(recomputed, comps[:, 0]):+.3f}")
    print("nan means an undefined diagnostic, including constant inputs.")
    print("Association describes this run; it does not establish general validity or redundancy.")
    if worst > 0.01:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
