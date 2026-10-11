#!/usr/bin/env python3
"""Independent SciPy rank-test fixtures; never calls or copies the MVS engine."""
from __future__ import annotations

import argparse
from collections import Counter
import itertools
import json
import math
from pathlib import Path
import random
import sys

FIXTURE = Path(__file__).with_name("rank-test-fixtures-v1.json")
SCHEMA = "mvs-rank-reference/v1"
SEED = 20261011
SETTINGS = {
    "mann_whitney": {"alternative": "two-sided", "method": "asymptotic", "use_continuity": True},
    "kruskal_wallis": {"reference": "chi-square", "ties": "average ranks and tie correction"},
}
# MVS uses a polynomial normal CDF. This is an absolute p-value accuracy gate,
# not a relative-tail precision claim. Kruskal-Wallis uses a separate gamma gate.
TOLERANCES = {"mann_whitney": 2e-7, "kruskal_wallis": 2e-10}


def inputs() -> list[tuple[str, str, list[list[float]]]]:
    cases = [
        ("mw_overlap", "mann_whitney", [[1, 2, 3, 4, 5], [2, 3, 4, 5, 6]]),
        ("mw_ties", "mann_whitney", [[1, 2, 2, 4, 5], [2, 3, 3, 6, 7]]),
        ("mw_equal_distributions", "mann_whitney", [[1, 2, 3, 4], [1, 2, 3, 4]]),
        ("mw_constant_separated", "mann_whitney", [[1] * 6, [2] * 6]),
        ("mw_unbalanced", "mann_whitney", [[-4, -2, 0, 3], [-3, -1, 1, 2, 4, 6, 8, 9, 10]]),
        ("mw_separated_n4", "mann_whitney", [list(range(4)), list(range(4, 8))]),
        ("mw_separated_n6", "mann_whitney", [list(range(6)), list(range(6, 12))]),
        ("mw_near_decision_threshold", "mann_whitney", [list(range(7)), list(range(6, 13))]),
        ("mw_extreme_tail", "mann_whitney", [list(range(100)), list(range(100, 200))]),
        ("kw_interleaved_two", "kruskal_wallis", [[1, 3, 5, 7, 9], [2, 4, 6, 8, 10]]),
        ("kw_ties_two", "kruskal_wallis", [[1, 1, 1, 2], [2, 2, 2, 2]]),
        ("kw_equal_three", "kruskal_wallis", [[1, 2, 3, 4]] * 3),
        ("kw_separated_three_n4", "kruskal_wallis", [list(range(i, i + 4)) for i in (0, 4, 8)]),
        ("kw_ties_three", "kruskal_wallis", [[0, 0, 1, 2, 2], [1, 2, 2, 3, 4], [2, 3, 4, 4, 4]]),
        ("kw_unbalanced", "kruskal_wallis", [[-3, -1, 1, 3], [0, 2, 4, 6, 8, 10], [-2, 0, 2, 4, 6, 8, 10, 12]]),
        ("kw_ten_groups", "kruskal_wallis", [[g + i / 4 for i in range(6)] for g in range(10)]),
        ("kw_extreme_tail", "kruskal_wallis", [list(range(i, i + 100)) for i in (0, 100, 200)]),
    ]
    rng = random.Random(SEED)
    for method, group_count in [("mann_whitney", 2), ("kruskal_wallis", 3)]:
        for index in range(16):
            groups = []
            for g in range(group_count if index < 12 else 5):
                n = rng.choice([4, 5, 8, 13, 25])
                values = [rng.gauss(g * (index % 4) * .35, 1) for _ in range(n)]
                groups.append([round(x) for x in values] if index % 2 else values)
            cases.append((f"{method}_seeded_{index:02}", method, groups[:2] if method == "mann_whitney" else groups))
    return cases


def exact_mann_whitney(groups: list[list[float]]) -> dict:
    """Enumerate labelled assignments, including ties; two-sided |U-E(U)| tail."""
    values = groups[0] + groups[1]
    n1, n2 = map(len, groups)
    ordered = sorted(values)
    ranks = {x: (ordered.index(x) + 1 + len(ordered) - ordered[::-1].index(x)) / 2 for x in set(values)}
    rank_values = [ranks[x] for x in values]
    center = n1 * (len(values) + 1) / 2
    observed = abs(sum(rank_values[:n1]) - center)
    count = total = 0
    for assignment in itertools.combinations(rank_values, n1):
        total += 1
        count += abs(sum(assignment) - center) >= observed
    return {"p": count / total, "assignments": total, "tail": "absolute centered U, inclusive", "ties": len(Counter(values)) < n1 + n2}


def build_fixture() -> dict:
    import scipy
    from scipy import stats

    cases = []
    for name, method, groups in inputs():
        result = (stats.mannwhitneyu(*groups, **SETTINGS[method]) if method == "mann_whitney"
                  else stats.kruskal(*groups, nan_policy="raise"))
        case = {"id": name, "method": method, "groups": groups,
                "reference": "scipy", "expectedP": float(result.pvalue),
                "expectedStatistic": float(result.statistic)}
        if name in {"mw_separated_n4", "mw_separated_n6", "mw_ties"}:
            case["exactDiagnostic"] = exact_mann_whitney(groups)
        cases.append(case)
    # These are explicit existing MVS policies, NOT SciPy numerical matches:
    # SciPy raises on constant Kruskal data; MVS returns one. Empty arrays are unavailable.
    for method in SETTINGS:
        for kind, groups, p in [("constant", [[2] * 4, [2] * 4], 1), ("empty", [[], [1, 2, 3, 4]], None)]:
            cases.append({"id": f"{method}_{kind}_policy", "method": method, "groups": groups,
                          "reference": "mvs-declared-policy", "expectedP": p})
    return {"schema": SCHEMA, "seed": SEED, "settings": SETTINGS,
            "absoluteTolerance": TOLERANCES,
            "provenance": {"library": "SciPy", "version": scipy.__version__,
                           "sources": ["https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.mannwhitneyu.html",
                                       "https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.kruskal.html"]},
            "scope": "Finite entity summaries, asymptotic p-values; not FWER or population calibration certification.",
            "cases": cases}


def load_fixture(path: Path = FIXTURE) -> dict:
    def invalid(value):
        raise ValueError(f"Nonstandard JSON number: {value}")
    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)
    if data.get("schema") != SCHEMA or data.get("seed") != SEED or data.get("settings") != SETTINGS:
        raise ValueError("Unknown fixture schema, seed or test settings")
    if data.get("absoluteTolerance") != TOLERANCES:
        raise ValueError("Fixture accuracy gate changed")
    expected = inputs()
    cases = data.get("cases", [])
    if len(cases) != len(expected) + 4 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Missing/duplicate rank fixtures")
    for case, (name, method, groups) in zip(cases, expected):
        if (case["id"], case["method"], case["groups"], case["reference"]) != (name, method, groups, "scipy"):
            raise ValueError(f"Fixture input/provenance mismatch: {name}")
        if not all(math.isfinite(x) for group in case["groups"] for x in group):
            raise ValueError(f"Nonfinite fixture input: {name}")
        p = case["expectedP"]
        if type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError(f"Invalid reference p-value: {name}")
    return data


def check_fixture(path: Path = FIXTURE) -> int:
    frozen = load_fixture(path)
    fresh = build_fixture()
    # Fixture verification uses a much tighter gate than native polynomial-CDF checks.
    for old, new in zip(frozen["cases"], fresh["cases"]):
        if old.keys() != new.keys():
            raise ValueError(f"Fixture fields differ: {old['id']}")
        for key in old:
            if key in {"expectedP", "expectedStatistic"} and old[key] is not None:
                if not math.isclose(old[key], new[key], rel_tol=1e-12, abs_tol=1e-14):
                    raise ValueError(f"Independent reference changed: {old['id']}.{key}")
            elif old[key] != new[key]:
                raise ValueError(f"Fixture differs: {old['id']}.{key}")
    print(f"Verified {len(frozen['cases'])} frozen rank cases against SciPy (no C# execution).")
    return len(frozen["cases"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Recompute references and verify the frozen fixture")
    parser.add_argument("--write", type=Path, help="Create a NEW reviewable fixture; refuses overwrite")
    args = parser.parse_args()
    if args.write and args.check:
        parser.error("Choose --check or --write")
    if args.write:
        with args.write.open("x", encoding="utf-8") as output:
            json.dump(build_fixture(), output, indent=2, allow_nan=False)
            output.write("\n")
        print(f"Wrote independent fixture: {args.write}")
    else:
        check_fixture()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, ImportError) as error:
        print(f"Rank reference check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
