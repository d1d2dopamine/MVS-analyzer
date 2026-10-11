#!/usr/bin/env python3
"""Independent simulation diagnostics for the active twelve-metric registry.

Usage: python validation/reference_simulation.py [replications] [primary|discriminating]
       [--output-dir DIRECTORY]

Protocol MVS-REFERENCE-2: sample SD, linear quantiles, floor(0.2*n) trimming,
absolute/guarded relative denominators, per-entity geometric-mean availability.
Tests use tie-corrected asymptotic Mann-Whitney with continuity correction.
Unavailable tests count as non-rejections; their availability is reported.
Both unadjusted any-of-twelve and fixed twelve-test Bonferroni are diagnostics.
Monte Carlo estimates are not population truth or independent certification of
the C# engine. This implementation does not import or invoke that engine.
Only numpy is required. Reports use v2 filenames and preserve historical reports.
"""

from __future__ import annotations

import argparse
import os
from statistics import NormalDist

import numpy as np

import dgp

SIM_SEED = 20260823
ALPHA = 0.05
PROTOCOL = "MVS-REFERENCE-2"
FAMILY_SIZE = 12
MIN_ENTITIES = 4
Z_CRIT = NormalDist().inv_cdf(1 - ALPHA / 2)
Z_BONFERRONI = NormalDist().inv_cdf(1 - ALPHA / (2 * FAMILY_SIZE))
HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# Entity-level reductions. Each takes (entities, reps) and returns (entities,).
# Definitions follow docs/METHODS.md.
# --------------------------------------------------------------------------
def _median(x):
    return np.median(x, axis=1)


def _mean(x):
    return np.mean(x, axis=1)


def _rms(x):
    return np.sqrt(np.mean(x * x, axis=1))


def _sd(x):
    return np.std(x, axis=1, ddof=1)


def _relative(numerator, denominator, x):
    # Double.Epsilon in C# is the smallest positive subnormal, not machine eps.
    tolerance = np.maximum(np.nextafter(0.0, 1.0), np.max(np.abs(x), axis=1) * 1e-12)
    out = np.full(x.shape[0], np.nan)
    np.divide(numerator, np.abs(denominator), out=out,
              where=np.abs(denominator) > tolerance)
    return out


def _cv(x):
    return _relative(_sd(x), _mean(x), x)


def _mad(x):
    med = np.median(x, axis=1, keepdims=True)
    return np.median(np.abs(x - med), axis=1)


def _iqr(x):
    return np.percentile(x, 75, axis=1) - np.percentile(x, 25, axis=1)


def _norm_mad(x):
    return _relative(_mad(x), _median(x), x)


def _norm_iqr(x):
    return _relative(_iqr(x), _median(x), x)


def _range(x):
    return np.max(x, axis=1) - np.min(x, axis=1)


def _geomean(x):
    valid = np.all(np.isfinite(x) & (x > 0), axis=1)
    out = np.full(x.shape[0], np.nan)
    out[valid] = np.exp(np.mean(np.log(x[valid]), axis=1))
    return out


def _trimmed20(x):
    s = np.sort(x, axis=1)
    k = int(np.floor(0.20 * x.shape[1]))
    return np.mean(s[:, k: x.shape[1] - k], axis=1) if x.shape[1] - 2 * k > 0 else _mean(x)


METRICS = {
    "median": _median,
    "standard_deviation": _sd,
    "coefficient_of_variation": _cv,
    "mad": _mad,
    "iqr": _iqr,
    "normalized_mad": _norm_mad,
    "normalized_iqr": _norm_iqr,
    "mean": _mean,
    "rms": _rms,
    "range": _range,
    "geometric_mean": _geomean,
    "trimmed_mean_20": _trimmed20,
}


# --------------------------------------------------------------------------
# Two-sided Mann-Whitney U, vectorised over replications.
# a, b have shape (reps, n1) and (reps, n2). Returns |z| per replication.
# --------------------------------------------------------------------------
def mannwhitney_absz(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Tie-corrected normal |z|; all-tied inputs have z=0 (p=1)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if (a.ndim != 2 or b.ndim != 2 or a.shape[0] != b.shape[0]
            or not a.shape[1] or not b.shape[1]
            or not np.isfinite(a).all() or not np.isfinite(b).all()):
        raise ValueError("Mann-Whitney inputs must be finite nonempty groups with equal replication counts")
    n1, n2 = a.shape[1], b.shape[1]
    total = n1 + n2
    both = np.concatenate([a, b], axis=1)
    order = np.argsort(both, axis=1, kind="stable")
    sorted_values = np.take_along_axis(both, order, axis=1)
    sorted_ranks = np.broadcast_to(np.arange(1, total + 1, dtype=float), both.shape).copy()
    tie_sum = np.zeros(a.shape[0])
    # Continuous rows retain the fast vectorized path; only tied rows need runs.
    tied_rows = np.flatnonzero(np.any(np.diff(sorted_values, axis=1) == 0, axis=1))
    for row in tied_rows:
        starts = np.r_[0, np.flatnonzero(np.diff(sorted_values[row]) != 0) + 1]
        ends = np.r_[starts[1:], total]
        for start, end in zip(starts, ends):
            count = end - start
            if count > 1:
                sorted_ranks[row, start:end] = (start + 1 + end) / 2
                tie_sum[row] += count ** 3 - count
    ranks = np.empty_like(sorted_ranks)
    np.put_along_axis(ranks, order, sorted_ranks, axis=1)
    u1 = ranks[:, :n1].sum(axis=1) - n1 * (n1 + 1) / 2
    variance = n1 * n2 / 12 * (total + 1 - tie_sum / (total * (total - 1)))
    numerator = np.maximum(np.abs(u1 - n1 * n2 / 2) - 0.5, 0)
    z = np.zeros(a.shape[0])
    np.divide(numerator, np.sqrt(np.maximum(variance, 0)), out=z, where=variance > 0)
    return z


def metric_test_z(a, b):
    """Filter unavailable entity values separately in each replication/group."""
    available = ((np.isfinite(a).sum(axis=1) >= MIN_ENTITIES)
                 & (np.isfinite(b).sum(axis=1) >= MIN_ENTITIES))
    z = np.full(a.shape[0], np.nan)
    complete = available & np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    if complete.any():
        z[complete] = mannwhitney_absz(a[complete], b[complete])
    for row in np.flatnonzero(available & ~complete):
        first = a[row, np.isfinite(a[row])][None, :]
        second = b[row, np.isfinite(b[row])][None, :]
        z[row] = mannwhitney_absz(first, second)[0]
    return z, available


def run(mechanism, reps: int, stream: int, **kwargs):
    """Unconditional rejection and availability rates; invalid tests do not reject."""
    if reps < 1:
        raise ValueError("replications must be positive")
    rng = np.random.default_rng([SIM_SEED, stream])
    first = mechanism(rng, **kwargs)
    names = list(first)
    if len(names) != 2:
        raise ValueError("Reference protocol requires exactly two groups")
    for arr in first.values():
        if arr.ndim != 2 or arr.shape[1] < 2 or not np.isfinite(arr).all():
            raise ValueError("Each group must have finite repeated measurements, at least two per entity")
    store = {m: {g: np.empty((reps, first[g].shape[0])) for g in names} for m in METRICS}
    for r in range(reps):
        sample = first if r == 0 else mechanism(rng, **kwargs)
        if set(sample) != set(names):
            raise ValueError("Mechanism changed group names")
        for g in names:
            arr = sample[g]
            if arr.shape != first[g].shape or not np.isfinite(arr).all():
                raise ValueError("Mechanism changed shape or produced nonfinite measurements")
            for m, fn in METRICS.items():
                store[m][g][r] = fn(arr)
    out = {}
    z_by_metric = []
    for m in METRICS:
        z, available = metric_test_z(store[m][names[0]], store[m][names[1]])
        z_by_metric.append(z)
        out[m] = float(np.mean(z > Z_CRIT))
        out["__available__" + m] = float(np.mean(available))
    all_z = np.vstack(z_by_metric)
    out["__any_of_twelve_unadjusted__"] = float(np.mean(np.any(all_z > Z_CRIT, axis=0)))
    out["__bonferroni_twelve__"] = float(np.mean(np.any(all_z > Z_BONFERRONI, axis=0)))
    return out


# Two grids, both fixed in advance.
#
# "primary" uses the same effect sizes as the shipped CSV datasets: large
# enough that a difference is visible in the app at all.
#
# "discriminating" is a historical development grid chosen for non-ceiling
# power. It is not an unseen holdout for future tuning or validation.
GRIDS = {
    "primary": [
        ("A_normal_additive", dgp.normal_additive, 11, {}),
        ("B_lognormal_multiplicative", dgp.lognormal_multiplicative, 12, {}),
        ("C_heavy_tails", dgp.heavy_tails, 13, {}),
        ("D_scale_only", dgp.scale_only, 14, {}),
        ("E_null", dgp.pure_null, 15, {}),
    ],
    "discriminating": [
        ("A_normal_additive", dgp.normal_additive, 21, {"shift": 2.0}),
        ("B_lognormal_multiplicative", dgp.lognormal_multiplicative, 22, {"factor": 1.07}),
        ("C_heavy_tails", dgp.heavy_tails, 23, {"shift": 1.5}),
        ("D_scale_only", dgp.scale_only, 24, {"sd_ratio": 1.20}),
        ("E_null", dgp.pure_null, 25, {}),
    ],
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("replications", type=int, nargs="?", default=2000)
    ap.add_argument("grid", choices=tuple(GRIDS), nargs="?", default="primary")
    ap.add_argument("--output-dir", default=HERE)
    args = ap.parse_args()
    if args.replications < 1:
        ap.error("replications must be positive")
    scenarios = GRIDS[args.grid]
    results = {}
    for name, fn, stream, kwargs in scenarios:
        n = args.replications * 2 if name == "E_null" else args.replications
        results[name] = run(fn, n, stream, **kwargs)

    header = ["metric"] + [name for name, _, _, _ in scenarios]
    lines_md = ["| " + " | ".join(header) + " |",
                "|" + "|".join(["---"] * len(header)) + "|"]
    lines_csv = [",".join(header)]
    rows = [(m, m) for m in METRICS] + [
        ("any_of_twelve_unadjusted", "__any_of_twelve_unadjusted__"),
        ("bonferroni_twelve", "__bonferroni_twelve__"),
    ]
    rows += [("available_" + m, "__available__" + m) for m in METRICS]
    for label, key in rows:
        row = [label] + [f"{results[name][key]:.3f}" for name, _, _, _ in scenarios]
        lines_md.append("| " + " | ".join(row) + " |")
        lines_csv.append(",".join(row))
    note = (
        f"Protocol: **{PROTOCOL}**; active legacy registry: {FAMILY_SIZE} metrics. "
        f"Grid: **{args.grid}**. Replications: {args.replications} per mechanism "
        f"({args.replications * 2} for null); seed: {SIM_SEED}. "
        f"Individual alpha = {ALPHA}; Bonferroni local alpha = {ALPHA / FAMILY_SIZE:.8f}. "
        "Tie-corrected asymptotic two-sided Mann-Whitney U with continuity correction; "
        f"minimum {MIN_ENTITIES} finite entity summaries per group. "
        "Rates use all replications; unavailable tests count as non-rejections. "
        "Availability rows give the fraction of testable replications. "
        "These are Monte Carlo diagnostics, not certified population truth or a C# parity test. "
        "Version 2 changes definitions and is not directly interchangeable with historical reports."
    )
    text = "\n".join([f"# Reference diagnostics ({args.grid} grid)", "", note, ""] + lines_md + [""])
    os.makedirs(args.output_dir, exist_ok=True)
    for suffix, content in (("md", text), ("csv", "\n".join(lines_csv) + "\n")):
        path = os.path.join(args.output_dir, f"reference_power_v2_{args.grid}.{suffix}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    print(text)


if __name__ == "__main__":
    main()
