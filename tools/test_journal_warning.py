#!/usr/bin/env python3
"""Opt-in real CLI/Python provenance-warning regression; no model or exit changes."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'python/src'), str(ROOT / 'tools')]
import mvs
from test_python_cli import compare_analysis, strict_json

WARNING = {'level': 'warning', 'code': 'journal_write_failed',
           'message': 'Analysis artifacts were saved, but the local run journal could not be updated.'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-cli', type=Path, required=True)
    parser.add_argument('--cli', type=Path, required=True)
    parser.add_argument('--calibration', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('The isolated XDG obstruction fixture is Linux-only.')
    root = args.artifacts.resolve(); root.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'examples/demo_three_groups.csv'
    calibration = args.calibration.resolve()
    before_state = sha(calibration / 'calibration_state.json')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    os.sched_setaffinity(0, set(cpus))
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(('MVS_', 'DOTNET_', 'COMPlus_'))}
    base_env.update(DOTNET_ROOT=os.environ.get('DOTNET_ROOT', '/tmp/mvs-dotnet'),
                    DOTNET_PROCESSOR_COUNT='2', MVS_DISABLE_BACKUPS='1', DOTNET_CLI_TELEMETRY_OPTOUT='1')
    records = []
    baseline_other_diagnostics = None

    def run(name, cli, *, blocked, python=False, strict=True, quiet=True, expect_warning=True):
        nonlocal baseline_other_diagnostics
        folder = root / name; folder.mkdir()
        data = folder / 'private-journal-location-MUST-NOT-APPEAR-IN-DIAGNOSTIC'
        data.mkdir()
        journal = data / 'MVS_Analyzer/run_journal.jsonl'
        if blocked:
            journal.mkdir(parents=True)
            (journal / 'preserve.txt').write_text('preserve exact journal obstruction\n')
        env = dict(base_env, XDG_DATA_HOME=str(data), XDG_CONFIG_HOME=str(folder / 'config'),
                   XDG_CACHE_HOME=str(folder / 'cache'))
        output = folder / 'output'
        calls = []
        native_run = subprocess.run

        def capture(argv, **kwargs):
            kwargs.setdefault('timeout', 60)
            process = native_run(argv, **kwargs)
            index = len(calls)
            (folder / f'call-{index}.stdout.json').write_text(process.stdout)
            (folder / f'call-{index}.stderr.txt').write_text(process.stderr)
            calls.append({'argv': [str(x) for x in argv], 'exit': process.returncode,
                          'stdoutSha256': sha(folder / f'call-{index}.stdout.json')})
            return process

        if python:
            previous = dict(os.environ)
            try:
                os.environ.clear(); os.environ.update(env)
                with patch('mvs.engine.subprocess.run', side_effect=capture):
                    engine = mvs.Engine(cli.resolve())
                    result = engine.analyze(source, calibration=calibration, output=output,
                                            allow_diagnostic=not strict)
                result.verify_artifacts()
                payload = dict(result.raw)
                assert [asdict(d) for d in result.diagnostics] == payload['diagnostics']
                assert [asdict(d) for d in result.diagnostics if d.code == 'journal_write_failed'] == ([WARNING] if expect_warning else [])
                assert result.status == 'completed' and result.exit_code == 0
            finally:
                os.environ.clear(); os.environ.update(previous)
        else:
            argv = [str(cli.resolve()), 'analyze', '--in', str(source), '--calibration', str(calibration),
                    '--out', str(output), '--json', '--quiet=' + str(quiet).lower()]
            process = capture(argv, env=env, text=True, encoding='utf-8', stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
            assert process.returncode == 0
            payload = json.loads(process.stdout)
        assert payload['status'] == 'completed' and payload['exitCode'] == 0 and payload['error'] is None
        expected = [WARNING] if expect_warning else []
        selected = [d for d in payload['diagnostics'] if d['code'] == 'journal_write_failed']
        assert selected == expected
        other = [d for d in payload['diagnostics'] if d['code'] != 'journal_write_failed']
        if baseline_other_diagnostics is None:
            baseline_other_diagnostics = other
        assert other == baseline_other_diagnostics, 'Existing diagnostics changed or disappeared'
        # Only the new diagnostic is privacy-minimal; artifact paths remain part
        # of the existing machine contract and are checked separately.
        portable = json.dumps(selected)
        for private in (str(data), str(journal), 'MUST-NOT-APPEAR', 'UnauthorizedAccessException', 'IOException'):
            assert private not in portable
        for artifact in payload['artifacts']:
            path = Path(artifact['path'])
            assert path.stat().st_size == artifact['sizeBytes'] and sha(path) == artifact['sha256']
        stderr = (folder / f'call-{len(calls)-1}.stderr.txt').read_text()
        assert ('Warning: journal write failed:' in stderr) == blocked
        if blocked:
            assert sorted(p.name for p in journal.iterdir()) == ['preserve.txt']
            assert (journal / 'preserve.txt').read_text() == 'preserve exact journal obstruction\n'
        else:
            assert journal.is_file() and len(journal.read_text().splitlines()) == 1
        actual = Path(payload['outputDirectory'])
        record = {'case': name, 'interface': 'python' if python else 'cli', 'blockedJournal': blocked,
                  'allowDiagnostic': not strict if python else None, 'quiet': quiet,
                  'status': payload['status'], 'exit': payload['exitCode'], 'diagnostics': payload['diagnostics'],
                  'artifactCount': len(payload['artifacts']), 'diagnosticPrivacyVerified': True,
                  'outputDirectory': str(actual), 'calls': calls}
        records.append(record)
        (folder / 'record.json').write_text(json.dumps(record, indent=2) + '\n')
        return actual

    baseline = run('baseline-warning-invisible', args.baseline_cli, blocked=True, expect_warning=False)
    for name, opts in [('cli-blocked-quiet', dict(blocked=True)),
                       ('cli-blocked-nonquiet', dict(blocked=True, quiet=False)),
                       ('cli-normal', dict(blocked=False, expect_warning=False)),
                       ('python-blocked-strict', dict(blocked=True, python=True)),
                       ('python-blocked-allow-diagnostic', dict(blocked=True, python=True, strict=False)),
                       ('python-normal', dict(blocked=False, python=True, expect_warning=False))]:
        actual = run(name, args.cli, **opts)
        compare_analysis(baseline, actual, 1e-12, 1e-10)
        records[-1]['scientificParity'] = True
    assert before_state == sha(calibration / 'calibration_state.json')
    result = {'status': 'passed', 'baselineGapReproduced': True, 'newCases': 6,
              'workloadInvocations': len(records), 'nativeInvocationsIncludingVersion': sum(len(r['calls']) for r in records),
              'cpuAffinity': cpus, 'timeoutSecondsPerNativeInvocation': 60,
              'warning': WARNING, 'records': records, 'scientificDecision': 'NO-GO retained',
              'beforeCliSha256': sha(args.baseline_cli.resolve().with_name('mvs.dll')),
              'afterCliSha256': sha(args.cli.resolve().with_name('mvs.dll')),
              'limitations': ['Linux XDG fixture only; no Windows/macOS runtime check.',
                              'Warning is runtime machine metadata, not a new artifact-manifest field.',
                              'Existing stderr detail remains; no private journal path added to the diagnostic.',
                              'No scientific method, status/exit, artifact content, or calibration change.']}
    (root / 'journal-warning-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'newCases', 'workloadInvocations', 'nativeInvocationsIncludingVersion')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
