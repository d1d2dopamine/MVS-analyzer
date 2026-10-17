"""Validate the bounded prospective ADEMP design and enumerate a plan only.

This module has no random generator, simulation adapter, native process launcher,
or result evaluator. Coordinates and reserved native seeds are arithmetic
identities, not random draws or generated observations.
Configuration validity and a complete plan do not authorize scientific execution.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = "validation/prospective-ademp-v1.json"
DOCUMENT_PATH = "docs/PROSPECTIVE_ADEMP_V1.md"
VALIDATOR_PATH = "validation/prospective_ademp.py"
PROTOCOL_ID = "MVS-STAT-COMPONENTS-PROSPECTIVE-1.0.0"
REPETITIONS = 1000
METRIC_KEYS = (
    "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr",
    "normalized_mad", "normalized_iqr", "mean", "rms", "range",
    "geometric_mean", "trimmed_mean_20",
)
SOURCE_PATHS = (
    "Core/VarianceAnalysis.cs", "Core/AnalysisEngine.cs", "Core/MetricRegistry.cs",
    "Core/MetricAvailability.cs", "Core/ScientificInfrastructure.cs", "Core/NumericalMethods.cs",
    "validation/benchmark-suite-v1.json", "validation/benchmark-suite-v1.1.json",
    "validation/round50-results.json", "validation/variance-sensitivity-protocol-v1.json",
    "validation/nist-univariate-protocol-v1.json", "validation/round53-results.json",
    "validation/variance_sensitivity/Program.cs",
)
TOP_FIELDS = (
    "schema", "protocol_id", "status", "evidence_role", "suite_version", "study_phase",
    "outer_repetitions_per_cell", "cells", "methods", "rng", "inference", "failure_policy",
    "budget", "readiness", "excluded_candidate", "input_policy", "engineering_probe", "source_bindings",
)
METHODS = [
    {
        "id": "gaussian_component_family_B199_E100_v1", "family_size": 2,
        "alpha": 0.05, "component_alpha": 0.025,
        "rejection": "adjusted_p_strictly_less_than_alpha", "reference_replications": 199,
        "evaluation_repetitions": 100, "within_effect": 2, "between_effect": 2,
        "minimum_finite_reference_fraction": 0.9,
        "p_formula": "(1+inclusive_exceedances)/(finite_reference_count+1)",
        "zero_failure_largest_rejecting_exceedance": 3,
    },
    {
        "id": "summary12_asymptotic_MW_Bonferroni_v1", "family_size": 12,
        "alpha": 0.05, "rejection": "adjusted_p_strictly_less_than_alpha",
        "metric_keys": list(METRIC_KEYS), "minimum_entities_per_group": 4,
        "nonfinite_summary_policy": "preserve_production_filter_report_per_metric_counts",
        "incomplete_family_policy": "available_rejection_positive_otherwise_unknown",
    },
]
RNG = {
    "generator": "numpy.random.PCG64", "numpy_version": "2.3.5",
    "seed_sequence": "numpy.random.SeedSequence", "master": 2026101754,
    "phase": 1, "data_stream": 0, "native_seed_stream": 1,
    "coordinates": ["master", "phase", "stream", "cell_index", "replication_zero_based"],
    "draw_order": "group_entity_intercepts_then_group_entity_repeat_residuals",
    "distribution_draws": "standard_normal_or_standard_t_df5_times_sqrt_3_over_5",
    "native_seed_derivation": "1540000000+1000*cell_index+replication_zero_based",
    "state_retention": "before_and_after_each_data_generation_plus_native_seed_and_internal_algorithm_identity",
    "shared_data_between_methods": True, "reuse_historical_data": False,
    "native_seed_base": 1540000000,
}
INFERENCE = {
    "null_endpoint_count": 31, "simultaneous_family": "all_31_true_null_cell_endpoint_pairs",
    "confidence": 0.95, "tail_allocation": "0.025/31_per_bound", "bounds": "exact_Clopper_Pearson",
    "inflation_rule": "simultaneous_lower_bound_exceeds_endpoint_nominal_alpha",
    "no_inflation_detected_status": "inconclusive_not_validation", "acceptance_tolerance": None,
    "power_intervals": "marginal_two_sided_95_percent_exact_Clopper_Pearson",
    "paired_differences": "conservative_discordance_CP_97_5_percent_union_bound",
    "paired_scope": "12_named_family_any_rejection_differences_descriptive_distinct_nulls_disclosed",
    "power_superiority_gate": None,
    "alternative_endpoints": {
        "within_component": ["C02", "C04", "C06"],
        "between_component": ["C03", "C04", "C07"],
        "both_components_correctly_detected": ["C04"],
        "family_any_operating_outcomes": "all_12_cells_with_null_truth_labels",
    },
}
FAILURE_POLICY = {
    "dataset_replacement": False, "retry_limit": 0, "drop_failed_repetitions": False,
    "method_failure": "retain_other_method_and_all_attempted_denominators",
    "family_outcome": "true_if_any_available_rejection_false_only_if_all_members_available_else_unknown",
    "rate_bounds": "observed_rejections_over_R_to_observed_rejections_plus_unknown_over_R",
    "technical_halt": "stop_on_identity_schema_hash_or_deterministic_harness_corruption_preserve_all_attempts",
    "resource_halt": "incomplete_no_extrapolated_completion",
    "resume": "same_manifest_same_case_no_recompute_unknown_partial_work",
    "stop_rule": "fixed_1000_each_no_significance_based_stopping",
}
BUDGET = {
    "max_workers": 8, "max_aggregate_rss_bytes": 2147483648, "max_case_wall_seconds": 300,
    "proposed_total_wall_seconds": 86400, "historical_seconds": 667.6336285640136,
    "historical_datasets": 192, "linear_reference_seconds_for_12000": 41727.10178525085,
    "cost_status": "unverified_extrapolation_requires_admission_no_run_authorization",
    "storage_status": "missing_measured_evidence_retention_admission",
    "historical_logical_evidence_bytes_approx": 105900000,
    "linear_logical_evidence_bytes_for_12000_approx": 6618750000,
}
INPUT_POLICY = {
    "minimum_measurements": 2, "minimum_value": -1000000, "maximum_value": 1000000,
    "retention": "exact_ordered_rows_and_binary64_values_or_both_methods_unavailable",
    "redraw_for_positivity": False, "transformations": False,
}
ENGINEERING_PROBE = {
    "status": "specified_not_executed", "fixture_source": "validation/variance_sensitivity/Program.cs",
    "fixture_function": "Fixture", "fixture_kind": "fixed_deterministic_formula_no_rng_no_study_coordinates",
    "fresh_sequential_calls": 3, "fresh_parallel_calls": 8, "max_total_calls": 11,
    "max_total_wall_seconds": 300, "method_configuration": "gaussian_component_family_B199_E100_v1",
    "admission_wall_projection": "2*max(sequential_case_seconds,parallel_batch_seconds)*12000/8<=86400",
    "admission_storage": "2*max_retained_case_bytes*12000+1073741824<=available_storage_bytes",
    "scientific_outcome_use": "none", "admission_limits": "fixture_only_no_worst_case_runtime_guarantee",
    "native_seed": 52000000, "per_process_cpu_limit": 1,
    "backups": "disabled_no_restore_or_cache_replay",
    "completeness": "existing_Round50_Complete_observer_all_callbacks_once_all_keys_counts_finite_and_ownership_each_call",
    "measured_work": "input_build_full_variance_run_summary_route_serialization_and_process_lifecycle",
}
READINESS = {
    "adapter": "missing", "binary_runtime_binding": "missing", "cost_admission": "missing",
    "final_execution_freeze": "missing", "data_generated": False,
}
EXCLUDED_CANDIDATE = {
    "id": "within_entity_variance_welch_centered_bootstrap_v1",
    "status": "design_only_requires_separate_protocol_and_asymmetric_tail_nulls", "admitted": False,
}
BLOCKERS = (
    ("adapter_missing", "A separately tested generation and method adapter is missing."),
    ("binary_binding_missing", "A frozen native binary identity is missing."),
    ("runtime_binding_missing", "Verified runtime, RNG and numerical-library bindings are missing."),
    ("cost_admission_missing", "Measured workload, resource-cost and evidence-storage admission are missing."),
    ("final_execution_freeze_missing", "Final execution-freeze acceptance is missing."),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_keys(value, keys, where):
    require(type(value) is dict, where + ": expected object")
    require(set(value) == set(keys), where + ": missing/unknown fields " +
            str(sorted(set(value) ^ set(keys))))


def exact_contract(value, expected, where):
    """Compare recursively, distinguishing bool, int, float, null and strings."""
    require(type(value) is type(expected), where + ": wrong value type")
    if type(expected) is dict:
        exact_keys(value, expected, where)
        for key in expected:
            exact_contract(value[key], expected[key], where + "." + key)
    elif type(expected) is list:
        require(len(value) == len(expected), where + ": wrong array length")
        for index, (actual, wanted) in enumerate(zip(value, expected)):
            exact_contract(actual, wanted, f"{where}[{index}]")
    else:
        require(value == expected, where + ": differs from frozen prospective contract")


def loads(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate JSON member: " + key)
            value[key] = item
        return value

    def invalid(value):
        raise ValueError("nonfinite JSON literal: " + value)

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)

    def finite(item):
        if type(item) is float:
            require(math.isfinite(item), "overflow/nonfinite JSON number")
        elif type(item) is dict:
            for child in item.values():
                finite(child)
        elif type(item) is list:
            for child in item:
                finite(child)

    finite(value)
    return value


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def canonical_sha256(value):
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False, allow_nan=False).encode("utf-8"))


def local_file(root, relative):
    """All callers supply an exact allowlisted repository-relative filename."""
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts,
            "invalid local binding path")
    current = Path(root)
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), "symlink is not a source binding: " + str(relative))
    require(current.is_file(), "missing bound file: " + str(relative))
    return current


def derived_truth(cell):
    """Both groups share the declared shape in this fixed twelve-cell design."""
    left, right = cell["group0"], cell["group1"]
    within = left["within_sd"] == right["within_sd"]
    between = left["between_sd"] == right["between_sd"]
    return {"within_null": within, "between_null": between,
            "variance_family_null": within and between,
            "summary_global_null": left == right}


def expected_cells():
    # Explicit ordered cells; no Cartesian-grid expansion or adaptive additions.
    specs = (
        ("gaussian_global_null", 16, 40, 20, 1, 1, "gaussian", "gaussian"),
        ("gaussian_location_only", 16, 40, 22, 1, 1, "gaussian", "gaussian"),
        ("gaussian_within_sd_x2", 16, 40, 20, 2, 1, "gaussian", "gaussian"),
        ("gaussian_between_sd_x2", 16, 40, 20, 1, 2, "gaussian", "gaussian"),
        ("gaussian_both_sd_x2", 16, 40, 20, 2, 2, "gaussian", "gaussian"),
        ("t5_both_global_null", 16, 40, 20, 1, 1, "standardized_t5", "standardized_t5"),
        ("gaussian_within_sd_x1_25", 16, 40, 20, 1.25, 1, "gaussian", "gaussian"),
        ("gaussian_between_sd_x1_25", 16, 40, 20, 1, 1.25, "gaussian", "gaussian"),
        ("t5_residual_global_null", 16, 40, 20, 1, 1, "standardized_t5", "gaussian"),
        ("t5_intercept_global_null", 16, 40, 20, 1, 1, "gaussian", "standardized_t5"),
        ("small_gaussian_global_null", 8, 5, 20, 1, 1, "gaussian", "gaussian"),
        ("small_t5_both_global_null", 8, 5, 20, 1, 1, "standardized_t5", "standardized_t5"),
    )
    cells = []
    for index, (name, entities, repeats, mean, within, between, wdist, bdist) in enumerate(specs):
        cell = {
            "index": index, "id": f"C{index:02d}", "name": name,
            "entities_per_group": entities, "repeats_per_entity": repeats,
            "group0": {"mean": 20, "within_sd": 1, "between_sd": 1},
            "group1": {"mean": mean, "within_sd": within, "between_sd": between},
            "within_distribution": wdist, "between_distribution": bdist,
        }
        cell["truth"] = derived_truth(cell)
        cells.append(cell)
    return cells


def null_endpoint_pairs(cells):
    endpoints = (("within_null", "within", 0.025), ("between_null", "between", 0.025),
                 ("variance_family_null", "variance_family", 0.05),
                 ("summary_global_null", "summary_family", 0.05))
    return [{"cell_id": cell["id"], "endpoint": endpoint, "nominal_alpha": alpha}
            for cell in cells for truth, endpoint, alpha in endpoints if derived_truth(cell)[truth]]


def verify_source_bindings(config, root):
    bindings = config["source_bindings"]
    exact_keys(bindings, SOURCE_PATHS, "source_bindings")
    for relative in SOURCE_PATHS:
        wanted = bindings[relative]
        require(type(wanted) is str and re.fullmatch(r"[0-9a-f]{64}", wanted) is not None,
                relative + ": invalid SHA-256")
        require(sha256_file(local_file(root, relative)) == wanted,
                relative + ": source/evidence SHA-256 drift")

    infrastructure = local_file(root, "Core/ScientificInfrastructure.cs").read_text(encoding="utf-8")
    version = re.search(r'public const string Version = "([^"]+)";', infrastructure)
    engine = re.search(r'public const string EngineVersion = "([^"]+)";', infrastructure)
    require(version is not None and version.group(1) == "1.4.0", "application version mismatch")
    require(engine is not None and engine.group(1) == "1.6.2", "engine version mismatch")
    registry = local_file(root, "Core/MetricRegistry.cs").read_text(encoding="utf-8")
    active = re.findall(r'^\s*new\("([^"]+)"[^\n]+, true(?:,|\))', registry, flags=re.MULTILINE)
    require(active == list(METRIC_KEYS), "production active metric registry/order mismatch")
    analysis = local_file(root, "Core/AnalysisEngine.cs").read_text(encoding="utf-8")
    require("internal static readonly string[] MetricKeys = MetricRegistry.LegacyKeys;" in analysis,
            "production analysis is not bound to the inspected active metric registry")
    suite = loads(local_file(root, "validation/benchmark-suite-v1.1.json").read_bytes())
    require(type(suite) is dict, "suite evidence must be an object")
    require(suite.get("suite_version") == config["suite_version"], "suite version mismatch")
    return {"application_version": version.group(1), "engine_version": engine.group(1),
            "suite_version": config["suite_version"],
            "method_ids": [method["id"] for method in config["methods"]]}


def validate_config(config, root=ROOT):
    exact_keys(config, TOP_FIELDS, "config")
    for key, expected in {
        "schema": "mvs-prospective-ademp/v1", "protocol_id": PROTOCOL_ID,
        "status": "design_frozen_execution_blocked", "evidence_role": "prospective_design_no_outcomes",
        "suite_version": "1.1.0", "study_phase": "independent_seed_evaluation_of_preselected_methods",
        "outer_repetitions_per_cell": REPETITIONS,
    }.items():
        exact_contract(config[key], expected, key)
    exact_contract(config["cells"], expected_cells(), "cells")
    exact_contract(config["methods"], METHODS, "methods")
    exact_keys(config["rng"], RNG, "rng")
    require(type(config["rng"]["data_stream"]) is int and
            type(config["rng"]["native_seed_stream"]) is int and
            config["rng"]["data_stream"] != config["rng"]["native_seed_stream"],
            "rng stream namespaces must be distinct integers")
    for key, expected in (("rng", RNG), ("inference", INFERENCE), ("failure_policy", FAILURE_POLICY),
                          ("budget", BUDGET), ("readiness", READINESS),
                          ("excluded_candidate", EXCLUDED_CANDIDATE), ("input_policy", INPUT_POLICY),
                          ("engineering_probe", ENGINEERING_PROBE)):
        exact_contract(config[key], expected, key)
    pairs = null_endpoint_pairs(config["cells"])
    require(len(pairs) == config["inference"]["null_endpoint_count"] == 31,
            "derived true-null endpoint count mismatch")
    alternative = config["inference"]["alternative_endpoints"]
    for key, truth in (("within_component", "within_null"), ("between_component", "between_null")):
        require(alternative[key] == [cell["id"] for cell in config["cells"]
                                     if not derived_truth(cell)[truth]],
                key + ": alternative endpoint truth mismatch")
    require(alternative["both_components_correctly_detected"] == [
        cell["id"] for cell in config["cells"]
        if not derived_truth(cell)["within_null"] and not derived_truth(cell)["between_null"]],
        "joint-component alternative truth mismatch")
    # This arithmetic describes a prior workload; it is not a measured admission.
    reference = config["budget"]["historical_seconds"] * 12000 / config["budget"]["historical_datasets"]
    require(math.isclose(reference, config["budget"]["linear_reference_seconds_for_12000"],
                         rel_tol=1e-15, abs_tol=0), "historical cost arithmetic mismatch")
    identity = verify_source_bindings(config, root)
    return {"schema": "mvs-prospective-ademp-check/v1", "configuration_valid": True,
            "status": "configuration_valid_execution_blocked", "protocol_id": PROTOCOL_ID,
            "cell_count": 12, "outer_repetitions_per_cell": REPETITIONS,
            "planned_dataset_count": 12000, "true_null_endpoint_count": len(pairs),
            "execution_ready": False, "scientific_datasets_generated": 0,
            "scientific_acceptance": "not_assessed", "identity": identity}


def load_config(path, root=ROOT):
    raw = Path(path).read_bytes()
    config = loads(raw)
    check = validate_config(config, root)
    check["config_sha256"] = sha256_bytes(raw)
    return config, check


def execution_readiness(config, root=ROOT):
    result = validate_config(config, root)
    result.update(status="execution_blocked", blockers=[
        {"id": key, "reason": message} for key, message in BLOCKERS])
    return result


def build_plan(config_path, root=ROOT):
    """Prepare identities and coordinate labels; instantiate no RNG or methods."""
    config, check = load_config(config_path, root)
    artifacts = {relative: sha256_file(local_file(root, relative))
                 for relative in (VALIDATOR_PATH, DOCUMENT_PATH)}
    require(artifacts[VALIDATOR_PATH] == sha256_file(__file__),
            "executing validator differs from the plan's validator binding")
    rng = config["rng"]
    cases, ids, coordinate_set, native_seeds = [], set(), set(), set()
    cells = []
    for cell in config["cells"]:
        cells.append({"id": cell["id"], "index": cell["index"], "name": cell["name"],
                      "planned_replications": REPETITIONS, "cell_sha256": canonical_sha256(cell),
                      "configuration": deepcopy(cell)})
        for replication in range(REPETITIONS):
            case_id = f'{PROTOCOL_ID}/{cell["id"]}/R{replication:04d}'
            data = [rng["master"], rng["phase"], rng["data_stream"], cell["index"], replication]
            native = [rng["master"], rng["phase"], rng["native_seed_stream"], cell["index"], replication]
            native_seed = rng["native_seed_base"] + REPETITIONS * cell["index"] + replication
            require(0 <= native_seed <= 2147483647 and native_seed not in native_seeds,
                    "duplicate or out-of-int32-range native seed")
            native_seeds.add(native_seed)
            require(case_id not in ids, "duplicate planned case ID")
            ids.add(case_id)
            for coordinates in (data, native):
                key = tuple(coordinates)
                require(key not in coordinate_set, "duplicate/colliding seed coordinates")
                coordinate_set.add(key)
            cases.append({"id": case_id, "cell_id": cell["id"], "cell_index": cell["index"],
                          "replication_zero_based": replication, "data_coordinates": data,
                          "native_seed_coordinates": native, "native_seed": native_seed})
    require(len(cases) == 12000 and len(coordinate_set) == 24000 and len(native_seeds) == 12000,
            "incomplete planned ID or coordinate enumeration")
    # Catch changes while enumerating before opening an output file.
    verify_source_bindings(config, root)
    require(sha256_file(config_path) == check["config_sha256"], "config changed during planning")
    for relative, wanted in artifacts.items():
        require(sha256_file(local_file(root, relative)) == wanted,
                relative + ": changed during planning")
    return {
        "schema": "mvs-prospective-ademp-plan/v1", "protocol_id": PROTOCOL_ID,
        "status": "planned_only", "execution_ready": False,
        "config_sha256": check["config_sha256"], "identity": check["identity"],
        "artifact_bindings": artifacts, "source_bindings": deepcopy(config["source_bindings"]),
        "cell_count": 12, "outer_repetitions_per_cell": REPETITIONS,
        "planned_dataset_count": len(cases), "planned_method_evaluations": len(cases) * 2,
        "scientific_datasets_generated": 0, "native_invocations": 0, "rng_instantiations": 0,
        "data_seed_coordinates_only": True, "native_seed_derivation": rng["native_seed_derivation"],
        "native_seed_range": [min(native_seeds), max(native_seeds)],
        "random_stream_limit": "unique root seeds and coordinates do not prove independent internal pseudorandom streams",
        "true_null_endpoint_pairs": null_endpoint_pairs(config["cells"]),
        "blockers": [{"id": key, "reason": message} for key, message in BLOCKERS],
        "cells": cells, "cases": cases,
    }


def write_once(path, value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", nargs="?", const="", metavar="CONFIG")
    actions.add_argument("--plan", type=Path, metavar="NEW_OUTPUT_JSON")
    actions.add_argument("--check-execution-readiness", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        require(root.is_dir(), "--root must be a source directory")
        if args.check and args.config:
            require(Path(args.check).resolve() == args.config.resolve(),
                    "--check CONFIG and --config name different inputs")
        path = Path(args.check) if args.check else args.config or root / CONFIG_PATH
        if args.plan is not None:
            plan = build_plan(path, root)
            write_once(args.plan, plan)
            result = {"status": "planned_only", "execution_ready": False,
                      "config_sha256": plan["config_sha256"],
                      "plan_sha256": sha256_file(args.plan), "planned_dataset_count": 12000,
                      "scientific_datasets_generated": 0, "output": str(args.plan)}
        else:
            config, result = load_config(path, root)
            if args.check_execution_readiness:
                result["status"] = "execution_blocked"
                result["blockers"] = [{"id": key, "reason": message} for key, message in BLOCKERS]
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 3 if args.check_execution_readiness else 0
    except (ValueError, OSError, TypeError, RecursionError) as error:
        print(json.dumps({"status": "invalid_or_blocked", "execution_ready": False,
                          "error": {"type": type(error).__name__, "message": str(error)}},
                         ensure_ascii=False, sort_keys=True, allow_nan=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
