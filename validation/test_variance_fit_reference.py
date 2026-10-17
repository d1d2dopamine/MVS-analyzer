"""Small fixed algebra, fixture, and fail-closed evidence regressions.

These tests never call a native Fit or optimize an additional dataset. The
separate CI command executes the frozen nine-reference/20-native protocol.
"""
import copy
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import variance_fit_reference as ref

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'validation/variance-fit-fixtures-v1.json'


class VarianceReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document, cls.digest = ref.load_fixtures(FIXTURES)
        cls.cases = {row['id']: row for row in cls.document['cases']}

    def bad_fixture(self, document):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'input.json'
            path.write_text(json.dumps(document))
            return ref.load_fixtures(path)

    def test_fixed_counts_and_matrix_budget(self):
        cases = self.document['cases']
        self.assertEqual(len(cases), 20)
        bases = [c for c in cases if c['classification'] == 'regular' and c['referenceCaseId'] is None]
        self.assertEqual(len(bases), 9)
        self.assertEqual(sum(2 * 2 ** (1 if c['equalBetween'] else 2) for c in bases), 64)
        self.assertEqual(max(sum(c['count'] for c in row['clusters']) for row in cases), 40)

    def test_fixture_requires_frozen_status(self):
        doc = copy.deepcopy(self.document)
        doc['status'] = 'proposed'
        with self.assertRaisesRegex(ref.InvalidEvidence, 'not frozen'):
            self.bad_fixture(doc)

    def test_wrong_count_and_duplicate_identity_rejected(self):
        for edit in ('remove', 'duplicate'):
            doc = copy.deepcopy(self.document)
            if edit == 'remove':
                doc['cases'].pop()
            else:
                doc['cases'][1]['id'] = doc['cases'][0]['id']
            with self.assertRaises(ref.InvalidEvidence):
                self.bad_fixture(doc)

    def test_summary_disagreement_rejected(self):
        doc = copy.deepcopy(self.document)
        doc['cases'][0]['clusters'][0]['mean'] += 1
        with self.assertRaisesRegex(ref.InvalidEvidence, 'mean mismatch'):
            self.bad_fixture(doc)

    def test_nonstandard_json_and_duplicate_keys_rejected(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ref.InvalidEvidence):
                ref.read_json(text)

    def test_dense_group_and_covariance_design(self):
        model = ref.DenseModel(self.cases['U_ML'])
        self.assertEqual(model.X.shape, (28, 2))
        self.assertTrue(np.all(model.X.sum(axis=1) == 1))
        self.assertEqual(model.bases.shape, (4, 28, 28))
        self.assertTrue(np.array_equal(model.bases[:2].sum(axis=0), np.eye(28)))
        self.assertEqual(np.linalg.matrix_rank(model.X), 2)
        shared = ref.DenseModel(self.cases['U_ML_equalBoth'])
        self.assertEqual(shared.dim, 2)
        self.assertTrue(np.array_equal(shared.bases[1], model.bases[2:].sum(axis=0)))

    def test_frozen_analytic_balanced_truth(self):
        self.assertEqual(ref.balanced_truth(self.cases['B_ML']),
                         dict(means=[3.,103.], within=[4.,4.], between=[1.,1.]))
        self.assertEqual(ref.balanced_truth(self.cases['B_REML'])['between'], [1.5,1.5])
        self.assertEqual(ref.balanced_truth(self.cases['Z_ML'])['within'], [3.125,3.125])
        self.assertEqual(ref.balanced_truth(self.cases['Z_REML'])['within'], [62.5/19,62.5/19])
        self.assertEqual(ref.balanced_truth(self.cases['Z_REML'])['between'], [0.,0.])

    def test_dense_gradient_at_fixed_first_start(self):
        # Central differences are only a derivative unit test at a frozen start.
        for case in self.document['cases'][:9]:
            model = ref.DenseModel(case)
            logs = np.full(model.dim, math.log(.1))
            _, gradient = model.evaluate(logs)
            numeric = []
            for i in range(model.dim):
                shift = np.zeros(model.dim)
                shift[i] = 1e-5
                numeric.append((model.evaluate(logs+shift)[0] - model.evaluate(logs-shift)[0]) / 2e-5)
            np.testing.assert_allclose(gradient, numeric, atol=3e-8, rtol=2e-7, err_msg=case['id'])

    def test_raw_full_likelihood_affine_units(self):
        for method in ('ML', 'REML'):
            base = ref.DenseModel(self.cases['U_' + method])
            logs = np.full(base.dim, math.log(.1))
            reference = base.evaluate(logs, details=True)
            for transform, b, a in (('large',1000.,0.), ('small',.001,0.), ('affine',-2.,7.), ('shift',1.,32.)):
                model = ref.DenseModel(self.cases['U_' + transform + '_' + method])
                actual = model.evaluate(logs, details=True)
                self.assertAlmostEqual(actual['normalizedNll'], reference['normalizedNll'], places=11)
                expected_shift = (base.n - (base.p if method == 'REML' else 0)) * math.log(abs(b))
                self.assertAlmostEqual(actual['rawFullNll']-reference['rawFullNll'], expected_shift, places=10)
                np.testing.assert_allclose(actual['means'], np.array(reference['means']) * b + a, atol=1e-10)

    def test_exact_zero_dense_objective_is_finite(self):
        model = ref.DenseModel(self.cases['Z_ML'])
        logs = np.log([3.125/model.scale2] * 2 + [math.exp(-23)] * 2)
        value, gradient = model.evaluate(logs, exact_zero_between=True)
        self.assertTrue(math.isfinite(value))
        self.assertTrue(np.isfinite(gradient).all())
        self.assertEqual(gradient[2:].tolist(), [0.,0.])

    def test_constant_guard_never_has_reference_optimization(self):
        with self.assertRaisesRegex(ref.OracleInvalid, 'Constant data'):
            ref.DenseModel(self.cases['C_ML'])

    def test_floor_log_gradient_does_not_hide_linear_descent(self):
        detail = dict(logs=[-23.], linearScores=[-1.], traceTerms=[0.], quadraticTerms=[2.])
        self.assertLess(ref.projected_gradient([-23.], [-math.exp(-23)]), 1e-6)
        self.assertEqual(ref.linear_kkt(detail), [0])
        detail['linearScores'] = [1.]
        self.assertEqual(ref.linear_kkt(detail), [])

    def test_numeric_classes_and_bit_patterns(self):
        for value in (0., -0., 2.5):
            bits = struct.pack('>d', value).hex()
            self.assertEqual(ref.verify_fp(value, dict(classification='finite', value=value, bits=bits)), 'finite')
        self.assertEqual(ref.verify_fp(None, dict(classification='nan', value=None, bits='7ff8000000000000')), 'nan')
        with self.assertRaises(ref.InvalidEvidence):
            ref.verify_fp(0., dict(classification='nan', value=0., bits='7ff8000000000000'))
        with self.assertRaises(ref.InvalidEvidence):
            ref.verify_fp(1., dict(classification='finite', value=1., bits='4000000000000000'))

    def test_wrong_provenance_fails_before_accessing_assemblies(self):
        native = dict(schemaVersion=1, protocolId=ref.PROTOCOL_ID, inputSha256='0'*64)
        with self.assertRaisesRegex(ref.InvalidEvidence, 'hash mismatch'):
            ref.validate_native(self.document, self.digest, native, ROOT, Path('/unavailable.dll'))

    def test_fixed_high_condition_preflight_and_endpoint_details(self):
        budget = ref.EvaluationBudget()
        checks = ref.conditioning_preflight(budget)
        self.assertEqual([row['blockSize'] for row in checks], [2,3,4,5])
        self.assertTrue(all('binary64Diagnostic' in row for row in checks))
        model = ref.DenseModel(self.cases['B_ML'])
        detail = model.evaluate([-23.,-23.,math.log(.1),math.log(.1)], budget=budget, details=True)
        self.assertGreater(detail['condition'], 1e8)
        self.assertEqual(detail['evaluationPrecision'], 'mpmath60')
        self.assertTrue(math.isfinite(detail['normalizedNll']))
        self.assertEqual(budget.high_precision_count, 5)
        self.assertEqual(budget.count, 5)

    def test_budget_caps_fail_closed(self):
        budget = ref.EvaluationBudget(limit=1)
        budget.check(evaluate=True)
        with self.assertRaises(ref.BudgetExhausted):
            budget.check(evaluate=True)
        with self.assertRaises(ref.BudgetExhausted):
            ref.EvaluationBudget(seconds=-1).check()
        budget = ref.EvaluationBudget()
        budget.high_precision_count = 128
        with self.assertRaises(ref.BudgetExhausted):
            budget.high_precision()

    def test_compare_rejects_uncertified_reference(self):
        with self.assertRaisesRegex(ref.InvalidEvidence, 'without certified'):
            ref.compare(self.document, {'status':'oracle_inconclusive'}, {})

    def test_existing_evidence_directory_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            sentinel = path / 'native.stdout'
            sentinel.write_bytes(b'original evidence')
            with self.assertRaisesRegex(ref.InvalidEvidence, 'refusing to overwrite'):
                ref.create_evidence_directory(path)
            self.assertEqual(sentinel.read_bytes(), b'original evidence')
            child = ref.create_evidence_directory(path / 'fresh')
            self.assertTrue(child.is_dir())

    def test_fixture_change_stops_before_native_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture.json'
            path.write_text('{}')
            with patch.object(ref.subprocess, 'run') as run:
                with self.assertRaisesRegex(ref.InvalidEvidence, 'changed after reference'):
                    ref.native_run(['dotnet', 'unused.dll'], path, self.digest, Path(temporary))
                run.assert_not_called()

    def test_malformed_native_stdout_preserves_invocation_and_raw_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            process = ref.subprocess.CompletedProcess(['dotnet'], 0, b'not JSON', b'raw stderr')
            with patch.object(ref.subprocess, 'run', return_value=process):
                with self.assertRaises(ValueError) as raised:
                    ref.native_run(['dotnet','unused.dll'], FIXTURES, self.digest, out)
            self.assertTrue(raised.exception.native_started)
            self.assertEqual((out/'native.stdout').read_bytes(), b'not JSON')
            self.assertEqual((out/'native.stderr').read_bytes(), b'raw stderr')

    def test_atomic_json_has_no_nonstandard_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'result.json'
            ref.atomic_json(path, {'finite':1., 'nonfinite':None})
            self.assertEqual(ref.read_json(path.read_bytes()), {'finite':1., 'nonfinite':None})
            self.assertFalse(path.with_name(path.name+'.tmp').exists())
            with self.assertRaises(ValueError):
                ref.atomic_json(path, {'bad':math.nan})


if __name__ == '__main__':
    unittest.main()
