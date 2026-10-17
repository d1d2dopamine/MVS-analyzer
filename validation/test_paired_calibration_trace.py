"""Synthetic-only tests: no retained input data or native calibration invocation."""
import copy
from fractions import Fraction as F
import itertools
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import paired_calibration_trace as p


def fixture():
    rows=[]
    for metric in p.METRICS:
        row={k:0.0 for k in p.DOUBLES}
        row.update({k:[0.0]*3 for k in p.DOUBLE_ARRAYS})
        row.update(metric=metric,power_curve='1:0|1.02:0|1.05:0|1.1:0|1.2:0',tracks=p.TRACKS[:],track_curves=['1:0|1.02:0|1.05:0|1.1:0|1.2:0']*3,track_mde_status=['estimated_on_grid']*3,track_failures=[0]*3,repetitions=1000,null_failures=0,applicable=True,fpr_inflated=False)
        rows.append(row)
    return rows


def value(row,key):
    v=row['moments'][key]
    return F(v['numerator'],v['denominator']) if isinstance(v,dict) else v


class MomentTests(unittest.TestCase):
    def test_hand_fixtures(self):
        tests=[([0,0,1,1],[0,0,1,1],F(1,3),0,F(1,6),1,0),([0,0,1,1],[1,1,0,0],F(-1,3),F(1,3),F(1,6),-1,2),([0,0,1,1],[0,1,0,1],0,F(1,6),F(1,6),0,1),([1,1,1,0,0],[1,0,0,1,0],F(-1,20),F(7,50),F(3,25),-1/6,F(7,6))]
        for x,y,c,vp,vi,rho,ratio in tests:
            r=p.pair_moments(x,y)
            for key,expected in [('covariance',c),('paired_variance',vp),('independent_variance',vi),('variance_ratio',ratio)]: self.assertEqual(value(r,key),expected)
            self.assertAlmostEqual(value(r,'correlation'),rho)
    def test_exhaustive_two_to_six(self):
        for n in range(2,7):
            vectors=list(itertools.product((0,1),repeat=n))
            for x,y in itertools.product(vectors,repeat=2):
                r=p.pair_moments(x,y); rx=F(sum(x),n); ry=F(sum(y),n)
                cov=sum((F(a)-rx)*(F(b)-ry) for a,b in zip(x,y))/(n-1)
                vp=sum((F(a-b)-(rx-ry))**2 for a,b in zip(x,y))/(n-1)/n
                self.assertEqual(value(r,'covariance'),cov); self.assertEqual(value(r,'paired_variance'),vp)
                self.assertEqual(value(r,'independent_variance')-vp,2*cov/n)
                reverse=p.pair_moments(y,x)
                self.assertEqual(value(reverse,'difference'),-value(r,'difference'))
                self.assertEqual(value(reverse,'paired_variance'),vp)
    def test_missing_constant_invalid(self):
        for x,y in [([-1,0,1,1],[0,0,1,0]),([0,-1],[0,0]),([0,0],[-1,0]),([-1,0],[-1,0])]:
            r=p.pair_moments(x,y); self.assertEqual(r['reason'],'nonfinite_code_present'); self.assertTrue(all(v is None for v in r['moments'].values()))
        r=p.pair_moments([-1,-1,-1,0,0,0,1,1,1],[-1,0,1]*3); self.assertEqual(r['joint_counts'],[[1]*3]*3)
        for x,y in [([0]*4,[0]*4),([1]*4,[0]*4)]:
            r=p.pair_moments(x,y); self.assertEqual(value(r,'paired_variance'),0); self.assertIsNone(value(r,'correlation'));self.assertIsNone(value(r,'variance_ratio'))
        r=p.pair_moments([0]*4,[0,0,1,1]);self.assertEqual(value(r,'paired_variance'),F(1,12));self.assertEqual(value(r,'variance_ratio'),1)
        for x,n,reason in [([],0,'insufficient_repetitions'),([0],1,'insufficient_repetitions'),([0],2,'incomplete_trace'),([0,0],1,'extra_replications')]:self.assertEqual(p.pair_moments(x,x,n)['reason'],reason)
        with self.assertRaises(ValueError): p.pair_moments([2],[0])


class CodecTests(unittest.TestCase):
    def test_codec(self):
        self.assertEqual(p.encode([-1,0,1,-1]),b'\x24');self.assertEqual(p.encode([1,0,-1,1]),b'\x86')
        for n in range(10):
            for values in itertools.product((-1,0,1),repeat=n): self.assertEqual(p.decode(p.encode(values),n),list(values))
        for raw,n in [(b'\x03',1),(b'\x40',1),(b'',1),(b'\x00\x00',4)]:
            with self.assertRaises(ValueError): p.decode(raw,n)
        with self.assertRaises(ValueError):p.decode(b'\x00',4,'wrong')
    def test_offsets_grid(self):
        # Base-three column identities; no pair of84positions has same1000vector.
        records=[[((rep//(3**(pos%5))+pos//5)%3)-1 for pos in range(84)] for rep in range(1000)]
        # Use unique binary column patterns instead, spanning every position.
        records=[[1 if rep & (1<<(pos%10)) else (0 if (rep+pos)//10%2 else -1) for pos in range(84)] for rep in range(1000)]
        records=[[((rep*(pos+1)+rep//(pos+1)+pos)%3)-1 for pos in range(84)] for rep in range(1000)]
        self.assertEqual(len({tuple(r[pos] for r in records) for pos in range(84)}),84)
        raw=b''.join(p.encode(r) for r in records); self.assertEqual(p.frames(raw),records)
        counts,gc=p.count_codes(records)
        for pos in range(84):
            self.assertEqual(counts[pos],[sum(r[pos]==c for r in records) for c in [-1,0,1]])
            for g in range(5):self.assertEqual(gc[g][pos],[sum(records[r][pos]==c for r in range(g,1000,5)) for c in [-1,0,1]])
        for raw2 in [raw[:-1],raw+b'\x00',raw[:-21],raw+raw[:21]]:
            with self.assertRaises(ValueError): p.frames(raw2)
        with self.assertRaises(ValueError):p.count_codes([[0]*83])


class EqualityTests(unittest.TestCase):
    def test_every_field(self):
        a=fixture();self.assertFalse(p.compare_rows(a,copy.deepcopy(a),[],[]))
        reordered=[dict(reversed(list(r.items()))) for r in a];self.assertFalse(p.compare_rows(a,reordered,[],[]))
        for field in p.FIELDS:
            b=copy.deepcopy(a);v=b[0][field]
            if type(v) is bool:b[0][field]=not v
            elif type(v) is int:b[0][field]+=1
            elif type(v) is float:b[0][field]=math.nextafter(v,1)
            elif type(v) is str:b[0][field]+='changed'
            elif isinstance(v,list): b[0][field]=v[::-1] if len(set(v))>1 else [*v[:-1],('changed' if type(v[-1]) is str else v[-1]+1)]
            try:self.assertTrue(p.compare_rows(a,b,[],[]),field)
            except ValueError:pass
        b=copy.deepcopy(a);b[0]['fpr']=-0.0;self.assertTrue(p.compare_rows(a,b,[],[]))
        for k in ['repetitions','applicable','track_powers','track_failures','tracks']:
            b=copy.deepcopy(a);b[0][k]=None
            with self.assertRaises(ValueError):p.compare_rows(a,b,[],[])
        b=copy.deepcopy(a);b[0]['fpr']=None
        with self.assertRaises(ValueError):p.compare_rows(a,b,[],[])
        labels=[{'path':'[0].fpr','value':'NaN'}]
        self.assertFalse(p.compare_rows(b,b,labels,labels))
        for cls in ['Infinity','-Infinity']:self.assertTrue(p.compare_rows(b,b,labels,[{'path':'[0].fpr','value':cls}]))
        for bad in [[*labels,*labels],[{'path':'[1].fpr','value':'NaN'}],[{'path':'[0].fpr','value':'bad'}]]:
            with self.assertRaises(ValueError):p.compare_rows(b,b,labels,bad)
    def test_duplicate_json(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'x';f.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):p.read_json(f)

    def test_file_backed_negative_zero(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'rows.json'; base=fixture()
            f.write_text(json.dumps(base)); original=p.read_json(f)
            text=json.dumps(base).replace('"fpr": 0.0','"fpr": -0',1)
            f.write_text(text); negative=p.read_json(f)
            self.assertTrue(p.compare_rows(original,negative,[],[]))
            text=json.dumps(base).replace('"track_powers": [0.0','"track_powers": [-0',1)
            f.write_text(text); self.assertTrue(p.compare_rows(original,p.read_json(f),[],[]))
            self.assertFalse(p.exact_tree(p.parse_json('{"v":-0}'),p.parse_json('{"v":0}')))
            self.assertFalse(p.exact_tree({'v':True},{'v':1}))


class ReconstructionTests(unittest.TestCase):
    def test_wilson_mde(self):
        lo,hi=p.wilson(0,1000);self.assertLess(abs(lo),1e-15);self.assertAlmostEqual(hi,0.0038267584855551234)
        lo,hi=p.wilson(1000,1000);self.assertEqual(hi,1)
        self.assertIsNone(p.mde([.8,.9,.9,.9,.9]));self.assertIsNone(p.mde([0,None,.9,.9,.9]));self.assertIsNone(p.mde([0,.1,.2,.3,.4]))
        self.assertEqual(p.mde([0,.9,.1,.9,.9]),1+(1.02-1)*(.8-0)/(.9-0)-1)
    def test_validity_thresholds_and_observed_lengths(self):
        # Independent expected consequences tested via reconstruction mismatch inventory.
        data={'group_names':['a','b'],'entities':[{'group':g,'metrics':[1.]*12} for g in ['a','b'] for _ in range(4)]}
        for valid in [899,900,901]:
            records=[[0]*84 for _ in range(1000)]
            for r in records[valid:]:r[0]=r[12]=-1
            rows=fixture(); report=p.reconstruct(records,rows,data)
            errors={e['path']:e for e in report['errors']}
            expected=valid>=900
            self.assertEqual(errors.get('0.applicable',{}).get('expected',True),expected)
            self.assertEqual(report['counts'][0][0],1000-valid)
        data['entities'].pop()
        report=p.reconstruct([[0]*84 for _ in range(1000)],fixture(),data)
        self.assertTrue(any(e['path']=='0.applicable' and e['expected'] is False for e in report['errors']))
    def test_grid_validity_thresholds(self):
        data={'group_names':['a'],'entities':[{'group':'a','metrics':[1.]*12} for _ in range(4)]}
        for valid in [179,180,181]:
            records=[[0]*84 for _ in range(1000)]
            for rep in list(range(0,1000,5))[valid:]:records[rep][48]=-1
            report=p.reconstruct(records,fixture(),data)
            self.assertEqual(report['details'][0]['grid_rates'][0][0],0.0 if valid>=180 else None)

    def test_complete_reconstruction_and_mutations(self):
        records=[[0]*84 for _ in range(1000)]
        data={'group_names':['a','b'],'entities':[{'group':g,'metrics':[1.]*12} for g in ['a','b'] for _ in range(4)]}
        rows=fixture()
        for row in rows:
            row.update(mde=None,track_mdes=[None]*3,alpha=.05,fpr_low=2.168404344971009e-19,fpr_high=.003826758485555124,track_power_low=[2.168404344971009e-19]*3,track_power_high=[.003826758485555124]*3,track_mde_status=['target_not_reached_or_invalid_curve']*3)
        self.assertFalse(p.reconstruct(records,rows,data)['errors'])
        fields=['fpr','power','score','applicable','mde','fpr_inflated','power_curve','tracks','track_powers','track_scores','track_mdes','track_curves','repetitions','fpr_low','fpr_high','track_power_low','track_power_high','track_failures','track_mde_status','alpha','null_failures']
        for field in fields:
            mutated=copy.deepcopy(rows); v=mutated[0][field]
            if type(v) is bool:mutated[0][field]=not v
            elif v is None:mutated[0][field]=0.0
            elif type(v) in (int,float):mutated[0][field]+=1
            elif type(v) is str:mutated[0][field]='1:1|1.02:0|1.05:0|1.1:0|1.2:0'
            else:mutated[0][field][0]=1 if v[0] is None or type(v[0]) in (int,float) else 'invalid'
            try:self.assertTrue(p.reconstruct(records,mutated,data)['errors'],field)
            except (ValueError,IndexError):pass
    def test_fpr_boundary_and_mde_status(self):
        data={'group_names':['a'],'entities':[{'group':'a','metrics':[1.]*12} for _ in range(4)]}
        for rejected,expected in [(24,False),(25,True)]:
            records=[[0]*84 for _ in range(1000)]
            for row in records[:rejected]:row[0]=1
            result=p.reconstruct(records,fixture(),data)
            errors={e['path']:e for e in result['errors']}
            self.assertEqual(errors.get('0.fpr_inflated',{}).get('expected',False),expected)
            if expected:self.assertEqual(errors['0.track_mde_status[0]']['expected'],'fpr_inflated')
        result=p.reconstruct([[0]*84 for _ in range(20)],fixture(),data)
        self.assertTrue(any(e['expected']=='insufficient_simulations' for e in result['errors']))

    def test_tolerance_edges_and_exact_mde(self):
        records=[[0]*84 for _ in range(1000)]
        data={'group_names':['a'],'entities':[{'group':'a','metrics':[1.]*12} for _ in range(4)]}
        rows=fixture()
        for row in rows:row.update(mde=None,track_mdes=[None]*3,alpha=.05,fpr_low=2.168404344971009e-19,fpr_high=.003826758485555124,track_power_low=[2.168404344971009e-19]*3,track_power_high=[.003826758485555124]*3,track_mde_status=['target_not_reached_or_invalid_curve']*3)
        for delta,allowed in [(5e-16,True),(2e-15,False)]:
            altered=copy.deepcopy(rows);altered[0]['fpr_low']+=delta
            errors=p.reconstruct(records,altered,data)['errors']
            self.assertEqual(not any(e['path']=='0.fpr_low' for e in errors),allowed)
        for delta,allowed in [(5e-13,True),(2e-12,False)]:
            altered=copy.deepcopy(rows);altered[0]['track_scores'][0]=delta;altered[0]['score']=delta
            errors=p.reconstruct(records,altered,data)['errors']
            self.assertEqual(not any(e['path']=='0.track_scores[0]' for e in errors),allowed)
        # Nonmonotone first crossing: counts0,180,20,180,180 out of200.
        counts=[0,180,20,180,180]
        for rep,row in enumerate(records):row[48]=int(rep//5 < counts[rep%5])
        expected=1+(1.02-1)*(.8-0)/(.9-0)-1
        rows[0].update(mde=expected,track_mdes=[expected,None,None],power_curve='1:0|1.02:0.9|1.05:0.1|1.1:0.9|1.2:0.9',track_curves=['1:0|1.02:0.9|1.05:0.1|1.1:0.9|1.2:0.9',rows[0]['track_curves'][1],rows[0]['track_curves'][2]],track_mde_status=['estimated_on_grid','target_not_reached_or_invalid_curve','target_not_reached_or_invalid_curve'])
        self.assertFalse(p.reconstruct(records,rows,data)['errors'])
        rows[0]['track_mdes'][0]=math.nextafter(expected,1)
        self.assertTrue(any(e['path']=='0.track_mdes[0]' for e in p.reconstruct(records,rows,data)['errors']))


class MetadataTests(unittest.TestCase):
    def test_complete_case_and_identity_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input.json';out=root/'native';out.mkdir()
            records=[[0]*84 for _ in range(1000)];raw=b''.join(p.encode(r) for r in records)
            rows=fixture();labels=[]
            for i,row in enumerate(rows):
                row.update(mde=None,track_mdes=[None]*3,alpha=.05,fpr_low=2.168404344971009e-19,fpr_high=.003826758485555124,track_power_low=[2.168404344971009e-19]*3,track_power_high=[.003826758485555124]*3,track_mde_status=['target_not_reached_or_invalid_curve']*3)
                labels.extend([{'path':f'[{i}].mde','value':'NaN'}]+[{'path':f'[{i}].track_mdes[{j}]','value':'NaN'} for j in range(3)])
            data={'group_names':['a'],'entities':[{'group':'a','metrics':[1.]*12} for _ in range(4)]}
            identity={'runtime':'synthetic','environment_sha256':'env','core_sha256':'core','harness_sha256':'harness'}
            x={'index':0,'settings':{'synthetic':True},'seeds':{'calibration_left_seed':1,'calibration_right_seed':2},'data':{side:{'sha256':'data','values':data} for side in ['left','right']},'calibration_left':rows,'calibration_right':rows,'nonfinite_fields':{'calibration_left':labels,'calibration_right':labels}}
            p.write_json(source,x);p.write_json(out/'result.json',{'schema':'mvs-paired-calibration-case/v1','status':'completed','index':0,'halves':{'left':'completed','right':'completed'},'error':None})
            cc,gc=p.count_codes(records)
            metas={}
            for side in ['left','right']:
                (out/(side+'.codes.bin')).write_bytes(raw);p.write_json(out/(side+'.rows.json'),{'rows':rows,'nonfinite_fields':labels})
                meta={'schema':'mvs-calibration-codes-2bit/v1','status':'completed','index':0,'side':side,'seed':x['seeds']['calibration_'+side+'_seed'],'source_input_sha256':p.digest(source),'canonical_data_sha256':'data','freeze_sha256':'freeze','metric_order':p.METRICS,'tracks':p.TRACKS,'grid':p.GRID,'identity':identity,'expected_repetitions':1000,'observed_repetitions':1000,'expected_bytes':21000,'observed_bytes':21000,'complete_prefix_records':1000,'residual_bytes':0,'rows_sha256':p.digest(out/(side+'.rows.json')),'all_field_match':True,'header_bytes':0,'expected_symbols':84000,'observed_symbols':84000,'significant_bits':168000,'count_code_order':[-1,0,1],'flattening':'Null[metric],Power[track][metric],Grid[track][metric]','bit_order':'least-significant-symbol-first','sha256':p.digest(out/(side+'.codes.bin')),'counts':cc,'grid_counts':gc}
                meta.update(settings=x['settings'],source_input=str(source.resolve()),rows_file=side+'.rows.json',code_mapping=[{'code':-1,'bits':'00'},{'code':0,'bits':'01'},{'code':1,'bits':'10'}],mismatches=[],error=None)
                p.write_json(out/(side+'.meta.json'),meta);metas[side]=meta
            report=p.validate_case(out,source,'freeze',identity)
            self.assertTrue(all(not r['row_mismatches'] and not r['reconstruction']['errors'] for r in report.values()))
            for key in ['runtime','environment_sha256','core_sha256','harness_sha256']:
                meta=copy.deepcopy(metas['left']);meta['identity'][key]='corrupt';(out/'left.meta.json').write_text(json.dumps(meta))
                with self.assertRaises(ValueError):p.validate_case(out,source,'freeze',identity)
            for key,val in [('code_mapping',[]),('settings',{}),('header_bytes',False),('mismatches',['bad']),('error','bad'),('counts',[[False,0,1000]]*84)]:
                meta=copy.deepcopy(metas['left']);meta[key]=val;(out/'left.meta.json').write_text(json.dumps(meta))
                with self.assertRaises(ValueError):p.validate_case(out,source,'freeze',identity)
            for key in ['sha256','rows_sha256','freeze_sha256','source_input_sha256','canonical_data_sha256']:
                meta=copy.deepcopy(metas['left']);meta[key]='corrupt';(out/'left.meta.json').write_text(json.dumps(meta))
                with self.assertRaises(ValueError):p.validate_case(out,source,'freeze',identity)


class DriverTests(unittest.TestCase):
    def execute(self,command,wall=2,memory=4*1024**3):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input.json';source.write_text('{}')
            out=root/'out';out.mkdir()
            result=p.execute_cases(out,command,[source]*12,'freeze',{},wall_seconds=wall,workers=2,memory_bytes=memory)
            self.assertEqual(len(result['attempts']),12);self.assertTrue(result['stop_reasons'])
            self.assertTrue(all(not r['started'] for r in result['attempts'][2:]))
            return result
    def test_launch_failure(self):self.execute(['/definitely/missing'])
    def test_nonzero(self):self.execute([sys.executable,'-c','import sys;sys.exit(3)'])
    def test_watchdog_wall(self):
        r=self.execute([sys.executable,'-c','import time;time.sleep(20)'],wall=.1)
        self.assertLess(r['elapsed_seconds'],2);self.assertIn('whole-run wall timeout',r['stop_reasons'])
    def test_memory(self):self.assertEqual(self.execute([sys.executable],memory=1)['attempts'][0]['started'],False)
    def test_watchdog_read_failure(self):
        with patch.object(p,'group_rss',side_effect=OSError('synthetic')):self.execute([sys.executable])
    def test_zero_budget(self):self.assertFalse(any(r['started'] for r in self.execute([sys.executable],wall=0)['attempts']))

    def test_storage_failure(self):
        original=p.write_json
        def broken(path,value):
            if Path(path).name=='started.json':raise OSError('synthetic storage failure')
            return original(path,value)
        with patch.object(p,'write_json',side_effect=broken):
            result=self.execute([sys.executable,'-c','import time;time.sleep(20)'])
            self.assertFalse(result['remaining_or_zombie_groups'])
    def test_partial_trace_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input';source.write_text('{}');out=root/'out';out.mkdir()
            script="import pathlib,sys;d=pathlib.Path(sys.argv[sys.argv.index('--out')+1]);d.mkdir();(d/'left.codes.bin').write_bytes(b'x'*43);sys.exit(3)"
            result=p.execute_cases(out,[sys.executable,'-c',script],[source],'freeze',{},workers=1,wall_seconds=2)
            trace=out/'case-000/native/left.codes.bin';self.assertEqual(trace.read_bytes(),b'x'*43)
            item=next(i for i in result['attempts'][0]['files'] if i['path'].endswith('codes.bin'))
            self.assertEqual((item['complete_prefix_records'],item['residual_bytes']),(2,1))

    def test_terminal_status_and_summary(self):
        success={'stop_reasons':[],'end_drift':'passed','counts':{'matched':120},'remaining_or_zombie_groups':[]}
        self.assertEqual(p.exit_status('run',success),0)
        for key,val in [('stop_reasons',['failure']),('end_drift','changed'),('counts',{'matched':119}),('remaining_or_zombie_groups',[1])]:
            changed=dict(success);changed[key]=val;self.assertEqual(p.exit_status('run',changed),1)
        self.assertEqual(p.exit_status('report',{'accepted':False}),1)
        rows=[]
        for stratum,_,_ in p.PAIRS:
            row=p.pair_moments([0,0,1,1],[0,0,1,1]);row['stratum']=stratum;rows.append(row)
        summaries=p.summarize(rows)
        for stratum,planned in [('location',6),('variability',21),('heterogeneity',6),('null',66)]:
            self.assertEqual(summaries[stratum]['fields']['covariance']['planned_count'],planned)
            self.assertEqual(summaries[stratum]['positive_covariance_fraction'],{'numerator':planned,'denominator':planned})
    def test_directory_failure_accounts_all_cases(self):
        original=Path.mkdir
        def broken(path,*args,**kwargs):
            if path.name=='case-000':raise OSError('synthetic directory failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'mkdir',broken):
            result=self.execute([sys.executable]);self.assertEqual(len(result['attempts']),12)

    def test_failure_reconciles_physical_half(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);native=root/'native';native.mkdir();(native/'left.codes.bin').write_bytes(b'x'*22)
            self.assertEqual(p.reconcile_halves(root),{'left':'failed','right':'not_started'})
            with patch.object(Path,'exists',side_effect=OSError('synthetic unreadable')):
                self.assertEqual(p.reconcile_halves(root),{'left':'unknown','right':'unknown'})

if __name__=='__main__':unittest.main()
