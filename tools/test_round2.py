#!/usr/bin/env python3
"""Failure-path regressions for the parity checker/runner, not real CLI parity."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import run_round2_validation as runner
import test_python_cli as parity
import check_outputs


class ParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.left, self.right = [Path(self.temp.name) / x for x in ["cli", "python"]]
        self.row = {"Metric": "median", "PValue": .0123, "AdjustedP": .1476, "Applicable": True,
                    "Verdict": "insufficient", "Mde": None, "TrackPowers": [.5, None]}
        for folder in [self.left, self.right]:
            folder.mkdir()
            self.write(folder, "results.json", {"schemaVersion": 2, "rows": [copy.deepcopy(self.row)]})
            self.write(folder, "run_manifest.json", {"runId": folder.name, "created": folder.name,
                       "files": [{"FileName": "results.json", "sha256": folder.name}],
                       "formula": {"hash": "frozen"}, "decision": {"familySize": 12, "alpha": .05}})
            (folder / "results.csv").write_text("metric,global_p,adjusted_p,verdict,applicable,track_powers\nmedian,0.0123,0.1476,insufficient,True,0.5|\n", encoding="utf-8")
            (folder / "calibration_state.json").write_text("identical saved state", encoding="utf-8")
            (folder / "metric_availability.csv").write_text("metric,group,usable_entities\nmedian,A,8\n", encoding="utf-8")

    @staticmethod
    def write(folder, name, data):
        (folder / name).write_text(json.dumps(data), encoding="utf-8")

    def compare(self):
        parity.compare_analysis(self.left, self.right, 1e-12, 1e-10)

    def test_equal_science_ignores_operational_manifest_fields(self):
        self.compare()

    def test_small_float_difference_uses_declared_tolerance(self):
        data = parity.strict_json(self.right / "results.json")
        data["rows"][0]["PValue"] += 1e-13
        self.write(self.right, "results.json", data)
        self.compare()

    def test_changed_pvalue_fails_even_when_identity_and_count_match(self):
        data = parity.strict_json(self.right / "results.json")
        data["rows"][0]["PValue"] = .2
        self.write(self.right, "results.json", data)
        with self.assertRaisesRegex(AssertionError, "PValue"):
            self.compare()

    def test_changed_status_and_unavailability_fail(self):
        for key, value in [("Verdict", "difference"), ("Applicable", False), ("Mde", 0)]:
            with self.subTest(key=key):
                row = copy.deepcopy(self.row)
                row[key] = value
                self.write(self.right, "results.json", {"schemaVersion": 2, "rows": [row]})
                with self.assertRaisesRegex(AssertionError, key):
                    self.compare()

    def test_row_order_and_missing_fields_fail(self):
        for right in [[{"Metric": "mean"}, {"Metric": "median"}], [{"Metric": "median"}]]:
            with self.subTest(right=right), self.assertRaises(AssertionError):
                parity.compare_value([{"Metric": "median"}, {"Metric": "mean"}], right, 1e-12, 1e-10)

    def test_exact_counts_and_boolean_types_are_not_float_tolerant(self):
        for left, right in [(12, 13), (True, 1), (False, 0)]:
            with self.subTest(left=left, right=right), self.assertRaises(AssertionError):
                parity.compare_value(left, right, 1, 1)

    def test_csv_numeric_change_is_detected_independently(self):
        path = self.right / "results.csv"
        path.write_text(path.read_text().replace("0.0123", "0.8"), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "results.csv.*global_p"):
            self.compare()

    def test_csv_vector_null_cannot_become_zero(self):
        path = self.right / "results.csv"
        path.write_text(path.read_text().replace("0.5|", "0.5|0"), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "track_powers"):
            self.compare()

    def test_availability_csv_count_change_is_detected_independently(self):
        path = self.right / "metric_availability.csv"
        path.write_text(path.read_text().replace(",8", ",7"), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "metric_availability.csv.*usable_entities"):
            self.compare()

    def test_formula_identity_is_compared(self):
        data = parity.strict_json(self.right / "run_manifest.json")
        data["formula"]["hash"] = "other"
        self.write(self.right, "run_manifest.json", data)
        with self.assertRaisesRegex(AssertionError, "formula.hash"):
            self.compare()

    def test_original_state_bytes_are_preserved(self):
        (self.right / "calibration_state.json").write_text("different state")
        with self.assertRaisesRegex(AssertionError, "state bytes"):
            self.compare()

    def test_nan_and_malformed_csv_fail(self):
        for text in ["metric,global_p\nmedian,NaN\n", "metric,global_p\nmedian\n", "metric,metric\nmedian,median\n", "metric,global_p\n"]:
            with self.subTest(text=text):
                path = self.right / "results.csv"
                path.write_text(text)
                with self.assertRaises(ValueError):
                    parity.read_results_csv(path)
        path = self.right / "results.json"
        path.write_text('{"p": NaN}')
        with self.assertRaises(ValueError):
            parity.strict_json(path)


class AvailabilityArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.row = {"Metric": "geometric_mean", "Applicable": False, "CalibrationApplicable": True,
            "ObservedStatus": "insufficient_usable_entities", "PValue": None, "AdjustedP": None, "Effect": None,
            "Verdict": "not_applicable", "EffectIntervalStatus": "unavailable", "Candidate": False,
            "GroupAvailability": [
                {"Group": "A", "RetainedEntities": 8, "UsableEntities": 3, "ExcludedEntities": 5, "ExclusionReasons": {"nonpositive_measurements": 5}},
                {"Group": "B", "RetainedEntities": 8, "UsableEntities": 8, "ExcludedEntities": 0, "ExclusionReasons": {}}]}
        self.csv = "metric,group,retained_entities,usable_entities,excluded_entities,exclusion_reasons,observed_status,calibration_applicable\ngeometric_mean,A,8,3,5,nonpositive_measurements:5,insufficient_usable_entities,True\ngeometric_mean,B,8,8,0,,insufficient_usable_entities,True\n"
        (self.folder / "metric_availability.csv").write_text(self.csv)

    def verify(self, row=None):
        check_outputs.check_availability({"rows": [row or self.row]}, self.folder)

    def test_unavailable_metric_counts_and_reasons_are_preserved(self):
        self.verify()

    def test_counts_cannot_use_measurement_rows_or_drop_exclusions(self):
        for key, value in [("RetainedEntities", 48), ("UsableEntities", 4), ("ExcludedEntities", 0), ("ExclusionReasons", {})]:
            with self.subTest(key=key):
                row = copy.deepcopy(self.row)
                row["GroupAvailability"][0][key] = value
                with self.assertRaises(AssertionError):
                    self.verify(row)

    def test_unavailable_calibration_can_coexist_with_available_observed_test(self):
        row = copy.deepcopy(self.row)
        row.update(Applicable=True, CalibrationApplicable=False, ObservedStatus="available", PValue=.001,
                   AdjustedP=.012, Effect=1, Verdict="difference", EffectIntervalStatus="pointwise_percentile_95")
        row["GroupAvailability"][0].update(UsableEntities=8, ExcludedEntities=0, ExclusionReasons={})
        path = self.folder / "metric_availability.csv"
        path.write_text(self.csv.replace("8,3,5,nonpositive_measurements:5", "8,8,0,").replace("insufficient_usable_entities,True", "available,False"))
        self.verify(row)
        row["Candidate"] = True
        with self.assertRaisesRegex(AssertionError, "candidate"):
            self.verify(row)

    def test_csv_cannot_disagree_with_json(self):
        (self.folder / "metric_availability.csv").write_text(self.csv.replace("nonpositive_measurements:5", "nonpositive_measurements:4"))
        with self.assertRaisesRegex(AssertionError, "CSV and JSON"):
            self.verify()


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "new-run"

    def test_failed_child_is_not_reported_as_pass(self):
        run = runner.ValidationRun(self.path)
        self.assertFalse(run.run("failing-child", [sys.executable, "-c", "raise SystemExit(7)"]))
        self.assertEqual(run.finish(), 1)
        report = json.loads((self.path / "verification.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["checks"][0]["exitCode"], 7)

    def test_missing_native_checks_make_success_incomplete(self):
        run = runner.ValidationRun(self.path)
        self.assertTrue(run.run("independent", [sys.executable, "-c", "print('reference only')"]))
        run.skip_native("No SDK")
        self.assertEqual(run.finish(), 2)
        self.assertTrue(all(c["status"] == "not_run" for c in run.checks[1:]))

    def test_native_failure_does_not_create_contradictory_pass_skip_records(self):
        run = runner.ValidationRun(self.path)
        run.run("native-core-tests", [sys.executable, "-c", "raise SystemExit(1)"])
        run.skip_native("Prerequisite failed")
        self.assertEqual(sum(c["name"] == "native-core-tests" for c in run.checks), 1)
        self.assertEqual(run.finish(), 1)

    def test_existing_run_is_never_overwritten(self):
        self.path.mkdir()
        evidence = self.path / "raw.txt"
        evidence.write_text("original evidence")
        with self.assertRaises(FileExistsError):
            runner.ValidationRun(self.path)
        self.assertEqual(evidence.read_text(), "original evidence")

    def test_missing_child_executable_is_failed(self):
        run = runner.ValidationRun(self.path)
        self.assertFalse(run.run("missing-child", [str(self.path / "absent-executable")]))
        self.assertEqual(run.finish(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
