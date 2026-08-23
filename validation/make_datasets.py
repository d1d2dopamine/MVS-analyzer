#!/usr/bin/env python3
"""Write the validation datasets as CSV files the importer accepts.

Usage:
    python3 validation/make_datasets.py

Deterministic: the same seed produces byte-identical files, so a reviewer can
regenerate them and diff. Layout is the standard six-role format documented in
docs/DATA_FORMAT.md:

    entity,group,value,sequence,variable,unit

Only numpy is required.
"""

from __future__ import annotations

import csv
import os

import numpy as np

import dgp

SEED = 20260823
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "datasets")
VARIABLE = "measurement"
UNIT = "unit"
NULL_REPLICATES = 10


def write_csv(path: str, groups: dict[str, np.ndarray]) -> int:
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["entity", "group", "value", "sequence", "variable", "unit"])
        for name, arr in groups.items():
            prefix = name[:3].upper()
            for i in range(arr.shape[0]):
                entity = f"{prefix}_{i + 1:02d}"
                for j in range(arr.shape[1]):
                    writer.writerow(
                        [entity, name, f"{arr[i, j]:.3f}", j + 1, VARIABLE, UNIT]
                    )
                    rows += 1
    return rows


def build() -> list[tuple[str, int, int]]:
    os.makedirs(OUT, exist_ok=True)
    made: list[tuple[str, int, int]] = []

    plan = [
        ("A_normal_additive", dgp.normal_additive, 1),
        ("B_lognormal_multiplicative", dgp.lognormal_multiplicative, 2),
        ("C_heavy_tails", dgp.heavy_tails, 3),
        ("D_scale_only", dgp.scale_only, 4),
        ("F_small_n", dgp.small_n, 5),
        ("G_ties_zero_spread", dgp.ties_and_zero_spread, 6),
    ]
    for name, fn, stream in plan:
        rng = np.random.default_rng([SEED, stream])
        path = os.path.join(OUT, f"{name}.csv")
        rows = write_csv(path, fn(rng))
        made.append((f"{name}.csv", rows, os.path.getsize(path)))

    for k in range(1, NULL_REPLICATES + 1):
        rng = np.random.default_rng([SEED, 100 + k])
        name = f"E_null_{k:02d}.csv"
        path = os.path.join(OUT, name)
        rows = write_csv(path, dgp.pure_null(rng))
        made.append((name, rows, os.path.getsize(path)))

    return made


if __name__ == "__main__":
    made = build()
    total = sum(size for _, _, size in made)
    print(f"{'file':<32} {'rows':>7} {'bytes':>9}")
    for name, rows, size in made:
        print(f"{name:<32} {rows:>7} {size:>9}")
    print(f"{'TOTAL':<32} {sum(r for _, r, _ in made):>7} {total:>9}")
