"""Small synthetic frames and explicitly fake native documents; no native claim."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import holm_benchmark_diagnostics as diagnostic


def frames(specifications=None):
    """Each specification is (condition, phase, status, diagnostics, p-values)."""
    if specifications is None:
        specifications = [('fixture', 'main', 'completed', 'retained', [.001, .0044, .0044] + [None] * 9)]
    reps, metrics, procedures, summaries = [], [], [], []
    groups = {}
    for condition, phase, status, retained, values in specifications:
        key = condition, phase
        index = groups.get(key, 0)
        groups[key] = index + 1
        identity = dict(condition=condition, phase=phase, replication_index=str(index))
        reps.append(dict(identity, status=status, diagnostics_status=retained,
                         error='fixture failure' if status == 'failed' else ''))
        for metric, p in zip(diagnostic.METRICS, values):
            metrics.append(dict(identity, metric=metric, p_value='' if p is None else str(p),
                observed_available=('true' if p is not None else 'false') if retained == 'retained' else '',
                rejected=str(p is not None and p < .05).lower() if status == 'completed' else ''))
        for name in diagnostic.raw_check.PROCEDURES:
            cutoff = .05 / 12 if name in ('bonferroni', 'mvs_registry_corrected') else .05
            rejected = any(p is not None and p < cutoff for p in values)
            procedures.append(dict(identity, procedure=name, chosen_metric='median' if status == 'completed' else '',
                claimed='true' if status == 'completed' else '',
                rejected=str(rejected).lower() if status == 'completed' else ''))
    for condition in dict.fromkeys(key[0] for key in groups):
        condition_groups = [(phase, count) for (name, phase), count in groups.items() if name == condition]
        phase, count = condition_groups[0]
        for name in diagnostic.raw_check.PROCEDURES:
            summaries.append(dict(condition=condition, procedure=name, planned=str(count),
                                  stage='determinism' if phase.startswith('replay-') else 'primary'))
    return reps, metrics, procedures, summaries


def fake_native(fixture, fixture_digest='f' * 64, assembly_digest='a' * 64):
    """Deliberately fake evidence for orchestration tests, never archived as native."""
    rows = []
    for case in fixture['cases']:
        expected = diagnostic.multiplicity_reference.reference(case['p_values'], 12)
        row = dict(id=case['id'], **expected)
        for method, values in expected.items():
            row[method + '_rejected'] = [p is not None and p < .05 for p in values]
        rows.append(row)
    return dict(schema='MVS-MULTIPLICITY-NATIVE-1', fixtureSha256=fixture_digest,
                coreAssemblySha256=assembly_digest, engineVersion='1.6.2', activeMetricCount=12,
                nativeRuntime='fake-unit-test-only', results=rows)


class FrameChecks(unittest.TestCase):
    def test_ties_yield_additional_members_with_same_any_event(self):
        fixture = diagnostic.build_fixtures(*frames())
        native = fake_native(fixture)
        rows, metrics, excluded, failures = diagnostic.summarize(fixture, native)
        self.assertFalse(failures)
        self.assertFalse(excluded)
        row = rows[0]
        self.assertEqual(row['bonferroni_any_rejection'], 1)
        self.assertEqual(row['holm_any_rejection'], 1)
        self.assertEqual(row['bonferroni_member_discoveries'], 1)
        self.assertEqual(row['holm_member_discoveries'], 3)
        self.assertEqual(row['additional_holm_members'], 2)
        self.assertEqual(row['replications_with_additional_holm_members'], 1)
        self.assertEqual(metrics[0]['metrics'][1]['additional_holm_discoveries'], 1)
        self.assertEqual(fixture['metric_order'], list(diagnostic.METRICS))

    def test_null_slots_keep_fixed_twelve(self):
        fixture = diagnostic.build_fixtures(*frames([
            ('fixture', 'main', 'completed', 'retained', [.01] + [None] * 11)]))
        native = fake_native(fixture)
        self.assertEqual(native['results'][0]['bonferroni'][0], .12)
        self.assertEqual(native['results'][0]['holm'][0], .12)
        self.assertEqual(native['results'][0]['holm'][1:], [None] * 11)
        rows, _, _, failures = diagnostic.summarize(fixture, native)
        self.assertFalse(failures)
        self.assertEqual(rows[0]['unavailable_slots'], 11)
        self.assertEqual(rows[0]['holm_any_rejection'], 0)

    def test_all_unavailable_remains_a_case(self):
        fixture = diagnostic.build_fixtures(*frames([
            ('fixture', 'main', 'completed', 'retained', [None] * 12)]))
        native = fake_native(fixture)
        self.assertEqual(native['results'][0]['holm'], [None] * 12)
        self.assertEqual(len(fixture['cases']), 1)

    def test_failed_partial_and_missing_are_explicit_not_counted(self):
        fixture = diagnostic.build_fixtures(*frames([
            ('fixture', 'main', 'completed', 'retained', [.001] + [None] * 11),
            ('fixture', 'main', 'failed', 'retained', [.0001] + [None] * 11),
            ('fixture', 'main', 'completed', 'legacy_missing', [None] * 12),
            ('fixture', 'main', 'unknown_legacy', 'legacy_missing', [None] * 12)]))
        rows, _, excluded, failures = diagnostic.summarize(fixture, fake_native(fixture))
        self.assertFalse(failures)
        self.assertEqual(len(fixture['cases']), 4)
        row = rows[0]
        self.assertEqual([row[x] for x in ('planned', 'completed', 'failed', 'unknown_status',
            'missing_diagnostics', 'analyzed_completed', 'not_analyzed')], [4, 2, 1, 1, 2, 1, 3])
        self.assertEqual(row['holm_member_discoveries'], 1)
        self.assertEqual(row['unknown_availability_slots'], 24)
        self.assertEqual(excluded[0]['error'], 'fixture failure')
        self.assertEqual(fixture['cases'][1]['p_values'][0], .0001)

    def test_replay_phases_and_conditions_are_separate(self):
        fixture = diagnostic.build_fixtures(*frames([
            ('main-a', 'main', 'completed', 'retained', [.001] + [None] * 11),
            ('main-b', 'main', 'completed', 'retained', [.8] * 12),
            ('replay', 'replay-first', 'completed', 'retained', [.001] + [None] * 11),
            ('replay', 'replay-second', 'completed', 'retained', [.001] + [None] * 11)]))
        self.assertEqual(len({case['id'] for case in fixture['cases']}), 4)
        rows, _, _, _ = diagnostic.summarize(fixture, fake_native(fixture))
        self.assertEqual([(row['condition'], row['phase']) for row in rows],
                         [('main-a', 'main'), ('main-b', 'main'), ('replay', 'replay-first'), ('replay', 'replay-second')])
        self.assertTrue(all(row['planned'] == 1 for row in rows))
        self.assertFalse(any('rate' in key for row in rows for key in row))

    def test_duplicate_replication_refused(self):
        inputs = frames()
        inputs[0].append(inputs[0][0].copy())
        with self.assertRaisesRegex(ValueError, 'Duplicate replication'):
            diagnostic.build_fixtures(*inputs)

    def test_metric_missing_duplicate_reordered_and_orphan_refused(self):
        for mutation in ('missing', 'duplicate', 'reordered', 'orphan'):
            with self.subTest(mutation=mutation):
                inputs = frames()
                if mutation == 'missing':
                    inputs[1].pop()
                elif mutation == 'duplicate':
                    inputs[1][-1] = inputs[1][0].copy()
                elif mutation == 'reordered':
                    inputs[1][:2] = inputs[1][1::-1]
                else:
                    inputs[1][0]['condition'] = 'ghost'
                with self.assertRaises(ValueError):
                    diagnostic.build_fixtures(*inputs)

    def test_bad_p_and_availability_refused(self):
        for p, available in [('nan', 'true'), ('inf', 'true'), ('-1', 'true'),
                             ('1.01', 'true'), ('.001', 'false'), ('', 'true')]:
            with self.subTest(p=p, available=available):
                inputs = frames()
                inputs[1][0].update(p_value=p, observed_available=available)
                with self.assertRaises(ValueError):
                    diagnostic.build_fixtures(*inputs)

    def test_missing_phase_or_planned_index_refused(self):
        inputs = frames([('fixture', 'replay-first', 'completed', 'retained', [.5] * 12)])
        with self.assertRaisesRegex(ValueError, 'diagnostic phases'):
            diagnostic.build_fixtures(*inputs)
        inputs = frames()
        for row in inputs[3]:
            row['planned'] = '2'
        with self.assertRaisesRegex(ValueError, 'planned replication indices'):
            diagnostic.build_fixtures(*inputs)

    def test_failed_decision_cannot_be_counted(self):
        inputs = frames([('fixture', 'main', 'failed', 'retained', [.001] + [None] * 11)])
        inputs[1][0]['rejected'] = 'true'
        with self.assertRaisesRegex(ValueError, 'decision presence'):
            diagnostic.build_fixtures(*inputs)

    def test_unknown_with_retained_diagnostics_refused(self):
        inputs = frames([('fixture', 'main', 'unknown_legacy', 'retained', [None] * 12)])
        with self.assertRaisesRegex(ValueError, 'Unknown status'):
            diagnostic.build_fixtures(*inputs)

    def test_native_bonferroni_legacy_disagreement_is_failure(self):
        fixture = diagnostic.build_fixtures(*frames())
        fixture['cases'][0]['legacy_procedure_rejected']['bonferroni'] = False
        _, _, _, failures = diagnostic.summarize(fixture, fake_native(fixture))
        self.assertTrue(any('legacy bonferroni' in x for x in failures))

    def test_any_rejection_mismatch_is_failure(self):
        fixture = diagnostic.build_fixtures(*frames())
        native = fake_native(fixture)
        native['results'][0]['holm_rejected'] = [False] * 12
        _, _, _, failures = diagnostic.summarize(fixture, native)
        self.assertTrue(any('any-rejection' in x for x in failures))


class SourceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in diagnostic.FROZEN_HASHES:
            (self.root / name).write_text('synthetic checksum fixture: ' + name)
        self.pins = {name: diagnostic.sha256(self.root / name) for name in diagnostic.FROZEN_HASHES}
        self.write_checksums()

    def write_checksums(self, pins=None):
        (self.root / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in (pins or self.pins).items()))

    def test_all_targets_including_manifest_and_checksum_list_are_hashed(self):
        with patch.object(diagnostic, 'FROZEN_HASHES', self.pins):
            hashes = diagnostic.source_hashes(self.root)
        self.assertEqual(len(hashes), 13)
        self.assertEqual(hashes['benchmark_manifest.json'], self.pins['benchmark_manifest.json'])
        self.assertEqual(hashes['SHA256SUMS.txt'], diagnostic.sha256(self.root / 'SHA256SUMS.txt'))

    def test_unrecognized_source_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'frozen development source'):
            diagnostic.source_hashes(self.root)

    def test_source_tampering_refused(self):
        (self.root / 'benchmark_manifest.json').write_text('tampered')
        with patch.object(diagnostic, 'FROZEN_HASHES', self.pins), self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            diagnostic.source_hashes(self.root)

    def test_missing_duplicate_and_unsafe_checksum_targets_refused(self):
        original = (self.root / 'SHA256SUMS.txt').read_text()
        for text in (original.split('\n', 1)[1], original + original.splitlines()[0] + '\n',
                     '0' * 64 + '  ../outside\n', '0' * 64 + '  /absolute\n',
                     '0' * 64 + '  subdir\\outside\n'):
            with self.subTest(text=text[:70]), patch.object(diagnostic, 'FROZEN_HASHES', self.pins):
                (self.root / 'SHA256SUMS.txt').write_text(text)
                with self.assertRaises(ValueError):
                    diagnostic.source_hashes(self.root)

    def test_source_symlink_refused(self):
        path = self.root / 'benchmark_choices.csv'
        original = path.read_bytes()
        path.unlink()
        target = self.root / 'target'
        target.write_bytes(original)
        path.symlink_to(target)
        with patch.object(diagnostic, 'FROZEN_HASHES', self.pins), self.assertRaisesRegex(ValueError, 'regular evidence'):
            diagnostic.source_hashes(self.root)

    def test_fixed_identity_fields_and_budgets(self):
        manifest = dict(diagnostic.IDENTITY, thresholds={'alpha': .05},
            replications=dict(primary=1000, grid=250, calibration=1000, stability=120, determinism=60),
            files=[name for name in diagnostic.FROZEN_HASHES if name != 'benchmark_manifest.json'])
        diagnostic.validate_identity(manifest)
        for field, value in [('engineVersion', '1.6.0'), ('profile', 'quick'), ('seed', 17),
                             ('protocolHash', 'f' * 64), ('overall', 'go'), ('protocolUnchanged', 1)]:
            changed = dict(manifest, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                diagnostic.validate_identity(changed)

    def test_round4_reconciliation_failure_is_propagated(self):
        (self.root / 'benchmark_manifest.json').write_text('{}')
        with patch.object(diagnostic, 'source_hashes', return_value={}), \
             patch.object(diagnostic, 'validate_identity'), \
             patch.object(diagnostic.raw_check, 'validate', side_effect=ValueError('R4 inconsistency')):
            with self.assertRaisesRegex(ValueError, 'R4 inconsistency'):
                diagnostic.load_source(self.root)


class WorkflowChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.benchmark = self.root / 'frozen'
        self.benchmark.mkdir()
        self.out = self.root / 'derived'
        self.assembly = self.root / 'FakeCore.dll'
        self.assembly.write_bytes(b'explicitly fake unit-test assembly, not executable')
        self.fixture = diagnostic.build_fixtures(*frames())
        self.source = dict(identity=dict(diagnostic.IDENTITY), source_sha256={'fixture-source': 's' * 64},
                           replication_rows=1, metric_rows=12, raw_reconciliation={'status': 'passed'})
        self.loader = patch.object(diagnostic, 'load_source', side_effect=lambda _: (copy.deepcopy(self.fixture), copy.deepcopy(self.source)))
        self.hashes = patch.object(diagnostic, 'source_hashes', side_effect=lambda _: self.source['source_sha256'])
        self.loader.start()
        self.hashes.start()
        self.addCleanup(self.loader.stop)
        self.addCleanup(self.hashes.stop)

    def prepare_native(self):
        result = diagnostic.prepare(self.benchmark, self.out)
        self.native_path = self.out / diagnostic.NATIVE_FILE
        native = fake_native(self.fixture, result['fixture_sha256'], diagnostic.sha256(self.assembly))
        self.native_path.write_bytes(diagnostic.json_bytes(native))
        return native

    def analyze(self):
        return diagnostic.analyze(self.benchmark, self.out, self.native_path, self.assembly)

    def test_two_phase_workflow_seven_files_checksums_and_immutable_preparation(self):
        self.prepare_native()
        before = {name: (self.out / name).read_bytes() for name in diagnostic.PREPARED_FILES}
        result = self.analyze()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['comparisons'], 24)
        self.assertEqual({p.name for p in self.out.iterdir()}, set(diagnostic.PREPARED_FILES) |
                         set(diagnostic.RESULT_FILES) | {diagnostic.NATIVE_FILE})
        self.assertEqual(before, {name: (self.out / name).read_bytes() for name in before})
        for line in (self.out / 'SHA256SUMS.txt').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(diagnostic.sha256(self.out / name), digest)
        report = diagnostic.read_json(self.out / 'diagnostics.json')
        self.assertEqual(report['original_scientific_verdict'], 'NO-GO')
        self.assertIsNone(report['new_benchmark_scientific_verdict'])
        self.assertEqual(report['core_assembly_sha256'], diagnostic.sha256(self.assembly))
        self.assertEqual(report['native_sha256'], diagnostic.sha256(self.native_path))

    def test_prepare_refuses_existing_output_and_source_descendant(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError, 'existing output directory'):
            diagnostic.prepare(self.benchmark, self.out)
        with self.assertRaisesRegex(ValueError, 'outside the immutable'):
            diagnostic.prepare(self.benchmark, self.benchmark / 'derived')

    def test_analyze_refuses_every_existing_result_file_without_overwriting(self):
        self.prepare_native()
        for name in diagnostic.RESULT_FILES:
            with self.subTest(name=name):
                path = self.out / name
                path.write_bytes(b'previous evidence')
                with self.assertRaisesRegex(ValueError, 'existing result files'):
                    self.analyze()
                self.assertEqual(path.read_bytes(), b'previous evidence')
                path.unlink()

    def test_prepared_fixture_tampering_refused(self):
        self.prepare_native()
        path = self.out / 'multiplicity-fixtures.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'fixture was changed'):
            self.analyze()

    def test_provenance_tampering_refused(self):
        self.prepare_native()
        path = self.out / 'provenance.json'
        doc = diagnostic.read_json(path)
        doc['source']['identity']['overall'] = 'go'
        path.write_bytes(diagnostic.json_bytes(doc))
        with self.assertRaisesRegex(ValueError, 'provenance was changed'):
            self.analyze()

    def test_source_changed_between_prepare_and_analysis_refused(self):
        self.prepare_native()
        self.source['source_sha256']['fixture-source'] = 't' * 64
        with self.assertRaisesRegex(ValueError, 'Prepared source'):
            self.analyze()

    def test_native_binary_and_fixture_provenance_refused(self):
        original = self.prepare_native()
        for field in ('fixtureSha256', 'coreAssemblySha256'):
            changed = dict(original, **{field: '0' * 64})
            self.native_path.write_bytes(diagnostic.json_bytes(changed))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.analyze()

    def test_actual_binary_tampering_refused(self):
        self.prepare_native()
        self.assembly.write_bytes(b'changed supplied binary')
        with self.assertRaisesRegex(ValueError, 'assembly hash mismatch'):
            self.analyze()

    def test_invalid_native_shapes_types_and_order_refused(self):
        original = self.prepare_native()
        for mutation in ('missing', 'duplicate', 'short', 'bool-number', 'number-bool', 'null-rejected'):
            native = copy.deepcopy(original)
            if mutation == 'missing':
                native['results'].clear()
            elif mutation == 'duplicate':
                native['results'].append(native['results'][0])
            elif mutation == 'short':
                native['results'][0]['holm'].pop()
            elif mutation == 'bool-number':
                native['results'][0]['holm'][0] = True
            elif mutation == 'number-bool':
                native['results'][0]['holm_rejected'][0] = 1
            else:
                native['results'][0]['holm_rejected'] = None
            self.native_path.write_bytes(diagnostic.json_bytes(native))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.analyze()

    def test_reference_mismatch_is_written_as_diagnostic_failure(self):
        native = self.prepare_native()
        native['results'][0]['holm'][0] = .02
        self.native_path.write_bytes(diagnostic.json_bytes(native))
        result = self.analyze()
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(diagnostic.read_json(self.out / 'multiplicity-comparison.json')['passed'])
        self.assertEqual(diagnostic.read_json(self.out / 'diagnostics.json')['status'], 'failed')

    def test_legacy_disagreement_is_written_as_diagnostic_failure(self):
        self.fixture['cases'][0]['legacy_procedure_rejected']['bonferroni'] = False
        self.prepare_native()
        result = self.analyze()
        self.assertEqual(result['status'], 'failed')
        comparison = diagnostic.read_json(self.out / 'multiplicity-comparison.json')
        self.assertEqual(comparison['failures'], [])
        self.assertFalse(comparison['legacy_decision_agreement'])

    def test_missing_diagnostics_is_incomplete_with_original_no_go(self):
        self.fixture = diagnostic.build_fixtures(*frames([
            ('fixture', 'main', 'completed', 'legacy_missing', [None] * 12)]))
        self.source['raw_reconciliation']['status'] = 'incomplete'
        self.prepare_native()
        self.assertEqual(self.analyze()['status'], 'incomplete')
        report = diagnostic.read_json(self.out / 'diagnostics.json')
        self.assertEqual(len(report['excluded_replications']), 1)
        self.assertEqual(report['condition_phase_summaries'][0]['missing_diagnostics'], 1)

    def test_evidence_changed_during_reference_is_refused(self):
        self.prepare_native()
        real_compare = diagnostic.multiplicity_reference.compare
        def changing_compare(*args):
            result = real_compare(*args)
            self.native_path.write_bytes(self.native_path.read_bytes() + b' ')
            return result
        with patch.object(diagnostic.multiplicity_reference, 'compare', side_effect=changing_compare):
            with self.assertRaisesRegex(ValueError, 'Evidence changed during analysis'):
                self.analyze()
        self.assertTrue(all(not (self.out / name).exists() for name in diagnostic.RESULT_FILES))

    def test_duplicate_json_keys_and_nonfinite_json_are_refused(self):
        self.prepare_native()
        for content in ('{"schema":1,"schema":2}', '{"value":NaN}'):
            self.native_path.write_text(content)
            with self.assertRaises(ValueError):
                self.analyze()


if __name__ == '__main__':
    unittest.main()
