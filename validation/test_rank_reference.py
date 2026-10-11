"""Independent fixture, exact-enumeration and tamper regressions; no C# runs."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

import rank_test_reference as reference


class RankReferenceTests(unittest.TestCase):
    def test_frozen_values_reproduce_with_independent_scipy(self):
        self.assertEqual(reference.check_fixture(), 53)

    def test_analytic_kruskal_value(self):
        # Interleaved ranks give H=3/11; chi-square(1) survival = erfc(sqrt(H/2)).
        case = next(c for c in reference.load_fixture()["cases"] if c["id"] == "kw_interleaved_two")
        self.assertAlmostEqual(case["expectedStatistic"], 3 / 11, places=13)
        self.assertAlmostEqual(case["expectedP"], math.erfc(math.sqrt(3 / 22)), places=13)

    def test_exact_small_sample_enumeration(self):
        for n in [4, 6]:
            result = reference.exact_mann_whitney([list(range(n)), list(range(n, 2 * n))])
            self.assertEqual(result["assignments"], math.comb(2 * n, n))
            self.assertEqual(result["p"], 2 / math.comb(2 * n, n))

    def test_tied_exact_enumeration_counts_labelled_assignments(self):
        # Six allocations of two of four observations, including duplicate ranks.
        result = reference.exact_mann_whitney([[0, 0], [1, 1]])
        self.assertEqual(result["assignments"], 6)
        self.assertEqual(result["p"], 1 / 3)
        self.assertTrue(result["ties"])

    def test_small_sample_approximation_can_change_bonferroni_decision(self):
        case = next(c for c in reference.load_fixture()["cases"] if c["id"] == "mw_separated_n6")
        self.assertGreater(case["expectedP"], .05 / 12)
        self.assertLess(case["exactDiagnostic"]["p"], .05 / 12)

    def test_constant_and_empty_policies_are_not_scipy_matches(self):
        data = reference.load_fixture()
        policies = [c for c in data["cases"] if c["reference"] == "mvs-declared-policy"]
        self.assertEqual(len(policies), 4)
        self.assertEqual(sum(c["expectedP"] is None for c in policies), 2)
        self.assertTrue(all(c["expectedP"] in (1, None) for c in policies))

    def tampered(self, transform, pattern):
        data = copy.deepcopy(reference.load_fixture())
        transform(data)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, pattern):
                reference.check_fixture(path)

    def test_changed_expected_value_fails(self):
        self.tampered(lambda d: d["cases"][0].update(expectedP=.123), "reference changed")

    def test_unknown_schema_fails(self):
        self.tampered(lambda d: d.update(schema="future"), "schema")

    def test_missing_and_duplicate_cases_fail(self):
        self.tampered(lambda d: d["cases"].pop(), "Missing/duplicate")
        self.tampered(lambda d: d["cases"][1].update(id=d["cases"][0]["id"]), "Missing/duplicate")

    def test_changed_test_settings_fail(self):
        self.tampered(lambda d: d["settings"]["mann_whitney"].update(use_continuity=False), "settings")

    def test_relaxed_native_accuracy_gate_fails(self):
        self.tampered(lambda d: d["absoluteTolerance"].update(mann_whitney=.1), "accuracy gate")

    def test_changed_fixture_input_fails(self):
        self.tampered(lambda d: d["cases"][0]["groups"][0].append(99), "input/provenance")

    def test_nonstandard_json_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text('{"schema": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Nonstandard"):
                reference.load_fixture(path)


if __name__ == "__main__":
    unittest.main()
