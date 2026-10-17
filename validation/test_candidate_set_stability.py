"""Hand-constructed software fixtures. Never opens retained calibration outcomes."""
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import candidate_set_stability as c


def original_wilson(k):
    # Original operation order is deliberately different from reference algebra.
    n=1000; z=1.959963984540054; p=k/n; den=1+z*z/n
    center=(p+z*z/(2*n))/den
    radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0,center-radius),min(1,center+radius)


def make_rows():
    fpr_low,fpr_high=original_wilson(4)
    low,high=original_wilson(800)
    return [{'metric':k,'fpr':.004,'power':.8,'score':.3,'robustness':.9,'repeatability':.9,'coverage':.95,'applicable':True,'mde':.2,'fpr_inflated':False,'power_curve':'1:0|1.5:0.8','tracks':list(c.TRACKS),'track_powers':[.8]*3,'track_scores':[.3]*3,'track_mdes':[.2]*3,'track_curves':['1:0|1.5:0.8']*3,'repetitions':1000,'fpr_low':fpr_low,'fpr_high':fpr_high,'track_power_low':[low]*3,'track_power_high':[high]*3,'track_failures':[0]*3,'track_mde_status':['estimated_on_grid']*3,'alpha':.05,'null_failures':0} for k in c.KEYS]


def encode_rows(rows):
    rows=copy.deepcopy(rows); metadata=[]
    for i,row in enumerate(rows):
        for field in c.SCALARS:
            if not math.isfinite(row[field]):
                v=row[field];metadata.append({'path':f'[{i}].{field}','value':'NaN' if math.isnan(v) else 'Infinity' if v>0 else '-Infinity'});row[field]=None
        for field in c.DOUBLE_ARRAYS:
            for j,v in enumerate(row[field]):
                if not math.isfinite(v):
                    metadata.append({'path':f'[{i}].{field}[{j}]','value':'NaN' if math.isnan(v) else 'Infinity' if v>0 else '-Infinity'});row[field][j]=None
    return rows,metadata


def set_track(row, p, low, high, j=0):
    row['track_powers'][j]=p;row['track_power_low'][j]=low;row['track_power_high'][j]=high
    if j==0: row['power']=p


def unavailable(row, track=None):
    if track is None:
        row['applicable']=False
        for key in ('fpr','fpr_low','fpr_high','robustness','repeatability','coverage'): row[key]=math.nan
        tracks=range(3)
    else:
        tracks=(track,);row['track_failures'][track]=101
    for j in tracks:
        for field in ('track_powers','track_power_low','track_power_high','track_scores'): row[field][j]=math.nan
    row['power']=row['track_powers'][0];row['score']=row['track_scores'][0]


def binding(value):
    canonical=json.dumps(value,separators=(',',':'),ensure_ascii=False)
    return {'canonical_json':canonical,'sha256':hashlib.sha256(canonical.encode()).hexdigest(),'values':copy.deepcopy(value)}


def make_case(index=0):
    rows=make_rows(); encoded,meta=encode_rows(rows)
    observation={'entity':'synthetic_01','group':'control','value':1.0,'sequence':1,'variable':'stride_interval','unit':'s'}
    data={'warnings':[],'import_summary':'synthetic software fixture','observations':[observation],'entities':[{'entity':'synthetic_01','group':'control','metrics':[1.0]*12,'measurements':40}],'total_entities':1,'group_names':['control'],'group_counts':[1],'valid_rows':1,'median_measurements':40.0,'entity_column':'entity','value_column':'value','group_column':'group','sequence_column':'sequence','measurement_name':'stride_interval','unit':'s','distribution_proxy':'synthetic','min_value_applied':-1000000,'max_value_applied':1000000,'min_measurements_applied':6}
    fp='synthetic-software-fixture-no-calibration'
    identity={'harness_sha256':'1'*64,'core_sha256':'2'*64,'runtime':'.NET 8.0.31','os':'synthetic Linux','architecture':'X64','engine_version':'1.6.2','benchmark_protocol':'MVS-BENCH-1.2.0','processor_count':1,'environment_fingerprint':fp,'environment_sha256':hashlib.sha256(fp.encode()).hexdigest(),'environment_probe_values':[1.0]*12}
    tau={'kendall_tau':1.0,'defined':True,'undefined_reason':None,'top_left_index':0,'top_right_index':0,'top_left':'median','top_right':'median','matched':True}
    availability=[{'metric':k,'row_present':True,'score_finite':True,'applicable':True,'projected_to_zero':False} for k in c.KEYS]
    return {'schema':'mvs-stability-replay-case/v1','index':index,'status':'completed','diagnostics_status':'retained','error':'','seeds':{'run_seed':20260904,'derived_seed':c.derived_seed(index),'split_seed':1,'calibration_left_seed':2,'calibration_right_seed':3},'settings':c.expected_settings(),'metric_order':list(c.KEYS),'identity':identity,'data':{'generated':binding([observation]),'built':binding(data),'left':binding(data),'right':binding(data)},'calibration_left':encoded,'calibration_right':copy.deepcopy(encoded),'nonfinite_fields':{'calibration_left':meta,'calibration_right':copy.deepcopy(meta)},'scores_left':[.3]*12,'scores_right':[.3]*12,'availability_left':availability,'availability_right':copy.deepcopy(availability),'legacy':tau,'corrected':copy.deepcopy(tau),'resources':{'wall_seconds':0.0,'cpu_seconds':0.0,'peak_working_set_bytes':0}}


def selection(candidates,best=None,qualified=()):
    candidates=list(candidates);best=best if best is not None else (candidates[0] if candidates else None)
    return {'candidates':candidates,'qualified':list(qualified),'best':best,'status':'qualified' if qualified else 'uncertain' if candidates else 'unavailable','empty_reasons':[] if candidates else ['no_applicable_natural_family']}


class LoaderTests(unittest.TestCase):
    def test_complete_roundtrip(self):
        rows=make_rows(); restored,audit=c.validate_rows(*encode_rows(rows))
        self.assertEqual(rows,restored);self.assertEqual(len(audit),12)
        self.assertEqual(c.validate_case(make_case(),0)[0]['left'],rows)

    def test_wilson_all_counts_and_preservation(self):
        for k in range(1001):
            lo,hi=original_wilson(k)
            self.assertEqual(c.validate_interval(k/1000,lo,hi,0,str(k))['successes'],k)
        lo,hi=original_wilson(1000)
        hi=math.nextafter(1.0,0.0)  # Explicit endpoint-roundoff fixture; preserve stored value.
        row=make_rows();set_track(row[0],1.0,lo,hi)
        restored,_=c.validate_rows(*encode_rows(row))
        self.assertEqual(restored[0]['track_power_high'][0],hi)

    def test_count_integrality_feasibility_and_wrong_bounds(self):
        for p,lo,hi,fails in ((.8000000000000002,*original_wilson(800),0),(.95,*original_wilson(950),100),(.8,.7,.9,0),(0.0,.01,.02,0)):
            with self.subTest(p=p,failures=fails),self.assertRaises(ValueError):c.validate_interval(p,lo,hi,fails,'fixture')

    def test_unavailable_track_and_nonapplicable(self):
        for mode in ('track','row'):
            rows=make_rows();unavailable(rows[0],1 if mode=='track' else None)
            restored,_=c.validate_rows(*encode_rows(rows))
            self.assertTrue(math.isnan(restored[0]['track_powers'][1]))
            self.assertNotIn('median',c.reference_selection(restored,'variability')['candidates'])

    def test_nonfinite_optional_classes_roundtrip(self):
        rows=make_rows();rows[0]['mde']=math.inf;rows[0]['track_mdes'][0]=math.inf;rows[1]['track_mdes'][2]=-math.inf;rows[2]['track_mdes'][1]=math.nan
        restored,_=c.validate_rows(*encode_rows(rows))
        self.assertEqual(restored[0]['mde'],math.inf);self.assertEqual(restored[1]['track_mdes'][2],-math.inf);self.assertTrue(math.isnan(restored[2]['track_mdes'][1]))

    def test_required_fields_arrays_metric_track_types(self):
        mutations=[lambda r:r[0].pop('fpr_high'),lambda r:r[0].update(extra=1),lambda r:r.pop(),lambda r:r.append(copy.deepcopy(r[0])),lambda r:r[1].update(metric='median'),lambda r:r[0].update(metric='huber_location'),lambda r:r.reverse(),lambda r:r[0].update(tracks=['location','location','heterogeneity']),lambda r:r[0].update(tracks=list(reversed(c.TRACKS))),lambda r:r[0].update(track_power_high=[.9,.9]),lambda r:r[0].update(track_scores=None),lambda r:r[0].update(applicable=1),lambda r:r[0].update(repetitions=1000.0),lambda r:r[0].update(null_failures=True),lambda r:r[0].update(alpha=.1),lambda r:r[0].update(repetitions=999),lambda r:r[0].update(track_failures=[0,-1,0]),lambda r:r[0].update(track_curves=['',1,'']),lambda r:r[0].update(null_failures=101)]
        for mutate in mutations:
            raw,meta=encode_rows(make_rows());mutate(raw)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):c.validate_rows(raw,meta)

    def test_nonfinite_sidecar_malformed(self):
        rows=make_rows();unavailable(rows[0],1);raw,meta=encode_rows(rows)
        mutations=[lambda r,m:m.pop(),lambda r,m:m.append(copy.deepcopy(m[0])),lambda r,m:m[0].update(path='[99].power'),lambda r,m:m[0].update(path='[0].applicable'),lambda r,m:m[0].update(path='[0].track_powers[3]'),lambda r,m:m[0].update(value='inf'),lambda r,m:m[0].update(value='Infinity'),lambda r,m:r[0]['track_powers'].__setitem__(1,.5),lambda r,m:m.append({'path':'[1].power','value':'NaN'}),lambda r,m:r[1].update(fpr_high=None)]
        for mutate in mutations:
            r,m=copy.deepcopy(raw),copy.deepcopy(meta);mutate(r,m)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):c.validate_rows(r,m)

    def test_mixed_unavailability_and_invalid_probabilities(self):
        changes=[lambda r:r[0]['track_failures'].__setitem__(1,101),lambda r:r[0].update(applicable=False),lambda r:r[0].update(fpr_inflated=True),lambda r:r[0].update(fpr=-.1),lambda r:r[0].update(fpr_high=math.inf),lambda r:r[0]['track_power_low'].__setitem__(1,.99),lambda r:r[0]['track_scores'].__setitem__(1,math.inf),lambda r:r[0].update(power=.9),lambda r:r[0].update(score=.9),lambda r:r[0].update(mde=.9),lambda r:r[0].update(power_curve='different')]
        for mutate in changes:
            rows=make_rows();mutate(rows)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):c.validate_rows(*encode_rows(rows))

    def test_case_schema_index_binding_and_settings(self):
        mutations=[lambda x:x.update(index=1),lambda x:x.update(index=True),lambda x:x.update(schema='v2'),lambda x:x.update(status='partial'),lambda x:x.update(diagnostics_status='failed'),lambda x:x.update(error='oops'),lambda x:x.update(extra=1),lambda x:x.pop('calibration_right'),lambda x:x['settings'].update(repetitions=900),lambda x:x['settings'].update(stage=True),lambda x:x['settings']['design'].update(shape=0),lambda x:x['nonfinite_fields'].update(extra=[]),lambda x:x['seeds'].update(derived_seed=1),lambda x:x['data']['left'].update(sha256='0'*64),lambda x:x['data']['left']['values'].update(extra=1),lambda x:x['availability_left'][0].update(projected_to_zero=True),lambda x:x['scores_left'].__setitem__(0,.9)]
        for mutate in mutations:
            value=make_case();mutate(value)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):c.validate_case(value,0)

    def test_duplicate_json_members_and_nonfinite_literals(self):
        for text in ('{"x":1,"x":2}','{"x":{"a":1,"a":2}}','{"x":NaN}','[Infinity]','[1e999]'):
            with self.subTest(text=text),self.assertRaises(ValueError):c.loads(text)

    def test_seed_boundary_goldens(self):
        self.assertEqual(c.derived_seed(0),8738233689029321767);self.assertEqual(c.derived_seed(119),5737789723273926856)

    def test_signed_zero_comparison(self):
        self.assertFalse(c.same_double(-0.0,0.0));self.assertTrue(c.same_double(math.nan,math.nan));self.assertFalse(c.same_double(math.inf,-math.inf))
        with self.assertRaises(ValueError):c.require_same_json(-0.0,0.0,'zero')


class SelectorTests(unittest.TestCase):
    def test_fixed_family_sets_and_rms_excluded(self):
        for track,size in zip(c.TRACKS,(4,7,4)):
            ref=c.reference_selection(make_rows(),track)
            self.assertEqual(ref['candidates'],list(c.FAMILIES[track]));self.assertEqual(len(ref['candidates']),size);self.assertNotIn('rms',ref['candidates'])

    def test_unique_max_ties_and_scores_irrelevant(self):
        rows=make_rows();set_track(rows[7],.9,.8,.95)
        rows[0]['score']=100;rows[0]['track_scores'][0]=100
        self.assertEqual(c.reference_selection(rows,'location')['best'],'mean')
        set_track(rows[0],.9,.8,.95)
        self.assertEqual(c.reference_selection(list(reversed(rows)),'location')['best'],'median')

    def test_inclusive_touch_separated_and_weaker_overlap(self):
        rows=make_rows()
        for row in rows:set_track(row,.3,.2,.4)
        set_track(rows[0],.8,.7,.9);set_track(rows[7],.6,.5,.7);set_track(rows[10],.6,.5,math.nextafter(.7,0));set_track(rows[11],.1,.05,.95)
        ref=c.reference_selection(rows,'location')
        self.assertEqual(ref['candidates'],['median','mean','trimmed_mean_20']);self.assertEqual(ref['qualified'],['median'])

    def test_fpr_boundary_nextafter_and_inflated(self):
        rows=make_rows()
        rows[0]['fpr_high']=c.FPR_LIMIT;rows[7]['fpr_high']=math.nextafter(c.FPR_LIMIT,math.inf);rows[10]['fpr_inflated']=True
        ref=c.reference_selection(rows,'location')
        self.assertIn('median',ref['candidates']);self.assertNotIn('mean',ref['candidates']);self.assertNotIn('geometric_mean',ref['candidates'])

    def test_quality_is_not_membership_gate(self):
        rows=make_rows()
        for row in rows:set_track(row,.8,math.nextafter(.7,0),.9)
        rows[0]['track_power_low'][0]=.7
        ref=c.reference_selection(rows,'location');self.assertEqual(len(ref['candidates']),4);self.assertEqual(ref['qualified'],['median'])
        rows[0]['track_power_low'][0]=math.nextafter(.7,0)
        ref=c.reference_selection(rows,'location');self.assertEqual(len(ref['candidates']),4);self.assertEqual(ref['status'],'uncertain')

    def test_genuine_empty_reasons(self):
        for applicable in (True,False):
            rows=make_rows()
            for row in rows:
                if applicable:row['fpr_high']=1.0
                else:unavailable(row)
            ref=c.reference_selection(rows,'location');self.assertEqual(ref['candidates'],[]);self.assertIsNone(ref['best']);self.assertEqual(ref['status'],'unavailable')
            self.assertEqual(ref['empty_reasons'],['applicable_natural_rows_fail_null_control' if applicable else 'no_applicable_natural_family'])


class ArithmeticTests(unittest.TestCase):
    def test_empty_equal_disjoint_partial_jaccard(self):
        cases=[(set(),set(),Fraction(1)),(set(),{'median'},Fraction(0)),({'median'},{'median'},Fraction(1)),({'median'},{'mean'},Fraction(0)),({'median','mean'},{'mean','geometric_mean'},Fraction(1,3))]
        for a,b,expected in cases:self.assertEqual(c.jaccard(a,b),expected)

    def test_skewed_marginals_high_agreement_without_excess(self):
        # Left marginal 3/4 A, right always A: observed equals product reference.
        out=c.chance_summary([{'median'}]*3+[{'mean'}],[{'median'}]*4)
        self.assertEqual(out['cross_pair_count'],16);self.assertEqual(out['explicit_cross_match_count'],12)
        self.assertEqual(out['exact']['observed'],c.rational(Fraction(3,4)));self.assertEqual(out['exact']['adjusted'],c.rational(0))

    def test_cross_and_category_product_exact(self):
        left=[set(),{'median'},{'median'},{'mean'}];right=[{'median'},set(),{'mean'},{'median'}]
        out=c.chance_summary(left,right)
        self.assertEqual(out['explicit_cross_match_count'],6);self.assertEqual(out['category_product_match_count'],6)
        self.assertEqual(out['exact']['reference'],c.rational(Fraction(3,8)))

    def test_mean_jaccard_is_not_expected_intersection_over_union(self):
        left=[{'median'},{'median','mean'}];right=[{'median'},{'mean'}]
        out=c.chance_summary(left,right)
        self.assertEqual(out['jaccard']['reference'],c.rational(Fraction(1,2)))
        ratio=Fraction(sum(len(a&b) for a in left for b in right),sum(len(a|b) for a in left for b in right))
        self.assertEqual(ratio,Fraction(3,7));self.assertNotEqual(out['jaccard']['reference'],c.rational(ratio))

    def test_degenerate_negative_and_zero_denominator(self):
        deg=c.chance_summary([set()]*3,[set()]*3)
        self.assertIsNone(deg['exact']['adjusted']);self.assertEqual(deg['exact']['undefined_reason'],'degenerate_marginals')
        neg=c.chance_summary([{'median'},{'mean'}],[{'mean'},{'median'}])
        self.assertEqual(neg['exact']['adjusted'],c.rational(-1))
        empty=c.chance_summary([],[]);self.assertIsNone(empty['exact']);self.assertEqual(empty['cross_pair_count'],0)

    def test_type7_exact_quantiles(self):
        self.assertEqual(c.quantile([0,1,2,3],Fraction(1,4)),c.rational(Fraction(3,4)))
        self.assertEqual(c.quantile([0,1,2,3],Fraction(1,2)),c.rational(Fraction(3,2)))

    def test_all120_denominators_and_empty_contribution(self):
        pairs=[{'left':selection(['median']),'right':selection(['median'])} for _ in range(60)]+[{'left':selection([]),'right':selection([])} for _ in range(60)]
        result=c.summarize_track(pairs,'location')
        self.assertEqual(result['denominator'],120);self.assertEqual(result['all_pairs']['candidate_chance']['cross_pair_count'],14400)
        self.assertEqual(result['exact_candidate']['count'],120);self.assertEqual(result['nonempty_exact_match']['count'],60);self.assertEqual(result['real_best_match']['count'],60)
        self.assertEqual(result['both_nonempty']['denominator'],60);self.assertEqual(result['both_nonempty']['candidate_chance']['cross_pair_count'],3600)
        self.assertEqual(result['all_pairs']['exact_set_minus_singleton'],c.rational(0))
        self.assertEqual(result['sides']['left']['candidate_inclusion']['rms']['count'],0)
        self.assertEqual(sum(result['sides']['left']['statuses'][s]['count'] for s in ('qualified','uncertain','unavailable')),120)

    def test_same_B_conditional_marginals_not_sidewise_nonempty(self):
        pairs=[{'left':selection(['median']),'right':selection(['mean'])},{'left':selection(['mean']),'right':selection([])},{'left':selection([]),'right':selection(['median'])},{'left':selection([]),'right':selection([])}]
        result=c.summarize_track(pairs,'location');both=result['both_nonempty']
        self.assertEqual(both['denominator'],1);self.assertEqual(both['candidate_chance']['cross_pair_count'],1)
        self.assertEqual(result['empty_counts'],{'left':2,'right':2,'both_empty':1,'left_only_empty':1,'right_only_empty':1,'both_nonempty':1})
        self.assertEqual(result['union_nonempty_jaccard']['denominator'],3)
        self.assertEqual(result['all_pairs']['singleton_agreement']['count'],1)

    def test_all_empty_conditional_undefined(self):
        result=c.summarize_track([{'left':selection([]),'right':selection([])}]*120,'location')
        self.assertEqual(result['both_nonempty']['denominator'],0);self.assertIsNone(result['both_nonempty']['exact_candidate']['value']);self.assertIsNone(result['both_nonempty']['candidate_chance']['exact']);self.assertIsNone(result['union_nonempty_jaccard']['value'])


def make_native(raw):
    # Explicit all-full-family golden, using fixed equal .8 powers for all twelve rows.
    identity={'harness_sha256':'3'*64,'core_sha256':'4'*64,'runtime':'.NET 8.0.31','os':'synthetic Linux','architecture':'X64','engine_version':'1.6.2'}
    evaluations=[]
    for side in ('left','right'):
        for track in c.TRACKS:
            family='variability' if track=='variability' else 'location'
            keys=list(c.FAMILIES[track]);low,high=original_wilson(800)
            build=[]
            for key in c.KEYS:
                eligible=key in keys;quality='qualified' if eligible else 'outside_family'
                build.append({'track':track,'family':family,'metric':key,'family_eligible':eligible,'applicable':True,'null_controlled':True,'power':.8,'power_low':low,'power_high':high,'best_power':.8,'best_power_low':low,'candidate':eligible,'quality':quality,'reason':c.REASONS[quality]})
            evaluations.append({'side':side,'track':track,'build':build,'summary':{'track':track,'family':family,'status':'qualified','candidates':keys,'qualified_candidates':keys.copy(),'best_metric':keys[0],'best_power':.8,'best_power_low':low},'nonfinite_fields':[]})
    return {'schema':'mvs-candidate-set-audit/v1','status':'completed','index':0,'input_sha256':'5'*64,'method_id':c.METHOD,'identity':identity,'validation':{'accepted':True,'half_count':2,'track_count':3,'build_invocations':6,'summarize_invocations':6,'exact_finite_roundtrip':True},'inputs':{side:{'rows':copy.deepcopy(raw['calibration_'+side]),'nonfinite_fields':copy.deepcopy(raw['nonfinite_fields']['calibration_'+side])} for side in ('left','right')},'evaluations':evaluations}


class NativeParityTests(unittest.TestCase):
    def setUp(self):
        self.raw=make_case();self.source={'raw':self.raw,'rows':c.validate_case(self.raw,0)[0]};self.native=make_native(self.raw)

    def compare(self,native):
        return c.compare_native(native,self.source,0,'5'*64,self.native['identity'])

    def test_full_native_golden(self):
        result=self.compare(self.native);self.assertEqual(len(result),6)
        self.assertEqual(result[('left','location')]['best'],'median')
        self.assertEqual(result[('right','variability')]['best'],'standard_deviation')

    def test_native_output_fail_closed(self):
        mutations=[lambda x:x.update(status='failed'),lambda x:x.update(index=False),lambda x:x.update(input_sha256='6'*64),lambda x:x.update(method_id='other'),lambda x:x.update(extra=1),lambda x:x['validation'].update(build_invocations=5),lambda x:x['evaluations'].pop(),lambda x:x['evaluations'].reverse(),lambda x:x['evaluations'][0]['build'].reverse(),lambda x:x['evaluations'][0]['build'][0].update(power=math.nextafter(.8,1)),lambda x:x['evaluations'][0]['build'][0].update(power=None),lambda x:x['evaluations'][0]['build'][0].update(candidate=1),lambda x:x['evaluations'][0]['build'][0].update(reason='changed'),lambda x:x['evaluations'][0]['summary'].update(best_metric='mean'),lambda x:x['evaluations'][0]['summary'].update(status='uncertain'),lambda x:x['evaluations'][0]['summary']['candidates'].append('median'),lambda x:x['evaluations'][0]['summary']['qualified_candidates'].clear(),lambda x:x['inputs']['left']['rows'][0].update(score=.8),lambda x:x['evaluations'][0]['nonfinite_fields'].append({'path':'build[0].power','value':'NaN'})]
        for mutate in mutations:
            value=copy.deepcopy(self.native);mutate(value)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):self.compare(value)

    def test_summary_order_can_differ_but_duplicate_cannot(self):
        value=copy.deepcopy(self.native)
        value['evaluations'][0]['summary']['candidates'].reverse()
        value['evaluations'][0]['summary']['qualified_candidates'].reverse()
        self.compare(value)


class DriverTests(unittest.TestCase):
    def test_write_once(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x.json';c.write_json(p,{'a':1})
            with self.assertRaises(FileExistsError):c.write_json(p,{'a':2})
            self.assertEqual(c.read_json(p),{'a':1})

    def test_input_set_missing_extra_and_mutation(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with self.assertRaises(ValueError):c.input_paths(root)
            for i in range(120):
                p=root/f'case-{i:03d}';p.mkdir();(p/'native.json').write_text('{}')
            self.assertEqual(len(c.input_paths(root)),120)
            p=root/'case-120';p.mkdir();(p/'native.json').write_text('{}')
            with self.assertRaises(ValueError):c.input_paths(root)
            (p/'native.json').unlink();p.rmdir()
            paths=c.input_paths(root);items=[{'index':i,'path':str(p),'sha256':c.digest(p)} for i,p in enumerate(paths)]
            paths[1].write_text('{"changed":true}')
            with patch.object(c,'validate_case',return_value=({'left':[],'right':[]},{})),patch.object(c,'read_json',return_value={'calibration_left':[],'calibration_right':[],'nonfinite_fields':{}}):
                rows,audit=c.validate_population({'inputs':items})
            self.assertFalse(audit['valid']);self.assertEqual(audit['valid_pairs'],119);self.assertEqual(audit['errors'][0]['index'],1)
            with self.assertRaises(ValueError):c.validate_population({'inputs':items[:-1]})

    def test_native_wait_is_blocking_and_sequential(self):
        with tempfile.TemporaryDirectory() as t:
            script=Path(t)/'fake.py';script.write_text('import time\ntime.sleep(.025)\n')
            out=Path(t)/'out';out.mkdir()
            items=[{'index':i,'path':'synthetic-not-read','sha256':'0'*64} for i in range(3)]
            real_wait=subprocess.Popen.wait;timeouts=[]
            def checked_wait(proc,*args,**kwargs):
                timeouts.append(kwargs.get('timeout'));return real_wait(proc,*args,**kwargs)
            with patch.object(subprocess.Popen,'wait',checked_wait):r=c.execute_cases(out,[sys.executable,str(script)],items,wall_seconds=3)
            self.assertEqual(r['completed_processes'],3);self.assertFalse(r['stop_reasons']);self.assertTrue(all(x is None for x in timeouts))
            self.assertTrue(all((out/f'case-{i:03d}'/'attempt.json').is_file() for i in range(3)))

    def test_timeout_preserves_attempt_and_logs(self):
        with tempfile.TemporaryDirectory() as t:
            script=Path(t)/'fake.py';script.write_text('import time\nprint("started",flush=True)\ntime.sleep(30)\n')
            out=Path(t)/'out';out.mkdir();start=time.monotonic()
            r=c.execute_cases(out,[sys.executable,str(script)],[{'index':0,'path':'synthetic','sha256':'0'*64}],wall_seconds=.15)
            self.assertLess(time.monotonic()-start,2);self.assertIn('whole-run wall budget exceeded',r['stop_reasons'])
            self.assertTrue((out/'case-000'/'stderr.log').exists());self.assertTrue((out/'case-000'/'attempt.json').exists())

    def test_memory_watchdog_preserves_failure(self):
        with tempfile.TemporaryDirectory() as t:
            script=Path(t)/'fake.py';script.write_text('import time\nx=bytearray(30*1024*1024)\ntime.sleep(30)\n')
            out=Path(t)/'out';out.mkdir()
            r=c.execute_cases(out,[sys.executable,str(script)],[{'index':0,'path':'synthetic','sha256':'0'*64}],wall_seconds=3,rss_bytes=1024)
            self.assertIn('child process-group RSS budget exceeded',r['stop_reasons']);self.assertEqual(r['completed_processes'],0)

    def test_owned_descendant_cleaned_after_leader_exit(self):
        with tempfile.TemporaryDirectory() as t:
            child=Path(t)/'child.py'; child.write_text('import time\ntime.sleep(30)\n')
            pidfile=Path(t)/'child.pid'
            script=Path(t)/'leader.py'
            script.write_text('import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'+repr(str(child))+'])\nPath('+repr(str(pidfile))+').write_text(str(p.pid))\ntime.sleep(.04)\n')
            out=Path(t)/'out';out.mkdir()
            result=c.execute_cases(out,[sys.executable,str(script)],[{'index':0,'path':'synthetic','sha256':'0'*64}],wall_seconds=3)
            self.assertEqual(result['completed_processes'],1)
            pid=int(pidfile.read_text())
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                stat=Path('/proc')/str(pid)/'stat'
                if not stat.exists() or stat.read_text().rsplit(')',1)[1].split()[0]=='Z':break
                time.sleep(.01)
            else:self.fail('owned descendant survived leader cleanup')

    def test_reference_has_no_native_candidate_input_or_calibration(self):
        import inspect
        source=inspect.getsource(c.reference_selection)
        self.assertNotIn('native',source);self.assertNotIn('score',source);self.assertNotIn('Build(',source)
        source=Path(c.__file__).read_text()
        for forbidden in ('AnalysisEngine.Calibrate(', 'BenchmarkRunner.Calibrate(', 'BenchmarkDatasets.Generate(', 'SplitEntities('):self.assertNotIn(forbidden,source)


if __name__=='__main__':unittest.main()
