"""Deterministic contract tests, not scientific outcomes; no native/RNG invocation."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import unittest

from scipy.stats import binom
import prospective_cases as cases
import prospective_outcomes as d


def fp(x):
    return {'classification':'finite' if math.isfinite(x) else 'nan',
            'value':x if math.isfinite(x) else None,'bits':struct.pack('>d',x).hex()}


def provenance():
    root=d.design.ROOT
    project=(root/'validation/prospective_case_adapter/ProspectiveCaseAdapter.csproj').read_text()
    sources=re.findall(r'LogicalName="source/([^"]+)"',project)
    adapters=['validation/prospective_case_adapter/Program.cs','validation/prospective_case_adapter/ProspectiveCaseAdapter.csproj']
    return {'identity':{'experimental':True,'sourceSha256':{p:d.design.sha256_file(root/p) for p in sources},
                        'harnessAssembly':{'sha256':'a'*64},'coreAssembly':{'sha256':'b'*64},
                        'runtime':{'coreLibrarySha256':'c'*64}},
            'adapterSourceSha256':{p:d.design.sha256_file(root/p) for p in adapters},
            'configSha256':cases.PROTOCOL_SHA256,'adapterScope':'test_only_general_case_seam_no_study_admission'}


def trace(observations, finishes=1):
    def branch(prefix):
        rs=[o for o in observations if o['Key'].startswith(prefix)]
        return {'attempted':len(rs),'callbacks':sum(o['CallbackCount'] for o in rs),
                'returned':sum(o['Returned'] for o in rs),'finite':sum(o['Finite'] is True for o in rs),
                'nonfinite':sum(o['Returned'] and o['Finite'] is False for o in rs),
                'converged':sum(o['Converged'] is True for o in rs),'exceptions':sum(not o['Returned'] for o in rs)}
    return {'cachedRequests':len(observations),'callbackCount':len(observations),
            'Begins':1,'Finishes':finishes,'Disposals':1,'RestoreHits':0,
            'initial':branch('initial-fit'),'interval':branch('interval/'),
            'tracks':[{'track':t,**{name:branch(t+'/'+suffix) for name,suffix in
                [('nullFit','null-fit'),('observed','observed'),('reference','reference/'),
                 ('nullEvaluation','null/'),('alternative','alternative/'),('grid','grid/')]}} for t in ('within','between')],
            'sourceDerivedFitEntryUpperLimit':2103,'sourceDerivedOptimizerInvocationUpperLimit':4206}


def fixture(cell=0, rep=0, finite=199, exceed=3):
    n,m=(16,40) if cell<10 else (8,5)
    request=cases.make_case([20.]*(2*n*m),cell,rep,purpose='planned_case')
    raw=json.dumps(request,separators=(',',':')).encode()
    observations=[]
    for key in d.expected_keys():
        fit=key=='initial-fit' or key.startswith('interval/') or key.endswith('/null-fit')
        if not fit and any('/'+b+'/' in key for b in ('null','alternative','grid')) and finite<180:
            continue
        x=2. if key.endswith('/observed') else 1.
        if '/reference/' in key:
            i=int(key.rsplit('/',1)[1]);x=float('nan') if i>=finite else 2. if i<exceed else 1.
        observations.append({'Key':key,'CallbackCount':1,'Returned':True,'Finite':True if fit else math.isfinite(x),
                             'Converged':True if fit else None,'AtBoundary':False if fit else None,
                             'Value':{'means':[fp(20.),fp(20.)],'within':[fp(1.),fp(1.)],'between':[fp(1.),fp(1.)],
                                      'negativeLogLikelihood':fp(10.),'converged':True,'atBoundary':False,'method':'synthetic','iterations':1} if fit else fp(x),'Exception':None})
    p=(1+exceed)/(finite+1) if finite>=180 else float('nan')
    tracks=[{'track':t,'statistic':fp(2.),'pValue':fp(p),'adjustedP':fp(min(1,2*p) if math.isfinite(p) else p),
             'effectSdMultiplier':fp(2.),'referenceReplications':finite,'referenceFailures':199-finite,
             'evaluationReplications':100,'nullFailures':0 if finite>=180 else 100,
             'alternativeFailures':0 if finite>=180 else 100,
             'verdict':'difference' if p<.025 else 'insufficient'} for t in ('within','between')]
    metrics=[{'index':i,'key':key,'applicable':True,'observedStatus':'available','firstCount':n,'secondCount':n,
              'p':fp(.5),'adjustedP':fp(1.),'reject':False,
              'groupAvailability':[{'Group':g,'RetainedEntities':n,'UsableEntities':n,'ExcludedEntities':0} for g in ('G0','G1')]}
             for i,key in enumerate(d.LEGACY_KEYS)]
    payload={**{k:request[k] for k in d.IDENTITY_FIELDS},'schema':'mvs-prospective-case-payload/v1',
             'rawRows':2*n*m,'retainedRows':2*n*m,'entities':2*n,'groupCounts':[n,n],
             'report':{'engineVersion':'1.6.2','seed':request['native_seed'],'alpha':fp(.05),'tracks':tracks},
             'legacy':{'familySize':12,'alpha':.05,'method':'production Metrics/MannWhitneyP/DecisionPolicy.Adjust','metrics':metrics,'anyReject':False},
             'trace':trace(observations),'buildError':None,'varianceError':None,'legacyError':None,'inputStatus':'retained_exactly'}
    prov=provenance()
    envelope={'schema':'mvs-prospective-case-result/v1','protocol_id':d.design.PROTOCOL_ID,
              'protocol_sha256':cases.PROTOCOL_SHA256,'methods':d.METHODS[:],'kind':'case_complete','mode':'run-case',
              'requestSha256':hashlib.sha256(raw).hexdigest(),'operationCounts':{'fixtureMaterializationCount':0,
                'buildCallCount':1,'runCallCount':1,'legacyCallCount':1,'payloadSerializationCount':1,'directGenerateCallCount':0,'directFitCallCount':0},
              'operationCountScope':'adapter_entry_calls_only_nested_production_calls_not_instrumented',
              'provenance':prov,'payload':payload,'buildTiming':None,'runTiming':None,'legacyTiming':None,
              'completed':True,'status':'paired_methods_returned','scientificStudyExecuted':True,
              'caseWallSeconds':1.,'processTotalCpuSeconds':1.,'processPeakWorkingSetBytes':100,'serializedUtf8Bytes':100}
    return raw,envelope,observations,[{'key':'result','hit':False}],prov


def normalized(rep, within='nonreject', between='nonreject', summary='nonreject', cell=0):
    metrics=[summary]*12
    states={'within':within,'between':between,'variance_family':d.family_state([within,between]),
            'summary_family':summary,'legacy_metrics':metrics}
    return {'case_id':cases.case_identity(cell,rep),'cell_index':cell,'replication_zero_based':rep,'states':states}


class ExactInferenceTests(unittest.TestCase):
    def test_cp_extremes_and_binomial_tail_oracle(self):
        for a in (.025,.0125,.025/31):
            self.assertAlmostEqual(d.clopper_pearson(0,1000,a)[1],1-a**(1/1000),places=14)
            self.assertAlmostEqual(d.clopper_pearson(1000,1000,a)[0],a**(1/1000),places=14)
            for k in (1,43,50,74,999):
                lo,hi=d.clopper_pearson(k,1000,a)
                self.assertAlmostEqual(binom.sf(k-1,1000,lo),a,places=12)
                self.assertAlmostEqual(binom.cdf(k,1000,hi),a,places=12)
        for k,alpha in ((43,.025),(74,.05)):
            self.assertGreater(d.clopper_pearson(k,1000,.025/31)[0],alpha)
            self.assertLessEqual(d.clopper_pearson(k-1,1000,.025/31)[0],alpha)
        for k,n in ((0,0),(True,1000),(11,10),(-1,10)):
            with self.assertRaises(ValueError): d.clopper_pearson(k,n)

    def test_unknown_and_hand_count_rates(self):
        r=d.rate_summary(['reject']*30+['nonreject']*70+['unavailable']*900)
        self.assertEqual((r['known'],r['reject'],r['unknown']),(100,30,900))
        self.assertEqual(r['conditional_on_valid_rate'],.3)
        self.assertEqual(r['failure_inclusive_rate_bounds'],[.03,.93])
        self.assertAlmostEqual(binom.sf(29,1000,r['failure_inclusive_cp'][0]),.025)
        unknown=d.rate_summary(['unavailable']*1000)
        self.assertIsNone(unknown['conditional_on_valid_rate']);self.assertIsNone(unknown['conditional_on_valid_cp'])
        self.assertEqual(unknown['failure_inclusive_cp'],[0.,1.])
        for s in ('reject','nonreject'):
            r=d.rate_summary([s]*1000);self.assertEqual(r['conditional_on_valid_rate'],float(s=='reject'))

    def test_paired_discordances_and_independent_failures(self):
        left=['reject']*4+['nonreject']*2+['reject']*3+['unavailable']*5+['nonreject']*986
        right=['nonreject']*4+['reject']*2+['unavailable']*3+['reject']*5+['nonreject']*986
        r=d.paired_summary(left,right)
        self.assertEqual((r['complete_pairs'],r['incomplete_pairs'],r['gaussian_only'],r['summary_only']),(992,8,4,2))
        self.assertEqual(r['conditional_on_complete_difference'],2/992)
        self.assertEqual(r['failure_inclusive_difference_bounds'],[-.006,.01])
        # Independent binomial-tail root oracle, not another beta formula.
        from scipy.optimize import brentq
        lower=lambda k,n: 0. if k==0 else brentq(lambda p:binom.sf(k-1,n,p)-.0125,0,1)
        upper=lambda k,n: 1. if k==n else brentq(lambda p:binom.cdf(k,n,p)-.0125,0,1)
        self.assertAlmostEqual(r['conditional_on_complete_conservative_95_interval'][0],lower(4,992)-upper(2,992),places=10)
        self.assertAlmostEqual(r['failure_inclusive_conservative_95_interval'][1],upper(12,1000)-lower(2,1000),places=10)
        all_unknown=d.paired_summary(['unavailable']*1000,['unavailable']*1000)
        self.assertIsNone(all_unknown['conditional_on_complete_difference'])
        self.assertEqual(all_unknown['failure_inclusive_conservative_95_interval'],[-1.,1.])


class ReportTests(unittest.TestCase):
    def report(self,rows,partial=True):
        return d.aggregate_validated(rows,cases.frozen_config(),allow_partial=partial,evidence_role='synthetic_contract_only')

    def test_all_unattempted_explicit_incomplete_all_cells_and_31_nulls(self):
        with self.assertRaises(ValueError): self.report([],False)
        r=self.report([])
        self.assertEqual((len(r['cells']),len(r['null_endpoints']),r['joint_bound_count']),(12,31,62))
        self.assertEqual(r['status'],'incomplete');self.assertFalse(r['scientific_evidence']);self.assertFalse(r['execution_ready'])
        self.assertEqual({x['nominal_alpha'] for x in r['null_endpoints']},{.025,.05})
        self.assertTrue(all(x['planned']==1000 and x['unknown']==1000 and x['one_tail_error']==.025/31 for x in r['null_endpoints']))
        self.assertEqual(len(r['cells'][4]['target_detection']),3)
        self.assertTrue(r['cells'][1]['paired_family_difference']['negative_control_distinct_null_states'])

    def test_partial_counts_and_duplicate_out_of_plan_fail_closed(self):
        rows=[normalized(0,'reject','unavailable'),normalized(1,'unavailable','unavailable','reject')]
        r=self.report(rows)
        c=r['cells'][0];self.assertEqual((c['attempted'],c['unattempted']),(2,998))
        self.assertEqual(c['family_operating_outcomes']['variance_family']['failure_inclusive_rate_bounds'],[.001,1.])
        for bad in (rows+[rows[0]], [{**rows[0],'replication_zero_based':1000}], [{**rows[0],'case_id':'fake'}]):
            with self.assertRaises(ValueError): self.report(bad)
        bad=copy.deepcopy(rows);bad[0]['states']['variance_family']='nonreject'
        with self.assertRaises(ValueError):self.report(bad)

    def test_full_attempt_accounting_has_no_scientific_go(self):
        rows=[normalized(r,cell=c) for c in range(12) for r in range(1000)]
        out=self.report(rows,False)
        self.assertEqual(out['status'],'complete_attempt_accounting')
        self.assertEqual(out['scientific_acceptance'],'not_assessed_no_go_gate')
        self.assertTrue(all(x['inflation_status']=='inconclusive_not_validation' for x in out['null_endpoints']))


class NativeEnvelopeTests(unittest.TestCase):
    def validate(self,f):
        raw,row,obs,tries,prov=f
        return d.validate_native_result(row,raw,prov,obs,tries,0)

    def test_strict_boundary_and_actual_finite_grid_including_ties(self):
        for finite,k,expected in ((199,3,'reject'),(199,4,'nonreject'),(180,3,'reject'),(180,4,'nonreject'),(179,0,'unavailable')):
            with self.subTest(finite=finite,k=k):
                states=self.validate(fixture(finite=finite,exceed=k))
                self.assertEqual(states['within'],expected)
        self.assertEqual(self.validate(fixture(cell=10))['summary_family'],'nonreject')

    def test_contradictory_p_counts_ties_and_missing_callbacks(self):
        original=fixture()
        for field,value in [('referenceReplications',198),('referenceFailures',1),('evaluationReplications',99),('nullFailures',1),('effectSdMultiplier',fp(1.5)),('pValue',fp(.015))]:
            f=copy.deepcopy(original);f[1]['payload']['report']['tracks'][0][field]=value
            with self.assertRaises(ValueError):self.validate(f)
        f=copy.deepcopy(original);f[1]['payload']['report']['tracks'][0].update(pValue=fp(.005),adjustedP=fp(.01))
        with self.assertRaises(ValueError):self.validate(f) # inclusive ties were three, not zero
        for change in ('duplicate','missing'):
            f=copy.deepcopy(original)
            if change=='duplicate':f[2][-1]=f[2][-2]
            else:f[2].pop()
            with self.assertRaises(ValueError):self.validate(f)

    def test_fit_diagnostics_must_match_encoded_fit(self):
        for key,value in [('converged',False),('atBoundary',True),('negativeLogLikelihood',fp(float('nan')))]:
            f=fixture();event=next(o for o in f[2] if o['Key']=='within/null-fit');event['Value'][key]=value
            with self.assertRaises(ValueError):self.validate(f)
        f=fixture();f[2][0]['Converged']=1
        with self.assertRaises(ValueError):self.validate(f)

    def test_method_protocol_source_seed_hash_exit_and_unknown_schema_reject(self):
        original=fixture()
        for key,value in [('methods',['fake']),('protocol_sha256','0'*64),('requestSha256','0'*64),('completed',False),('extra',1)]:
            f=copy.deepcopy(original);f[1][key]=value
            with self.assertRaises(ValueError):self.validate(f)
        for key,value in [('native_seed',1),('ordered_binary64_sha256','0'*64),('case_id','bad'),('rawRows',1)]:
            f=copy.deepcopy(original);f[1]['payload'][key]=value
            with self.assertRaises(ValueError):self.validate(f)
        f=copy.deepcopy(original);f[1]['provenance']=copy.deepcopy(f[4]);f[1]['provenance']['identity']['coreAssembly']['sha256']='0'*64
        with self.assertRaises(ValueError):self.validate(f)
        raw,row,obs,tries,prov=original
        for code in (None,1,2,True):
            with self.assertRaises(ValueError):d.validate_native_result(row,raw,prov,obs,tries,code)

    def test_methods_may_fail_independently_and_unknown_members_preserved(self):
        f=fixture();p=f[1]['payload'];p.update(report=None,varianceError={'type':'test','message':'failure'},trace=trace([],0));f[2].clear()
        f[1]['status']='paired_method_failure_retained'
        s=self.validate(f);self.assertEqual((s['variance_family'],s['summary_family']),('unavailable','nonreject'))
        f=fixture();p=f[1]['payload'];p.update(legacy=None,legacyError={'type':'test','message':'failure'});f[1]['status']='paired_method_failure_retained'
        s=self.validate(f);self.assertEqual((s['variance_family'],s['summary_family']),('reject','unavailable'))
        f=fixture();metric=f[1]['payload']['legacy']['metrics'][0]
        metric.update(applicable=False,p=fp(float('nan')),adjustedP=fp(float('nan')),observedStatus='insufficient_usable_entities',firstCount=3)
        metric['groupAvailability'][0].update(UsableEntities=3,ExcludedEntities=13)
        self.assertEqual(self.validate(f)['summary_family'],'unavailable')
        other=f[1]['payload']['legacy']['metrics'][1];other.update(p=fp(.001),adjustedP=fp(.012),reject=True)
        f[1]['payload']['legacy']['anyReject']=True
        self.assertEqual(self.validate(f)['summary_family'],'reject')

    def test_early_recording_failure_retains_other_route_without_success_relaxation(self):
        for begins,disposals,finishes in ((0,0,0),(1,0,0),(1,1,0)):
            f=fixture();p=f[1]['payload'];p.update(report=None,varianceError={'type':'test','message':'recording failure'},trace=trace([],finishes))
            p['trace'].update(Begins=begins,Disposals=disposals);f[2].clear();f[3].clear()
            f[1]['status']='paired_method_failure_retained'
            s=self.validate(f)
            self.assertEqual((s['variance_family'],s['summary_family']),('unavailable','nonreject'))
        f=fixture();f[1]['payload'].update(report=None,varianceError={'type':'test','message':'Finish or Dispose failure'})
        f[1]['status']='paired_method_failure_retained'
        self.assertEqual(self.validate(f)['summary_family'],'nonreject')
        for field in ('Begins','Finishes','Disposals'):
            f=fixture();f[1]['payload']['trace'][field]=0
            with self.assertRaises(ValueError):self.validate(f)
        f=fixture();f[3].clear()
        with self.assertRaises(ValueError):self.validate(f)

    def test_bundle_retains_failure_and_does_not_accept_engineering_ids(self):
        raw,row,obs,tries,prov=fixture()
        attempt={'request_json':raw.decode(),'exit_code':-9,'status':'timeout','result':None,'observations':obs[:2],
                 'tries':tries,'failure':'timeout','artifact_sha256':{'stdout':'a'*64,'stderr':'b'*64}}
        bundle={'schema':'mvs-prospective-outcome-bundle/v1','protocol_sha256':cases.PROTOCOL_SHA256,
                'methods':d.METHODS[:],'evidence_role':'synthetic_contract_only','attempts':[attempt]}
        out=d.analyze_bundle(bundle,prov,allow_partial=True)
        self.assertEqual(out['attempted_datasets'],1);self.assertEqual(out['retained_attempts'][0],attempt)
        with self.assertRaises(ValueError):d.analyze_bundle(bundle,prov)
        engineering=copy.deepcopy(bundle)
        engineering['attempts'][0]['request_json']=json.dumps(cases.make_case([20.]*1280,0,0))
        with self.assertRaises(ValueError):d.analyze_bundle(engineering,prov,allow_partial=True)
        complete=copy.deepcopy(bundle);complete['attempts'][0].update(exit_code=0,status='native_complete',result=row,observations=obs,failure=None)
        self.assertEqual(d.analyze_bundle(complete,prov,allow_partial=True)['cells'][0]['family_operating_outcomes']['variance_family']['reject'],1)
        bundle['attempts'].append(copy.deepcopy(attempt))
        with self.assertRaises(ValueError):d.analyze_bundle(bundle,prov,allow_partial=True)


if __name__=='__main__':unittest.main()
