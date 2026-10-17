"""Mocked engineering driver checks. No native invocation or benchmark data."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import variance_sensitivity as d


class CostRuleTests(unittest.TestCase):
    def test_fixed_rule_uses_slower_call(self):
        r=d.select_count([4,8],[1,2],[.5,1],3,30,2)
        self.assertEqual(r['T_seconds'],11)
        self.assertEqual(r['U_seconds'],28)
        self.assertEqual(r['P_seconds'],19.5)
        self.assertEqual(r['O_seconds'],10.5)
        self.assertEqual(r['H_seconds'],86)
        self.assertEqual(r['n_raw'],25)
        self.assertEqual(r['n'],25)
        self.assertFalse(r['science_execution_authorized'])

    def test_maximum_and_minimum_and_large_overhead(self):
        self.assertEqual(d.select_count([1,1],[0,0],[0,0],0,2,0)['n'],32)
        self.assertIsNone(d.select_count([100,100],[0,0],[0,0],0,200,0)['n'])
        self.assertIsNone(d.select_count([1,1],[0,0],[0,0],0,1000,0)['n'])

    def test_invalid_timing_or_incomplete_calls(self):
        for costs in ([1], [float('nan'),1],[-1,1],[True,1]):
            with self.assertRaises(ValueError): d.select_count(costs,[1,1],[1,1],1,10,0)
        with self.assertRaises(ValueError): d.select_count([0,0],[0,0],[0,0],0,0,0)


class CompletenessTests(unittest.TestCase):
    def callbacks(self):
        return [dict(Key=k,CallbackCount=1,Returned=True,Finite=True,
                     Converged=True if k=='initial-fit' or '/null-fit' in k or k.startswith('interval/') else None,
                     Exception=None) for k in d.expected_keys()]

    def test_exact_work_not_default_counts(self):
        rows=self.callbacks();self.assertEqual(len(rows),1103);d.validate_callbacks(rows)
        for track in ('within','between'):
            self.assertEqual(sum(r['Key'].startswith(track+'/reference/') for r in rows),199)
            for branch in ('null','alternative','grid'):
                self.assertEqual(sum(r['Key'].startswith(track+'/'+branch+'/') for r in rows),100)

    def test_failures_and_cache_replay_rejected(self):
        for field,value in [('CallbackCount',0),('CallbackCount',2),('Returned',False),('Exception',{'message':'failed'}),('Finite',False),('Converged',False)]:
            rows=self.callbacks();rows[0][field]=value
            with self.assertRaises(ValueError): d.validate_callbacks(rows)
        for key in ('within/reference/198','between/grid/99','within/observed','between/alternative/99'):
            rows=self.callbacks();next(r for r in rows if r['Key']==key)['Finite']=False
            with self.assertRaises(ValueError):d.validate_callbacks(rows)
        rows=self.callbacks()
        with self.assertRaises(ValueError):d.validate_callbacks(rows[:-1])
        rows[-1]=rows[-2]
        with self.assertRaises(ValueError):d.validate_callbacks(rows)

    def test_interval_boundary_retained_without_suppressing_work(self):
        rows=self.callbacks();rows[1]['Converged']=False;rows[1]['Finite']=False
        d.validate_callbacks(rows)  # The frozen protocol requires traversal, not 100 converged intervals.

    def test_identity_requires_all_fourteen_source_hashes_and_runtime(self):
        source={f'source{i}.cs':str(i) for i in range(14)}
        identity={'experimental':True,'sourceSha256':source,
                  'harnessAssembly':{'fileName':'harness.dll','sha256':'h'},
                  'coreAssembly':{'fileName':'core.dll','sha256':'c'},
                  'runtime':{'coreLibrarySha256':'runtime'}}
        start={'identity':identity,'protocolId':'round50-variance-cost-v1',
               'protocolSha256':d.PROTOCOL_SHA,'processorCount':1}
        manifest={'root':'/repo','native_dir':'/native','runtime_files':['/runtime/System.Private.CoreLib.dll'],
                  'pins':{**{'/repo/'+k:v for k,v in source.items()},'/native/harness.dll':'h',
                          '/native/core.dll':'c','/runtime/System.Private.CoreLib.dll':'runtime'}}
        d.validate_identity(start,manifest)
        del source['source13.cs']
        with self.assertRaises(ValueError):d.validate_identity(start,manifest)
        source['source13.cs']='13';identity['runtime']['coreLibrarySha256']='wrong'
        with self.assertRaises(ValueError):d.validate_identity(start,manifest)

    def test_strict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw'
            for value in ('{"kind":"start","kind":"complete"}\n','{"x":NaN}\n','{"x":Infinity}\n'):
                path.write_text(value)
                with self.assertRaises(ValueError):d.parse_jsonl(path)


class LifecycleTests(unittest.TestCase):
    def test_one_blocking_call_raw_logs_and_affinity(self):
        process=Mock(returncode=0);process.communicate.return_value=(b'raw stdout\n',b'raw stderr\n')
        with tempfile.TemporaryDirectory() as tmp, patch.object(d.subprocess,'Popen',return_value=process) as spawn, patch.object(d.os,'sched_getaffinity',return_value={4,5}), patch.object(d.time,'monotonic',side_effect=[10,10.2,12]):
            result=d.execute(tmp,['dotnet','harness.dll','cost'])
            self.assertEqual(result['status'],'completed');self.assertEqual(result['lifecycle_wall_seconds'],2)
            process.communicate.assert_called_once_with(timeout=179.8)
            self.assertTrue((Path(tmp)/'stdout.jsonl').exists());self.assertTrue((Path(tmp)/'stderr.log').exists())
            args=spawn.call_args.kwargs
            self.assertEqual(args['stdout'],subprocess.PIPE);self.assertEqual(args['stderr'],subprocess.PIPE)
            self.assertEqual((Path(tmp)/'stdout.jsonl').read_bytes(),b'raw stdout\n')
            self.assertEqual((Path(tmp)/'stderr.log').read_bytes(),b'raw stderr\n')
            self.assertTrue(args['start_new_session']);self.assertEqual(args['env']['MVS_DISABLE_BACKUPS'],'1')
            self.assertEqual(args['env']['DOTNET_PROCESSOR_COUNT'],'1')
            with patch.object(d.os,'sched_setaffinity') as affinity:args['preexec_fn']();affinity.assert_called_once_with(0,{4})

    def test_timeout_kills_owned_group_without_retry(self):
        process=Mock(returncode=-9);process.communicate.side_effect=[subprocess.TimeoutExpired('native',180,output=b'partial'),(b'partial completed capture',b'error bytes')]
        with tempfile.TemporaryDirectory() as tmp, patch.object(d.subprocess,'Popen',return_value=process) as spawn, patch.object(d.replay,'kill_group') as kill:
            result=d.execute(tmp,['native'])
            self.assertEqual(result['status'],'timeout');spawn.assert_called_once();kill.assert_called_once_with(process)
            self.assertEqual(process.communicate.call_args.kwargs,{'timeout':10})
            self.assertEqual((Path(tmp)/'stdout.jsonl').read_bytes(),b'partial completed capture')
            self.assertEqual((Path(tmp)/'stderr.log').read_bytes(),b'error bytes')

    def test_launch_failure_retained(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(d.subprocess,'Popen',side_effect=OSError('missing')):
            result=d.execute(tmp,['native']);self.assertEqual(result['status'],'failed');self.assertIsNone(result['returncode'])
            self.assertIn('missing',result['error'])

    def test_second_attempt_blocked_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(d,'verify',return_value={}), patch.object(d,'execute') as execute:
            (Path(tmp)/'started.json').write_text('{}')
            with self.assertRaises(ValueError):d.run_cost(tmp,'a'*64)
            execute.assert_not_called()

    def test_failure_sealed_and_no_count_selection(self):
        manifest={'command':['dotnet','harness.dll'],'root':'/repo'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(d,'verify',return_value=manifest), patch.object(d,'execute',return_value={'status':'timeout','lifecycle_wall_seconds':180}), patch.object(d,'select_count') as count:
            result=d.run_cost(tmp,'a'*64)
            self.assertEqual(result['status'],'timeout');count.assert_not_called()
            self.assertTrue((Path(tmp)/'seal.sha256').is_file());self.assertTrue((Path(tmp)/'evidence.zip').is_file())
            seal=d.read_json(Path(tmp)/'seal.json')
            self.assertEqual(seal['files']['result.json'],d.digest(Path(tmp)/'result.json'))

    def test_changed_sources_make_completed_cost_unrepresentative(self):
        manifest={'command':['dotnet','harness.dll'],'root':'/repo'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(d,'verify',side_effect=[manifest,ValueError('changed source')]), patch.object(d,'execute',return_value={'status':'completed'}), patch.object(d,'select_count') as count:
            result=d.run_cost(tmp,'a'*64)
            self.assertEqual(result['status'],'cost_unrepresentative');count.assert_not_called()

    def test_science_cli_requires_explicit_binding(self):
        with self.assertRaises(SystemExit):d.main(['run-science'])




class ScienceStatisticsTests(unittest.TestCase):
    def test_frozen_protocol_without_generating_data(self):
        plan=d.science_protocol(Path(__file__).resolve().parents[1])
        self.assertEqual(len(plan['tasks']),192)
        self.assertEqual(plan['tasks'][-1]['outer_seed_sequence'],[20261017,50,50001,5,31])

    def test_mock_rng_draw_order_and_t_scaling(self):
        import numpy as np
        class ToyRng:
            def __init__(self):self.calls=[]
            def standard_normal(self,n):self.calls.append(('normal',n));return np.ones(n)
            def standard_t(self,df,n):self.calls.append(('t',df,n));return np.ones(n)
        task={'condition_index':0,'replicate':0,'variance_seed':7,'outer_seed_sequence':[7]}
        condition={'latent_distribution':'gaussian','group0':{'mean':0,'within_sd':2,'between_sd':3},'group1':{'mean':1,'within_sd':4,'between_sd':5}}
        rng=ToyRng()
        with patch.object(d,'analytic_references',return_value={}):
            request,raw,_=d.generate_case({'conditions':[condition]},task,lambda seed:rng)
        self.assertEqual(rng.calls,[('normal',32),('normal',1280)])
        self.assertEqual(request['values'][:640],[5.]*640);self.assertEqual(request['values'][640:],[10.]*640)
        self.assertEqual(d.hashlib.sha256(raw).hexdigest(),request['dataSha256'])
        self.assertEqual(len(raw),1280*8)
        condition['latent_distribution']='standardized_t5';rng=ToyRng()
        with patch.object(d,'analytic_references',return_value={}):
            request,_,_=d.generate_case({'conditions':[condition]},task,lambda seed:rng)
        self.assertEqual(rng.calls,[('t',5,32),('t',5,1280)])
        self.assertAlmostEqual(request['values'][0],5*(3/5)**.5)

    def test_analytic_toy_raw_reference_identity_and_scale(self):
        import numpy as np
        residual=np.arange(40,dtype=float)-19.5
        base=np.arange(16,dtype=float)[:,None]+residual[None,:]
        values=np.stack([base,base])
        condition={'gaussian_within_reference_applicable':True,'gaussian_between_reference_applicable':True}
        refs=d.analytic_references(values,condition)
        self.assertAlmostEqual(refs['within']['statistic'],1)
        self.assertAlmostEqual(refs['within']['p'],1)
        self.assertEqual(refs['within']['df1'],624);self.assertEqual(refs['between']['df1'],15)
        self.assertEqual(refs['between']['state'],'nonreject')
        values[1]=np.arange(16)[:,None]+2*residual[None,:]
        refs=d.analytic_references(values,condition)
        self.assertAlmostEqual(refs['within']['statistic'],4)
        self.assertEqual(refs['within']['state'],'reject')
        self.assertAlmostEqual(refs['between']['statistic'],1)
        condition['gaussian_between_reference_applicable']=False
        self.assertEqual(d.analytic_references(values,condition)['between']['reason'],'reference_not_applicable')

    def test_wilson_and_cp_boundaries_independent_formulas(self):
        self.assertAlmostEqual(d.wilson(0)[1],.1071791982550706)
        self.assertAlmostEqual(d.wilson(32)[0],1-.1071791982550706)
        self.assertAlmostEqual(d.clopper_pearson(0,32)[1],1-.0125**(1/32))
        self.assertAlmostEqual(d.clopper_pearson(32,32)[0],.0125**(1/32))

    def test_family_missing_states_and_fixed_paired_denominator(self):
        self.assertEqual(d.family_state(['reject','unavailable']),'reject')
        self.assertEqual(d.family_state(['nonreject','unavailable']),'unavailable')
        self.assertEqual(d.family_state(['nonreject','nonreject']),'nonreject')
        a=['reject']*4+['unavailable']*4+['nonreject']*24
        b=['nonreject']*4+['reject']*4+['nonreject']*24
        out=d.paired_summary(a,b)
        self.assertEqual(out['operational_2x2'],[[24,4],[4,0]])
        self.assertEqual(sum(map(sum,out['paired_3x3'])),32)
        self.assertEqual(out['left']['failure_bounds'],[.125,.25])
        self.assertEqual(out['difference_left_minus_right'],0)
        self.assertLess(out['pointwise_conservative_95_difference_interval'][0],0)
        with self.assertRaises(ValueError):d.paired_summary(a[:-1],b[:-1])

    def test_fp_corruption_and_nonfinite(self):
        good={'classification':'finite','value':.25,'bits':'3fd0000000000000'}
        self.assertEqual(d.decode_fp(good),.25)
        bad=copy.deepcopy(good);bad['value']=.5
        with self.assertRaises(ValueError):d.decode_fp(bad)
        bad=copy.deepcopy(good);bad['classification']='nan'
        with self.assertRaises(ValueError):d.decode_fp(bad)
        self.assertTrue(d.math.isnan(d.decode_fp({'classification':'nan','value':None,'bits':'7ff8000000000000'})))

    def test_all_missing_summary_keeps192_and_both_components(self):
        plan=d.science_protocol(Path(__file__).resolve().parents[1]);records=[d.empty_science_record(t) for t in plan['tasks']]
        result=d.science_summaries(records,plan)
        self.assertEqual(result['requested'],192)
        for c in result['conditions']:
            self.assertEqual(c['global_variance_minus_legacy']['paired_3x3'][2][2],32)
            self.assertEqual(c['both_components_reject']['unavailable'],32)
            self.assertEqual(c['components']['within']['failure_bounds'],[0,1])


class ScienceEnvelopeTests(unittest.TestCase):
    def trace(self,observations=None):
        zero={'attempted':0,'callbacks':0,'returned':0,'finite':0,'nonfinite':0,'converged':0,'exceptions':0}
        return {'cachedRequests':0,'callbackCount':0,'Begins':0,'Finishes':0,'Disposals':0,'RestoreHits':0,
                'initial':dict(zero),'interval':dict(zero),'tracks':[{'track':t,**{k:dict(zero) for k in ('nullFit','observed','reference','nullEvaluation','alternative','grid')}} for t in ('within','between')],
                'sourceDerivedFitEntryUpperLimit':2103,'sourceDerivedOptimizerInvocationUpperLimit':4206}

    def example(self):
        request={'condition':0,'replicate':0,'seed':50000000,'dataSha256':'a'*64}
        payload={**request,'rawRows':1280,'retainedRows':None,'entities':None,'groupCounts':None,'report':None,'legacy':None,
                 'trace':self.trace(),'buildError':{'message':'bad input'},'varianceError':None,'legacyError':None,'inputStatus':'input_retention_mismatch'}
        row={'kind':'case_complete',**request,'payload':payload,'buildTiming':None,'runTiming':None,'legacyTiming':None,
             'serializationTiming':{'WallSeconds':.1,'CpuSeconds':.1,'PeakWorkingSetBytes':100}}
        return request,row

    def test_retention_failure_is_not_infrastructure_failure(self):
        request,row=self.example();states=d.validate_science_case(row,request,[],[])
        self.assertEqual(states['variance_family'],'unavailable');self.assertEqual(states['legacy_family'],'unavailable')

    def test_corrupt_identity_trace_and_envelope_rejected(self):
        request,row=self.example()
        bad=copy.deepcopy(row);bad['dataSha256']='b'*64
        with self.assertRaises(ValueError):d.validate_science_case(bad,request,[],[])
        bad=copy.deepcopy(row);bad['payload']['trace']['RestoreHits']=1
        with self.assertRaises(ValueError):d.validate_science_case(bad,request,[],[])
        bad=copy.deepcopy(row);bad['payload']['trace']['interval']['attempted']=100
        with self.assertRaises(ValueError):d.validate_science_case(bad,request,[],[])
        bad=copy.deepcopy(row);p=bad['payload'];p.update(inputStatus='retained_exactly',buildError=None,retainedRows=1280,entities=32,groupCounts=[16,16]);p['trace'].update(Begins=1,Disposals=1)
        with self.assertRaises(ValueError):d.validate_science_case(bad,request,[],[{'key':'result','hit':False}])

    def test_mock_complete_report_and_corrupt_reference_counts(self):
        def fp(v):return {'classification':'finite','value':v,'bits':d.struct.pack('>d',v).hex()}
        request,row=self.example();p=row['payload'];p.update(inputStatus='retained_exactly',buildError=None,retainedRows=1280,entities=32,groupCounts=[16,16])
        observations=[]
        for key in d.expected_keys():
            fit=key=='initial-fit' or key.startswith('interval/') or key.endswith('/null-fit')
            observations.append({'Key':key,'CallbackCount':1,'Returned':True,'Finite':True,'Converged':True if fit else None,'Value':{} if fit else fp(2. if key.endswith('/observed') else 1.),'Exception':None})
        def branch(prefix):
            rs=[r for r in observations if r['Key'].startswith(prefix)]
            return {'attempted':len(rs),'callbacks':len(rs),'returned':len(rs),'finite':len(rs),'nonfinite':0,'converged':sum(r['Converged'] is True for r in rs),'exceptions':0}
        trace=p['trace'];trace.update(cachedRequests=1103,callbackCount=1103,Begins=1,Finishes=1,Disposals=1,initial=branch('initial-fit'),interval=branch('interval/'))
        for tr in trace['tracks']:
            for name,suffix in [('nullFit','null-fit'),('observed','observed'),('reference','reference/'),('nullEvaluation','null/'),('alternative','alternative/'),('grid','grid/')]:tr[name]=branch(tr['track']+'/'+suffix)
        tracks=[{'track':t,'pValue':fp(.005),'adjustedP':fp(.01),'referenceReplications':199,'referenceFailures':0,'evaluationReplications':100,'nullFailures':0,'alternativeFailures':0} for t in ('within','between')]
        p['report']={'seed':request['seed'],'alpha':fp(.05),'tracks':tracks}
        metrics=[{'index':i,'key':key,'applicable':True,'observedStatus':'available','firstCount':16,'secondCount':16,'p':fp(.5),'adjustedP':fp(1.),'reject':False,
                  'groupAvailability':[{'Group':g,'RetainedEntities':16,'UsableEntities':16,'ExcludedEntities':0,'ExclusionReasons':{}} for g in ('G0','G1')]} for i,key in enumerate(d.LEGACY_KEYS)]
        p['legacy']={'familySize':12,'metrics':metrics,'anyReject':False}
        states=d.validate_science_case(row,request,observations,[{'key':'result','hit':False}])
        self.assertEqual(states['variance_family'],'reject');self.assertEqual(states['legacy_family'],'nonreject')
        for field,value in [('referenceFailures',1),('referenceReplications',198),('evaluationReplications',99),('nullFailures',1),('alternativeFailures',1)]:
            bad=copy.deepcopy(row);bad['payload']['report']['tracks'][0][field]=value
            with self.assertRaises(ValueError):d.validate_science_case(bad,request,observations,[{'key':'result','hit':False}])
        bad=copy.deepcopy(row);bad['payload']['legacy']['metrics'][0]['key']='wrong'
        with self.assertRaises(ValueError):d.validate_science_case(bad,request,observations,[{'key':'result','hit':False}])
        bad=copy.deepcopy(row);bad['payload']['legacy']=None
        with self.assertRaises(ValueError):d.validate_science_case(bad,request,observations,[{'key':'result','hit':False}])
        bad=copy.deepcopy(row);bad['payload']['report']['tracks'][0]['pValue']=fp(.01);bad['payload']['report']['tracks'][0]['adjustedP']=fp(.02)
        with self.assertRaises(ValueError):d.validate_science_case(bad,request,observations,[{'key':'result','hit':False}])

    def test_science_second_attempt_blocked_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'science_verify',return_value={}),patch.object(d,'science_execute') as execute:
            (Path(tmp)/'started.json').write_text('{}')
            with self.assertRaises(ValueError):d.science_run(tmp,'a'*64)
            execute.assert_not_called()

    def test_cleanup_failure_never_seals(self):
        result={'cleanup_complete':False,'completed_cases':0,'stop_reason':'cleanup_timeout'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'science_verify',return_value={}),patch.object(d,'science_execute',return_value=result),patch.object(d,'science_seal') as seal:
            (Path(tmp)/'protocol.json').write_text('{}')
            response=d.science_run(tmp,'a'*64)
            self.assertEqual(response['status'],'cleanup_failed_unsealed');seal.assert_not_called()
            self.assertTrue((Path(tmp)/'cleanup-failure.json').exists())


class ScienceSupervisorTests(unittest.TestCase):
    def plan(self):
        return {'tasks':[{'task_index':i,'condition_index':i%6,'replicate':i//6,'variance_seed':i} for i in range(192)]}

    def fake_generate(self,plan,task):
        # Synthetic placeholder bytes only; no PRNG and no native analysis.
        request={'condition':task['condition_index'],'replicate':task['replicate'],'seed':task['variance_seed'],'dataSha256':'a'*64,'values':[]}
        return request,b'toy fixture bytes',{}

    def factory(self,hang=False):
        import io
        import threading
        from collections import deque
        processes=[]
        class Fake:
            def __init__(self,*args,**kwargs):
                self.pid=10000+len(processes);self.returncode=None;self.count=0;self.killed=threading.Event();self.pending=deque()
                self.stdout=self;self.stdin=self;self.stderr=io.BytesIO();self.kwargs=kwargs
                self.emit({'kind':'worker_ready','identity':{}});processes.append(self)
            def emit(self,row):self.pending.append(json.dumps(row).encode()+b'\n')
            def write(self,encoded):
                r=json.loads(encoded);self.count+=1;self.emit({'kind':'case_start',**r,'rawRows':1280})
                if not hang:self.emit({'kind':'case_complete',**r,'runTiming':{},'payload':{}})
                return len(encoded)
            def flush(self):pass
            def readline(self,limit):
                if self.pending:return self.pending.popleft()
                if hang:self.killed.wait()
                return b''
            def read(self):return b''
            def close(self):self.emit({'kind':'worker_complete','cases':self.count,'runCallCount':self.count,'legacyCallCount':self.count})
            def wait(self):self.returncode=-9 if self.killed.is_set() else 0;return self.returncode
            def poll(self):return self.returncode
        return Fake,processes

    def test_eight_persistent_workers_process192_once_using_pipes(self):
        Fake,processes=self.factory()
        states=d.empty_science_record({})['states']
        m={'taskset':'taskset','command':['dotnet','harness.dll'],'root':'/repo'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'generate_case',side_effect=self.fake_generate),patch.object(d.subprocess,'Popen',side_effect=Fake),patch.object(d,'validate_science_identity'),patch.object(d,'validate_science_case',return_value=states),patch.object(d.os,'sched_getaffinity',return_value=set(range(8))),patch.object(d.replay,'group_rss',return_value=0):
            result=d.science_execute(tmp,m,self.plan())
        self.assertEqual(result['status'],'completed');self.assertEqual(result['completed_cases'],192)
        self.assertEqual(len(processes),8);self.assertEqual(sum(p.count for p in processes),192)
        self.assertEqual(sorted(i for w in result['workers'] for i in w['completed_indices']),list(range(192)))
        for p in processes:
            self.assertEqual(p.kwargs['stdout'],subprocess.PIPE);self.assertEqual(p.kwargs['stdin'],subprocess.PIPE)
            self.assertEqual(p.kwargs['stderr'],subprocess.PIPE);self.assertTrue(p.kwargs['start_new_session'])
            self.assertEqual(p.kwargs['env']['DOTNET_PROCESSOR_COUNT'],'1')

    def test_timeout_kills_owned_workers_and_keeps_all192(self):
        Fake,processes=self.factory(hang=True)
        m={'taskset':'taskset','command':['dotnet','harness.dll'],'root':'/repo'}
        limits={**d.SCIENCE_LIMITS,'wall_seconds':.05,'cleanup_seconds':1}
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'SCIENCE_LIMITS',limits),patch.object(d,'generate_case',side_effect=self.fake_generate),patch.object(d.subprocess,'Popen',side_effect=Fake),patch.object(d,'validate_science_identity'),patch.object(d.os,'sched_getaffinity',return_value=set(range(8))),patch.object(d.replay,'group_rss',return_value=0),patch.object(d.replay,'kill_group',side_effect=lambda p:p.killed.set()):
            result=d.science_execute(tmp,m,self.plan())
        self.assertEqual(result['status'],'incomplete');self.assertEqual(result['stop_reason'],'wall_timeout')
        self.assertEqual(len(result['records']),192);self.assertEqual(result['completed_cases'],0)
        self.assertTrue(result['cleanup_complete']);self.assertTrue(all(p.killed.is_set() for p in processes))

    def test_evidence_threshold_stops_before_starting_native(self):
        limits={**d.SCIENCE_LIMITS,'package_max_bytes':100}
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'SCIENCE_LIMITS',limits),patch.object(d,'generate_case',side_effect=self.fake_generate),patch.object(d.subprocess,'Popen') as spawn,patch.object(d.os,'sched_getaffinity',return_value=set(range(8))),patch.object(d.replay,'group_rss',return_value=0):
            (Path(tmp)/'existing-metadata').write_bytes(b'x'*200)
            result=d.science_execute(tmp,{},self.plan())
            spawn.assert_not_called()
        self.assertEqual(result['stop_reason'],'evidence_cap');self.assertEqual(result['requested_cases'],192)
        self.assertEqual(result['completed_cases'],0);self.assertGreaterEqual(result['logical_evidence_bytes_with_reserves'],200)


if __name__=='__main__':unittest.main()
