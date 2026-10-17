"""Tiny no-calibration corruption and lifecycle tests; never execute the native harness."""
import copy
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import stability_replay_driver as d

ROOT = Path(__file__).resolve().parents[1]


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.rows = d.read_history(ROOT / d.HISTORY)
        self.cases = []
        for i, row in enumerate(self.rows):
            old = dict(kendall_tau=float(row['kendall_tau']), defined=True, undefined_reason=None,
                       top_left=row['top_left'], top_right=row['top_right'], matched=row['matched'] == 'true')
            self.cases.append(dict(index=i, status='completed', diagnostics_status='retained', error='',
                                   legacy=old, corrected=copy.deepcopy(old)))

    def test_all120_exact(self):
        r = d.compare(self.rows, self.cases)
        self.assertTrue(r['all_120_legacy_diagnostics_exact'])
        self.assertEqual(r['original_matched'], 27)
        self.assertEqual(r['corrected_finite_count'], 120)
        self.assertEqual(r['original_top_one_agreement'], .225)
        self.assertEqual(len(r['paired_cases']), 120)

    def test_missing_duplicate(self):
        for cases in (self.cases[:-1], self.cases + [self.cases[0]]):
            self.assertFalse(d.compare(self.rows, cases)['all_120_legacy_diagnostics_exact'])

    def test_one_ulp_not_tolerated_and_corrected_not_selected(self):
        old = self.cases[0]['legacy']
        old['kendall_tau'] = math.nextafter(old['kendall_tau'], 1)
        r = d.compare(self.rows, self.cases)
        self.assertFalse(r['all_120_legacy_diagnostics_exact'])
        self.assertEqual(r['corrected_finite_count'], 120)

    def test_each_legacy_field_mismatch(self):
        for field in ('top_left', 'top_right', 'matched'):
            cases = copy.deepcopy(self.cases)
            cases[0]['legacy'][field] = False if field == 'matched' else 'other'
            self.assertFalse(d.compare(self.rows, cases)['all_120_legacy_diagnostics_exact'])
        for field in ('status', 'diagnostics_status', 'error'):
            cases = copy.deepcopy(self.cases)
            cases[0][field] = 'changed'
            self.assertFalse(d.compare(self.rows, cases)['all_120_legacy_diagnostics_exact'])

    def test_undefined_changes_denominator_only(self):
        self.cases[0]['corrected'].update(defined=False, kendall_tau=None, undefined_reason='constant')
        r = d.compare(self.rows, self.cases)
        self.assertEqual(r['corrected_finite_count'], 119)
        self.assertEqual(r['corrected_undefined_count'], 1)
        self.assertEqual(r['corrected_matched_finite_count'], 26)
        self.assertEqual(r['corrected_top_one_agreement'], 26 / 119)

    def test_native_failure_explicit(self):
        self.cases[0].update(status='failed', error='synthetic')
        r = d.compare(self.rows, self.cases)
        self.assertFalse(r['all_120_legacy_diagnostics_exact'])
        self.assertEqual(r['replay_execution_or_diagnostics_failed_count'], 1)

    def test_quantile_existing_linear_definition(self):
        self.assertEqual(d.quantile([0, 1, 2, 3], .25), .75)


class BindingTests(unittest.TestCase):
    def test_nonfinite_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'bad.json'
            for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":1,"x":2}'):
                p.write_text(text)
                with self.assertRaises(ValueError): d.read_json(p)

    def test_write_once(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'one.json'
            d.write_json(p, {'a': 1})
            with self.assertRaises(FileExistsError): d.write_json(p, {'a': 2})
            self.assertEqual(d.read_json(p), {'a': 1})

    def test_altered_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            d.write_json(p / 'bind.json', {})
            (p / 'bind.sha256').write_text('wrong')
            with self.assertRaisesRegex(ValueError, 'manifest altered'): d.verify(p)

    def test_altered_source_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            source = p / 'source.cs'
            source.write_text('before')
            native = p / 'native'
            native.mkdir()
            history, protocol = p / 'history', p / 'protocol'
            history.write_text('history'); protocol.write_text('protocol')
            pins = d.pin_paths([source, history, protocol])
            m = dict(indices=list(range(120)), workers=8, wall_seconds=900, memory_bytes=4*1024**3,
                     root=str(p), sources=[str(source)], native_dir=str(native), native_files=[],
                     pins=pins, history=str(history), protocol=str(protocol))
            d.write_json(p / 'bind.json', m)
            (p / 'bind.sha256').write_text(d.digest(p / 'bind.json'))
            source.write_text('after')
            with patch.object(d, 'HISTORY_SHA', pins[str(history)]), patch.object(d, 'PROTOCOL_SHA', pins[str(protocol)]):
                with self.assertRaisesRegex(ValueError, 'pinned hash changed'): d.verify(p)


@unittest.skipUnless(sys.platform == 'linux', 'Linux process lifecycle tests')
class LifecycleTests(unittest.TestCase):
    def run_fake(self, body, seconds=3, indices=(0,)):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        script = root / 'fake.py'
        script.write_text(body)
        out = root / 'output'
        out.mkdir()
        result = d.execute_cases(out, [sys.executable, str(script)], indices, seconds, 2, 4*1024**3)
        return out, result

    def test_success_env_and_every_index_once(self):
        out, result = self.run_fake('import os,sys,json\np=sys.argv[sys.argv.index("--out")+1]\nopen(p,"x").write(json.dumps(dict(env=os.environ["DOTNET_PROCESSOR_COUNT"],backups=os.environ["MVS_DISABLE_BACKUPS"])))\n', indices=(0, 1, 2))
        self.assertEqual([a['index'] for a in result['attempts']], [0, 1, 2])
        self.assertTrue(all(a['returncode'] == 0 for a in result['attempts']))
        self.assertEqual(d.read_json(out / 'case-000/native.json'), {'env': '1', 'backups': '1'})

    def test_failure_retained_no_retry(self):
        out, r = self.run_fake('import sys\nprint("failure evidence", file=sys.stderr)\nsys.exit(7)\n')
        self.assertEqual(len(r['attempts']), 1)
        self.assertEqual(r['attempts'][0]['returncode'], 7)
        self.assertIn('failure evidence', (out / 'case-000/stderr.log').read_text())

    def test_timeout_cleanup_retains_partial_and_stops_new_cases(self):
        body = ('import time,sys,os\np=sys.argv[sys.argv.index("--out")+1]\n'
                'open(p+".partial.json","x").write("{\\"partial\\":true}")\n'
                'time.sleep(30)\n')
        out, r = self.run_fake(body, seconds=.25, indices=(0, 1, 2, 3))
        self.assertIn('whole-run wall timeout', r['stop_reasons'])
        self.assertLess(r['elapsed_seconds'], 3)
        self.assertTrue((out / 'case-000/native.json.partial.json').exists())
        self.assertFalse(r['attempts'][2]['started'])
        for a in r['attempts']:
            if a['started']:
                with self.assertRaises(ProcessLookupError): os.kill(a['pid'], 0)

    def test_descendant_process_group_cleanup(self):
        body = ('import subprocess,sys,time\np=sys.argv[sys.argv.index("--out")+1]\n'
                'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])\n'
                'open(p+".child","x").write(str(child.pid))\ntime.sleep(30)\n')
        out, r = self.run_fake(body, seconds=.25)
        pid = int((out / 'case-000/native.json.child').read_text())
        proc = Path('/proc') / str(pid) / 'stat'
        if proc.exists():
            self.assertEqual(proc.read_text().rsplit(')', 1)[1].split()[0], 'Z')
        self.assertIn('whole-run wall timeout', r['stop_reasons'])

    def test_spawn_error_retained(self):
        with tempfile.TemporaryDirectory() as td:
            r = d.execute_cases(Path(td), ['/no/such/native'], [0], 1, 1, 4*1024**3)
            self.assertFalse(r['attempts'][0]['started'])
            self.assertIn('FileNotFoundError', r['attempts'][0]['error'])
            self.assertTrue((Path(td) / 'case-000/started.json').exists())

    def test_memory_watchdog(self):
        with patch.object(d, 'group_rss', return_value=10**12):
            out, r = self.run_fake('import time\ntime.sleep(30)\n')
        self.assertIn('aggregate process-group RSS limit exceeded', r['stop_reasons'])
        self.assertIsNotNone(r['attempts'][0]['returncode'])


if __name__ == '__main__': unittest.main()
