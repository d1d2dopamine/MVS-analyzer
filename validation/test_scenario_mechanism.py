"""Round47 pre-retained exact, mutation, supervisor and portable gate regressions.

Ordinary discovery is self-contained and never opens retained scientific inputs.
The explicit scenario_mechanism.py synthetic command additionally requires real
native Core execution; it never treats a missing native runtime as a passing skip.
"""
import copy
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import scenario_mechanism as s


def literal_source(path):
    entities=[];observations=[]
    for g in ('A','B'):
        for i in range(8):
            values=[100+i+x for x in [-3,-1,1,3]*10]
            entities.append({'entity':str(i),'group':g,'measurements':40,'metrics':s.metric_reference(values)})
            observations.extend({'entity':str(i),'group':g,'value':x} for x in values)
    data={'group_names':['A','B'],'group_counts':[8,8],'entities':entities,'observations':observations,'total_entities':16}
    text=json.dumps(data,separators=(',',':'),allow_nan=False)
    encoded={'sha256':hashlib.sha256(text.encode()).hexdigest(),'canonical_json':text,'values':data}
    payload={'schema':'mvs-stability-replay-case/v1','index':0,'status':'completed','diagnostics_status':'retained',
             'metric_order':s.METRICS,'settings':{'effect':1.15,'alpha':.05,'repetitions':1000,'missing_rate':0,'outlier_rate':.02,'tracks':s.TRACKS},
             'data':{'left':copy.deepcopy(encoded),'right':copy.deepcopy(encoded)}}
    path.write_text(json.dumps(payload,allow_nan=False));return payload


class ExactMechanismTests(unittest.TestCase):
    def test_rational_27_state_noise_oracle(self):
        result=s.exact_toys()
        self.assertEqual(len(result['states']),27)
        self.assertEqual(result['weight_sum'],s.fraction(1))
        self.assertEqual(result['expected_variance_null'],s.fraction(F(3,2)))
        self.assertEqual(result['expected_variance_alternative'],s.fraction(F(729,400)))
        self.assertEqual(result['expected_variance_ratio'],s.fraction(F(243,200)))
        self.assertAlmostEqual(result['sd_equivalent'],math.sqrt(1.215))
        weights=[F(int(x['weight']['numerator']),int(x['weight']['denominator'])) for x in result['states']]
        self.assertEqual(sum(weights),1)
        # An unrelated exact identity: unbiased variance is mean pairwise square distance / n.
        for state in result['states']:
            for effect,key in ((F(1),'null_variance'),(F(23,20),'alternative_variance')):
                values=[effect*x+z for x,z in zip([-1,0,1],state['increments'])]
                pair_sum=sum((a-b)**2 for a,b in itertools.combinations(values,2))/6
                self.assertEqual(state[key],s.fraction(pair_sum))

    def test_symmetric_scale_blindspot_and_group_geometry(self):
        offsets=[-7,-5,-3,-1,1,3,5,7]
        a=[[100+o+x for x in [-3,-1,1,3]*10] for o in offsets]
        b=[s.transform_reference(x,'heterogeneity',100,100,2) for x in a]
        self.assertEqual(s.variance([s.mean(x) for x in b])/s.variance([s.mean(x) for x in a]),4)
        for x,y in zip(a,b):self.assertEqual(s.variance(x),s.variance(y))
        for mi in (0,7,11):
            rank=s.rank_reference([s.metric_reference(x)[mi] for x in a],[s.metric_reference(x)[mi] for x in b])
            self.assertEqual((rank['u2'],rank['z']),(64,0))
            self.assertFalse(rank['reference_reject'])

    def test_variability_seven_metrics_and_location_positive_controls(self):
        raw=[100+x for x in [-3,-1,1,3]*10]
        transformed=s.transform_reference(raw,'variability',100,100,2)
        a,b=s.metric_reference(raw),s.metric_reference(transformed)
        for mi in s.NATURAL['variability']:
            self.assertAlmostEqual(b[mi]/a[mi],2)
            rank=s.rank_reference([a[mi]]*8,[b[mi]]*8)
            self.assertEqual(rank['u2'],128);self.assertTrue(rank['reference_reject'])
        rank=s.rank_reference([-7,-5,-3,-1,1,3,5,7],[25,27,29,31,33,35,37,39])
        self.assertEqual(rank['u2'],128);self.assertTrue(rank['reference_reject'])

    def test_skewed_normalized_metrics_use_transformed_median(self):
        raw=[1,2,3,4,5,6,7,20]
        transformed=s.transform_reference(raw,'variability',6,6,2)
        self.assertEqual(transformed,[-4,-2,0,2,4,6,8,34])
        a,b=s.metric_reference(raw),s.metric_reference(transformed)
        self.assertEqual((a[0],b[0]),(4.5,3))
        for mi in (5,6):self.assertAlmostEqual(b[mi]/a[mi],3)
        self.assertTrue(math.isnan(b[10]))

    def test_location_preserves_absolute_spread_not_geometric_mean(self):
        raw=[1,2,4,9]*10;a=s.metric_reference(raw)
        transformed=s.transform_reference(raw,'location',4,7,1.15);b=s.metric_reference(transformed)
        for mi in (1,3,4,9):self.assertAlmostEqual(a[mi],b[mi])
        for mi in (0,7,11):self.assertAlmostEqual(b[mi]-a[mi],1.05)
        self.assertNotAlmostEqual(b[10]-a[10],1.05)

    def test_identity_binary64_and_no_clipping(self):
        values=[-0.,0.,-1e8,1e8]
        self.assertEqual([s.bits(x) for x in s.transform_reference(values,'identity',1,1)],[s.bits(x) for x in values])
        self.assertGreater(max(s.transform_reference(values,'variability',0,1,2)),1e8)

    def test_availability_reasons_and_fixed_family(self):
        zero=[-3,-1,1,3]*10;metrics=s.metric_reference(zero)
        for mi in (2,5,6,10):self.assertTrue(math.isnan(metrics[mi]))
        self.assertEqual(s.requirement_reason('coefficient_of_variation',zero),'near_zero_mean')
        self.assertEqual(s.requirement_reason('normalized_mad',zero),'near_zero_median')
        self.assertEqual(s.requirement_reason('geometric_mean',zero),'nonpositive_measurements')
        rank=s.rank_reference([1]*3,[2]*8,minimum=4)
        self.assertFalse(rank['available']);self.assertIsNone(rank['reference_reject']);self.assertEqual(s.FAMILY,12)


class RankOracleTests(unittest.TestCase):
    def test_n8_u59_vs_u60_strict_decision_boundary(self):
        for target,first,reject in ((59,3.5,False),(60,4.5,True)):
            r=s.rank_reference(list(range(1,9)),[first,*range(9,16)])
            self.assertEqual(r['u'],target);self.assertEqual(r['reference_reject'],reject)
            self.assertEqual(min(1,12*r['polynomial_p'])<.05,reject)
            self.assertEqual(r['variance_exact'],s.fraction(F(272,3)))

    def test_ties_swap_and_empty(self):
        a,b=[1,1,2,4],[1,2,3,3]
        r=s.rank_reference(a,b);q=s.rank_reference(b,a)
        self.assertEqual(r['u2']+q['u2'],32)
        self.assertEqual(r['scipy_p'],q['scipy_p'])
        self.assertEqual(r['tie_block_sizes'],[3,2,2,1]);self.assertEqual(r['tie_correction_sum'],36)
        self.assertEqual(r['u2'],19)
        tied=s.rank_reference([1]*8,[1]*8)
        self.assertEqual((tied['variance'],tied['polynomial_p']),(0,1))
        self.assertFalse(s.rank_reference([],b)['available'])

    def test_exhaustive_small_pair_count_against_rank_sum(self):
        for a in itertools.product(range(3),repeat=3):
            for b in itertools.product(range(3),repeat=3):
                pooled=sorted([*a,*b]);rank={v:F(2*pooled.index(v)+pooled.count(v)+1,2) for v in set(pooled)}
                expected=sum(rank[x] for x in b)-6
                self.assertEqual(s.rank_reference(a,b)['u2'],2*expected)

    def test_nonfinite_rejected_no_near_tie_coercion(self):
        with self.assertRaises(ValueError):s.rank_reference([math.nan],[1])
        r=s.rank_reference([1.],[math.nextafter(1.,math.inf)])
        self.assertEqual(r['u2'],2);self.assertEqual(r['tie_correction_sum'],0)


class InputAndPinTests(unittest.TestCase):
    def test_case_loader_and_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.json';original=literal_source(path)
            _,halves=s.load_source(path,0,s.digest(path));self.assertEqual(len(halves),2)
            old_sha=s.digest(path);path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'hash'):s.load_source(path,0,old_sha)
            for kind in ('missing_half','wrong_entities','reordered_metrics','canonical_values','duplicate_entity'):
                bad=copy.deepcopy(original)
                if kind=='missing_half':del bad['data']['right']
                elif kind=='reordered_metrics':bad['metric_order']=list(reversed(s.METRICS))
                elif kind=='canonical_values':bad['data']['left']['values']['observations'][0]['value']+=1
                else:
                    data=bad['data']['left']['values']
                    if kind=='wrong_entities':data['entities'].pop()
                    else:data['entities'][1]['entity']=data['entities'][0]['entity']
                    text=json.dumps(data,separators=(',',':'));bad['data']['left']['canonical_json']=text;bad['data']['left']['sha256']=hashlib.sha256(text.encode()).hexdigest()
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError,msg=kind):s.load_source(path,0,s.digest(path))

    def test_source_inventory_same_string_order_before_and_after(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('alpha.py','alpha/x.py','alpha-z.cs','Z/z.py'):
                p=root/name;p.parent.mkdir(exist_ok=True);p.write_text('# test')
            inventory=s.source_inventory(root)
            self.assertEqual(inventory,sorted(inventory));self.assertEqual(inventory,s.source_inventory(root))
            pins=s.pin_files(inventory);Path(inventory[0]).write_text('mutated')
            self.assertNotEqual(pins[inventory[0]],s.digest(inventory[0]))

    def test_codec_reserved_symbol_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'reserved'):s.trace.frames(bytes([255])+bytes(20999))

    def test_nonfinite_metadata_unknown_duplicate_and_missing(self):
        values=[-3,-1,1,3]*10
        row={'values':values}
        native={'halves':[{'entities':[row],'conditions':[]}], 'nonfinite_fields':[{'path':f'halves[0].entities[0].metrics[{i}]','value':'NaN'} for i in (2,5,6,10)]}
        audit=s.Audit();s.validate_nonfinite_fields(native,audit);self.assertFalse(audit.errors)
        for change in ('missing','unknown','class'):
            bad=copy.deepcopy(native)
            if change=='missing':bad['nonfinite_fields'].pop()
            elif change=='unknown':bad['nonfinite_fields'][0]['path']='unknown'
            else:bad['nonfinite_fields'][0]['value']='Infinity'
            audit=s.Audit();s.validate_nonfinite_fields(bad,audit);self.assertTrue(audit.errors)
        native['nonfinite_fields'].append(native['nonfinite_fields'][0])
        with self.assertRaisesRegex(ValueError,'duplicate'):s.validate_nonfinite_fields(native,s.Audit())

    def test_portable_protocol_uses_shipped_document_not_external_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'docs').mkdir();doc=root/'docs/ROUND47_SCENARIO_MECHANISM_PROTOCOL.md';doc.write_text('fixed synthetic protocol')
            plan={'protocol_path':'/does/not/exist/old.md','protocol_sha256':s.digest(doc),'metric_order':s.METRICS,'conditions':[{'id':c} for c in s.CONDITIONS],
                  'outputs':s.COUNTS,'alpha':s.ALPHA,'family_denominator':12,'limits':s.LIMITS,'tolerances':{'mathematical_erfc_p_absolute':s.TAIL_TOL},'inputs':[{'index':i} for i in range(120)]}
            path=root/'plan.json';path.write_text(json.dumps(plan))
            with patch.object(s,'PLAN_SHA',s.digest(path)),patch.object(s,'DOCUMENT_SHA',s.digest(doc)):
                self.assertEqual(s.validate_plan(plan,path,root),doc)


class SupervisorTests(unittest.TestCase):
    def supervise_fixture(self,script,limits=None):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);limits=dict(s.LIMITS,**(limits or {}))
            resources={'samples':0,'peak_aggregate_rss_bytes':0,'peak_output_bytes':0,'maximum_observed_sample_gap_seconds':0.,'last_sample_monotonic':time.monotonic(),'processes':[]}
            with patch.object(s,'LIMITS',limits),patch.object(s.bounded,'LIMITS',limits):
                try:s.supervise([sys.executable,'-c',script],out,'fixture',time.monotonic()+limits['wall_seconds'],resources,dict(os.environ))
                except Exception as exc:return resources,str(exc)
            return resources,None

    def test_normal_exit_and_failure_preservation(self):
        r,error=self.supervise_fixture('print("fixture")');self.assertIsNone(error);self.assertEqual(r['processes'][0]['state'],'completed')
        r,error=self.supervise_fixture('raise SystemExit(7)');self.assertIn('exit 7',error);self.assertEqual(r['processes'][0]['state'],'failed')

    def test_deadline_rss_output_and_descendant_cleanup(self):
        for script,limits,reason in [('import time;time.sleep(10)',{'wall_seconds':.1},'global_wall_deadline'),
             ('import time;time.sleep(10)',{'aggregate_rss_bytes':1},'aggregate_rss_limit'),
             ('print("x"*100000);import time;time.sleep(10)',{'output_bytes':1000},'evidence_output_limit'),
             ('import subprocess,sys;subprocess.Popen([sys.executable,"-c","import time;time.sleep(10)"])',{'wall_seconds':.15},None)]:
            r,error=self.supervise_fixture(script,limits);self.assertIsNotNone(error)
            if reason:self.assertEqual(error,reason)
            self.assertEqual(r['processes'][0]['cleanup']['live_members_after'],[])

    def test_final_inventory_failure_never_marks_success_and_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);s.write_json(out/'bind.json',{'synthetic_only':True})
            binding={'synthetic':True,'commands':{k:[k] for k in ('worker','verifier','postpins')},'cases':[],'output_inventory':s.BASE_OUTPUTS,'pins':{}}
            def fake(command,out,label,deadline,resources,env):
                if label=='worker':(out/'unplanned').write_text('x')
                if label=='verifier':s.write_json(out/'independent-audit.json',{'valid':True})
                if label=='postpins':s.write_json(out/'post-run-pins.json',{'valid':True})
            with patch.object(s,'verify',return_value=binding),patch.object(s,'supervise',side_effect=fake),patch.object(s,'validate_attestation'):
                result=s.run(out,s.digest(out/'bind.json'))
            self.assertEqual(result['status'],'technical_failure');self.assertEqual(s.read_json(out/'run.json')['status'],'technical_failure')
            with self.assertRaisesRegex(ValueError,'single attempt'):s.run(out,s.digest(out/'bind.json'))

    def test_native_case_logs_use_final_paths_without_rename(self):
        # Deterministic regression for the observed enumeration/stat race:
        # all paths seen while the child writes remain present afterward.
        for code in (0,7):
            with tempfile.TemporaryDirectory() as directory:
                out=Path(directory);seen=[]
                real_run=subprocess.run
                def observe(command,**kwargs):
                    seen.extend(p['path'] for p in s.bounded.output_inventory(out))
                    return real_run(command,**kwargs)
                script=f'import sys;print("stdout");print("stderr",file=sys.stderr);raise SystemExit({code})'
                with patch.object(s.subprocess,'run',side_effect=observe),patch.object(Path,'rename',side_effect=AssertionError('case logs must never rename')):
                    if code:
                        with self.assertRaisesRegex(ValueError,'exit 7'):s.run_native([sys.executable,'-c',script],out,None,[])
                    else:s.run_native([sys.executable,'-c',script],out,None,[])
                self.assertEqual(sorted(seen),['stderr.log','stdout.log'])
                self.assertEqual(sorted(p.name for p in out.iterdir()),['stderr.log','stdout.log'])
                self.assertEqual((out/'stdout.log').read_text().strip(),'stdout')
                self.assertEqual((out/'stderr.log').read_text().strip(),'stderr')
                for name in seen:self.assertGreater((out/name).stat().st_size,0)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);s.run_native([sys.executable,'-c','pass'],out,'toys',[])
            self.assertEqual(sorted(p.name for p in out.iterdir()),['toys.stderr.log','toys.stdout.log'])

    def test_worker_case_path_remains_visible_during_sampling(self):
        # Exercise worker(), including its success/failure-log handling, with a
        # tiny process fixture. Statistical auditing is mocked only because this
        # regression isolates path stability, not native numerical parity.
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);done=threading.Event();seen=set();errors=[]
            script=('import json,pathlib,sys,time;time.sleep(.04);'
                    'print(json.dumps({"identity":{}})) if "--self-test" in sys.argv else '
                    'pathlib.Path(sys.argv[sys.argv.index("--out")+1]).write_text("{}")')
            binding={'native_command':[sys.executable,'-c',script],'identity':{},'probe_settings':{},'synthetic':True,
                     'cases':[{'index':0,'path':'synthetic-only-unused-input','sha256':'a'*64}]}
            def sample():
                while not done.is_set():
                    try:
                        for item in s.bounded.output_inventory(out):
                            if item['path'].endswith('.log'):seen.add(item['path'])
                    except Exception as exc:errors.append(str(exc))
                    time.sleep(.001)
            sampler=threading.Thread(target=sample);sampler.start()
            try:
                with patch.object(s,'verify',return_value=binding),patch.object(s,'supervised_binding',return_value='b'*64),\
                     patch.object(s,'audit_native_toys',return_value={'native_audit':{'valid':True}}),\
                     patch.object(s,'audit_case',return_value={'audit':{'valid':True}}),\
                     patch.object(Path,'rename',side_effect=AssertionError('worker must not rename logs')):
                    result=s.worker(out)
            finally:done.set();sampler.join()
            self.assertEqual(result['status'],'worker_completed');self.assertFalse(errors)
            self.assertIn('case-000/stdout.log',seen);self.assertIn('case-000/stderr.log',seen)
            self.assertNotIn('case-000/native.stdout.log',seen);self.assertNotIn('case-000/native.stderr.log',seen)
            for name in seen:self.assertTrue((out/name).is_file())

    def test_private_worker_requires_supervised_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);s.write_json(out/'bind.json',{})
            with patch.dict(os.environ,{},clear=True):
                with self.assertRaisesRegex(ValueError,'supervisor-only'):s.supervised_binding(out)


if __name__=='__main__':unittest.main(verbosity=2)
