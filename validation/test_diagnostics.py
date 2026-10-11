#!/usr/bin/env python3
"""Regression fixtures for independent Python diagnostics; no C# execution."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import numpy as np

import analyze_results as analysis
import reference_simulation as reference

ROOT = Path(__file__).resolve().parents[1]


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "results.csv"

    def write_csv(self, **overrides):
        row = dict(metric="median", applicable="true", calibrated_power="0.64",
                   calibrated_fpr="0.01", mvs_score="39.72682430331276",
                   robustness="0.8", repeatability="0.7", coverage="0.95")
        row.update(overrides)
        with self.csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    def write_manifest(self, **updates):
        # Read metadata only; expected numerical scores above are independent fixtures.
        source = (ROOT / "Infrastructure/OutputExporter.cs").read_text()
        specification = re.search(r'public const string FormulaSpecification = "([^"]+)";', source)[1]
        doc = {
            "formula": {"version": "MVS-1.4.0", "specification": specification,
                        "hash": analysis.FORMULA_SHA256},
            "decision": {"alpha": 0.05, "familySize": 12},
            "calibration": {"alpha": 0.05},
            "files": [{"FileName": "results.csv",
                       "sha256": hashlib.sha256(self.csv.read_bytes()).hexdigest()}],
        }
        doc.update(updates)
        path = self.root / "run_manifest.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_current_formula_independent_fixture(self):
        self.write_csv()
        self.write_manifest()
        formula, alpha, size, _ = analysis.resolve_formula(self.csv)
        _, comps, reported = analysis.read_results(self.csv, alpha, size, formula)
        np.testing.assert_allclose(analysis.score_with(analysis.CURRENT, comps), reported, atol=1e-12)

    def test_current_does_not_need_excluded_diagnostics(self):
        self.write_csv(robustness="unavailable", repeatability="", coverage="nan")
        _, comps, _ = analysis.read_results(self.csv, 0.05, 12)
        self.assertEqual(comps.shape, (1, 2))

    def test_missing_metadata_requires_explicit_parameters(self):
        self.write_csv()
        with self.assertRaisesRegex(ValueError, "No manifest"):
            analysis.resolve_formula(self.csv)
        with self.assertRaisesRegex(ValueError, "family-size"):
            analysis.resolve_formula(self.csv, formula="MVS-1.4.0", alpha=0.05)
        self.assertEqual(analysis.resolve_formula(
            self.csv, formula="MVS-1.4.0", alpha=0.05, family_size=12)[:3],
            ("MVS-1.4.0", 0.05, 12))

    def test_manifest_rejects_parameter_overrides(self):
        self.write_csv()
        self.write_manifest()
        for kwargs in ({"alpha": 0.1}, {"family_size": 10},
                       {"formula": analysis.LEGACY_FORMULA}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "disagrees"):
                analysis.resolve_formula(self.csv, **kwargs)

    def test_manifest_rejects_unknown_and_mismatched_specification(self):
        self.write_csv()
        self.write_manifest(formula={"version": "future", "hash": "x", "specification": "x"})
        with self.assertRaisesRegex(ValueError, "Unsupported formula"):
            analysis.resolve_formula(self.csv)
        self.write_manifest(formula={"version": "MVS-1.4.0", "hash": analysis.FORMULA_SHA256,
                                     "specification": "different"})
        with self.assertRaisesRegex(ValueError, "specification/hash mismatch"):
            analysis.resolve_formula(self.csv)

    def test_alpha_consistency_and_csv_identity(self):
        self.write_csv()
        self.write_manifest(calibration={"alpha": 0.1})
        with self.assertRaisesRegex(ValueError, "alpha disagree"):
            analysis.resolve_formula(self.csv)
        self.write_manifest()
        self.write_csv(calibrated_power="0.5")
        with self.assertRaisesRegex(ValueError, "checksum"):
            analysis.resolve_formula(self.csv)

    def test_invalid_parameters_and_rows_are_not_silently_dropped(self):
        for alpha, size in [(0, 12), (float("nan"), 12), (0.05, 0), (0.05, True), (0.05, 12.5)]:
            with self.subTest(alpha=alpha, size=size), self.assertRaises(ValueError):
                analysis.validate_parameters(alpha, size)
        for changes in ({"calibrated_power": "nan"}, {"calibrated_fpr": "-0.1"},
                        {"mvs_score": ""}, {"applicable": "unknown"}):
            self.write_csv(**changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                analysis.read_results(self.csv, 0.05, 12)
        self.csv.write_text("metric,applicable,calibrated_power,calibrated_fpr,mvs_score\nmedian\n")
        with self.assertRaisesRegex(ValueError, "missing applicable"):
            analysis.read_results(self.csv, 0.05, 12)

    def test_historical_formula_is_explicit_and_distinct(self):
        self.write_csv(mvs_score="78.88765674936586")
        formula, alpha, size, _ = analysis.resolve_formula(
            self.csv, formula=analysis.LEGACY_FORMULA, alpha=0.05)
        self.assertIsNone(size)
        _, comps, reported = analysis.read_results(self.csv, alpha, formula=formula)
        np.testing.assert_allclose(analysis.score_with(analysis.LEGACY_WEIGHTS, comps, legacy=True),
                                   reported, atol=1e-12)

    def test_zero_power_is_exactly_zero_in_current_formula(self):
        scores = analysis.score_with(analysis.CURRENT, np.array([[0, 1], [0.64, 1], [1, 0]]))
        np.testing.assert_allclose(scores, [0, 80, 0], atol=1e-12)
        self.assertEqual(analysis.score_with(np.array([1., 0]), np.array([[0.64, 0]]))[0], 64)
        tiny = np.nextafter(0.0, 1.0)
        self.assertAlmostEqual(analysis.score_with(analysis.CURRENT, np.array([[tiny, 1]]))[0]
                               / (100 * math.sqrt(tiny)), 1, places=12)

    def test_single_metric_cli_and_failure_exit(self):
        self.write_csv()
        self.write_manifest()
        command = [sys.executable, str(ROOT / "validation/analyze_results.py"), str(self.csv), "--draws", "5"]
        good = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("Formula check: PASS", good.stdout)
        self.assertIn("nan means", good.stdout)
        self.write_csv(mvs_score="80")
        self.write_manifest()
        bad = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stderr)
        self.assertIn("Formula check: FAIL", bad.stdout)


class RankTests(unittest.TestCase):
    def test_average_tied_ranks(self):
        np.testing.assert_array_equal(analysis.average_ranks(np.array([3, 1, 1, 2])), [4, 1.5, 1.5, 3])

    def test_spearman_and_tau_b_known_fixtures(self):
        a, b = np.array([1, 1, 2, 3]), np.array([1, 2, 2, 3])
        self.assertAlmostEqual(analysis.spearman(a, b), 5 / 6)
        self.assertAlmostEqual(analysis.kendall_tau(a, b), 0.8)
        self.assertEqual(analysis.spearman(np.arange(4), -np.arange(4)), -1)
        self.assertEqual(analysis.kendall_tau(np.arange(4), -np.arange(4)), -1)

    def test_constant_single_and_empty_ranks_are_undefined(self):
        for a, b in [(np.ones(3), np.arange(3)), (np.array([1]), np.array([2])),
                     (np.array([]), np.array([]))]:
            self.assertTrue(math.isnan(analysis.spearman(a, b)))
            self.assertTrue(math.isnan(analysis.kendall_tau(a, b)))

    def test_invalid_rank_inputs(self):
        with self.assertRaises(ValueError):
            analysis.spearman(np.array([1]), np.array([1, 2]))
        with self.assertRaises(ValueError):
            analysis.kendall_tau(np.array([np.nan]), np.array([1]))


class MetricTests(unittest.TestCase):
    def test_registry_has_twelve_active_names_in_legacy_order(self):
        self.assertEqual(list(reference.METRICS),
                         ["median", "standard_deviation", "coefficient_of_variation", "mad", "iqr",
                          "normalized_mad", "normalized_iqr", "mean", "rms", "range",
                          "geometric_mean", "trimmed_mean_20"])

    def test_trim_floor_boundary(self):
        x = np.array([[0, 0, 0, 1, 2, 3, 100, 1000.]])
        self.assertAlmostEqual(reference._trimmed20(x)[0], 106 / 6)
        self.assertEqual(reference._trimmed20(np.array([[1, 2, 3, 4.]]))[0], 2.5)

    def test_geomean_availability_is_per_entity(self):
        actual = reference._geomean(np.array([[1, 2, 3], [0, 2, 3], [-1, 2, 3.]]))
        self.assertAlmostEqual(actual[0], 6 ** (1 / 3))
        self.assertTrue(np.isnan(actual[1:]).all())

    def test_sample_sd_and_linear_quantiles(self):
        x = np.array([[1, 2, 3, 4.]])
        self.assertAlmostEqual(reference._sd(x)[0], math.sqrt(5 / 3))
        self.assertEqual(reference._mad(x)[0], 1)
        self.assertEqual(reference._iqr(x)[0], 1.5)

    def test_relative_metrics_absolute_denominators(self):
        x = np.array([[-4, -3, -2, -1.]])
        self.assertAlmostEqual(reference._cv(x)[0], math.sqrt(5 / 3) / 2.5)
        self.assertAlmostEqual(reference._norm_mad(x)[0], 0.4)
        self.assertAlmostEqual(reference._norm_iqr(x)[0], 0.6)

    def test_near_zero_denominators_and_unit_scaling(self):
        x = np.array([[-1, -1, 1, 1.], [-1, -1, 1, 1 + 1e-14]])
        for fn in (reference._cv, reference._norm_mad, reference._norm_iqr):
            self.assertTrue(np.isnan(fn(x)).all())
            ordinary = np.array([[1, 2, 3, 4.]])
            np.testing.assert_allclose(fn(ordinary), fn(ordinary * 1e-15), rtol=1e-14)


class ReferenceTestTests(unittest.TestCase):
    def test_independent_mann_whitney_fixtures(self):
        # Expected z values checked against SciPy's asymptotic, tie-corrected,
        # continuity-corrected two-sided method; SciPy is not required to run tests.
        a = np.array([[1, 2, 2, 5], [1, 2, 3, 4], [1, 1, 1, 1.]])
        b = np.array([[2, 3, 3, 4], [5, 6, 7, 8], [1, 1, 1, 1.]])
        expected = [0.7441756972344841, 2.165063509461097, 0]
        np.testing.assert_allclose(reference.mannwhitney_absz(a, b), expected, atol=1e-14)
        np.testing.assert_allclose(reference.mannwhitney_absz(b, a), expected, atol=1e-14)
        np.testing.assert_allclose(reference.mannwhitney_absz(a[:, ::-1], b[:, ::-1]), expected, atol=1e-14)

    def test_partial_entity_availability_and_insufficient_replications(self):
        a = np.array([[1, 2, 3, 4, np.nan], [1, 2, 3, np.nan, np.nan]])
        b = np.array([[5, 6, 7, 8, np.nan], [5, 6, 7, 8, 9.]])
        z, available = reference.metric_test_z(a, b)
        np.testing.assert_array_equal(available, [True, False])
        self.assertAlmostEqual(z[0], 2.165063509461097)
        self.assertTrue(np.isnan(z[1]))

    def test_all_unavailable_and_different_group_sizes(self):
        def small(rng):
            return {"A": np.ones((3, 4)), "B": np.ones((5, 4))}
        result = reference.run(small, 2, 1)
        self.assertEqual(result["__bonferroni_twelve__"], 0)
        self.assertEqual(result["__any_of_twelve_unadjusted__"], 0)
        self.assertEqual(result["__available__median"], 0)

    def test_reproducibility_and_bonferroni_subset(self):
        first = reference.run(reference.dgp.normal_additive, 12, 11)
        second = reference.run(reference.dgp.normal_additive, 12, 11)
        self.assertEqual(first, second)
        self.assertLessEqual(first["__bonferroni_twelve__"], first["__any_of_twelve_unadjusted__"])
        self.assertEqual(first["__available__median"], 1)

    def test_cli_reports_version_and_preserves_old_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "reference_power_primary.csv"
            old.write_text("historical bytes", encoding="utf-8")
            command = [sys.executable, str(ROOT / "validation/reference_simulation.py"),
                       "2", "primary", "--output-dir", tmp]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(old.read_text(), "historical bytes")
            self.assertIn("MVS-REFERENCE-2", result.stdout)
            self.assertIn("bonferroni_twelve", result.stdout)
            self.assertIn("available_geometric_mean", result.stdout)
            self.assertTrue((Path(tmp) / "reference_power_v2_primary.csv").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
