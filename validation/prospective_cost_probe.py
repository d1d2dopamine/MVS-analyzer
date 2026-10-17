#!/usr/bin/env python3
"""Bounded Round55 literal-fixture engineering screen; never a study launcher.

prepare invokes identity/validate-only (zero numerical calls), writes immutable
request and binding. run requires --execute and the independently reviewed binding
SHA. Exactly three sequential fresh processes precede one eight-process batch.
Blocking wait measures lifecycle; independent deadline and sampled RSS watchdogs
own cancellation. RSS/output limits are sampled, not kernel hard limits; overshoot and retained tails remain evidence. Neither
functional parity nor fixture-only budget eligibility establishes a speed claim,
worst-case bound, statistical validity, or authorization for 12,000 datasets.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time

import stability_replay_driver as replay
import variance_sensitivity as round50

require, digest, read_json, write_json = replay.require, replay.digest, replay.read_json, replay.write_json
PROTOCOL = 'validation/prospective-cost-probe-v1.json'
PROSPECTIVE = 'validation/prospective-ademp-v1.json'
PROSPECTIVE_SHA = '75d594af6fd2f249ca044340013ea02d16e8cdbae71aef8c4e16ff6853a324ed'
REQUEST_SHA = '6aed9dd4fb65af09414db6b245edfe29173b72521807fa3dafa4008ef396e440'
HISTORY_STDOUT_SHA = 'b696300b6df17a094b2b120bc69cd05b9d4557e3bb764bb2ebd49a8cc03e725b'
HISTORY_RESULT_SHA = '985a14cf4253caa12eb995d6a348937325013e65fc9db417bbc7ffe5e270405b'
REQUEST = dict(schemaVersion=1, protocolId='round55-prospective-adapter-engineering-v1', mode='engineering-fixed-fixture',
               status='frozen', fixtureId='round50-fixed-2x16x40-v1', seed=52000000, repetitions=100,
               referenceReplications=199, withinEffect=2, betweenEffect=2, alpha=.05, calls=1, wallCapSeconds=180)
LIMITS = dict(total_wall_seconds=300, native_case_wall_seconds=180, cleanup_seconds=10, max_workers=8,
              aggregate_rss_bytes=2*1024**3, retained_output_bytes=20_000_000, rss_sampling_seconds=.05, per_process_cpu_count=1)
ENVIRONMENT = {k: '1' for k in ('MVS_DISABLE_BACKUPS', 'DOTNET_PROCESSOR_COUNT', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')}
DOCS = ['docs/PROSPECTIVE_ADAPTER_CONTRACT.md', 'docs/PROSPECTIVE_ADEMP_V1.md', 'docs/BENCHMARK_SUITE.md']
COUNTS = ('fixtureMaterializationCount', 'buildCallCount', 'runCallCount', 'legacyCallCount', 'completenessCallCount', 'payloadSerializationCount', 'directGenerateCallCount', 'directFitCallCount')
CERTIFICATION = ('certified', 'exactKeys', 'allCallbacksExecutedOnce', 'initialConvergedFinite', 'nullFitsConvergedFinite',
                 'allObservedReferenceEvaluationGridStatisticsFinite', 'normalOwnershipNoRestore', 'reportCountsComplete')
SCHEMA = 'mvs-prospective-adapter-envelope-v1'
FINAL_METADATA_RESERVE = 1024**2


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def strict_equal(a, b):
    # JSON object order is immaterial; int versus bool and float bit tokens are not.
    return canonical(a) == canonical(b)


def parse_jsonl(path):
    raw = Path(path).read_bytes()
    require(raw.endswith(b'\n'), 'missing final JSONL newline')
    rows, lines = round50.parse_jsonl(path)
    for row in rows:
        require(type(row) is dict, 'native event must be an object')
        canonical(row)  # rejects overflow-to-infinity numbers as well as literal NaN
    return rows, lines


def files_in(directory):
    return sorted(str(p.resolve()) for p in Path(directory).rglob('*') if p.is_file())


def schedule():
    return [[0], [1], [2], list(range(3, 11))]


def check_protocol(root):
    root = Path(root)
    p = read_json(root / PROTOCOL)
    require(p['schema'] == 'mvs-prospective-cost-probe/v1' and p['status'] == 'frozen_before_engineering_execution', 'protocol not frozen')
    require(p['science_execution_authorized'] is False and p['scientific_datasets_generated'] == 0, 'science forbidden')
    require(strict_equal(p['request'], REQUEST) and p['request_canonical_sha256'] == REQUEST_SHA, 'request contract changed')
    require(hashlib.sha256(canonical(p['request'])).hexdigest() == REQUEST_SHA, 'canonical request changed')
    require(strict_equal(p['limits'], LIMITS) and p['required_environment'] == ENVIRONMENT, 'resource contract changed')
    require(p['schedule'] == dict(sequential_fresh_processes=3, parallel_fresh_processes=8, max_native_calculation_calls=11, retries=0), 'schedule changed')
    require(p['prospective_protocol'] == {'path': PROSPECTIVE, 'sha256': PROSPECTIVE_SHA}, 'original54 reference changed')
    require(digest(root / PROSPECTIVE) == PROSPECTIVE_SHA, 'original54 protocol changed')
    parity = p['parity']
    require(parity['reference_stdout_sha256'] == HISTORY_STDOUT_SHA and parity['reference_result_sha256'] == HISTORY_RESULT_SHA, 'historical hashes changed')
    require(parity['excluded_payload_fields'] == ['call'] and parity['excluded_trace_fields'] == ['call'], 'parity exclusions changed')
    require(parity['expected_cached_callbacks_per_call'] == 1103 and parity['compare_all_callback_payloads'] is True and parity['require_complete_each_call'] is True and parity['no_replacement_on_mismatch'] is True, 'parity requirements changed')
    admission = p['admission']
    require(admission['wall_projection'] == '2*max(max_sequential_lifecycle_seconds,parallel_batch_lifecycle_seconds)*12000/8', 'wall formula changed')
    require(admission['storage_projection'] == '2*max_retained_case_bytes*12000+1073741824', 'storage formula changed')
    require(admission['max_projected_seconds'] == 86400 and admission['historical_linear_reference_seconds'] == 41727.10178525085 and admission['scientific_launch_authorized'] is False, 'admission changed')
    return p


def envelope(row, mode, expected_request=REQUEST_SHA):
    require(row['schema'] == SCHEMA and row['protocolId'] == REQUEST['protocolId'] and row['mode'] == mode, 'native envelope mismatch')
    require(row['requestSha256'] == expected_request, 'native request SHA mismatch')
    require(row['operationCountScope'] == 'adapter_entry_calls_only_nested_production_calls_not_instrumented', 'operation counter scope changed')
    counts = row['operationCounts']
    require(set(counts) == set(COUNTS) and all(type(v) is int and v in (0, 1) for v in counts.values()), 'operation counts invalid')
    require(counts['directGenerateCallCount'] == counts['directFitCallCount'] == 0, 'forbidden generation/direct Fit')


def validate_identity(row, manifest, mode='identity'):
    envelope(row, mode, None if mode == 'identity' else REQUEST_SHA)
    require(row['frozenEngineeringRequestSha256'] == REQUEST_SHA, 'native frozen request mismatch')
    identity = row['identity']; root = Path(manifest['root']); pins = manifest['pins']
    require(identity['experimental'] is True and len(identity['sourceSha256']) == 14, 'native source identity incomplete')
    for rel, sha in identity['sourceSha256'].items():
        require(pins[str(root / rel)] == sha, 'embedded Round50/Core source mismatch: ' + rel)
    require(set(row['adapterSourceSha256']) == {'validation/prospective_adapter/Program.cs', 'validation/prospective_adapter/ProspectiveAdapter.csproj'}, 'adapter source set mismatch')
    for rel, sha in row['adapterSourceSha256'].items():
        require(pins[str(root / rel)] == sha, 'embedded adapter source mismatch: ' + rel)
    for key in ('harnessAssembly', 'coreAssembly'):
        item = identity[key]
        require(Path(item['fileName']).name == item['fileName'], 'invalid assembly filename')
        require(pins[str(Path(manifest['native_dir']) / item['fileName'])] == item['sha256'], 'assembly mismatch: ' + key)
    runtime = identity['runtime']
    require(runtime['version'] == '8.0.31' and runtime['framework'] == '.NET 8.0.31' and runtime['processArchitecture'] == 'X64', 'runtime identity mismatch')
    require(runtime['coreLibrarySha256'] in [pins[p] for p in manifest['runtime_files'] if Path(p).name == 'System.Private.CoreLib.dll'], 'core runtime bytes mismatch')
    if mode == 'identity': require(all(v == 0 for v in row['operationCounts'].values()), 'identity performed computation')
    else: require(row['processorCount'] == 1, 'native CPU cap mismatch')


def historical_reference(stdout, result):
    require(digest(stdout) == HISTORY_STDOUT_SHA and digest(result) == HISTORY_RESULT_SHA, 'historical evidence changed')
    require(read_json(result)['status'] == 'cost_certified', 'historical certification missing')
    rows, _ = parse_jsonl(stdout)
    payloads = [r['payload'] for r in rows if r['kind'] == 'call_complete']
    require([p['call'] for p in payloads] == [1, 2], 'historical call count changed')
    traces = [[{k: v for k, v in r.items() if k != 'call'} for r in rows if r.get('call') == call and r['kind'] in ('try', 'cached', 'completeness')] for call in (1, 2)]
    payloads = [{k: v for k, v in p.items() if k != 'call'} for p in payloads]
    require(strict_equal(payloads[0], payloads[1]) and strict_equal(traces[0], traces[1]), 'historical calls disagree; no replacement allowed')
    round50.validate_callbacks([r['observation'] for r in traces[0] if r['kind'] == 'cached'])
    fixture = [r for r in rows if r['kind'] == 'fixture']; require(len(fixture) == 1, 'historical fixture count')
    fixture = {k: v for k, v in fixture[0].items() if k not in ('kind', 'buildTiming')}
    return dict(payload=payloads[0], trace=traces[0], fixture=fixture)


def validate_native(path, manifest, reference):
    rows, _ = parse_jsonl(path)
    require(rows and rows[0]['kind'] == 'adapter_start' and rows[-1]['kind'] == 'adapter_complete', 'incomplete native stream')
    allowed = {'adapter_start', 'fixture', 'try', 'cached', 'variance_returned', 'completeness', 'call_complete', 'adapter_complete'}
    require(all(r['kind'] in allowed for r in rows), 'unknown native event')
    for row in rows:
        if row['kind'] not in ('try', 'cached', 'completeness'): envelope(row, 'engineering')
        if 'call' in row: require(type(row['call']) is int and row['call'] == 1, 'unexpected native call')
    for kind in ('adapter_start', 'fixture', 'variance_returned', 'completeness', 'call_complete', 'adapter_complete'):
        require(sum(r['kind'] == kind for r in rows) == 1, 'missing/duplicate event: ' + kind)
    validate_identity(rows[0], manifest, 'engineering')
    expected_kinds = ['adapter_start', 'fixture'] + [r['kind'] for r in reference['trace'] if r['kind'] != 'completeness'] + ['variance_returned', 'completeness', 'call_complete', 'adapter_complete']
    require([r['kind'] for r in rows] == expected_kinds, 'native event order changed')
    for row in rows:
        kind = row['kind']
        if kind in ('adapter_start', 'fixture', 'variance_returned', 'call_complete', 'adapter_complete'):
            done = {'adapter_start': 0, 'fixture': 2, 'variance_returned': 3, 'call_complete': 6, 'adapter_complete': 6}[kind]
            require(row['operationCounts'] == {k: int(i < done) for i, k in enumerate(COUNTS)}, 'operation phase count mismatch')
    fixture = next(r for r in rows if r['kind'] == 'fixture')
    require(fixture['exactOrderedBinary64Retention'] is True, 'input changed during Build')
    require(strict_equal({k: fixture[k] for k in reference['fixture']}, reference['fixture']), 'historical fixture parity failed')
    round50.timing(fixture['buildTiming'])
    cached = [r['observation'] for r in rows if r['kind'] == 'cached']
    round50.validate_callbacks(cached)
    trace = [{k: v for k, v in r.items() if k != 'call'} for r in rows if r['kind'] in ('try', 'cached', 'completeness')]
    require(strict_equal(trace, reference['trace']), 'historical callback trace parity failed')
    summary = next(r['summary'] for r in rows if r['kind'] == 'completeness')
    require(all(summary[k] is True for k in CERTIFICATION), 'actual Complete certification failed')
    require(summary['actualCachedRequests'] == summary['expectedCachedRequests'] == 1103 and summary['missingKeys'] == [], 'incomplete callback count')
    complete = next(r for r in rows if r['kind'] == 'call_complete'); payload = complete['payload']
    require(set(payload) == {'call', 'dataSha256', 'report', 'legacy', 'completeness'} and type(payload['call']) is int and payload['call'] == 1, 'payload fields changed')
    require(strict_equal({k: v for k, v in payload.items() if k != 'call'}, reference['payload']), 'historical scientific payload parity failed')
    returned = next(r for r in rows if r['kind'] == 'variance_returned')
    require(strict_equal(returned['report'], payload['report']) and strict_equal(returned['runTiming'], complete['runTiming']), 'duplicated report/timing mismatch')
    require(strict_equal(summary, payload['completeness']), 'duplicated completeness mismatch')
    for key in ('runTiming', 'legacyTiming', 'serializationTiming'): round50.timing(complete[key])
    for key in ('serializedUtf8Bytes', 'legacySerializedUtf8Bytes'):
        require(type(complete[key]) is int and complete[key] > 0, 'serialized byte count invalid')
    end = rows[-1]
    require(end['completed'] is True and end['status'] == 'engineering_fixture_complete' and end['scientificStudyExecuted'] is False, 'native completion failed')
    require(end['operationCounts'] == {k: int(k not in ('directGenerateCallCount', 'directFitCallCount')) for k in COUNTS}, 'actual operation counts incomplete')
    require(all(type(end[k]) in (int, float) and math.isfinite(end[k]) and end[k] >= 0 for k in ('nativeTotalWallSeconds', 'processTotalCpuSeconds')), 'invalid native clock')
    require(type(end['processPeakWorkingSetBytes']) is int and 0 < end['processPeakWorkingSetBytes'] <= LIMITS['aggregate_rss_bytes'], 'invalid native high-water RSS')
    return dict(certified=True, payload_sha256=hashlib.sha256(canonical(reference['payload'])).hexdigest(),
                callback_trace_sha256=hashlib.sha256(canonical(trace)).hexdigest(), native_totals=end,
                run_timing=complete['runTiming'], legacy_timing=complete['legacyTiming'], serialization_timing=complete['serializationTiming'])


def native_argv(command):
    return [command[0], '--fx-version', '8.0.31', command[1]]


def child_environment(dotnet):
    env = dict(os.environ, **ENVIRONMENT)
    # Disable runtime roll-forward, startup injection and inherited profiler hooks.
    for key in list(env):
        if key.startswith(('DOTNET_', 'COMPlus_', 'CORECLR_', 'COR_')): env.pop(key)
    env.update(ENVIRONMENT, DOTNET_ROLL_FORWARD='Disable', DOTNET_ROOT=str(Path(dotnet).parent))
    return env


def live_group_members(pids):
    members = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(stat[2]) in pids and stat[0] != 'Z': members.append(int(path.name))
        except (FileNotFoundError, ProcessLookupError): pass  # bounded process-exit race only
    return members


def retained_bytes(directory):
    return sum(p.stat().st_size for p in Path(directory).rglob('*') if p.is_file())


def execute_schedule(out, commands, batches, environment, validator=None, *, wall_seconds=300, memory_bytes=2*1024**3,
                     output_bytes=20_000_000, sample_seconds=.05, cleanup_seconds=10, rss_reader=None):
    """Private synthetic-test seam; public run fixes every resource and all 11 calls.

    Uses tested replay process-group kill/RSS readers. A separate Timer is never
    delayed by RSS or disk reads. No polling subprocess wait enters wall timing.
    On stuck cleanup a daemon Timer writes an abort marker then exits 124.
    """
    out = Path(out); rss_reader = rss_reader or replay.group_rss
    require(sorted(i for batch in batches for i in batch) == list(range(len(commands))), 'invalid schedule')
    streams, attempts = {}, []
    # Open *all* direct output files before any measured engineering timer.
    try:
        for i, command in enumerate(commands):
            directory = out / f'case-{i:02d}'; directory.mkdir()
            streams[i] = ((directory / 'stdout.jsonl').open('xb'), (directory / 'stderr.log').open('xb'))
            attempts.append(dict(index=i, started=False, status='not_started', returncode=None, command=command, rss_samples=0))
    except Exception:
        for pair in streams.values():
            for stream in pair: stream.close()
        raise
    lock = threading.Lock(); stop_lock = threading.Lock(); stopped = threading.Event(); finished = threading.Event()
    live, owned, reasons = {}, {}, []; peak, samples = 0, 0; abort_timer = None; supervisor_closed = False
    start = time.monotonic(); deadline = start + wall_seconds
    cpu0 = resource.getrusage(resource.RUSAGE_CHILDREN)

    def abort():
        for proc in list(owned.copy().values()):
            try: replay.kill_group(proc)
            except OSError: pass
        try: write_json(out / 'cleanup-abort.json', {'status': 'cleanup_failure', 'active_pids': list(live), 'exit_code': 124})
        finally: os._exit(124)

    def stop(code, detail=''):
        nonlocal abort_timer
        # Killing does not depend on successful writes or the launch lock.
        with stop_lock:
            if supervisor_closed: return
            first = not stopped.is_set(); stopped.set()
            if not any(r['code'] == code and r['detail'] == detail for r in reasons): reasons.append({'code': code, 'detail': detail})
            if first:
                abort_timer = threading.Timer(cleanup_seconds, abort); abort_timer.daemon = True; abort_timer.start()
        if first:
            try: write_json(out / 'watchdog-stop.json', {'code': code, 'detail': detail, 'monotonic': time.monotonic()})
            except OSError: pass
        for proc in list(owned.copy().values()):
            try: replay.kill_group(proc)
            except OSError as exc:
                if not any(r['code'] == 'cleanup_failure' for r in reasons): reasons.append({'code': 'cleanup_failure', 'detail': repr(exc)})

    def sample():
        nonlocal peak, samples
        snapshot = live.copy()
        value = rss_reader(set(owned.copy()))
        require(type(value) is int and value >= 0, 'invalid RSS sample')
        peak = max(peak, value); samples += 1
        for pid, proc in snapshot.items():
            # A vanished /proc entry is allowed only after a verified process exit.
            if not Path(f'/proc/{pid}').exists() and proc.returncode is None:
                try: os.kill(pid, 0)
                except ProcessLookupError: pass
                else: raise OSError('owned live process missing /proc record')
            attempts[proc.probe_index]['rss_samples'] += 1
        if value > memory_bytes: stop('memory_limit', str(value))
        if retained_bytes(out) > output_bytes: stop('bytes_limit', 'retained output cap exceeded')

    def watch():
        while not finished.wait(sample_seconds):
            try: sample()
            except Exception as exc: stop('resource_read_failure', repr(exc)); return

    def one(i):
        record = attempts[i]; directory = out / f'case-{i:02d}'; stdout, stderr = streams[i]; proc = None
        try:
            with lock:
                if stopped.is_set() or time.monotonic() >= deadline:
                    record['error'] = 'budget exhausted or prior failure'; return
                # Direct files already open. Timer immediately precedes Popen.
                record['start_monotonic'] = time.monotonic(); record['start_unix'] = time.time()
                proc = subprocess.Popen(commands[i], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        env=environment, shell=False, start_new_session=True)
                proc.probe_index = i; owned[proc.pid] = proc; live[proc.pid] = proc
                record.update(started=True, pid=proc.pid, status='running')
                if stopped.is_set(): replay.kill_group(proc)
            write_json(directory / 'started.json', {k: record[k] for k in ('index', 'pid', 'command', 'start_monotonic', 'start_unix')})
            record['returncode'] = proc.wait()  # blocking wait; independent watchdog owns the deadline
            record['end_monotonic'] = time.monotonic(); record['end_unix'] = time.time()
            record['lifecycle_seconds'] = record['end_monotonic'] - record['start_monotonic']
            if record['returncode'] is None: stop('unknown_exit', str(i)); record['status'] = 'unknown_exit'
            elif record['returncode'] != 0: stop('native_failure', str(i)); record['status'] = 'native_failure'
            else: record['status'] = 'process_exited'
        except Exception as exc:
            record.update(status='process_failure', error=repr(exc)); stop('process_failure', repr(exc))
        finally:
            if proc:
                try:
                    replay.kill_group(proc)
                    if proc.returncode is None: proc.wait(timeout=cleanup_seconds)
                    record['returncode'] = proc.returncode
                    until = time.monotonic() + cleanup_seconds
                    while live_group_members({proc.pid}):
                        replay.kill_group(proc)
                        if time.monotonic() >= until: raise TimeoutError('live process-group descendants after cleanup')
                        finished.wait(.01)
                except Exception as exc:
                    record.update(status='cleanup_failure', cleanup_error=repr(exc)); stop('cleanup_failure', repr(exc))
                else:
                    live.pop(proc.pid, None); owned.pop(proc.pid, None)
            stdout.close(); stderr.close()
            record['cleanup_end_monotonic'] = time.monotonic()
            if record['status'] == 'process_exited':
                try:
                    if (directory / 'stdout.jsonl').stat().st_size == 0:
                        record['status'] = 'missing_outputs'; stop('missing_outputs', str(i)); raise ValueError('missing native output')
                    require((directory / 'stderr.log').stat().st_size == 0, 'native stderr nonempty')
                    if validator is not None: record['validation'] = validator(directory / 'stdout.jsonl')
                    record['status'] = 'completed'
                except Exception as exc:
                    record['error'] = repr(exc)
                    if record['status'] != 'missing_outputs': record['status'] = 'validation_failure'; stop('validation_failure', repr(exc))
            try:
                record['file_sha256'] = {p.name: digest(p) for p in directory.iterdir() if p.is_file()}
                write_json(directory / 'attempt.json', record)
            except Exception as exc:
                record.update(status='retention_failure', error=repr(exc)); stop('retention_failure', repr(exc))

    watchdog = threading.Thread(target=watch, daemon=True); watchdog.start()
    wall_timer = threading.Timer(max(.001, deadline - time.monotonic()), lambda: stop('wall_timeout', 'global deadline reached')); wall_timer.daemon = True; wall_timer.start()
    handlers = {}; batch_records = []
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM): handlers[sig] = signal.signal(sig, lambda s, f: stop('driver_signal', str(s)))
    try:
        for batch in batches:
            if stopped.is_set(): break
            with ThreadPoolExecutor(max_workers=len(batch)) as pool: list(pool.map(one, batch))
            started = [attempts[i] for i in batch if attempts[i]['started']]
            ended = [a for a in started if 'end_monotonic' in a]
            batch_records.append({'indices': batch, 'lifecycle_seconds': max(a['end_monotonic'] for a in ended) - min(a['start_monotonic'] for a in started) if len(ended) == len(batch) else None})
            if any(attempts[i]['status'] != 'completed' for i in batch): break
        sample()  # fail closed on final resource/bytes read as well
    except Exception as exc: stop('supervisor_failure', repr(exc))
    finally:
        finished.set(); wall_timer.cancel(); wall_timer.join(timeout=cleanup_seconds); watchdog.join(timeout=cleanup_seconds)
        if watchdog.is_alive() or wall_timer.is_alive(): stop('cleanup_failure', 'resource/deadline watchdog did not terminate')
        # A failed first cleanup must not discard ownership or cancel its watchdog.
        if owned:
            until = time.monotonic() + cleanup_seconds
            while owned and time.monotonic() < until:
                for pid, proc in list(owned.copy().items()):
                    try:
                        replay.kill_group(proc)
                        if proc.returncode is not None and not live_group_members({pid}):
                            owned.pop(pid, None); live.pop(pid, None)
                    except Exception: pass  # already failed; retain ownership until abort
                if owned: threading.Event().wait(.01)
            if owned and abort_timer is not None: abort_timer.join(cleanup_seconds + .1)
        for pair in streams.values():
            for stream in pair: stream.close()
        for sig, handler in handlers.items(): signal.signal(sig, handler)
        with stop_lock:
            if not owned and not live and not watchdog.is_alive() and not wall_timer.is_alive():
                supervisor_closed = True
                if abort_timer is not None: abort_timer.cancel()
        if supervisor_closed and abort_timer is not None: abort_timer.join(timeout=cleanup_seconds)
    for record in attempts:
        if not record['started'] and not (out / f"case-{record['index']:02d}" / 'attempt.json').exists():
            try: write_json(out / f"case-{record['index']:02d}" / 'attempt.json', record)
            except Exception as exc: reasons.append({'code': 'retention_failure', 'detail': repr(exc)})
    cpu1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(attempts=attempts, batches=batch_records, stop_reasons=reasons, elapsed_seconds=time.monotonic()-start,
                peak_aggregate_rss_bytes=peak, rss_sample_count=samples, rss_scope='sampled owned process groups; 50ms nominal, not a kernel hard limit',
                host_child_cpu_seconds=(cpu1.ru_utime+cpu1.ru_stime)-(cpu0.ru_utime+cpu0.ru_stime), cleanup_complete=not owned and not live and not watchdog.is_alive() and not wall_timer.is_alive())


def prepare(root, out, native_dir, runtime_dirs, command, historical_stdout, historical_result, build_evidence):
    root, out, native_dir = (Path(p).resolve() for p in (root, out, native_dir))
    require(not out.exists(), 'fresh output directory required; no overwrite/resume')
    require(sys.platform == 'linux' and hasattr(os, 'sched_getaffinity'), 'Linux /proc, process groups and affinity required')
    p = check_protocol(root)
    cpus = sorted(os.sched_getaffinity(0))[:8]; require(len(cpus) == 8, 'eight distinct available CPUs required')
    require(len(command) == 2 and Path(command[1]).suffix == '.dll', 'command must be dotnet plus adapter DLL only')
    dotnet, taskset = shutil.which(command[0]), shutil.which('taskset')
    require(dotnet is not None and taskset is not None, 'dotnet and taskset required')
    command = [str(Path(dotnet).resolve()), str(Path(command[1]).resolve())]; taskset = str(Path(taskset).resolve())
    native = files_in(native_dir); require(command[1] in native, 'adapter DLL must be pinned inside native build')
    expected_runtime_dirs = sorted(str(Path(command[0]).parent / d / '8.0.31') for d in ('shared/Microsoft.NETCore.App', 'host/fxr'))
    runtime_dirs = sorted(str(Path(d).resolve()) for d in runtime_dirs)
    require(runtime_dirs == expected_runtime_dirs and all(Path(d).is_dir() for d in runtime_dirs), 'exact .NET 8.0.31 runtime/fxr directories required')
    runtime = sorted(set(f for d in runtime_dirs for f in files_in(d))); require(runtime, 'runtime files missing')
    history = [str(Path(x).resolve()) for x in (historical_stdout, historical_result)]
    historical_reference(*history)
    build_evidence = str(Path(build_evidence).resolve()); require(bool(read_json(build_evidence)), 'build evidence required')
    sources = list(map(str, replay.source_paths(root)))
    docs = [str(root / d) for d in DOCS]
    implementation = sorted(str(Path(f).resolve()) for f in (__file__, replay.__file__, round50.__file__))
    paths = implementation + sources + native + runtime + docs + history + [str(root / PROTOCOL), str(root / PROSPECTIVE), command[0], taskset, str(Path(sys.executable).resolve()), build_evidence]
    pins = replay.pin_paths(map(Path, paths))
    m = dict(schema='mvs-prospective-cost-binding/v1', root=str(root), command=command, taskset=taskset,
             native_dir=str(native_dir), native_files=native, runtime_dirs=runtime_dirs, runtime_files=runtime,
             sources=sources, implementation_files=implementation, documents=docs, pins=pins, history_stdout=history[0], history_result=history[1], build_evidence=build_evidence,
             limits=LIMITS, schedule=schedule(), cpu_ids=cpus, environment_overrides=ENVIRONMENT,
             python_executable=str(Path(sys.executable).resolve()), python_version=sys.version, science_execution_authorized=False)
    out.mkdir(parents=True)
    with (out / 'request.json').open('xb') as f: f.write(canonical(p['request']))
    m['request'] = str(out / 'request.json'); m['pins'][m['request']] = REQUEST_SHA
    # These two processes cannot invoke numerical work; their raw evidence is pinned.
    check_dir = out / 'preflight'; check_dir.mkdir()
    cmds = [[taskset, '-c', str(cpus[0]), *native_argv(command), 'identity'], [taskset, '-c', str(cpus[0]), *native_argv(command), 'validate-only', m['request'], REQUEST_SHA]]
    preflight = execute_schedule(check_dir, cmds, [[0], [1]], child_environment(command[0]), wall_seconds=30)
    write_json(check_dir / 'result.json', preflight)
    require(not preflight['stop_reasons'] and all(a['status'] == 'completed' for a in preflight['attempts']), 'identity/request preflight failed; inspect retained evidence')
    identity_rows, _ = parse_jsonl(check_dir / 'case-00/stdout.jsonl'); require(len(identity_rows) == 1 and identity_rows[0]['kind'] == 'identity', 'identity response shape')
    validate_identity(identity_rows[0], m)
    valid_rows, _ = parse_jsonl(check_dir / 'case-01/stdout.jsonl'); require(len(valid_rows) == 1, 'request validation response shape')
    valid = valid_rows[0]; envelope(valid, 'validate-only')
    require(valid['kind'] == 'request_validated' and valid['valid'] is True and valid['completed'] is False and valid['computationInvoked'] is False and all(v == 0 for v in valid['operationCounts'].values()), 'validation invoked computation')
    m['preflight_files'] = files_in(check_dir); m['pins'].update(replay.pin_paths(map(Path, m['preflight_files'])))
    m['native_identity'] = identity_rows[0]
    write_json(out / 'bind.json', m)
    with (out / 'bind.sha256').open('x') as f: f.write(digest(out / 'bind.json') + '\n')
    return m


def verify(out, expected_sha=None):
    out = Path(out).resolve(); sha = digest(out / 'bind.json')
    require(sha == (out / 'bind.sha256').read_text().strip(), 'binding seal mismatch')
    if expected_sha is not None: require(sha == expected_sha, 'approved binding SHA mismatch')
    m = read_json(out / 'bind.json'); root = Path(m['root'])
    require(m['schema'] == 'mvs-prospective-cost-binding/v1' and m['science_execution_authorized'] is False, 'binding scope changed')
    require(strict_equal(m['limits'], LIMITS) and m['schedule'] == schedule() and m['environment_overrides'] == ENVIRONMENT, 'binding contract changed')
    require(len(m['cpu_ids']) == len(set(m['cpu_ids'])) == 8 and all(type(c) is int and c in os.sched_getaffinity(0) for c in m['cpu_ids']), 'CPU affinity unavailable')
    require(m['sources'] == list(map(str, replay.source_paths(root))), 'source file set changed')
    require(m['implementation_files'] == sorted(str(Path(f).resolve()) for f in (__file__, replay.__file__, round50.__file__)), 'actual Python implementation changed')
    require(len(m['command']) == 2 and Path(m['command'][0]).name == 'dotnet' and m['command'][1] in m['native_files'] and Path(m['command'][1]).suffix == '.dll', 'invalid native command')
    require(Path(m['taskset']).name == 'taskset', 'invalid affinity executable')
    require(m['runtime_dirs'] == sorted(str(Path(m['command'][0]).parent / d / '8.0.31') for d in ('shared/Microsoft.NETCore.App', 'host/fxr')), 'runtime directory contract changed')
    require(m['native_files'] == files_in(m['native_dir']), 'native build file set changed')
    require(m['runtime_files'] == sorted(set(f for d in m['runtime_dirs'] for f in files_in(d))), 'runtime file set changed')
    require(m['documents'] == [str(root / d) for d in DOCS], 'document set changed')
    require(m['preflight_files'] == files_in(out / 'preflight'), 'preflight file set changed')
    require(m['request'] == str(out / 'request.json') and digest(m['request']) == REQUEST_SHA, 'request path or bytes changed')
    require(m['python_executable'] == str(Path(sys.executable).resolve()) and m['python_version'] == sys.version, 'Python runtime changed')
    expected = set(m['implementation_files'] + m['sources'] + m['native_files'] + m['runtime_files'] + m['documents'] + m['preflight_files'] +
                   [str(root / PROTOCOL), str(root / PROSPECTIVE), m['history_stdout'], m['history_result'], m['build_evidence'],
                    m['command'][0], m['taskset'], m['python_executable'], m['request']])
    require(set(m['pins']) == expected, 'binding pin coverage changed')
    for path, sha in m['pins'].items(): require(digest(path) == sha, 'pinned content changed: ' + path)
    check_protocol(root); historical_reference(m['history_stdout'], m['history_result']); validate_identity(m['native_identity'], m)
    require(strict_equal(parse_jsonl(out / 'preflight/case-00/stdout.jsonl')[0], [m['native_identity']]), 'stored/preflight native identity differs')
    return m


def admission(sequential_seconds, parallel_seconds, max_case_bytes, available_bytes, *, all_complete, rss_ok, failures=()):
    require(len(sequential_seconds) == 3 and all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in [*sequential_seconds, parallel_seconds]), 'complete positive wall measurements required')
    require(type(max_case_bytes) is int and max_case_bytes > 0 and type(available_bytes) is int and available_bytes >= 0, 'invalid storage measurements')
    projected = 2 * max(max(sequential_seconds), parallel_seconds) * 12000 / 8
    storage = 2 * max_case_bytes * 12000 + 1024**3
    return dict(projected_wall_seconds=projected, projected_wall_hours=projected/3600, storage_required_bytes=storage,
                available_storage_bytes=available_bytes, budget_eligible=all_complete is True and rss_ok is True and not failures and projected <= 86400 and storage <= available_bytes,
                historical_linear_reference_seconds=41727.10178525085, historical_linear_reference_hours=41727.10178525085/3600,
                historical_reference_is_distinct=True, science_execution_authorized=False,
                interpretation='functional parity and fixed-fixture resource screen only; no speed claim, worst-case guarantee or scientific launch authorization')


def run(out, binding_sha, execute=False):
    require(execute is True, 'explicit --execute required')
    out = Path(out).resolve(); m = verify(out, binding_sha)
    require(not (out / 'run-started.json').exists(), 'already attempted; no retry/overwrite/resume')
    write_json(out / 'run-started.json', dict(binding_sha256=binding_sha, unix_seconds=time.time(), schedule=schedule()))
    reference = historical_reference(m['history_stdout'], m['history_result'])
    commands = [[m['taskset'], '-c', str(m['cpu_ids'][0 if i < 3 else i-3]), *native_argv(m['command']), 'engineering', m['request'], REQUEST_SHA] for i in range(11)]
    result = {'schema': 'mvs-prospective-cost-result/v1', 'status': 'technical_failure', 'binding_sha256': binding_sha,
              'science_execution_authorized': False, 'scientific_datasets_generated': 0}
    try:
        result.update(execute_schedule(out, commands, schedule(), child_environment(m['command'][0]), lambda p: validate_native(p, m, reference), output_bytes=LIMITS['retained_output_bytes']-FINAL_METADATA_RESERVE))
        try: verify(out, binding_sha); result['end_provenance'] = 'verified'
        except Exception as exc: result['end_provenance'] = 'failed'; result['stop_reasons'].append({'code': 'provenance_failure', 'detail': repr(exc)})
        attempts = result['attempts']; complete = all(a['status'] == 'completed' and a['returncode'] == 0 and a.get('validation', {}).get('certified') is True for a in attempts) and len(attempts) == 11
        sampled = all(a['rss_samples'] > 0 for a in attempts) and result['rss_sample_count'] > 0 and 0 < result['peak_aggregate_rss_bytes'] <= LIMITS['aggregate_rss_bytes']
        if not sampled: result['stop_reasons'].append({'code': 'memory_evidence_incomplete', 'detail': 'every engineering process needs at least one sampled RSS observation'})
        native_peaks = [a.get('validation', {}).get('native_totals', {}).get('processPeakWorkingSetBytes', 0) for a in attempts]
        # Sum individual peaks is a conservative crosscheck, not a simultaneous measurement.
        result['native_parallel_peak_sum_bytes'] = sum(native_peaks[3:]); rss_ok = sampled and max(native_peaks, default=0) <= LIMITS['aggregate_rss_bytes'] and sum(native_peaks[3:]) <= LIMITS['aggregate_rss_bytes']
        if not rss_ok: result['stop_reasons'].append({'code': 'memory_crosscheck_failure', 'detail': 'sampled/native high-water resource evidence failed'})
        case_bytes = [retained_bytes(out / f'case-{i:02d}') for i in range(11)]
        result['retained_case_bytes'] = case_bytes; result['retained_output_bytes_before_summary'] = retained_bytes(out)
        if result['retained_output_bytes_before_summary'] + FINAL_METADATA_RESERVE > LIMITS['retained_output_bytes']: result['stop_reasons'].append({'code': 'bytes_limit', 'detail': 'final evidence exceeds cap'})
        available = shutil.disk_usage(out).free
        if complete and len(result['batches']) == 4 and result['batches'][-1]['lifecycle_seconds'] is not None:
            result['admission'] = admission([a['lifecycle_seconds'] for a in attempts[:3]], result['batches'][-1]['lifecycle_seconds'], max(case_bytes), available,
                                            all_complete=complete, rss_ok=rss_ok, failures=result['stop_reasons'])
        else: result['admission'] = {'budget_eligible': False, 'science_execution_authorized': False, 'reason': 'incomplete engineering evidence'}
        if complete and rss_ok and not result['stop_reasons'] and result['cleanup_complete']: result['status'] = 'engineering_complete'
    except Exception as exc:
        result['failure'] = repr(exc); result['admission'] = {'budget_eligible': False, 'science_execution_authorized': False}
    # Bound final metadata before choosing a completed result. Reserve includes the
    # result JSON and seal; failure evidence is retained even if the cap is exceeded.
    result['final_metadata_reserve_bytes'] = FINAL_METADATA_RESERVE
    projected_seal = {'schema': 'mvs-prospective-cost-seal/v1', 'files': {str(Path(p).relative_to(out)): '0'*64 for p in files_in(out)}}
    projected_seal['files']['result.json'] = '0'*64
    pretty = lambda value: (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    if len(pretty(result)) + len(pretty(projected_seal)) > FINAL_METADATA_RESERVE:
        result['status'] = 'retention_failure'; result['admission']['budget_eligible'] = False
        result.setdefault('stop_reasons', []).append({'code': 'bytes_limit', 'detail': 'final metadata reserve exceeded'})
    write_json(out / 'result.json', result)
    paths = files_in(out)
    write_json(out / 'seal.json', {'schema': 'mvs-prospective-cost-seal/v1', 'files': {str(Path(p).relative_to(out)): digest(p) for p in paths}})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); subs = parser.add_subparsers(dest='action', required=True)
    p = subs.add_parser('prepare')
    for name in ('root', 'out', 'native-dir', 'historical-stdout', 'historical-result', 'build-evidence'): p.add_argument('--' + name, required=True)
    p.add_argument('--runtime-dir', action='append', required=True); p.add_argument('--command', nargs=2, required=True)
    p = subs.add_parser('verify'); p.add_argument('--out', required=True); p.add_argument('--binding-sha')
    p = subs.add_parser('run'); p.add_argument('--out', required=True); p.add_argument('--binding-sha', required=True); p.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        value = prepare(args.root, args.out, args.native_dir, args.runtime_dir, args.command, args.historical_stdout, args.historical_result, args.build_evidence)
        print(json.dumps({'status': 'prepared', 'binding_sha256': digest(Path(args.out) / 'bind.json'), 'science_execution_authorized': False})); return 0
    if args.action == 'verify': verify(args.out, args.binding_sha); print(json.dumps({'status': 'verified'})); return 0
    value = run(args.out, args.binding_sha, args.execute); print(json.dumps(value, indent=2, allow_nan=False)); return 0 if value['status'] == 'engineering_complete' else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc: print(json.dumps({'status': 'technical_failure', 'error': str(exc), 'science_execution_authorized': False}), file=sys.stderr); raise SystemExit(2)
