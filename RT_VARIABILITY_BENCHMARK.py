#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reaction-Time Variability Benchmark.

Simulates participant-level reaction times under prespecified scenarios and
compares common variability metrics. The benchmark evaluates statistical
behavior only; it does not establish a diagnosis, mechanism, treatment effect,
or the Allostatic Sprint hypothesis.

Example:
    python RT_VARIABILITY_BENCHMARK.py --config configs/benchmark-v0.1.json
    python RT_VARIABILITY_BENCHMARK.py --config configs/benchmark-v0.1.json --quick
    python RT_VARIABILITY_BENCHMARK.py --config configs/benchmark-v0.1.json --self-test
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import sys
import tempfile
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

SCRIPT_VERSION = "0.1.0"
DEFAULT_CONFIG = Path("configs/benchmark-v0.1.json")
METRIC_IDS = ("median_rt", "sd_rt", "cv_rt", "mad_rt", "iqr_rt")


# ---------------------------------------------------------------------------
# Configuration and reproducibility
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "project",
        "config_version",
        "seed",
        "simulation_repetitions",
        "groups",
        "reaction_time_model",
        "scenarios",
        "participant_metrics",
        "group_test",
        "outputs",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Configuration is missing required keys: {missing}")

    groups = config["groups"]
    names = groups.get("names", [])
    if len(names) != 2:
        raise ValueError("Exactly two group names are required.")
    if int(groups.get("participants_per_group", 0)) < 2:
        raise ValueError("participants_per_group must be at least 2.")

    model = config["reaction_time_model"]
    if model.get("distribution") != "lognormal":
        raise ValueError("Version 0.1 supports only the lognormal RT model.")
    if float(model.get("median_ms", 0)) <= 0:
        raise ValueError("median_ms must be positive.")
    valid_range = model.get("valid_rt_range_ms", [])
    if len(valid_range) != 2 or not (0 < valid_range[0] < valid_range[1]):
        raise ValueError("valid_rt_range_ms must contain increasing positive bounds.")

    scenario_ids: set[str] = set()
    for scenario in config["scenarios"]:
        scenario_id = str(scenario.get("id", "")).strip()
        if not scenario_id or scenario_id in scenario_ids:
            raise ValueError(f"Scenario IDs must be non-empty and unique: {scenario_id!r}")
        scenario_ids.add(scenario_id)
        for key in ("group_a_log_sigma", "group_b_log_sigma"):
            if float(scenario.get(key, 0)) <= 0:
                raise ValueError(f"{scenario_id}: {key} must be positive.")
        rate = float((scenario.get("missingness") or {}).get("target_rate", 0.0))
        if not 0.0 <= rate < 1.0:
            raise ValueError(f"{scenario_id}: missingness target_rate must be in [0, 1).")

    configured_metrics = tuple(item.get("id") for item in config["participant_metrics"])
    unknown_metrics = sorted(set(configured_metrics).difference(METRIC_IDS))
    if unknown_metrics:
        raise ValueError(f"Unsupported participant metrics: {unknown_metrics}")
    if config["group_test"].get("method") != "mann_whitney_u":
        raise ValueError("Version 0.1 supports group_test.method='mann_whitney_u'.")


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


# ---------------------------------------------------------------------------
# Reaction-time generation and contamination
# ---------------------------------------------------------------------------


def participant_trial_count(rng: np.random.Generator, specification: dict[str, Any]) -> int:
    mechanism = specification.get("mechanism", "fixed")
    if mechanism == "fixed":
        return int(specification["value"])
    if mechanism == "discrete_uniform":
        low = int(specification["minimum"])
        high = int(specification["maximum"])
        if low <= 0 or high < low:
            raise ValueError("Invalid discrete_uniform trial-count bounds.")
        return int(rng.integers(low, high + 1))
    raise ValueError(f"Unsupported trial-count mechanism: {mechanism}")


def generate_reaction_times(
    rng: np.random.Generator,
    n_trials: int,
    median_ms: float,
    log_sigma: float,
) -> np.ndarray:
    """Generate positively skewed RTs with the requested population median."""
    return rng.lognormal(mean=math.log(median_ms), sigma=log_sigma, size=n_trials)


def apply_outliers(
    rng: np.random.Generator,
    reaction_times: np.ndarray,
    specification: dict[str, Any],
) -> tuple[np.ndarray, int]:
    values = reaction_times.copy()
    if not specification.get("enabled", False):
        return values, 0

    rate = float(specification.get("rate", 0.0))
    count = min(len(values), max(0, int(round(rate * len(values)))))
    if count == 0:
        return values, 0

    if specification.get("multiplier_distribution") != "uniform":
        raise ValueError("Version 0.1 supports only uniform outlier multipliers.")
    low, high = map(float, specification["multiplier_range"])
    indices = rng.choice(len(values), size=count, replace=False)
    values[indices] *= rng.uniform(low, high, size=count)
    return values, count


def apply_missingness(
    rng: np.random.Generator,
    reaction_times: np.ndarray,
    specification: dict[str, Any],
) -> tuple[np.ndarray, int]:
    values = reaction_times.copy()
    mechanism = specification.get("mechanism", "none")
    target_rate = float(specification.get("target_rate", 0.0))
    count = min(len(values), max(0, int(round(target_rate * len(values)))))
    if mechanism == "none" or count == 0:
        return values, 0

    if mechanism == "mcar":
        indices = rng.choice(len(values), size=count, replace=False)
    elif mechanism == "slow_response_dependent":
        # Rank-based weights make slow responses more likely to be missing while
        # preserving the prespecified target count for every participant.
        order = np.argsort(np.argsort(values, kind="mergesort"), kind="mergesort")
        percentiles = (order.astype(float) + 1.0) / len(values)
        weights = np.square(percentiles) + 1e-12
        weights /= weights.sum()
        indices = rng.choice(len(values), size=count, replace=False, p=weights)
    else:
        raise ValueError(f"Unsupported missingness mechanism: {mechanism}")

    values[indices] = np.nan
    return values, count


# ---------------------------------------------------------------------------
# Participant metrics
# ---------------------------------------------------------------------------


def calculate_participant_metrics(values: np.ndarray, minimum_valid_trials: int) -> dict[str, float]:
    valid = np.asarray(values, dtype=float)
    valid = valid[np.isfinite(valid)]
    result = {metric: math.nan for metric in METRIC_IDS}
    result["valid_trials"] = float(len(valid))
    if len(valid) < minimum_valid_trials:
        return result

    median = float(np.median(valid))
    mean = float(np.mean(valid))
    sd = float(np.std(valid, ddof=1)) if len(valid) > 1 else math.nan
    q25, q75 = np.percentile(valid, [25, 75])
    result.update(
        {
            "median_rt": median,
            "sd_rt": sd,
            "cv_rt": sd / mean if mean > 0 and math.isfinite(sd) else math.nan,
            "mad_rt": float(np.median(np.abs(valid - median))),
            "iqr_rt": float(q75 - q25),
        }
    )
    return result


def simulate_group(
    rng: np.random.Generator,
    n_participants: int,
    group_name: str,
    log_sigma: float,
    scenario: dict[str, Any],
    model: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    collected: dict[str, list[float]] = {metric: [] for metric in METRIC_IDS}
    explicit_missing = 0
    range_excluded = 0
    generated_trials = 0
    valid_participants = 0

    low_rt, high_rt = map(float, model["valid_rt_range_ms"])
    minimum_valid = int(model["minimum_valid_trials"])

    for _ in range(n_participants):
        n_trials = participant_trial_count(rng, scenario["trial_counts"])
        generated_trials += n_trials
        values = generate_reaction_times(
            rng,
            n_trials=n_trials,
            median_ms=float(model["median_ms"]),
            log_sigma=float(log_sigma),
        )
        values, _ = apply_outliers(rng, values, scenario.get("outliers") or {"enabled": False})
        values, missing_count = apply_missingness(
            rng, values, scenario.get("missingness") or {"mechanism": "none"}
        )
        explicit_missing += missing_count

        outside = np.isfinite(values) & ((values < low_rt) | (values > high_rt))
        range_excluded += int(outside.sum())
        values[outside] = np.nan

        metrics = calculate_participant_metrics(values, minimum_valid)
        if metrics["valid_trials"] >= minimum_valid:
            valid_participants += 1
        for metric in METRIC_IDS:
            collected[metric].append(metrics[metric])

    arrays = {key: np.asarray(values, dtype=float) for key, values in collected.items()}
    diagnostics = {
        "group": group_name,
        "generated_trials": float(generated_trials),
        "explicit_missing_rate": explicit_missing / generated_trials if generated_trials else math.nan,
        "range_excluded_rate": range_excluded / generated_trials if generated_trials else math.nan,
        "valid_participants": float(valid_participants),
    }
    return arrays, diagnostics


# ---------------------------------------------------------------------------
# Mann-Whitney U with average ranks and tie-corrected normal approximation
# ---------------------------------------------------------------------------


def average_ranks(values: np.ndarray) -> tuple[np.ndarray, list[int]]:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=float)
    tie_sizes: list[int] = []
    start = 0
    while start < len(values):
        stop = start + 1
        while stop < len(values) and sorted_values[stop] == sorted_values[start]:
            stop += 1
        average_rank = ((start + 1) + stop) / 2.0
        ranks[order[start:stop]] = average_rank
        tie_sizes.append(stop - start)
        start = stop
    return ranks, tie_sizes


def mann_whitney_two_sided(group_b: Iterable[float], group_a: Iterable[float]) -> dict[str, float]:
    """Compare Group B against Group A; positive effect means larger values in B."""
    b = np.asarray(list(group_b), dtype=float)
    a = np.asarray(list(group_a), dtype=float)
    b = b[np.isfinite(b)]
    a = a[np.isfinite(a)]
    n_b, n_a = len(b), len(a)
    if n_b < 2 or n_a < 2:
        return {"u": math.nan, "p_value": math.nan, "rank_biserial": math.nan}

    combined = np.concatenate([b, a])
    ranks, tie_sizes = average_ranks(combined)
    u_b = float(ranks[:n_b].sum() - n_b * (n_b + 1) / 2.0)
    expected = n_b * n_a / 2.0
    n_total = n_b + n_a
    tie_term = sum(size**3 - size for size in tie_sizes)
    variance = (n_b * n_a / 12.0) * (
        (n_total + 1.0) - tie_term / (n_total * (n_total - 1.0))
    )
    if variance <= 0:
        p_value = 1.0
    else:
        continuity_adjusted = max(0.0, abs(u_b - expected) - 0.5)
        z = continuity_adjusted / math.sqrt(variance)
        p_value = math.erfc(z / math.sqrt(2.0))
        p_value = min(1.0, max(0.0, p_value))
    rank_biserial = 2.0 * u_b / (n_b * n_a) - 1.0
    return {"u": u_b, "p_value": p_value, "rank_biserial": rank_biserial}


# ---------------------------------------------------------------------------
# Benchmark runner and summaries
# ---------------------------------------------------------------------------


def run_benchmark(
    config: dict[str, Any],
    repetitions: int,
    seed: int,
    progress: bool = True,
    scenario_limit: int | None = None,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    scenarios = list(config["scenarios"])
    if scenario_limit is not None:
        scenarios = scenarios[:scenario_limit]
    model = config["reaction_time_model"]
    n_participants = int(config["groups"]["participants_per_group"])
    group_a_name, group_b_name = config["groups"]["names"]
    alpha = float(config["group_test"].get("alpha", config.get("alpha", 0.05)))
    rows: list[dict[str, Any]] = []

    for scenario_index, scenario in enumerate(scenarios, start=1):
        if progress:
            print(f"[{scenario_index}/{len(scenarios)}] {scenario['id']}", flush=True)
        checkpoint = max(1, repetitions // 10)
        for repetition in range(1, repetitions + 1):
            group_a, diag_a = simulate_group(
                rng,
                n_participants,
                group_a_name,
                float(scenario["group_a_log_sigma"]),
                scenario,
                model,
            )
            group_b, diag_b = simulate_group(
                rng,
                n_participants,
                group_b_name,
                float(scenario["group_b_log_sigma"]),
                scenario,
                model,
            )
            for metric in METRIC_IDS:
                a = group_a[metric]
                b = group_b[metric]
                test = mann_whitney_two_sided(b, a)
                finite_a = a[np.isfinite(a)]
                finite_b = b[np.isfinite(b)]
                difference = (
                    float(np.median(finite_b) - np.median(finite_a))
                    if len(finite_a) and len(finite_b)
                    else math.nan
                )
                rows.append(
                    {
                        "scenario": scenario["id"],
                        "repetition": repetition,
                        "metric": metric,
                        "n_group_a": len(finite_a),
                        "n_group_b": len(finite_b),
                        "median_group_a": float(np.median(finite_a)) if len(finite_a) else math.nan,
                        "median_group_b": float(np.median(finite_b)) if len(finite_b) else math.nan,
                        "median_difference_b_minus_a": difference,
                        "mann_whitney_u_b": test["u"],
                        "p_value": test["p_value"],
                        "significant": int(math.isfinite(test["p_value"]) and test["p_value"] < alpha),
                        "rank_biserial_b_vs_a": test["rank_biserial"],
                        "missing_rate_group_a": diag_a["explicit_missing_rate"],
                        "missing_rate_group_b": diag_b["explicit_missing_rate"],
                        "range_excluded_rate_group_a": diag_a["range_excluded_rate"],
                        "range_excluded_rate_group_b": diag_b["range_excluded_rate"],
                        "valid_participants_group_a": int(diag_a["valid_participants"]),
                        "valid_participants_group_b": int(diag_b["valid_participants"]),
                    }
                )
            if progress and (repetition % checkpoint == 0 or repetition == repetitions):
                print(f"  completed {repetition}/{repetitions}", flush=True)
    return rows


def finite_numbers(values: Iterable[Any]) -> np.ndarray:
    output = np.asarray([float(value) for value in values], dtype=float)
    return output[np.isfinite(output)]


def summarize_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scenario"]), str(row["metric"]))].append(row)

    summary: list[dict[str, Any]] = []
    for (scenario, metric), subset in grouped.items():
        p_values = finite_numbers(row["p_value"] for row in subset)
        differences = finite_numbers(row["median_difference_b_minus_a"] for row in subset)
        effects = finite_numbers(row["rank_biserial_b_vs_a"] for row in subset)
        significant = np.asarray([int(row["significant"]) for row in subset], dtype=float)
        is_null = scenario == "null_equal_groups"
        summary.append(
            {
                "scenario": scenario,
                "metric": metric,
                "completed_repetitions": len(subset),
                "evaluation": "false_positive_rate" if is_null else "statistical_power",
                "significance_rate": float(np.mean(significant)) if len(significant) else math.nan,
                "median_p_value": float(np.median(p_values)) if len(p_values) else math.nan,
                "median_group_difference_b_minus_a": float(np.median(differences)) if len(differences) else math.nan,
                "mean_rank_biserial_b_vs_a": float(np.mean(effects)) if len(effects) else math.nan,
                "sd_rank_biserial_b_vs_a": float(np.std(effects, ddof=1)) if len(effects) > 1 else math.nan,
                "mean_valid_participants_group_a": float(
                    np.mean([row["valid_participants_group_a"] for row in subset])
                ),
                "mean_valid_participants_group_b": float(
                    np.mean([row["valid_participants_group_b"] for row in subset])
                ),
            }
        )
    return sorted(summary, key=lambda row: (row["scenario"], row["metric"]))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return json_ready(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})


def output_paths(config: dict[str, Any], output_dir: Path | None) -> dict[str, Path]:
    configured = config["outputs"]
    if output_dir is None:
        return {key: Path(value) for key, value in configured.items()}
    return {
        "result_table": output_dir / "benchmark_results.csv",
        "summary_table": output_dir / "metric_summary.csv",
        "configuration_copy": output_dir / "benchmark_config.json",
        "reproducibility_log": output_dir / "reproducibility_log.json",
        "figure": output_dir / "metric_performance.png",
    }


def create_figure(path: Path, summary: list[dict[str, Any]]) -> str:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not installed; figure skipped"

    scenarios = list(dict.fromkeys(row["scenario"] for row in summary))
    metrics = list(METRIC_IDS)
    matrix = np.full((len(scenarios), len(metrics)), np.nan)
    lookup = {(row["scenario"], row["metric"]): row for row in summary}
    for row_index, scenario in enumerate(scenarios):
        for column_index, metric in enumerate(metrics):
            row = lookup.get((scenario, metric))
            if row:
                matrix[row_index, column_index] = row["significance_rate"]

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, max(4.5, 0.75 * len(scenarios))))
    image = ax.imshow(matrix, vmin=0, vmax=1, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(metrics)), metrics, rotation=30, ha="right")
    ax.set_yticks(range(len(scenarios)), scenarios)
    ax.set_title("Detection rate by scenario and RT metric")
    for row_index in range(len(scenarios)):
        for column_index in range(len(metrics)):
            value = matrix[row_index, column_index]
            if math.isfinite(value):
                color = "white" if value < 0.45 else "black"
                ax.text(column_index, row_index, f"{value:.2f}", ha="center", va="center", color=color)
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("False-positive rate for null; power otherwise")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return "created"


def write_outputs(
    config: dict[str, Any],
    config_path: Path,
    paths: dict[str, Path],
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    repetitions: int,
    seed: int,
    make_figure: bool,
) -> dict[str, Any]:
    write_csv(paths["result_table"], rows)
    write_csv(paths["summary_table"], summary)

    runtime_config = json.loads(json.dumps(config))
    runtime_config["runtime"] = {
        "actual_repetitions": repetitions,
        "actual_seed": seed,
        "script_version": SCRIPT_VERSION,
    }
    paths["configuration_copy"].parent.mkdir(parents=True, exist_ok=True)
    paths["configuration_copy"].write_text(
        json.dumps(json_ready(runtime_config), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    figure_status = "disabled"
    if make_figure:
        figure_status = create_figure(paths["figure"], summary)

    provenance = {
        "project": config["project"],
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "seed": seed,
        "repetitions": repetitions,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            "numpy": package_version("numpy"),
            "matplotlib": package_version("matplotlib"),
        },
        "group_test": "internal Mann-Whitney U, average ranks, tie-corrected normal approximation",
        "figure_status": figure_status,
        "outputs": {key: str(value) for key, value in paths.items()},
        "interpretation_boundary": config.get("interpretation_boundary", ""),
    }
    paths["reproducibility_log"].parent.mkdir(parents=True, exist_ok=True)
    paths["reproducibility_log"].write_text(
        json.dumps(json_ready(provenance), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return provenance


# ---------------------------------------------------------------------------
# Deterministic synthetic self-test
# ---------------------------------------------------------------------------


def self_test(config: dict[str, Any]) -> dict[str, Any]:
    test_config = json.loads(json.dumps(config))
    test_config["groups"]["participants_per_group"] = 12
    first = run_benchmark(test_config, repetitions=3, seed=12345, progress=False, scenario_limit=2)
    second = run_benchmark(test_config, repetitions=3, seed=12345, progress=False, scenario_limit=2)
    if first != second:
        raise AssertionError("Determinism check failed.")
    expected_rows = 2 * 3 * len(METRIC_IDS)
    if len(first) != expected_rows:
        raise AssertionError(f"Expected {expected_rows} rows, received {len(first)}.")
    for row in first:
        p = float(row["p_value"])
        if not 0.0 <= p <= 1.0:
            raise AssertionError(f"Invalid p-value: {p}")
    sample = np.asarray([100.0, 200.0, 300.0, 400.0, 500.0])
    metrics = calculate_participant_metrics(sample, minimum_valid_trials=2)
    if metrics["median_rt"] != 300.0 or metrics["iqr_rt"] != 200.0:
        raise AssertionError("Metric sanity check failed.")
    return {
        "status": "PASS",
        "script_version": SCRIPT_VERSION,
        "deterministic_rows": len(first),
        "metric_sanity_check": "PASS",
        "p_value_range_check": "PASS",
    }


# ---------------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="JSON benchmark configuration")
    parser.add_argument("--output-dir", type=Path, default=None, help="override all configured output paths")
    parser.add_argument("--repetitions", type=int, default=None, help="override simulation repetitions")
    parser.add_argument("--seed", type=int, default=None, help="override random seed")
    parser.add_argument("--quick", action="store_true", help="run 10 repetitions for a quick smoke test")
    parser.add_argument("--self-test", action="store_true", help="run deterministic synthetic checks and exit")
    parser.add_argument("--no-figure", action="store_true", help="skip PNG figure generation")
    parser.add_argument("--json-summary", action="store_true", help="print final summary as JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {SCRIPT_VERSION}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config_path = args.config.resolve()
        config = load_config(config_path)
        if args.self_test:
            print(json.dumps(self_test(config), indent=2))
            return 0

        repetitions = int(
            10 if args.quick else args.repetitions
            if args.repetitions is not None
            else config["simulation_repetitions"]
        )
        seed = int(args.seed if args.seed is not None else config["seed"])
        if repetitions < 1:
            raise ValueError("repetitions must be at least 1")

        print(f"RT Variability Benchmark v{SCRIPT_VERSION}")
        print(f"Config: {config_path}")
        print(f"Seed: {seed}; repetitions per scenario: {repetitions}")
        rows = run_benchmark(config, repetitions=repetitions, seed=seed, progress=True)
        summary = summarize_results(rows)
        paths = output_paths(config, args.output_dir)
        provenance = write_outputs(
            config,
            config_path,
            paths,
            rows,
            summary,
            repetitions,
            seed,
            make_figure=not args.no_figure,
        )

        compact = {
            "status": "PASS",
            "script_version": SCRIPT_VERSION,
            "scenarios": len(config["scenarios"]),
            "repetitions_per_scenario": repetitions,
            "result_rows": len(rows),
            "outputs": provenance["outputs"],
            "figure_status": provenance["figure_status"],
        }
        if args.json_summary:
            print(json.dumps(compact, indent=2))
        else:
            print("\nCompleted successfully.")
            print(f"Raw results: {paths['result_table']}")
            print(f"Summary: {paths['summary_table']}")
            print(f"Reproducibility log: {paths['reproducibility_log']}")
            print(f"Figure: {provenance['figure_status']}")
        return 0
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
