"""Synthetic host/contract regressions. No engineering/statistical native calls.

The optional native input tests added separately also use identity/validate-only,
never a valid engineering request. Host supervisor tests run tiny Python stubs.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import threading
import unittest
from unittest import mock

import prospective_cost_probe as probe

ROOT = Path(__file__).resolve().parents[1]


def fake_identity(manifest):
    source = {str(Path(p).relative_to(manifest['root'])): sha for p, sha in manifest['pins'].items()
              if str(Path(p).parent) == manifest['root'] and p.endswith('.cs')}
    return dict(experimental=True, sourceSha256=source,
                runtime=dict(version='8.0.31', framework='.NET 8.0.31', processArchitecture='X64', coreLibrarySha256=manifest['pins'][next(p for p in manifest['runtime_files'] if Path(p).name=='System.Private.CoreLib.dll')]),
                harnessAssembly=dict(fileName='MvsAnalyzer.Core.Tests.dll', sha256=manifest['pins'][manifest['command'][1]]),
                coreAssembly=dict(fileName='MvsAnalyzer.Core.dll', sha256=manifest['pins'][str(Path(manifest['native_dir'])/'MvsAnalyzer.Core.dll')]))


def envelope(kind, counts=0, mode='engineering'):
    return dict(schema=probe.SCHEMA, protocolId=probe.REQUEST['protocolId'], kind=kind, mode=mode,
                requestSha256=None if mode == 'identity' else probe.REQUEST_SHA,
                operationCountScope='adapter_entry_calls_only_nested_production_calls_not_instrumented',
                operationCounts={k: int(i < counts) for i, k in enumerate(probe.COUNTS)})


def identity_row(m):
    row = envelope('identity', mode='identity'); row.update(identity=fake_identity(m), frozenEngineeringRequestSha256=probe.REQUEST_SHA,
        adapterSourceSha256={name:m['pins'][str(Path(m['root'])/name)] for name in ('validation/prospective_adapter/Program.cs','validation/prospective_adapter/ProspectiveAdapter.csproj')})
    return row


def fixture_manifest():
    m = dict(root='/repo', native_dir='/native', command=['/dotnet','/native/MvsAnalyzer.Core.Tests.dll'], runtime_files=['/runtime/System.Private.CoreLib.dll'])
    paths = [f'/repo/source{i:02}.cs' for i in range(14)] + ['/repo/validation/prospective_adapter/Program.cs', '/repo/validation/prospective_adapter/ProspectiveAdapter.csproj', '/native/MvsAnalyzer.Core.Tests.dll','/native/MvsAnalyzer.Core.dll', '/runtime/System.Private.CoreLib.dll']
    m['pins'] = {p: hashlib.sha256(p.encode()).hexdigest() for p in paths}; return m


def fixture_stream(m):
    timing = dict(WallSeconds=.1, CpuSeconds=.1, PeakWorkingSetBytes=1_000_000)
    summary = {k: True for k in probe.CERTIFICATION}; summary.update(actualCachedRequests=1103, expectedCachedRequests=1103, intervalConvergedCount=100, intervalFiniteCount=100, missingKeys=[])
    fixture = dict(dataSha256='a'*64, observations=[], rawRows=1280, retainedRows=1280, entities=32, GroupCounts=[16,16])
    trace = [dict(kind='try', key='result', hit=False)]
    for key in probe.round50.expected_keys():
        trace.append(dict(kind='cached', observation=dict(Key=key, CallbackCount=1, Returned=True, Exception=None, Finite=True,
                     Converged=True if key=='initial-fit' or key.endswith('/null-fit') else None, Value={'bits':'3ff0000000000000','value':1}, AtBoundary=False)))
    trace.append(dict(kind='completeness', summary=summary))
    payload = dict(dataSha256='a'*64, report={'seed':52000000, 'value':{'bits':'3ff0000000000000','value':1}}, legacy={'familySize':12}, completeness=summary)
    reference = dict(payload=payload, trace=trace, fixture=fixture)
    start = envelope('adapter_start'); ident = identity_row(m)
    start.update({k: ident[k] for k in ('identity','adapterSourceSha256','frozenEngineeringRequestSha256')}); start['processorCount']=1
    frow = envelope('fixture',2); frow.update(fixture, exactOrderedBinary64Retention=True, buildTiming=timing)
    rows = [start,frow]
    rows.extend(dict(r,call=1) for r in trace[:-1])
    returned = envelope('variance_returned',3); returned.update(call=1,runTiming=timing,report=payload['report']);rows.append(returned)
    rows.append(dict(trace[-1],call=1))
    complete = envelope('call_complete',6); complete.update(call=1,runTiming=timing,legacyTiming=timing,serializationTiming=timing,serializedUtf8Bytes=1,legacySerializedUtf8Bytes=1,payload=dict(payload,call=1));rows.append(complete)
    end = envelope('adapter_complete',6); end.update(completed=True,status='engineering_fixture_complete',scientificStudyExecuted=False,nativeTotalWallSeconds=.2,processTotalCpuSeconds=.2,processPeakWorkingSetBytes=1_000_000); rows.append(end)
    return rows, reference


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'stdout.jsonl'
        self.m=fixture_manifest(); self.rows,self.reference=fixture_stream(self.m)
    def tearDown(self): self.tmp.cleanup()
    def write(self, rows=None):
        self.path.write_bytes(b''.join(probe.canonical(r) for r in (self.rows if rows is None else rows)));return self.path
    def test_canonical_request_sha(self): self.assertEqual(hashlib.sha256(probe.canonical(probe.REQUEST)).hexdigest(),probe.REQUEST_SHA)
    def test_runtime_is_selected_exactly(self):
        self.assertEqual(probe.native_argv(['/dotnet','/adapter.dll']),['/dotnet','--fx-version','8.0.31','/adapter.dll'])
    def test_fixed_schedule(self): self.assertEqual(probe.schedule(),[[0],[1],[2],list(range(3,11))])
    def test_original54_and_frozen_contract(self): probe.check_protocol(ROOT)
    def test_scientific_payload_and_callbacks_accept(self): self.assertTrue(probe.validate_native(self.write(),self.m,self.reference)['certified'])
    def test_truncated_stream(self):
        for rows in (self.rows[:-1],self.rows[1:]):
            with self.subTest(length=len(rows)),self.assertRaises(ValueError):probe.validate_native(self.write(rows),self.m,self.reference)
    def test_missing_duplicate_reordered_callbacks(self):
        for action in ('missing','duplicate','reorder'):
            rows=copy.deepcopy(self.rows)
            if action=='missing': del rows[3]
            elif action=='duplicate': rows.insert(3,copy.deepcopy(rows[3]))
            else: rows[3],rows[4]=rows[4],rows[3]
            with self.subTest(action=action),self.assertRaises(ValueError):probe.validate_native(self.write(rows),self.m,self.reference)
    def test_callback_corruption_and_cache_hit(self):
        changes=[(2,lambda r:r.update(hit=True)),(3,lambda r:r['observation'].update(CallbackCount=0)),(3,lambda r:r['observation'].update(Finite=False)),(3,lambda r:r['observation']['Value'].update(bits='3ff0000000000001'))]
        for index,change in changes:
            rows=copy.deepcopy(self.rows);change(rows[index])
            with self.subTest(index=index),self.assertRaises(ValueError):probe.validate_native(self.write(rows),self.m,self.reference)
    def test_report_bit_corruption(self):
        rows=copy.deepcopy(self.rows); rows[-2]['payload']['report']['value']['bits']='3ff0000000000001'
        with self.assertRaises(ValueError):probe.validate_native(self.write(rows),self.m,self.reference)
    def test_false_completeness(self):
        rows=copy.deepcopy(self.rows);rows[-3]['summary']['certified']=False
        with self.assertRaises(ValueError):probe.validate_native(self.write(rows),self.m,self.reference)
    def test_source_and_runtime_identity_corruption(self):
        for key in ('source','adapter','runtime','assembly'):
            rows=copy.deepcopy(self.rows)
            if key=='source':rows[0]['identity']['sourceSha256']['source00.cs']='0'*64
            elif key=='adapter':rows[0]['adapterSourceSha256']['validation/prospective_adapter/Program.cs']='0'*64
            elif key=='runtime':rows[0]['identity']['runtime']['coreLibrarySha256']='0'*64
            else:rows[0]['identity']['harnessAssembly']['sha256']='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):probe.validate_native(self.write(rows),self.m,self.reference)
    def test_operation_counts_and_counter_scope(self):
        for key,value in [('directGenerateCallCount',1),('runCallCount',2)]:
            rows=copy.deepcopy(self.rows);rows[-1]['operationCounts'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):probe.validate_native(self.write(rows),self.m,self.reference)
        self.rows[-1]['operationCountScope']='nested counters'
        with self.assertRaises(ValueError):probe.validate_native(self.write(),self.m,self.reference)
    def test_no_unknown_fields_inside_scientific_payload(self):
        self.rows[-2]['payload']['extra']='ignored?'
        with self.assertRaises(ValueError):probe.validate_native(self.write(),self.m,self.reference)
    def test_parser_duplicate_nonfinite_truncated_and_nonobject(self):
        for raw in (b'{"a":1,"a":2}\n',b'{"a":NaN}\n',b'{"a":1e999}\n',b'{"a":1}',b'[]\n'):
            self.path.write_bytes(raw)
            with self.subTest(raw=raw),self.assertRaises(ValueError):probe.parse_jsonl(self.path)
    def test_exact_comparison_rejects_boolean_coercion(self): self.assertFalse(probe.strict_equal({'a':True},{'a':1}))
    def test_budget_math_and_historical_reference_separate(self):
        value=probe.admission([1,2,3],4,100,10**10,all_complete=True,rss_ok=True)
        self.assertEqual(value['projected_wall_seconds'],12000);self.assertEqual(value['storage_required_bytes'],2*100*12000+1024**3)
        self.assertTrue(value['budget_eligible']);self.assertFalse(value['science_execution_authorized']);self.assertAlmostEqual(value['historical_linear_reference_hours'],11.590861607014126)
    def test_budget_boundaries(self):
        args=([28.8]*3,28.8,100,2*100*12000+1024**3)
        self.assertTrue(probe.admission(*args,all_complete=True,rss_ok=True)['budget_eligible'])
        for kwargs in ({'all_complete':False,'rss_ok':True},{'all_complete':True,'rss_ok':False},{'all_complete':True,'rss_ok':True,'failures':['unknown_exit']}):self.assertFalse(probe.admission(*args,**kwargs)['budget_eligible'])
        self.assertFalse(probe.admission([28.80001]*3,28.8,args[2],args[3],all_complete=True,rss_ok=True)['budget_eligible'])
        self.assertFalse(probe.admission(args[0],args[1],args[2],args[3]-1,all_complete=True,rss_ok=True)['budget_eligible'])
    def test_invalid_budget_inputs(self):
        for args in (([1,2],3,1,1),([1,2,float('nan')],3,1,1),([1,2,3],0,1,1),([1,2,3],4,-1,1)):
            with self.subTest(args=args),self.assertRaises(ValueError):probe.admission(*args,all_complete=True,rss_ok=True)
    def test_no_overwrite_and_explicit_execution(self):
        probe.write_json(self.path,{'a':1})
        with self.assertRaises(FileExistsError):probe.write_json(self.path,{'a':2})
        with self.assertRaisesRegex(ValueError,'explicit --execute'):probe.run(self.tmp.name,'0'*64)
        with self.assertRaisesRegex(ValueError,'fresh output'):probe.prepare(ROOT,self.tmp.name,'x',[],['a','b'],None,None,None)
    def test_invalid_binding_seal_and_approval(self):
        out=Path(self.tmp.name);probe.write_json(out/'bind.json',{});(out/'bind.sha256').write_text('0'*64)
        with self.assertRaisesRegex(ValueError,'binding seal'):probe.verify(out)
        (out/'bind.sha256').write_text(probe.digest(out/'bind.json'))
        with self.assertRaisesRegex(ValueError,'approved binding'):probe.verify(out,'0'*64)


@unittest.skipUnless(sys.platform=='linux','Linux process-group and procfs tests')
class SupervisorTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.out=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def execute(self,codes,batches=None,**kwargs):
        commands=[[sys.executable,'-c',code] for code in codes]
        return probe.execute_schedule(self.out,commands,batches or [[i] for i in range(len(codes))],dict(os.environ),sample_seconds=.01,cleanup_seconds=2,**kwargs)
    def test_success_blocking_wait_lifecycle_and_fixed_batch(self):
        code="import time; print('{}',flush=True);time.sleep(.06)"
        result=self.execute([code]*11,probe.schedule())
        self.assertFalse(result['stop_reasons']);self.assertTrue(result['cleanup_complete'])
        self.assertEqual(len({a['pid'] for a in result['attempts']}),11)
        for a in result['attempts']:
            self.assertEqual(a['status'],'completed');self.assertGreaterEqual(a['lifecycle_seconds'],.06)
            self.assertGreater(a['rss_samples'],0)
            self.assertTrue((self.out/f"case-{a['index']:02d}"/'started.json').exists())
        self.assertLess(result['attempts'][0]['end_monotonic'],result['attempts'][1]['start_monotonic'])
        self.assertLess(result['attempts'][2]['end_monotonic'],min(a['start_monotonic'] for a in result['attempts'][3:]))
        batch=result['batches'][-1];a=result['attempts'][3:]
        self.assertEqual(batch['lifecycle_seconds'],max(x['end_monotonic'] for x in a)-min(x['start_monotonic'] for x in a))
    def test_timeout_kills_entire_process_group_retains_partial(self):
        code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);print(p.pid,flush=True);time.sleep(30)"
        result=self.execute([code,"raise Exception('must not start')"],wall_seconds=.15)
        self.assertIn('wall_timeout',[r['code'] for r in result['stop_reasons']]);self.assertFalse(result['attempts'][1]['started'])
        self.assertNotEqual(result['attempts'][0]['returncode'],0);self.assertTrue(result['cleanup_complete'])
        pid=int((self.out/'case-00/stdout.jsonl').read_text());stat=Path(f'/proc/{pid}/stat')
        self.assertTrue(not stat.exists() or stat.read_text().rsplit(')',1)[1].split()[0]=='Z')
    def test_native_nonzero_no_retry(self):
        result=self.execute(["print('{}');raise SystemExit(7)","print('{}')"])
        self.assertEqual(result['attempts'][0]['returncode'],7);self.assertFalse(result['attempts'][1]['started']);self.assertIn('native_failure',[r['code'] for r in result['stop_reasons']])
    def test_missing_outputs_distinct_failure(self):
        result=self.execute(['pass']);self.assertEqual(result['attempts'][0]['status'],'missing_outputs');self.assertIn('missing_outputs',[r['code'] for r in result['stop_reasons']])
    def test_stderr_is_failure(self):
        result=self.execute(["import sys;print('{}');print('bad',file=sys.stderr)"]);self.assertEqual(result['attempts'][0]['status'],'validation_failure')
    def test_callback_validation_failure_stops_later_launch(self):
        def reject(path):raise ValueError('incomplete callbacks')
        result=self.execute(["print('{}')","print('{}')"],validator=reject)
        self.assertIn('validation_failure',[r['code'] for r in result['stop_reasons']]);self.assertFalse(result['attempts'][1]['started'])
    def test_memory_limit_is_fail_closed(self):
        result=self.execute(["import time;print('{}',flush=True);time.sleep(30)"],memory_bytes=10,rss_reader=lambda pids:11)
        self.assertIn('memory_limit',[r['code'] for r in result['stop_reasons']]);self.assertTrue(result['cleanup_complete'])
    def test_resource_read_error_is_fail_closed(self):
        def broken(pids):raise PermissionError('unreadable proc')
        result=self.execute(["import time;print('{}',flush=True);time.sleep(30)"],rss_reader=broken)
        self.assertIn('resource_read_failure',[r['code'] for r in result['stop_reasons']]);self.assertTrue(result['cleanup_complete'])
    def test_output_byte_cap_is_fail_closed(self):
        result=self.execute(["import time;print('x'*10000,flush=True);time.sleep(30)"],output_bytes=3000)
        self.assertIn('bytes_limit',[r['code'] for r in result['stop_reasons']]);self.assertGreater((self.out/'case-00/stdout.jsonl').stat().st_size,3000)
    def test_retained_byte_read_failure(self):
        with mock.patch.object(probe,'retained_bytes',side_effect=OSError('storage unavailable')):
            result=self.execute(["import time;print('{}',flush=True);time.sleep(30)"])
        self.assertTrue({'resource_read_failure','supervisor_failure'} & {r['code'] for r in result['stop_reasons']})
    def test_no_polling_wait_or_shell(self):
        original=subprocess.Popen
        waits=[];shells=[]
        def start(*args,**kwargs):
            shells.append(kwargs.get('shell'));p=original(*args,**kwargs);wait=p.wait
            def tracked(*a,**kw):waits.append((a,kw));return wait(*a,**kw)
            p.wait=tracked;return p
        with mock.patch.object(probe.subprocess,'Popen',side_effect=start):self.execute(["print('{}')"])
        self.assertEqual(waits,[((),{})]);self.assertEqual(shells,[False])
    def test_corrupted_schedule_rejected_before_process(self):
        with self.assertRaises(ValueError):self.execute(["print('{}')"],[[0,0]])

    def test_unknown_exit_has_distinct_failure(self):
        original=subprocess.Popen
        def start(*args,**kwargs):
            p=original(*args,**kwargs);wait=p.wait
            def unknown(*a,**kw):wait(*a,**kw);return None
            p.wait=unknown;return p
        with mock.patch.object(probe.subprocess,'Popen',side_effect=start):result=self.execute(["print('{}')"])
        self.assertIn('unknown_exit',[r['code'] for r in result['stop_reasons']]);self.assertEqual(result['attempts'][0]['status'],'unknown_exit')
    def test_cleanup_read_failure_retains_ownership_until_retry_verified(self):
        original=probe.live_group_members;calls=[]
        def read(pids):
            calls.append(set(pids))
            if len(calls)==1:raise OSError('injected cleanup read failure')
            return original(pids)
        with mock.patch.object(probe,'live_group_members',side_effect=read):result=self.execute(["print('{}')"])
        self.assertGreaterEqual(len(calls),2);self.assertIn('cleanup_failure',[r['code'] for r in result['stop_reasons']]);self.assertTrue(result['cleanup_complete']);self.assertEqual(result['attempts'][0]['status'],'cleanup_failure')
    def test_concurrent_failures_create_one_canceled_abort_timer(self):
        original=threading.Timer;timers=[];barrier=threading.Barrier(8)
        def timer(*args,**kwargs):
            t=original(*args,**kwargs);timers.append(t);return t
        def reject(path):barrier.wait(timeout=2);raise ValueError('parallel validation failure')
        with mock.patch.object(probe.threading,'Timer',side_effect=timer):result=self.execute(["print('{}')"]*8,[list(range(8))],validator=reject)
        self.assertEqual(len([t for t in timers if t.interval==2]),1);self.assertTrue(all(not t.is_alive() for t in timers));self.assertTrue(result['cleanup_complete'])


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'repo';self.root.mkdir()
        for name in (probe.PROTOCOL,probe.PROSPECTIVE):
            dest=self.root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for name in probe.DOCS:
            dest=self.root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text('normative test document')
        for i in range(14):(self.root/f'source{i:02}.cs').write_text('source')
        for name in ('Program.cs','ProspectiveAdapter.csproj'):
            dest=self.root/'validation/prospective_adapter'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text('source')
        self.native=self.base/'native';self.native.mkdir()
        for name in ('MvsAnalyzer.Core.Tests.dll','MvsAnalyzer.Core.dll'):(self.native/name).write_bytes(b'native')
        install=self.base/'dotnet';install.mkdir();self.dotnet=install/'dotnet';self.dotnet.write_bytes(b'dotnet');self.dotnet.chmod(0o755)
        self.runtimes=[install/'shared/Microsoft.NETCore.App/8.0.31',install/'host/fxr/8.0.31']
        for d in self.runtimes:d.mkdir(parents=True)
        (self.runtimes[0]/'System.Private.CoreLib.dll').write_bytes(b'corelib');(self.runtimes[1]/'libhostfxr.so').write_bytes(b'fxr')
        self.history=self.base/'history.jsonl';self.history.write_text('{}\n');self.result=self.base/'historic-result.json';self.result.write_text('{}\n')
        self.build=self.base/'build.json';self.build.write_text('{"build":"passed"}');self.out=self.base/'out'
    def tearDown(self):self.tmp.cleanup()
    def prepare(self):
        def fake_execute(out,commands,batches,environment,**kwargs):
            # Only synthetic identity and validate-only records, no subprocesses.
            self.assertEqual([c[-1] if c[-1]=='identity' else c[-3] for c in commands],['identity','validate-only'])
            m=dict(root=str(self.root),native_dir=str(self.native),command=[str(self.dotnet),str(self.native/'MvsAnalyzer.Core.Tests.dll')],runtime_files=probe.files_in(self.runtimes[0])+probe.files_in(self.runtimes[1]),pins={})
            m['pins']=probe.replay.pin_paths([*self.root.rglob('*.cs'),*self.root.rglob('*.csproj'),*self.native.rglob('*'),*(Path(p) for p in m['runtime_files'])])
            identity=identity_row(m);valid=envelope('request_validated',mode='validate-only');valid.update(valid=True,completed=False,computationInvoked=False,frozenEngineeringRequestSha256=probe.REQUEST_SHA)
            for i,row in enumerate((identity,valid)):
                d=Path(out)/f'case-{i:02}';d.mkdir();(d/'stdout.jsonl').write_bytes(probe.canonical(row));(d/'stderr.log').write_bytes(b'')
            return {'stop_reasons':[],'attempts':[{'status':'completed'}]*2}
        with mock.patch.object(probe,'historical_reference',return_value={}),mock.patch.object(probe,'execute_schedule',side_effect=fake_execute):
            return probe.prepare(self.root,self.out,self.native,self.runtimes,[str(self.dotnet),str(self.native/'MvsAnalyzer.Core.Tests.dll')],self.history,self.result,self.build)
    def verify(self):
        with mock.patch.object(probe,'historical_reference',return_value={}):return probe.verify(self.out,probe.digest(self.out/'bind.json'))
    def test_complete_binding_verifies_without_numerical_execution(self):
        m=self.prepare();self.verify();self.assertIn(str(Path(probe.__file__).resolve()),m['pins']);self.assertEqual(probe.digest(self.out/'request.json'),probe.REQUEST_SHA)
    def test_source_native_runtime_and_request_corruption(self):
        self.prepare()
        for path in (self.root/'source00.cs',self.native/'MvsAnalyzer.Core.dll',self.runtimes[0]/'System.Private.CoreLib.dll',self.out/'request.json'):
            original=path.read_bytes();path.write_bytes(original+b'corrupt')
            with self.subTest(path=path),self.assertRaises(ValueError):self.verify()
            path.write_bytes(original)
    def test_inventory_addition_rejected(self):
        self.prepare();(self.native/'unbound.dll').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'native build file set'):self.verify()
    def test_pin_omission_rejected_even_if_resealed(self):
        self.prepare();m=probe.read_json(self.out/'bind.json');m['pins'].pop(str(self.root/'source00.cs'))
        (self.out/'bind.json').write_bytes(probe.canonical(m));(self.out/'bind.sha256').write_text(probe.digest(self.out/'bind.json'))
        with self.assertRaisesRegex(ValueError,'pin coverage'):self.verify()


class FinalAccountingTests(unittest.TestCase):
    def test_summary_reserve_prevents_boundary_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);m=dict(cpu_ids=list(range(8)),taskset='/usr/bin/taskset',command=['/dotnet','/native.dll'],request='/request',history_stdout='x',history_result='y')
            attempts=[]
            for i in range(11):
                d=out/f'case-{i:02}';d.mkdir();(d/'stdout.jsonl').write_text('{}\n')
                attempts.append(dict(index=i,status='completed',returncode=0,rss_samples=1,lifecycle_seconds=1,validation={'certified':True,'native_totals':{'processPeakWorkingSetBytes':1000}}))
            execution=dict(attempts=attempts,batches=[{'lifecycle_seconds':1}]*4,stop_reasons=[],rss_sample_count=1,peak_aggregate_rss_bytes=8000,cleanup_complete=True)
            real=probe.retained_bytes
            def size(path):return probe.LIMITS['retained_output_bytes']-probe.FINAL_METADATA_RESERVE+1 if Path(path)==out else real(path)
            with mock.patch.object(probe,'verify',return_value=m),mock.patch.object(probe,'historical_reference',return_value={}),mock.patch.object(probe,'execute_schedule',return_value=execution),mock.patch.object(probe,'retained_bytes',side_effect=size):
                result=probe.run(out,'0'*64,True)
            self.assertNotEqual(result['status'],'engineering_complete');self.assertFalse(result['admission']['budget_eligible']);self.assertTrue((out/'seal.json').exists())


if __name__=='__main__':unittest.main()
