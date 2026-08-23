#!/usr/bin/env python3
"""Weight-sensitivity and discriminant-validity analysis of a finished run.

Usage:
    python3 validation/analyze_results.py path/to/results.csv [--draws 5000]

Point it at the `results.csv` of any run the app has already produced. It does
not touch the app, does not need the app to change, and does not need the raw
data -- `results.csv` already contains every component of the score.

It answers three questions that were asked of the project and could not be
answered by argument:

1. Does the reported MVS score follow from the published formula? (parse check)
2. How much of the ranking is the data, and how much is the weight vector?
   Reported as top-1 stability, pairwise rank-flip rate and Kendall's tau
   against alternative weighting schemes, including a Dirichlet cloud around
   the current weights. This is the uncertainty-analysis step of the OECD/JRC
   composite-indicator protocol.
3. Is the composite doing any work that power alone does not already do?
   Reported as the correlation between the score and the power component.

Only numpy is required.
"""

from __future__ import annotations

import argparse
import csv
import math
import os

import numpy as np

COMPONENTS = ["power", "false_alarm", "robustness", "repeatability", "coverage"]
CURRENT = np.array([0.30, 0.25, 0.20, 0.15, 0.10])
ALPHA_DEFAULT = 0.05


def false_alarm_component(fpr: float, alpha: float) -> float:
    """F = exp(-max(0, FPR - alpha) / alpha), exactly as in the frozen formula."""
    return math.exp(-max(0.0, fpr - alpha) / alpha)


def read_results(path: str, alpha: float):
    metrics, comps, reported = [], [], []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row.get("applicable", "true").strip().lower() in ("false", "0"):
                continue
            try:
                power = float(row["calibrated_power"])
                fpr = float(row["calibrated_fpr"])
                rob = float(row["robustness"])
                rep = float(row["repeatability"])
                cov = float(row["coverage"])
                score = float(row["mvs_score"])
            except (KeyError, ValueError):
                continue
            metrics.append(row["metric"])
            comps.append([power, false_alarm_component(fpr, alpha), rob, rep, cov])
            reported.append(score)
    if not metrics:
        raise SystemExit("No usable rows. Is this a results.csv from a finished run?")
    return metrics, np.array(comps), np.array(reported)


def score_with(weights: np.ndarray, comps: np.ndarray) -> np.ndarray:
    safe = np.clip(comps, 1e-9, None)
    return 100.0 * np.exp(np.log(safe) @ weights)


def kendall_tau(a: np.ndarray, b: np.ndarray) -> float:
    n = len(a)
    con = dis = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = np.sign(a[i] - a[j]) * np.sign(b[i] - b[j])
            if s > 0:
                con += 1
            elif s < 0:
                dis += 1
    total = con + dis
    return (con - dis) / total if total else float("nan")


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(-a)).astype(float)
    rb = np.argsort(np.argsort(-b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt(float((ra * ra).sum() * (rb * rb).sum()))
    return float((ra * rb).sum() / denom) if denom else float("nan")


def rank_order_centroid(n: int) -> np.ndarray:
    """ROC weights for n criteria ranked most- to least-important. Uses only the
    ORDER of the components, not their magnitudes -- the standard check for
    'do the exact numbers matter, or only their ranking?'"""
    return np.array([sum(1.0 / k for k in range(i + 1, n + 1)) / n for i in range(n)])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="path to results.csv")
    ap.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    ap.add_argument("--draws", type=int, default=5000)
    ap.add_argument("--concentration", type=float, default=50.0,
                    help="Dirichlet concentration; lower = wider disagreement")
    ap.add_argument("--seed", type=int, default=20260823)
    args = ap.parse_args()

    metrics, comps, reported = read_results(args.results, args.alpha)
    recomputed = score_with(CURRENT, comps)
    worst = float(np.max(np.abs(recomputed - reported)))

    print(f"# Weight sensitivity — {os.path.basename(args.results)}\n")
    print(f"Metrics analysed: {len(metrics)}   alpha: {args.alpha}\n")
    print("## 1. Formula reproduction\n")
    print(f"Largest |recomputed - reported| score difference: {worst:.4f}")
    print("(Anything above ~0.01 means the exported components do not reproduce")
    print(" the exported score, which is a bug worth reporting.)\n")

    order_current = np.argsort(-recomputed)
    top_current = metrics[int(order_current[0])]

    print("## 2. Alternative weighting schemes\n")
    schemes = {
        "current 0.30/0.25/0.20/0.15/0.10": CURRENT,
        "equal 0.20 each": np.full(5, 0.2),
        "rank-order centroid": rank_order_centroid(5),
        "power only": np.array([1.0, 0.0, 0.0, 0.0, 0.0]),
        "false-alarm first": np.array([0.25, 0.40, 0.15, 0.10, 0.10]),
    }
    print("| Scheme | Top-1 metric | Kendall tau vs current |")
    print("|---|---|---|")
    for label, w in schemes.items():
        s = score_with(w, comps)
        tau = kendall_tau(recomputed, s)
        print(f"| {label} | {metrics[int(np.argmax(s))]} | {tau:+.3f} |")

    arith = 100.0 * (comps @ CURRENT)
    print(f"| arithmetic instead of geometric mean | {metrics[int(np.argmax(arith))]} "
          f"| {kendall_tau(recomputed, arith):+.3f} |")
    print()

    print("## 3. Dirichlet cloud around the current weights\n")
    rng = np.random.default_rng(args.seed)
    draws = rng.dirichlet(CURRENT * args.concentration, size=args.draws)
    scores = np.array([score_with(w, comps) for w in draws])
    tops = np.argmax(scores, axis=1)
    stability = float(np.mean(tops == order_current[0]))
    taus = np.array([kendall_tau(recomputed, s) for s in scores[: min(500, args.draws)]])

    n = len(metrics)
    base_sign = np.sign(recomputed[:, None] - recomputed[None, :])
    flips = 0
    pairs = 0
    for s in scores[: min(500, args.draws)]:
        sign = np.sign(s[:, None] - s[None, :])
        iu = np.triu_indices(n, 1)
        flips += int(np.sum(sign[iu] != base_sign[iu]))
        pairs += len(iu[0])

    print(f"Draws: {args.draws}, concentration: {args.concentration}")
    print(f"Top-1 metric unchanged in **{stability * 100:.1f} %** of draws "
          f"(current top-1: {top_current})")
    print(f"Mean Kendall tau vs current ranking: {taus.mean():+.3f} "
          f"(min {taus.min():+.3f})")
    print(f"Pairwise rank-flip rate: {flips / pairs * 100:.1f} %\n")

    ranks = np.argsort(np.argsort(-scores, axis=1), axis=1) + 1
    print("| Metric | current rank | rank range over draws | share of draws at rank 1 |")
    print("|---|---|---|---|")
    for i in np.argsort(-recomputed):
        col = ranks[:, i]
        print(f"| {metrics[i]} | {int(np.where(order_current == i)[0][0]) + 1} "
              f"| {col.min()}-{col.max()} | {np.mean(col == 1) * 100:.1f} % |")
    print()

    print("## 4. Discriminant validity\n")
    power = comps[:, 0]
    print(f"Spearman(score, power component): {spearman(recomputed, power):+.3f}")
    print(f"Kendall(score, power component):  {kendall_tau(recomputed, power):+.3f}")
    print("\nIf these sit at or above ~0.95, the composite is a relabelled power")
    print("column on this dataset and the other four components are decoration.")


if __name__ == "__main__":
    main()
