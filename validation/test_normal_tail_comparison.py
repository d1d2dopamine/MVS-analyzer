"""Synthetic comparison-driver tests. No native A/B candidates are executed."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import unittest

import mpmath as mp
import run_normal_tail_comparison as driver


def fp(value: float) -> dict:
    return {"bits": driver.bits(value),
            "kind": "nan" if math.isnan(value) else "positive_infinity" if value == math.inf else "negative_infinity" if value == -math.inf else "finite",
            "value": value if math.isfinite(value) else None,
            "roundTrip": repr(value)}


def identity(variant="A") -> dict:
    return {"experimental": True, "variant": variant,
            "sourceTreeSha256": "source-tree", "sourceAnalysisSha256": "source-analysis",
            "variantAnalysisSha256": "variant-analysis", "programSourceSha256": "program",
            "buildManifestSha256": "build", "coreDllSha256": "core", "harnessDllSha256": "harness",
            "formulaHash": "formula", "formulaVersion": "version", "engineVersion": "engine",
            "decisionPolicy": "policy", "runtime": "runtime", "architecture": "architecture",
            "mathNetVersion": None, "mathNetDllSha256": None, "mathNetPackageSha256": "package"}


def assess(value: float, reference: mp.mpf, rounded: float | None = None) -> dict:
    if rounded is None:
        rounded = driver.from_bits(driver.round_mpf_bits(reference))
    log_reference = mp.log(reference) if reference else mp.ninf
    return driver.accuracy(driver.bits(value), mp.nstr(reference, 240), mp.nstr(log_reference, 240), driver.bits(rounded))


class SerializationAndBindingTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"value": 1, "value": 2}')
            with self.assertRaisesRegex(driver.EvidenceError, "duplicate JSON key"):
                driver.read_json(path)

    def test_nonstandard_json_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for token in ("NaN", "Infinity", "-Infinity"):
                path.write_text('{"value": ' + token + '}')
                with self.assertRaisesRegex(driver.EvidenceError, "nonstandard JSON"):
                    driver.read_json(path)

    def test_signed_zero_and_nonfinite_bits_preserved(self):
        for value in (0., -0., math.inf, -math.inf, math.nan):
            self.assertEqual(driver.fp_bits(fp(value)), driver.bits(value))
        self.assertNotEqual(driver.fp_bits(fp(0.)), driver.fp_bits(fp(-0.)))

    def test_corrupt_fp_kind_value_roundtrip_rejected(self):
        for key, wrong in (("kind", "nan"), ("value", 2.), ("roundTrip", "2")):
            record = fp(1.)
            record[key] = wrong
            with self.assertRaises(driver.EvidenceError):
                driver.fp_bits(record)
        record = fp(math.nan)
        record["value"] = 0
        with self.assertRaises(driver.EvidenceError):
            driver.fp_bits(record)

    def test_malformed_bits_rejected(self):
        for value in ("0", "g" * 16, "0" * 17, 123):
            with self.assertRaises(driver.EvidenceError):
                driver.from_bits(value)

    def test_identity_wrong_variant_hash_and_missing_field_rejected(self):
        expected = identity()
        driver.validate_identity(expected, expected, "A")
        wrong = dict(expected, coreDllSha256="different")
        with self.assertRaises(driver.EvidenceError):
            driver.validate_identity(wrong, expected, "A")
        with self.assertRaises(driver.EvidenceError):
            driver.validate_identity(expected, expected, "B")
        incomplete = dict(expected)
        del incomplete["formulaHash"]
        with self.assertRaisesRegex(driver.EvidenceError, "incomplete"):
            driver.validate_identity(expected, incomplete, "A")

    def test_binding_tamper_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source"
            path.write_text("original")
            binding = {"path": "source", "sha256": driver.sha256(path)}
            self.assertEqual(len(driver.verify_bound_files([binding], root)), 1)
            with self.assertRaisesRegex(driver.EvidenceError, "duplicate binding"):
                driver.verify_bound_files([binding, binding], root)
            path.write_text("tampered")
            with self.assertRaisesRegex(driver.EvidenceError, "binding mismatch"):
                driver.verify_bound_files([binding], root)

    def test_coverage_missing_duplicate_extra_rejected(self):
        for rows in ([{"id": "a"}], [{"id": "a"}, {"id": "a"}], [{"id": "a"}, {"id": "b"}, {"id": "extra"}]):
            with self.assertRaises(driver.EvidenceError):
                driver.unique_by(rows, "id", ["a", "b"])


class AccuracyAndPolicyTests(unittest.TestCase):
    def test_central_accuracy_pass_and_fail(self):
        self.assertTrue(assess(.5, mp.mpf(".5"))["pass"])
        failed = assess(.5 + 4e-15, mp.mpf(".5"))
        self.assertFalse(failed["pass"])
        self.assertIn("absolute_error_gt_2e-15", failed["failures"])

    def test_normal_tail_positive_and_premature_zero(self):
        h = mp.power(2, -40)
        self.assertTrue(assess(2. ** -40, h)["pass"])
        zero = assess(0., h)
        self.assertEqual(zero["region"], "normal_tail")
        self.assertTrue(zero["prematureZero"])
        self.assertIn("premature_zero", zero["failures"])

    def test_subnormal_eight_quanta_pass_nine_fail(self):
        quantum = mp.power(2, -1074)
        h = quantum * 20
        self.assertTrue(assess(driver.from_bits(f"{28:016x}"), h)["pass"])
        failed = assess(driver.from_bits(f"{29:016x}"), h)
        self.assertFalse(failed["pass"])
        self.assertIn("subnormal_error_gt_8_ulps", failed["failures"])
        self.assertIn("positive_subnormal_required", assess(0., h)["failures"])

    def test_rounded_zero_requires_actual_zero(self):
        h = mp.power(2, -1076)
        self.assertTrue(assess(0., h)["pass"])
        failed = assess(driver.from_bits("0000000000000001"), h)
        self.assertIn("rounded_zero_required", failed["failures"])

    def test_invalid_candidate_probability_fails(self):
        for value in (math.nan, math.inf, -1., 1.1):
            result = assess(value, mp.mpf(".5"))
            self.assertFalse(result["pass"])
            self.assertEqual(result["failures"], ["finite_unit_interval"])

    def test_explicit_rounding_ties_even_normal_and_subnormal(self):
        self.assertEqual(driver.round_mpf_bits(mp.power(2, -1075)), "0000000000000000")
        self.assertEqual(driver.round_mpf_bits(3 * mp.power(2, -1075)), "0000000000000002")
        self.assertEqual(driver.round_mpf_bits(mp.mpf(1) + mp.power(2, -53)), driver.bits(1.))
        self.assertEqual(driver.round_mpf_bits(mp.mpf(1) + 3 * mp.power(2, -53)), driver.bits(1. + 2. ** -51))
        self.assertEqual(driver.round_mpf_bits(mp.power(2, -1022) - mp.power(2, -1075)), "0010000000000000")

    def test_reference_disagreement_fails(self):
        self.assertTrue(driver.reference_agreement(".5", ".5", "-1", "-1", driver.bits(.5), driver.bits(.5))["pass"])
        self.assertFalse(driver.reference_agreement(".5", ".5", "-1", "-1", driver.bits(.5), driver.bits(.6))["pass"])
        self.assertFalse(driver.reference_agreement(".5", ".5", "-1", "-1.0000001", driver.bits(.5), driver.bits(.5))["pass"])

    def test_decision_classification_checks_all_B_outcomes(self):
        self.assertEqual(driver.classify_decision(False, True, True), "improving")
        self.assertEqual(driver.classify_decision(True, False, True), "worsening")
        self.assertEqual(driver.classify_decision(False, False, True), "both_incorrect")
        self.assertEqual(driver.classify_decision(True, True, True), "unchanged_correct")
        self.assertEqual(driver.classify_decision(False, True, None), "unresolved")

    def test_native_domain_rejection_is_mandatory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            inp = {"id": "negative", "zBits": driver.bits(-1.), "expected": "reject"}
            path.write_text(json.dumps(inp))
            row = {"id": "negative", "input": inp, "z": fp(-1.), "status": "rejected_domain", "candidateInvoked": False}
            output = {"schema": "mvs-normal-tail-scalar/v1", "identity": identity(), "inputSha256": driver.sha256(path), "rows": [row]}
            driver.validate_native(output, "scalar", "A", identity(), path, [inp])
            row["p"] = fp(.5)
            with self.assertRaisesRegex(driver.EvidenceError, "invalid domain was evaluated"):
                driver.validate_native(output, "scalar", "A", identity(), path, [inp])


class CostAndProcessTests(unittest.TestCase):
    def test_nearest_rank_p95(self):
        self.assertEqual(driver.nearest_rank(list(range(1, 30)), .95), 28)
        self.assertEqual(driver.nearest_rank([3., 1., 2.], 1), 3)

    def test_first_startup_pair_excluded_only_from_summary(self):
        result = driver.cost_gates([9999.] + [100.] * 29, [8888.] + [110.] * 29, [1.] * 30, [1.] * 30, 100, 200)
        self.assertEqual(result["startup"]["A"]["n"], 29)
        self.assertEqual(result["startup"]["A"]["medianMs"], 100.)
        self.assertEqual(result["startup"]["B"]["p95Ms"], 110.)
        self.assertEqual(len(result["startup"]["pairedRatios"]), 30)

    def test_ratio_of_medians_is_gate_not_median_of_ratios(self):
        a = [1.] * 15 + [100.] * 15
        b = [2.] * 15 + [110.] * 15
        result = driver.cost_gates([100.] * 30, [100.] * 30, a, b, 0, 0)
        self.assertEqual(result["throughput"]["medianBOverMedianA"], statistics.median(b) / statistics.median(a))
        self.assertGreater(statistics.median(result["throughput"]["pairedRatios"]), 1.25)
        self.assertTrue(result["checks"]["throughput_median_ratio_lte_1_25"])

    def test_cost_budgets_and_incomplete_samples(self):
        passed = driver.cost_gates([100.] * 30, [120.] * 30, [4.] * 30, [5.] * 30, 0, 10 * 1024 * 1024)
        self.assertTrue(passed["pass"])
        failed = driver.cost_gates([100.] * 30, [151.] * 30, [4.] * 30, [5.01] * 30, 0, 10 * 1024 * 1024 + 1)
        self.assertFalse(failed["pass"])
        self.assertTrue(all(not result for result in failed["checks"].values()))
        with self.assertRaises(driver.EvidenceError):
            driver.cost_gates([1.] * 29, [1.] * 30, [1.] * 30, [1.] * 30, 0, 0)

    def test_throughput_workload_checksum_ticks_validation(self):
        output = {"schema": "mvs-normal-tail-throughput/v1", "identity": identity(), "warmupCalls": 100000, "measuredCalls": 100000,
                  "zBits": [driver.bits(x) for x in driver.THROUGHPUT_Z], "checksum": fp(42.), "warmupChecksum": fp(42.),
                  "elapsedTicks": 10, "stopwatchFrequency": 1000, "elapsedSeconds": .01}
        self.assertEqual(driver.validate_performance_output(output, "throughput", "A", identity(), "unused", driver.bits(42.)), 10.)
        for key, wrong in (("measuredCalls", 1500000), ("checksum", fp(43.)), ("zBits", list(reversed(output["zBits"]))), ("elapsedSeconds", .02), ("elapsedTicks", 0)):
            corrupt = dict(output)
            corrupt[key] = wrong
            with self.assertRaises(driver.EvidenceError):
                driver.validate_performance_output(corrupt, "throughput", "A", identity(), "unused", driver.bits(42.))

    def test_startup_requires_correct_frozen_pair_result(self):
        output = {"schema": "mvs-normal-tail-startup/v1", "experimental": True, "variant": "A", "sourceTreeSha256": "source-tree", "valid": True, "p": fp(.5)}
        self.assertIsNone(driver.validate_performance_output(output, "startup", "A", identity(), driver.bits(.5), "unused"))
        with self.assertRaisesRegex(driver.EvidenceError, "fixed-pair p differs"):
            driver.validate_performance_output(output, "startup", "A", identity(), driver.bits(.25), "unused")

    def test_synthetic_process_success_and_stdout_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = driver.retained_process([sys.executable, "-c", 'print(\'{"ok":true}\')'], root, "synthetic", 5)
            self.assertGreater(result["wallNs"], 0)
            self.assertEqual(driver.parse_successful_process(result, root), {"ok": True})
            with self.assertRaisesRegex(driver.EvidenceError, "refusing to overwrite"):
                driver.retained_process([sys.executable, "-c", "pass"], root, "synthetic", 5)
            (root / result["stdout"]).write_text('{"ok":false}')
            with self.assertRaisesRegex(driver.EvidenceError, "stdout hash mismatch"):
                driver.parse_successful_process(result, root)

    def test_synthetic_nonzero_exit_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = driver.retained_process([sys.executable, "-c", "import sys; print('retained'); sys.exit(7)"], root, "bad-exit", 5)
            self.assertEqual(result["exitCode"], 7)
            self.assertIn("retained", (root / result["stdout"]).read_text())
            self.assertTrue((root / "bad-exit.process.json").exists())
            with self.assertRaises(driver.EvidenceError):
                driver.parse_successful_process(result, root)

    def test_synthetic_watchdog_terminates_and_records_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = driver.retained_process([sys.executable, "-c", "import time; time.sleep(3)"], root, "timeout", .15)
            self.assertTrue(result["timedOut"])
            self.assertEqual(result["launchError"], "child_timeout")
            self.assertNotEqual(result["exitCode"], 0)
            self.assertLess(result["wallMs"], 2000)
            self.assertTrue((root / "timeout.process.json").exists())
            with self.assertRaises(driver.EvidenceError):
                driver.parse_successful_process(result, root)

    def test_launch_failure_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = driver.retained_process([str(root / "nonexistent-executable")], root, "launch-failed", 1)
            self.assertIsNone(result["exitCode"])
            self.assertIn("FileNotFoundError", result["launchError"])
            self.assertTrue((root / "launch-failed.process.json").exists())


if __name__ == "__main__":
    unittest.main()
