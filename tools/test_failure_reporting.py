#!/usr/bin/env python3
"""Check a deliberately failing native test fixture, never a scientific run."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import unittest


def validate(code, stdout):
    required = ('FAIL  controlled nested failure: controlled outer fixture',
                'DETAIL System.IO.IOException', 'System.UnauthorizedAccessException',
                'controlled inner fixture', 'ThrowInner', 'ThrowOuter',
                'PASS  following control', '1/2 tests passed')
    if code != 1:
        raise ValueError('Controlled failing process must exit 1')
    if any(value not in stdout for value in required):
        raise ValueError('Missing type, nested exception, stack, continuation or summary')
    lines = stdout.splitlines()
    if sum(x.startswith('FAIL  ') for x in lines) != 1 or sum(x.startswith('PASS  ') for x in lines) != 1:
        raise ValueError('Unexpected test counts')
    if lines[-1] != '1/2 tests passed':
        raise ValueError('Final summary changed')


class ReportingChecks(unittest.TestCase):
    text = '\n'.join(('FAIL  controlled nested failure: controlled outer fixture',
        'DETAIL System.IO.IOException: controlled outer fixture',
        'System.UnauthorizedAccessException: controlled inner fixture',
        'at ThrowInner()', 'at ThrowOuter()', 'PASS  following control', '1/2 tests passed'))
    def test_expected_failure(self):
        validate(1, self.text)
    def test_success_is_not_failure_evidence(self):
        for code in (0, 2, -1):
            with self.subTest(code=code), self.assertRaises(ValueError): validate(code, self.text)
    def test_every_detail_required(self):
        for token in ('DETAIL System.IO.IOException', 'System.UnauthorizedAccessException', 'ThrowInner', 'ThrowOuter', 'PASS  following control', '1/2 tests passed'):
            with self.subTest(token=token), self.assertRaises(ValueError): validate(1, self.text.replace(token, 'omitted'))
    def test_counts_and_final_summary(self):
        for text in (self.text+'\nFAIL  extra', self.text.replace('PASS  following control', 'PASS  following control\nPASS  extra'), self.text+'\ntrailing'):
            with self.subTest(text=text), self.assertRaises(ValueError): validate(1, text)
    def test_windows_exit_records_and_unchanged_gate(self):
        source = (Path(__file__).resolve().parents[1]/'.github/workflows/windows-workflow.yml').read_text()
        for name in ('core-tests', 'publish-cli'):
            self.assertIn(f"command = '{name}'", source)
            self.assertIn(f'{name}-status.json', source)
        self.assertIn('${{ env.MVS_GATE_ROOT }}/*-status.json', source)
        self.assertIn('Ran 21 tests', source)
        self.assertIn('skipped|FAILED|ERROR', source)
        self.assertIn('if ($code -ne 0) { exit $code }', source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembly', type=Path)
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReportingChecks))
    if not result.wasSuccessful(): return 1
    if args.assembly is None:
        if args.out is not None: parser.error('--out requires --assembly')
        return 0
    if args.out is None: parser.error('--assembly requires --out')
    args.out.mkdir(parents=True, exist_ok=False)
    command = [args.dotnet, str(args.assembly.resolve()), '--test-failure-reporting-fixture']
    try:
        proc = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        (args.out/'failure.json').write_text(json.dumps({'command': command, 'errorType':type(error).__name__, 'message':str(error)},indent=2)+'\n')
        raise
    (args.out/'stdout.log').write_text(proc.stdout, encoding='utf-8')
    (args.out/'stderr.log').write_text(proc.stderr, encoding='utf-8')
    report = {'command': command, 'nativeExitCode':proc.returncode, 'expectedNativeExitCode':1,
              'purpose':'Controlled test reporter failure; no scientific computation', 'passed':False}
    try:
        validate(proc.returncode, proc.stdout)
        report['passed'] = True
    finally:
        (args.out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Controlled native failure preserved exit 1, details and continuation.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
