#!/usr/bin/env python3
"""Write-once, bounded test-only replay. No native execution in prepare/verify/report.

prepare --root REPO --out NEW_DIR --protocol JSON --native-dir BUILD --command dotnet HARNESS.dll
verify --out DIR
run --out DIR       (only after independent review)
report --out DIR

All historical cases are requested exactly once; no retry, seed search, or selected
splits. A successful comparison means same-recipe replay matching retained
 diagnostics, never recovery of original score vectors or byte identity.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import statistics
import struct
import subprocess
import sys
import threading
import time

COUNT = 120
WORKERS = 8
WALL_SECONDS = 900
MEMORY_BYTES = 4 * 1024**3
HISTORY = 'benchmark_history/1.4.0-engine-1.6.2-MVS-BENCH-1.2.0/benchmark_stability_replications.csv'
PROTOCOL_SHA = 'bb94422017c04e6b9229dd7cd0165ef751446cd957de437823f12b0dd13b938d'
HISTORY_SHA = 'f43adc15a64f22386a47684644c1f523d359cb00efa2ceb956564b08cb55621f'
LIMITATIONS = [
    'No original score vectors were retained: these are reconstructed same-recipe vectors, not recovered original scores or proof of byte identity.',
    'Development-only diagnostic replay; scientific NO-GO remains unchanged.',
    'Top-one agreement uses the existing finite-tau denominator and can change solely because that denominator changes.',
    'No retries, replacement seeds, selected splits, or new scientific validation datasets.',
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    def pairs(items):
        d = {}
        for k, v in items:
            require(k not in d, 'duplicate JSON key: ' + k)
            d[k] = v
        return d
    def invalid(value):
        raise ValueError('nonfinite JSON: ' + value)
    value = json.loads(Path(path).read_text(), parse_constant=invalid, object_pairs_hook=pairs)
    def finite(x):
        if isinstance(x, float):
            require(math.isfinite(x), 'nonfinite JSON number')
        elif isinstance(x, dict):
            for v in x.values(): finite(v)
        elif isinstance(x, list):
            for v in x: finite(v)
    finite(value)
    return value


def write_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def source_paths(root):
    return sorted(p.resolve() for p in root.rglob('*') if p.is_file()
                  and p.suffix in {'.cs', '.csproj', '.py', '.props', '.targets'}
                  and not {'bin', 'obj', '.git', '__pycache__'}.intersection(p.relative_to(root).parts))


def pin_paths(paths):
    return {str(p): digest(p) for p in sorted(set(paths))}


def read_history(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    require(len(rows) == COUNT, 'history must contain exactly 120 rows')
    require([int(r['split_index']) for r in rows] == list(range(COUNT)), 'history indices must be ordered 0..119')
    for r in rows:
        require(math.isfinite(float(r['kendall_tau'])), 'nonfinite historical tau')
        require(r['matched'] in ('true', 'false'), 'invalid historical matched')
    return rows


def prepare(root, out, protocol, native_dir, command):
    root, out, protocol, native_dir = map(lambda p: Path(p).resolve(), (root, out, protocol, native_dir))
    require(not out.exists(), 'output root already exists; never overwrite or resume')
    require(sys.platform == 'linux' and Path('/proc/self/status').exists(), 'Linux process groups and /proc required')
    history = root / HISTORY
    require(digest(history) == HISTORY_SHA, 'historical evidence hash mismatch')
    read_history(history)
    require(digest(protocol) == PROTOCOL_SHA, 'frozen protocol hash mismatch')
    plan = read_json(protocol)
    history_files = [root / p for p in plan['historicalInputs']]
    for p, expected in plan['historicalInputs'].items():
        require(digest(root / p) == expected, 'historical input hash mismatch: ' + p)
    require(command and native_dir.is_dir(), 'native command/build directory required')
    exe = shutil.which(command[0])
    require(exe is not None, 'native executable not found')
    command = [str(Path(exe).resolve()), *command[1:]]
    for i, arg in enumerate(command[1:], 1):
        if Path(arg).is_file(): command[i] = str(Path(arg).resolve())
    require(len(command) == 2 and Path(command[1]).suffix == '.dll', 'command must be absolute dotnet and harness DLL only')
    runtime_dir = Path(command[0]).parent / 'shared/Microsoft.NETCore.App/8.0.31'
    fxr_dir = Path(command[0]).parent / 'host/fxr/8.0.31'
    require(runtime_dir.is_dir() and fxr_dir.is_dir(), 'pinned .NET 8.0.31 runtime required')
    runtime_files = sorted(p.resolve() for d in (runtime_dir, fxr_dir) for p in d.rglob('*') if p.is_file())
    native = sorted(p.resolve() for p in native_dir.rglob('*') if p.is_file())
    require(native, 'empty native build directory')
    require(Path(command[1]) in native, 'harness DLL must be pinned inside native directory')
    sources = source_paths(root)
    pins = pin_paths(sources + native + runtime_files + history_files + [protocol, history, Path(command[0])])
    manifest = {'schema': 'mvs-stability-replay-bind/v1', 'root': str(root), 'history': str(history),
                'protocol': str(protocol), 'native_dir': str(native_dir), 'command': command,
                'runtime_files': [str(p) for p in runtime_files],
                'sources': [str(p) for p in sources], 'native_files': [str(p) for p in native],
                'pins': pins, 'indices': list(range(COUNT)), 'workers': WORKERS,
                'wall_seconds': WALL_SECONDS, 'memory_bytes': MEMORY_BYTES,
                'limitations': LIMITATIONS}
    out.mkdir(parents=True)
    write_json(out / 'bind.json', manifest)
    (out / 'bind.sha256').write_text(digest(out / 'bind.json') + '\n')
    return manifest


def verify(out):
    out = Path(out)
    require(digest(out / 'bind.json') == (out / 'bind.sha256').read_text().strip(), 'bind manifest altered')
    m = read_json(out / 'bind.json')
    require(m['indices'] == list(range(COUNT)), 'indices altered')
    require((m['workers'], m['wall_seconds'], m['memory_bytes']) == (WORKERS, WALL_SECONDS, MEMORY_BYTES), 'resource contract altered')
    require(m['pins'][m['protocol']] == PROTOCOL_SHA, 'protocol pin altered')
    require(m['pins'][m['history']] == HISTORY_SHA, 'historical pin altered')
    require([str(p) for p in source_paths(Path(m['root']))] == m['sources'], 'source file set changed')
    require(sorted(str(p.resolve()) for p in Path(m['native_dir']).rglob('*') if p.is_file()) == m['native_files'], 'native file set changed')
    for path, expected in m['pins'].items():
        require(digest(path) == expected, 'pinned hash changed: ' + path)
    return m


def kill_group(proc):
    try: os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError: pass


def group_rss(pids):
    """Resident bytes for all processes in the launched process groups."""
    total = 0
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            stat = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(stat[2]) in pids:
                total += int(stat[21]) * os.sysconf('SC_PAGE_SIZE')
        except (FileNotFoundError, ProcessLookupError):
            pass
    return total


def execute_cases(out, command, indices, wall_seconds, workers, memory_bytes):
    """Private test seam; public run always uses the immutable full 120-case plan."""
    out = Path(out)
    start = time.monotonic()
    deadline = start + wall_seconds
    lock, stopped, finished = threading.Lock(), threading.Event(), threading.Event()
    live, reasons, attempts = {}, [], []
    peak = 0
    cleanup_deadline = None
    def stop(reason):
        nonlocal cleanup_deadline
        # Do not depend on a worker lock or successful disk writes to stop children.
        first = cleanup_deadline is None
        if first: cleanup_deadline = min(deadline, time.monotonic()) + 10
        stopped.set()
        if reason not in reasons: reasons.append(reason)
        for proc in list(live.copy().values()): kill_group(proc)
        if first:
            try: write_json(out / 'watchdog-stop.json', {'reason': reason, 'cleanup_deadline_monotonic': cleanup_deadline})
            except OSError: pass
    def watch():
        nonlocal peak
        while not finished.wait(0.05):
            try:
                if cleanup_deadline is not None and time.monotonic() >= cleanup_deadline:
                    # Last-resort bounded abort: preserve started logs and native sidecars.
                    try:
                        for proc in list(live.copy().values()): kill_group(proc)
                        write_json(out / 'cleanup-abort.json', {'reason': 'cleanup exceeded 10 seconds', 'active_pids': list(live)})
                    finally:
                        os._exit(124)
                if time.monotonic() >= deadline: stop('whole-run wall timeout')
                rss = group_rss(set(live.copy()))
                peak = max(peak, rss)
                if rss > memory_bytes: stop('aggregate process-group RSS limit exceeded')
            except Exception as exc:
                stop('resource watchdog failure: ' + repr(exc))
    def one(index):
        directory = out / ('case-%03d' % index)
        directory.mkdir()
        begun = time.monotonic()
        record = {'index': index, 'started': False, 'elapsed_seconds': 0, 'returncode': None}
        proc = None
        try:
            with (directory / 'stdout.log').open('xb') as stdout, (directory / 'stderr.log').open('xb') as stderr:
                with lock:
                    if stopped.is_set() or time.monotonic() >= deadline:
                        record['error'] = 'not started: budget exhausted'
                    else:
                        argv = [*command, '--case', str(index), '--out', str(directory / 'native.json')]
                        env = dict(os.environ, DOTNET_PROCESSOR_COUNT='1', DOTNET_GCHeapHardLimit='0x18000000', MVS_DISABLE_BACKUPS='1', DOTNET_ROLL_FORWARD='Disable', DOTNET_ROOT=str(Path(command[0]).parent))
                        write_json(directory / 'started.json', {'index': index, 'argv': argv, 'monotonic_seconds': begun, 'environment': {k: env[k] for k in ('DOTNET_PROCESSOR_COUNT', 'DOTNET_GCHeapHardLimit', 'MVS_DISABLE_BACKUPS', 'DOTNET_ROLL_FORWARD', 'DOTNET_ROOT')}})
                        if stopped.is_set() or time.monotonic() >= deadline:
                            record['error'] = 'not started: budget exhausted before spawn'
                        else:
                            proc = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
                            live[proc.pid] = proc
                            record['started'] = True
                            record['pid'] = proc.pid
                            if stopped.is_set() or time.monotonic() >= deadline: kill_group(proc)
                if proc:
                    record['returncode'] = proc.wait()  # blocking wait; watchdog owns all deadlines
                    if record['returncode'] != 0: record['error'] = 'native failure'
        except Exception as exc:
            record['error'] = repr(exc)
        finally:
            if proc:
                kill_group(proc)
                try: proc.wait(timeout=max(.001, (cleanup_deadline or deadline + 10) - time.monotonic()))
                except subprocess.TimeoutExpired: stop('process cleanup failed')
                with lock: live.pop(proc.pid, None)
            record['elapsed_seconds'] = time.monotonic() - begun
            record['files'] = pin_paths(p for p in directory.iterdir() if p.is_file())
            write_json(directory / 'attempt.json', record)
            with lock: attempts.append(record)
    watchdog = threading.Thread(target=watch, daemon=True)
    watchdog.start()
    handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, lambda signum, frame: stop('driver signal ' + str(signum)))
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, indices))
    finally:
        finished.set()
        watchdog.join(timeout=5)
        for sig, handler in handlers.items(): signal.signal(sig, handler)
        with lock:
            for proc in live.values(): kill_group(proc)
    return {'attempts': sorted(attempts, key=lambda a: a['index']), 'stop_reasons': reasons,
            'elapsed_seconds': time.monotonic() - start,
            'scientific_elapsed_seconds': min(time.monotonic() - start, wall_seconds),
            'post_deadline_cleanup_seconds': max(0, time.monotonic() - deadline),
            'peak_aggregate_rss_bytes': peak}


def run(out):
    out = Path(out).resolve()
    m = verify(out)
    write_json(out / 'run-started.json', {'bind_sha256': digest(out / 'bind.json'), 'unix_seconds': time.time()})
    result = execute_cases(out, m['command'], m['indices'], m['wall_seconds'], m['workers'], m['memory_bytes'])
    try:
        verify(out)
        result['end_hash_verification'] = 'passed'
    except Exception as exc:
        result['end_hash_verification'] = 'failed'
        result['hash_error'] = str(exc)
    result['bind_sha256'] = digest(out / 'bind.json')
    write_json(out / 'run-finished.json', result)
    return result


def bits(value):
    require(type(value) in (int, float) and math.isfinite(value), 'tau must be finite number')
    return struct.pack('>d', float(value))


def quantile(values, q):
    values = sorted(values)
    if not values: return None
    pos = q * (len(values) - 1)
    lo = math.floor(pos)
    hi = min(len(values) - 1, lo + 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def compare(rows, cases):
    errors, seen, corrected = [], set(), []
    paired = [{'index': i, 'legacy_tau': float(r['kendall_tau']), 'corrected_tau': None,
               'status': 'missing', 'comparison_errors': []} for i, r in enumerate(rows)]
    for case in cases:
        index = case.get('index')
        if type(index) is not int or index not in range(COUNT):
            errors.append('invalid case index'); continue
        if index in seen:
            errors.append('duplicate index %s' % index); continue
        seen.add(index)
        pair, row = paired[index], rows[index]
        pair['status'] = case.get('status')
        pair['legacy_replay'] = case.get('legacy')
        pair['corrected_replay'] = case.get('corrected')
        try:
            for key in ('status', 'diagnostics_status', 'error'):
                require(case[key] == row[key], '%s mismatch' % key)
            old = case['legacy']
            require(bits(old['kendall_tau']) == bits(float(row['kendall_tau'])), 'legacy binary64 tau mismatch')
            for key in ('top_left', 'top_right'):
                require(old[key] == row[key], 'legacy %s mismatch' % key)
            require(type(old['matched']) is bool and old['matched'] == (row['matched'] == 'true'), 'legacy matched mismatch')
            require(old['defined'] is True, 'legacy defined mismatch')
        except (ValueError, KeyError, TypeError) as exc:
            pair['comparison_errors'].append('legacy: ' + str(exc))
        # Summarize every valid corrected diagnostic, even if its legacy gate fails.
        try:
            require(case['status'] == 'completed' and case['diagnostics_status'] == 'retained' and case['error'] == '', 'execution/diagnostics failed')
            new = case['corrected']
            require(type(new['defined']) is bool and type(new['matched']) is bool, 'invalid corrected flags')
            require(new['matched'] == (new['top_left'] == new['top_right']), 'corrected matched inconsistent with winners')
            for key in ('top_left', 'top_right', 'matched'):
                require(new[key] == case['legacy'][key], 'corrected/legacy winner disagreement')
            if new['defined']:
                bits(new['kendall_tau'])
                require(-1 <= new['kendall_tau'] <= 1, 'corrected tau outside [-1,1]')
            else:
                require(new['kendall_tau'] is None and bool(new['undefined_reason']), 'undefined corrected tau needs null and reason')
            corrected.append(new)
            pair['corrected_tau'] = new['kendall_tau']
            pair['undefined_reason'] = new.get('undefined_reason')
        except (ValueError, KeyError, TypeError) as exc:
            pair['comparison_errors'].append('corrected: ' + str(exc))
        errors.extend('index %s: %s' % (index, e) for e in pair['comparison_errors'])
    missing = sorted(set(range(COUNT)) - seen)
    if missing: errors.append('missing indices: ' + str(missing))
    oldtaus = [float(r['kendall_tau']) for r in rows]
    finite = [c for c in corrected if c['defined']]
    matched = sum(c['matched'] for c in finite)
    return {'comparison_errors': errors, 'all_120_legacy_diagnostics_exact': not errors,
            'paired_cases': paired, 'original_requested': COUNT, 'original_legacy_usable': len(oldtaus),
            'original_execution_failed': 0, 'replay_missing_count': len(missing),
            'replay_execution_or_diagnostics_failed_count': COUNT - len(corrected),
            'original_matched': sum(r['matched'] == 'true' for r in rows),
            'original_tau_summary': {'median': statistics.median(oldtaus), 'lower_quartile': quantile(oldtaus, .25), 'min': min(oldtaus), 'max': max(oldtaus)},
            'original_top_one_agreement': sum(r['matched'] == 'true' for r in rows) / len(oldtaus),
            'replay_diagnostic_cases': len(corrected), 'corrected_finite_count': len(finite),
            'corrected_undefined_count': sum(not c['defined'] for c in corrected),
            'corrected_median_tau': statistics.median(c['kendall_tau'] for c in finite) if finite else None,
            'corrected_lower_quartile_tau': quantile([c['kendall_tau'] for c in finite], .25),
            'corrected_matched_finite_count': matched,
            'corrected_top_one_agreement': matched / len(finite) if finite else None,
            'corrected_matched_over_requested': matched / COUNT,
            'top_one_denominator': 'finite corrected tau cases only; can differ from original 120',
            'limitations': LIMITATIONS}


def validate_native(case, manifest):
    require(case['schema'] == 'mvs-stability-replay-case/v1', 'wrong native schema')
    metrics = ['median', 'standard_deviation', 'coefficient_of_variation', 'mad', 'iqr', 'normalized_mad', 'normalized_iqr', 'mean', 'rms', 'range', 'geometric_mean', 'trimmed_mean_20']
    require(case['metric_order'] == metrics, 'metric order mismatch')
    expected = dict(run_seed=20260904, stage=5, stream=1, index_min=0, index_max=119, injection='None', generation_effect=1, contamination=0, min_value=-1000000, max_value=1000000, min_measurements=6, repetitions=1000, effect=1.15, scenario='location', outlier_rate=.02, missing_rate=0, alpha=.05, tracks=['location', 'variability', 'heterogeneity'])
    for key, value in expected.items(): require(case['settings'][key] == value, 'native setting mismatch: ' + key)
    design = dict(id='gait_stride_like', entities_per_group=16, measurements_per_entity=40, base_level=1.10, between_sd=.08, within_cv=.025, cv_heterogeneity=.25, shape=1, variable='stride_interval', unit='s')
    for key, value in design.items(): require(case['settings']['design'][key] == value, 'native design mismatch: ' + key)
    import replay_primary_rank_draws as rng
    seeds = case['seeds']
    require(seeds['run_seed'] == 20260904 and seeds['derived_seed'] == rng.derive(20260904, 5, 1, case['index']), 'derived/run seed mismatch')
    for key in ('split_seed', 'calibration_left_seed', 'calibration_right_seed'):
        require(type(seeds[key]) is int and 1 <= seeds[key] <= 50000000, 'invalid consumed seed: ' + key)
    ident = case['identity']
    historic = read_json(Path(manifest['history']).with_name('benchmark_manifest.json'))
    require(hashlib.sha256(ident['environment_fingerprint'].encode()).hexdigest() == ident['environment_sha256'], 'environment fingerprint hash mismatch')
    require(ident['environment_sha256'] == historic['environmentHash'] and ident['processor_count'] == 1, 'native historical environment/processor identity mismatch')
    require(ident['runtime'] == '.NET 8.0.31' and ident['architecture'] == 'X64', 'native runtime identity mismatch')
    require(ident['harness_sha256'] == manifest['pins'][manifest['command'][1]], 'native harness identity mismatch')
    core = str(Path(manifest['native_dir']) / 'MvsAnalyzer.Core.dll')
    require(ident['core_sha256'] == manifest['pins'][core], 'native core identity mismatch')
    for name in ('generated', 'built', 'left', 'right'):
        bound = case['data'][name]
        require(hashlib.sha256(bound['canonical_json'].encode()).hexdigest() == bound['sha256'], 'native data hash mismatch')
        require(json.loads(bound['canonical_json']) == bound['values'], 'native data value mismatch')
    for side in ('left', 'right'):
        require(len(case['scores_' + side]) == 12 and len(case['availability_' + side]) == 12, 'incomplete vectors')
        require(bool(case['calibration_' + side]), 'missing full calibration rows')
        scores = case['scores_' + side]
        for score in scores: bits(score)
        top = max(range(12), key=lambda i: scores[i])
        for method in ('legacy', 'corrected'):
            require(case[method]['top_' + side + '_index'] == top and case[method]['top_' + side] == metrics[top], 'winner/vector mismatch')
        require([a['metric'] for a in case['availability_' + side]] == metrics, 'availability metric order mismatch')


def report(out):
    out = Path(out)
    errors = []
    try: m = verify(out)
    except Exception as exc:
        errors.append(str(exc)); m = read_json(out / 'bind.json')
    run_result = read_json(out / 'run-finished.json')
    if run_result['end_hash_verification'] != 'passed': errors.append('end hash verification failed')
    errors.extend(run_result['stop_reasons'])
    cases = []
    for attempt in run_result['attempts']:
        try:
            require(attempt['started'] and attempt['returncode'] == 0 and not attempt.get('error'), 'native attempt failed/not started')
            for path, expected in attempt['files'].items(): require(digest(path) == expected, 'attempt evidence hash changed')
            case = read_json(out / ('case-%03d' % attempt['index']) / 'native.json')
            require(case['index'] == attempt['index'], 'attempt/result index mismatch')
            validate_native(case, m)
            cases.append(case)
        except Exception as exc: errors.append('attempt %s: %s' % (attempt['index'], exc))
    result = compare(read_history(m['history']), cases)
    by_index = {a['index']: a for a in run_result['attempts']}
    for pair in result['paired_cases']:
        attempt = by_index.get(pair['index'])
        pair['attempt'] = attempt
        if attempt and not attempt['started']: pair['status'] = 'not-started'
        elif attempt and (attempt['returncode'] != 0 or attempt.get('error')): pair['status'] = 'execution-failed'
        elif attempt and pair['status'] == 'missing': pair['status'] = 'invalid-diagnostics'
    result['not_started_count'] = sum(not a['started'] for a in run_result['attempts'])
    result['execution_failed_count'] = sum(a['started'] and (a['returncode'] != 0 or bool(a.get('error'))) for a in run_result['attempts'])
    result['resources'] = {k: v for k, v in run_result.items() if k != 'attempts'}
    result['execution_errors'] = errors
    result['same_recipe_replay_matching_retained_diagnostics'] = not errors and result['all_120_legacy_diagnostics_exact']
    result['scientific_go'] = False
    result['bind_sha256'] = digest(out / 'bind.json')
    write_json(out / 'report.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='phase', required=True)
    p = sub.add_parser('prepare')
    for name in ('root', 'out', 'protocol', 'native-dir'): p.add_argument('--' + name, required=True)
    p.add_argument('--command', nargs=argparse.REMAINDER, required=True)
    for phase in ('verify', 'run', 'report'): sub.add_parser(phase).add_argument('--out', required=True)
    args = vars(parser.parse_args())
    phase = args.pop('phase')
    try:
        result = globals()[phase](**args)
        print(json.dumps(result, indent=2, allow_nan=False))
        if phase == 'report' and not result['same_recipe_replay_matching_retained_diagnostics']: return 2
        if phase == 'run' and (result['stop_reasons'] or result['end_hash_verification'] != 'passed' or any(a.get('error') for a in result['attempts'])): return 2
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
