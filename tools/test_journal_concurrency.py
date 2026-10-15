#!/usr/bin/env python3
"""Bounded isolated actual-process journal integrity audit; retain every outcome."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'validation/journal-concurrency-v1.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2); stream.write('\n')


def verify_chain(path, expected_ids):
    errors, ids, previous = [], [], 'genesis'
    if not path.is_file():
        return {'passed': False, 'errors': ['journal missing'], 'entries': 0}
    raw = path.read_bytes()
    if not raw.endswith(b'\n'):
        errors.append('missing final newline')
    for i, line in enumerate(raw.splitlines()):
        try:
            item = json.loads(line)
            ids.append(item['runId'])
            if item.get('previous') != previous:
                errors.append(f'chain mismatch at line {i+1}')
        except (ValueError, KeyError, TypeError) as error:
            errors.append(f'line {i+1}: {type(error).__name__}')
        previous = hashlib.sha256(line).hexdigest()
    if len(ids) != len(expected_ids) or set(ids) != set(expected_ids) or len(set(ids)) != len(ids):
        errors.append('missing, unexpected or duplicate IDs')
    return {'passed': not errors, 'errors': errors, 'entries': len(ids), 'ids': ids, 'sha256': sha(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--dotnet', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    if not hasattr(os, 'sched_setaffinity'):
        parser.error('Linux affinity and /proc required')
    protocol = json.loads(PROTOCOL.read_text())
    root = args.artifacts.resolve(); root.mkdir(parents=True, exist_ok=False)
    probe = args.probe.resolve(); dotnet = args.dotnet.resolve()
    cpus = sorted(os.sched_getaffinity(0))[:protocol['cpuAffinityCount']]
    (root / 'protocol.json').write_bytes(PROTOCOL.read_bytes())
    (root / 'runner.py').write_bytes(Path(__file__).read_bytes())
    (root / 'RunAuditor.cs').write_bytes((ROOT / 'Infrastructure/RunAuditor.cs').read_bytes())
    (root / 'RunAuditorProcessProbe.cs').write_bytes((ROOT / 'MvsAnalyzer.Core.Tests/RunAuditorProcessProbe.cs').read_bytes())
    write_new(root / 'freeze.json', {'utc': datetime.now(timezone.utc).isoformat(), 'protocolSha256': sha(PROTOCOL),
              'runnerSha256': sha(Path(__file__)), 'probeSha256': sha(probe), 'coreSha256': sha(probe.with_name('MvsAnalyzer.Core.dll')),
              'cpuAffinity': cpus, 'scope': 'Synthetic bounded local journal audit, no statistical procedure or user journal'})
    scenarios = []

    def scenario_dir(name):
        folder = root / name; folder.mkdir()
        for sub in ('data', 'reports'):
            (folder / sub).mkdir()
        return folder

    def start(folder, name, mode, gate, **settings):
        job = folder / name; job.mkdir()
        disable_locking = settings.pop('disableLocking', None)
        request = dict(mode=mode, output=str(job / 'result.json'), ready=str(job / 'ready'),
                       gate=str(gate), auditRoot=str(folder / 'reports'), **settings)
        write_new(job / 'request.json', request)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('MVS_', 'DOTNET_', 'COMPlus_'))}
        env.update(DOTNET_ROOT=str(dotnet.parent), DOTNET_PROCESSOR_COUNT='1', MVS_DISABLE_BACKUPS='1',
                   DOTNET_CLI_TELEMETRY_OPTOUT='1', XDG_DATA_HOME=str(folder / 'data'))
        if disable_locking is not None:
            env['DOTNET_SYSTEM_IO_DISABLEFILELOCKING'] = disable_locking
        stdout, stderr = (job / 'stdout.txt').open('wb'), (job / 'stderr.txt').open('wb')
        argv = [str(dotnet), str(probe), '--journal-process-probe', str(job / 'request.json')]
        child = subprocess.Popen(argv, cwd=folder, env=env, stdout=stdout, stderr=stderr,
                                 start_new_session=settings.pop('newSessions', False) if 'newSessions' in settings else False,
                                 preexec_fn=lambda: os.sched_setaffinity(0, set(cpus)))
        return {'process': child, 'job': job, 'handles': [stdout, stderr], 'started': time.monotonic(), 'argv': argv,
                'rssSamples': 0, 'maxRssKiB': 0}

    def tick(children):
        rss = 0
        for child in children:
            process = child['process']
            if process.poll() is not None:
                continue
            if time.monotonic() - child['started'] > protocol['processTimeoutSeconds']:
                raise TimeoutError('Native probe exceeded frozen deadline')
            try:
                values = dict(line.split(':', 1) for line in Path(f'/proc/{process.pid}/status').read_text().splitlines() if ':' in line)
                current = int(values.get('VmRSS', '0 kB').split()[0]); rss += current
                assert sorted(os.sched_getaffinity(process.pid)) == cpus
                child['rssSamples'] += 1; child['maxRssKiB'] = max(child['maxRssKiB'], current)
            except (FileNotFoundError, ProcessLookupError):
                pass
        if rss > protocol['aggregateSampledRssLimitMiB'] * 1024:
            raise MemoryError('Aggregate sampled RSS exceeded frozen bound')

    def await_files(paths, children):
        deadline = time.monotonic() + protocol['readyTimeoutSeconds']
        while not all(p.exists() for p in paths):
            tick(children)
            if time.monotonic() > deadline:
                raise TimeoutError('Readiness gate timed out')
            if any(c['process'].poll() is not None for c in children):
                raise RuntimeError('Child exited before readiness marker')
            time.sleep(protocol['pollSeconds'])

    def finish(children):
        while any(c['process'].poll() is None for c in children):
            tick(children); time.sleep(protocol['pollSeconds'])
        results = []
        for child in children:
            for handle in child['handles']: handle.close()
            result = json.loads((child['job'] / 'result.json').read_text())
            result.update(processExit=child['process'].returncode, rssSamples=child['rssSamples'],
                          sampledPeakRssKiB=child['maxRssKiB'], argv=child['argv'])
            results.append(result)
        return results

    for spec in protocol['scenarios']:
        folder = scenario_dir(spec['id']); gate = folder / 'start'; children = []
        try:
            if spec['id'].startswith('disabled-file-locking-'):
                children.append(start(folder, 'writer', 'append', gate, writer='disabled', count=1,
                                      payloadChars=0, disableLocking=spec['value']))
                await_files([children[0]['job'] / 'ready'], children); gate.touch(exist_ok=False)
                results = finish(children)
                journal = folder / 'data/MVS_Analyzer/run_journal.jsonl'
                passed = (results[0]['processExit'] == 1 and results[0].get('errorType') == 'NotSupportedException'
                          and not journal.exists() and results[0]['elapsedSeconds'] < 5)
                detail = {'journalCreated': journal.exists(), 'expectedUnsupportedLock': True, 'processes': results}
            elif 'writers' in spec:
                for i in range(spec['writers']):
                    children.append(start(folder, f'writer-{i}', 'append', gate, writer=f'w{i}', count=spec['entriesEach'],
                                          payloadChars=spec['payloadChars'], newSessions=spec['newSessions']))
                if spec.get('readerIterations'):
                    children.append(start(folder, 'reader', 'read', gate, count=spec['readerIterations']))
                await_files([c['job'] / 'ready' for c in children], children); gate.touch(exist_ok=False)
                results = finish(children)
                expected = [f'w{i}-{j:03}' for i in range(spec['writers']) for j in range(spec['entriesEach'])]
                chain = verify_chain(folder / 'data/MVS_Analyzer/run_journal.jsonl', expected)
                findings = [f for result in results for obs in result.get('observations', []) for f in obs['journalFindings'] if f['Severity'] == 'fail']
                passed = chain['passed'] and not findings and all(r['processExit'] == 0 for r in results)
                detail = {'chain': chain, 'readerFailures': findings, 'processes': results}
            elif spec['id'].startswith('controlled-held-partial') or spec['id'] in ('owner-crash-release', 'lock-timeout'):
                finish_gate, partial = folder / 'finish-write', folder / 'partial-ready'
                children.append(start(folder, 'writer', 'held-partial', gate, partialReady=str(partial), finishGate=str(finish_gate), newSessions=spec.get('newSessions', False)))
                await_files([children[0]['job'] / 'ready'], children); gate.touch(exist_ok=False)
                await_files([partial], children)
                reading = folder / 'reading'
                children.append(start(folder, 'reader', 'read', gate, count=1, reading=str(reading), newSessions=spec.get('newSessions', False)))
                await_files([reading], children)
                if spec['id'] == 'owner-crash-release':
                    writer = children[0]
                    writer['process'].kill(); writer['process'].wait(timeout=5)
                    for handle in writer['handles']: handle.close()
                    results = finish(children[1:])
                    findings = [f for obs in results[0].get('observations', []) for f in obs['journalFindings']]
                    journal = folder / 'data/MVS_Analyzer/run_journal.jsonl'
                    passed = (results[0]['processExit'] == 0 and journal.read_bytes() == b'{' and
                              any(f['Severity'] == 'fail' and f['Code'] == 'JOURNAL_UNREADABLE' for f in findings))
                    detail = {'ownerTerminatedByTest': True, 'ownerExit': writer['process'].returncode,
                              'partialBytesPreserved': journal.read_bytes() == b'{', 'processes': results}
                elif spec['id'] == 'lock-timeout':
                    deadline = time.monotonic() + 14
                    while not (children[1]['job'] / 'result.json').exists():
                        tick(children)
                        if time.monotonic() > deadline:
                            raise TimeoutError('Reader did not report bounded lock timeout')
                        time.sleep(protocol['pollSeconds'])
                    finish_gate.touch(exist_ok=False)
                    results = finish(children)
                    reader = results[1]
                    chain = verify_chain(folder / 'data/MVS_Analyzer/run_journal.jsonl', ['held-000'])
                    passed = (reader['processExit'] == 1 and reader.get('errorType') == 'IOException'
                              and 9 <= reader['elapsedSeconds'] < 15 and chain['passed'])
                    detail = {'expectedTimeoutError': True, 'chain': chain, 'processes': results}
                else:
                    deadline = time.monotonic() + spec['observationWindowSeconds']
                    while time.monotonic() < deadline:
                        tick(children); time.sleep(protocol['pollSeconds'])
                    premature = (children[1]['job'] / 'result.json').exists()
                    finish_gate.touch(exist_ok=False)
                    results = finish(children)
                    chain = verify_chain(folder / 'data/MVS_Analyzer/run_journal.jsonl', ['held-000'])
                    reader = results[1]
                    bad = [f for obs in reader.get('observations', []) for f in obs['journalFindings'] if f['Severity'] == 'fail']
                    passed = not premature and not bad and chain['passed'] and reader.get('observations', [{}])[-1].get('JournalEntries') == 1
                    detail = {'readerCompletedBeforeWriterRelease': premature, 'readerFailures': bad, 'chain': chain, 'processes': results}
            else:
                journal = folder / 'data/MVS_Analyzer/run_journal.jsonl'; journal.parent.mkdir()
                if spec['id'] == 'malformed-json':
                    journal.write_text('{"runId":')
                    expected_code = 'JOURNAL_UNREADABLE'
                else:
                    journal.write_text(json.dumps({'runId': 'first', 'previous': 'genesis'}) + '\n' + json.dumps({'runId': 'second', 'previous': 'wrong'}) + '\n')
                    expected_code = 'JOURNAL_BROKEN'
                before = sha(journal)
                children.append(start(folder, 'reader', 'read', gate, count=1))
                await_files([children[0]['job'] / 'ready'], children); gate.touch(exist_ok=False)
                results = finish(children)
                findings = [f for result in results for obs in result.get('observations', []) for f in obs['journalFindings']]
                passed = any(f['Severity'] == 'fail' and f['Code'] == expected_code for f in findings) and before == sha(journal)
                detail = {'expectedFailureCode': expected_code, 'journalPreserved': before == sha(journal), 'processes': results}
            scenarios.append({'id': spec['id'], 'passed': passed, **detail})
        except Exception as error:
            scenarios.append({'id': spec['id'], 'passed': False, 'harnessError': type(error).__name__ + ': ' + str(error)})
        finally:
            for child in children:
                if child['process'].poll() is None:
                    child['process'].kill(); child['process'].wait(timeout=5)
                for handle in child['handles']: handle.close()
        write_new(folder / 'scenario.json', scenarios[-1])
        print(json.dumps({'id': spec['id'], 'passed': scenarios[-1]['passed'], 'harnessError': scenarios[-1].get('harnessError')}), flush=True)
    result = {'protocolId': protocol['protocolId'], 'protocolSha256': sha(PROTOCOL),
              'status': 'passed' if all(s['passed'] for s in scenarios) else 'failed', 'scenarios': scenarios,
              'scientificDecision': 'NO-GO retained', 'limitations': protocol['limits']}
    write_new(root / 'results.json', result)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
