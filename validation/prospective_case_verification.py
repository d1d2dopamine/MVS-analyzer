"""Four deterministic engineering calls; no study RNG or study coordinator."""
from pathlib import Path
import argparse, copy, hashlib, json, math, os, shutil, sys
import prospective_cases as cases
import prospective_outcomes as outcomes
import prospective_cost_probe as host

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL='validation/prospective-case-contract-v1.json'
HASHES={'large':'a7e6041a2e9b3afd24fc894ceecbac07baa43ee203e79f90a175f3363c0a75bf','small':'42fff4a06912fa90f2042c6945726d4298b7e61cf1ef9f4c30c5e2723b042c34'}
VOLATILE=['mode','requestSha256','buildTiming','runTiming','legacyTiming','caseWallSeconds','processTotalCpuSeconds','processPeakWorkingSetBytes']
require=host.require
sha=host.digest
canonical=host.canonical
write=host.write_json

def literal_case(size):
    require(size in HASHES,'unknown fixture'); values=[]
    for g in range(2):
        for i in range(16):
            for j in range(40):
                u=(i-7.5)/math.sqrt(21.25);v=(j-19.5)/math.sqrt(133.25);a=1+.02*((i%3)-1)
                value=20+2*g+(1+.5*g)*u+(1+.5*g)*a*v
                if size=='large' or i<8 and j<5: values.append(value)
    result=cases.make_case(values,0 if size=='large' else 10,0,'engineering_literal')
    require(result['ordered_binary64_sha256']==HASHES[size],'literal formula/hash mismatch')
    return result

def provenance(row):
    return {k:row[k] for k in ('identity','adapterSourceSha256','configSha256','adapterScope')}

def verify(out,binding_sha):
    out=Path(out);require(sha(out/'bind.json')==binding_sha,'binding changed');m=host.read_json(out/'bind.json')
    require(m['schema']=='mvs-case-verification-binding/v1' and m['science_execution_authorized'] is False,'binding schema')
    for p,h in m['pins'].items(): require(sha(p)==h,'pinned content changed: '+p)
    require([str(p) for p in host.replay.source_paths(Path(m['root']))]==m['sources'],'source inventory changed')
    require(host.files_in(m['native_dir'])==m['native_files'],'native inventory changed')
    outcomes.validate_provenance(m['provenance'],m['provenance'],Path(m['root']))
    return m

def prepare(root,out,dotnet,dll,prior=None):
    root,out,dll=Path(root).resolve(),Path(out).resolve(),Path(dll).resolve()
    require(not out.exists(),'fresh directory required');require(sys.platform=='linux','Linux-only verification supervisor')
    dotnet=Path(shutil.which(dotnet) or dotnet).resolve();taskset=Path(shutil.which('taskset')).resolve()
    require(dotnet.is_file() and dll.is_file(),'native files missing');cpu=sorted(os.sched_getaffinity(0))[0]
    p=host.read_json(root/PROTOCOL)
    require(p['study_execution_authorized'] is False and p['limits']=={'max_calls':4,'retries':0,'wall_seconds':300,'cleanup_seconds':10,'max_workers':1,'cpu_per_child':1,'sampled_rss_bytes':2147483648,'retained_bytes':20000000},'frozen limits mismatch')
    expected_schedule=[{'fixture':size,'route':route,'cell_template':0 if size=='large' else 10,'native_seed':1540000000 if size=='large' else 1540010000} for size in HASHES for route in ('reference','serialized')]
    require(p['schedule']==expected_schedule and p['scientific_datasets_generated']==0 and p['status']=='frozen_before_calculation','schedule/purpose changed')
    require(p['comparison']['allowed_different_top_level_fields']==VOLATILE and p['comparison']['allowed_different_count_fields']==['fixtureMaterializationCount'],'comparison policy mismatch')
    prior_info=validate_prior(root,prior) if prior is not None else None
    out.mkdir();requests={}
    for size in HASHES:
        path=out/(size+'.json');write(path,literal_case(size));requests[size]=str(path)
    pre=out/'preflight';pre.mkdir();argv=host.native_argv([str(dotnet),str(dll)])
    commands=[[str(taskset),'-c',str(cpu),*argv,'identity']]+[[str(taskset),'-c',str(cpu),*argv,'validate-only',requests[s],sha(requests[s])] for s in HASHES]
    result=host.execute_schedule(pre,commands,[[0],[1],[2]],host.child_environment(str(dotnet)),wall_seconds=30)
    write(pre/'result.json',result);require(not result['stop_reasons'] and all(a['status']=='completed' for a in result['attempts']),'preflight failed')
    rows,_=host.parse_jsonl(pre/'case-00/stdout.jsonl');require(len(rows)==1 and rows[0]['kind']=='identity','identity malformed');identity=provenance(rows[0]);outcomes.validate_provenance(identity,identity,root)
    require(identity['identity']['harnessAssembly']['sha256']==sha(dll),'harness hash mismatch')
    require(identity['identity']['coreAssembly']['sha256']==sha(dll.parent/'MvsAnalyzer.Core.dll'),'Core hash mismatch')
    for i,size in enumerate(HASHES,1):
        rows,_=host.parse_jsonl(pre/f'case-{i:02d}/stdout.jsonl');require(len(rows)==1 and rows[0]['kind']=='case_validated' and rows[0]['computationInvoked'] is False and all(v==0 for v in rows[0]['operationCounts'].values()),'validation computed')
        require(rows[0]['case_id']==literal_case(size)['case_id'] and rows[0]['ordered_binary64_sha256']==HASHES[size] and rows[0]['requestSha256']==sha(requests[size]),'validation identity mismatch')
    if prior_info is not None:
        previous=host.read_json(Path(prior_info['directory'])/'bind.json')
        require(identity==previous['provenance'],'continuation changed native identity')
        require(all(sha(requests[size])==sha(previous['requests'][size]) for size in HASHES),'continuation changed input bytes')
    sources=[str(p) for p in host.replay.source_paths(root)];native=host.files_in(dll.parent)
    runtime=[]
    for folder in ('shared/Microsoft.NETCore.App','host/fxr'):
        runtime+=host.files_in(dotnet.parent/folder/'8.0.31')
    docs=[root/'docs/PROSPECTIVE_CASE_CONTRACT.md',root/PROTOCOL,root/'validation/prospective-ademp-v1.json']
    paths=list(map(Path,sources+native+runtime+host.files_in(pre)+list(requests.values())))+docs+[dotnet,taskset,Path(sys.executable).resolve()]
    if prior_info is not None:
        paths += list(map(Path,host.files_in(prior_info['directory'])))+[root/'validation/prospective-case-continuation-v1.json',root/'docs/ROUND56_TECHNICAL_CONTINUATION.md']
    m={'schema':'mvs-case-verification-binding/v1','root':str(root),'sources':sources,'native_dir':str(dll.parent),'native_files':native,'command':[str(dotnet),str(dll)],'taskset':str(taskset),'cpu':cpu,'requests':requests,'provenance':identity,'pins':host.replay.pin_paths(paths),'science_execution_authorized':False,'continuation':prior_info}
    write(out/'bind.json',m);verify(out,sha(out/'bind.json'));return sha(out/'bind.json')

def validate_call(directory,m,size,reference):
    directory=Path(directory);require((directory/'stderr.log').read_bytes()==b'','unexpected stderr')
    rows,_=host.parse_jsonl(directory/'stdout.jsonl');require(len(rows)>=2 and rows[0].get('kind')=='case_start' and rows[-1].get('kind')=='case_complete','incomplete envelope')
    require(all(r.get('kind') in ('try','cached') for r in rows[1:-1]),'unknown/repeated native event')
    raw=Path(m['requests'][size]).read_bytes();request=cases.loads(raw);end=rows[-1];start=rows[0]
    start_keys={'schema','protocol_id','protocol_sha256','methods','kind','mode','requestSha256','operationCounts','operationCountScope','provenance','case_id','ordered_binary64_sha256','scientificStudyExecuted','processorCount'}
    require(set(start)==start_keys,'start fields changed')
    mode='engineering-reference' if reference else 'run-case';request_sha=None if reference else hashlib.sha256(raw).hexdigest()
    for row in (start,end):
        require(row['mode']==mode and row['requestSha256']==request_sha and row['scientificStudyExecuted'] is False,'transport/engineering identity mismatch')
        require(row['operationCounts']['fixtureMaterializationCount']==int(reference),'fixture work count')
        require(row['provenance']==m['provenance'],'provenance drift')
    require(start['case_id']==request['case_id'] and start['ordered_binary64_sha256']==HASHES[size] and start['processorCount']==1,'start case mismatch')
    normalized=copy.deepcopy(end);normalized['mode']='run-case';normalized['requestSha256']=hashlib.sha256(raw).hexdigest();normalized['operationCounts']['fixtureMaterializationCount']=0
    observations=[r['observation'] for r in rows if r.get('kind')=='cached'];tries=[r for r in rows if r.get('kind')=='try']
    states=outcomes.validate_native_result(normalized,raw,m['provenance'],observations,tries,0,root=Path(m['root']))
    require(end['status']=='paired_methods_returned' and end['payload']['buildError'] is None and end['payload']['varianceError'] is None and end['payload']['legacyError'] is None,'engineering fixture methods failed')
    require(len(observations)==1103,'engineering callback count')
    require(all(states[k]!='unavailable' for k in ('within','between','variance_family','summary_family')),'engineering endpoint unavailable')
    for key in ('buildTiming','runTiming','legacyTiming'): host.round50.timing(end[key])
    for key in ('caseWallSeconds','processTotalCpuSeconds','processPeakWorkingSetBytes'):
        require(type(end[key]) in (int,float) and math.isfinite(end[key]) and end[key]>=0,'invalid resource evidence')
    require(0<end['processPeakWorkingSetBytes']<=2147483648,'native peak exceeds bound')
    return {'end':end,'trace':rows[1:-1],'states':states,'callbacks':len(observations)}

def compare_pair(a,b):
    x,y=copy.deepcopy(a['end']),copy.deepcopy(b['end'])
    for key in VOLATILE: del x[key];del y[key]
    del x['operationCounts']['fixtureMaterializationCount'];del y['operationCounts']['fixtureMaterializationCount']
    require(host.strict_equal(x,y),'full result mismatch');require(host.strict_equal(a['trace'],b['trace']),'ordered trace mismatch')
    return {'matched':True,'callbacks':a['callbacks'],'payload_sha256':hashlib.sha256(canonical(x['payload'])).hexdigest(),'trace_sha256':hashlib.sha256(canonical(a['trace'])).hexdigest()}

def validate_output(path,m,labels):
    path=Path(path);require(path.name=='stdout.jsonl','supervisor callback must supply stdout path')
    directory=path.parent;index=int(directory.name.split('-')[-1])
    value=validate_call(directory,m,*labels[index]);return {'certified':True,'callbacks':value['callbacks']}

def validate_prior(root,prior):
    root,prior=Path(root),Path(prior).resolve();plan=host.read_json(root/'validation/prospective-case-continuation-v1.json')
    for name,key in [('bind.json','original_binding_sha256'),('result.json','original_result_sha256'),('seal.json','original_seal_sha256')]:require(sha(prior/name)==plan[key],'original evidence changed')
    seal=host.read_json(prior/'seal.json')
    for name,h in seal['files'].items():require(sha(prior/name)==h,'original sealed file changed')
    old=host.read_json(prior/'bind.json');result=host.read_json(prior/'result.json')
    require(result['status']=='technical_failure' and result['cleanup_complete'] is True,'original failure state')
    require(len(result['attempts'])==4 and result['attempts'][0]['started'] is True and result['attempts'][0]['returncode']==0 and all(a['started'] is False and a['status']=='not_started' for a in result['attempts'][1:]),'only first slot may have run')
    for path,h in old['pins'].items():
        if sha(path)==h:continue
        relative=str(Path(path).relative_to(Path(old['root'])))
        require(plan['allowed_changed_source_sha256'].get(relative)==h,'unexpected original dependency drift')
    validate_call(prior/'case-00',old,'large',True)
    require(0<result['elapsed_seconds']<300,'original budget invalid')
    return {'directory':str(prior),'original_binding_sha256':plan['original_binding_sha256'],'original_result_sha256':plan['original_result_sha256'],'original_elapsed_seconds':result['elapsed_seconds'],'original_bytes':host.retained_bytes(prior),'retained_slot':0,'new_slots':[1,2,3]}

def run(out,binding_sha,execute=False):
    require(execute is True,'explicit execute required');out=Path(out);m=verify(out,binding_sha);require(not (out/'started.json').exists(),'attempt already exists; no retry')
    previous=m.get('continuation');prior=None
    if previous:
        prior=validate_prior(m['root'],previous['directory']);require(prior==previous,'continuation evidence changed')
    write(out/'started.json',{'binding_sha256':binding_sha,'science_execution_authorized':False});commands=[];labels=[]
    all_labels=[('large',True),('large',False),('small',True),('small',False)]
    labels=all_labels[1:] if prior else all_labels
    for size,reference in labels:
        args=['engineering-reference',size] if reference else ['run-case',m['requests'][size],sha(m['requests'][size])]
        commands.append([m['taskset'],'-c',str(m['cpu']),*host.native_argv(m['command']),*args])
    old_time=prior['original_elapsed_seconds'] if prior else 0;old_bytes=prior['original_bytes'] if prior else 0
    result=host.execute_schedule(out,commands,[[i] for i in range(len(commands))],host.child_environment(m['command'][0]),lambda path:validate_output(path,m,labels),wall_seconds=300-old_time,output_bytes=19_000_000-old_bytes)
    result.update(schema='mvs-case-verification-result/v1',binding_sha256=binding_sha,scientific_datasets_generated=0,science_execution_authorized=False,status='technical_failure',original_status='technical_failure' if prior else None,new_call_count=len(commands),retained_call_count=int(bool(prior)))
    try:
        verify(out,binding_sha);require(not result['stop_reasons'] and result['cleanup_complete'] and all(a['status']=='completed' for a in result['attempts']),'incomplete attempt')
        values=[validate_call(out/f'case-{i:02d}',m,*labels[i]) for i in range(len(labels))]
        if prior:
            old=host.read_json(Path(prior['directory'])/'bind.json');values.insert(0,validate_call(Path(prior['directory'])/'case-00',old,'large',True))
        result['pairs']=[compare_pair(values[0],values[1]),compare_pair(values[2],values[3])]
        require(0<result['peak_aggregate_rss_bytes']<=2147483648 and all(a['rss_samples']>0 for a in result['attempts']),'missing memory evidence')
        result['combined_computation_lifecycle_seconds']=old_time+result['elapsed_seconds']
        require(host.retained_bytes(out)+old_bytes+1048576<=20_000_000,'final retention reserve exhausted');result['status']='supplemental_engineering_parity_verified' if prior else 'engineering_parity_verified'
    except Exception as ex:result['verification_error']=repr(ex)
    write(out/'result.json',result);write(out/'seal.json',{'files':{str(Path(p).relative_to(out)):sha(p) for p in host.files_in(out)}});return result

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','run']);p.add_argument('--root',default=str(ROOT));p.add_argument('--out',required=True);p.add_argument('--dotnet');p.add_argument('--dll');p.add_argument('--binding-sha');p.add_argument('--execute',action='store_true');p.add_argument('--prior');a=p.parse_args()
    if a.action=='prepare':value={'binding_sha256':prepare(a.root,a.out,a.dotnet,a.dll,a.prior)}
    elif a.action=='verify':verify(a.out,a.binding_sha);value={'status':'verified'}
    else:value=run(a.out,a.binding_sha,a.execute)
    print(json.dumps(value,indent=2,allow_nan=False));return 0 if a.action!='run' or value['status'] in ('engineering_parity_verified','supplemental_engineering_parity_verified') else 2
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as ex:print(json.dumps({'status':'technical_failure','error':str(ex),'science_execution_authorized':False}),file=sys.stderr);raise SystemExit(2)
