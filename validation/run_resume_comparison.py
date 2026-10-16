#!/usr/bin/env python3
"""TEST-only Round34 real CLI resume comparison; never executes a model on import.

freeze binds sources, binaries, runtime, immutable completed-result fixtures and plan.
run requires explicit measurement-window approval and retains all 30 planned attempts.
verify recomputes retained evidence without writes or native/model process launches.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import argparse
import csv
import decimal
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import statistics
import subprocess
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parent
METRICS = ('wallSeconds', 'cpuUserSeconds', 'cpuSystemSeconds', 'cpuTotalSeconds', 'peakRssKiB')
KINDS = ('calibrate', 'analyze', 'variance', 'estimation', 'melsm')

def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def dump_new(path, data):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False, default=lambda x: float(x) if isinstance(x, decimal.Decimal) else (_ for _ in ()).throw(TypeError(type(x).__name__)))
        stream.write('\n')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def strict_json(raw):
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8-sig')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'Nonfinite JSON token: {value}')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=decimal.Decimal, parse_constant=invalid)


def read_json(path):
    return strict_json(Path(path).read_bytes())


def token_spans(raw):
    """JSON pointer -> (start,end,value) without rewriting number/string tokens."""
    text = raw.decode('utf-8')
    prefix = 1 if text.startswith('\ufeff') else 0
    strict_json(raw)
    decoder = json.JSONDecoder(parse_float=decimal.Decimal)
    spans = {}
    def ws(pos):
        while pos < len(text) and text[pos] in ' \r\n\t':
            pos += 1
        return pos
    def pointer(parent, child):
        return parent + '/' + str(child).replace('~', '~0').replace('/', '~1')
    def parse(pos, path):
        pos = ws(pos)
        start = pos
        if text[pos] == '{':
            value = {}
            pos = ws(pos + 1)
            if text[pos] != '}':
                while True:
                    key, pos = decoder.raw_decode(text, pos)
                    require(isinstance(key, str), 'Non-string JSON key')
                    pos = ws(pos)
                    require(text[pos] == ':', 'Expected JSON colon')
                    child, pos = parse(pos + 1, pointer(path, key))
                    value[key] = child
                    pos = ws(pos)
                    if text[pos] == '}':
                        break
                    require(text[pos] == ',', 'Expected JSON comma')
                    pos = ws(pos + 1)
            pos += 1
        elif text[pos] == '[':
            value = []
            pos = ws(pos + 1)
            if text[pos] != ']':
                while True:
                    child, pos = parse(pos, pointer(path, len(value)))
                    value.append(child)
                    pos = ws(pos)
                    if text[pos] == ']':
                        break
                    require(text[pos] == ',', 'Expected JSON array comma')
                    pos = ws(pos + 1)
            pos += 1
        else:
            value, pos = decoder.raw_decode(text, pos)
        spans[path] = (start, pos, value)
        return value, pos
    _, end = parse(prefix, '')
    require(ws(end) == len(text), 'Trailing JSON data')
    return text, spans


def replace_tokens(raw, replacements):
    text, spans = token_spans(raw)
    edits = []
    for path, value in replacements.items():
        require(path in spans, f'Missing normalized metadata pointer: {path}')
        start, end, old = spans[path]
        edits.append((start, end, json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))))
    edits.sort(reverse=True)
    previous = len(text) + 1
    for start, end, value in edits:
        require(end <= previous, 'Overlapping token replacements')
        text = text[:start] + value + text[end:]
        previous = start
    return text.encode('utf-8')


def date_value(value, location):
    require(isinstance(value, str) and bool(value), f'Missing timestamp: {location}')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(stamp.tzinfo is not None, f'Naive timestamp: {location}')


def record_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f'Not regular file: {path}')
    return {'sizeBytes': path.stat().st_size, 'sha256': sha(path)}


def source_manifest(root):
    """Bind exact production project/source files, excluding generated builds/tests."""
    root = Path(root)
    paths = set()
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(x in {'bin', 'obj', '.git', '__pycache__', 'validation', 'benchmark_history'} or x.endswith('.Tests') for x in relative.parts):
            continue
        if path.is_file() and path.suffix.lower() in {'.cs', '.csproj', '.props', '.targets'}:
            paths.add(path)
    require(paths, 'No production sources found')
    return {str(p.relative_to(root)): record_file(p) for p in sorted(paths)}


def binary_manifest(directory):
    directory = Path(directory)
    return {str(p.relative_to(directory)): record_file(p) for p in sorted(directory.rglob('*')) if p.is_file()}


def verify_artifact(path, size, checksum):
    actual = record_file(path)
    require(actual['sizeBytes'] == size, f'Artifact size mismatch: {path}')
    require(isinstance(checksum, str) and re.fullmatch('[0-9a-f]{64}', checksum) is not None, f'Malformed hash: {path}')
    require(actual['sha256'] == checksum, f'Artifact checksum mismatch: {path}')
    return actual


def canonical_state(raw):
    state = strict_json(raw)
    date_value(state['CreatedUtc'], 'calibration.CreatedUtc')
    unsigned = replace_tokens(raw, {'/PayloadHash':''})
    require(digest(unsigned) == state['PayloadHash'], 'Calibration raw payload checksum mismatch')
    normalized_unsigned = replace_tokens(raw, {'/CreatedUtc':'<timestamp>', '/PayloadHash':''})
    return replace_tokens(normalized_unsigned, {'/PayloadHash':digest(normalized_unsigned)})


def raw_token(raw, pointer):
    text, spans = token_spans(raw)
    start, end, _ = spans[pointer]
    return text[start:end].encode('utf-8')


def checkpoint(path):
    """Independent archive, checksum, request and completed-unit inspection."""
    with zipfile.ZipFile(path) as archive:
        require(sorted(archive.namelist()) == ['SHA256SUMS.txt', 'backup.json'], 'Unexpected checkpoint entries')
        require(all(i.file_size <= 64 * 1024 * 1024 for i in archive.infolist()), 'Checkpoint expansion bound')
        raw = archive.read('backup.json')
        require(archive.read('SHA256SUMS.txt').decode('utf-8').strip() == digest(raw) + '  backup.json', 'Checkpoint archive checksum differs')
    doc = strict_json(raw)
    require(doc['RequestHash'] == digest(raw_token(raw, '/Request')), 'Checkpoint request checksum differs')
    require(doc['Schema'] == 1 and doc['Implementation'] == 'portable-checkpoints-1', 'Checkpoint schema differs')
    require(doc['Request']['Kind'] in KINDS, 'Checkpoint kind differs')
    require(doc['CalculationComplete'] is True and set(doc['Units']) == {'result'}, 'Expected completed-result fixture, not unfinished work')
    require(isinstance(doc['Environments'], list) and doc['Environments'], 'Fixture environment history missing')
    date_value(doc['SavedUtc'], 'checkpoint.SavedUtc')
    return {'document': doc, 'raw': raw, 'request': raw_token(raw, '/Request'), 'result': raw_token(raw, '/Units/result')}


def plan_path():
    return ROOT / 'round34-plan.json'


def fixture_manifest():
    return read_json(ROOT / 'fixtures/manifest.json')


def check_fixtures():
    items = fixture_manifest()['fixtures']
    require([x['id'] for x in items] == list(KINDS), 'Fixture order/kinds differ')
    result = {}
    for item in items:
        path = ROOT / 'fixtures' / item['file']
        require(Path(item['file']).name == item['file'], 'Unsafe fixture path')
        require(record_file(path) == {k: item[k] for k in ('sizeBytes', 'sha256')}, 'Frozen checkpoint identity changed: ' + item['id'])
        checked = checkpoint(path)
        doc = checked['document']
        require(doc['Request']['Kind'] == item['id'], 'Fixture kind mismatch')
        require(doc['RequestHash'] == item['requestHash'] and doc['Id'] == item['backupId'], 'Fixture request/id mismatch')
        require(doc['Environments'] == item['environmentHistory'], 'Fixture original environment history differs')
        require(item['calculationComplete'] is True and item['unitKeys'] == ['result'], 'Fixture completed/cache declaration missing')
        result[item['id']] = checked
    return result


def freeze(args):
    require(sys.platform == 'linux' and hasattr(os, 'wait4'), 'Linux wait4 is required')
    plan = read_json(plan_path())
    require(plan['execution']['pairOrder'] == ['AB', 'BA', 'AB'], 'Unplanned pair order')
    require(plan['execution']['environment'].get('MVS_DISABLE_BACKUPS') is None, 'Restore must remain enabled')
    require(plan['execution']['measuredProcesses'] == 30, 'Unplanned invocation count')
    require(sha(ROOT/'fixtures/manifest.json') == plan['fixtureManifestSha256'], 'Plan fixture manifest identity differs')
    check_fixtures()
    dotnet = Path(args.dotnet).resolve()
    require(dotnet.is_file(), 'Missing dotnet host')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    require(len(cpus) == 2, 'Two CPUs required')
    libraries = sorted((dotnet.parent / 'shared/Microsoft.NETCore.App').glob('*/libcoreclr.so'))
    require(libraries, 'Missing CoreCLR')
    builds = {}
    for label, key, supplied in [('A', 'baselineSource', args.baseline_binary), ('B', 'candidateSource', args.candidate_binary)]:
        source = Path(plan[key]).resolve()
        entrypoint = Path(supplied).resolve() if supplied else source / 'MvsAnalyzer.Cli/bin/Release/net8.0/mvs.dll'
        require(entrypoint.is_file() and entrypoint.name == 'mvs.dll', 'Missing CLI entrypoint ' + label)
        builds[label] = {'sourceRoot': str(source), 'sourceFiles': source_manifest(source), 'entrypoint': str(entrypoint),
                         'binaryDirectory': str(entrypoint.parent), 'binaryFiles': binary_manifest(entrypoint.parent)}
    environment = {'PATH': str(dotnet.parent) + ':/usr/bin:/bin', 'DOTNET_ROOT': str(dotnet.parent), **plan['execution']['environment']}
    binding = {'schema': 'mvs-round34-resume-binding/v1', 'boundUtc': now(), 'planSha256': sha(plan_path()),
               'driverSha256': sha(__file__), 'fixtureManifest': record_file(ROOT/'fixtures/manifest.json'),
               'fixtureFiles': {x['file']: record_file(ROOT/'fixtures'/x['file']) for x in fixture_manifest()['fixtures']},
               'builds': builds, 'dotnetHost': {'path': str(dotnet), **record_file(dotnet)},
               'coreclrFiles': {str(p): record_file(p) for p in libraries}, 'cpuAffinity': cpus,
               'baseEnvironment': environment, 'platform': platform.platform(), 'python': sys.version,
               'pythonExecutable': sys.executable}
    dump_new(ROOT/'binding.json', binding)
    print(json.dumps({'binding': str(ROOT/'binding.json'), 'sha256': sha(ROOT/'binding.json')}))
    return 0


def check_binding(binding):
    require(sha(plan_path()) == binding['planSha256'], 'Frozen plan changed')
    require(sha(__file__) == binding['driverSha256'], 'Frozen driver changed')
    require(record_file(ROOT/'fixtures/manifest.json') == binding['fixtureManifest'], 'Fixture manifest changed')
    require(sha(ROOT/'fixtures/manifest.json') == read_json(plan_path())['fixtureManifestSha256'], 'Plan fixture manifest identity differs')
    check_fixtures()
    for name, identity in binding['fixtureFiles'].items():
        require(record_file(ROOT/'fixtures'/name) == identity, 'Fixture changed: ' + name)
    host = binding['dotnetHost']
    require(record_file(host['path']) == {k: host[k] for k in ('sizeBytes','sha256')}, 'dotnet host changed')
    for path, identity in binding['coreclrFiles'].items():
        require(record_file(path) == identity, 'CoreCLR changed')
    for label, build in binding['builds'].items():
        require(source_manifest(build['sourceRoot']) == build['sourceFiles'], 'Sources changed: ' + label)
        require(binary_manifest(build['binaryDirectory']) == build['binaryFiles'], 'Binaries changed: ' + label)


def environment(binding, folder):
    env = dict(binding['baseEnvironment'])
    require('MVS_DISABLE_BACKUPS' not in env, 'Restore/cache bypass forbidden')
    for key, sub in [('HOME', 'home'), ('TMPDIR', 'tmp'), ('MVS_APPDATA_ROOT', 'appdata'), ('MVS_BACKUP_DIR', 'backups')]:
        directory = folder / sub
        directory.mkdir()
        env[key] = str(directory)
    return env


def _sample_process(pid, cpus, rss_limit, observed):
    """Watchdog-only observation. Never used to determine the main wait completion."""
    try:
        if sorted(os.sched_getaffinity(pid)) != cpus:
            return 'affinity_changed'
        status = Path(f'/proc/{pid}/status').read_text()
        match = re.search(r'^VmRSS:\s+(\d+) kB', status, re.M)
        rss = int(match.group(1)) if match else 0
        observed['sampledPeakRssKiB'] = max(observed['sampledPeakRssKiB'], rss)
        for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
            if line.endswith('/libcoreclr.so'):
                observed['coreclrPaths'].add(line.split()[-1])
        return 'rss_limit' if rss > rss_limit * 1024 else None
    except (FileNotFoundError, ProcessLookupError):
        return None


def _kill_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False


def _watchdog(pid, done, started_ns, cpus, timeout, rss_limit, interval, observed):
    """Independent bounded watchdog; a slow sample cannot bias elapsed child time."""
    try:
        while not done.is_set():
            elapsed = (time.perf_counter_ns() - started_ns) / 1e9
            violation = 'timeout' if elapsed >= timeout else _sample_process(pid, cpus, rss_limit, observed)
            if violation and not done.is_set():
                killed = _kill_group(pid)
                observed['forcedKill'] |= killed
                observed['events'].append({'type': violation, 'elapsedSeconds': elapsed, 'signal': 'SIGKILL', 'signalSent': killed})
                return
            # The timer deadline remains bounded independently of the sampling interval.
            done.wait(max(0.0, min(interval, timeout - elapsed)))
    except BaseException as exc:
        observed['events'].append({'type': 'watchdog_error', 'error': type(exc).__name__ + ': ' + str(exc)})
        observed['forcedKill'] |= _kill_group(pid)


def execute(command, directory, env, cpus, timeout, rss_limit, interval=0.02):
    """Exactly one wait4 owner, blocking wait, exact-child rusage, no exit polling.

    Capture files are opened before starting the timer. The elapsed endpoint is
    captured immediately when wait4 returns, BEFORE any Event.set or thread join.
    Launch errors and interruption cleanup return retained machine-readable records.
    """
    # Strict JSON preserves numeric decimals; threading timeouts require native floats.
    # Convert only operational timer bounds, never scientific payload numbers.
    timeout, interval = float(timeout), float(interval)
    require(timeout > 0 and interval > 0, 'Positive watchdog bounds required')
    observed = {'events': [], 'forcedKill': False, 'sampledPeakRssKiB': 0, 'coreclrPaths': set()}
    done = threading.Event()
    process = None
    watchdog = None
    watchdog_started = False
    cleanup_errors = []
    usage = None
    code = None
    error = None
    reaped = False
    def setup():
        os.sched_setaffinity(0, set(cpus))
    with (directory/'stdout.json').open('xb') as stdout, (directory/'stderr.log').open('xb') as stderr:
        started_ns = time.perf_counter_ns()
        try:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=directory, env=env,
                                       start_new_session=True, preexec_fn=setup)
            watchdog = threading.Thread(target=_watchdog, name='resume-comparison-watchdog', daemon=True,
                                        args=(process.pid, done, started_ns, cpus, timeout, rss_limit, interval, observed))
            watchdog.start()
            watchdog_started = True
            while True:
                try:
                    pid, status, usage = os.wait4(process.pid, 0)
                    ended_ns = time.perf_counter_ns()  # Must remain first operation after wait4 return.
                    break
                except InterruptedError:
                    continue
            require(pid == process.pid, 'wait4 returned wrong child')
            reaped = True
            code = os.waitstatus_to_exitcode(status)
            process.returncode = code  # Popen must never reap again.
        except BaseException as exc:
            ended_ns = time.perf_counter_ns()
            error = {'type': type(exc).__name__, 'message': str(exc)}
            observed['events'].append({'type': 'launch_error' if process is None else 'runner_error', 'error': error})
            if process is not None and not reaped:
                try:
                    observed['forcedKill'] |= _kill_group(process.pid)
                except BaseException as cleanup:
                    cleanup_errors.append({'action': 'kill_process_group', 'type': type(cleanup).__name__, 'message': str(cleanup)})
                while True:
                    try:
                        pid, status, usage = os.wait4(process.pid, 0)
                        ended_ns = time.perf_counter_ns()
                        reaped = pid == process.pid
                        if reaped:
                            code = os.waitstatus_to_exitcode(status)
                            process.returncode = code
                        else:
                            cleanup_errors.append({'action': 'reap', 'type': 'WrongChild', 'message': str(pid)})
                        break
                    except InterruptedError:
                        continue
                    except BaseException as cleanup:
                        ended_ns = time.perf_counter_ns()
                        cleanup_errors.append({'action': 'reap', 'type': type(cleanup).__name__, 'message': str(cleanup)})
                        break
                if cleanup_errors:
                    observed['events'].append({'type': 'cleanup_failure', 'errors': cleanup_errors})
        finally:
            done.set()
            if watchdog is not None and watchdog_started:
                watchdog.join(timeout=2.0)
                if watchdog.is_alive():
                    observed['events'].append({'type': 'watchdog_join_timeout'})
        elapsed = (ended_ns - started_ns) / 1e9
    return {'pid': process.pid if process else None, 'returncode': code, 'wallSeconds': elapsed,
            'cpuUserSeconds': usage.ru_utime if usage else None, 'cpuSystemSeconds': usage.ru_stime if usage else None,
            'cpuTotalSeconds': usage.ru_utime + usage.ru_stime if usage else None, 'peakRssKiB': usage.ru_maxrss if usage else None,
            'minorFaults': usage.ru_minflt if usage else None, 'majorFaults': usage.ru_majflt if usage else None,
            'sampledPeakRssKiB': observed['sampledPeakRssKiB'], 'coreclrPaths': sorted(observed['coreclrPaths']),
            'events': observed['events'], 'forcedKill': observed['forcedKill'], 'reaped': reaped, 'runnerError': error, 'cleanupErrors': cleanup_errors,
            'interrupted': error is not None and error['type'] in ('KeyboardInterrupt', 'SystemExit'),
            'timer': 'perf_counter_ns: immediately before Popen to immediately after blocking wait4(pid,0)',
            'rusage': 'exact child wait4, Linux ru_maxrss KiB'}


def inspect_saved_backup(folder, source):
    primary = list((folder/'backups').glob('*.mvsbackup'))
    primary = [p for p in primary if not p.name.endswith('.previous.mvsbackup')]
    require(len(primary) == 1, 'One real resumed-session primary backup required')
    saved = checkpoint(primary[0])
    original, current = source['document'], saved['document']
    for key in ('Id', 'RequestHash', 'Schema', 'Implementation', 'Application', 'Engine', 'Formula', 'Protocol', 'OriginJob'):
        require(original[key] == current[key], 'Resumed backup changed ' + key)
    require(source['request'] == saved['request'], 'Resumed request bytes changed')
    require(source['result'] == saved['result'], 'Cached completed result bytes changed')
    history = original['Environments']
    require(current['Environments'][:len(history)] == history, 'Original environment history was rewritten')
    require(len(current['Environments']) in (len(history), len(history)+1), 'Unexpected environment transitions')
    require(current['SavedUtc'] != original['SavedUtc'], 'No real session publication observed')
    normalized = replace_tokens(saved['raw'], {'/SavedUtc': '<session-save-timestamp>'})
    return {'file': str(primary[0].relative_to(folder)), **record_file(primary[0]),
            'requestHash': current['RequestHash'], 'retainedUnitKeys': sorted(current['Units']),
            'completedResultExactBytesRetained': True, 'environmentHistory': current['Environments'],
            'normalizedDocument': normalized}


def inspect_run(folder, fixture, source):
    record = read_json(folder/'record.json')
    require(record['returncode'] in fixture['expectedExit'], 'Unexpected process exit: ' + str(record['returncode']))
    require(record['reaped'] and not record['forcedKill'] and not record['events'], 'Process lifecycle/watchdog violation')
    for filename, key in [('stdout.json','stdout'), ('stderr.log','stderr')]:
        require(record_file(folder/filename) == record[key], 'Retained raw capture changed: ' + filename)
    raw = (folder/'stdout.json').read_bytes()
    payload = strict_json(raw)
    require(payload['schemaVersion'] == 'mvs-cli-result/v1' and payload['command'] == 'resume', 'Machine resume schema/command differs')
    require(payload['exitCode'] == record['returncode'], 'Machine/process exit differs')
    require(payload['status'] == {0:'completed', 2:'diagnostic'}[record['returncode']], 'Machine status differs')
    require(payload['execution']['completed'] is True and payload['error'] is None, 'Run incomplete')
    require(payload['engineVersion'] == '1.6.2' and payload['scientificReadiness']['status'] == 'no_go', 'Scientific identity/readiness differs')
    output = Path(payload['outputDirectory']).resolve()
    requested = (folder/'output').resolve()
    require(output.is_relative_to(requested) and output != requested, 'Resume output escaped its fresh parent')
    require(output.is_dir() and not output.is_symlink(), 'Output directory missing')
    entries = list(output.iterdir())
    require(all(p.is_file() and not p.is_symlink() for p in entries), 'Unexpected output member')
    actual = {p.name:p for p in entries}
    require(set(actual) == set(fixture['artifacts']), 'Output file set differs: ' + str(sorted(actual)))
    artifacts = payload['artifacts']
    names = [a['name'] for a in artifacts]
    require(len(names) == len(set(names)) and set(names) == set(actual), 'Machine artifact identity differs')
    identities = {}
    for item in artifacts:
        name = item['name']
        path = Path(item['path'])
        require(path.is_absolute() and path.resolve() == actual[name].resolve(), 'Machine artifact path differs')
        identities[name] = verify_artifact(path, item['sizeBytes'], item['sha256'])
    saved = inspect_saved_backup(folder, source)
    provenance = strict_json(actual['backup_resume.json'].read_bytes())
    doc = source['document']
    require(provenance['backupId'] == doc['Id'] and provenance['requestHash'] == doc['RequestHash'], 'Resume provenance identity differs')
    require(provenance['retainedUnits'] == len(doc['Units']), 'Resume retained-unit count differs')
    require(datetime.fromisoformat(provenance['resumedFromUtc'].replace('Z','+00:00')) == datetime.fromisoformat(doc['SavedUtc'].replace('Z','+00:00')), 'Original checkpoint timestamp differs')
    require(provenance['environments'] == saved['environmentHistory'], 'Resume provenance environment history differs')
    normalized = {}
    for name, path in actual.items():
        if name == 'run_manifest.json':
            continue
        content = path.read_bytes()
        if name == 'calibration_state.json':
            content = canonical_state(content)
        elif name.endswith('.json'):
            strict_json(content)
        elif name.endswith('.csv'):
            list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
        normalized[name] = content
    if 'run_manifest.json' in actual:
        manifest_raw = actual['run_manifest.json'].read_bytes()
        manifest = strict_json(manifest_raw)
        require(Path(payload['manifestPath']).resolve() == actual['run_manifest.json'].resolve(), 'Machine manifest association differs')
        date_value(manifest['created'], 'manifest.created')
        require(isinstance(manifest['runId'], str) and manifest['runId'], 'Manifest runId missing')
        require(payload['runId'] == manifest['runId'], 'Machine/manifest runId differs')
        files = manifest['files']
        names = [f['FileName'] for f in files]
        require(len(names) == len(set(names)) and set(names) == set(actual)-{'run_manifest.json'}, 'Manifest artifact membership differs')
        changes = {'/created':'<timestamp>', '/runId':'<run-id>'}
        for index, item in enumerate(files):
            name = item['FileName']
            verify_artifact(actual[name], item['SizeBytes'], item['sha256'])
            changes[f'/files/{index}/sha256'] = digest(normalized[name])
            changes[f'/files/{index}/SizeBytes'] = len(normalized[name])
        normalized['run_manifest.json'] = replace_tokens(manifest_raw, changes)
    else:
        require(payload['manifestPath'] is None and payload['runId'] is None, 'Calibration invented manifest/runId')
    changes = {'/outputDirectory':'<output>', '/manifestPath':'<output>/run_manifest.json' if payload['manifestPath'] else None,
               '/runId':'<run-id>' if payload['runId'] else None}
    for index, item in enumerate(artifacts):
        name = item['name']
        changes[f'/artifacts/{index}/path'] = '<output>/' + name
        changes[f'/artifacts/{index}/sha256'] = digest(normalized[name])
        changes[f'/artifacts/{index}/sizeBytes'] = len(normalized[name])
    normalized['stdout.json'] = replace_tokens(raw, changes)
    # Entire restored state must remain exact except its actual session publication time.
    normalized['resumed_checkpoint.json'] = saved.pop('normalizedDocument')
    return {'record': record, 'artifacts': identities, 'normalized': normalized, 'savedBackup': saved, 'status': payload['status']}
def planned_invocations(plan, fixtures):
    for fixture in fixtures:
        for pair, order in enumerate(plan['execution']['pairOrder'], 1):
            for position, label in enumerate(order, 1):
                yield fixture, {'id': f'{fixture["id"]}-pair{pair}-{position}-{label}', 'workload': fixture['id'],
                                'pair': pair, 'position': position, 'build': label}


def summary(values):
    valid = [v for v in values if v is not None]
    return {'values': values, 'available': len(valid), 'median': statistics.median(valid) if valid else None,
            'min': min(valid) if valid else None, 'max': max(valid) if valid else None}


def _comparison(reference, actual):
    different = sorted(name for name in set(reference['normalized']) | set(actual['normalized'])
                       if reference['normalized'].get(name) != actual['normalized'].get(name))
    same = reference['record']['returncode'] == actual['record']['returncode'] and reference['status'] == actual['status']
    return {'reference': reference['record']['id'], 'actual': actual['record']['id'],
            'exactNormalizedBytesEqual': not different, 'differentFiles': different, 'statusExitEqual': same}


def report_from_retained(plan, binding):
    """Pure reader. All normalization stays in memory; never creates missing evidence."""
    sources = check_fixtures()
    fixtures = fixture_manifest()['fixtures']
    destination = ROOT/'execution'
    finished = read_json(destination/'finished.json')
    require(finished['invocations'] == 30, 'Execution is not a completed 30-attempt comparison')
    all_records, reports, errors, normalized_outputs = [], [], [], {}
    for fixture in fixtures:
        inspected, records, local_errors = {}, [], []
        for _, expected in planned_invocations(plan, [fixture]):
            folder = destination/expected['id']
            try:
                record = read_json(folder/'record.json')
                for key, value in expected.items():
                    require(record[key] == value, 'Invocation order/binding differs: ' + key)
                records.append(record)
                all_records.append(record)
                item = inspect_run(folder, fixture, sources[fixture['id']])
                require(set(item['record']['coreclrPaths']).issubset(binding['coreclrFiles']), 'Unbound runtime observation')
                inspected[expected['id']] = item
                normalized_outputs[expected['id']] = item['normalized']
            except Exception as exc:
                local_errors.append({'invocation': expected['id'], 'error': type(exc).__name__ + ': ' + str(exc)})
        comparisons, paired = [], []
        if len(inspected) == 6:
            items = list(inspected.values())
            comparisons = [_comparison(items[0], item) for item in items[1:]]
            for pair in range(1, 4):
                matched = {x['record']['build']: x for x in items if x['record']['pair'] == pair}
                paired.append({'pair': pair, **_comparison(matched['A'], matched['B'])})
            for comparison in comparisons + paired:
                if not comparison['exactNormalizedBytesEqual'] or not comparison['statusExitEqual']:
                    local_errors.append({'invocation': comparison['actual'], 'error': 'Exact parity mismatch', 'differentFiles': comparison['differentFiles']})
        performance = {}
        for metric in METRICS:
            by_build = {label: [next((r.get(metric) for r in records if r['pair'] == pair and r['build'] == label), None)
                                for pair in (1,2,3)] for label in ('A','B')}
            a, b = by_build['A'], by_build['B']
            a = [float(v) if v is not None else None for v in a]
            b = [float(v) if v is not None else None for v in b]
            ratios = [bb/aa if aa is not None and bb is not None and aa != 0 else None for aa,bb in zip(a,b)]
            sa, sb = summary(a), summary(b)
            performance[metric] = {'A': sa, 'B': sb, 'pairedBOverA': summary(ratios),
                                   'medianBOverMedianA': sb['median']/sa['median'] if sa['median'] and sb['median'] is not None else None}
        reports.append({'workload': fixture['id'], 'passed': len(inspected)==6 and not local_errors,
                        'invocations': len(records), 'fixtureClass': 'completed_result_cached_engineering_export',
                        'comparisonsToFirstBaseline': comparisons, 'pairedComparisons': paired, 'errors': local_errors,
                        'performance': performance,
                        'artifacts': [{'invocation': name, 'actual': item['artifacts'], 'savedBackup': item['savedBackup'],
                                       'normalized': {n:{'sha256':digest(b),'sizeBytes':len(b)} for n,b in item['normalized'].items()}}
                                      for name,item in inspected.items()]})
        errors.extend(local_errors)
    require(len(all_records) == 30, 'Retained record count differs from 30')
    report = {'schema': 'mvs-round34-resume-comparison/v1', 'planSha256': sha(plan_path()), 'bindingSha256': sha(ROOT/'binding.json'),
              'driverSha256': sha(__file__), 'fixtureManifestSha256': sha(ROOT/'fixtures/manifest.json'),
              'scientificReleaseDecision': 'NO-GO retained', 'scope': plan['scope'], 'invocationCount': len(all_records),
              'passed': not errors and all(w['passed'] for w in reports), 'workloads': reports,
              'allRawMeasurements': all_records, 'errors': errors, 'limitations': plan['performance']['limitations']}
    return report, normalized_outputs


def inventory(root):
    return {str(p.relative_to(root)): record_file(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.name != 'evidence-sha256.json' and '__pycache__' not in p.parts}


def summary_text(report):
    lines = ['Round34 completed-cache CLI resume/export comparison',
             f'Exact scientific output/status parity: {report["passed"]}; retained attempts: {report["invocationCount"]}/30.',
             'Three matched pairs per workload, AB/BA/AB. Every attempt retained, including failures.',
             'Wall: blocking wait4 with immediate monotonic endpoint; independent watchdog. CPU/RSS: exact child rusage.',
             'These are completed-result cached engineering fixtures, not unfinished scientific recomputation.', '']
    for workload in report['workloads']:
        lines.append(workload['workload'] + ': parity ' + str(workload['passed']))
        for metric, data in workload['performance'].items():
            lines.append('  '+metric+': '+json.dumps(data, allow_nan=False))
    lines.extend(['', 'Descriptive process cost only. No speed, independent scientific correctness, or publication-readiness claim.',
                  'Existing scientific NO-GO remains. Genuine unfinished checkpoint regression is separate.'])
    return '\n'.join(lines)+'\n'


def publish_report(plan, binding):
    """Only run may publish initial evidence. verify is a separate read-only path."""
    report, normalized = report_from_retained(plan, binding)
    destination = ROOT/'execution'
    for name, artifacts in normalized.items():
        folder = destination/name/'normalized'
        folder.mkdir(exist_ok=False)
        for filename, content in artifacts.items():
            with (folder/filename).open('xb') as stream:
                stream.write(content)
    dump_new(destination/'comparison-results.json', report)
    with (destination/'comparison-summary.txt').open('x') as stream:
        stream.write(summary_text(report))
    dump_new(destination/'evidence-sha256.json', inventory(destination))
    return report


def run(args):
    require(args.approved_exclusive_window, 'Lead exclusive GO and --approved-exclusive-window required')
    binding = read_json(ROOT/'binding.json')
    plan = read_json(plan_path())
    check_binding(binding)
    require(set(binding['cpuAffinity']).issubset(os.sched_getaffinity(0)), 'Frozen CPUs unavailable')
    destination = ROOT/'execution'
    destination.mkdir(exist_ok=False)
    shutil.copyfile(ROOT/'binding.json', destination/'binding.json')
    shutil.copyfile(plan_path(), destination/'plan.json')
    shutil.copyfile(ROOT/'fixtures/manifest.json', destination/'fixtures-manifest.json')
    dump_new(destination/'started.json', {'startedUtc': now(), 'bindingSha256': sha(ROOT/'binding.json'), 'driverSha256': sha(__file__)})
    (destination/'host-before.txt').write_text(platform.platform()+'\n'+Path('/proc/loadavg').read_text()+Path('/proc/cpuinfo').read_text())
    records = []
    try:
        for fixture, context in planned_invocations(plan, fixture_manifest()['fixtures']):
            check_binding(binding)
            folder = destination/context['id']
            folder.mkdir()
            env = environment(binding, folder)
            command = [binding['dotnetHost']['path'], binding['builds'][context['build']]['entrypoint'],
                       'resume', '--in', str(ROOT/'fixtures'/fixture['file']), '--out', str(folder/'output'), '--json', '--quiet']
            context = {**context, 'command': command, 'environment': env, 'cpuAffinity': binding['cpuAffinity'],
                       'fixture': {k: fixture[k] for k in ('file','sha256','sizeBytes','requestHash','backupId')}, 'startedUtc': now()}
            dump_new(folder/'invocation.json', context)
            print('RUN '+context['id'], flush=True)
            result = execute(command, folder, env, binding['cpuAffinity'], plan['execution']['timeoutSeconds'],
                             plan['execution']['rssLimitMiB'], plan['execution']['watchdogPollSeconds'])
            result = {**context, **result, 'finishedUtc': now(), 'stdout': record_file(folder/'stdout.json'), 'stderr': record_file(folder/'stderr.log')}
            # Retain lifecycle failure before any post-run assertion can stop the comparison.
            dump_new(folder/'record.json', result)
            records.append(result)
            with (destination/'invocations.jsonl').open('a') as stream:
                stream.write(json.dumps(result, allow_nan=False)+'\n')
            if result['interrupted']:
                raise KeyboardInterrupt('Operator interrupted; retained this attempt and stopped remaining launches')
            require(result.get('pid') is None or result['reaped'], 'Unresolved child cleanup; retained attempt and stopped remaining launches')
            check_binding(binding)
    except BaseException as exc:
        dump_new(destination/'aborted.json', {'atUtc': now(), 'retainedAttempts': len(records), 'error': type(exc).__name__+': '+str(exc),
                                            'note': 'No replacement or cherry-picked rerun. Incomplete comparison is not a pass.'})
        raise
    dump_new(destination/'finished.json', {'finishedUtc': now(), 'invocations': len(records), 'bindingUnchanged': True})
    (destination/'host-after.txt').write_text(platform.platform()+'\n'+Path('/proc/loadavg').read_text())
    report = publish_report(plan, binding)
    print(json.dumps({'passed': report['passed'], 'invocations': len(records), 'report': str(destination/'comparison-results.json')}))
    return 0 if report['passed'] else 2


def verify(args):
    """Read-only verification: no mkdir, open-for-write, publish, model, or repair."""
    binding = read_json(ROOT/'binding.json')
    check_binding(binding)
    destination = ROOT/'execution'
    require(read_json(destination/'binding.json') == binding, 'Retained binding differs')
    require(read_json(destination/'plan.json') == read_json(plan_path()), 'Retained plan differs')
    require(read_json(destination/'fixtures-manifest.json') == fixture_manifest(), 'Retained fixture manifest differs')
    report, normalized = report_from_retained(read_json(plan_path()), binding)
    require(read_json(destination/'comparison-results.json') == strict_json(json.dumps(report, default=float)), 'Saved report differs from recomputation')
    require((destination/'comparison-summary.txt').read_text() == summary_text(report), 'Saved summary differs')
    for name, artifacts in normalized.items():
        folder = destination/name/'normalized'
        require(folder.is_dir(), 'Missing normalized evidence; verify never repairs')
        require({p.name:p.read_bytes() for p in folder.iterdir()} == artifacts, 'Saved normalized evidence differs')
    require(read_json(destination/'evidence-sha256.json') == inventory(destination), 'Evidence inventory differs')
    print(json.dumps({'passed': report['passed'], 'invocations': report['invocationCount'], 'readOnly': True,
                      'report': str(destination/'comparison-results.json'), 'errors': report['errors']}))
    return 0 if report['passed'] else 2


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Evidence root containing round34-plan.json and fixtures/')
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('freeze')
    p.add_argument('--dotnet', default='/workspace/scratch/8105054a3211/mvs_r22_baseline/sdk/dotnet')
    p.add_argument('--baseline-binary')
    p.add_argument('--candidate-binary')
    p.set_defaults(func=freeze)
    p = sub.add_parser('run')
    p.add_argument('--approved-exclusive-window', action='store_true')
    p.set_defaults(func=run)
    sub.add_parser('verify').set_defaults(func=verify)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
