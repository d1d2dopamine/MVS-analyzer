"""Reference-solver/tool regressions; frozen native defects remain explicitly failing accuracy cases."""
import copy
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import unittest

import huber_reference as huber

ROOT = Path(__file__).resolve().parent


class HuberReferenceChecks(unittest.TestCase):
    def setUp(self):
        self.cases, self.digest = huber.load_fixtures(ROOT / 'huber-fixtures-v1.json')
        self.native = json.loads((ROOT / 'huber-native-baseline-v1.json').read_text())

    def test_analytic_asymmetric_root(self):
        root, scale, score = huber.reference([0, 1, 2, 3, 4, 20])
        with localcontext() as context:
            context.prec = 80
            expected = (Decimal(10) + huber.C * huber.MAD_FACTOR * Decimal('1.5')) / 5
            self.assertLess(abs(root - expected), Decimal('1e-70'))
            self.assertLess(abs(score), Decimal('1e-70'))

    def test_analytic_five_value_root(self):
        # At this root 0,1,2,7 are unsaturated and 30 contributes +c.
        root, scale, score = huber.reference([0, 1, 2, 7, 30])
        with localcontext() as context:
            context.prec = 80
            expected = (Decimal(10) + huber.C * scale) / 4
            self.assertLess(abs(root - expected), Decimal('1e-70'))
            self.assertLess(abs(score), Decimal('1e-70'))

    def test_zero_mad_policy(self):
        root, scale, _ = huber.reference([1, 1, 1, 2, 1e13])
        self.assertEqual(root, 1)
        self.assertEqual(scale, 0)

    def test_symmetric_root(self):
        self.assertEqual(huber.reference([-2, -1, 0, 1, 2])[0], 0)

    def test_translation_equivariance_for_exact_inputs(self):
        with localcontext() as context:
            context.prec = 80
            root = huber.reference([0, 1, 2, 7, 30])[0]
            shifted = huber.reference([3e12 + x for x in [0, 1, 2, 7, 30]])[0]
            self.assertLess(abs(shifted - Decimal('3e12') - root), Decimal('1e-65'))

    def test_positive_scaling_equivariance(self):
        with localcontext() as context:
            context.prec = 80
            root = huber.reference([0, 1, 2, 7, 30])[0]
            scaled = huber.reference([1000000 * x for x in [0, 1, 2, 7, 30]])[0]
            self.assertLess(abs(scaled / 1000000 - root), Decimal('1e-70'))

    def test_invalid_inputs_rejected(self):
        for values in ([1], [0, math.nan], [0, math.inf]):
            with self.assertRaises(ValueError):
                huber.reference(values)

    def test_wrong_provenance_rejected(self):
        self.native['fixtureSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            huber.compare(self.cases, self.digest, self.native)

    def test_missing_or_duplicate_case_rejected(self):
        self.native['results'].append(copy.deepcopy(self.native['results'][0]))
        with self.assertRaisesRegex(ValueError, 'identities'):
            huber.compare(self.cases, self.digest, self.native)

    def test_activation_rejected(self):
        self.native['metricStaged'] = False
        with self.assertRaisesRegex(ValueError, 'activation'):
            huber.compare(self.cases, self.digest, self.native)

    def test_frozen_native_evidence_exposes_defects(self):
        report = huber.compare(self.cases, self.digest, self.native)
        self.assertEqual(report['status'], 'failed_accuracy')
        results = {row['id']: row for row in report['results']}
        self.assertFalse(results['scale_1e-13']['passed'])
        self.assertGreater(Decimal(results['scale_1e-13']['error_in_scale_units']), Decimal('.07'))
        self.assertFalse(results['shift_3000000000000.0']['passed'])
        self.assertGreater(Decimal(results['shift_3000000000000.0']['error_in_scale_units']), Decimal('.5'))
        self.assertTrue(results['constant']['passed'])
        self.assertTrue(results['scale_1.0']['passed'])

    def test_reference_rounded_to_binary64_passes_declared_tolerance(self):
        cases = {row['id']: row for row in self.cases}
        for row in self.native['results']:
            row['value'] = float(huber.reference(cases[row['id']]['values'])[0])
            row['status'] = 'finite'
        report = huber.compare(self.cases, self.digest, self.native)
        self.assertEqual(report['failed'], 0)


if __name__ == '__main__':
    unittest.main()
