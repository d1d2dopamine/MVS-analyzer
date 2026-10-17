#!/usr/bin/env python3
"""Round45 test-only paired-code reference and write-once bounded driver.

prepare/verify/report do not invoke calibration. run is an explicitly gated single
attempt. No scientific inference, selected pairs, retries, or production changes.
"""
from __future__ import annotations
import argparse
from collections import Counter
from fractions import Fraction
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import struct
import subprocess
import time

from stability_replay_driver import write_json, digest, source_paths, pin_paths, require, group_rss, kill_group

METRICS = 'median standard_deviation coefficient_of_variation mad iqr normalized_mad normalized_iqr mean rms range geometric_mean trimmed_mean_20'.split()
TRACKS = ['location', 'variability', 'heterogeneity']
GRID = [1., 1.02, 1.05, 1.10, 1.20]
FIELDS = 'metric fpr power score robustness repeatability coverage applicable mde fpr_inflated power_curve tracks track_powers track_scores track_mdes track_curves repetitions fpr_low fpr_high track_power_low track_power_high track_failures track_mde_status alpha null_failures'.split()
DOUBLES = set('fpr power score robustness repeatability coverage mde fpr_low fpr_high alpha'.split())
DOUBLE_ARRAYS = set('track_powers track_scores track_mdes track_power_low track_power_high'.split())
INTS = {'repetitions', 'null_failures'}
BOOLS = {'applicable', 'fpr_inflated'}
STRINGS = {'metric', 'power_curve'}
STRING_ARRAYS = {'tracks', 'track_curves', 'track_mde_status'}
PAIRS = [(s, i, j) for s, indices in [('location', [0,7,10,11]), ('variability',[1,2,3,4,5,6,9]), ('heterogeneity',[0,7,10,11]), ('null',list(range(12)))] for i,j in itertools.combinations(indices,2)]
COUNT, WORKERS, WALL, CLEANUP, MEMORY = 120, 8, 900, 10, 4*1024**3


def parse_json(text):
    def pairs(items):
        result = {}
        for k,v in items:
            require(k not in result, 'duplicate JSON key: '+k)
            result[k]=v
        return result
    def invalid(value): raise ValueError('nonfinite JSON literal: '+value)
    def integer(value): return -0.0 if value == '-0' else int(value)
    value=json.loads(text,object_pairs_hook=pairs,parse_constant=invalid,parse_int=integer)
    def finite(v):
        if isinstance(v,float): require(math.isfinite(v),'nonfinite JSON number')
        elif isinstance(v,dict):
            for x in v.values(): finite(x)
        elif isinstance(v,list):
            for x in v: finite(x)
    finite(value)
    return value


def read_json(path):
    return parse_json(Path(path).read_text())


def exact_tree(a,b):
    if isinstance(a,dict) and isinstance(b,dict):
        return set(a)==set(b) and all(exact_tree(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):
        return len(a)==len(b) and all(exact_tree(x,y) for x,y in zip(a,b))
    if type(a) in (int,float) and type(b) in (int,float): return bits(a)==bits(b)
    return type(a)==type(b) and a==b


def bits(x):
    return struct.pack('>d', float(x)).hex()


def encode(values):
    result = bytearray((len(values)+3)//4)
    for i,v in enumerate(values):
        require(type(v) is int and v in (-1,0,1), 'invalid code')
        result[i//4] |= (v+1) << (2*(i%4))
    return bytes(result)


def decode(raw, symbols, sha256=None):
    require(type(symbols) is int and symbols >= 0, 'invalid symbol count')
    require(len(raw) == (symbols+3)//4, 'trace length mismatch')
    if sha256 is not None: require(hashlib.sha256(raw).hexdigest() == sha256, 'trace hash mismatch')
    if symbols % 4: require(raw[-1] >> (2*(symbols%4)) == 0, 'nonzero padding')
    result = [(raw[i//4] >> (2*(i%4))) & 3 for i in range(symbols)]
    require(3 not in result, 'reserved symbol 11')
    return [v-1 for v in result]


def frames(raw, expected=1000, sha256=None):
    require(len(raw) == expected*21, 'wrong frame count or torn frame')
    codes = decode(raw, expected*84, sha256)
    return [codes[i:i+84] for i in range(0,len(codes),84)]


def count_codes(records):
    require(all(len(r)==84 for r in records), 'wrong frame shape')
    counts = [[0,0,0] for _ in range(84)]
    grid_counts = [[[0,0,0] for _ in range(84)] for _ in GRID]
    for rep, row in enumerate(records):
        for p,c in enumerate(row):
            require(type(c) is int and c in (-1,0,1), 'invalid symbol')
            counts[p][c+1] += 1
            grid_counts[rep%5][p][c+1] += 1
    return counts, grid_counts


def validate_rows(rows, labels):
    require(type(rows) is list and len(rows)==12, 'expected 12 ordered rows')
    require(type(labels) is list, 'nonfinite labels must be list')
    mapping = {}
    for label in labels:
        require(type(label) is dict and set(label)=={'path','value'}, 'invalid nonfinite label')
        p, v = label['path'], label['value']
        require(p not in mapping and v in ('NaN','Infinity','-Infinity'), 'duplicate/invalid nonfinite label')
        mapping[p] = v
    nulls = set()
    def number(v,p):
        if v is None: nulls.add(p)
        else: require(type(v) in (int,float) and math.isfinite(v), 'invalid double at '+p)
    for i,row in enumerate(rows):
        require(type(row) is dict and set(row)==set(FIELDS), 'row property set mismatch')
        require(row['metric']==METRICS[i], 'metric order mismatch')
        for k,v in row.items():
            p = f'[{i}].{k}'
            if k in DOUBLES: number(v,p)
            elif k in DOUBLE_ARRAYS:
                require(type(v) is list and len(v)==3, 'double array shape '+p)
                for j,x in enumerate(v): number(x,f'{p}[{j}]')
            elif k in INTS: require(type(v) is int,'integer type '+p)
            elif k in BOOLS: require(type(v) is bool,'boolean type '+p)
            elif k in STRINGS: require(type(v) is str,'string type '+p)
            elif k in STRING_ARRAYS: require(type(v) is list and len(v)==3 and all(type(x) is str for x in v),'string array '+p)
            elif k=='track_failures': require(type(v) is list and len(v)==3 and all(type(x) is int for x in v),'integer array '+p)
    require(set(mapping)==nulls, 'unlabeled null, finite label, or unknown nonfinite path')
    return mapping


def compare_rows(expected, actual, expected_labels, actual_labels):
    """Schema-aware exact binary64 parity, independent of JSON numeric spelling."""
    em, am = validate_rows(expected,expected_labels), validate_rows(actual,actual_labels)
    errors = []
    def compare(a,b,p,double=False):
        if double and type(a) in (int,float) and type(b) in (int,float):
            if bits(a)!=bits(b): errors.append({'path':p,'expected_bits':bits(a),'actual_bits':bits(b),'expected_type':type(a).__name__,'actual_type':type(b).__name__})
        elif type(a)!=type(b): errors.append({'path':p,'expected_type':type(a).__name__,'actual_type':type(b).__name__})
        elif isinstance(a,list):
            if len(a)!=len(b): errors.append({'path':p,'reason':'array length'})
            for j,(x,y) in enumerate(zip(a,b)): compare(x,y,f'{p}[{j}]',double)
        elif a!=b: errors.append({'path':p,'expected':a,'actual':b})
    for i,(a,b) in enumerate(zip(expected,actual)):
        for k in FIELDS: compare(a[k],b[k],f'[{i}].{k}',k in DOUBLES or k in DOUBLE_ARRAYS)
    for p in sorted(set(em)|set(am)):
        if em.get(p)!=am.get(p): errors.append({'path':p,'expected_class':em.get(p),'actual_class':am.get(p)})
    return errors


def rational(f):
    return {'numerator': f.numerator, 'denominator':f.denominator, 'value':float(f)}


def pair_moments(x,y,expected=None):
    require(len(x)==len(y),'unequal pair lengths')
    expected = len(x) if expected is None else expected
    require(all(type(v) is int and v in (-1,0,1) for v in [*x,*y]),'invalid pair symbol')
    n=len(x); matrix=[[0]*3 for _ in range(3)]
    for a,b in zip(x,y): matrix[a+1][b+1]+=1
    ml=sum(matrix[0]); mr=sum(row[0] for row in matrix); both=matrix[0][0]
    a=sum(matrix[2])
    b=sum(row[2] for row in matrix)
    result={'joint_counts':matrix,'n_observed':n,'expected_n':expected,'missing_left':ml,'missing_right':mr,'both_missing':both,'missing_only_left':ml-both,'missing_only_right':mr-both,'jointly_valid':n-ml-mr+both,'rejections_left':a,'rejections_right':b}
    reason = 'incomplete_trace' if n<expected else 'extra_replications' if n>expected else 'insufficient_repetitions' if n<2 else 'nonfinite_code_present' if ml or mr else None
    result['reason']=reason
    result['rates'] = [rational(Fraction(a,n)),rational(Fraction(b,n))] if n==expected and n else None
    names=['difference','variance_left','variance_right','covariance','paired_variance','independent_variance','variance_reduction','correlation','variance_ratio','paired_mc_sd','independent_mc_sd']
    result['moments']={k:None for k in names}; result['undefined']={}
    if reason:
        result['undefined']={k:reason for k in names}; return result
    c=matrix[2][2]; q=matrix[2][1]+matrix[1][2]
    vi=Fraction(a*(n-a),n*(n-1)); vj=Fraction(b*(n-b),n*(n-1)); cov=Fraction(n*c-a*b,n*(n-1))
    vp=Fraction(n*q-(a-b)**2,n*n*(n-1)); vn=(vi+vj)/n
    require(vp>=0 and vn>=0,'negative variance numerator')
    vals={'difference':Fraction(a-b,n),'variance_left':vi,'variance_right':vj,'covariance':cov,'paired_variance':vp,'independent_variance':vn,'variance_reduction':vn-vp}
    result['moments'].update({k:rational(v) for k,v in vals.items()})
    result['covariance_sign']=(cov>0)-(cov<0)
    if vi and vj: result['moments']['correlation']=float(cov)/math.sqrt(float(vi*vj))
    else: result['undefined']['correlation']='constant_marginal'
    if vn: result['moments']['variance_ratio']=rational(vp/vn)
    else: result['undefined']['variance_ratio']='zero_independent_variance'
    result['moments']['paired_mc_sd']=math.sqrt(float(vp)); result['moments']['independent_mc_sd']=math.sqrt(float(vn))
    return result


def wilson(k,n):
    z=1.959963984540054; p=k/n; den=1+z*z/n
    center=(p+z*z/(2*n))/den; radius=z*math.sqrt(p*(1-p)/n+z*z/(4.0*n*n))/den
    return max(0,center-radius),min(1,center+radius)


def mde(curve):
    if any(v is None for v in curve) or curve[0]>=.8: return None
    for i in range(1,5):
        if curve[i]>=.8 and curve[i-1]<.8:
            return GRID[i-1]+(GRID[i]-GRID[i-1])*(.8-curve[i-1])/(curve[i]-curve[i-1])-1
    return None


def reconstruct(records, rows, data):
    counts,gc=count_codes(records); n=len(records); errors=[]; deltas=[]; details=[]
    def check(actual,expected,path,tolerance=0):
        if expected is None or actual is None: ok=actual is expected
        elif type(expected) is float:
            delta=float(actual)-expected; deltas.append({'path':path,'delta':delta,'absolute_error':abs(delta),'tolerance':tolerance})
            ok=abs(delta)<=tolerance if tolerance else bits(actual)==bits(expected)
        else: ok=type(actual)==type(expected) and actual==expected
        if not ok: errors.append({'path':path,'actual':actual,'expected':expected,'tolerance':tolerance})
    for i,row in enumerate(rows):
        observed=all(sum(1 for e in data['entities'] if e['group'].casefold()==g.casefold() and e['metrics'][i] is not None and math.isfinite(e['metrics'][i]))>=4 for g in data['group_names'])
        applicable=observed and n-counts[i][0]>=.9*n
        fpr=counts[i][2]/n if applicable else None; nominal=.05/12
        inflated=fpr is not None and fpr>min(1,max(1.5*nominal,nominal+.02))
        check(row['applicable'],applicable,f'{i}.applicable'); check(row['fpr'],fpr,f'{i}.fpr'); check(row['fpr_inflated'],inflated,f'{i}.fpr_inflated')
        check(row['null_failures'],counts[i][0],f'{i}.null_failures'); check(row['repetitions'],n,f'{i}.repetitions'); check(row['alpha'],.05,f'{i}.alpha')
        ci=wilson(counts[i][2],n) if applicable else (None,None)
        for key,v in zip(['fpr_low','fpr_high'],ci): check(row[key],v,f'{i}.{key}',1e-15)
        curves=[]
        for t in range(3):
            p=12+t*12+i; power=counts[p][2]/n if applicable and n-counts[p][0]>=.9*n else None
            check(row['track_powers'][t],power,f'{i}.track_powers[{t}]'); check(row['track_failures'][t],counts[p][0],f'{i}.track_failures[{t}]')
            ci=wilson(counts[p][2],n) if power is not None else (None,None)
            for key,v in zip(['track_power_low','track_power_high'],ci): check(row[key][t],v,f'{i}.{key}[{t}]',1e-15)
            totals=[sum(g[48+t*12+i]) for g in gc]
            curve=[g[48+t*12+i][2]/total if applicable and total and total-g[48+t*12+i][0]>=.9*total else None for g,total in zip(gc,totals)]
            curves.append(curve)
            estimate=mde(curve) if applicable and not inflated and min(totals)>=100 else None
            status='not_applicable' if not applicable else 'fpr_inflated' if inflated else 'insufficient_simulations' if min(totals)<100 else 'estimated_on_grid' if estimate is not None else 'target_not_reached_or_invalid_curve'
            check(row['track_mdes'][t],estimate,f'{i}.track_mdes[{t}]'); check(row['track_mde_status'][t],status,f'{i}.track_mde_status[{t}]')
            parts=row['track_curves'][t].split('|'); require(len(parts)==5,'curve shape')
            for j,part in enumerate(parts):
                e,v=part.split(':'); check(float(e),GRID[j],f'{i}.curve_effect[{t},{j}]')
                check(None if v=='NaN' else float(v),curve[j],f'{i}.curve_rate[{t},{j}]')
            score=100*math.sqrt(max(0,min(1,power))*max(0,min(1,math.exp(-max(0,fpr-nominal)/nominal)))) if power is not None else None
            check(row['track_scores'][t],score,f'{i}.track_scores[{t}]',1e-12)
        for key,track in [('power','track_powers'),('score','track_scores'),('mde','track_mdes'),('power_curve','track_curves')]: check(row[key],row[track][0],f'{i}.{key}')
        check(row['tracks'],TRACKS,f'{i}.tracks')
        details.append({'metric':METRICS[i],'grid_rates':curves,'null_rejection_fraction':rational(Fraction(counts[i][2],n)),'nominal_alpha':nominal})
    return {'errors':errors,'floating_deltas':deltas,'max_absolute_error':max((x['absolute_error'] for x in deltas),default=0),'counts':counts,'grid_counts':gc,'details':details,'score_dependencies':'power and FPR only; legacy diagnostics independently checked by exact native-row parity'}

PROTOCOL_SHA = 'f44ee37d238660eb7ebf54e55114cbed50965398d568015c785d145800c70951'


def child_env(command):
    return dict(os.environ,DOTNET_PROCESSOR_COUNT='1',DOTNET_GCHeapHardLimit='0x18000000',MVS_DISABLE_BACKUPS='1',DOTNET_ROLL_FORWARD='Disable',DOTNET_ROOT=str(Path(command[0]).parent))


def prepare(root,out,protocol,native_dir,input_dir,command):
    root,out,protocol,native_dir,input_dir=map(lambda p:Path(p).resolve(),(root,out,protocol,native_dir,input_dir))
    require(not out.exists(),'output exists; no overwrite/resume')
    require(digest(protocol)==PROTOCOL_SHA,'unreviewed protocol')
    plan=read_json(protocol); require(digest(root/plan['document_path'])==plan['document_sha256'],'protocol document changed')
    require(len(command)==2,'expected dotnet harness.dll')
    exe=shutil.which(command[0]); require(exe is not None,'missing executable')
    command=[str(Path(exe).resolve()),str(Path(command[1]).resolve())]
    native=sorted(p.resolve() for p in native_dir.rglob('*') if p.is_file())
    require(Path(command[1]) in native,'harness outside pinned build')
    runtime_root=Path(command[0]).parent
    runtime=[]
    for sub in ['shared/Microsoft.NETCore.App/8.0.31','host/fxr/8.0.31']:
        d=runtime_root/sub; require(d.is_dir(),'exact runtime absent'); runtime.extend(p.resolve() for p in d.rglob('*') if p.is_file())
    for p,h in plan['source_hashes'].items(): require(digest(root/p)==h,'source mismatch '+p)
    inputs=[]
    for i,item in enumerate(plan['inputs']):
        require(i==item['index'],'unordered input indices'); p=input_dir/item['path']; require(digest(p)==item['sha256'],'input changed')
        x=read_json(p); require(x['index']==i and x['metric_order']==METRICS,'input identity')
        require(x['identity']['environment_sha256']==plan['environment_sha256'],'R43 environment mismatch')
        for side in ['left','right']:
            d=x['data'][side]; require(hashlib.sha256(d['canonical_json'].encode()).hexdigest()==d['sha256']==item[side+'_data_sha256'],'canonical hash')
            require(exact_tree(parse_json(d['canonical_json']),d['values']),'canonical values mismatch')
            require(x['seeds']['calibration_'+side+'_seed']==item[side+'_seed'],'seed mismatch')
            validate_rows(x['calibration_'+side],x['nonfinite_fields']['calibration_'+side])
        inputs.append(p.resolve())
    require(len(inputs)==COUNT,'fixed120 inputs required')
    probe=subprocess.run([*command,'--inspect'],env=child_env(command),capture_output=True,text=True,timeout=30)
    require(probe.returncode==0,'native inspect failed '+probe.stderr)
    identity=json.loads(probe.stdout)
    if 'identity' in identity: identity=identity['identity']
    require(identity['environment_sha256']==plan['environment_sha256'] and identity['runtime']==plan['runtime'],'native runtime/probe discrepancy')
    sources=source_paths(root)
    provenance=[input_dir/'bind.json',input_dir/'bind.sha256',input_dir.parent/'mvs-r45-before.json',input_dir.parent/'mvs-r44-analysis/report.json',input_dir.parent/'mvs-r44-analysis/post-run-verification.json']
    require(digest(provenance[0])==provenance[1].read_text().strip(),'R43 binding checksum mismatch')
    pins=pin_paths(sources+native+runtime+inputs+provenance+[protocol,root/plan['document_path'],Path(command[0])])
    manifest={'schema':'mvs-paired-calibration-bind/v1','utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'root':str(root),'protocol':str(protocol),'native_dir':str(native_dir),'input_dir':str(input_dir),'inputs':[str(p) for p in inputs],'command':command,'identity':identity,'sources':[str(p) for p in sources],'native_files':[str(p) for p in native],'runtime_files':sorted(str(p) for p in runtime),'pins':pins,'pairs':PAIRS,'limits':plan['limits'],'freeze_argument':'SHA256 of this complete bind.json, transitively binding reviewed machine protocol','environment':{k:v for k,v in child_env(command).items() if k.startswith(('DOTNET_','MVS_'))},'python':{'version':platform.python_version(),'executable':sys_executable(),'sha256':digest(sys_executable())}}
    out.mkdir(parents=True); write_json(out/'bind.json',manifest)
    with (out/'bind.sha256').open('x') as f: f.write(digest(out/'bind.json')+'\n')
    return manifest


def sys_executable():
    import sys
    return str(Path(sys.executable).resolve())


def verify(out):
    out=Path(out); require(digest(out/'bind.json')==(out/'bind.sha256').read_text().strip(),'binding changed')
    m=read_json(out/'bind.json'); require(m['pins'][m['protocol']]==PROTOCOL_SHA,'protocol changed')
    require(m['pairs']==[list(p) for p in PAIRS] and len(m['inputs'])==COUNT,'fixed universe changed')
    require(m['limits']==read_json(m['protocol'])['limits'],'limits changed')
    require([str(p) for p in source_paths(Path(m['root']))]==m['sources'],'source set drift')
    require(sorted(str(p.resolve()) for p in Path(m['native_dir']).rglob('*') if p.is_file())==m['native_files'],'native set drift')
    for p,h in m['pins'].items(): require(digest(p)==h,'hash drift '+p)
    require(digest(m['python']['executable'])==m['python']['sha256'],'Python executable drift')
    return m


def validate_case(directory,source,freeze,identity):
    directory=Path(directory); x=read_json(source); result=read_json(directory/'result.json')
    require(result['schema']=='mvs-paired-calibration-case/v1' and result['status']=='completed' and result['index']==x['index'],'case failure')
    require(set(result)=={'schema','status','index','halves','error'} and result['error'] is None and set(result['halves'])=={'left','right'},'result envelope')
    reports={}
    for side in ['left','right']:
        require(result['halves'][side]=='completed','half not complete')
        meta=read_json(directory/(side+'.meta.json')); payload=read_json(directory/(side+'.rows.json'))
        expected_keys=set('schema index side status seed source_input source_input_sha256 canonical_data_sha256 freeze_sha256 identity settings metric_order tracks grid code_mapping flattening bit_order header_bytes expected_repetitions observed_repetitions expected_symbols observed_symbols expected_bytes observed_bytes significant_bits complete_prefix_records residual_bytes sha256 counts grid_counts count_code_order rows_file rows_sha256 all_field_match mismatches error'.split())
        require(set(meta)==expected_keys and set(payload)=={'rows','nonfinite_fields'},'metadata/payload keyset')
        require(meta['error'] is None and meta['mismatches']==[],'completed metadata failure detail')
        require(exact_tree(meta['identity'],identity) and exact_tree(meta['settings'],x['settings']),'full identity/settings mismatch')
        require(exact_tree(meta['code_mapping'],[{'code':-1,'bits':'00'},{'code':0,'bits':'01'},{'code':1,'bits':'10'}]),'code mapping mismatch')
        require(meta['source_input']==str(Path(source).resolve()) and meta['rows_file']==side+'.rows.json','file references mismatch')
        for key in ['index','seed','header_bytes','expected_repetitions','observed_repetitions','expected_symbols','observed_symbols','expected_bytes','observed_bytes','significant_bits','complete_prefix_records','residual_bytes']:
            require(type(meta[key]) is int,'integer metadata '+key)
        require(type(meta['counts']) is list and len(meta['counts'])==84 and type(meta['grid_counts']) is list and len(meta['grid_counts'])==5,'count shapes')
        for matrix in [meta['counts'],*meta['grid_counts']]:
            require(type(matrix) is list and len(matrix)==84 and all(type(row) is list and len(row)==3 and all(type(v) is int and v>=0 for v in row) for row in matrix),'count matrix types')
        require(meta['schema']=='mvs-calibration-codes-2bit/v1' and meta['status']=='completed','trace status/schema')
        require(meta['index']==x['index'] and meta['side']==side and meta['seed']==x['seeds']['calibration_'+side+'_seed'],'half identity')
        require(meta['source_input_sha256']==digest(source) and meta['canonical_data_sha256']==x['data'][side]['sha256'] and meta['freeze_sha256']==freeze,'half bindings')
        require(meta['metric_order']==METRICS and meta['tracks']==TRACKS and meta['grid']==GRID,'trace ordering')
        for key in ['runtime','environment_sha256','core_sha256','harness_sha256']:
            require(meta['identity'][key]==identity[key],'loaded identity mismatch '+key)
        require(meta['expected_repetitions']==meta['observed_repetitions']==1000 and meta['expected_bytes']==meta['observed_bytes']==21000 and meta['complete_prefix_records']==1000 and meta['residual_bytes']==0,'trace dimensions')
        require(meta['rows_sha256']==digest(directory/(side+'.rows.json')) and meta['all_field_match'] is True,'rows binding/native parity')
        require(meta['header_bytes']==0 and meta['expected_symbols']==meta['observed_symbols']==84000 and meta['significant_bits']==168000,'trace symbol shape')
        require(meta['count_code_order']==[-1,0,1] and meta['flattening']=='Null[metric],Power[track][metric],Grid[track][metric]' and meta['bit_order']=='least-significant-symbol-first','codec layout')
        raw=(directory/(side+'.codes.bin')).read_bytes(); records=frames(raw,sha256=meta['sha256'])
        differences=compare_rows(x['calibration_'+side],payload['rows'],x['nonfinite_fields']['calibration_'+side],payload['nonfinite_fields'])
        reconstruction=reconstruct(records,payload['rows'],x['data'][side]['values'])
        require(reconstruction['counts']==meta['counts'] and reconstruction['grid_counts']==meta['grid_counts'],'native/reference counts mismatch')
        reports[side]={'row_mismatches':differences,'reconstruction':reconstruction}
    return reports


def inventory(directory):
    result=[]
    for p in sorted(Path(directory).rglob('*')):
        if p.is_file():
            item={'path':str(p.relative_to(directory)),'bytes':p.stat().st_size,'sha256':digest(p)}
            if p.name.endswith('.codes.bin'): item.update(complete_prefix_records=item['bytes']//21,residual_bytes=item['bytes']%21)
            result.append(item)
    return result


def reconcile_halves(directory):
    states={}
    for side in ['left','right']:
        try:
            native=Path(directory)/'native'; marker=native/(side+'.started.json'); trace=native/(side+'.codes.bin'); meta=native/(side+'.meta.json')
            started=(marker.exists() and marker.stat().st_size>0) or (trace.exists() and trace.stat().st_size>0)
            states[side]='failed' if started else 'not_started'
            if meta.exists() and meta.stat().st_size:
                value=read_json(meta)['status']
                states[side]=value if value in ('completed','failed','not_started') else 'unknown'
        except Exception:
            states[side]='unknown'
    return states


def execute_cases(out,command,inputs,freeze,identity,wall_seconds=WALL,workers=WORKERS,memory_bytes=MEMORY,validator=validate_case):
    """Synthetic-test seam; public run binds all parameters to frozen constants."""
    out=Path(out); start=time.monotonic(); deadline=start+wall_seconds; pending=list(enumerate(inputs)); active={}; attempts=[]; reasons=[]; events=[]; peak=0; stop_time=None; owned=set()
    def stop(reason):
        nonlocal stop_time
        if reason not in reasons: reasons.append(reason); events.append({'elapsed':time.monotonic()-start,'reason':reason})
        if stop_time is None: stop_time=time.monotonic()
        for p in list(active): kill_group(p)
    handlers={}
    if __import__('threading').current_thread() is __import__('threading').main_thread():
        for sig in (signal.SIGINT,signal.SIGTERM): handlers[sig]=signal.signal(sig,lambda s,f:stop('driver signal '+str(s)))
    try:
        while pending or active:
            now=time.monotonic()
            if now>=deadline: stop('whole-run wall timeout')
            try:
                rss=group_rss(owned)+int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'); peak=max(peak,rss)
                if rss>memory_bytes: stop('aggregate RSS exceeded')
            except Exception as exc: stop('watchdog failure '+repr(exc))
            while pending and len(active)<workers and stop_time is None:
                index,source=pending[0]; directory=out/f'case-{index:03d}'; directory.mkdir(); pending.pop(0)
                record={'index':index,'started':False,'returncode':None,'halves':{'left':'not_started','right':'not_started'}}
                logs=[]
                try:
                    argv=[*command,'--input',str(source),'--index',str(index),'--sha256',digest(source),'--out',str(directory/'native'),'--freeze-sha256',freeze]
                    record['argv']=argv; record['elapsed_at_launch']=time.monotonic()-start
                    logs=[(directory/'stdout.log').open('xb'),(directory/'stderr.log').open('xb')]
                    if stop_time is not None or time.monotonic()>=deadline: raise TimeoutError('stop-before-launch')
                    p=subprocess.Popen(argv,stdout=logs[0],stderr=logs[1],env=child_env(command),start_new_session=True)
                    owned.add(p.pid); record.update(started=True,pid=p.pid); active[p]=(record,directory,source,logs)
                    write_json(directory/'started.json',record)
                    if stop_time is not None or time.monotonic()>=deadline: stop('stop-during-launch')
                except Exception as exc:
                    record['error']=repr(exc)
                    if not record['started']: attempts.append(record)
                    stop('launch failure')
                    for f in logs: f.close()
            for p,(record,directory,source,logs) in list(active.items()):
                code=p.poll()
                if code is None: continue
                record['returncode']=code; record['elapsed_at_exit']=time.monotonic()-start
                kill_group(p)
                for f in logs: f.close()
                try:
                    if code!=0: raise RuntimeError('native nonzero exit '+str(code))
                    reports=validator(directory/'native',source,freeze,identity)
                    write_json(directory/'validation.json',reports)
                    require(all(not r['row_mismatches'] and not r['reconstruction']['errors'] for r in reports.values()),'parity/reconstruction mismatch')
                    record['matched']=True
                except Exception as exc: record['error']=repr(exc); stop('case failure')
                record['halves']=reconcile_halves(directory)
                try: record['files']=inventory(directory); write_json(directory/'attempt.json',record)
                except Exception as exc: record['inventory_or_status_error']=repr(exc); stop('artifact finalization failure')
                attempts.append(record); del active[p]
            if stop_time is not None:
                for index,source in pending: attempts.append({'index':index,'started':False,'returncode':None,'halves':{'left':'not_started','right':'not_started'},'reason':'stopped_before_launch'})
                pending.clear()
                if time.monotonic()>=min(deadline,stop_time)+CLEANUP:
                    for p,(record,directory,source,logs) in list(active.items()):
                        kill_group(p); record.update(error='cleanup deadline; state unknown',cleanup_unknown=True,files=inventory(directory)); attempts.append(record)
                        for f in logs: f.close()
                    break
            if pending or active: time.sleep(.025)
    except BaseException as exc:
        stop('driver exception '+repr(exc))
    finally:
        for p in active: kill_group(p)
        until=min(deadline,stop_time if stop_time is not None else time.monotonic())+CLEANUP
        for p,(record,directory,source,logs) in list(active.items()):
            try:
                p.wait(timeout=max(.001,until-time.monotonic()))
                record['returncode']=p.returncode
            except subprocess.TimeoutExpired: record['cleanup_unknown']=True
            for f in logs:
                try: f.close()
                except OSError: pass
            record['halves']=reconcile_halves(directory)
            record['error']=record.get('error','driver stopped')
            try: record['files']=inventory(directory)
            except Exception as exc: record['inventory_error']=repr(exc)
            if not any(a['index']==record['index'] for a in attempts): attempts.append(record)
        for index,source in pending:
            if not any(a['index']==index for a in attempts): attempts.append({'index':index,'started':False,'returncode':None,'halves':{'left':'not_started','right':'not_started'},'reason':'driver_stopped'})
        for sig,handler in handlers.items(): signal.signal(sig,handler)
    remaining=[]
    for pid in owned:
        try: os.killpg(pid,0); remaining.append(pid)
        except ProcessLookupError: pass
    return {'attempts':sorted(attempts,key=lambda r:r['index']),'stop_reasons':reasons,'watchdog_events':events,'elapsed_seconds':time.monotonic()-start,'peak_aggregate_rss_bytes':peak,'remaining_or_zombie_groups':remaining,'planned_cases':len(inputs),'planned_halves':2*len(inputs)}


def run(out,authorized=False):
    require(authorized,'explicit --authorized-single-attempt required after review')
    out=Path(out); m=verify(out); write_json(out/'run-started.json',{'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'freeze_sha256':digest(out/'bind.json')})
    result=execute_cases(out,m['command'],m['inputs'],digest(out/'bind.json'),m['identity'])
    try: verify(out); result['end_drift']='passed'
    except Exception as exc: result['end_drift']=repr(exc)
    result['counts']={'requested':COUNT,'started':sum(r['started'] for r in result['attempts']),'matched':sum(r.get('matched',False) for r in result['attempts']),'failed':sum(r['started'] and not r.get('matched',False) for r in result['attempts']),'not_started':sum(not r['started'] for r in result['attempts'])}
    result['counts'].update(planned=COUNT,completed_native=sum(all(s=='completed' for s in r['halves'].values()) for r in result['attempts']),killed=sum((r.get('returncode') or 0)<0 for r in result['attempts']),cleanup_unknown=sum(r.get('cleanup_unknown',False) for r in result['attempts']))
    result['half_counts']={'planned':240,'native_status_counts':dict(Counter(s for r in result['attempts'] for s in r['halves'].values())),'independently_matched':2*sum(r.get('matched',False) for r in result['attempts']),'killed_or_interrupted':sum(sum(s=='failed' for s in r['halves'].values()) for r in result['attempts'] if (r.get('returncode') or 0)<0),'cleanup_unknown_cases':sum(r.get('cleanup_unknown',False) for r in result['attempts'])}
    write_json(out/'run.json',result); return result


def summarize(rows):
    result={}
    for stratum in [*TRACKS,'null']:
        subset=[r for r in rows if r['stratum']==stratum]; fields={}
        for field in subset[0]['moments']:
            vals=[]; undefined=Counter()
            for r in subset:
                v=r['moments'][field]
                if v is None: undefined[r['undefined'].get(field,r['reason'] or 'undefined')]+=1
                else: vals.append(Fraction(v['numerator'],v['denominator']) if isinstance(v,dict) else v)
            vals.sort(); n=len(vals)
            def present(v): return rational(v) if isinstance(v,Fraction) else v
            fields[field]={'planned_count':len(subset),'observed_valid_count':sum(r['n_observed']==r['expected_n'] for r in subset),'finite_count':n,'undefined_count':len(subset)-n,'undefined_by_reason':dict(undefined),'minimum':present(vals[0]) if n else None,'median':present(vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2) if n else None,'maximum':present(vals[-1]) if n else None}
        signs=Counter(r['covariance_sign'] for r in subset if 'covariance_sign' in r); defined=sum(signs.values())
        rate_values=[F for r in subset if r['rates'] is not None for F in [Fraction(v['numerator'],v['denominator']) for v in r['rates']]]
        result[stratum]={'marginal_rate_context':{'planned_count':2*len(subset),'finite_count':len(rate_values),'undefined_count':2*len(subset)-len(rate_values),'minimum':rational(min(rate_values)) if rate_values else None,'maximum':rational(max(rate_values)) if rate_values else None},'fields':fields,'covariance_sign_counts':{'negative':signs[-1],'zero':signs[0],'positive':signs[1]},'positive_covariance_fraction':{'numerator':signs[1],'denominator':defined},'defined_covariance_fraction':{'numerator':defined,'denominator':len(subset)},'weighting':'equal pair-half weights; dependent computations, not independent sample size'}
    return result


def report(out):
    out=Path(out); m=verify(out); execution=read_json(out/'run.json'); failures=[]; all_records=[]
    for i,source in enumerate(m['inputs']):
        d=out/f'case-{i:03d}'/'native'
        try:
            validation=validate_case(d,source,digest(out/'bind.json'),m['identity'])
            require(all(not r['row_mismatches'] and not r['reconstruction']['errors'] for r in validation.values()),'equality or reconstruction failed')
            for side in ['left','right']:
                rows=read_json(d/(side+'.rows.json'))['rows']; records=frames((d/(side+'.codes.bin')).read_bytes())
                all_records.append((i,side,rows,records))
        except Exception as exc: failures.append({'index':i,'error':repr(exc)})
    accepted=not failures and len(all_records)==240 and execution['end_drift']=='passed' and not execution['stop_reasons'] and not execution['remaining_or_zombie_groups']
    audit={'accepted':accepted,'completed_validated_halves':len(all_records),'planned_halves':240,'failures':failures,'interpretation':'withheld' if not accepted else 'conditional reused-synthetic-data descriptive moments; scientific NO-GO unchanged','inventory':inventory(out)}
    if accepted:
        pairs=[]
        for i,side,rows,records in all_records:
            for stratum,a,b in PAIRS:
                offset=0 if stratum=='null' else 12+12*TRACKS.index(stratum)
                item=pair_moments([r[offset+a] for r in records],[r[offset+b] for r in records],1000)
                item.update(case=i,side=side,stratum=stratum,metric_i=METRICS[a],metric_j=METRICS[b],applicable_i=rows[a]['applicable'],applicable_j=rows[b]['applicable'])
                pairs.append(item)
        require(len(pairs)==23760,'pair universe mismatch')
        with gzip.open(out/'pairs.jsonl.gz','xb') as f:
            for item in pairs: f.write((json.dumps(item,allow_nan=False,separators=(',',':'))+'\n').encode())
        write_json(out/'summaries.json',summarize(pairs)); audit['pair_count']=len(pairs)
    verify(out); write_json(out/'report.json',audit); return audit


def exit_status(mode,result):
    if mode=='run': return 0 if not result['stop_reasons'] and result['end_drift']=='passed' and result['counts']['matched']==120 and not result['remaining_or_zombie_groups'] else 1
    if mode=='report': return 0 if result['accepted'] else 1
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='mode',required=True)
    q=sub.add_parser('prepare')
    for name in ['root','out','protocol','native-dir','input-dir']: q.add_argument('--'+name,required=True)
    q.add_argument('--command',nargs='+',required=True)
    for name in ['verify','run','report']:
        q=sub.add_parser(name); q.add_argument('--out',required=True)
        if name=='run': q.add_argument('--authorized-single-attempt',action='store_true')
    a=p.parse_args()
    if a.mode=='prepare': result=prepare(a.root,a.out,a.protocol,a.native_dir,a.input_dir,a.command)
    elif a.mode=='verify': result=verify(a.out)
    elif a.mode=='run': result=run(a.out,a.authorized_single_attempt)
    else: result=report(a.out)
    status=exit_status(a.mode,result)
    print(json.dumps({'mode':a.mode,'status':'completed' if status==0 else 'incomplete','accepted':result.get('accepted')},allow_nan=False))
    return status

if __name__=='__main__': raise SystemExit(main())
