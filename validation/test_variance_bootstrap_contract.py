"""Synthetic algebra/fail-closed tests; no native/scientific scenario execution."""
import copy
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import variance_bootstrap_contract as ref


def fp(value):
    kind='nan' if math.isnan(value) else 'positive_infinity' if value==math.inf else 'negative_infinity' if value==-math.inf else 'finite'
    return dict(classification=kind,value=value if math.isfinite(value) else None,bits=struct.pack('>d',value).hex())


def synthetic_case(n=100,r=99):
    fit=dict(Means=[0.,10.],Within=[2.,2.],Between=[1.,1.],NegativeLogLikelihood=0.,Converged=True,AtBoundary=False,Method='ML',Iterations=0)
    cache={'initial-fit':dict(fit,Converged=False,Method='REML')}
    for track in ('within','between'):
        cache[track+'/null-fit']=copy.deepcopy(fit)
        cache[track+'/observed']=1
        cache.update({track+'/reference/'+str(i):0 for i in range(r)})
        for label in ('null','alternative','grid'):
            cache.update({track+'/'+label+'/'+str(i):1 for i in range(n)})
    return dict(id='synthetic',data=dict(groupNames=['A','B'],warnings=[],observations=[dict(group=g,entity=e,value=v,sequence=i) for g,base in [('A',0),('B',10)] for e,delta in [('x',0),('y',2)] for i,v in enumerate([base+delta-1,base+delta+1])]),repetitions=n,referenceReplications=r,alpha=.05,withinEffect=2,betweenEffect=3,seed=54,cache=cache,expectedException=None)


class ContractTests(unittest.TestCase):
    def test_plus_one_inclusive_ties(self):
        self.assertEqual(ref.bootstrap_p([0.,2.,None],2.),2/3)
        self.assertEqual(ref.bootstrap_p([0.,2.],3.),1/3)
        self.assertIsNone(ref.bootstrap_p([],1))
        self.assertIsNone(ref.bootstrap_p([1],None))

    def test_strict_alpha_and_fixed_family(self):
        c=synthetic_case(); c['alpha']=.02
        rows=ref.expected_run(c,'test')['report']['tracks']
        self.assertEqual(rows[0]['pValue'],.01)
        self.assertEqual(rows[0]['adjustedP'],.02)
        self.assertEqual(rows[0]['verdict'],'insufficient')
        self.assertEqual(rows[0]['power'],0.)

    def test_requested_denominator_and_failure_threshold(self):
        c=synthetic_case()
        for i in range(90,100): c['cache']['within/alternative/'+str(i)]='NaN'
        row=ref.expected_run(c,'test')['report']['tracks'][0]
        self.assertEqual(row['power'],.9)
        self.assertEqual(row['alternativeFailures'],10)
        c['cache']['within/alternative/89']='NaN'
        row=ref.expected_run(c,'test')['report']['tracks'][0]
        self.assertIsNone(row['power']); self.assertIsNone(row['fpr'])
        self.assertEqual(row['status'],'excess_simulation_failures')
        self.assertEqual(row['pValue'],.01)

    def test_reference_threshold_and_unusable_keys(self):
        c=synthetic_case(r=100)
        for i in range(90,100): c['cache']['within/reference/'+str(i)]='NaN'
        self.assertEqual(ref.expected_run(c,'test')['report']['tracks'][0]['referenceReplications'],90)
        c['cache']['within/reference/89']='NaN'
        with self.assertRaises(ref.InvalidEvidence): ref.expected_run(c,'test') # unused evaluation keys forbidden
        for label in ('null','alternative','grid'):
            for i in range(100): del c['cache']['within/'+label+'/'+str(i)]
        row=ref.expected_run(c,'test')['report']['tracks'][0]
        self.assertEqual(row['status'],'bootstrap_or_fit_failure')
        self.assertEqual(row['nullFailures'],100)
        self.assertIsNone(row['pValue'])

    def test_boundary_nuisance_and_geometric_flag(self):
        c=synthetic_case()
        for track in ('within','between'):
            c['cache'][track+'/null-fit']['Within']=[1e-8,1e-8]
        rows=ref.expected_run(c,'test')['report']['tracks']
        self.assertIsNone(rows[0]['power']); self.assertEqual(rows[0]['fpr'],1.)
        self.assertEqual(rows[1]['power'],1.)
        for track in ('within','between'):
            c['cache'][track+'/null-fit'].update(Within=[2e-8,2e-8],AtBoundary=True)
        self.assertEqual(ref.expected_run(c,'test')['report']['tracks'][0]['power'],1.)

    def test_grid_preserves_noisy_curve_and_requires_complete_curve(self):
        self.assertAlmostEqual(ref.mde_from_curve(ref.EFFECT_GRID,[0.,.5,.9,.7,.95]),.0425)
        self.assertIsNone(ref.mde_from_curve(ref.EFFECT_GRID,[0.,.5,None,.7,.95]))
        self.assertIsNone(ref.mde_from_curve(ref.EFFECT_GRID,[.8,.9,.9,.7,.95]))

    def test_wilson_algebra_anchor(self):
        low,high=ref.wilson(0,100)
        self.assertAlmostEqual(low,0.)
        self.assertAlmostEqual(high,1.959963984540054**2/(100+1.959963984540054**2))
        low,high=ref.wilson(50,100)
        self.assertAlmostEqual(low+high,1.)

    def test_generator_axis_transform_and_clamp(self):
        case=dict(design=[dict(entity='e',group=0,count=2,mean=999,withinSumSquares=999)],model=dict(Means=[0.],Within=[1.],Between=[1.]),uniformTape=[0,0,.5,0,.5,.5],track='none',effect=1)
        row=ref.expected_generate(case)[0]
        self.assertAlmostEqual(row['mean'],math.sqrt(30*math.log(10))+math.sqrt(math.log(2)))
        self.assertAlmostEqual(row['withinSumSquares'],2*math.log(2))
        case['uniformTape'] += [.5,0]
        with self.assertRaises(ref.InvalidEvidence): ref.expected_generate(case)

    def test_fp_integrity_and_nonfinite_classes(self):
        self.assertEqual(ref.decode_numeric(fp(.1)),.1)
        self.assertIsNone(ref.decode_numeric(fp(float('nan'))))
        bad=fp(.1); bad['value']=.2
        with self.assertRaises(ref.InvalidEvidence): ref.decode_numeric(bad)
        with self.assertRaises(ref.InvalidEvidence): ref.decode_numeric(fp(math.inf))
        with self.assertRaises(ref.InvalidEvidence): ref.decode_numeric(.1)
        bad=fp(float('nan'));bad['classification']='finite'
        with self.assertRaises(ref.InvalidEvidence): ref.decode_numeric(bad)

    def test_json_duplicates_nonstandard_numbers(self):
        for text in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.assertRaises(ref.InvalidEvidence): ref.read_json(text)

    def test_full_shape_counts_and_boolean_types(self):
        self.assertTrue(ref.compare_value({'p':.01},{'p':.01,'failures':0}))
        self.assertTrue(ref.compare_value([1],[1,2]))
        self.assertTrue(ref.compare_value(True,1))
        self.assertTrue(ref.compare_value(float('nan'),.1))
        self.assertTrue(ref.compare_value(0.,None))

    def test_missing_cache_and_extra_cache_fail_closed(self):
        c=synthetic_case(); del c['cache']['within/null/0']
        with self.assertRaises(ref.InvalidEvidence): ref.expected_run(c,'test')
        c=synthetic_case();c['cache']['unexpected']=0
        with self.assertRaises(ref.InvalidEvidence): ref.expected_run(c,'test')

    def test_fresh_directory_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ref.InvalidEvidence): ref.create_evidence_directory(tmp)
            path=ref.create_evidence_directory(Path(tmp)/'fresh')
            self.assertTrue(path.is_dir())

    def test_native_failure_retains_exact_output(self):
        for process in [subprocess.CompletedProcess([],2,b'partial stdout',b'native failure'),subprocess.TimeoutExpired([],30,output=b'partial',stderr=b'timed out')]:
            with self.subTest(process=type(process).__name__), tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);fixture=out/'fixture';fixture.write_bytes(b'{}')
                kw={'side_effect':process} if isinstance(process,Exception) else {'return_value':process}
                with patch.object(ref.subprocess,'run',**kw):
                    with self.assertRaises(ref.InvalidEvidence) as error: ref.native_run(['fake'],fixture,ref.sha256(b'{}'),out)
                self.assertTrue(error.exception.native_started)
                self.assertTrue((out/'native.stdout').read_bytes())
                self.assertTrue((out/'native.stderr').read_bytes())
                self.assertTrue((out/'native-process.json').exists())

    def test_changed_fixture_prevents_native_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture=p/'fixture';fixture.write_bytes(b'{}')
            with patch.object(ref.subprocess,'run') as run:
                with self.assertRaises(ref.InvalidEvidence): ref.native_run(['fake'],fixture,'0'*64,p)
                run.assert_not_called()

    def test_frozen_literal_report_anchors(self):
        path=Path(__file__).resolve().parent/'variance-bootstrap-fixtures-v1.json'
        document,_=ref.load_fixtures(path)
        rows={c['id']:ref.expected_run(c,'1.6.2')['report']['tracks'] for c in document['runCases']}
        # Literal expectations transcribed from the frozen protocol, not branch helpers.
        anchors={
          'R01':(.02,.04,.1,.8,99,0,0,0,'insufficient','conditional_plugin_bootstrap'),
          'R02':(.01,.02,0.,0.,99,0,0,0,'insufficient','conditional_plugin_bootstrap'),
          'R03':(1/91,2/91,.1,.8,90,10,0,0,'difference','conditional_plugin_bootstrap'),
          'R04':(None,None,None,None,89,11,100,100,'insufficient','bootstrap_or_fit_failure'),
          'R05':(.01,.02,.1,.8,99,0,10,10,'difference','conditional_plugin_bootstrap'),
          'R06':(.01,.02,None,None,99,0,11,10,'difference','excess_simulation_failures'),
          'R07':(.01,.02,None,None,99,0,10,11,'difference','excess_simulation_failures'),
          'R08':(.01,.02,10/499,80/499,99,0,0,0,'difference','conditional_plugin_bootstrap'),
          'R09':(.01,.02,.02,.16,99,0,0,0,'difference','conditional_plugin_bootstrap'),
          'R10':(.01,.02,.02,.16,99,0,0,0,'difference','conditional_plugin_bootstrap'),
          'R11':(.01,.02,.02,.16,99,0,0,0,'difference','conditional_plugin_bootstrap'),
          'R12':(.01,.02,.1,None,99,0,0,0,'difference','boundary_baseline_power_not_identifiable'),
          'R13':(.01,.02,.1,.8,99,0,0,0,'difference','conditional_plugin_bootstrap'),
          'R14':(None,None,None,None,99,0,100,100,'insufficient','bootstrap_or_fit_failure')}
        names=['pValue','adjustedP','fpr','power','referenceReplications','referenceFailures','nullFailures','alternativeFailures','verdict','status']
        for case,expected in anchors.items():
            with self.subTest(case=case): self.assertEqual(tuple(rows[case][0][key] for key in names),expected)
        for case in anchors:
            if case not in ('R02','R12'):
                for key in names: self.assertEqual(rows[case][0][key],rows[case][1][key])
        self.assertEqual(rows['R02'][1]['referenceReplications'],0)
        self.assertEqual(rows['R02'][1]['referenceFailures'],99)
        self.assertEqual(rows['R02'][1]['status'],'bootstrap_or_fit_failure')
        self.assertEqual(rows['R12'][1]['power'],.8)
        curves={'R01':[1.]*5,'R02':[0.]*5,'R03':[1.]*5,'R04':[None]*5,'R05':[.9]*5,
            'R06':[1.]*5,'R07':[1.]*5,'R08':[0.,.5,.9,.7,95/99],'R09':[0.,.5,.9,.7,.95],
            'R10':[0.,.5,.8,.7,.95],'R11':[0.,.5,None,.7,.95],'R12':[None]*5,'R13':[1.]*5,'R14':[None]*5}
        for case,curve in curves.items(): self.assertEqual(rows[case][0]['powerCurve'],curve)
        for case in anchors:
            actual=rows[case][0]['mde']
            if case=='R09': self.assertAlmostEqual(actual,.0425,places=12)
            elif case=='R10': self.assertAlmostEqual(actual,.05,places=12)
            else: self.assertIsNone(actual)
        self.assertEqual(rows['R09'][0]['mdeStatus'],'estimated_on_grid')
        self.assertEqual(rows['R10'][0]['mdeStatus'],'estimated_on_grid')
        self.assertEqual(rows['R11'][0]['mdeStatus'],'target_not_reached_or_invalid_curve')
        self.assertEqual(rows['R12'][0]['mdeStatus'],'zero_baseline')
        self.assertEqual([len(c['cache']) for c in document['runCases']],[803,404,805,205,803,803,803,3197,3203,3203,3203,803,803,203])

    def test_frozen_generator_hand_algebra(self):
        document,_=ref.load_fixtures(Path(__file__).resolve().parent/'variance-bootstrap-fixtures-v1.json')
        a=math.sqrt(2*math.log(2))
        means=[10+(1-math.sqrt(2))*a,20+(-2+math.sqrt(3))*a,30+(3-math.sqrt(8))*a]
        for i,c in enumerate(document['generatorCases'][:5]):
            actual=ref.expected_generate(c); expected_means=list(means);wss=[4*a*a,18*a*a,16*a*a]
            if i==1: expected_means[2]=30+(3-2*math.sqrt(8))*a;wss[2]=64*a*a
            if i==2: expected_means[2]=30+(6-math.sqrt(8))*a
            for j,row in enumerate(actual):
                self.assertAlmostEqual(row['mean'],expected_means[j],places=12)
                self.assertAlmostEqual(row['withinSumSquares'],wss[j],places=12)

    def test_raw_null_cannot_substitute_nan_provenance(self):
        with self.assertRaises(ref.InvalidEvidence): ref.decode_expected(None,None)
        self.assertIsNone(ref.decode_expected(fp(float('nan')),None))

    def test_seal_binds_sources_binaries_and_zero_case_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ref.SOURCE_FILES+('validation/variance_bootstrap_contract.py','validation/test_variance_bootstrap_contract.py'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
            for name in ('fixture','protocol','harness.dll','MvsAnalyzer.Core.dll'): (root/name).write_bytes(name.encode())
            identity=dict(schemaVersion=1,protocolId=ref.PROTOCOL_ID,generateCallCount=0,runCallCount=0,
                identity=dict(experimental=True,sourceSha256={name:ref.sha256((root/name).read_bytes()) for name in ref.SOURCE_FILES},
                    harnessAssembly=dict(sha256=ref.sha256(b'harness.dll')),coreAssembly=dict(sha256=ref.sha256(b'MvsAnalyzer.Core.dll')),
                    runtime=dict(version='synthetic',coreLibrarySha256='a'*64)))
            seal=ref.prepare_seal(root,root/'fixture',root/'protocol',root/'harness.dll',identity)
            self.assertEqual(seal['runtimeVersion'],'synthetic')
            self.assertEqual(seal['fixtureSha256'],ref.sha256(b'fixture'))
            identity['runCallCount']=1
            with self.assertRaises(ref.InvalidEvidence): ref.prepare_seal(root,root/'fixture',root/'protocol',root/'harness.dll',identity)
            identity['runCallCount']=0
            (root/'harness.dll').write_bytes(b'changed')
            with self.assertRaises(ref.InvalidEvidence): ref.prepare_seal(root,root/'fixture',root/'protocol',root/'harness.dll',identity)

    def test_bad_native_provenance_is_rejected(self):
        with self.assertRaises(ref.InvalidEvidence): ref.validate_native({},'0'*64,{'schemaVersion':1,'protocolId':ref.PROTOCOL_ID,'inputSha256':'1'*64},Path('.'),Path('missing'))

if __name__=='__main__': unittest.main()
