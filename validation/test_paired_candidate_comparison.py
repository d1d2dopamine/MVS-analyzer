"""Pre-outcome literal and exhaustive oracles. No retained data is opened."""
import copy
from fractions import Fraction as F
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import signal
import threading
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import paired_candidate_comparison as p
import test_candidate_set_stability as oldtests
import test_paired_calibration_trace as tracetests


def oracle_tail(w,l):
    # Explicit enumeration, independent of comb/sum implementation.
    q=w+l
    return F(sum(sum(bits)>=w for bits in itertools.product((0,1),repeat=q)),2**q)


def pascal_tail(w,l):
    row=[1]
    for _ in range(w+l):row=[1]+[a+b for a,b in zip(row,row[1:])]+[1]
    return F(sum(row[w:]),2**(w+l))


def oracle_holm(values):
    order=sorted(range(len(values)),key=lambda i:(values[i],i));rejected=set()
    for rank,pos in enumerate(order):
        if values[pos]>=F(1,20*(len(values)-rank)):break
        rejected.add(pos)
    adjusted={pos:min(F(1),max((len(values)-s)*values[order[s]] for s in range(rank+1))) for rank,pos in enumerate(order)}
    return rejected,adjusted


def family_fixture(n,counts,eligible=None):
    family=['A','B','C','D'];vectors={m:[1]*k+[0]*(n-k) for m,k in zip(family,counts)}
    return p.paired_family(vectors,family,family if eligible is None else eligible)


class TailHolmTests(unittest.TestCase):
    def test_literal_tails_and_extremes(self):
        fixtures={(0,0):F(1),(1,0):F(1,2),(0,1):F(1),(2,0):F(1,4),(1,1):F(3,4),(2,1):F(1,2),(3,0):F(1,8),(3,1):F(5,16),(4,0):F(1,16),(4,1):F(3,16),(1,4):F(31,32)}
        for (w,l),v in fixtures.items():self.assertEqual(p.exact_tail(w,l)[2],v);self.assertEqual(pascal_tail(w,l),v)
        self.assertEqual(p.exact_tail(0,1000),(2**1000,1000,F(1)))
        self.assertEqual(p.exact_tail(1000,0),(1,1000,F(1,2**1000)))
        for vector in ([0]*8,[1]*8,[1,0]*4):
            r=p.paired_family({'A':vector,'B':vector},['A','B'],['A','B']);self.assertTrue(all(t['discordances']==0 and p.from_rational(t['raw_p'])==1 for t in r['tests']))
        for bad in ((-1,1),(1,-1),(1.0,1),(True,1)):
            with self.assertRaises(ValueError):p.exact_tail(*bad)

    def test_every_paired_vector_zero_to_six(self):
        cases=0
        for n in range(7):
            for outcomes in itertools.product(range(4),repeat=n):
                x=[v//2 for v in outcomes];y=[v%2 for v in outcomes];cells=[outcomes.count(i) for i in range(4)]
                w,l=cells[2],cells[1];value=p.exact_tail(w,l)[2]
                self.assertEqual(value,oracle_tail(w,l));self.assertEqual(value,pascal_tail(w,l));self.assertTrue(0<=value<=1)
                self.assertEqual(value+p.exact_tail(l,w)[2],1+F(math.comb(w+l,w),2**(w+l)))
                self.assertEqual(sum(x)-sum(y),w-l)
                if n:
                    r=p.paired_family({'A':x,'B':y},['A','B'],['A','B'])['tests'][0]
                    self.assertEqual([r[f'n{a}{b}'] for a,b in itertools.product((0,1),repeat=2)],cells)
                cases+=1
        self.assertEqual(cases,sum(4**n for n in range(7)))

    def test_fixed_family_first_threshold(self):
        for m,passing,failing in ((12,8,7),(42,10,9)):
            for count,expected in ((passing,True),(failing,False)):
                r=p.holm([F(1,2**count)]+[F(1)]*(m-1));self.assertEqual(r[0]['rejected'],expected)
        r=family_fixture(8,[8,0,0,0],['A','B'])
        self.assertEqual(len(r['tests']),12);self.assertEqual(r['candidates'],['A'])

    def test_strict_stop_adjusted_and_ties(self):
        values=[F(1,480),F(1,220),F(1,210)]+[F(1)]*9;r=p.holm(values)
        self.assertEqual([x['rejected'] for x in r],[True]+[False]*11)
        self.assertTrue(r[2]['passes_own_rank_threshold']);self.assertFalse(r[2]['prefix_passes'])
        self.assertEqual([p.from_rational(x['adjusted_p']) for x in r[:3]],[F(1,40),F(1,20),F(1,20)])
        r=p.holm([F(1,256),F(1,256)]+[F(1)]*10)
        self.assertEqual([x['holm_rank'] for x in r[:2]],[1,2]);self.assertTrue(all(x['rejected'] for x in r[:2]));self.assertEqual([p.from_rational(x['adjusted_p']) for x in r[:2]],[F(3,64)]*2)

    def test_exhaustive_holm_small_and_rank_boundaries(self):
        grid=[F(0),F(1,100),F(1,40),F(1,20),F(1,10),F(1)]
        for m in range(1,5):
            for values in itertools.product(grid,repeat=m):
                expected,adjusted=oracle_holm(values);actual=p.holm(values)
                self.assertEqual({i for i,r in enumerate(actual) if r['rejected']},expected)
                self.assertEqual({i:p.from_rational(r['adjusted_p']) for i,r in enumerate(actual)},adjusted)
            for rank in range(1,m+1):
                threshold=F(1,20*(m-rank+1))
                for delta,pass_ in ((-F(1,100000),True),(F(0),False),(F(1,100000),False)):
                    r=p.holm([F(0)]*(rank-1)+[threshold+delta]+[F(1)]*(m-rank));self.assertEqual(r[rank-1]['rejected'],pass_)


class SelectionTests(unittest.TestCase):
    def test_full_family_rejecting_and_multilevel_literals(self):
        r=family_fixture(8,[8,0,0,0]);self.assertEqual(r['candidates'],['A']);self.assertEqual(r['edges'],[['A','B'],['A','C'],['A','D']])
        self.assertTrue(all(p.from_rational(t['adjusted_p'])==F(3,64) for t in r['tests'] if t['rejected']))
        changed=family_fixture(8,[8,0,0,0],['B','C','D']);self.assertEqual(changed['candidates'],['B','C','D'])
        for a,b in zip(r['tests'],changed['tests']):
            for key in ('raw_p','adjusted_p','holm_rank','rejected'):self.assertEqual(a[key],b[key])
        r=family_fixture(16,[16,8,0,0]);self.assertEqual(r['candidates'],['A']);self.assertEqual(len(r['edges']),5)
        for t in r['tests']:
            if t['rejected']:self.assertEqual(p.from_rational(t['adjusted_p']),F(3,16384) if t['discordances']==16 else F(5,128))

    def test_simultaneous_graph_and_cycle_failure(self):
        family=list('ABCD');self.assertEqual(p.graph_select(family,family,[['A','B'],['B','C']]),['A','D'])
        with self.assertRaises(ValueError):p.graph_select(family,family,[['A','B'],['B','C'],['C','A']])
        self.assertEqual(p.graph_select(family,['B'],[['A','B']]),['B'])
        self.assertEqual(p.graph_select(family,[],[['A','B']]),[])

    def test_empirical_ties_and_equal_vectors(self):
        r=family_fixture(16,[16,16,0,0]);self.assertEqual(r['candidates'],['A','B']);self.assertEqual(r['maxima'],['A','B'])
        for k in (0,4,8):
            r=family_fixture(8,[k]*4);self.assertEqual(r['candidates'],list('ABCD'));self.assertTrue(all(p.from_rational(t['raw_p'])==1 for t in r['tests']))
        self.assertEqual(family_fixture(8,[8,0,0,0],[])['candidates'],[])

    def test_low_power_and_quality_boundary_is_label_only(self):
        family=p.FAMILIES['location'];rows=oldtests.make_rows();records=[[0]*84 for _ in range(1000)]
        for j,m in enumerate(family):
            count=8 if j==0 else 0;idx=p.METRICS.index(m);low,high=oldtests.original_wilson(count);oldtests.set_track(rows[idx],count/1000,low,high)
            for i in range(count):records[i][12+idx]=1
        oldref=p.old.reference_selection(rows,'location');h,tests=p.half_record(0,'left','location',rows,records,{'summary':{'status':oldref['status']}},{},{})
        self.assertEqual(h['new_candidates'],[family[0]]);self.assertEqual(h['new_qualified'],[]);self.assertEqual(h['new_status'],'uncertain');self.assertEqual(h['metric_context'][0]['power'],.008)
        self.assertEqual(h['invariant_checks']['qualification_nonempty_unchanged'],True)
        # Isolated label fixture, deliberately not a count-consistent CI claim.
        baseline=family_fixture(8,[8,0,0,0]);c=baseline['candidates']
        label=lambda lo:[m for m in c if lo[m]>=.70]
        self.assertEqual(label({'A':.70}),['A']);self.assertEqual(label({'A':math.nextafter(.70,0)}),[]);self.assertEqual(baseline['candidates'],['A'])

    def test_all_count_consistent_quality_invariants_and_wilson_monotone(self):
        lowers=[oldtests.original_wilson(k)[0] for k in range(1001)]
        self.assertTrue(all(a<=b for a,b in zip(lowers,lowers[1:])))
        # This independently sweeps the native formula, not 1001 observed native calls.
        for k in range(1001):self.assertAlmostEqual(lowers[k],p.old.wilson(k)[0],delta=1e-15)
        for counts in ([1000,800,0,0],[8,0,0,0],[800,800,780,0],[0,0,0,0],[700,650,500,200]):
            rows=oldtests.make_rows();family=p.FAMILIES['location'];vectors={}
            for m,k in zip(family,counts):
                idx=p.METRICS.index(m);oldtests.set_track(rows[idx],k/1000,*oldtests.original_wilson(k));vectors[m]=[1]*k+[0]*(1000-k)
            ref=p.old.reference_selection(rows,'location');new=p.paired_family(vectors,family,ref['pool']);qualified=[m for m in new['candidates'] if rows[p.METRICS.index(m)]['track_power_low'][0]>=.70]
            self.assertEqual(bool(ref['qualified']),bool(qualified))

    def test_missing_scope_and_side_cases(self):
        records=[[0]*84 for _ in range(8)];family=p.FAMILIES['location'];idx=p.METRICS.index(family[0])
        for missing_sides in (('left',),('right',),('left','right')):
            actual=[]
            for side in ('left','right'):
                r=copy.deepcopy(records)
                if side in missing_sides:r[3][12+idx]=-1
                f=p.paired_family(p.family_vectors(r,'location'),family,[]);actual.append(f['analysis_availability'])
                if side in missing_sides:
                    self.assertIsNone(f['tests']);self.assertIsNone(f['candidates']);self.assertEqual(f['unavailable_reason'][0]['positions'],[3])
            self.assertEqual(actual.count('unavailable_missing_power_code'),len(missing_sides))
        for pos in (0,12+8,24+idx,48+idx):
            r=copy.deepcopy(records);r[0][pos]=-1;self.assertEqual(p.paired_family(p.family_vectors(r,'location'),family,[])['analysis_availability'],'available')

    def test_exhaustive_four_metrics_one_to_four_all_eligibilities(self):
        family=list('ABCD');permuted=['C','A','D','B'];cases=0;subsets=[list(itertools.compress(family,bits)) for bits in itertools.product((0,1),repeat=4)]
        for n in range(1,5):
            vectors=list(itertools.product((0,1),repeat=n))
            for values in itertools.product(vectors,repeat=4):
                raw=dict(zip(family,values));result=p.paired_family(raw,family,family)
                self.assertFalse(result['edges']);self.assertEqual(result['candidates'],family)
                for t in result['tests']:
                    x,y=raw[t['competitor']],raw[t['target']];w=sum(a==1 and b==0 for a,b in zip(x,y));l=sum(a==0 and b==1 for a,b in zip(x,y))
                    self.assertEqual(p.from_rational(t['raw_p']),oracle_tail(w,l));self.assertEqual(t['competitor_rejections'],sum(x));self.assertEqual(t['target_rejections'],sum(y))
                # All eligibility subsets use the same already computed full family.
                for eligible in subsets:
                    selected=p.graph_select(family,eligible,result['edges']);self.assertEqual(selected,eligible)
                    maxima=[m for m in eligible if sum(raw[m])==max((sum(raw[e]) for e in eligible),default=-1)]
                    self.assertTrue(set(maxima)<=set(selected));self.assertEqual(bool(selected),bool(eligible))
                    self.assertEqual(set(p.graph_select(permuted,[m for m in permuted if m in eligible],result['edges'])),set(selected))
                # Consistent relabeling preserves all tests; canonical tie positions re-map.
                renamed={m:raw[m] for m in permuted};reverse=p.paired_family(renamed,permuted,permuted)
                a={(t['competitor'],t['target']):(t['raw_p'],t['adjusted_p'],t['rejected']) for t in result['tests']};b={(t['competitor'],t['target']):(t['raw_p'],t['adjusted_p'],t['rejected']) for t in reverse['tests']};self.assertEqual(a,b)
                cases+=1
        self.assertEqual(cases,sum(2**(4*n) for n in range(1,5)))


class SummaryTests(unittest.TestCase):
    def test_literal_jaccard_chance_negative_and_degenerate(self):
        self.assertEqual(p.jaccard([],[]),1);self.assertEqual(p.jaccard([],['A']),0);self.assertEqual(p.jaccard(['A','B'],['B','C']),F(1,3))
        r=p.chance([['A'],['B']],[['B'],['A']])
        for key in ('exact','jaccard'):
            self.assertEqual(p.from_rational(r[key]['observed']),0);self.assertEqual(p.from_rational(r[key]['baseline']),F(1,2));self.assertEqual(p.from_rational(r[key]['excess']),F(-1,2));self.assertEqual(p.from_rational(r[key]['adjusted']),-1)
        r=p.chance([['A','B']]*2,[['A','B']]*2);self.assertEqual(r['jaccard']['reason'],'degenerate_marginals');self.assertIsNone(r['exact']['adjusted'])
        r=p.chance([[],['A']],[[],['A']]);self.assertEqual(p.from_rational(r['exact']['baseline']),F(1,2));self.assertEqual(p.from_rational(r['exact']['adjusted']),1)
        r=p.chance([['A']],[['A']]);self.assertEqual(r['exact']['reason'],'degenerate_marginals')
        r=p.chance([['A'],['A','B']],[['A'],['A','B']]);self.assertEqual(p.from_rational(r['jaccard']['baseline']),F(3,4));self.assertNotEqual(F(3,4),F(5,7))
        self.assertIsNone(p.chance([],[])['exact']['baseline']);self.assertEqual(p.chance([],[])['exact']['reason'],'zero_denominator')

    def test_exhaustive_small_set_populations_and_quantiles(self):
        choices=[[],['A'],['B'],['A','B']]
        for n in (1,2,3):
            for sets in itertools.product(choices,repeat=2*n):
                left,right=sets[:n],sets[n:];r=p.chance(left,right)
                exact=0;overlap=F(0)
                for a in left:
                    for b in right:
                        union=sum(m in a or m in b for m in 'AB');intersection=sum(m in a and m in b for m in 'AB');exact+=a==b;overlap+=F(intersection,union) if union else F(1)
                self.assertEqual(r['exact_matches'],exact);self.assertEqual(p.from_rational(r['jaccard_sum']),overlap)
        for n in range(1,6):
            for values in itertools.product((0,1,2),repeat=n):
                v=sorted(values)
                for q in (F(0),F(1,4),F(1,2),F(3,4),F(1)):
                    h=(n-1)*q;i=h.numerator//h.denominator;f=h-i;expected=(1-f)*v[i]+f*v[min(i+1,n-1)];self.assertEqual(p.quantile(values,q),expected)
        r=p.finite_summary([.1,.2]);self.assertEqual(p.from_rational(r['median']),(F.from_float(.1)+F.from_float(.2))/2)

    def test_complete_summary_schema_shared_companions_and_denominators(self):
        family=p.FAMILIES['location'];halves=[];pairs=[]
        for i in range(3):
            local=[]
            for side in ('left','right'):
                rows=oldtests.make_rows();records=[[0]*84 for _ in range(1000)]
                for m in family:
                    idx=p.METRICS.index(m);oldtests.set_track(rows[idx],0.,*oldtests.original_wilson(0))
                    if i==0:rows[idx]['fpr_high']=.2
                ref=p.old.reference_selection(rows,'location');h,ts=p.half_record(i,side,'location',rows,records,{'summary':{'status':ref['status']}},{},{})
                halves.append(h);local.append(h)
            pairs.append(p.pair_record(*local))
        s=p.summarize_track(halves,pairs,'location',3);self.assertEqual(s['observed_denominators']['B'],2);self.assertEqual(s['observed_denominators']['U'],2)
        for method in ('old','new'):
            r=s['methods'][method];self.assertEqual(r['empty_categories']['both_empty'],1);self.assertEqual(r['chance_B']['cross_pairs'],4);self.assertEqual(r['chance_all']['cross_pairs'],9);self.assertEqual(r['chance_B']['exact']['reason'],'degenerate_marginals')
            for side in ('left','right'):self.assertEqual(sum(r['sides'][side]['candidate_sizes']['histogram'].values()),3)
        empty=[h for h in halves if h['case_index']==0];ss=p.summarize_track(empty,pairs[:1],'location',1)
        self.assertEqual(ss['methods']['old']['B']['reason'],'zero_denominator');self.assertIsNone(ss['new_minus_old']['B_exact_difference'])
        mutated=copy.deepcopy(local[1]);mutated['new_candidates']=[]
        with self.assertRaises(ValueError):p.pair_record(local[0],mutated)


class BoundaryTests(unittest.TestCase):
    def test_declared_subset_and_complete_input_inventory(self):
        required=['case-000/native.json','bind.json'];observed=['prior.log','bind.json','case-000/native.json']
        declared,supplementary=p.partition_input_inventory(required,observed)
        self.assertEqual(declared,sorted(required));self.assertEqual(supplementary,['prior.log']);self.assertEqual(set(declared+supplementary),set(observed))
        self.assertEqual(p.partition_input_inventory(required,required),(sorted(required),[]))
        for declared,actual in [(required,['bind.json']),(required+['bind.json'],observed),(required,observed+['prior.log'])]:
            with self.assertRaises(ValueError):p.partition_input_inventory(declared,actual)

    def test_strict_fractions(self):
        self.assertEqual(p.from_rational(p.rational(F(-1,2))),F(-1,2))
        for value in ({'numerator':'2','denominator':'4'},{'numerator':'1','denominator':'-2'},{'numerator':1,'denominator':'2'},{'numerator':'01','denominator':'2'},{'numerator':'1','denominator':'0'}):
            with self.assertRaises((ValueError,TypeError)):p.from_rational(value)

    def test_write_once_and_direct_worker_denied(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'one';p.write_json(f,{'x':1})
            with self.assertRaises(FileExistsError):p.write_json(f,{'x':2})
            p.write_json(Path(d)/'bind.json',{'synthetic':True})
            with self.assertRaises(ValueError):p.worker(d)

    def supervise_fixture(self,script,limits=None):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);resources={'samples':0,'peak_aggregate_rss_bytes':0,'peak_output_bytes':0,'maximum_observed_sample_gap_seconds':0,'last_sample_monotonic':time.monotonic(),'processes':[]}
            original=p.LIMITS
            custom=dict(original,**(limits or {}))
            with patch.object(p,'LIMITS',custom):
                try:p.supervise([sys.executable,'-c',script],out,'synthetic',time.monotonic()+custom['wall_seconds'],resources,dict(os.environ))
                except Exception as exc:return resources,str(exc),sorted(x.name for x in out.iterdir())
            return resources,None,sorted(x.name for x in out.iterdir())

    def test_success_sequential_wait_and_returncode(self):
        r,error,files=self.supervise_fixture('import time;time.sleep(.1);print("synthetic")');self.assertIsNone(error);self.assertEqual(r['processes'][0]['state'],'completed');self.assertGreaterEqual(r['processes'][0]['wall_seconds'],.1)
        r,error,files=self.supervise_fixture('raise SystemExit(7)');self.assertIn('exit 7',error);self.assertEqual(r['processes'][0]['state'],'failed');self.assertIn('synthetic.stderr.log',files)

    def test_launch_failure_is_recorded(self):
        with patch.object(p.subprocess,'Popen',side_effect=FileNotFoundError('synthetic missing executable')):
            r,error,files=self.supervise_fixture('pass')
        self.assertEqual(r['processes'][0]['state'],'failed');self.assertEqual(r['processes'][0]['reason'],'launch_failure');self.assertIsNone(r['processes'][0]['pid']);self.assertEqual(r['processes'][0]['cleanup']['status'],'not_needed_no_process')

    def test_signal_terminates_owned_group_and_restores_handler(self):
        previous=signal.getsignal(signal.SIGTERM);signal.signal(signal.SIGTERM,p.termination_signal)
        timer=threading.Timer(.15,lambda:os.kill(os.getpid(),signal.SIGTERM));timer.start()
        try:
            r,error,files=self.supervise_fixture('import time;time.sleep(10)')
            self.assertIn('received signal',error);self.assertEqual(r['processes'][0]['cleanup']['live_members_after'],[]);self.assertEqual(r['processes'][0]['state'],'failed')
        finally:
            timer.cancel();timer.join();signal.signal(signal.SIGTERM,previous)
        self.assertEqual(signal.getsignal(signal.SIGTERM),previous)

    @staticmethod
    def good_attestation(bind='a'*64):
        return {'valid':True,'status':'passed','binding_sha256':bind,'verifier_sha256':'b'*64,'counts':{'half_tracks':720,'ordered_tests':15840,'native_build_invocations':720,'native_summarize_invocations':720,'traces':240,'pair_tracks':360},'summary_tracks_checked':p.TRACKS,'all_summary_fields_exact':True}

    def test_contradictory_or_unbound_audit_rejected(self):
        binding={'verifier_command':['python','synthetic-verifier'],'pins':{'synthetic-verifier':'b'*64}};good=self.good_attestation();p.validate_audit_attestation(good,'a'*64,binding)
        for key,value in [('valid',False),('status','failed'),('binding_sha256','c'*64),('verifier_sha256','c'*64),('counts',{}),('summary_tracks_checked',list(reversed(p.TRACKS))),('all_summary_fields_exact',False)]:
            bad=copy.deepcopy(good);bad[key]=value
            with self.assertRaises(ValueError):p.validate_audit_attestation(bad,'a'*64,binding)

    def test_partial_native_attempt_reconciles_without_success(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'native/case-000';folder.mkdir(parents=True);(folder/'started.json').write_text('{"state":"started"}');(folder/'attempt.json').write_text('{"returncode":')
            states=p.native_case_states(d)
            self.assertEqual(len(states),120);self.assertEqual(states[0]['state'],'unknown_partial_attempt');self.assertTrue(states[0]['parse_error']);self.assertEqual(states[0]['attempt_evidence']['bytes'],len('{"returncode":'));self.assertEqual(states[1]['state'],'not_started')
            (folder/'attempt.json').write_text('')
            self.assertEqual(p.native_case_states(d)[0]['state'],'unknown_partial_attempt')

    def test_terminal_inventory_failure_cannot_attest_completion(self):
        self.finalization_fixture(unplanned=True,small_limit=False)

    def test_terminal_size_failure_cannot_attest_completion(self):
        self.finalization_fixture(unplanned=False,small_limit=True)

    def finalization_fixture(self,unplanned,small_limit):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);p.write_json(out/'bind.json',{'synthetic_only':True})
            m={'commands':{name:[name] for name in ('worker','verifier','postpins')},'output_inventory':p.BASE_ARTIFACTS,'verifier_command':['python','synthetic-verifier'],'pins':{'synthetic-verifier':'b'*64}}
            def fake_supervise(command,out,label,deadline,resources,env):
                if label=='worker' and unplanned:(out/'unexpected.txt').write_text('synthetic')
                if label=='verifier':p.write_json(out/'independent-audit.json',self.good_attestation(p.digest(out/'bind.json')))
                if label=='postpins':p.write_json(out/'post-run-pins.json',{'valid':True})
            with patch.object(p,'verify',return_value=m),patch.object(p,'supervise',side_effect=fake_supervise),patch.object(p,'LIMITS',dict(p.LIMITS,output_bytes=1 if small_limit else p.LIMITS['output_bytes'])):
                result=p.run(out,p.digest(out/'bind.json'))
            self.assertEqual(result['status'],'technical_failure');self.assertEqual(p.read_json(out/'run.json')['status'],'technical_failure');self.assertEqual(p.read_json(out/'resources.json')['status'],'technical_failure');self.assertTrue(p.read_json(out/'run.json')['finalization_errors'])

    def test_deadline_memory_output_and_descendant_cleanup(self):
        r,error,_=self.supervise_fixture('import time;time.sleep(10)',{'wall_seconds':.1});self.assertEqual(error,'global_wall_deadline');self.assertEqual(r['processes'][0]['cleanup_group_rss_bytes'],0)
        r,error,_=self.supervise_fixture('import time;time.sleep(10)',{'aggregate_rss_bytes':1});self.assertEqual(error,'aggregate_rss_limit')
        r,error,_=self.supervise_fixture('print("x"*100000);import time;time.sleep(10)',{'output_bytes':1000});self.assertEqual(error,'evidence_output_limit')
        r,error,_=self.supervise_fixture('import subprocess,sys;subprocess.Popen([sys.executable,"-c","import time;time.sleep(10)"])',{'wall_seconds':.2});self.assertIsNotNone(error);self.assertEqual(r['processes'][0]['cleanup_group_rss_bytes'],0)


def load_tests(loader,tests,pattern):
    # Restore the original Round44 structural/selection/native-parity fixtures and
    # Round45 code/identity/reconstruction mutations without running retained data.
    suite=unittest.TestSuite([tests])
    for cls in (oldtests.LoaderTests,oldtests.SelectorTests,oldtests.NativeParityTests,tracetests.CodecTests,tracetests.EqualityTests,tracetests.ReconstructionTests,tracetests.MetadataTests):suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


if __name__=='__main__':unittest.main(verbosity=2)
