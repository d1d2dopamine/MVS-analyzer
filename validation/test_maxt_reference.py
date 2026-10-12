"""Independent oracle/checker regressions; constructed evidence is SYNTHETIC.

These tests never label reference-generated documents as actual native output.
Real parity separately requires the native exporter and its actual Core DLL.
"""
import contextlib
import copy
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

import maxt_reference as maxt


class MaxTReferenceTests(unittest.TestCase):
    def setUp(self):
        self.document, self.digest = maxt.load_fixtures()
        self.cases = {case['id']: case for case in self.document['cases']}

    def evaluate(self, identifier):
        case = self.cases[identifier]
        return maxt.reference(case['observed'], case['resamples'], case['family_size'])

    def test_hand_union_counts_and_exact_fractions(self):
        self.assertEqual(self.evaluate('hand_ties'), dict(
            exceedance_counts=[2, 4, 0], adjusted_p=[Fraction(3, 5), Fraction(1), Fraction(1, 5)]))

    def test_ties_are_inclusive(self):
        self.assertEqual(self.evaluate('hand_all_equal')['exceedance_counts'], [3, 3, 3])
        self.assertEqual(self.evaluate('hand_family_one')['adjusted_p'], [Fraction(3, 5)])

    def test_all_above_and_below(self):
        self.assertEqual(self.evaluate('hand_all_above')['adjusted_p'], [Fraction(1)] * 3)
        self.assertEqual(self.evaluate('hand_all_below')['adjusted_p'], [Fraction(1, 3)] * 3)

    def test_negative_scores_are_not_missing(self):
        self.assertEqual(self.evaluate('hand_negative_finite')['adjusted_p'],
                         [Fraction(3, 4), Fraction(1, 2), Fraction(1, 4)])

    def test_minimum_family_and_rows(self):
        self.assertEqual(maxt.reference([1], [[0]], 1)['adjusted_p'], [Fraction(1, 2)])
        self.assertEqual(self.evaluate('hand_minimum_rows')['adjusted_p'], [Fraction(1, 2), Fraction(1)])

    def test_common_positive_scale_and_translation(self):
        expected = self.evaluate('hand_ties')
        for identifier in ('common_scale_tiny', 'common_scale_large', 'common_translation'):
            with self.subTest(identifier=identifier):
                self.assertEqual(self.evaluate(identifier), expected)

    def test_joint_column_and_row_permutations(self):
        expected = self.evaluate('hand_ties')
        self.assertEqual(self.evaluate('row_permutation'), expected)
        permuted = self.evaluate('joint_column_permutation')
        for key in ('exceedance_counts', 'adjusted_p'):
            self.assertEqual(permuted[key], [expected[key][i] for i in [2, 0, 1]])

    def test_same_marginals_different_joint_dependence(self):
        cases = [self.cases['correlation_' + label] for label in ('perfect', 'product', 'opposed')]
        for column in range(2):
            marginals = [sorted(row[column] for row in case['resamples']) for case in cases]
            self.assertEqual(marginals[0], marginals[1])
            self.assertEqual(marginals[1], marginals[2])
        self.assertEqual([self.evaluate(case['id'])['adjusted_p'][0] for case in cases],
                         [Fraction(9, 17), Fraction(13, 17), Fraction(1)])

    def test_strict_alpha_resolution(self):
        self.assertEqual([self.evaluate('resolution_B' + str(n))['adjusted_p'][0] < maxt.ALPHA
                          for n in (18, 19, 20)], [False, False, True])
        self.assertEqual(self.evaluate('resolution_B19')['adjusted_p'], [Fraction(1, 20)])
        self.assertEqual([self.evaluate('nonzero_tail_B' + str(n))['adjusted_p'][0] < maxt.ALPHA
                          for n in (39, 40)], [False, True])

    def test_complete_family_cannot_be_shrunk(self):
        full = maxt.reference([2, 2], [[0, 3], [0, 4]], 2)
        self.assertEqual(full['adjusted_p'], [Fraction(1), Fraction(1)])
        with self.assertRaises(ValueError):
            maxt.reference([2], [[0], [0]], 2)

    def test_invalid_family_size(self):
        for size in (0, -1, 1.0, True, None, '1'):
            with self.subTest(size=size), self.assertRaises(ValueError):
                maxt.reference([1], [[0]], size)

    def test_unavailable_and_nonfinite_scores_are_rejected(self):
        for score in (None, True, '1', math.nan, math.inf, -math.inf, 10**400):
            with self.subTest(score=score), self.assertRaises(ValueError):
                maxt.reference([score], [[0]], 1)
            with self.subTest(row_score=score), self.assertRaises(ValueError):
                maxt.reference([0, 0], [[100, score]], 2)

    def test_empty_ragged_and_nonlist_matrices_are_rejected(self):
        for observed, rows, size in [([], [[0]], 1), (None, [[0]], 1),
                                     ([0], [], 1), ([0], None, 1), ([0], [[0], []], 1),
                                     ([0], [[0, 1]], 1), ([0], [None], 1),
                                     ([0], ['0'], 1), ([0, 1], [[0]], 2)]:
            with self.subTest(observed=observed, rows=rows), self.assertRaises(ValueError):
                maxt.reference(observed, rows, size)

    def test_nonmutation(self):
        case = copy.deepcopy(self.cases['hand_ties'])
        saved = copy.deepcopy(case)
        maxt.reference(case['observed'], case['resamples'], case['family_size'])
        self.assertEqual(case, saved)

    def test_frozen_fixture_audit(self):
        report = maxt.audit_frozen_fixtures()
        self.assertTrue(report['passed'])
        self.assertEqual(report['cases'], 40)
        self.assertEqual(report['adjusted_values'], 104)
        self.assertEqual(report['toy_identity_cases'], 20)
        self.assertGreater(report['toy_full_orbit_plus_one_differs_cases'], 0)
        self.assertIn('not MVS FWER', report['qualification'])

    def test_each_entity_assignment_omit_one_identity(self):
        assignments, scores = maxt.toy_orbit()
        self.assertEqual(len(assignments), math.comb(6, 3))
        self.assertEqual(len(set(assignments)), 20)
        for i, assignment in enumerate(assignments):
            case = self.cases['toy_assignment_' + ''.join(map(str, assignment))]
            self.assertEqual(case['resamples'], scores[:i] + scores[i + 1:])
            # Complementary group assignments have equal absolute scores; retain
            # that second occurrence when excluding ONLY the observed index.
            self.assertIn(scores[i], case['resamples'])
            self.assertEqual(len(case['resamples']), 19)
            exact_counts = [sum(any(value >= threshold for value in row) for row in scores)
                            for threshold in scores[i]]
            self.assertEqual(self.evaluate(case['id'])['adjusted_p'],
                             [Fraction(count, 20) for count in exact_counts])

    def test_all_assignments_strict_family_any_bound_is_conditional_toy_only(self):
        assignments, scores = maxt.toy_orbit()
        all_p = [maxt.reference(scores[i], scores[:i] + scores[i + 1:], 3)['adjusted_p']
                 for i in range(len(assignments))]
        counts = []
        for alpha in maxt.TOY_ALPHA_GRID:
            count = sum(any(p < alpha for p in row) for row in all_p)
            counts.append(count)
            self.assertLessEqual(Fraction(count, len(assignments)), alpha)
        self.assertEqual(counts, [0, 0, 0, 4, 8, 18])

    def test_global_max_any_rejection_identity(self):
        for case in self.document['cases']:
            result = self.evaluate(case['id'])
            threshold = max(case['observed'])
            global_count = sum(any(score >= threshold for score in row) for row in case['resamples'])
            self.assertEqual(min(result['adjusted_p']), Fraction(global_count + 1, len(case['resamples']) + 1))
            self.assertEqual(any(p < maxt.ALPHA for p in result['adjusted_p']),
                             Fraction(global_count + 1, len(case['resamples']) + 1) < maxt.ALPHA)

    def test_full_orbit_as_mc_rows_is_not_exact_orbit_convention(self):
        _, scores = maxt.toy_orbit()
        differences = 0
        for observed in scores:
            counts = [sum(any(value >= threshold for value in row) for row in scores)
                      for threshold in observed]
            mc = maxt.reference(observed, scores, 3)['adjusted_p']
            exact = [Fraction(count, 20) for count in counts]
            self.assertEqual(mc, [Fraction(count + 1, 21) for count in counts])
            for left, right in zip(mc, exact):
                self.assertGreaterEqual(left, right)
                differences += left != right
        self.assertGreater(differences, 0)


class MaxTEvidenceCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.fixtures = root / 'fixtures.json'
        self.native = root / 'synthetic-native-shaped.json'
        self.core = root / 'synthetic-binary.bin'
        self.core.write_bytes(b'NOT A NATIVE BINARY: isolated checker unit test only')
        self.fixture_doc = dict(schemaVersion=maxt.FIXTURE_SCHEMA, alpha=.05, cases=[
            dict(id='hand', family_size=3, observed=[2, 1, 4],
                 resamples=[[1, 0, -1], [2, -1, -1], [0, 1, -1], [3, 0, 1]]),
            dict(id='boundary', family_size=1, observed=[1], resamples=[[0]] * 20)])
        self.fixtures.write_text(json.dumps(self.fixture_doc), encoding='utf-8')
        # These expected answers are hand-set, not populated by the oracle.
        self.evidence = dict(schemaVersion=maxt.NATIVE_SCHEMA,
                             fixtureSha256=hashlib.sha256(self.fixtures.read_bytes()).hexdigest(),
                             engineVersion='1.6.2', activeMetricCount=12,
                             coreAssemblySha256=hashlib.sha256(self.core.read_bytes()).hexdigest(),
                             nativeRuntime='SYNTHETIC UNIT TEST ONLY', results=[
                                 dict(id='hand', family_size=3, resample_count=4,
                                      exceedance_counts=[2, 4, 0], adjusted_p=[.6, 1, .2],
                                      rejected=[False, False, False]),
                                 dict(id='boundary', family_size=1, resample_count=20,
                                      exceedance_counts=[0], adjusted_p=[1 / 21], rejected=[True])])
        self.save_evidence()

    def save_evidence(self):
        self.native.write_text(json.dumps(self.evidence), encoding='utf-8')

    def compare(self):
        return maxt.compare(self.fixtures, self.native, self.core)

    def test_checker_accepts_handset_synthetic_document(self):
        result = self.compare()
        self.assertTrue(result['passed'])
        self.assertEqual(result['comparisons'], 4)
        self.assertEqual(result['coreAssemblySha256'], hashlib.sha256(self.core.read_bytes()).hexdigest())
        self.assertEqual(result['nativeEvidenceSha256'], hashlib.sha256(self.native.read_bytes()).hexdigest())

    def test_wrong_count_probability_and_decision_are_individually_detected(self):
        for key, value in [('exceedance_counts', 1), ('adjusted_p', .5), ('rejected', True)]:
            with self.subTest(key=key):
                original = copy.deepcopy(self.evidence)
                self.evidence['results'][0][key][0] = value
                self.save_evidence()
                result = self.compare()
                self.assertFalse(result['passed'])
                self.assertEqual(len(result['failures']), 1)
                self.evidence = original

    def test_plausible_count_and_p_changed_together_still_fail(self):
        self.evidence['results'][0]['exceedance_counts'][0] = 1
        self.evidence['results'][0]['adjusted_p'][0] = .4
        self.save_evidence()
        self.assertEqual(len(self.compare()['failures']), 2)

    def test_wrong_schema_fixture_hash_engine_and_active_count(self):
        for key, value in [('schemaVersion', 'wrong'), ('fixtureSha256', '0' * 64),
                           ('engineVersion', '1.6.1'), ('activeMetricCount', 11),
                           ('activeMetricCount', 12.0), ('nativeRuntime', ''), ('nativeRuntime', 42)]:
            with self.subTest(key=key, value=value):
                original = copy.deepcopy(self.evidence)
                self.evidence[key] = value
                self.save_evidence()
                with self.assertRaises(ValueError):
                    self.compare()
                self.evidence = original

    def test_actual_supplied_binary_hash_must_match(self):
        self.core.write_bytes(b'a different binary from the purported run')
        with self.assertRaisesRegex(ValueError, 'assembly hash'):
            self.compare()

    def test_correct_length_hex_hash_alone_does_not_suffice(self):
        self.evidence['coreAssemblySha256'] = 'a' * 64
        self.save_evidence()
        with self.assertRaisesRegex(ValueError, 'assembly hash'):
            self.compare()

    def test_missing_core_binary_is_not_optional(self):
        self.core.unlink()
        with self.assertRaises(OSError):
            self.compare()

    def test_missing_duplicate_extra_and_reordered_cases(self):
        originals = copy.deepcopy(self.evidence['results'])
        for rows in [originals[:1], originals + [originals[0]], list(reversed(originals)), [], [None]]:
            with self.subTest(rows=rows):
                self.evidence['results'] = rows
                self.save_evidence()
                with self.assertRaises(ValueError):
                    self.compare()

    def test_family_or_resample_count_mismatch_rejected(self):
        for key, value in [('family_size', 2), ('family_size', 3.0),
                           ('resample_count', 3), ('resample_count', 4.0)]:
            with self.subTest(key=key, value=value):
                original = copy.deepcopy(self.evidence)
                self.evidence['results'][0][key] = value
                self.save_evidence()
                with self.assertRaises(ValueError):
                    self.compare()
                self.evidence = original

    def test_missing_field_and_truncated_vectors_rejected(self):
        for key in ('exceedance_counts', 'adjusted_p', 'rejected'):
            for remove in (True, False):
                with self.subTest(key=key, remove=remove):
                    original = copy.deepcopy(self.evidence)
                    if remove:
                        del self.evidence['results'][0][key]
                    else:
                        self.evidence['results'][0][key].pop()
                    self.save_evidence()
                    with self.assertRaises(ValueError):
                        self.compare()
                    self.evidence = original

    def test_nonfinite_null_and_wrong_types_fail_closed(self):
        for key, invalids in [('exceedance_counts', [-1, 5, True, 2.0, None]),
                              ('adjusted_p', [math.nan, math.inf, None, True, '0.6', -1, 2, 10**400]),
                              ('rejected', [0, 1, None, 'false'])]:
            for value in invalids:
                with self.subTest(key=key, value=value):
                    original = copy.deepcopy(self.evidence)
                    self.evidence['results'][0][key][0] = value
                    self.save_evidence()
                    with self.assertRaises(ValueError):
                        self.compare()
                    self.evidence = original

    def test_fixtures_cannot_change_without_hash_change(self):
        self.fixture_doc['cases'][0]['resamples'].pop()
        self.fixtures.write_text(json.dumps(self.fixture_doc), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'fixture hash'):
            self.compare()

    def test_duplicate_fixture_ids_and_invalid_matrices_rejected(self):
        original = copy.deepcopy(self.fixture_doc)
        for kind in ('duplicate', 'missing', 'ragged', 'null'):
            with self.subTest(kind=kind):
                data = copy.deepcopy(original)
                if kind == 'duplicate':
                    data['cases'].append(copy.deepcopy(data['cases'][0]))
                elif kind == 'missing':
                    del data['cases'][0]['resamples']
                elif kind == 'ragged':
                    data['cases'][0]['resamples'][0].pop()
                else:
                    data['cases'][0]['resamples'][0][0] = None
                self.fixtures.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError):
                    maxt.load_fixtures(self.fixtures)

    def test_duplicate_json_fields_and_malformed_documents_rejected(self):
        for text in ('{"schemaVersion":"x","schemaVersion":"y"}', '[1,2]', '{',
                     '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(text=text):
                self.native.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.compare()

    def test_frozen_fixture_changes_rejected_even_if_self_consistent(self):
        document = maxt.build_fixtures()
        document['cases'][0]['id'] = 'renamed-but-arithmetically-identical'
        self.fixtures.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Frozen fixture'):
            maxt.audit_frozen_fixtures(self.fixtures)

    def test_output_exclusive_creation_preserves_prior_evidence(self):
        output = Path(self.temporary.name) / 'report.json'
        output.write_bytes(b'existing historical result')
        with self.assertRaises(FileExistsError):
            maxt.write_report(output, self.compare(), [self.fixtures, self.native, self.core])
        self.assertEqual(output.read_bytes(), b'existing historical result')

    def test_output_cannot_alias_input(self):
        before = self.fixtures.read_bytes()
        with self.assertRaisesRegex(ValueError, 'separate'):
            maxt.write_report(self.fixtures, self.compare(), [self.fixtures, self.native, self.core])
        self.assertEqual(self.fixtures.read_bytes(), before)

    def test_cli_default_checks_frozen_fixtures_only(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(maxt.main([]), 0)
        result = json.loads(output.getvalue())
        self.assertIn('native parity not checked', result['qualification'])

    def test_cli_requires_binary_and_emits_separate_comparison(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            maxt.main(['--native', str(self.native)])
        self.assertEqual(error.exception.code, 2)
        output = Path(self.temporary.name) / 'new-comparison.json'
        arguments = ['--fixtures', str(self.fixtures), '--native', str(self.native),
                     '--core-assembly', str(self.core), '--out', str(output)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(maxt.main(arguments), 0)
            before = output.read_bytes()
            self.assertEqual(maxt.main(arguments), 2)
        self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
