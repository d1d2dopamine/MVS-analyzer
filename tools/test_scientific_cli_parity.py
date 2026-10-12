#!/usr/bin/env python3
"""Opt-in real CLI/Python scientific interface audit; import/tests never run models.

Freeze creates new external inputs/protocol before executions. Reproduce retains
pre-fix evidence. Audit runs each frozen case once, serially, and retains failures.
Verify rechecks existing evidence without rerunning a model. This is same-engine
interface/export consistency, not independent scientific/model certification.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'validation/scientific-interface-parity-v1.json'
ABSOLUTE, RELATIVE = 1e-12, 1e-10
ARTIFACTS = {
    'variance': ['variance_report.json', 'variance_components.csv', 'variance_tests.csv', 'run_manifest.json'],
    'estimation': ['estimation_report.json', 'estimation_performance.csv', 'estimation_draws.csv', 'run_manifest.json'],
    'melsm': ['melsm_report.json', 'melsm_parameters.csv', 'melsm_random_effects.csv', 'run_manifest.json'],
}
TABLES = {'variance': [('variance_components.csv', 'Groups'), ('variance_tests.csv', 'Tracks')],
          'estimation': [('estimation_performance.csv', 'Performance'), ('estimation_draws.csv', 'Draws')],
          'melsm': [('melsm_parameters.csv', 'Parameters'), ('melsm_random_effects.csv', 'RandomEffects')]}
RANDOM_COLUMNS = ['Entity', 'Observations', 'LocationEffect', 'LogVarianceEffect']


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strict_json(text):
    def invalid(value):
        raise ValueError(f'Nonfinite JSON number: {value}')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    def finite(value):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else invalid(value)
    return json.loads(text, parse_constant=invalid, parse_float=finite, object_pairs_hook=pairs)


def read_json(path):
    return strict_json(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, document):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(document, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write('\n')


def compare_value(expected, actual, absolute=ABSOLUTE, relative=RELATIVE, location='$'):
    if type(expected) in (int, float) and type(actual) in (int, float):
        # Integer fields are counts/identity, never tolerance-based. JSON has no
        # declared float type, so an exactly equal integral float is harmless.
        if type(expected) is int and type(actual) is int:
            equal = expected == actual
        elif type(expected) is int or type(actual) is int:
            equal = expected == actual and math.isfinite(expected) and math.isfinite(actual)
        else:
            equal = math.isfinite(expected) and math.isfinite(actual) and math.isclose(expected, actual, abs_tol=absolute, rel_tol=relative)
        if not equal:
            raise AssertionError(f'{location}: scientific number differs: {expected!r} != {actual!r}')
    elif isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            raise AssertionError(f'{location}: field set differs')
        for key in expected:
            compare_value(expected[key], actual[key], absolute, relative, f'{location}.{key}')
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            raise AssertionError(f'{location}: array length differs')
        for index, (left, right) in enumerate(zip(expected, actual)):
            compare_value(left, right, absolute, relative, f'{location}[{index}]')
    elif type(expected) is not type(actual) or expected != actual:
        raise AssertionError(f'{location}: status/identity/null differs: {expected!r} != {actual!r}')


def scientific_manifest(manifest):
    return {key: value for key, value in manifest.items() if key not in {'created', 'runId', 'files'}}


def scalar_row(row):
    return {key: value for key, value in row.items() if not isinstance(value, (dict, list))}


def read_table(path, expected_rows, *, expected_columns=None):
    expected = [scalar_row(row) for row in expected_rows]
    columns = list(expected[0]) if expected else expected_columns
    if columns is None:
        raise ValueError('Header-only table requires explicit expected columns')
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != columns or len(set(columns)) != len(columns):
            raise AssertionError(f'{path}: scalar column names/order differ')
        raw_rows = list(reader)
    if len(raw_rows) != len(expected):
        raise AssertionError(f'{path}: CSV/report row count differs')
    converted = []
    for index, (row, reference) in enumerate(zip(raw_rows, expected)):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f'{path}: malformed CSV row')
        parsed = {}
        for key, value in row.items():
            target = reference[key]
            if target is None:
                if value != '':
                    raise AssertionError(f'{path}: unavailable {key} must be blank')
                parsed[key] = None
            elif type(target) is bool:
                if value not in ('True', 'False'):
                    raise ValueError(f'{path}: invalid boolean {value}')
                parsed[key] = value == 'True'
            elif type(target) is int:
                if str(int(value)) != value:
                    raise ValueError(f'{path}: invalid integer {value}')
                parsed[key] = int(value)
            elif type(target) is float:
                parsed[key] = float(value)
                if not math.isfinite(parsed[key]):
                    raise ValueError(f'{path}: nonfinite number {value}')
            else:
                # ScientificTables/Cli Table protect spreadsheet formula strings.
                parsed[key] = value[1:] if target and target[0] in '=+-@\t\r' and value == "'" + target else value
        compare_value(reference, parsed, location=f'{path}[{index}]')
        converted.append(parsed)
    return columns, converted


def verify_file(path, expected_size, expected_sha256):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise AssertionError(f'Missing/nonregular artifact: {path}')
    if path.stat().st_size != expected_size:
        raise AssertionError(f'Artifact size mismatch: {path}')
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or sha256(path) != expected_sha256.lower():
        raise AssertionError(f'Artifact checksum mismatch: {path}')


def compare_outputs(left, right, command):
    for name in [f'{command}_report.json', 'run_manifest.json']:
        first, second = read_json(Path(left) / name), read_json(Path(right) / name)
        if name == 'run_manifest.json':
            first, second = scientific_manifest(first), scientific_manifest(second)
        compare_value(first, second, location=name)
    first = read_json(Path(left) / f'{command}_report.json')
    second = read_json(Path(right) / f'{command}_report.json')
    for name, key in TABLES[command]:
        kwargs = {'expected_columns': RANDOM_COLUMNS} if key == 'RandomEffects' else {}
        fields_a, rows_a = read_table(Path(left) / name, first[key], **kwargs)
        fields_b, rows_b = read_table(Path(right) / name, second[key], **kwargs)
        compare_value(fields_a, fields_b, location=name + '.columns')
        compare_value(rows_a, rows_b, location=name)


def input_bytes():
    repeated = (ROOT / 'examples/repeated_conditions.csv').read_bytes()
    lines = repeated.splitlines(keepends=True)
    selected = {f'P{i:03}' for i in range(1, 9)}
    subset = lines[:1] + [line for line in lines[1:] if line.split(b',', 1)[0].decode() in selected]
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['entity', 'group', 'value', 'sequence', 'variable', 'unit'])
    for group in ('A', 'B'):
        for entity in range(1, 5):
            for repeat in range(1, 4):
                writer.writerow([f'{group}{entity:03}', group, 1, repeat, 'outcome', 'unit'])
    no_sequence = b''.join(b','.join(line.rstrip(b'\r\n').split(b',')[:3] + line.rstrip(b'\r\n').split(b',')[4:]) + b'\n' for line in subset)
    return {'variance_demo.csv': (ROOT / 'examples/variance_demo.csv').read_bytes(),
            'repeated_conditions.csv': repeated, 'repeated_conditions_8_subjects.csv': b''.join(subset),
            'repeated_conditions_no_sequence.csv': no_sequence, 'constant_variance.csv': output.getvalue().encode()}


def validate_protocol(protocol):
    if protocol['protocolId'] != 'MVS-SCIENTIFIC-INTERFACE-1' or protocol['scientificReleaseDecision'] != 'NO-GO retained':
        raise ValueError('Unexpected protocol identity/decision')
    if protocol['numericTolerance'] != {'absolute': ABSOLUTE, 'relative': RELATIVE}:
        raise ValueError('Unexpected numeric tolerance')
    if protocol['limits'] != {'cpus': 2, 'rssLimitMiB': 768, 'pollSeconds': 0.05, 'negativeTimeoutSeconds': 20}:
        raise ValueError('Unexpected execution limits')
    generated = input_bytes()
    for record in protocol['inputs']:
        data = generated[record['name']]
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Frozen input hash mismatch: ' + record['name'])
        rows = list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
        if len(rows) != record['rows'] or len({row['entity'] for row in rows}) != record['entities']:
            raise ValueError('Frozen input counts mismatch')


def check_scientific(report, command, case, input_path):
    compare_value('1.6.2', report['EngineVersion'])
    observations = list(csv.DictReader(input_path.open(encoding='utf-8', newline=''))) if input_path else []
    if command == 'variance':
        groups = list(dict.fromkeys(row['group'] for row in observations))
        compare_value(groups, [row['Group'] for row in report['Groups']])
        compare_value(['within', 'between'], [row['Track'] for row in report['Tracks']])
        compare_value(case['options']['seed'], report['Seed'])
        compare_value(case['options']['alpha'], report['Alpha'])
        for group in report['Groups']:
            data = [r for r in observations if r['group'] == group['Group']]
            compare_value(len(data), group['Measurements'])
            compare_value(len({r['entity'] for r in data}), group['Entities'])
            within, between = group['WithinVariance'], group['BetweenVariance']
            if within is not None and between is not None and within + between > 0:
                compare_value(between / (within + between), group['Icc'])
        for track in report['Tracks']:
            compare_value(case['options'][track['Track'] + '_effect'], track['EffectSdMultiplier'])
            compare_value(99, track['ReferenceReplications'] + track['ReferenceFailures'])
            compare_value(100, track['EvaluationReplications'])
            assert 0 <= track['NullFailures'] <= 100 and 0 <= track['AlternativeFailures'] <= 100
            compare_value(None if track['PValue'] is None else min(1, 2 * track['PValue']), track['AdjustedP'])
            compare_value(None, track['Mde'])
            assert len(track['EffectGrid']) == len(track['PowerCurve'])
            if case['id'] == 'variance-degenerate':
                compare_value('bootstrap_or_fit_failure', track['Status'])
                for key in ('Statistic', 'PValue', 'AdjustedP', 'Fpr', 'Power'):
                    compare_value(None, track[key])
                for key in ('ReferenceFailures',):
                    compare_value(99, track[key])
                for key in ('NullFailures', 'AlternativeFailures'):
                    compare_value(100, track[key])
                compare_value(0, track['ReferenceReplications'])
        if case['id'] == 'variance-degenerate':
            for group in report['Groups']:
                compare_value('not_converged_or_degenerate', group['Status'])
                for key in ('WithinVariance', 'BetweenVariance', 'Icc', 'WithinLow', 'WithinHigh', 'BetweenLow', 'BetweenHigh'):
                    compare_value(None, group[key])
        return {'entities': sum(g['Entities'] for g in report['Groups']), 'observations': sum(g['Measurements'] for g in report['Groups']),
                'groupStatuses': [g['Status'] for g in report['Groups']], 'trackStatuses': [t['Status'] for t in report['Tracks']],
                'referenceFailures': [t['ReferenceFailures'] for t in report['Tracks']], 'nullFailures': [t['NullFailures'] for t in report['Tracks']],
                'alternativeFailures': [t['AlternativeFailures'] for t in report['Tracks']], 'mde': [t['Mde'] for t in report['Tracks']]}
    if command == 'estimation':
        option_names = {'target': 'Target', 'shape': 'Shape', 'entities': 'Entities', 'measurements': 'Measurements',
                        'repetitions': 'Repetitions', 'bootstrap': 'BootstrapReplications', 'seed': 'Seed',
                        'location': 'Location', 'within_sd': 'WithinSd', 'between_sd': 'BetweenSd'}
        compare_value({option_names[k]: v for k, v in case['options'].items()}, report['Options'])
        compare_value(100, report['Truth'])
        methods = ['arithmetic_mean', 'trimmed_entity_mean_20', 'median_of_entity_medians']
        compare_value(methods, [row['Estimator'] for row in report['Performance']])
        compare_value(300, len(report['Draws']))
        compare_value([(rep, method) for rep in range(1, 101) for method in methods],
                      [(draw['Replication'], draw['Estimator']) for draw in report['Draws']])
        recomputed = []
        for performance in report['Performance']:
            all_draws = [d for d in report['Draws'] if d['Estimator'] == performance['Estimator']]
            valid = [d for d in all_draws if d['Estimate'] is not None]
            intervals = [d for d in valid if d['Low'] is not None and d['High'] is not None]
            errors = [d['Estimate'] - report['Truth'] for d in valid]
            squared = [e * e for e in errors]
            covered = sum(d['Low'] <= report['Truth'] <= d['High'] for d in intervals)
            sd = statistics.stdev([d['Estimate'] for d in valid]) if len(valid) > 1 else None
            mse = statistics.mean(squared) if squared else None
            coverage = covered / len(intervals) if intervals else None
            expected = {'Requested': 100, 'Completed': len(valid), 'Failures': 100 - len(valid),
                        'Bias': statistics.mean(errors) if errors else None,
                        'BiasMcse': sd / math.sqrt(len(valid)) if sd is not None else None,
                        'Mse': mse, 'MseMcse': statistics.stdev(squared) / math.sqrt(len(squared)) if len(squared) > 1 else None,
                        'Rmse': math.sqrt(mse) if mse is not None else None, 'EmpiricalSd': sd,
                        'IntervalsCompleted': len(intervals), 'Coverage': coverage,
                        'CoverageMcse': math.sqrt(coverage * (1 - coverage) / len(intervals)) if intervals else None,
                        'CoverageUnconditional': covered / 100,
                        'MeanIntervalWidth': statistics.mean([d['High'] - d['Low'] for d in intervals]) if intervals else None}
            for key, value in expected.items():
                compare_value(value, performance[key], location='recomputed.' + key)
            recomputed.append(expected)
        for index, performance in enumerate(report['Performance']):
            baseline, current = recomputed[0], recomputed[index]
            compare_value(baseline['Mse'] / current['Mse'], performance['RelativeMseEfficiency'])
            compare_value((baseline['EmpiricalSd'] / current['EmpiricalSd']) ** 2, performance['RelativeVarianceEfficiency'])
            compare_value(methods[0], performance['Reference'])
        return {'truth': report['Truth'], 'draws': len(report['Draws']), 'methods': methods,
                'completed': [p['Completed'] for p in report['Performance']], 'failures': [p['Failures'] for p in report['Performance']],
                'coverage': [p['Coverage'] for p in report['Performance']], 'independentDrawRecomputation': 'passed'}
    subjects = list(dict.fromkeys(r['entity'] for r in observations))
    groups = list(dict.fromkeys(r['group'] for r in observations))
    compare_value(len(subjects), report['Subjects'])
    compare_value(len(observations), report['Observations'])
    names = [name for group in groups for name in ('mean:' + group, 'residual_variance_at_v0:' + group)]
    names.append('between_entity_variance')
    options = report['Options']
    expected_options = {'MeanTime': bool(case['options'].get('mean_time')), 'ScaleTime': bool(case['options'].get('scale_time')),
                        'Correlate': bool(case['options'].get('correlate')), 'RandomScale': not case['options'].get('no_random_scale', False),
                        'QuadraturePoints': case['options']['quadrature'], 'MaxIterations': case['options']['max_iterations']}
    compare_value(expected_options, options)
    if options['RandomScale']:
        names.append('random_log_variance_sd')
    if options['Correlate']:
        names.append('location_scale_correlation')
    if options['MeanTime']:
        names.append('mean_time_slope')
    if options['ScaleTime']:
        names.append('log_variance_time_slope')
    compare_value(names, [p['Name'] for p in report['Parameters']])
    if report['RandomEffects']:
        compare_value(['P_' + hashlib.sha256(entity.encode()).hexdigest()[:12] for entity in subjects],
                      [row['Entity'] for row in report['RandomEffects']])
        compare_value([sum(r['entity'] == entity for r in observations) for entity in subjects],
                      [row['Observations'] for row in report['RandomEffects']])
    else:
        assert not report['Converged'] or report['QuadratureDifference'] is None or report['QuadratureDifference'] > .01
    return {'subjects': report['Subjects'], 'observations': report['Observations'], 'modelStatus': report['Status'],
            'converged': report['Converged'], 'iterations': report['Iterations'], 'quadraturePoints': report['QuadraturePoints'],
            'quadratureDifference': report['QuadratureDifference'], 'parameterNames': names, 'randomEffectRows': len(report['RandomEffects'])}


def check_operational(payload, returncode, out, command, case, input_path):
    assert payload['schemaVersion'] == 'mvs-cli-result/v1'
    compare_value(command, payload['command'])
    compare_value('1.6.2', payload['engineVersion'])
    compare_value('1.4.0', payload['applicationVersion'])
    compare_value(returncode, payload['exitCode'])
    compare_value({0: 'completed', 1: 'error', 2: 'diagnostic'}[returncode], payload['status'])
    if case.get('negative'):
        compare_value(1, returncode)
        compare_value(None, payload['outputDirectory'])
        compare_value(None, payload['manifestPath'])
        compare_value([], payload['artifacts'])
        assert isinstance(payload['error']['type'], str) and payload['error']['message']
        if case.get('sentinel'):
            compare_value(['sentinel.txt'], sorted(p.name for p in out.iterdir()))
            compare_value('preserve this exact sentinel\n', (out / 'sentinel.txt').read_text())
        else:
            assert not out.exists() or not list(out.iterdir())
        return {'errorType': payload['error']['type'], 'emptyOutputAllowed': True, 'sentinelPreserved': bool(case.get('sentinel'))}
    assert returncode in case['expectedExit']
    compare_value(str(out.resolve()), payload['outputDirectory'])
    compare_value(str((out / 'run_manifest.json').resolve()), payload['manifestPath'])
    compare_value(None, payload['error'])
    compare_value(sorted(ARTIFACTS[command]), sorted(p.name for p in out.iterdir()))
    artifacts = payload['artifacts']
    compare_value(sorted(ARTIFACTS[command]), sorted(item['name'] for item in artifacts))
    for item in artifacts:
        path = out / item['name']
        compare_value(str(path.resolve()), item['path'])
        verify_file(path, item['sizeBytes'], item['sha256'])
    manifest = read_json(out / 'run_manifest.json')
    compare_value(2, manifest['schemaVersion'])
    compare_value(payload['engineVersion'], manifest['engineVersion'])
    compare_value(payload['applicationVersion'], manifest['version'])
    compare_value(payload['runId'], manifest['runId'])
    datetime.fromisoformat(manifest['created'].replace('Z', '+00:00'))
    assert manifest['runId'].startswith(manifest['kind'] + '_')
    compare_value('model-specific', manifest['formula']['version'])
    compare_value('', manifest['formula']['hash'])
    # The summary-score machine identity is independently checked against version;
    # it is intentionally different from this model-specific manifest identity.
    compare_value(sorted(ARTIFACTS[command][:-1]), sorted(item['FileName'] for item in manifest['files']))
    for item in manifest['files']:
        verify_file(out / item['FileName'], item['SizeBytes'], item['sha256'])
    report = read_json(out / f'{command}_report.json')
    compare_value(report if command == 'variance' else report['Options'], manifest['configuration'])
    if input_path:
        compare_value(input_path.name, manifest['inputData']['file'])
        compare_value(sha256(input_path), manifest['inputData']['sha256'])
    else:
        compare_value('synthetic', manifest['inputData']['file'])
        # Configuration is serialized by ScientificJson (two-space indentation,
        # no trailing newline), and these frozen options need no special escapes.
        expected_hash = hashlib.sha256(json.dumps(manifest['configuration'], indent=2).encode()).hexdigest()
        compare_value(expected_hash, manifest['inputData']['sha256'])
    for name, key in TABLES[command]:
        read_table(out / name, report[key], **({'expected_columns': RANDOM_COLUMNS} if key == 'RandomEffects' else {}))
    result = check_scientific(report, command, case, input_path)
    result['artifactsVerified'] = len(artifacts)
    result['manifestFilesVerified'] = len(manifest['files'])
    return result


def python_worker(request_path):
    sys.path.insert(0, str(ROOT / 'python/src'))
    import mvs
    from mvs.engine import ScientificDiagnostic
    request = read_json(request_path)
    folder = Path(request_path).parent
    native_run = subprocess.run
    calls = []
    def traced_run(*args, **kwargs):
        completed = native_run(*args, **kwargs)
        index = len(calls)
        (folder / f'native-{index}-stdout.json').write_text(completed.stdout, encoding='utf-8')
        (folder / f'native-{index}-stderr.txt').write_text(completed.stderr, encoding='utf-8')
        calls.append({'argv': list(args[0]), 'returncode': completed.returncode, 'stdout': f'native-{index}-stdout.json', 'stderr': f'native-{index}-stderr.txt'})
        return completed
    subprocess.run = traced_run
    result = None
    exception = None
    try:
        engine = mvs.Engine(request['cli'])
        method = getattr(engine, request['case']['command'])
        kwargs = dict(request['case']['options'], output=request['output'])
        if request.get('strictDiagnostic'):
            kwargs['allow_diagnostic'] = False
        result = method(request['input'], **kwargs) if request['input'] else method(**kwargs)
    except Exception as exc:
        exception = {'type': type(exc).__name__, 'message': str(exc)}
        if isinstance(exc, ScientificDiagnostic):
            result = exc.result
    finally:
        subprocess.run = native_run
    description = {'exception': exception, 'calls': calls, 'resultType': type(result).__name__ if result is not None else None,
                   'resultRaw': dict(result.raw) if result is not None else None, 'typedArtifactAccessVerified': False}
    if result is not None:
        result.verify_artifacts()
        for artifact in result.artifacts:
            compare_value(artifact.path, result.artifact(artifact.name))
            if artifact.name.endswith('.json'):
                compare_value(read_json(artifact.path), result.read_json(artifact.name))
            else:
                compare_value(len(list(csv.DictReader(artifact.path.open(encoding='utf-8-sig', newline='')))), len(result.read_csv(artifact.name)))
        compare_value(read_json(result.manifest_path), dict(result.manifest.data))
        description['typedArtifactAccessVerified'] = True
    write_new(folder / 'python-result.json', description)
    print(json.dumps({'wrapperRecorded': True, 'exceptionType': exception['type'] if exception else None}))
    return 0


def process_tree_sample(pid, *, proc_root=Path('/proc'), affinity=None):
    """Read PPid links; task/PID/children is absent in some restricted sandboxes."""
    affinity = affinity or os.sched_getaffinity
    statuses = {}
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            statuses[int(entry.name)] = dict(line.split(':', 1) for line in (entry / 'status').read_text().splitlines() if ':' in line)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    result, pending, seen = [], [pid], set()
    while pending:
        current = pending.pop()
        if current in seen or current not in statuses:
            continue
        seen.add(current)
        status = statuses[current]
        pending.extend(child for child, values in statuses.items() if int(values.get('PPid', '-1')) == current)
        try:
            result.append({'pid': current, 'rssKiB': int(status.get('VmRSS', '0 kB').split()[0]),
                           'affinity': sorted(affinity(current)), 'name': status['Name'].strip()})
        except ProcessLookupError:
            continue
    return result


def execute(argv, folder, env, cpus, timeout, limits):
    started = time.monotonic()
    samples, violations = [], []
    with (folder / 'stdout.txt').open('wb') as stdout, (folder / 'stderr.txt').open('wb') as stderr:
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env, cwd=ROOT,
                                   start_new_session=True, preexec_fn=lambda: os.sched_setaffinity(0, set(cpus)))
        killed = False
        while True:
            waited, status, usage = os.wait4(process.pid, os.WNOHANG)
            elapsed = time.monotonic() - started
            if waited:
                process.returncode = os.waitstatus_to_exitcode(status)
                break
            tree = process_tree_sample(process.pid)
            samples.append({'elapsedSeconds': elapsed, 'processes': tree, 'treeRssKiB': sum(item['rssKiB'] for item in tree)})
            reason = None
            if elapsed >= timeout:
                reason = 'timeout'
            if any(item['affinity'] != cpus for item in tree):
                reason = 'affinity_changed'
            if samples[-1]['treeRssKiB'] > limits['rssLimitMiB'] * 1024:
                reason = 'sampled_tree_rss_watchdog'
            if reason and not killed:
                violations.append(reason)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                killed = True
            time.sleep(limits['pollSeconds'])
    resource = {'argv': argv, 'returncode': process.returncode, 'wallSeconds': elapsed, 'timeoutSeconds': timeout,
                'affinity': cpus, 'rssLimitMiB': limits['rssLimitMiB'], 'violations': violations,
                'sampledTreePeakRssKiB': max((sample['treeRssKiB'] for sample in samples if sample['processes']), default=None),
                'treeSamplingAvailable': any(sample['processes'] for sample in samples),
                'wait4MaxRssKiB': usage.ru_maxrss, 'wait4UserCpuSeconds': usage.ru_utime, 'wait4SystemCpuSeconds': usage.ru_stime,
                'memoryAccounting': 'sampledTreePeakRssKiB sums observed root/native descendants; sampling may miss short peaks. wait4MaxRssKiB is the kernel wait4 high-water statistic, not simultaneous tree RSS.',
                'samples': samples}
    write_new(folder / 'resource.json', resource)
    return resource


def load_frozen(raw):
    freeze = read_json(raw / 'freeze.json')
    verify_file(raw / 'protocol.json', freeze['protocolSizeBytes'], freeze['protocolSha256'])
    compare_value(freeze['harnessAtFreezeSha256'], sha256(raw / 'harness-at-freeze.py'))
    compare_value(freeze['engineBeforeSha256'], sha256(raw / 'engine-before.py'))
    compare_value(freeze['protocolSha256'], sha256(PROTOCOL))
    protocol = read_json(raw / 'protocol.json')
    validate_protocol(protocol)
    for item in protocol['inputs']:
        verify_file(raw / 'inputs' / item['name'], item['sizeBytes'], item['sha256'])
    verify_file(Path(freeze['cli']).with_name('MvsAnalyzer.Core.dll'), freeze['nativeCoreSizeBytes'], protocol['nativeCoreSha256'])
    return freeze, protocol


def freeze_run(raw, cli):
    if raw.exists():
        raise FileExistsError('Choose a fresh external raw directory; evidence is never overwritten')
    if raw.is_relative_to(ROOT):
        raise ValueError('Raw executions must be outside the source tree')
    protocol = read_json(PROTOCOL)
    validate_protocol(protocol)
    compare_value(protocol['nativeCoreSha256'], sha256(cli.with_name('MvsAnalyzer.Core.dll')))
    raw.mkdir(parents=True)
    (raw / 'inputs').mkdir()
    for name, content in input_bytes().items():
        (raw / 'inputs' / name).write_bytes(content)
    (raw / 'protocol.json').write_bytes(PROTOCOL.read_bytes())
    (raw / 'engine-before.py').write_bytes((ROOT / 'python/src/mvs/engine.py').read_bytes())
    (raw / 'harness-at-freeze.py').write_bytes(Path(__file__).read_bytes())
    cpus = sorted(os.sched_getaffinity(0))[:protocol['limits']['cpus']]
    selected = {'DOTNET_ROOT': '/tmp/mvs-dotnet', 'DOTNET_CLI_HOME': '/tmp/mvs-dotnet-home',
                'NUGET_PACKAGES': '/tmp/mvs-nuget/packages', 'DOTNET_PROCESSOR_COUNT': str(len(cpus)),
                'MVS_DISABLE_BACKUPS': '1', 'MVS_BACKUP_ROOT': str(raw / 'backups'),
                'XDG_CONFIG_HOME': str(raw / 'xdg/config'), 'XDG_DATA_HOME': str(raw / 'xdg/data'),
                'XDG_CACHE_HOME': str(raw / 'xdg/cache'), 'PYTHONDONTWRITEBYTECODE': '1'}
    removed = sorted(key for key in os.environ if key.startswith(('COMPlus_', 'DOTNET_', 'MVS_')) and key not in selected)
    record = {'frozenAt': utc_now(), 'cli': str(cli), 'protocolSha256': sha256(PROTOCOL), 'protocolSizeBytes': PROTOCOL.stat().st_size,
              'nativeCoreSizeBytes': cli.with_name('MvsAnalyzer.Core.dll').stat().st_size, 'nativeCoreSha256': protocol['nativeCoreSha256'],
              'engineBeforeSha256': sha256(raw / 'engine-before.py'), 'harnessAtFreezeSha256': sha256(Path(__file__)),
              'cpus': cpus, 'selectedEnvironment': selected, 'removedEnvironmentVariableNames': removed,
              'scope': 'Same native engine, bounded interface/export consistency only; no canonical scientific-validation or external-model-certification claim.'}
    write_new(raw / 'freeze.json', record)
    print(json.dumps(record, indent=2))


def launch_case(raw, freeze, protocol, case, interface, suffix='', strict=False):
    folder = raw / 'runs' / (case['id'] + '-' + interface + suffix)
    folder.mkdir(parents=True, exist_ok=False)
    out = folder / 'output'
    if case.get('sentinel'):
        out.mkdir()
        (out / 'sentinel.txt').write_text('preserve this exact sentinel\n')
    input_path = raw / 'inputs' / case['input'] if case.get('input') else None
    request = {'case': case, 'cli': freeze['cli'], 'input': str(input_path) if input_path else None, 'output': str(out), 'strictDiagnostic': strict}
    write_new(folder / 'request.json', request)
    if interface == 'cli':
        argv = [freeze['cli'], case['command']]
        if input_path:
            argv += ['--in', str(input_path)]
        argv += ['--out', str(out)]
        for key, value in case['options'].items():
            argv.append('--' + key.replace('_', '-'))
            if value is not True:
                argv.append(str(value))
        argv += ['--json', '--quiet']
    else:
        argv = [sys.executable, str(Path(__file__).resolve()), '--python-worker', str(folder / 'request.json')]
    env = {key: value for key, value in os.environ.items() if not key.startswith(('COMPlus_', 'DOTNET_', 'MVS_'))}
    env.update(freeze['selectedEnvironment'])
    resource = execute(argv, folder, env, freeze['cpus'], case['timeoutSeconds'], protocol['limits'])
    print(f"{folder.name}: process exit {resource['returncode']}, {resource['wallSeconds']:.3f}s", flush=True)
    return folder


def inspect_run(folder, freeze, *, pre_fix=False):
    request = read_json(folder / 'request.json')
    case, command = request['case'], request['case']['command']
    resource = read_json(folder / 'resource.json')
    assert not resource['violations'], resource['violations']
    python = '-python' in folder.name
    if python:
        compare_value(0, resource['returncode'])
        wrapper = read_json(folder / 'python-result.json')
        compare_value(2, len(wrapper['calls']))
        version = read_json(folder / wrapper['calls'][0]['stdout'])
        compare_value('version', version['command'])
        compare_value(0, wrapper['calls'][0]['returncode'])
        payload = read_json(folder / wrapper['calls'][1]['stdout'])
        returncode = wrapper['calls'][1]['returncode']
        if case.get('negative'):
            expected = 'EngineError' if pre_fix and case['id'] == 'variance-min-measurements' else 'InputError'
            compare_value(expected, wrapper['exception']['type'])
            compare_value(None, wrapper['resultType'])
        else:
            expected_type = {'variance': 'VarianceResult', 'estimation': 'EstimationResult', 'melsm': 'MelsmResult'}[command]
            compare_value(expected_type, wrapper['resultType'])
            compare_value(True, wrapper['typedArtifactAccessVerified'])
            compare_value(payload, wrapper['resultRaw'])
            compare_value('ScientificDiagnostic' if request['strictDiagnostic'] else None,
                          wrapper['exception']['type'] if wrapper['exception'] else None)
        for key in ('engineVersion', 'applicationVersion', 'formulaVersion', 'formulaHash'):
            compare_value(version[key], payload[key])
    else:
        payload = read_json(folder / 'stdout.txt')
        returncode = resource['returncode']
    details = check_operational(payload, returncode, Path(request['output']), command, case,
                                Path(request['input']) if request['input'] else None)
    details.update({'case': case['id'], 'interface': 'python' if python else 'cli', 'status': payload['status'], 'exitCode': payload['exitCode'],
                    'wallSeconds': resource['wallSeconds'], 'sampledTreePeakRssKiB': resource['sampledTreePeakRssKiB'] if any(s['processes'] for s in resource['samples']) else None,
                    'treeSamplingAvailable': any(s['processes'] for s in resource['samples']),
                    'wait4MaxRssKiB': resource['wait4MaxRssKiB'], 'path': str(folder),
                    'payloadSha256': sha256(folder / (wrapper['calls'][1]['stdout'] if python else 'stdout.txt'))})
    if python:
        details.update({'wrapperException': wrapper['exception']['type'] if wrapper['exception'] else None, 'resultType': wrapper['resultType'],
                        'typedArtifactAccessVerified': wrapper['typedArtifactAccessVerified']})
    return details, payload


def reproduce(raw):
    freeze, protocol = load_frozen(raw)
    compare_value(freeze['engineBeforeSha256'], sha256(ROOT / 'python/src/mvs/engine.py'))
    case = next(case for case in protocol['negativeCases'] if case['id'] == 'variance-min-measurements')
    records = []
    for interface in ('cli', 'python'):
        folder = launch_case(raw, freeze, protocol, case, interface, '-pre-fix')
        details, payload = inspect_run(folder, freeze, pre_fix=True)
        compare_value('ArgumentOutOfRangeException', payload['error']['type'])
        records.append(details)
    write_new(raw / 'pre-fix.json', {'reproducedAt': utc_now(), 'engineSha256': freeze['engineBeforeSha256'],
                                   'finding': 'Actual CLI ArgumentOutOfRangeException is classified EngineError by the original Python wrapper; InputError is the documented input-error contract.', 'runs': records})
    print('Confirmed pre-fix ArgumentOutOfRangeException -> EngineError; evidence retained.', flush=True)


def assess(raw, freeze, protocol):
    records, pairs, failures = [], [], []
    for case in protocol['scientificCases'] + protocol['negativeCases']:
        payloads = {}
        for interface in ('cli', 'python'):
            folder = raw / 'runs' / (case['id'] + '-' + interface)
            try:
                details, payload = inspect_run(folder, freeze)
                records.append(details)
                payloads[interface] = payload
            except Exception as exc:
                failures.append({'path': str(folder), 'error': type(exc).__name__ + ': ' + str(exc)})
        try:
            if len(payloads) != 2:
                raise AssertionError('Both interfaces must pass structural validation before parity')
            first, second = payloads['cli'], payloads['python']
            operational = {'outputDirectory', 'manifestPath', 'runId', 'artifacts'}
            # Native error messages include the deliberately different output path.
            if case.get('sentinel'):
                first = dict(first, error=dict(first['error']))
                second = dict(second, error=dict(second['error']))
                for payload, interface in ((first, 'cli'), (second, 'python')):
                    out = str(raw / 'runs' / (case['id'] + '-' + interface) / 'output')
                    payload['error']['message'] = payload['error']['message'].replace(out, '<own-output>')
            compare_value({k: v for k, v in first.items() if k not in operational},
                          {k: v for k, v in second.items() if k not in operational}, location=case['id'] + '.machine')
            if not case.get('negative'):
                compare_outputs(raw / 'runs' / (case['id'] + '-cli') / 'output',
                                raw / 'runs' / (case['id'] + '-python') / 'output', case['command'])
            pairs.append({'case': case['id'], 'passed': True, 'negative': bool(case.get('negative'))})
        except Exception as exc:
            failures.append({'case': case['id'], 'error': type(exc).__name__ + ': ' + str(exc)})
            pairs.append({'case': case['id'], 'passed': False, 'negative': bool(case.get('negative'))})
    strict_folder = raw / 'runs/variance-degenerate-python-strict'
    try:
        details, payload = inspect_run(strict_folder, freeze)
        compare_outputs(raw / 'runs/variance-degenerate-cli/output', strict_folder / 'output', 'variance')
        records.append(details)
    except Exception as exc:
        failures.append({'path': str(strict_folder), 'error': type(exc).__name__ + ': ' + str(exc)})
    return {'protocolId': protocol['protocolId'], 'evaluatedAt': utc_now(), 'protocolSha256': freeze['protocolSha256'],
            'frozenAt': freeze['frozenAt'], 'rawDirectory': str(raw), 'status': 'passed' if not failures else 'failed',
            'scientificReleaseDecision': 'NO-GO retained', 'nativeCoreSha256': freeze['nativeCoreSha256'],
            'wrapperBeforeSha256': freeze['engineBeforeSha256'], 'wrapperAfterSha256': sha256(ROOT / 'python/src/mvs/engine.py'),
            'harnessSha256': sha256(Path(__file__)), 'preFix': read_json(raw / 'pre-fix.json'),
            'pairs': pairs, 'runs': records, 'failures': failures,
            'counts': {'plannedPairs': len(protocol['scientificCases']) + len(protocol['negativeCases']), 'passedPairs': sum(p['passed'] for p in pairs),
                       'scientificPairs': len(protocol['scientificCases']), 'negativePairs': len(protocol['negativeCases']), 'validatedPostFixRuns': len(records),
                       'preFixRuns': 2, 'strictDiagnosticRuns': 1,
                       'actualWorkloadInvocations': len(list((raw / 'runs').glob('*/resource.json'))),
                       'pythonVersionHandshakes': len(list((raw / 'runs').glob('*/python-result.json'))),
                       'totalNativeInvocations': len(list((raw / 'runs').glob('*/resource.json'))) + len(list((raw / 'runs').glob('*/python-result.json'))),
                       'verifiedOutputArtifacts': sum(r.get('artifactsVerified', 0) for r in records)},
            'limits': protocol['limits'], 'affinity': freeze['cpus'],
            'resourceMonitoringStatus': 'sampled' if all(r.get('treeSamplingAvailable') for r in records) else 'incomplete_tree_observation',
            'resourceMonitoringNote': 'CPU affinity was set before launch and per-case timeout controls ran. Original round-18 samples were empty because this sandbox lacks task/PID/children; tree RSS/observed affinity are unavailable. Kernel wait4 RSS is retained and is not simultaneous tree RSS. The final harness uses PPid traversal, tested separately without models. Successful cases were not rerun.',
            'limitations': protocol['limitations'] + (['Original actual runs have no usable process-tree RSS samples; the 768 MiB sampled-tree watchdog therefore was not verified/enforced from observations. Do not interpret zero raw samples as zero memory use.'] if any(not r.get('treeSamplingAvailable') for r in records) else [])}


def archive(raw, summary_path, zip_path, result):
    write_new(summary_path, result)
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive_file:
        archive_file.write(summary_path, 'scientific-interface-parity-round18.json')
        archive_file.write(PROTOCOL, 'scientific-interface-parity-v1.json')
        for path in sorted(raw.rglob('*')):
            if path.is_file():
                if path.suffix.lower() in {'.dll', '.exe', '.so', '.pdb', '.pyc'}:
                    raise ValueError('Binary/cache must not enter evidence archive: ' + str(path))
                archive_file.write(path, 'raw/' + str(path.relative_to(raw)))
    with zipfile.ZipFile(zip_path) as archive_file:
        assert archive_file.testzip() is None
    print(json.dumps({'summary': str(summary_path), 'summarySha256': sha256(summary_path), 'zip': str(zip_path), 'zipSha256': sha256(zip_path),
                      'status': result['status'], 'counts': result['counts'], 'failures': result['failures']}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', nargs='?', choices=['freeze', 'reproduce', 'audit', 'verify'])
    parser.add_argument('--raw', type=Path)
    parser.add_argument('--cli', type=Path)
    parser.add_argument('--summary', type=Path)
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--python-worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.python_worker:
        return python_worker(args.python_worker)
    if not args.raw or not args.phase:
        parser.error('phase and --raw are required')
    raw = args.raw.resolve()
    if args.phase == 'freeze':
        if not args.cli:
            parser.error('--cli is required for freeze')
        freeze_run(raw, args.cli.resolve())
        return 0
    if args.phase == 'reproduce':
        reproduce(raw)
        return 0
    freeze, protocol = load_frozen(raw)
    if args.phase == 'audit':
        # All intended runs are attempted once; failures remain inspectable.
        for case in protocol['scientificCases'] + protocol['negativeCases']:
            for interface in ('cli', 'python'):
                launch_case(raw, freeze, protocol, case, interface)
            if case['id'] == 'variance-degenerate':
                launch_case(raw, freeze, protocol, case, 'python', '-strict', strict=True)
    result = assess(raw, freeze, protocol)
    if args.summary or args.zip:
        if not args.summary or not args.zip:
            parser.error('Both --summary and --zip are required to archive')
        archive(raw, args.summary, args.zip, result)
    else:
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
