#!/usr/bin/env python3
"""Reconcile R1-07 CSVs; reports requested-denominator rates, never certifies science.

Exit 0: complete and consistent; 1: inconsistent; 2: legacy diagnostics incomplete.
Uses Python standard library, independently of the C# benchmark implementation.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path

PROCEDURES = ('cherry_pick', 'bonferroni', 'fixed_median', 'fixed_cv', 'mvs_pilot',
              'mvs_strict', 'mvs_lenient', 'mvs_registry_corrected')
METRICS = ('median', 'standard_deviation', 'coefficient_of_variation', 'mad', 'iqr',
           'normalized_mad', 'normalized_iqr', 'mean', 'rms', 'range',
           'geometric_mean', 'trimmed_mean_20')
KEY = ('condition', 'phase', 'replication_index')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def boolean(value, optional=False):
    if optional and value == '':
        return None
    require(value in ('true', 'false'), f'Invalid boolean: {value!r}')
    return value == 'true'


def number(value):
    if value == '':
        return None
    result = float(value)
    require(math.isfinite(result), f'Non-finite numeric cell: {value}')
    return result


def read_csv(folder, filename):
    with (Path(folder) / filename).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    require(reader.fieldnames is not None, f'Missing CSV header: {filename}')
    require(len(reader.fieldnames) == len(set(reader.fieldnames)), f'Duplicate header: {filename}')
    require(all(None not in row and None not in row.values() for row in rows),
            f'Malformed CSV row: {filename}')
    return rows


def index_rows(rows, keys):
    result = {}
    for row in rows:
        key = tuple(row[name] for name in keys)
        require(key not in result, f'Duplicate row: {key}')
        result[key] = row
    return result


def validate(folder):
    manifest = json.loads((Path(folder) / 'benchmark_manifest.json').read_text(encoding='utf-8-sig'))
    require(manifest.get('diagnosticsVersion') == 'MVS-BENCH-DIAGNOSTICS-1', 'Unknown diagnostics version')
    reps = index_rows(read_csv(folder, 'benchmark_replications.csv'), KEY)
    procedures = index_rows(read_csv(folder, 'benchmark_replication_procedures.csv'), KEY + ('procedure',))
    metrics = index_rows(read_csv(folder, 'benchmark_replication_metrics.csv'), KEY + ('metric',))
    summaries = index_rows(read_csv(folder, 'benchmark_summary.csv'), ('condition', 'procedure'))
    metric_summaries = index_rows(read_csv(folder, 'benchmark_metrics.csv'), ('condition', 'metric'))
    choices = index_rows(read_csv(folder, 'benchmark_choices.csv'), ('condition', 'procedure', 'metric'))
    require(bool(reps), 'No replication rows')
    require(len(procedures) == len(reps) * len(PROCEDURES), 'Procedure row count mismatch')
    require(len(metrics) == len(reps) * len(METRICS), 'Metric row count mismatch')
    incomplete = False
    groups = {}
    for key, row in reps.items():
        condition, phase, index = key
        require(phase in ('main', 'replay-first', 'replay-second'), f'Invalid phase: {key}')
        require(str(int(index)) == index and int(index) >= 0, f'Invalid replication index: {key}')
        require(row['half'] == str(int(index) % 2), f'Wrong oracle half: {key}')
        status = row['status']
        require(status in ('completed', 'failed', 'unknown_legacy'), f'Invalid status: {key}')
        require(row['diagnostics_status'] in ('retained', 'legacy_missing'), f'Invalid diagnostics status: {key}')
        require(status != 'unknown_legacy' or row['diagnostics_status'] == 'legacy_missing', f'Unknown status with retained diagnostics: {key}')
        incomplete |= status == 'unknown_legacy' or row['diagnostics_status'] == 'legacy_missing'
        if row['diagnostics_status'] == 'retained':
            for field in ('run_seed', 'seed_stage', 'seed_stream', 'derived_seed'):
                require(row[field] != '' and int(row[field]) >= 0, f'Missing/invalid seed {field}: {key}')
        calibration_seed = row['calibration_seed']
        if calibration_seed != '':
            require(str(int(calibration_seed)) == calibration_seed and 1 <= int(calibration_seed) <= 50000000,
                    f'Invalid calibration seed: {key}')
        if status == 'completed' and row['diagnostics_status'] == 'retained':
            require(calibration_seed != '', f'Missing calibration seed: {key}')
        groups.setdefault((condition, phase), []).append(key)
        raw = {}
        for metric in METRICS:
            item = metrics[key + (metric,)]
            p = number(item['p_value'])
            available = boolean(item['observed_available'], optional=True)
            reject = boolean(item['rejected'], optional=True)
            if p is not None:
                require(0 <= p <= 1 and available is True, f'Invalid p/availability: {key} {metric}')
            if available is True:
                require(p is not None, f'Available test without p: {key} {metric}')
            if status != 'completed':
                require(reject is None, f'Failed/unknown replication counted: {key} {metric}')
            else:
                require(reject is not None, f'Missing completed metric decision: {key} {metric}')
            if status == 'completed' and row['diagnostics_status'] == 'retained':
                require(available is not None, f'Missing observed status: {key} {metric}')
                require(reject == (p is not None and p < .05), f'Raw decision mismatch: {key} {metric}')
            number(item['calibration_score'])
            for field in ('calibration_applicable', 'gate_location', 'gate_variability', 'gate_heterogeneity'):
                boolean(item[field], optional=True)
            raw[metric] = p
        for procedure in PROCEDURES:
            item = procedures[key + (procedure,)]
            claim = boolean(item['claimed'], optional=True)
            reject = boolean(item['rejected'], optional=True)
            require(item['chosen_metric'] in ('', 'none') + METRICS, f'Unknown chosen metric: {key}')
            if status != 'completed':
                require(claim is None and reject is None and item['chosen_metric'] == '', f'Failed/unknown procedure counted: {key}')
            else:
                require(claim is not None and reject is not None, f'Missing completed decision: {key}')
                require(not reject or claim, f'Rejection without claim: {key}')
                if row['diagnostics_status'] == 'retained' and procedure in ('cherry_pick', 'bonferroni', 'mvs_registry_corrected'):
                    cutoff = .05 if procedure == 'cherry_pick' else .05 / 12
                    expected = any(p is not None and (min(1, 12 * p) < .05
                        if procedure == 'mvs_registry_corrected' else p < cutoff) for p in raw.values())
                    require(reject == expected, f'Family decision mismatch: {key} {procedure}')
                elif row['diagnostics_status'] == 'retained':
                    chosen_p = raw.get(item['chosen_metric'])
                    require(reject == (chosen_p is not None and chosen_p < .05),
                            f'Selected decision mismatch: {key} {procedure}')
    require(manifest.get('diagnosticsMissingReplications') ==
            sum(row['diagnostics_status'] == 'legacy_missing' for row in reps.values()),
            'Manifest missing-diagnostics count mismatch')
    stability = index_rows(read_csv(folder, 'benchmark_stability_replications.csv'), ('split_index',))
    require(sorted(int(key[0]) for key in stability) == list(range(len(stability))), 'Missing stability indices')
    require(len(stability) == manifest['replications']['stability'], 'Planned stability count mismatch')
    stability_known = True
    good_stability = []
    stability_failed = 0
    for key, row in stability.items():
        status = row['status']
        require(status in ('completed', 'failed', 'unknown_legacy'), f'Invalid stability status: {key}')
        require(row['diagnostics_status'] in ('retained', 'legacy_missing'), f'Invalid stability diagnostics: {key}')
        incomplete |= row['diagnostics_status'] == 'legacy_missing' or status == 'unknown_legacy'
        stability_known &= status != 'unknown_legacy'
        tau = number(row['kendall_tau'])
        matched = boolean(row['matched'], optional=True)
        require(tau is None or -1 <= tau <= 1, f'Invalid Kendall tau: {key}')
        for field in ('top_left', 'top_right'):
            require(row[field] in ('', 'none') + METRICS, f'Invalid stability metric: {key}')
        if status == 'completed':
            require(tau is not None and matched is not None, f'Missing completed stability values: {key}')
            if row['diagnostics_status'] == 'retained':
                require(matched == (row['top_left'] in METRICS and row['top_left'] == row['top_right']),
                        f'Stability match mismatch: {key}')
            good_stability.append((int(key[0]), tau, matched))
        else:
            require(matched is None, f'Failed/unknown stability match counted: {key}')
            stability_failed += status == 'failed'
    if stability_known:
        expected = manifest['stability']
        require((expected['splits'], expected['failed']) == (len(good_stability), stability_failed),
                'Stability manifest counts mismatch')
        legacy_tau = [number(row['kendall_tau']) for row in read_csv(folder, 'benchmark_stability.csv')]
        require(len(legacy_tau) == len(good_stability) and all(actual is not None and abs(actual - item[1]) <= .00000051
                for actual, item in zip(legacy_tau, sorted(good_stability))), 'Legacy stability tau mismatch')
    expected_groups = {}
    for (condition, procedure), summary in summaries.items():
        require(procedure in PROCEDURES, f'Unknown summary procedure: {procedure}')
        phases = ('replay-first', 'replay-second') if summary['stage'] == 'determinism' else ('main',)
        for phase in phases:
            group = condition, phase
            planned = int(summary['planned'])
            require(group not in expected_groups or expected_groups[group] == planned, 'Inconsistent planned counts')
            expected_groups[group] = planned
    require(set(groups) == set(expected_groups), 'Missing or unexpected diagnostic phases')
    require(all(len(groups[key]) == planned for key, planned in expected_groups.items()), 'Phase replication count mismatch')
    for condition, procedure, metric in choices:
        require((condition, procedure) in summaries and metric in METRICS + ('none',), 'Unknown choice summary row')
    rates = []
    seen_summaries = set()
    seen_metric_summaries = set()
    for (condition, phase), keys in groups.items():
        require(sorted(int(key[2]) for key in keys) == list(range(len(keys))),
                f'Missing replication indices: {condition}/{phase}')
        known = all(reps[key]['status'] != 'unknown_legacy' for key in keys)
        completed = [key for key in keys if reps[key]['status'] == 'completed']
        failed = sum(reps[key]['status'] == 'failed' for key in keys)
        for procedure in PROCEDURES:
            count = sum(procedures[key + (procedure,)]['rejected'] == 'true' for key in completed)
            claims = sum(procedures[key + (procedure,)]['claimed'] == 'true' for key in completed)
            rates.append(dict(condition=condition, phase=phase, procedure=procedure,
                              requested=len(keys), completed=len(completed) if known else None,
                              failed=failed if known else None, rejections=count if known else None,
                              requested_rate=count / len(keys) if known else None))
            if phase != 'replay-second':
                summary = summaries[(condition, procedure)]
                seen_summaries.add((condition, procedure))
                require(int(summary['planned']) == len(keys), f'Planned count mismatch: {condition}')
                if known:
                    require((int(summary['completed']), int(summary['failed']), int(summary['rejections'])) ==
                            (len(completed), failed, count), f'Summary mismatch: {condition}/{procedure}')
                    expected_rate = count / len(completed) if completed else None
                    actual_rate = number(summary['rate'])
                    require(actual_rate is None if expected_rate is None else
                            actual_rate is not None and abs(actual_rate - expected_rate) <= .00000051,
                            f'Conditional rate mismatch: {condition}/{procedure}')
                    actual_claim = number(summary['claim_rate'])
                    expected_claim = claims / len(completed) if completed else None
                    require(actual_claim is None if expected_claim is None else
                            actual_claim is not None and abs(actual_claim - expected_claim) <= .00000051,
                            f'Claim rate mismatch: {condition}/{procedure}')
                    for metric in METRICS + ('none',):
                        selected = sum((procedures[key + (procedure,)]['chosen_metric'] or 'none') == metric for key in completed)
                        choice = choices.get((condition, procedure, metric))
                        require((int(choice['count']) if choice else 0) == selected,
                                f'Choice count mismatch: {condition}/{procedure}/{metric}')
        if phase != 'replay-second':
            for metric in METRICS:
                summary = metric_summaries[(condition, metric)]
                seen_metric_summaries.add((condition, metric))
                if known:
                    count = sum(metrics[key + (metric,)]['rejected'] == 'true' for key in completed)
                    require((int(summary['completed']), int(summary['rejections'])) == (len(completed), count),
                            f'Metric summary mismatch: {condition}/{metric}')
    require(seen_summaries == set(summaries), 'Missing diagnostic conditions/procedures')
    require(seen_metric_summaries == set(metric_summaries), 'Missing diagnostic metric summaries')
    return {'status': 'incomplete' if incomplete else 'passed', 'replications': len(reps),
            'requested_denominator_rates': rates,
            'note': 'Counts and selected decisions reconciled, not every manifest/uncertainty field. Failures count as non-rejections; these rates do not establish error control or power.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.folder)
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}))
        return 1
    print(json.dumps(report, indent=2))
    return 2 if report['status'] == 'incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
