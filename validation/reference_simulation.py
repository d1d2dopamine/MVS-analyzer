#!/usr/bin/env python3
"""Monte-Carlo truth table for the validation datasets.

Usage:
    python3 validation/reference_simulation.py [replications]

This is an INDEPENDENT reference implementation. It does not import, call or
reuse any part of MVS Analyzer. It answers one question per mechanism:

    given this known data-generating process, which entity-level summary
    statistic actually has the highest power, and how much?

That is the ground truth the tool is judged against. If MVS ranks a metric
first in a world where a different metric provably detects the effect more
often, the ranking is wrong -- and we would rather find that here than in a
comment thread.

Method: for each replication, draw a fresh dataset from the mechanism, reduce
each entity to one value per metric, and run a two-sided Mann-Whitney U test on
the entity-level values (normal approximation with a continuity correction,
alpha = 0.05). The rejection rate over replications is power (or, under the
null mechanism, the false-positive rate).

The mechanisms are continuous, so ties have probability zero and no tie
correction is applied. Two statistics that the current engine does NOT
implement -- the geometric mean and a 20 % trimmed mean -- are included as
reference rows, because the point of a truth table is to show what you are
leaving on the table.

Only numpy is required.
"""

from __future__ import annotations

import os
import sys

import numpy as np

import dgp

SIM_SEED = 20260823
ALPHA = 0.05
Z_CRIT = 1.959963984540054  # two-sided 0.05
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


def _cv(x):
    return _sd(x) / _mean(x)


def _mad(x):
    med = np.median(x, axis=1, keepdims=True)
    return np.median(np.abs(x - med), axis=1)


def _iqr(x):
    return np.percentile(x, 75, axis=1) - np.percentile(x, 25, axis=1)


def _norm_mad(x):
    return _mad(x) / np.median(x, axis=1)


def _norm_iqr(x):
    return _iqr(x) / np.median(x, axis=1)


def _range(x):
    return np.max(x, axis=1) - np.min(x, axis=1)


def _geomean(x):
    if np.any(x <= 0):
        return np.full(x.shape[0], np.nan)
    return np.exp(np.mean(np.log(x), axis=1))


def _trimmed20(x):
    s = np.sort(x, axis=1)
    k = int(round(0.20 * x.shape[1]))
    return np.mean(s[:, k: x.shape[1] - k], axis=1) if x.shape[1] - 2 * k > 0 else _mean(x)


IMPLEMENTED = {
    "median": _median,
    "mean": _mean,
    "rms": _rms,
    "standard_deviation": _sd,
    "coefficient_of_variation": _cv,
    "mad": _mad,
    "iqr": _iqr,
    "normalized_mad": _norm_mad,
    "normalized_iqr": _norm_iqr,
    "range": _range,
}
NOT_IMPLEMENTED = {
    "geometric_mean*": _geomean,
    "trimmed_mean_20*": _trimmed20,
}
METRICS = {**IMPLEMENTED, **NOT_IMPLEMENTED}


# --------------------------------------------------------------------------
# Two-sided Mann-Whitney U, vectorised over replications.
# a, b have shape (reps, n1) and (reps, n2). Returns |z| per replication.
# --------------------------------------------------------------------------
def mannwhitney_absz(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n1, n2 = a.shape[1], b.shape[1]
    both = np.concatenate([a, b], axis=1)
    order = np.argsort(both, axis=1, kind="stable")
    ranks = np.empty_like(order, dtype=float)
    positions = np.broadcast_to(
        np.arange(1, n1 + n2 + 1, dtype=float), both.shape
    ).copy()
    np.put_along_axis(ranks, order, positions, axis=1)
    r1 = ranks[:, :n1].sum(axis=1)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    sigma = np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    return np.maximum(np.abs(u1 - mu) - 0.5, 0.0) / sigma


def run(mechanism, reps: int, stream: int, **kwargs):
    """Return {metric: rejection_rate} plus the any-of-ten selection rate."""
    rng = np.random.default_rng([SIM_SEED, stream])
    first = mechanism(rng, **kwargs)
    names = list(first.keys())
    n_entities = first[names[0]].shape[0]

    store = {
        m: {g: np.empty((reps, n_entities)) for g in names} for m in METRICS
    }
    for r in range(reps):
        sample = first if r == 0 else mechanism(rng, **kwargs)
        for g in names:
            arr = sample[g]
            for m, fn in METRICS.items():
                store[m][g][r] = fn(arr)

    out: dict[str, float] = {}
    z_by_metric = {}
    for m in METRICS:
        a, b = store[m][names[0]], store[m][names[1]]
        if np.isnan(a).any() or np.isnan(b).any():
            out[m] = float("nan")
            continue
        z = mannwhitney_absz(a, b)
        z_by_metric[m] = z
        out[m] = float(np.mean(z > Z_CRIT))

    implemented_z = np.vstack([z_by_metric[m] for m in IMPLEMENTED if m in z_by_metric])
    out["__any_of_ten__"] = float(np.mean(implemented_z.max(axis=0) > Z_CRIT))
    return out


# Two grids, both fixed in advance.
#
# "primary" uses the same effect sizes as the shipped CSV datasets: large
# enough that a difference is visible in the app at all.
#
# "discriminating" shrinks every effect until the best metric lands in the
# 0.3-0.8 power band. A comparison run at ceiling power cannot tell two metrics
# apart -- if everything detects everything, every ordering looks the same.
# The ranking claims are therefore judged on this grid.
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
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    grid = sys.argv[2] if len(sys.argv) > 2 else "primary"
    SCENARIOS = GRIDS[grid]
    results = {}
    for name, fn, stream, kwargs in SCENARIOS:
        n = reps * 2 if name == "E_null" else reps
        results[name] = run(fn, n, stream, **kwargs)
        results[name]["__reps__"] = n

    header = ["metric"] + [name for name, _, _, _ in SCENARIOS]
    lines_md = ["| " + " | ".join(header) + " |",
                "|" + "|".join(["---"] * len(header)) + "|"]
    lines_csv = [",".join(header)]
    for m in METRICS:
        row = [m]
        for name, _, _, _ in SCENARIOS:
            v = results[name][m]
            row.append("n/a" if v != v else f"{v:.3f}")
        lines_md.append("| " + " | ".join(row) + " |")
        lines_csv.append(",".join(row))
    row = ["any of the ten (selection)"]
    for name, _, _, _ in SCENARIOS:
        row.append(f"{results[name]['__any_of_ten__']:.3f}")
    lines_md.append("| **" + row[0] + "** | " + " | ".join(row[1:]) + " |")
    lines_csv.append(",".join(["any_of_ten"] + row[1:]))

    note = (
        f"Grid: **{grid}**. Replications: {reps} per mechanism ({reps * 2} for the null). "
        f"alpha = {ALPHA}. Two-sided Mann-Whitney U on entity-level values. "
        "Rows marked * are not implemented in the engine and are shown for "
        "comparison only."
    )
    text = "\n".join(
        [f"# Reference truth table ({grid} grid)", "", note, ""] + lines_md + [""]
    )
    with open(os.path.join(HERE, f"reference_power_{grid}.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(HERE, f"reference_power_{grid}.csv"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines_csv) + "\n")
    print(text)


if __name__ == "__main__":
    main()
