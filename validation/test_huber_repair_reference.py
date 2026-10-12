"""Independent oracle/gate regressions. Native-shaped documents here are SYNTHETIC.

No test-generated document is native execution evidence. The original frozen
native evidence is evaluated separately, by its unchanged historical checker.
"""
import copy
from decimal import Decimal, localcontext
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import huber_repair_reference as huber

ROOT = Path(__file__).resolve().parent
HISTORICAL = Path(os.environ.get('MVS_HUBER_HISTORICAL_DIR', str(ROOT)))
SYNTHETIC_ASSEMBLY_BYTES = b'SYNTHETIC TEST DATA ONLY: this is not a Core assembly.\n'
SYNTHETIC_ASSEMBLY_SHA = hashlib.sha256(SYNTHETIC_ASSEMBLY_BYTES).hexdigest()


def synthetic_document(cases, fixture_hash):
    """Construct test data, explicitly labeled; never write native evidence files."""
    rows = []
    for case in cases:
        root, scale, _ = huber.reference(case['values'])
        rows.append(dict(id=case['id'], value=float(root), status='finite',
                         solverStatus='converged' if scale else 'zero_mad_fallback',
                         iterations=40 if scale else 0))
    return dict(schema='MVS-HUBER-NATIVE-1', fixtureSha256=fixture_hash,
                coreAssemblySha256=SYNTHETIC_ASSEMBLY_SHA,
                engineVersion='1.6.2', nativeRuntime='SYNTHETIC UNIT TEST; NO NATIVE EXECUTION',
                metricStaged=True, activeMetricCount=12,
                implementationId=huber.IMPLEMENTATION_ID, testDataOnly=True, results=rows)


class HuberRepairReferenceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.digest = huber.load_fixtures(ROOT / 'huber-repair-fixtures-v1.json')
        cls.by_id = {case['id']: case for case in cls.cases}
        cls.synthetic = synthetic_document(cls.cases, cls.digest)

    def setUp(self):
        self.native = copy.deepcopy(self.synthetic)

    def row(self, case_id='scale_1.0'):
        return next(row for row in self.native['results'] if row['id'] == case_id)

    def compare(self):
        return huber.compare(self.cases, self.digest, self.native, SYNTHETIC_ASSEMBLY_SHA)

    def assertReferenceNear(self, actual, expected, scale):
        with localcontext() as context:
            context.prec = huber.PRECISION
            self.assertLessEqual(abs(actual - expected), scale * Decimal('1e-1099'))

    def test_analytic_five_value_root(self):
        root, scale, residual = huber.reference([0, 1, 2, 7, 30])
        with localcontext() as context:
            context.prec = huber.PRECISION
            self.assertReferenceNear(root, (Decimal(10) + huber.C * scale) / 4, scale)
        self.assertLess(abs(residual), Decimal('1e-1099'))

    def test_analytic_even_root(self):
        root, scale, _ = huber.reference([0, 1, 2, 3, 4, 20])
        with localcontext() as context:
            context.prec = huber.PRECISION
            self.assertReferenceNear(root, (Decimal(10) + huber.C * scale) / 5, scale)

    def test_maximum_symmetric_root_exact_zero(self):
        maximum = sys.float_info.max
        root, scale, score = huber.reference([-maximum, -maximum, maximum, maximum])
        self.assertEqual(root, 0)
        self.assertEqual(score, 0)
        self.assertGreater(scale, huber.D(maximum))

    def test_maximum_asymmetric_unclipped_analytic_root(self):
        maximum = sys.float_info.max
        root, scale, _ = huber.reference([-maximum, -maximum, maximum / 4, maximum / 2, maximum])
        with localcontext() as context:
            context.prec = huber.PRECISION
            expected = -huber.D(maximum) / 20
            radius = huber.C * scale
            self.assertTrue(all(abs(huber.D(value) - expected) < radius
                                for value in [-maximum, -maximum, maximum / 4, maximum / 2, maximum]))
            self.assertReferenceNear(root, expected, scale)

    def test_maximum_reconstruction_cancellation_analytic_root(self):
        maximum = sys.float_info.max
        root, scale, _ = huber.reference([-maximum, -maximum, -maximum / 2, maximum, maximum])
        with localcontext() as context:
            context.prec = huber.PRECISION
            expected = (-Decimal('2.5') * huber.D(maximum) + 2 * huber.C * scale) / 3
            self.assertReferenceNear(root, expected, scale)
            # Three negative inputs are unclipped; the two maximum inputs clip.
            self.assertLess(abs(-huber.D(maximum) - expected), huber.C * scale)
            self.assertGreater(huber.D(maximum) - expected, huber.C * scale)

    def test_half_subnormal_exact_midpoint_rounds_zero(self):
        tiny = math.ulp(0.0)
        root, scale, score = huber.reference([0.0, tiny])
        with localcontext() as context:
            context.prec = huber.PRECISION
            self.assertEqual(root, huber.D(tiny) / 2)
            self.assertEqual(scale, huber.MAD_FACTOR * huber.D(tiny) / 2)
        self.assertGreater(scale, 0)
        self.assertEqual(score, 0)
        self.assertEqual(float(root), 0.0)

    def test_subnormal_symmetric_exact_zero(self):
        tiny = math.ulp(0.0)
        root, scale, score = huber.reference([-tiny, tiny])
        self.assertEqual(root, 0)
        self.assertEqual(score, 0)
        self.assertGreater(scale, 0)

    def test_tiny_scale_survives_maximum_outlier(self):
        case = self.by_id['tiny_mad_max_outlier']
        root, scale, _ = huber.reference(case['values'])
        with localcontext() as context:
            context.prec = huber.PRECISION
            tiny = huber.D(math.ulp(0.0))
            self.assertEqual(scale, huber.MAD_FACTOR * 32 * tiny)
            self.assertReferenceNear(root, (160 * tiny + huber.C * scale) / 4, scale)

    def test_original_sample_median_and_mad(self):
        # Even median and MAD are computed before any numerical coordinates.
        with localcontext() as context:
            context.prec = huber.PRECISION
            root, scale, _ = huber.reference([0.0, 1.0, 2.0, 8.0])
            self.assertEqual(scale, huber.MAD_FACTOR)
            self.assertReferenceNear(root, (Decimal(3) + huber.C * scale) / 3, scale)

    def test_exact_translation_and_maximum_offset(self):
        with localcontext() as context:
            context.prec = huber.PRECISION
            base_root, base_scale, _ = huber.reference([0, 1, 2, 7, 30])
            translated, scale, _ = huber.reference([3e12 + value for value in [0, 1, 2, 7, 30]])
            self.assertReferenceNear(translated - Decimal('3e12'), base_root, base_scale)
            maximum = sys.float_info.max
            root, scale, _ = huber.reference(self.by_id['max_common_offset']['values'])
            self.assertReferenceNear(root, huber.D(maximum) - base_root * huber.D(math.ulp(maximum)), scale)

    def test_binary_scalings_reflections_and_permutations(self):
        with localcontext() as context:
            context.prec = huber.PRECISION
            root, scale, _ = huber.reference([0, 1, 2, 7, 30])
            for exponent in [-1070, -1022, -900, -500, 500, 1019]:
                with self.subTest(exponent=exponent):
                    case_id = f'binary_scale_{exponent}'
                    factor = Decimal(2) ** exponent
                    actual, actual_scale, _ = huber.reference(self.by_id[case_id]['values'])
                    self.assertReferenceNear(actual, root * factor, actual_scale)
                    self.assertEqual(actual_scale, scale * factor)
                    reflected = huber.reference(self.by_id[case_id + '_reflected']['values'])[0]
                    permuted = huber.reference(self.by_id[case_id + '_permuted']['values'])[0]
                    self.assertReferenceNear(reflected, -actual, actual_scale)
                    self.assertEqual(permuted, actual)

    def test_all_generated_reflection_and_permutation_pairs(self):
        for case in self.cases:
            if case['id'].endswith('_reflected'):
                with self.subTest(case=case['id']):
                    base = self.by_id[case['id'][:-10]]
                    root, scale, _ = huber.reference(base['values'])
                    reflected = huber.reference(case['values'])[0]
                    permuted = huber.reference(self.by_id[base['id'] + '_permuted']['values'])[0]
                    if scale:
                        self.assertReferenceNear(reflected, root.copy_negate(), scale)
                    else:
                        self.assertEqual(reflected, root.copy_negate())
                    self.assertEqual(permuted, root)

    def test_constants_and_strict_majority_ties_exact_fallback(self):
        for case in self.cases:
            if case['category'] in ('zero_mad_constant', 'zero_mad_majority'):
                with self.subTest(case=case['id']):
                    root, scale, score = huber.reference(case['values'])
                    self.assertEqual(scale, 0)
                    self.assertEqual(score, 0)
                    self.assertEqual(root, huber.D(case['values'][0]))

    def test_fixture_count_and_original_twenty_retained(self):
        old = json.loads((HISTORICAL / 'huber-fixtures-v1.json').read_text())
        self.assertEqual(len(self.cases), 136)
        self.assertEqual(self.cases[:20], old['cases'])
        self.assertEqual(sum(case['category'] == 'fixed_seed_varied' for case in self.cases), 48)
        scales = [huber.reference(case['values'])[1] for case in self.cases]
        self.assertEqual(sum(scale == 0 for scale in scales), 22)
        self.assertEqual(sum(scale > 0 for scale in scales), 114)

    def test_input_is_not_mutated(self):
        values = [30.0, 2.0, 7.0, 0.0, 1.0]
        original = values.copy()
        huber.reference(values)
        self.assertEqual(values, original)

    def test_invalid_reference_inputs(self):
        for values in ([], [1], [0, math.nan], [0, math.inf], [0, -math.inf],
                       [False, 1], [0, True], ['0', 1], [0, None], [0, 10**1000], '01'):
            with self.subTest(values=repr(values)[:80]):
                with self.assertRaises(ValueError):
                    huber.reference(values)

    def test_reference_preserves_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 17
            huber.reference([0, 1, 2, 7, 30])
            self.assertEqual(context.prec, 17)

    def test_synthetic_rounded_reference_passes(self):
        report = self.compare()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['passed'], 136)
        self.assertEqual(report['failed'], 0)
        self.assertIs(report['testDataOnly'], True)
        self.assertEqual(report['coreAssemblyVerification'], 'matched_supplied_binary_sha256')

    def test_wrong_value_is_accuracy_failure(self):
        self.row()['value'] = 0.0
        report = self.compare()
        self.assertEqual(report['failed'], 1)
        row = next(row for row in report['results'] if row['id'] == 'scale_1.0')
        self.assertIn('value_outside_tolerance', row['failureReasons'])

    def test_unavailable_is_always_accuracy_failure(self):
        row = self.row()
        row.update(value=None, status='unavailable', solverStatus='iteration_limit', iterations=1)
        report = self.compare()
        self.assertEqual(report['failed'], 1)
        self.assertEqual(report['status'], 'failed_accuracy')
        failed = next(row for row in report['results'] if not row['passed'])
        self.assertEqual(failed['failureReasons'], ['unavailable_native_result'])
        self.assertIsNone(failed['absolute_error'])

    def test_all_declared_native_failure_statuses_fail_accuracy(self):
        for status in huber.FAILURE_STATUSES:
            with self.subTest(status=status):
                self.row().update(value=None, status='unavailable', solverStatus=status, iterations=1)
                report = self.compare()
                self.assertEqual(report['failed'], 1)
                self.assertEqual(report['status'], 'failed_accuracy')

    def test_positive_mad_cannot_claim_fallback_even_when_value_is_zero(self):
        self.row('half_subnormal_midpoint').update(solverStatus='zero_mad_fallback', iterations=0)
        report = self.compare()
        self.assertEqual(report['failed'], 1)
        failed = next(row for row in report['results'] if not row['passed'])
        self.assertEqual(failed['failureReasons'], ['wrong_solver_status_for_original_mad'])

    def test_exact_zero_mad_requires_explicit_fallback_status(self):
        self.row('constant').update(solverStatus='converged', iterations=1)
        self.assertEqual(self.compare()['failed'], 1)

    def test_native_nan_infinity_boolean_and_nonnumeric_rejected(self):
        for value in (math.nan, math.inf, -math.inf, True, False, '3.497', None, 10**1000):
            with self.subTest(value=repr(value)[:80]):
                self.row()['value'] = value
                with self.assertRaises(ValueError):
                    self.compare()

    def test_unknown_or_inconsistent_status_rejected(self):
        for changes in (dict(status='bogus'), dict(solverStatus='bogus'),
                        dict(status='finite', solverStatus='iteration_limit'),
                        dict(status='unavailable', value=None, solverStatus='converged'),
                        dict(status='unavailable', value=1.0, solverStatus='iteration_limit')):
            with self.subTest(changes=changes):
                self.native = copy.deepcopy(self.synthetic)
                self.row().update(changes)
                with self.assertRaises(ValueError):
                    self.compare()

    def test_every_native_result_field_is_required(self):
        for key in ('id', 'value', 'status', 'solverStatus', 'iterations'):
            with self.subTest(key=key):
                self.native = copy.deepcopy(self.synthetic)
                row = self.row()
                row.update(value=None, status='unavailable', solverStatus='iteration_limit', iterations=1)
                del row[key]
                with self.assertRaises(ValueError):
                    self.compare()

    def test_iteration_bounds_and_types(self):
        for iterations in (-1, 65, True, 3.0, None, '4', 0):
            with self.subTest(iterations=iterations):
                self.row()['iterations'] = iterations
                with self.assertRaises(ValueError):
                    self.compare()
        self.native = copy.deepcopy(self.synthetic)
        self.row('constant')['iterations'] = 1
        with self.assertRaises(ValueError):
            self.compare()

    def test_native_iteration_cap_sixty_four_is_accepted(self):
        self.row()['iterations'] = 64
        self.assertEqual(self.compare()['failed'], 0)

    def test_fixture_hash_mismatch_and_malformed_hashes_rejected(self):
        for field, value in [('fixtureSha256', '0' * 64), ('fixtureSha256', 'bad'),
                             ('coreAssemblySha256', None), ('coreAssemblySha256', 'g' * 64),
                             ('coreAssemblySha256', '0' * 63)]:
            with self.subTest(field=field, value=value):
                self.native = copy.deepcopy(self.synthetic)
                self.native[field] = value
                with self.assertRaises(ValueError):
                    self.compare()

    def test_supplied_binary_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Core assembly hash mismatch'):
            huber.compare(self.cases, self.digest, self.native, '0' * 64)

    def test_declaration_only_binary_provenance_disclosed(self):
        report = huber.compare(self.cases, self.digest, self.native)
        self.assertEqual(report['coreAssemblyVerification'], 'declared_sha256_not_independently_checked')

    def test_identity_version_runtime_and_family_are_required(self):
        for key, value in [('implementationId', 'old-irls'), ('implementationId', None),
                           ('engineVersion', '1.6.3'), ('nativeRuntime', ''),
                           ('metricStaged', False), ('metricStaged', 1),
                           ('activeMetricCount', 13), ('activeMetricCount', True),
                           ('activeMetricCount', 12.0), ('schema', 'MVS-HUBER-NATIVE-2')]:
            with self.subTest(key=key, value=value):
                self.native = copy.deepcopy(self.synthetic)
                self.native[key] = value
                with self.assertRaises(ValueError):
                    self.compare()

    def test_duplicate_missing_and_extra_native_ids_rejected(self):
        for operation in ('duplicate', 'missing', 'extra'):
            with self.subTest(operation=operation):
                self.native = copy.deepcopy(self.synthetic)
                if operation == 'duplicate':
                    self.native['results'].append(copy.deepcopy(self.row()))
                elif operation == 'missing':
                    self.native['results'].pop()
                else:
                    extra = copy.deepcopy(self.row()); extra['id'] = 'not_a_fixture'
                    self.native['results'].append(extra)
                with self.assertRaisesRegex(ValueError, 'identities'):
                    self.compare()

    def test_invalid_fixture_documents_rejected(self):
        document = json.loads((ROOT / 'huber-repair-fixtures-v1.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.json'
            variants = []
            duplicate = copy.deepcopy(document); duplicate['cases'].append(duplicate['cases'][0]); variants.append(duplicate)
            empty = copy.deepcopy(document); empty['cases'] = []; variants.append(empty)
            wrong = copy.deepcopy(document); wrong['mad_normal_consistency'] = '1.48'; variants.append(wrong)
            for value in [True, math.nan, math.inf, '1.0', None]:
                variant = copy.deepcopy(document); variant['cases'][0]['values'][0] = value; variants.append(variant)
            for variant in variants:
                path.write_text(json.dumps(variant))
                with self.assertRaises(ValueError):
                    huber.load_fixtures(path)

    def test_duplicate_json_keys_and_nonfinite_tokens_rejected(self):
        for content in ['{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}']:
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    huber.read_json_bytes(content.encode())

    def test_report_decimal_strings_are_compact_but_nonzero_errors_survive(self):
        report = self.compare()
        for row in report['results']:
            for key in ['reference', 'fixed_mad_scale', 'absolute_error', 'error_in_scale_units',
                        'tolerance', 'reference_mean_score_residual']:
                if row[key] is not None:
                    self.assertLess(len(row[key]), 55)
        half = next(row for row in report['results'] if row['id'] == 'half_subnormal_midpoint')
        self.assertGreater(Decimal(half['absolute_error']), 0)
        self.assertEqual(report['displaySignificantDigits'], 40)

    def test_declared_tolerance_is_unchanged_and_comparison_is_unrounded(self):
        root, scale, _ = huber.reference([0, 1, 2, 7, 30])
        with localcontext() as context:
            context.prec = huber.PRECISION
            tolerance = max(Decimal('1e-10') * scale, 4 * huber.D(math.ulp(float(root))))
            self.row()['value'] = float(root + tolerance * Decimal('0.999'))
            self.assertEqual(self.compare()['failed'], 0)
            self.row()['value'] = float(root + tolerance * Decimal('1.001'))
            self.assertEqual(self.compare()['failed'], 1)

    def test_historical_native_baseline_still_has_nine_failures(self):
        spec = importlib.util.spec_from_file_location('unchanged_historical_huber_reference', HISTORICAL / 'huber_reference.py')
        old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
        cases, digest = old.load_fixtures(HISTORICAL / 'huber-fixtures-v1.json')
        self.assertEqual(digest, '089da6ed6bb3b1eda1eb0e5e6bc6aaffa7056e59f91f69d24e2d1c167cf22b8e')
        baseline = json.loads((HISTORICAL / 'huber-native-baseline-v1.json').read_text())
        report = old.compare(cases, digest, baseline)
        self.assertEqual(report['status'], 'failed_accuracy')
        self.assertEqual((report['cases'], report['passed'], report['failed']), (20, 11, 9))
        # The stricter repair checker must not silently accept the old implementation.
        with self.assertRaises(ValueError):
            huber.compare(cases, digest, baseline)

    def test_cli_exit_codes_and_actual_file_hash_binding_using_synthetic_data(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            fixtures = directory / 'fixtures.json'
            fixture_doc = dict(schema='MVS-HUBER-REFERENCE-1', metric='huber_location',
                               tuning_constant=str(huber.C), mad_normal_consistency=str(huber.MAD_FACTOR),
                               cases=[self.by_id['scale_1.0']])
            fixtures.write_text(json.dumps(fixture_doc))
            cases, digest = huber.load_fixtures(fixtures)
            native = synthetic_document(cases, digest)
            native_path = directory / 'synthetic-native-shaped-document.json'
            assembly = directory / 'synthetic-test-bytes.bin'; assembly.write_bytes(SYNTHETIC_ASSEMBLY_BYTES)
            out = directory / 'synthetic-comparison.json'
            command = [sys.executable, str(ROOT / 'huber_repair_reference.py'), '--fixtures', str(fixtures),
                       '--native', str(native_path), '--core-assembly', str(assembly), '--out', str(out)]
            for expected_code in [0, 1, 2]:
                if expected_code == 1:
                    native['results'][0].update(value=None, status='unavailable', solverStatus='iteration_limit', iterations=1)
                elif expected_code == 2:
                    native['coreAssemblySha256'] = '0' * 64
                native_path.write_text(json.dumps(native))
                completed = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(completed.returncode, expected_code, completed.stdout + completed.stderr)
                report = json.loads(completed.stdout)
                self.assertEqual(report['status'], ['passed', 'failed_accuracy', 'invalid'][expected_code])
                if expected_code != 2:
                    self.assertIs(json.loads(out.read_text())['testDataOnly'], True)


if __name__ == '__main__':
    unittest.main()
