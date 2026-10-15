#!/usr/bin/env python3
"""Opt-in actual Linux journal-path regression; retain fresh pre/post evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_python_cli import compare_analysis, strict_json


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-cli', type=Path, required=True)
    parser.add_argument('--cli', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('These actual XDG/HOME regressions require Linux.')
    root = args.artifacts.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = root / 'demo_three_groups.csv'
    shutil.copyfile(ROOT / 'examples/demo_three_groups.csv', source)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    env = {k: v for k, v in os.environ.items() if not k.startswith(('MVS_', 'DOTNET_', 'COMPlus_'))}
    env.update(DOTNET_ROOT=os.environ.get('DOTNET_ROOT', '/tmp/mvs-dotnet'),
               DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_PROCESSOR_COUNT='2', MVS_DISABLE_BACKUPS='1')
    records = []

    def invoke(cli, name, command, options, *, xdg='missing', sentinel=False):
        case = root / name
        case.mkdir()
        cwd, home = case / 'cwd', case / 'home'
        cwd.mkdir(); home.mkdir()
        data = case / 'data'
        child_env = dict(env, HOME=str(home), XDG_CONFIG_HOME=str(case / 'config'), XDG_CACHE_HOME=str(case / 'cache'))
        if xdg == 'unset':
            child_env.pop('XDG_DATA_HOME', None)
            expected_data = home / '.local/share'
        elif xdg == 'relative':
            child_env['XDG_DATA_HOME'] = 'relative-data'
            expected_data = home / '.local/share'
        else:
            child_env['XDG_DATA_HOME'] = str(data)
            expected_data = data
        if xdg == 'existing':
            data.mkdir()
        elif xdg == 'file':
            data.write_text('preserve obstruction\n')
        elif xdg == 'child-file':
            data.mkdir(); (data / 'MVS_Analyzer').write_text('preserve child obstruction\n')
        elif xdg == 'journal-directory':
            (data / 'MVS_Analyzer/run_journal.jsonl').mkdir(parents=True)
        old = cwd / 'MVS_Analyzer/run_journal.jsonl'
        before = b'unrelated legacy journal; must remain unchanged\n'
        if sentinel:
            old.parent.mkdir(); old.write_bytes(before)
        output = case / 'output'
        argv = [str(cli.resolve()), command, *options, '--out', str(output), '--json', '--quiet']
        with (case / 'stdout.json').open('wb') as stdout, (case / 'stderr.txt').open('wb') as stderr:
            process = subprocess.run(argv, cwd=cwd, env=child_env, stdout=stdout, stderr=stderr,
                                     timeout=60, preexec_fn=lambda: os.sched_setaffinity(0, set(cpus)))
        payload = strict_json(case / 'stdout.json')
        expected_exit = 1 if xdg in ('file', 'child-file') else 0
        assert process.returncode == expected_exit and payload['exitCode'] == expected_exit
        assert payload['status'] == ('error' if expected_exit else 'completed')
        if expected_exit:
            assert payload['error'] is not None and payload['artifacts'] == [] and payload['outputDirectory'] is None
        else:
            assert payload['error'] is None
        for artifact in payload['artifacts']:
            path = Path(artifact['path'])
            assert path.stat().st_size == artifact['sizeBytes'] and digest(path) == artifact['sha256']
        if sentinel:
            assert old.read_bytes() == before, 'Legacy working-directory journal changed'
        record = {'case': name, 'command': argv, 'exit': process.returncode, 'inputSha256': digest(source),
                  'expectedJournal': str(expected_data / 'MVS_Analyzer/run_journal.jsonl'),
                  'cwdJournalExists': old.exists(), 'legacySentinelPreserved': sentinel,
                  'stdoutSha256': digest(case / 'stdout.json'), 'stderr': (case / 'stderr.txt').read_text(),
                  'outputDirectory': payload['outputDirectory']}
        records.append(record)
        return Path(payload['outputDirectory']) if payload['outputDirectory'] else output, expected_data / 'MVS_Analyzer/run_journal.jsonl', case

    calibration, _, _ = invoke(args.baseline_cli, 'baseline-calibration', 'calibrate',
                               ['--in', str(source), '--repetitions', '100', '--seed', '20260719'])
    options = ['--in', str(source), '--calibration', str(calibration)]
    baseline, journal, case = invoke(args.baseline_cli, 'baseline-missing-xdg', 'analyze', options)
    assert not journal.exists() and (case / 'cwd/MVS_Analyzer/run_journal.jsonl').is_file(), 'Baseline bug was not reproduced'
    records[-1]['reproducedCwdFallback'] = True
    for mode in ('missing', 'existing', 'unset', 'relative', 'file', 'child-file', 'journal-directory'):
        output, journal, case = invoke(args.cli, 'fixed-' + mode, 'analyze', options, xdg=mode, sentinel=True)
        if mode not in ('file', 'child-file'):
            compare_analysis(baseline, output, 1e-12, 1e-10)
            records[-1]['scientificParity'] = True
        if mode in ('file', 'child-file'):
            assert not journal.is_file()
            assert 'plugins' in records[-1]['stderr'], 'Expected earlier plugin-directory obstruction'
            obstruction = case / 'data' if mode == 'file' else case / 'data/MVS_Analyzer'
            assert obstruction.read_text() == ('preserve obstruction\n' if mode == 'file' else 'preserve child obstruction\n')
            records[-1]['expectedApplicationDataError'] = True
        elif mode == 'journal-directory':
            assert journal.is_dir() and not list(journal.iterdir())
            assert 'Warning: journal write failed:' in records[-1]['stderr']
            records[-1]['expectedJournalWarning'] = True
        else:
            entries = journal.read_text().splitlines()
            assert len(entries) == 1 and json.loads(entries[0])['previous'] == 'genesis'
            assert 'journal write failed' not in records[-1]['stderr']
            records[-1]['absoluteJournalWritten'] = True
    assert digest(source) == digest(ROOT / 'examples/demo_three_groups.csv')
    result = {'status': 'passed', 'baselineReproduced': True, 'fixedCases': 7, 'nativeInvocations': len(records),
              'cpuAffinity': cpus, 'timeoutSecondsPerInvocation': 60,
              'baselineCoreSha256': digest(args.baseline_cli.resolve().with_name('MvsAnalyzer.Core.dll')),
              'repairedCoreSha256': digest(args.cli.resolve().with_name('MvsAnalyzer.Core.dll')),
              'records': records, 'scientificDecision': 'NO-GO retained',
              'limitations': ['Linux runtime only; other platforms have pure path tests but no runtime verification here.',
                              'No automatic legacy journal migration, merge, deletion or authenticity guarantee.',
                              'Journal failure keeps existing CLI successful analysis plus stderr warning behavior.',
                              'Path/error/parity validation, not a statistical benchmark or filesystem-race proof.']}
    (root / 'journal-path-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'fixedCases': 7, 'nativeInvocations': len(records), 'evidence': str(root)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
