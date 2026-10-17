"""Literal configuration mutations and plan checks; no scientific simulation."""
import ast
import builtins
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import prospective_ademp as p


def config():
    return p.loads((p.ROOT / p.CONFIG_PATH).read_bytes())


def objects(value, path=()):
    if type(value) is dict:
        yield path
        for key, child in value.items():
            yield from objects(child, path + (key,))
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from objects(child, path + (index,))


def leaves(value, path=()):
    if type(value) is dict:
        for key, child in value.items():
            yield from leaves(child, path + (key,))
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from leaves(child, path + (index,))
    else:
        yield path, value


def at(value, path):
    for key in path:
        value = value[key]
    return value


def copy_tree(root):
    for relative in (*p.SOURCE_PATHS, p.CONFIG_PATH, p.VALIDATOR_PATH, p.DOCUMENT_PATH):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p.ROOT / relative, destination)


class ConfigurationTests(unittest.TestCase):
    def test_current_configuration_and_versions(self):
        result = p.validate_config(config())
        self.assertEqual(result["planned_dataset_count"], 12000)
        self.assertEqual(result["true_null_endpoint_count"], 31)
        self.assertEqual(result["identity"]["engine_version"], "1.6.2")
        self.assertEqual(result["identity"]["application_version"], "1.4.0")
        self.assertEqual(result["scientific_acceptance"], "not_assessed")
        self.assertFalse(result["execution_ready"])
        self.assertEqual(result["scientific_datasets_generated"], 0)

    def test_duplicate_keys_at_all_depths_and_nonfinite_json(self):
        invalid = ('{"a":1,"a":2}', '{"outer":{"a":1,"a":2}}',
                   '[{"x":0,"x":0}]', '{"a":NaN}', '[Infinity]', '[-Infinity]',
                   '{"x":1e999}', '{"x":[-1e999]}')
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                p.loads(raw)

    def test_every_object_rejects_unknown_fields(self):
        original = config()
        for path in objects(original):
            mutated = deepcopy(original)
            at(mutated, path)["unexpected"] = "not allowed"
            with self.subTest(path=path), self.assertRaises(ValueError):
                p.validate_config(mutated)

    def test_every_object_rejects_missing_fields(self):
        original = config()
        for path in objects(original):
            for key in at(original, path):
                mutated = deepcopy(original)
                del at(mutated, path)[key]
                with self.subTest(path=path, key=key), self.assertRaises(ValueError):
                    p.validate_config(mutated)

    def test_every_frozen_leaf_rejects_mutation(self):
        original = config()
        for path, value in leaves(original):
            changed = (not value if type(value) is bool else value + 1 if type(value) in (int, float)
                       else value + "_changed" if type(value) is str else "not_null")
            mutated = deepcopy(original)
            at(mutated, path[:-1])[path[-1]] = changed
            with self.subTest(path=path), self.assertRaises(ValueError):
                p.validate_config(mutated)

    def test_boolean_numeric_and_null_types_are_not_interchangeable(self):
        original = config()
        for path, value in leaves(original):
            if type(value) is bool:
                changed = int(value)
            elif type(value) is int:
                changed = float(value)
            elif type(value) is float:
                changed = str(value)
            elif value is None:
                changed = False
            else:
                continue
            mutated = deepcopy(original)
            at(mutated, path[:-1])[path[-1]] = changed
            with self.subTest(path=path), self.assertRaises(ValueError):
                p.validate_config(mutated)

    def test_exact_ordered_twelve_cells(self):
        for operation in (lambda x: x.pop(), lambda x: x.append(deepcopy(x[0])),
                          lambda x: x.reverse(), lambda x: x.__setitem__(1, deepcopy(x[0]))):
            value = config()
            operation(value["cells"])
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                p.validate_config(value)
        cells = p.expected_cells()
        self.assertEqual([cell["id"] for cell in cells], [f"C{i:02d}" for i in range(12)])
        self.assertEqual([cell["entities_per_group"] for cell in cells], [16] * 10 + [8] * 2)
        self.assertEqual([cell["repeats_per_entity"] for cell in cells], [40] * 10 + [5] * 2)

    def test_truth_derived_independently_and_exact_31_endpoint_inventory(self):
        value = config()
        self.assertEqual(p.derived_truth(value["cells"][1]), {
            "within_null": True, "between_null": True,
            "variance_family_null": True, "summary_global_null": False})
        pairs = p.null_endpoint_pairs(value["cells"])
        wanted = {
            "within": [0, 1, 3, 5, 7, 8, 9, 10, 11],
            "between": [0, 1, 2, 5, 6, 8, 9, 10, 11],
            "variance_family": [0, 1, 5, 8, 9, 10, 11],
            "summary_family": [0, 5, 8, 9, 10, 11],
        }
        for endpoint, indices in wanted.items():
            self.assertEqual([item["cell_id"] for item in pairs if item["endpoint"] == endpoint],
                             [f"C{i:02d}" for i in indices])
        self.assertEqual(len(pairs), 31)
        self.assertEqual(len({(item["cell_id"], item["endpoint"]) for item in pairs}), 31)
        for item in pairs:
            self.assertEqual(item["nominal_alpha"], .025 if item["endpoint"] in ("within", "between") else .05)

    def test_two_methods_and_frozen_registry_order(self):
        for key in ("methods",):
            for mutation in (lambda x: x.reverse(), lambda x: x.append(deepcopy(x[0])), lambda x: x.pop()):
                value = config()
                mutation(value[key])
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    p.validate_config(value)
        for mutation in (lambda x: x.reverse(), lambda x: x.pop(), lambda x: x.append("huber_location"),
                         lambda x: x.__setitem__(1, "median")):
            value = config()
            mutation(value["methods"][1]["metric_keys"])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                p.validate_config(value)

    def test_strict_reference_grid_and_no_failure_denominator_replacement(self):
        method = config()["methods"][0]
        self.assertEqual(method["reference_replications"], 199)
        self.assertEqual([k for k in range(200) if 2 * (1 + k) / 200 < .05], [0, 1, 2, 3])
        self.assertEqual(method["zero_failure_largest_rejecting_exceedance"], 3)
        self.assertIn("finite_reference_count", method["p_formula"])
        value = config()
        value["methods"][0]["p_formula"] = "(1+inclusive_exceedances)/(requested_reference_count+1)"
        with self.assertRaises(ValueError):
            p.validate_config(value)

    def test_rng_namespace_collisions_and_index_aliases_rejected(self):
        changes = (("native_seed_stream", 0), ("data_stream", 1), ("phase", 0),
                   ("master", 20260904), ("data_stream", False), ("native_seed_base", 2147483647))
        for key, changed in changes:
            value = config()
            value["rng"][key] = changed
            with self.subTest(key=key, changed=changed), self.assertRaises(ValueError):
                p.validate_config(value)
        value = config()
        value["rng"]["coordinates"][-1] = "worker_index"
        with self.assertRaises(ValueError):
            p.validate_config(value)

    def test_failure_policy_cannot_be_relaxed(self):
        mutations = {"dataset_replacement": True, "retry_limit": 1, "drop_failed_repetitions": True,
                     "family_outcome": "unknown_is_false", "rate_bounds": "complete_cases_only",
                     "resume": "retry_unknown", "stop_rule": "stop_when_significant"}
        for key, changed in mutations.items():
            value = config()
            value["failure_policy"][key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_config(value)

    def test_no_tolerance_pass_or_power_winner(self):
        for key, changed in (("acceptance_tolerance", .01), ("power_superiority_gate", .8),
                             ("no_inflation_detected_status", "pass")):
            value = config()
            value["inference"][key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_config(value)

    def test_cannot_promote_design_to_executed_or_admit_candidate(self):
        for key, changed in (("status", "completed"), ("evidence_role", "validated")):
            value = config()
            value[key] = changed
            with self.assertRaises(ValueError):
                p.validate_config(value)
        for key in ("adapter", "binary_runtime_binding", "cost_admission", "final_execution_freeze"):
            value = config()
            value["readiness"][key] = "ready"
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_config(value)
        value = config()
        value["excluded_candidate"]["admitted"] = True
        with self.assertRaises(ValueError):
            p.validate_config(value)

    def test_readiness_explicitly_blocks_all_execution_prerequisites(self):
        result = p.execution_readiness(config())
        self.assertEqual(result["status"], "execution_blocked")
        self.assertFalse(result["execution_ready"])
        self.assertEqual({item["id"] for item in result["blockers"]}, {
            "adapter_missing", "binary_binding_missing", "runtime_binding_missing",
            "cost_admission_missing", "final_execution_freeze_missing"})

    def test_engineering_probe_is_fixed_bounded_and_unexecuted(self):
        probe = config()["engineering_probe"]
        self.assertEqual(probe["fresh_sequential_calls"] + probe["fresh_parallel_calls"], 11)
        self.assertEqual(probe["max_total_calls"], 11)
        self.assertEqual(probe["max_total_wall_seconds"], 300)
        self.assertEqual(probe["status"], "specified_not_executed")
        self.assertEqual(probe["scientific_outcome_use"], "none")
        self.assertEqual(probe["native_seed"], 52000000)
        self.assertEqual(probe["per_process_cpu_limit"], 1)
        self.assertEqual(probe["backups"], "disabled_no_restore_or_cache_replay")
        self.assertEqual(probe["completeness"],
                         "existing_Round50_Complete_observer_all_callbacks_once_all_keys_counts_finite_and_ownership_each_call")
        self.assertEqual(probe["measured_work"],
                         "input_build_full_variance_run_summary_route_serialization_and_process_lifecycle")
        for key, changed in (("fixture_function", "RandomFixture"), ("fresh_sequential_calls", 4),
                             ("fresh_parallel_calls", 9), ("max_total_calls", 12),
                             ("max_total_wall_seconds", 301), ("status", "completed"),
                             ("native_seed", 1540000000), ("per_process_cpu_limit", 8),
                             ("backups", "enabled"), ("completeness", "exit_zero_only"),
                             ("measured_work", "inference_only_without_serialization")):
            value = config()
            value["engineering_probe"][key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_config(value)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        copy_tree(self.root)

    def test_every_source_or_evidence_hash_drift_rejected(self):
        value = config()
        for relative in p.SOURCE_PATHS:
            path = self.root / relative
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.subTest(path=relative), self.assertRaisesRegex(ValueError, "SHA-256 drift"):
                p.validate_config(value, self.root)
            path.write_bytes(original)

    def test_missing_binding_file_and_missing_hash_rejected(self):
        (self.root / p.SOURCE_PATHS[0]).unlink()
        with self.assertRaisesRegex(ValueError, "missing bound file"):
            p.validate_config(config(), self.root)
        value = config()
        del value["source_bindings"][p.SOURCE_PATHS[0]]
        with self.assertRaises(ValueError):
            p.validate_config(value)

    def test_source_symlink_rejected_even_if_bytes_match(self):
        relative = p.SOURCE_PATHS[0]
        path = self.root / relative
        path.unlink()
        path.symlink_to(p.ROOT / relative)
        with self.assertRaisesRegex(ValueError, "symlink"):
            p.validate_config(config(), self.root)

    def test_rebound_version_drift_is_still_rejected(self):
        relative = "Core/ScientificInfrastructure.cs"
        path = self.root / relative
        path.write_text(path.read_text().replace('EngineVersion = "1.6.2"', 'EngineVersion = "1.6.3"'))
        value = config()
        value["source_bindings"][relative] = p.sha256_file(path)
        with self.assertRaisesRegex(ValueError, "engine version mismatch"):
            p.validate_config(value, self.root)

    def test_rebound_production_registry_drift_is_still_rejected(self):
        relative = "Core/MetricRegistry.cs"
        path = self.root / relative
        path.write_text(path.read_text().replace('new("median",', 'new("changed_median",', 1))
        value = config()
        value["source_bindings"][relative] = p.sha256_file(path)
        with self.assertRaisesRegex(ValueError, "registry/order mismatch"):
            p.validate_config(value, self.root)

    def test_rebound_suite_version_drift_is_still_rejected(self):
        relative = "validation/benchmark-suite-v1.1.json"
        path = self.root / relative
        value = json.loads(path.read_text())
        value["suite_version"] = "1.2.0"
        path.write_text(json.dumps(value))
        changed = config()
        changed["source_bindings"][relative] = p.sha256_file(path)
        with self.assertRaisesRegex(ValueError, "suite version mismatch"):
            p.validate_config(changed, self.root)

    def test_plan_requires_companion_document_and_matching_validator(self):
        document = self.root / p.DOCUMENT_PATH
        document.unlink()
        p.validate_config(config(), self.root)
        with self.assertRaisesRegex(ValueError, "missing bound file"):
            p.build_plan(self.root / p.CONFIG_PATH, self.root)
        document.write_text("Literal test document; no scientific outcomes.")
        (self.root / p.VALIDATOR_PATH).write_text("# changed validator\n")
        with self.assertRaisesRegex(ValueError, "executing validator differs"):
            p.build_plan(self.root / p.CONFIG_PATH, self.root)


class PlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = p.build_plan(p.ROOT / p.CONFIG_PATH)

    def test_all_12000_ids_coordinates_and_native_seeds_unique(self):
        cases = self.plan["cases"]
        self.assertEqual(len(cases), 12000)
        self.assertEqual(len({item["id"] for item in cases}), 12000)
        coordinates = [tuple(item[key]) for item in cases
                       for key in ("data_coordinates", "native_seed_coordinates")]
        self.assertEqual(len(coordinates), 24000)
        self.assertEqual(len(set(coordinates)), 24000)
        self.assertEqual(Counter(item["cell_id"] for item in cases),
                         {f"C{i:02d}": 1000 for i in range(12)})
        seeds = [item["native_seed"] for item in cases]
        self.assertEqual(seeds, list(range(1540000000, 1540012000)))
        self.assertTrue(all(type(seed) is int and 0 <= seed <= 2147483647 for seed in seeds))
        for case in cases:
            i, r = case["cell_index"], case["replication_zero_based"]
            self.assertEqual(case["id"], f"{p.PROTOCOL_ID}/C{i:02d}/R{r:04d}")
            self.assertEqual(case["data_coordinates"], [2026101754, 1, 0, i, r])
            self.assertEqual(case["native_seed_coordinates"], [2026101754, 1, 1, i, r])

    def test_plan_binds_every_cell_and_all_artifacts(self):
        self.assertEqual(self.plan["config_sha256"], p.sha256_file(p.ROOT / p.CONFIG_PATH))
        self.assertEqual(self.plan["source_bindings"], config()["source_bindings"])
        for relative, digest in self.plan["artifact_bindings"].items():
            self.assertEqual(digest, p.sha256_file(p.ROOT / relative))
        for actual, expected in zip(self.plan["cells"], config()["cells"]):
            self.assertEqual(actual["configuration"], expected)
            self.assertEqual(actual["cell_sha256"], p.canonical_sha256(expected))
            self.assertEqual(actual["planned_replications"], 1000)
        self.assertEqual(self.plan["planned_method_evaluations"], 24000)
        self.assertEqual(self.plan["status"], "planned_only")
        self.assertFalse(self.plan["execution_ready"])
        for key in ("scientific_datasets_generated", "native_invocations", "rng_instantiations"):
            self.assertEqual(self.plan[key], 0)

    def test_plans_are_deterministic_without_timestamps_or_host_paths(self):
        other = p.build_plan(p.ROOT / p.CONFIG_PATH)
        self.assertEqual(other, self.plan)
        self.assertNotIn("timestamp", self.plan)
        self.assertNotIn("host", self.plan)
        self.assertNotIn("root", self.plan)

    def test_plan_imports_no_rng_and_launches_no_process(self):
        original = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in ("random", "numpy", "subprocess", "scipy"):
                raise AssertionError("Forbidden planning dependency: " + name)
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded), \
             patch("os.system", side_effect=AssertionError("No process execution")), \
             patch("subprocess.run", side_effect=AssertionError("No native execution")):
            result = p.build_plan(p.ROOT / p.CONFIG_PATH)
        self.assertEqual(len(result["cases"]), 12000)
        source = ast.parse(Path(p.__file__).read_text())
        imports = {alias.name.split(".")[0] for node in ast.walk(source)
                   if isinstance(node, ast.Import) for alias in node.names}
        imports |= {node.module.split(".")[0] for node in ast.walk(source)
                    if isinstance(node, ast.ImportFrom)}
        self.assertFalse(imports & {"random", "numpy", "subprocess", "scipy"})

    def test_write_once_refuses_file_directory_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "plan.json"
            p.write_once(path, {"literal": True})
            first = path.read_bytes()
            with self.assertRaises(FileExistsError):
                p.write_once(path, self.plan)
            self.assertEqual(path.read_bytes(), first)
            with self.assertRaises(FileExistsError):
                p.write_once(root, self.plan)
            link = root / "link.json"
            link.symlink_to(path)
            with self.assertRaises(FileExistsError):
                p.write_once(link, self.plan)
            self.assertEqual(path.read_bytes(), first)


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(p.ROOT / p.VALIDATOR_PATH),
                               "--root", str(p.ROOT), *map(str, args)], capture_output=True,
                              text=True, check=False, timeout=30)

    def test_check_default_and_explicit_path(self):
        for args in (("--check",), ("--check", p.ROOT / p.CONFIG_PATH),
                     ("--config", p.ROOT / p.CONFIG_PATH, "--check")):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["execution_ready"])

    def test_readiness_is_nonzero_with_five_blockers(self):
        result = self.run_cli("--check-execution-readiness")
        self.assertEqual(result.returncode, 3)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "execution_blocked")
        self.assertEqual(len(output["blockers"]), 5)

    def test_actual_plan_cli_is_deterministic_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "first.json", Path(folder) / "second.json"
            for target in (first, second):
                result = self.run_cli("--plan", target)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "planned_only")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            before = first.read_bytes()
            result = self.run_cli("--plan", first)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(first.read_bytes(), before)
            self.assertEqual(json.loads(result.stderr)["error"]["type"], "FileExistsError")

    def test_invalid_duplicate_unknown_and_hash_mutations_nonzero_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "bad.json", Path(folder) / "plan.json"
            changed = config()
            changed["unexpected"] = True
            bad_hash = config()
            bad_hash["source_bindings"][p.SOURCE_PATHS[0]] = "0" * 64
            for raw in ('{"schema":1,"schema":2}', json.dumps(changed), json.dumps(bad_hash),
                        '{"value":1e999}'):
                source.write_text(raw)
                for args in (("--check", source), ("--config", source, "--plan", output),
                             ("--config", source, "--check-execution-readiness")):
                    result = self.run_cli(*args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertEqual(json.loads(result.stderr)["status"], "invalid_or_blocked")

    def test_no_execution_option_and_mutually_exclusive_actions(self):
        for args in (("--execute",), ("--run",), ("--check", "--check-execution-readiness"), ()):
            result = self.run_cli(*args)
            self.assertNotEqual(result.returncode, 0)

    def test_conflicting_config_paths_rejected(self):
        result = self.run_cli("--check", p.ROOT / p.CONFIG_PATH, "--config", "different.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different inputs", result.stderr)


if __name__ == "__main__":
    unittest.main()
