"""Independent synthetic CSV fixtures, not a substitute for native execution."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

import check_benchmark_diagnostics as check


class DiagnosticChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.tables = {
            'benchmark_stability_replications.csv': [
                dict(split_index='0', status='completed', diagnostics_status='retained', error='',
                     kendall_tau='.25', top_left='median', top_right='median', matched='true'),
                dict(split_index='1', status='failed', diagnostics_status='retained', error='fixture',
                     kendall_tau='', top_left='', top_right='', matched='')],
            'benchmark_stability.csv': [dict(split='1', kendall_tau='.25')]}
        self.tables['benchmark_replications.csv'] = [dict(
            condition='fixture', phase='main', replication_index=str(i), half=str(i % 2),
            status='completed' if i == 0 else 'failed', diagnostics_status='retained',
            error='' if i == 0 else 'InvalidDataException: unavailable, "example"\nsecond line',
            run_seed='17', seed_stage='1', seed_stream='0', derived_seed=str(i + 123),
            calibration_seed='99' if i == 0 else '') for i in range(2)]
        procedures, metrics, summaries, metric_summaries, choices = [], [], [], [], []
        for i in range(2):
            for proc in check.PROCEDURES:
                withheld = proc == 'mvs_strict'
                reject = proc not in ('mvs_strict', 'fixed_cv')
                chosen = 'none' if withheld else 'coefficient_of_variation' if proc == 'fixed_cv' else 'median'
                procedures.append(dict(condition='fixture', phase='main', replication_index=str(i),
                    procedure=proc, chosen_metric=chosen if i == 0 else '',
                    claimed=str(not withheld).lower() if i == 0 else '',
                    rejected=str(reject).lower() if i == 0 else ''))
                if i == 0:
                    summaries.append(dict(condition='fixture', stage='primary', procedure=proc, planned='2', completed='1',
                        failed='1', rejections=str(int(reject)), rate=str(int(reject)), claim_rate=str(int(not withheld))))
                    choices.append(dict(condition='fixture', procedure=proc, metric=chosen, count='1'))
            for metric in check.METRICS:
                p = '.001' if metric == 'median' else '.5'
                metrics.append(dict(condition='fixture', phase='main', replication_index=str(i), metric=metric,
                    p_value=p if i == 0 else '', observed_available='true' if i == 0 else '',
                    rejected=str(metric == 'median').lower() if i == 0 else '',
                    calibration_applicable='true' if i == 0 else '', calibration_score='30' if i == 0 else '',
                    gate_location='false' if i == 0 else '', gate_variability='false' if i == 0 else '',
                    gate_heterogeneity='false' if i == 0 else ''))
                if i == 0:
                    metric_summaries.append(dict(condition='fixture', metric=metric, completed='1',
                                                rejections=str(int(metric == 'median'))))
        self.tables.update({'benchmark_replication_procedures.csv': procedures,
                           'benchmark_replication_metrics.csv': metrics,
                           'benchmark_summary.csv': summaries,
                           'benchmark_metrics.csv': metric_summaries,
                           'benchmark_choices.csv': choices})

    def run_check(self):
        manifest = {'diagnosticsVersion': 'MVS-BENCH-DIAGNOSTICS-1',
                    'replications': {'stability': 2}, 'stability': {'splits': 1, 'failed': 1},
                    'diagnosticsMissingReplications': sum(row['diagnostics_status'] == 'legacy_missing'
                        for row in self.tables['benchmark_replications.csv'])}
        (self.folder / 'benchmark_manifest.json').write_text(json.dumps(manifest))
        for filename, rows in self.tables.items():
            with (self.folder / filename).open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        return check.validate(self.folder)

    def test_failed_replications_remain_in_requested_denominator(self):
        result = self.run_check()
        self.assertEqual(result['status'], 'passed')
        rates = result['requested_denominator_rates']
        self.assertEqual(rates[0]['requested_rate'], .5)
        self.assertEqual(rates[0]['failed'], 1)
        self.assertEqual(rates[5]['requested_rate'], 0)

    def test_stability_failed_match_rejected(self):
        self.tables['benchmark_stability_replications.csv'][1]['matched'] = 'true'
        with self.assertRaisesRegex(ValueError, 'stability match counted'):
            self.run_check()

    def test_stability_wrong_match_rejected(self):
        self.tables['benchmark_stability_replications.csv'][0]['top_right'] = 'mean'
        with self.assertRaisesRegex(ValueError, 'Stability match mismatch'):
            self.run_check()

    def test_stability_lost_split_index_rejected(self):
        self.tables['benchmark_stability_replications.csv'][1]['split_index'] = '2'
        with self.assertRaisesRegex(ValueError, 'Missing stability indices'):
            self.run_check()

    def test_unavailable_metrics_do_not_shrink_family(self):
        for row in self.tables['benchmark_replication_metrics.csv'][1:12]:
            row['p_value'] = ''
            row['observed_available'] = 'false'
            row['rejected'] = 'false'
        self.tables['benchmark_replication_metrics.csv'][0]['p_value'] = '.01'
        with self.assertRaisesRegex(ValueError, 'Family decision mismatch'):
            self.run_check()

    def test_missing_legacy_metric_decision_rejected(self):
        self.tables['benchmark_replications.csv'][0]['diagnostics_status'] = 'legacy_missing'
        self.tables['benchmark_replication_metrics.csv'][0]['rejected'] = ''
        with self.assertRaisesRegex(ValueError, 'Missing completed metric decision'):
            self.run_check()

    def test_unknown_cannot_claim_retained(self):
        self.tables['benchmark_replications.csv'][0]['status'] = 'unknown_legacy'
        with self.assertRaisesRegex(ValueError, 'Unknown status with retained'):
            self.run_check()

    def test_extra_choice_row_rejected(self):
        self.tables['benchmark_choices.csv'].append(dict(condition='ghost', procedure='ghost', metric='median', count='999'))
        with self.assertRaisesRegex(ValueError, 'Unknown choice'):
            self.run_check()

    def test_failed_choice_rejected(self):
        self.tables['benchmark_replication_procedures.csv'][8]['chosen_metric'] = 'mean'
        with self.assertRaisesRegex(ValueError, 'Failed/unknown procedure'):
            self.run_check()

    def test_invalid_calibration_seed_rejected(self):
        self.tables['benchmark_replications.csv'][0]['calibration_seed'] = 'garbage'
        with self.assertRaises(ValueError):
            self.run_check()

    def test_missing_second_replay_rejected(self):
        for row in self.tables['benchmark_summary.csv']:
            row['stage'] = 'determinism'
        for filename in ('benchmark_replications.csv', 'benchmark_replication_procedures.csv', 'benchmark_replication_metrics.csv'):
            for row in self.tables[filename]:
                row['phase'] = 'replay-first'
        with self.assertRaisesRegex(ValueError, 'diagnostic phases'):
            self.run_check()

    def test_duplicate_replication_is_rejected(self):
        self.tables['benchmark_replications.csv'].append(self.tables['benchmark_replications.csv'][0].copy())
        with self.assertRaisesRegex(ValueError, 'Duplicate row'):
            self.run_check()

    def test_failed_partial_rejection_is_rejected(self):
        self.tables['benchmark_replication_procedures.csv'][8]['rejected'] = 'true'
        with self.assertRaisesRegex(ValueError, 'Failed/unknown procedure'):
            self.run_check()

    def test_metric_failure_not_made_zero_p(self):
        self.tables['benchmark_replication_metrics.csv'][12]['p_value'] = '0'
        with self.assertRaisesRegex(ValueError, 'p/availability'):
            self.run_check()

    def test_family_size_is_twelve(self):
        self.tables['benchmark_replication_metrics.csv'][0]['p_value'] = '.01'
        with self.assertRaisesRegex(ValueError, 'Family decision mismatch'):
            self.run_check()

    def test_legacy_missing_is_explicitly_incomplete(self):
        self.tables['benchmark_replications.csv'][0]['diagnostics_status'] = 'legacy_missing'
        for row in self.tables['benchmark_replication_metrics.csv'][:12]:
            for field in ('p_value', 'observed_available', 'calibration_applicable', 'calibration_score',
                          'gate_location', 'gate_variability', 'gate_heterogeneity'):
                row[field] = ''
        self.assertEqual(self.run_check()['status'], 'incomplete')

    def test_unknown_legacy_has_no_fabricated_rate(self):
        for row in self.tables['benchmark_replications.csv']:
            row['status'] = 'unknown_legacy'
            row['diagnostics_status'] = 'legacy_missing'
        for row in self.tables['benchmark_replication_procedures.csv']:
            row['claimed'] = row['rejected'] = row['chosen_metric'] = ''
        for row in self.tables['benchmark_replication_metrics.csv']:
            row['rejected'] = ''
        result = self.run_check()
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(all(row['requested_rate'] is None for row in result['requested_denominator_rates']))

    def test_summary_rejection_mismatch_rejected(self):
        self.tables['benchmark_summary.csv'][0]['rejections'] = '0'
        with self.assertRaisesRegex(ValueError, 'Summary mismatch'):
            self.run_check()

    def test_wrong_half_rejected(self):
        self.tables['benchmark_replications.csv'][1]['half'] = '0'
        with self.assertRaisesRegex(ValueError, 'Wrong oracle half'):
            self.run_check()

    def test_missing_procedure_rejected(self):
        self.tables['benchmark_replication_procedures.csv'].pop()
        with self.assertRaisesRegex(ValueError, 'row count mismatch'):
            self.run_check()

    def test_nonfinite_numeric_rejected(self):
        self.tables['benchmark_replication_metrics.csv'][0]['p_value'] = 'nan'
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            self.run_check()

    def test_invalid_boolean_rejected(self):
        self.tables['benchmark_replication_metrics.csv'][0]['observed_available'] = '1'
        with self.assertRaisesRegex(ValueError, 'Invalid boolean'):
            self.run_check()


if __name__ == '__main__':
    unittest.main()
