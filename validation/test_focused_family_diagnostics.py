"""Deterministic toy frames/corruption tests, never new scientific samples."""
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import focused_family_diagnostics as diagnostic
from test_holm_benchmark_diagnostics import frames


def input_case(values=None):
    values = [.01] + [None] * 11 if values is None else values
    return dict(id='synthetic-only', pValues=values,
                available=[value is not None for value in values])


def stability_row(index, left='median', right='median', status='completed'):
    return dict(split_index=str(index), status=status, diagnostics_status='retained',
        error='' if status == 'completed' else 'synthetic failure',
        kendall_tau='.5' if status == 'completed' else '',
        top_left=left if status == 'completed' else '', top_right=right if status == 'completed' else '',
        matched=str(left == right).lower() if status == 'completed' else '')


class ArithmeticTests(unittest.TestCase):
    def test_registry_families_are_fixed_ordered_and_partition_complete(self):
        self.assertEqual(list(diagnostic.FAMILIES), ['all12', 'location4', 'variability7',
            'absolute4', 'relative3', 'magnitude1'])
        partition_indices = [index for name in diagnostic.PARTITION for index in diagnostic.FAMILIES[name]]
        self.assertEqual(sorted(partition_indices), list(range(12)))
        self.assertEqual(len(partition_indices), len(set(partition_indices)))
        self.assertTrue(all(list(indices) == sorted(indices) for indices in diagnostic.FAMILIES.values()))

    def test_strict_boundary_neighbors_all_multipliers(self):
        for multiplier in (1, 3, 4, 7, 12, 16):
            threshold = .05/multiplier
            for p in (math.nextafter(threshold, 0), threshold, math.nextafter(threshold, 1)):
                values = [p] * 12
                indices = tuple(range(multiplier)) if multiplier <= 12 else tuple(range(4))
                result = diagnostic.family_reference(values, [True]*12, indices, 4 if multiplier == 16 else 1)
                self.assertEqual(result['members'][0]['adjustedP'], min(1, p*multiplier))
                self.assertEqual(result['anyRejected'], min(1, p*multiplier) < .05)
        result = diagnostic.case_reference(input_case([.05/4] + [None]*11))
        self.assertFalse(result['families']['location4']['anyRejected'])

    def test_unavailable_does_not_reduce_denominator(self):
        result = diagnostic.case_reference(input_case())
        self.assertEqual(result['availabilityStatus'], 'partially-available')
        self.assertEqual(result['families']['all12']['members'][0]['adjustedP'], .12)
        self.assertEqual(result['families']['location4']['members'][0]['adjustedP'], .04)
        self.assertEqual(result['families']['location4']['fullDenominator'], 4)
        self.assertEqual(result['families']['location4']['availableCount'], 1)
        self.assertTrue(result['families']['location4']['anyRejected'])
        self.assertFalse(result['simultaneousPartition']['anyRejected'])
        self.assertEqual(result['simultaneousPartition']['families']['location4']['multiplier'], 16)

    def test_all_unavailable_not_observed_nonrejection(self):
        result = diagnostic.case_reference(input_case([None]*12))
        self.assertEqual(result['availabilityStatus'], 'all-unavailable')
        self.assertIsNone(result['families']['all12']['minAdjustedP'])
        self.assertIsNone(result['simultaneousPartition']['minAdjustedP'])
        self.assertFalse(result['naiveFocusedUnion']['anyRejected'])
        self.assertTrue(all(not member['rejected'] and member['adjustedP'] is None
                            for member in result['families']['all12']['members']))

    def test_partition_direct_multiplication_not_compounded_rounding(self):
        values = [.1, .003, .004, .8, .9, .7, .6, .5, .01, .4, .3, .2]
        result = diagnostic.case_reference(input_case(values))
        for name in diagnostic.PARTITION:
            family = result['simultaneousPartition']['families'][name]
            self.assertEqual(family['multiplier'], 4*len(diagnostic.FAMILIES[name]))
            for member in family['members']:
                self.assertEqual(member['adjustedP'], min(1, values[member['index']]*family['multiplier']))
        self.assertEqual(result['simultaneousPartition']['rejectedMembers'],
                         ['standard_deviation', 'coefficient_of_variation', 'rms'])
        self.assertEqual(result['naiveFocusedUnion']['rejectedFamilies'], ['absolute4', 'relative3', 'magnitude1'])

    def test_invalid_vector_rejected(self):
        for values in ([None]*11, [None]*13, [float('nan')]+[None]*11,
                       [float('inf')]+[None]*11, [-.1]+[None]*11,
                       [1.1]+[None]*11, [True]+[None]*11, ['.01']+[None]*11):
            with self.subTest(values=values), self.assertRaises(ValueError):
                diagnostic.case_reference(input_case(values))
        for availability in ([False]*12, [None]+[False]*11, [1]+[False]*11, [True]*11):
            case = input_case()
            case['available'] = availability
            with self.subTest(availability=availability), self.assertRaises(ValueError):
                diagnostic.case_reference(case)

    def test_zero_one_and_capping(self):
        values = [0, 1]+[None]*10
        result = diagnostic.case_reference(input_case(values))['families']['all12']
        self.assertEqual([member['adjustedP'] for member in result['members'][:2]], [0, 1])
        self.assertEqual(result['rejectedMembers'], ['median'])


class FrameIntegrityTests(unittest.TestCase):
    def test_rectangular_frames_and_ids(self):
        inputs, cases = diagnostic.build_input(*frames())
        self.assertEqual(inputs['schemaVersion'], 'mvs-focused-family-input/v1')
        self.assertEqual(inputs['cases'][0]['id'], '["fixture","main","0"]')
        self.assertEqual(len(inputs['cases'][0]['pValues']), 12)
        self.assertTrue(cases[0]['analysis_eligible'])

    def test_duplicate_missing_and_reordered_metric_rows(self):
        for mutation in ('duplicate', 'missing', 'reordered', 'orphan'):
            data = frames()
            if mutation == 'duplicate': data[1].append(copy.deepcopy(data[1][0]))
            if mutation == 'missing': data[1].pop()
            if mutation == 'reordered': data[1][0], data[1][1] = data[1][1], data[1][0]
            if mutation == 'orphan': data[1][0]['replication_index'] = '9'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                diagnostic.build_input(*data)

    def test_duplicate_missing_procedures_and_reps(self):
        for target, mutation in ((0, 'duplicate'), (2, 'duplicate'), (2, 'missing'), (3, 'missing')):
            data = frames()
            if mutation == 'duplicate': data[target].append(copy.deepcopy(data[target][0]))
            else: data[target].pop()
            with self.subTest(target=target, mutation=mutation), self.assertRaises(ValueError):
                diagnostic.build_input(*data)

    def test_status_and_availability_corruption(self):
        mutations = [(0, 'status', 'unknown'), (0, 'diagnostics_status', 'legacy_missing'),
            (1, 'p_value', 'NaN'), (1, 'p_value', '1.01'), (1, 'observed_available', 'false'),
            (1, 'observed_available', ''), (1, 'rejected', 'false'),
            (2, 'rejected', ''), (0, 'replication_index', '-1')]
        for frame, key, value in mutations:
            data = frames()
            data[frame][0][key] = value
            with self.subTest(frame=frame, key=key), self.assertRaises(ValueError):
                diagnostic.build_input(*data)

    def test_missing_index_rejected(self):
        data = frames()
        for group in data[:3]:
            for row in group: row['replication_index'] = '1'
        with self.assertRaises(ValueError): diagnostic.build_input(*data)

    def test_failed_case_is_preserved_and_not_a_discovery(self):
        specs = [('fixture', 'main', 'completed', 'retained', [.01]+[None]*11),
                 ('fixture', 'main', 'failed', 'retained', [.00001]+[None]*11)]
        inputs, cases = diagnostic.build_input(*frames(specs))
        results = [diagnostic.case_reference(case) for case in inputs['cases']]
        summary = diagnostic.summarize_conditions(cases, results)[0]
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(summary['analyzedCompleted'], 1)
        self.assertEqual(summary['methods']['location4']['allRequested']['rate'], .5)
        self.assertEqual(summary['methods']['location4']['completedOnly']['rate'], 1)
        self.assertIn('operational', summary['methods']['location4']['allRequestedInterpretation'])
        self.assertEqual(summary['methods']['all12']['allRequested']['count'], 0)

    def test_failed_unknown_availability_is_invalid_never_fabricated_false(self):
        data = frames([('fixture', 'main', 'failed', 'retained', [None]*12)])
        data[1][0]['observed_available'] = ''
        with self.assertRaisesRegex(ValueError, 'twelve booleans'):
            diagnostic.build_input(*data)

    def test_baseline_checks_both_legacy_procedures(self):
        inputs, cases = diagnostic.build_input(*frames())
        results = [diagnostic.case_reference(case) for case in inputs['cases']]
        self.assertFalse(diagnostic.baseline_failures(cases, results))
        for procedure in ('bonferroni', 'mvs_registry_corrected'):
            changed = copy.deepcopy(cases)
            changed[0]['legacy_procedure_rejected'][procedure] = False
            self.assertEqual(len(diagnostic.baseline_failures(changed, results)), 1)

    def test_all_phases_report_separately_and_pair_gains_losses(self):
        specs = [('a', 'main', 'completed', 'retained', [.01]+[None]*11),
                 ('b', 'main', 'completed', 'retained', [None, .003]+[None]*10),
                 ('replay', 'replay-first', 'completed', 'retained', [.001]+[None]*11),
                 ('replay', 'replay-second', 'completed', 'retained', [.001]+[None]*11)]
        inputs, cases = diagnostic.build_input(*frames(specs))
        results = [diagnostic.case_reference(case) for case in inputs['cases']]
        summaries = diagnostic.summarize_conditions(cases, results)
        self.assertEqual(len(summaries), 4)
        self.assertEqual(summaries[0]['methods']['location4']['pairedVersusAll12']['candidateOnly'], 1)
        self.assertEqual(summaries[1]['methods']['location4']['pairedVersusAll12']['baselineOnly'], 1)
        self.assertEqual(summaries[2]['scientificRole'], 'reproducibility-only')


class ExactComparisonTests(unittest.TestCase):
    def test_each_output_field_is_checked(self):
        expected = diagnostic.native_reference(dict(cases=[input_case()]), 'a'*64, 'b'*64, 'c'*64)
        self.assertFalse(diagnostic.exact_compare(expected, copy.deepcopy(expected)))
        mutations = [
            lambda x: x.update(alpha=.051),
            lambda x: x['provenance'].update(coreSha256='d'*64),
            lambda x: x['familyDefinitions'][0].update(fullDenominator=11),
            lambda x: x['cases'][0].update(id='other'),
            lambda x: x['cases'][0].update(availabilityStatus='all-available'),
            lambda x: x['cases'][0]['families']['all12']['members'][0].update(adjustedP=.12000000000000001),
            lambda x: x['cases'][0]['families']['location4'].update(anyRejected=False),
            lambda x: x['cases'][0]['simultaneousPartition'].update(familyCount=3),
            lambda x: x['cases'][0]['naiveFocusedUnion'].update(interpretation='controlled'),
            lambda x: x['cases'][0]['families']['all12']['members'][1].update(adjustedP=0),
            lambda x: x['cases'][0]['families']['location4'].update(anyRejected=1),
            lambda x: x['cases'].append(copy.deepcopy(x['cases'][0])),
            lambda x: x.update(extra='unexpected'),
        ]
        for mutation in mutations:
            changed = copy.deepcopy(expected)
            mutation(changed)
            self.assertTrue(diagnostic.exact_compare(expected, changed))

    def test_numeric_nan_and_type_corruption(self):
        for value in (float('nan'), float('inf'), True, None, '.1'):
            self.assertTrue(diagnostic.exact_compare(.1, value))
        self.assertFalse(diagnostic.exact_compare(1.0, 1))
        self.assertTrue(diagnostic.exact_compare(True, 1))

    def test_duplicate_json_key_nonfinite_and_symlink_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'file.json'
            for content in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
                path.write_text(content)
                with self.assertRaises(ValueError): diagnostic.read_json(path)
            path.write_text('{}')
            link = Path(tmp)/'link.json'
            link.symlink_to(path)
            with self.assertRaises(ValueError): diagnostic.read_json(link)


class StabilityTests(unittest.TestCase):
    def test_known_confusion_chance_and_kappa(self):
        # Two exact matches; four same-family matches after fixed coarsening.
        rows = diagnostic.validate_stability([stability_row(0, 'median', 'mean'),
            stability_row(1, 'mean', 'mean'), stability_row(2, 'mad', 'iqr'),
            stability_row(3, 'mad', 'mad')])
        result = diagnostic.summarize_stability(rows)
        self.assertEqual(result['exactMetric']['agreement']['count'], 2)
        self.assertEqual(result['exactMetric']['independentMarginalChanceAgreement'], .25)
        self.assertAlmostEqual(result['exactMetric']['cohenKappa'], 1/3)
        coarse = result['registeredFamilyCoarsening']
        self.assertEqual(coarse['confusionMatrix'], [[2,0,0],[0,2,0],[0,0,0]])
        self.assertEqual(coarse['leftMarginals'], {'location4':2, 'variability7':2, 'magnitude1':0})
        self.assertEqual(coarse['independentMarginalChanceAgreement'], .5)
        self.assertEqual(coarse['cohenKappa'], 1)
        self.assertEqual(result['partition4Coarsening']['agreement']['count'], 4)

    def test_asymmetric_marginals_and_cross_family(self):
        rows = diagnostic.validate_stability([stability_row(0, 'median', 'median'),
            stability_row(1, 'median', 'mad'), stability_row(2, 'mad', 'mad')])
        coarse = diagnostic.summarize_stability(rows)['registeredFamilyCoarsening']
        self.assertEqual(coarse['confusionMatrix'], [[1,1,0],[0,1,0],[0,0,0]])
        self.assertAlmostEqual(coarse['independentMarginalChanceAgreement'], 4/9)
        self.assertAlmostEqual(coarse['cohenKappa'], .4)

    def test_constant_label_kappa_undefined_and_failed_explicit(self):
        rows = diagnostic.validate_stability([stability_row(0), stability_row(1, status='failed')])
        result = diagnostic.summarize_stability(rows)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['exactMetric']['independentMarginalChanceAgreement'], 1)
        self.assertIsNone(result['exactMetric']['cohenKappa'])
        self.assertEqual(result['exactMetric']['agreement']['denominator'], 1)

    def test_all_failed_has_no_rate_or_kappa(self):
        rows = diagnostic.validate_stability([stability_row(0, status='failed')])
        result = diagnostic.summarize_stability(rows)
        self.assertIsNone(result['exactMetric']['agreement']['rate'])
        self.assertIsNone(result['exactMetric']['independentMarginalChanceAgreement'])
        self.assertIsNone(result['retainedArchivedWholeRegistryStatistic']['mean'])

    def test_stability_corruptions_fail_closed(self):
        for key, value in [('split_index', '-1'), ('split_index', '01'), ('status', 'unknown'),
            ('diagnostics_status', 'legacy_missing'), ('kendall_tau', 'NaN'),
            ('kendall_tau', '1.01'), ('top_left', 'invented'), ('top_right', ''), ('matched', 'false')]:
            row = stability_row(0)
            row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                diagnostic.validate_stability([row])
        with self.assertRaises(ValueError):
            diagnostic.validate_stability([stability_row(0), stability_row(0)])
        with self.assertRaises(ValueError): diagnostic.validate_stability([stability_row(1)])
        with self.assertRaises(ValueError): diagnostic.validate_stability([stability_row(0)], 120)

    def test_wilson_known_interval_and_zero_denominator(self):
        self.assertEqual(diagnostic.wilson(0, 0)['wilson95'], None)
        lower, upper = diagnostic.wilson(5, 10)['wilson95']
        self.assertAlmostEqual(lower, .236593090512564)
        self.assertAlmostEqual(upper, .763406909487436)
        self.assertAlmostEqual(diagnostic.wilson(0, 10)['wilson95'][1], .2775327998628892)
        with self.assertRaises(ValueError): diagnostic.wilson(11, 10)


class ProtocolAndPipelineTests(unittest.TestCase):
    def test_protocol_hash_contract_and_source_corruption(self):
        template = diagnostic.read_json(Path(diagnostic.__file__).with_name('focused-family-protocol-v1.json'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_hashes = dict(template['inputSha256'])
            for name in diagnostic.PROTOCOL_SOURCES:
                file = root/name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('synthetic-source-only')
                template['sourceSha256'][name] = diagnostic.sha256(file)
            protocol = root/'protocol.json'
            protocol.write_bytes(diagnostic.json_bytes(template))
            digest = diagnostic.sha256(protocol)
            diagnostic.validate_protocol(protocol, digest, root, source_hashes)
            with self.assertRaises(ValueError): diagnostic.validate_protocol(protocol, 'a'*64, root, source_hashes)
            (root/diagnostic.PROTOCOL_SOURCES[0]).write_text('changed')
            with self.assertRaises(ValueError): diagnostic.validate_protocol(protocol, digest, root, source_hashes)
            (root/diagnostic.PROTOCOL_SOURCES[0]).write_text('synthetic-source-only')
            for mutation in ('families', 'priorInspectedResults', 'inputSha256'):
                changed = copy.deepcopy(template)
                changed[mutation] = {}
                protocol.write_bytes(diagnostic.json_bytes(changed))
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    diagnostic.validate_protocol(protocol, diagnostic.sha256(protocol), root, source_hashes)

    def synthetic_pipeline(self, root):
        inputs, cases = diagnostic.build_input(*frames())
        stability = diagnostic.validate_stability([stability_row(0)])
        protocol = root/'protocol.json'
        protocol.write_text('synthetic-only')
        digest = diagnostic.sha256(protocol)
        source = {'protocol': {'path': str(protocol), 'sha256': digest}}
        data = (inputs, cases, stability, source, {'priorInspectedResults': diagnostic.PRIOR_INSPECTED})
        out, archive = root/'out', root/'archive'
        archive.mkdir()
        core, harness = root/'core.dll', root/'harness.dll'
        core.write_bytes(b'synthetic-core-not-native')
        harness.write_bytes(b'synthetic-harness-not-native')
        common = archive, out, protocol, digest
        with patch.object(diagnostic, 'load_source', return_value=data), patch.object(diagnostic, 'tool_hashes', return_value={}):
            diagnostic.prepare(*common)
        native_path = out/diagnostic.NATIVE_FILE
        native = diagnostic.native_reference(inputs, diagnostic.sha256(out/diagnostic.INPUT_FILE),
                                             diagnostic.sha256(core), diagnostic.sha256(harness))
        native_path.write_bytes(diagnostic.json_bytes(native))
        return data, common, (native_path, core, harness)

    def test_three_phases_bind_files_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, common, native_args = self.synthetic_pipeline(Path(tmp))
            with patch.object(diagnostic, 'load_source', return_value=data), patch.object(diagnostic, 'tool_hashes', return_value={}):
                result = diagnostic.compare(*common, *native_args)
                self.assertEqual(result['status'], 'passed')
                self.assertEqual(result['archivedBaselineDecisionsCompared'], 2)
                result = diagnostic.report(*common, *native_args)
                self.assertEqual(result['status'], 'passed')
                summary = diagnostic.read_json(common[1]/diagnostic.SUMMARY_FILE)
                self.assertIsNone(summary['candidateSelected'])
                self.assertIsNone(summary['newScientificVerdict'])
                self.assertEqual(len(summary['conditionPhaseSummaries']), 1)
                self.assertTrue((common[1]/diagnostic.CHECKSUM_FILE).exists())
                with self.assertRaises(ValueError): diagnostic.prepare(*common)
                with self.assertRaises(ValueError): diagnostic.compare(*common, *native_args)
                with self.assertRaises(ValueError): diagnostic.report(*common, *native_args)

    def test_mutated_native_or_assembly_cannot_pass(self):
        for target in ('native', 'assembly'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                data, common, native_args = self.synthetic_pipeline(Path(tmp))
                if target == 'native':
                    native = diagnostic.read_json(native_args[0])
                    native['cases'][0]['families']['all12']['members'][0]['adjustedP'] += .000001
                    native_args[0].write_bytes(diagnostic.json_bytes(native))
                else: native_args[1].write_bytes(b'changed-core')
                with patch.object(diagnostic, 'load_source', return_value=data), patch.object(diagnostic, 'tool_hashes', return_value={}):
                    result = diagnostic.compare(*common, *native_args)
                    self.assertEqual(result['status'], 'failed')
                    with self.assertRaises(ValueError): diagnostic.report(*common, *native_args)
                    self.assertFalse((common[1]/diagnostic.SUMMARY_FILE).exists())

    def test_prepared_input_provenance_and_tools_cannot_change(self):
        for target in ('input', 'provenance', 'tools'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                data, common, native_args = self.synthetic_pipeline(Path(tmp))
                out = common[1]
                if target == 'input': (out/diagnostic.INPUT_FILE).write_text('{}')
                if target == 'provenance': (out/diagnostic.PROVENANCE_FILE).write_text('{}')
                tool_hashes = {'changed': 'a'*64} if target == 'tools' else {}
                with patch.object(diagnostic, 'load_source', return_value=data), patch.object(diagnostic, 'tool_hashes', return_value=tool_hashes):
                    with self.assertRaises(ValueError): diagnostic.compare(*common, *native_args)
                    self.assertFalse((out/diagnostic.COMPARISON_FILE).exists())

    def test_per_case_or_comparison_corruption_blocks_report(self):
        for filename in (diagnostic.CASES_FILE, diagnostic.COMPARISON_FILE):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                data, common, native_args = self.synthetic_pipeline(Path(tmp))
                with patch.object(diagnostic, 'load_source', return_value=data), patch.object(diagnostic, 'tool_hashes', return_value={}):
                    diagnostic.compare(*common, *native_args)
                    (common[1]/filename).write_text('{}')
                    with self.assertRaises(ValueError): diagnostic.report(*common, *native_args)
                    self.assertFalse((common[1]/diagnostic.SUMMARY_FILE).exists())

    def test_output_inside_archive_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)/'archive'
            archive.mkdir()
            with self.assertRaises(ValueError): diagnostic.check_output(archive, archive/'out')
            with self.assertRaises(ValueError): diagnostic.check_output(archive, archive)
            link = Path(tmp)/'out'
            link.symlink_to(Path(tmp)/'target')
            with self.assertRaises(ValueError): diagnostic.check_output(archive, link)


if __name__ == '__main__':
    unittest.main()
