#!/usr/bin/env python3
"""Pure retained-file and subprocess-lifecycle tests. No MVS/native/model execution."""
import sys
sys.dont_write_bytecode = True
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time
import types
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('resume_comparison', HERE/'run_resume_comparison.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def save(path, value):
    path.write_text(json.dumps(value, indent=2))


def zip_checkpoint(path, raw):
    with zipfile.ZipFile(path, 'x') as archive:
        archive.writestr('backup.json', raw)
        archive.writestr('SHA256SUMS.txt', m.digest(raw)+'  backup.json\n')


def copy_fixture_inputs(destination):
    source=HERE/'fixtures'
    if (source/'manifest.json').is_file():
        shutil.copytree(source,destination)
        return
    archive_path=HERE/'resume-output-fixtures-v1.zip'
    expected={'manifest.json',*[kind+'-completed.mvsbackup' for kind in m.KINDS]}
    with zipfile.ZipFile(archive_path) as archive:
        if set(archive.namelist())!=expected or len(archive.infolist())!=len(expected):
            raise AssertionError('Unexpected durable fixture ZIP members')
        destination.mkdir()
        for name in sorted(expected):
            if archive.getinfo(name).file_size>64*1024*1024:
                raise AssertionError('Oversized durable fixture member')
            with (destination/name).open('xb') as stream:
                stream.write(archive.read(name))

def make_run(root, fixture, context):
    folder = root/'execution'/context['id']
    folder.mkdir(parents=True)
    output = folder/'output/restored-fixture'
    output.mkdir(parents=True)
    source = m.checkpoint(root/'fixtures'/fixture['file'])
    doc = source['document']
    backup = folder/'backups'
    backup.mkdir()
    zip_checkpoint(backup/'resumed.mvsbackup', m.replace_tokens(source['raw'], {'/SavedUtc':'2026-10-16T12:00:00Z'}))
    state = b'{"CreatedUtc":"2026-10-16T12:00:00Z","Rows":[{"value":1.00}],"PayloadHash":""}'
    state = m.replace_tokens(state, {'/PayloadHash':m.digest(state)})
    provenance = {'backupId':doc['Id'], 'requestHash':doc['RequestHash'], 'retainedUnits':len(doc['Units']),
                  'resumedFromUtc':doc['SavedUtc'], 'environments':doc['Environments'], 'originalProcessing':None}
    for name in fixture['artifacts']:
        if name == 'run_manifest.json':
            continue
        if name == 'calibration_state.json':
            (output/name).write_bytes(state)
        elif name == 'backup_resume.json':
            save(output/name, provenance)
        else:
            (output/name).write_bytes(b'{"science":1.00,"created":"scientific field"}' if name.endswith('.json') else b'value\n1.00\n')
    run_id = None
    manifest = None
    if 'run_manifest.json' in fixture['artifacts']:
        run_id = 'restored_20261016_120000'
        manifest = output/'run_manifest.json'
        save(manifest, {'runId':run_id, 'created':'2026-10-16T12:00:00Z',
                        'files':[{'FileName':p.name, 'SizeBytes':p.stat().st_size, 'sha256':m.sha(p)} for p in sorted(output.iterdir())]})
    code = fixture['expectedExit'][0]
    payload = {'schemaVersion':'mvs-cli-result/v1','command':'resume','status':{0:'completed',2:'diagnostic'}[code],
               'exitCode':code,'execution':{'completed':True,'outcome':{0:'completed',2:'diagnostic'}[code]},
               'error':None,'engineVersion':'1.6.2','scientificReadiness':{'status':'no_go'},
               'outputDirectory':str(output.resolve()),'manifestPath':str(manifest.resolve()) if manifest else None,
               'runId':run_id,'artifacts':[{'name':p.name,'path':str(p.resolve()),**m.record_file(p)} for p in sorted(output.iterdir())]}
    save(folder/'stdout.json',payload)
    (folder/'stderr.log').write_bytes(b'')
    record = {**context, 'returncode':code,'forcedKill':False,'events':[],'reaped':True,'coreclrPaths':[],
              'stdout':m.record_file(folder/'stdout.json'),'stderr':m.record_file(folder/'stderr.log'),
              'wallSeconds':0.013,'cpuUserSeconds':0.01,'cpuSystemSeconds':0.001,'cpuTotalSeconds':0.011,'peakRssKiB':1000}
    save(folder/'record.json',record)
    return folder, source


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='r34-lifecycle-')
        self.folder = Path(self.temp.name)
        self.cpus = sorted(os.sched_getaffinity(0))[:2]
    def tearDown(self):
        self.temp.cleanup()
    def execute(self, code, timeout=3):
        return m.execute([sys.executable,'-c',code],self.folder,{'PATH':'/usr/bin:/bin'},self.cpus,timeout,512)
    def test_actual_parsed_plan_timer_values_complete_without_watchdog_error(self):
        plan=m.read_json(HERE/'round34-plan.json')
        interval=plan['execution']['watchdogPollSeconds']
        self.assertIsInstance(interval,m.decimal.Decimal)
        result=m.execute([sys.executable,'-c','import time;time.sleep(.04);print("ok")'],self.folder,{'PATH':'/usr/bin:/bin'},self.cpus,plan['execution']['timeoutSeconds'],plan['execution']['rssLimitMiB'],interval)
        self.assertEqual(result['returncode'],0)
        self.assertTrue(result['reaped'])
        self.assertEqual(result['events'],[])
        self.assertEqual((self.folder/'stdout.json').read_text(),'ok\n')
    def test_decimal_timeout_and_interval_kill_reap_without_type_error(self):
        config=m.strict_json(b'{"timeout":0.1,"poll":0.01}')
        result=m.execute([sys.executable,'-c','import time;time.sleep(30)'],self.folder,{'PATH':'/usr/bin:/bin'},self.cpus,config['timeout'],512,config['poll'])
        self.assertEqual(result['returncode'],-signal.SIGKILL)
        self.assertTrue(result['forcedKill'] and result['reaped'])
        self.assertEqual([e['type'] for e in result['events']],['timeout'])
    def test_exact_child_blocking_wait_and_nonquantized_endpoint_before_join(self):
        events=[]
        usage=types.SimpleNamespace(ru_utime=.003,ru_stime=.002,ru_maxrss=1234,ru_minflt=7,ru_majflt=0)
        process=types.SimpleNamespace(pid=321,returncode=None)
        def clock():
            events.append('clock')
            self.assertTrue((self.folder/'stdout.json').exists())
            self.assertTrue((self.folder/'stderr.log').exists())
            return [1_000_000_000,1_013_123_456][events.count('clock')-1]
        def wait4(pid, flags):
            self.assertEqual((pid,flags),(321,0))
            events.append('wait4')
            return 321,0,usage
        class Thread:
            def __init__(self,*args,**kwargs):pass
            def start(self):events.append('start')
            def join(self,timeout):events.append('join')
            def is_alive(self):return False
        with mock.patch.object(m.subprocess,'Popen',return_value=process),mock.patch.object(m.os,'wait4',side_effect=wait4),mock.patch.object(m.time,'perf_counter_ns',side_effect=clock),mock.patch.object(m.threading,'Thread',Thread),mock.patch.object(m.time,'sleep',side_effect=AssertionError('Exit polling forbidden')):
            result=m.execute(['fake'],self.folder,{},self.cpus,3,512)
        self.assertEqual(events,['clock','start','wait4','clock','join'])
        self.assertEqual(result['wallSeconds'],.013123456)
        self.assertNotEqual(result['wallSeconds'] % .05,0)
        self.assertEqual(result['cpuTotalSeconds'],.005)
        self.assertEqual(result['peakRssKiB'],1234)
        self.assertTrue(result['reaped'])
        self.assertEqual(process.returncode,0)
    def test_watchdog_join_delay_excluded(self):
        original=m._watchdog
        def delayed(pid,done,*args):
            original(pid,done,*args)
            time.sleep(.2)
        before=time.perf_counter()
        with mock.patch.object(m,'_watchdog',delayed):
            result=self.execute('print("ok")')
        total=time.perf_counter()-before
        self.assertGreater(total-result['wallSeconds'],.15)
        self.assertEqual(result['returncode'],0)
    def test_success_reaped_once_exact_usage(self):
        result=self.execute('print("ok")')
        self.assertEqual(result['returncode'],0)
        self.assertEqual((self.folder/'stdout.json').read_text(),'ok\n')
        self.assertEqual(result['events'],[])
        self.assertGreater(result['peakRssKiB'],0)
        with self.assertRaises(ChildProcessError):os.waitpid(result['pid'],os.WNOHANG)
    def test_timeout_kill_reap_and_partial_capture_retained(self):
        result=self.execute('import time;print("retained",flush=True);time.sleep(30)',.2)
        self.assertEqual(result['returncode'],-signal.SIGKILL)
        self.assertTrue(result['forcedKill'] and result['reaped'])
        self.assertEqual(result['events'][0]['type'],'timeout')
        self.assertIn(b'retained',(self.folder/'stdout.json').read_bytes())
        with self.assertRaises(ChildProcessError):os.waitpid(result['pid'],os.WNOHANG)
    def test_nonzero_failure_capture_retained(self):
        result=self.execute('import sys;print("partial");print("failed",file=sys.stderr);sys.exit(7)')
        self.assertEqual(result['returncode'],7)
        self.assertTrue(result['reaped'])
        self.assertFalse(result['forcedKill'])
        self.assertEqual((self.folder/'stdout.json').read_text(),'partial\n')
        self.assertEqual((self.folder/'stderr.log').read_text(),'failed\n')
    def test_launch_failure_record_and_empty_captures_retained(self):
        result=m.execute(['/nonexistent-r34-fixture-executable'],self.folder,{},self.cpus,3,512)
        self.assertIsNone(result['returncode'])
        self.assertEqual(result['events'][0]['type'],'launch_error')
        self.assertEqual(result['runnerError']['type'],'FileNotFoundError')
        self.assertFalse(result['reaped'])
        self.assertTrue((self.folder/'stdout.json').exists() and (self.folder/'stderr.log').exists())
    def test_watchdog_rss_violation_kills_and_reaps(self):
        with mock.patch.object(m,'_sample_process',return_value='rss_limit'):
            result=self.execute('import time;time.sleep(30)')
        self.assertEqual(result['events'][0]['type'],'rss_limit')
        self.assertTrue(result['forcedKill'] and result['reaped'])
    def test_cleanup_wait_failure_still_returns_retained_lifecycle_record(self):
        process=types.SimpleNamespace(pid=987654,returncode=None)
        class Thread:
            def __init__(self,*args,**kwargs):pass
            def start(self):pass
            def join(self,timeout):pass
            def is_alive(self):return False
        with mock.patch.object(m.subprocess,'Popen',return_value=process),mock.patch.object(m.threading,'Thread',Thread),mock.patch.object(m.os,'wait4',side_effect=ChildProcessError('already reaped elsewhere')),mock.patch.object(m,'_kill_group',return_value=False):
            result=m.execute(['fake'],self.folder,{},self.cpus,3,512)
        self.assertEqual(result['runnerError']['type'],'ChildProcessError')
        self.assertEqual(result['cleanupErrors'][0]['type'],'ChildProcessError')
        self.assertFalse(result['reaped'])
        self.assertIsNone(result['returncode'])
        self.assertTrue((self.folder/'stdout.json').exists())
        self.assertEqual(result['events'][-1]['type'],'cleanup_failure')
    def test_keyboard_interrupt_kills_reaps_and_marks_operator_stop(self):
        process=types.SimpleNamespace(pid=987654,returncode=None)
        usage=types.SimpleNamespace(ru_utime=0,ru_stime=0,ru_maxrss=1,ru_minflt=0,ru_majflt=0)
        class Thread:
            def __init__(self,*args,**kwargs):pass
            def start(self):pass
            def join(self,timeout):pass
            def is_alive(self):return False
        with mock.patch.object(m.subprocess,'Popen',return_value=process),mock.patch.object(m.threading,'Thread',Thread),mock.patch.object(m.os,'wait4',side_effect=[KeyboardInterrupt(),(987654,signal.SIGKILL,usage)]),mock.patch.object(m,'_kill_group',return_value=True):
            result=m.execute(['fake'],self.folder,{},self.cpus,3,512)
        self.assertTrue(result['interrupted'] and result['forcedKill'] and result['reaped'])
        self.assertEqual(result['returncode'],-signal.SIGKILL)
    def test_interrupted_wait_retried_blocking(self):
        original=m.os.wait4
        calls=[]
        def wait4(pid, flags):
            calls.append((pid,flags))
            if len(calls)==1:raise InterruptedError()
            return original(pid,flags)
        with mock.patch.object(m.os,'wait4',side_effect=wait4):result=self.execute('pass')
        self.assertEqual(len(calls),2)
        self.assertTrue(all(flags==0 for _,flags in calls))
        self.assertTrue(result['reaped'])


class RetainedVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='r34-retained-')
        self.root=Path(self.temp.name)
        copy_fixture_inputs(self.root/'fixtures')
        self.original_root=m.ROOT
        m.ROOT=self.root
        self.fixture=m.fixture_manifest()['fixtures'][0]
        self.context={'id':'calibrate-pair1-1-A','workload':'calibrate','pair':1,'position':1,'build':'A'}
        self.folder,self.source=make_run(self.root,self.fixture,self.context)
    def tearDown(self):
        m.ROOT=self.original_root
        self.temp.cleanup()
    def inspect(self):return m.inspect_run(self.folder,self.fixture,self.source)
    def rewrite_payload(self, change):
        path=self.folder/'stdout.json'
        payload=json.loads(path.read_text())
        change(payload)
        save(path,payload)
        record=json.loads((self.folder/'record.json').read_text())
        record['stdout']=m.record_file(path)
        save(self.folder/'record.json',record)
    def refresh_artifacts(self):
        self.rewrite_payload(lambda payload:payload.update(artifacts=[{'name':p.name,'path':str(p.resolve()),**m.record_file(p)} for p in sorted((self.folder/'output/restored-fixture').iterdir())]))
    def test_frozen_five_completed_fixture_identities(self):
        self.assertEqual(set(m.check_fixtures()),set(m.KINDS))
    def test_expected_output_and_saved_cached_result(self):
        result=self.inspect()
        self.assertTrue(result['savedBackup']['completedResultExactBytesRetained'])
        self.assertIn('resumed_checkpoint.json',result['normalized'])
    def test_actual_file_checksum_required(self):
        path=self.folder/'output/restored-fixture/calibration.csv'
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(AssertionError,'size mismatch|checksum mismatch'):self.inspect()
    def test_payload_checksum_required_independently(self):
        path=self.folder/'output/restored-fixture/calibration_state.json'
        path.write_bytes(path.read_bytes().replace(b'1.00',b'1.01'))
        self.refresh_artifacts()
        with self.assertRaisesRegex(AssertionError,'payload checksum mismatch'):self.inspect()
    def test_raw_stdout_identity_required(self):
        path=self.folder/'stdout.json';path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(AssertionError,'raw capture changed'):self.inspect()
    def test_misdirected_artifact_rejected(self):
        self.rewrite_payload(lambda p:p['artifacts'][0].update(path='/wrong/file'))
        with self.assertRaisesRegex(AssertionError,'artifact path differs'):self.inspect()
    def test_duplicate_artifact_rejected(self):
        self.rewrite_payload(lambda p:p['artifacts'].__setitem__(1,p['artifacts'][0]))
        with self.assertRaisesRegex(AssertionError,'artifact identity differs'):self.inspect()
    def test_unexpected_artifact_rejected(self):
        (self.folder/'output/restored-fixture/extra.txt').write_text('x')
        with self.assertRaisesRegex(AssertionError,'file set differs'):self.inspect()
    def test_restore_bypass_rejected_without_saved_backup(self):
        (self.folder/'backups/resumed.mvsbackup').unlink()
        with self.assertRaisesRegex(AssertionError,'resumed-session primary backup'):self.inspect()
    def test_changed_cached_result_rejected(self):
        path=self.folder/'backups/resumed.mvsbackup'
        data=m.checkpoint(path)
        changed=m.replace_tokens(data['raw'],{'/Units/result':[]})
        path.unlink();zip_checkpoint(path,changed)
        with self.assertRaisesRegex(AssertionError,'Cached completed result bytes changed'):self.inspect()
    def test_rewritten_environment_history_rejected(self):
        path=self.folder/'backups/resumed.mvsbackup'
        data=m.checkpoint(path)
        changed=m.replace_tokens(data['raw'],{'/Environments':['wrong']})
        path.unlink();zip_checkpoint(path,changed)
        with self.assertRaisesRegex(AssertionError,'history was rewritten'):self.inspect()
    def test_checkpoint_original_bytes_frozen(self):
        path=self.root/'fixtures'/self.fixture['file'];path.chmod(0o644);path.write_bytes(path.read_bytes()+b'x')
        with self.assertRaisesRegex(AssertionError,'identity changed'):m.check_fixtures()
    def test_no_generic_scientific_timestamp_removal(self):
        raw=b'{"CreatedUtc":"2026-10-16T00:00:00Z","Rows":[{"created":"scientific column"}],"PayloadHash":""}'
        normalized=m.canonical_state(m.replace_tokens(raw,{'/PayloadHash':m.digest(raw)}))
        self.assertIn(b'"created":"scientific column"',normalized)
    def test_numeric_lexeme_precision_and_pointer_escaping(self):
        raw=b'{"a/b":{"~key":[1.000000000000001,1e-20]},"when":"old"}'
        result=m.replace_tokens(raw,{'/when':'new'})
        self.assertEqual(result,b'{"a/b":{"~key":[1.000000000000001,1e-20]},"when":"new"}')
        self.assertEqual(m.raw_token(result,'/a~1b/~0key/1'),b'1e-20')
    def test_duplicate_or_nonfinite_json_rejected(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}']:
            with self.assertRaises((AssertionError,ValueError)):m.strict_json(raw)
    def prepare_full_report(self):
        shutil.rmtree(self.root/'execution')
        plan={'scope':'synthetic pure verifier test','execution':{'pairOrder':['AB','BA','AB']},'performance':{'limitations':[]}}
        save(m.plan_path(),plan)
        binding={'coreclrFiles':{}}
        save(self.root/'binding.json',binding)
        for fixture,context in m.planned_invocations(plan,m.fixture_manifest()['fixtures']):make_run(self.root,fixture,context)
        destination=self.root/'execution'
        save(destination/'finished.json',{'invocations':30})
        save(destination/'binding.json',binding)
        save(destination/'plan.json',plan)
        save(destination/'fixtures-manifest.json',m.fixture_manifest())
        m.publish_report(plan,binding)
    def test_full_30_run_verify_is_readonly_and_recomputes(self):
        self.prepare_full_report()
        before=m.inventory(self.root)
        original_open=Path.open
        def readonly_open(path,mode='r',*args,**kwargs):
            self.assertFalse(any(flag in mode for flag in 'wax+'),'verify attempted write: '+str(path))
            return original_open(path,mode,*args,**kwargs)
        with mock.patch.object(m,'check_binding'),mock.patch.object(Path,'open',readonly_open),mock.patch.object(Path,'mkdir',side_effect=AssertionError('verify mkdir')),mock.patch.object(m.subprocess,'Popen',side_effect=AssertionError('verify process')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.verify(None),0)
        self.assertEqual(before,m.inventory(self.root))
    def test_missing_normalized_evidence_not_repaired(self):
        self.prepare_full_report()
        path=self.root/'execution/calibrate-pair1-1-A/normalized/calibration.csv'
        path.unlink()
        before=m.inventory(self.root)
        with mock.patch.object(m,'check_binding'),self.assertRaisesRegex(AssertionError,'normalized evidence differs'):m.verify(None)
        self.assertFalse(path.exists())
        self.assertEqual(before,m.inventory(self.root))
    def test_failure_retained_report_does_not_drop_attempt(self):
        self.prepare_full_report()
        path=self.root/'execution/calibrate-pair1-1-A/record.json'
        record=json.loads(path.read_text());record.update(returncode=-9,forcedKill=True,events=[{'type':'timeout'}]);save(path,record)
        report,_=m.report_from_retained(m.read_json(m.plan_path()),m.read_json(self.root/'binding.json'))
        self.assertFalse(report['passed'])
        self.assertEqual(report['invocationCount'],30)
        self.assertEqual(len(report['allRawMeasurements']),30)
        self.assertIn('calibrate-pair1-1-A',[e['invocation'] for e in report['errors']])
    def test_run_operator_interrupt_records_attempt_then_stops(self):
        shutil.rmtree(self.root/'execution')
        plan={'execution':{'pairOrder':['AB','BA','AB'],'timeoutSeconds':60,'rssLimitMiB':1024,'watchdogPollSeconds':.02}}
        save(m.plan_path(),plan)
        binding={'cpuAffinity':sorted(os.sched_getaffinity(0))[:2],'baseEnvironment':{},'dotnetHost':{'path':'unused'},'builds':{'A':{'entrypoint':'unused'},'B':{'entrypoint':'unused'}}}
        save(self.root/'binding.json',binding)
        def interrupted(command,folder,*args):
            (folder/'stdout.json').write_bytes(b'partial')
            (folder/'stderr.log').write_bytes(b'')
            return {'interrupted':True,'returncode':-9,'reaped':True,'forcedKill':True,'events':[{'type':'runner_error'}]}
        with mock.patch.object(m,'check_binding'),mock.patch.object(m,'execute',side_effect=interrupted) as execute,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(KeyboardInterrupt):
            m.run(types.SimpleNamespace(approved_exclusive_window=True))
        self.assertEqual(execute.call_count,1)
        destination=self.root/'execution'
        self.assertEqual(m.read_json(destination/'aborted.json')['retainedAttempts'],1)
        self.assertTrue((destination/'calibrate-pair1-1-A/record.json').is_file())
        self.assertFalse((destination/'finished.json').exists())
        self.assertFalse((destination/'calibrate-pair1-2-B').exists())
    def test_run_unresolved_child_stops_without_overlapping_next_attempt(self):
        shutil.rmtree(self.root/'execution')
        plan={'execution':{'pairOrder':['AB','BA','AB'],'timeoutSeconds':60,'rssLimitMiB':1024,'watchdogPollSeconds':.02}}
        save(m.plan_path(),plan)
        binding={'cpuAffinity':sorted(os.sched_getaffinity(0))[:2],'baseEnvironment':{},'dotnetHost':{'path':'unused'},'builds':{'A':{'entrypoint':'unused'},'B':{'entrypoint':'unused'}}}
        save(self.root/'binding.json',binding)
        def unresolved(command,folder,*args):
            (folder/'stdout.json').write_bytes(b'partial')
            (folder/'stderr.log').write_bytes(b'')
            return {'pid':987654,'interrupted':False,'returncode':None,'reaped':False,'forcedKill':False,'cleanupErrors':[{'action':'reap'}],'events':[{'type':'cleanup_failure'}]}
        with mock.patch.object(m,'check_binding'),mock.patch.object(m,'execute',side_effect=unresolved) as execute,contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(AssertionError,'Unresolved child cleanup'):
            m.run(types.SimpleNamespace(approved_exclusive_window=True))
        self.assertEqual(execute.call_count,1)
        destination=self.root/'execution'
        self.assertEqual(m.read_json(destination/'aborted.json')['retainedAttempts'],1)
        self.assertTrue((destination/'calibrate-pair1-1-A/record.json').is_file())
        self.assertFalse((destination/'calibrate-pair1-2-B').exists())
    def test_measured_order_exactly_AB_BA_AB_five_types(self):
        items=list(m.planned_invocations({'execution':{'pairOrder':['AB','BA','AB']}},m.fixture_manifest()['fixtures']))
        self.assertEqual(len(items),30)
        for offset in range(0,30,6):self.assertEqual(''.join(c['build'] for _,c in items[offset:offset+6]),'ABBAAB')


if __name__=='__main__':unittest.main(verbosity=2)
