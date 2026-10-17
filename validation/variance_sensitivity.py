#!/usr/bin/env python3
"""Write-once Round 50 engineering cost probe. No science execution or generation.

prepare pins existing source/build/runtime/protocol without materializing a fixture.
run-cost requires the reviewed binding SHA; it never retries a failed probe.
Native phase clocks are authoritative; host communicate bounds lifecycle wall time.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import subprocess
import struct
import sys
import time
import zipfile

import stability_replay_driver as replay

require = replay.require
digest = replay.digest
read_json = replay.read_json
write_json = replay.write_json
PROTOCOL = 'validation/variance-cost-protocol-v1.json'
PROTOCOL_SHA = 'e0abc7a5849f24cf61ec0fdf634e9bcc79534de2a75abb761dfdd48b8c93e87a'
DOCUMENT = 'docs/ROUND50_VARIANCE_COST_PROTOCOL.md'
DOCUMENT_SHA = '14eb09c29e8179a87f82bf88b49d5bd47f212eb5ecbbef0ea970c99728870aba'
LIMITS = {'wall_seconds':180, 'cleanup_seconds':10, 'cpu_count':1,
          'memory_limit_bytes':None, 'retries':0, 'package_max_bytes':20_000_000}
ENVIRONMENT = {k:'1' for k in ('MVS_DISABLE_BACKUPS','DOTNET_PROCESSOR_COUNT','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}


def files_in(directory):
    return sorted(str(p.resolve()) for p in Path(directory).rglob('*') if p.is_file())


def prepare(root, out, native_dir, runtime_dirs, command, build_evidence):
    root, out, native_dir = (Path(p).resolve() for p in (root,out,native_dir))
    require(not out.exists(), 'fresh output directory required; no overwrite/resume')
    require(sys.platform=='linux' and hasattr(os,'sched_getaffinity'), 'Linux affinity/process groups required')
    require(digest(root/PROTOCOL)==PROTOCOL_SHA, 'cost protocol changed')
    require(digest(root/DOCUMENT)==DOCUMENT_SHA, 'cost protocol document changed')
    require(len(command)==2 and Path(command[1]).suffix=='.dll', 'command must be dotnet and harness DLL')
    executable=shutil.which(command[0]); require(executable is not None, 'dotnet executable unavailable')
    command=[str(Path(executable).resolve()),str(Path(command[1]).resolve())]
    native=files_in(native_dir); require(command[1] in native, 'DLL must be inside native directory')
    runtime_dirs=[str(Path(p).resolve()) for p in runtime_dirs]
    require(runtime_dirs and all(Path(p).is_dir() for p in runtime_dirs), 'runtime directories required')
    runtime=sorted(set(p for directory in runtime_dirs for p in files_in(directory)))
    require(runtime, 'empty runtime provenance')
    sources=list(map(str,replay.source_paths(root)))
    build_evidence=Path(build_evidence).resolve(); evidence=read_json(build_evidence)
    require(isinstance(evidence,dict) and evidence, 'build/restore evidence required')
    paths=sources+native+runtime+[str(root/PROTOCOL),str(root/DOCUMENT),command[0],str(build_evidence)]
    pins=replay.pin_paths(map(Path,paths))
    manifest={'schema':'mvs-variance-cost-binding/v1','root':str(root),'command':command,
              'native_dir':str(native_dir),'native_files':native,'runtime_dirs':runtime_dirs,
              'runtime_files':runtime,'sources':sources,'pins':pins,'limits':LIMITS,
              'environment_overrides':ENVIRONMENT,'build_evidence':str(build_evidence),
              'science_execution_authorized':False}
    out.mkdir(parents=True)
    write_json(out/'bind.json',manifest)
    (out/'bind.sha256').write_text(digest(out/'bind.json')+'\n')
    write_json(out/'build-evidence.json',evidence)
    return manifest


def verify(out, expected_sha=None):
    out=Path(out); actual=digest(out/'bind.json')
    require(actual==(out/'bind.sha256').read_text().strip(), 'binding seal mismatch')
    if expected_sha is not None: require(actual==expected_sha, 'approved binding SHA mismatch')
    m=read_json(out/'bind.json')
    require(m['schema']=='mvs-variance-cost-binding/v1' and m['limits']==LIMITS, 'binding contract altered')
    require(m['environment_overrides']==ENVIRONMENT and m['science_execution_authorized'] is False,'execution scope altered')
    root=Path(m['root'])
    require(m['pins'][str(root/PROTOCOL)]==PROTOCOL_SHA and m['pins'][str(root/DOCUMENT)]==DOCUMENT_SHA,'protocol pins altered')
    require(list(map(str,replay.source_paths(root)))==m['sources'],'source inventory changed')
    require(files_in(m['native_dir'])==m['native_files'],'native inventory changed')
    require(sorted(set(p for d in m['runtime_dirs'] for p in files_in(d)))==m['runtime_files'],'runtime inventory changed')
    for path, expected in m['pins'].items(): require(digest(path)==expected,'pinned content changed: '+path)
    return m


def select_count(run_seconds, legacy_seconds, serialization_seconds, build_seconds,
                 lifecycle_seconds, prelaunch_seconds):
    """Resource-only frozen heuristic. No p, effect, power or rejection arguments."""
    require(len(run_seconds)==len(legacy_seconds)==len(serialization_seconds)==2,'exactly two complete call costs required')
    values=[*run_seconds,*legacy_seconds,*serialization_seconds,build_seconds,lifecycle_seconds,prelaunch_seconds]
    require(all(type(x) in (int,float) and math.isfinite(x) and x>=0 for x in values),'invalid cost timing')
    t=max(sum(row) for row in zip(run_seconds,legacy_seconds,serialization_seconds))
    u=2*(t+build_seconds); require(u>0,'zero work cost')
    p=build_seconds+sum(run_seconds)+sum(legacy_seconds)+sum(serialization_seconds)
    o=max(0,lifecycle_seconds-p); h=8*o+prelaunch_seconds
    raw=math.floor(.65*(900-max(90,h))*8/(6*u)); n=min(32,raw)
    return {'T_seconds':t,'S_seconds':build_seconds,'U_seconds':u,'L_seconds':lifecycle_seconds,
            'P_seconds':p,'O_seconds':o,'H_seconds':h,'n_raw':raw,'n':n if n>=8 else None,
            'budget_eligible':n>=8,'science_execution_authorized':False,
            'interpretation':'resource heuristic, not a timing guarantee or scientific validation'}


def execute(out, command):
    """One owned process; pipe communicate uses blocking selector-based I/O.

    Raw bytes (including incomplete JSON lines) survive timeout. No file-wait
    polling enters lifecycle wall time. RUSAGE_CHILDREN is a host high-water
    cross-check, not independent phase-local RSS.
    """
    out=Path(out); cpu=min(os.sched_getaffinity(0)); env=os.environ.copy();env.update(ENVIRONMENT)
    proc=None; raw_stdout=b''; raw_stderr=b''
    result={'status':'failed','cpu_affinity':[cpu],'limits':LIMITS}
    def affinity(): os.sched_setaffinity(0,{cpu})
    with (out/'stdout.jsonl').open('xb') as stdout, (out/'stderr.log').open('xb') as stderr:
        before=resource.getrusage(resource.RUSAGE_CHILDREN); started=time.monotonic()
        try:
            proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,
                                  cwd=out,env=env,start_new_session=True,preexec_fn=affinity)
            remaining=max(0, LIMITS['wall_seconds']-(time.monotonic()-started))
            raw_stdout,raw_stderr=proc.communicate(timeout=remaining)
            result['status']='completed' if proc.returncode==0 else 'native_failed'
        except subprocess.TimeoutExpired as exc:
            result['status']='timeout';raw_stdout=exc.output or b'';raw_stderr=exc.stderr or b''
            if proc is not None:
                replay.kill_group(proc)
                try: raw_stdout,raw_stderr=proc.communicate(timeout=LIMITS['cleanup_seconds'])
                except subprocess.TimeoutExpired as cleanup:
                    result['cleanup_failed']=True
                    raw_stdout=cleanup.output or raw_stdout;raw_stderr=cleanup.stderr or raw_stderr
        except BaseException as exc:
            result['error']=type(exc).__name__+': '+str(exc)
            if proc is not None:
                replay.kill_group(proc)
                try: raw_stdout,raw_stderr=proc.communicate(timeout=LIMITS['cleanup_seconds'])
                except subprocess.TimeoutExpired as cleanup:
                    result['cleanup_failed']=True
                    raw_stdout=cleanup.output or raw_stdout;raw_stderr=cleanup.stderr or raw_stderr
            if isinstance(exc,(KeyboardInterrupt,SystemExit)): result['status']='interrupted'
        finally:
            result['lifecycle_wall_seconds']=time.monotonic()-started
            result['returncode']=proc.returncode if proc is not None else None
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            result['host_child_cpu_seconds']=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
            result['host_children_peak_rss_bytes']=after.ru_maxrss*1024
            result['host_rss_scope']='RUSAGE_CHILDREN process-lifetime high water; may include earlier children'
            stdout.write(raw_stdout);stderr.write(raw_stderr)
    return result


def seal(out):
    out=Path(out)
    paths=sorted(p for p in out.rglob('*') if p.is_file() and p.name not in ('seal.json','seal.sha256','evidence.zip'))
    write_json(out/'seal.json',{'schema':'mvs-variance-cost-seal/v1','files':{str(p.relative_to(out)):digest(p) for p in paths}})
    (out/'seal.sha256').write_text(digest(out/'seal.json')+'\n')
    with zipfile.ZipFile(out/'evidence.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in paths+[out/'seal.json',out/'seal.sha256']: z.write(p,str(p.relative_to(out)))
    require((out/'evidence.zip').stat().st_size<LIMITS['package_max_bytes'],'evidence package exceeds 20 MB; retained without retry')


def expected_keys():
    keys=['initial-fit']+['interval/'+str(i) for i in range(100)]
    for track in ('within','between'):
        keys += [track+'/null-fit',track+'/observed']
        keys += [track+'/reference/'+str(i) for i in range(199)]
        keys += [track+'/'+branch+'/'+str(i) for i in range(100) for branch in ('null','alternative','grid')]
    return keys


def finite_number(value):
    return type(value) in (int,float) and math.isfinite(value)


def timing(value):
    require(set(value)=={'WallSeconds','CpuSeconds','PeakWorkingSetBytes'},'timing fields changed')
    require(all(finite_number(value[k]) and value[k]>=0 for k in ('WallSeconds','CpuSeconds')),'invalid native timing')
    require(type(value['PeakWorkingSetBytes']) is int and value['PeakWorkingSetBytes']>0,'invalid native RSS')
    return value['WallSeconds']


def parse_jsonl(path):
    # Reuse the strict duplicate-key/nonfinite parser on individual lines without
    # materializing a second output file.
    def pairs(items):
        result={}
        for k,v in items:
            require(k not in result,'duplicate native JSON key'); result[k]=v
        return result
    def bad(value): raise ValueError('nonfinite native JSON: '+value)
    lines=Path(path).read_text().splitlines()
    return [json.loads(line,object_pairs_hook=pairs,parse_constant=bad) for line in lines],lines


def validate_callbacks(cached):
    require([r['Key'] for r in cached]==expected_keys(),'actual callback keys/order incomplete')
    require(all(r['CallbackCount']==1 and r['Returned'] is True and r['Exception'] is None for r in cached),'cache replay or callback failure')
    require(all(r['Finite'] is True for r in cached if r['Converged'] is None),'nonfinite observed/reference/evaluation/grid statistic')
    require(all(r['Converged'] is True and r['Finite'] is True for r in cached if r['Key']=='initial-fit' or r['Key'].endswith('/null-fit')),'initial/null fit invalid')


def validate_identity(start, manifest):
    identity=start['identity']
    require(start['protocolId']=='round50-variance-cost-v1' and start['protocolSha256']==PROTOCOL_SHA,'native protocol mismatch')
    require(start['processorCount']==1,'native CPU cap mismatch')
    require(identity['experimental'] is True and len(identity['sourceSha256'])==14,'native identity incomplete')
    for rel, sha in identity['sourceSha256'].items():
        require(manifest['pins'][str(Path(manifest['root'])/rel)]==sha,'embedded source identity mismatch: '+rel)
    for assembly in ('harnessAssembly','coreAssembly'):
        item=identity[assembly]
        require(manifest['pins'][str(Path(manifest['native_dir'])/item['fileName'])]==item['sha256'],'native assembly identity mismatch')
    require(identity['runtime']['coreLibrarySha256'] in [manifest['pins'][p] for p in manifest['runtime_files'] if Path(p).name=='System.Private.CoreLib.dll'],'runtime identity mismatch')


def validate_native(out, manifest):
    rows,lines=parse_jsonl(Path(out)/'stdout.jsonl')
    require(rows and rows[0]['kind']=='start' and rows[-1]['kind']=='complete','incomplete native stream')
    validate_identity(rows[0],manifest)
    fixtures=[r for r in rows if r['kind']=='fixture'];require(len(fixtures)==1,'fixture event count')
    fixture=fixtures[0]
    require((fixture['rawRows'],fixture['retainedRows'],fixture['entities'],fixture['GroupCounts'])==(1280,1280,32,[16,16]),'fixture dimensions changed')
    require(len(fixture['observations'])==1280,'fixture observations missing')
    fixture_line=lines[rows.index(fixture)]
    encoded=fixture_line.split('"observations":',1)[1].rsplit(',"rawRows":',1)[0]
    require(hashlib.sha256(encoded.encode()).hexdigest()==fixture['dataSha256'],'fixture data SHA mismatch')
    for pos,row in enumerate(fixture['observations']):
        g=pos//640;i=(pos%640)//40;j=pos%40
        require((row['group'],row['entity'],row['sequence'])==(f'G{g}',f'E{i:02d}',j),'fixture ordering changed')
        value=row['value']; expected=20+2*g+(1+.5*g)*((i-7.5)/math.sqrt(21.25))+(1+.5*g)*(1+.02*((i%3)-1))*((j-19.5)/math.sqrt(133.25))
        require(value['classification']=='finite' and struct.pack('>d',value['value']).hex()==value['bits'],'invalid fixture binary64 encoding')
        require(struct.pack('>d',expected).hex()==value['bits'],'literal fixture changed')
    build=timing(fixture['buildTiming']);runs=[];legacy=[];serialization=[]
    require(all(r['kind'] in {'start','fixture','try','cached','variance_returned','completeness','call_complete','complete'} for r in rows),'unknown native event')
    require([r['call'] for r in rows if r['kind']=='call_complete']==[1,2],'native call order changed')
    require(all(r.get('call') in (1,2) for r in rows if r['kind'] in ('try','cached','variance_returned','completeness','call_complete')),'unexpected extra call')
    for call in (1,2):
        events=[r for r in rows if r.get('call')==call]
        cached=[r['observation'] for r in events if r['kind']=='cached']
        validate_callbacks(cached)
        require(all(r['hit'] is False for r in events if r['kind']=='try'),'restored computation forbidden')
        complete=[r for r in events if r['kind']=='completeness'];finished=[r for r in events if r['kind']=='call_complete'];returned=[r for r in events if r['kind']=='variance_returned']
        require(len(complete)==len(finished)==len(returned)==1,'call completion missing/duplicate')
        summary=complete[0]['summary']
        for key in ('certified','exactKeys','allCallbacksExecutedOnce','initialConvergedFinite','nullFitsConvergedFinite','allObservedReferenceEvaluationGridStatisticsFinite','normalOwnershipNoRestore','reportCountsComplete'):
            require(summary[key] is True,'native completeness failed: '+key)
        require(summary['actualCachedRequests']==summary['expectedCachedRequests']==1103 and summary['missingKeys']==[],'callback count mismatch')
        tracks=returned[0]['report']['tracks'];require(len(tracks)==2,'track count')
        for tr in tracks:
            require((tr['referenceReplications'],tr['referenceFailures'],tr['evaluationReplications'],tr['nullFailures'],tr['alternativeFailures'])==(199,0,100,0,0),'report counts incomplete')
        item=finished[0];require(item['runTiming']==returned[0]['runTiming'],'duplicated Run timing mismatch')
        require(item['payload']['dataSha256']==fixture['dataSha256'],'call data hash mismatch')
        family=item['payload']['legacy']
        require(family['familySize']==12 and len(family['metrics'])==12,'legacy family incomplete')
        require([metric['index'] for metric in family['metrics']]==list(range(12)),'legacy registry order incomplete')
        for metric in family['metrics']:
            require(metric['applicable'] is True,'legacy fixture metric unavailable')
            require(metric['firstCount']==metric['secondCount']==16,'legacy entity counts incomplete')
            groups=metric['groupAvailability']
            require(len(groups)==2 and {g['Group'] for g in groups}=={'G0','G1'},'legacy availability groups')
            require(all(g['RetainedEntities']==g['UsableEntities']==16 and g['ExcludedEntities']==0 for g in groups),'legacy availability incomplete')
        runs.append(timing(item['runTiming']));legacy.append(timing(item['legacyTiming']));serialization.append(timing(item['serializationTiming']))
    end=rows[-1]
    require(end['runCallCount']==end['legacyCallCount']==2 and end['status']=='engineering_cost_only','native total call mismatch')
    require(all(finite_number(end[k]) and end[k]>=0 for k in ('nativeTotalWallSeconds','processTotalCpuSeconds','processPeakWorkingSetBytes')),'invalid process totals')
    return {'certified':True,'run_seconds':runs,'legacy_seconds':legacy,'serialization_seconds':serialization,
            'build_seconds':build,'data_sha256':fixture['dataSha256'],'native_totals':end,
            'fit_entries_per_call_source_upper_bound':2103,'optimizer_invocations_per_call_source_upper_bound':4206,
            'counts_are_profiled':False}


def run_cost(out, approved_sha):
    out=Path(out).resolve(); setup=time.monotonic();m=verify(out,approved_sha)
    require(not (out/'started.json').exists(),'probe already attempted; retries/resume forbidden')
    require(not any((out/p).exists() for p in ('stdout.jsonl','stderr.log','result.json','seal.json','evidence.zip')),'output already contains probe evidence')
    command=m['command']+['cost',str(Path(m['root'])/PROTOCOL),PROTOCOL_SHA]
    write_json(out/'started.json',{'approved_binding_sha256':approved_sha,'command':command,'science_execution_authorized':False})
    prelaunch=time.monotonic()-setup
    result=execute(out,command); result['prelaunch_setup_seconds']=prelaunch
    try:
        verify(out,approved_sha)
        if result['status']=='completed':
            cost=validate_native(out,m);result['native_cost']=cost
            result['count_selection']=select_count(cost['run_seconds'],cost['legacy_seconds'],cost['serialization_seconds'],cost['build_seconds'],result['lifecycle_wall_seconds'],prelaunch)
            result['status']='cost_certified'
    except Exception as exc:
        result['status']='cost_unrepresentative';result['validation_error']=str(exc)
    result['science_execution_authorized']=False
    write_json(out/'result.json',result);seal(out)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--root',required=True);p.add_argument('--out',required=True)
    p.add_argument('--native-dir',required=True);p.add_argument('--runtime-dir',action='append',required=True)
    p.add_argument('--build-evidence',required=True);p.add_argument('--command',nargs=2,required=True)
    p=sub.add_parser('verify');p.add_argument('--out',required=True)
    p=sub.add_parser('run-cost');p.add_argument('--out',required=True);p.add_argument('--approved-binding-sha256',required=True)
    args=parser.parse_args(argv)
    if args.action=='prepare': result=prepare(args.root,args.out,args.native_dir,args.runtime_dir,args.command,args.build_evidence)
    elif args.action=='verify': result=verify(args.out)
    else: result=run_cost(args.out,args.approved_binding_sha256)
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0 if args.action!='run-cost' or result['status']=='cost_certified' else 2




# Science execution exists only in the separately frozen science source copy.
SCIENCE_PROTOCOL = 'validation/variance-sensitivity-protocol-v1.json'
SCIENCE_SHA = 'eccb4e6a817483a61efcaefdfbde211b284a417074d4d305a0c3b4d462d6eb75'
SCIENCE_DOCUMENT = 'docs/ROUND50_VARIANCE_COMPARISON_PROTOCOL.md'
SCIENCE_DOCUMENT_SHA = 'ae296f941a8d024083a76e2b5fea454af332e1f8a77dfe0497c0b11f62849946'
SCIENCE_LIMITS = {'wall_seconds':900,'worker_processes':8,'worker_threads':1,
                  'cleanup_seconds':30,'package_max_bytes':200_000_000,'memory_limit_bytes':None,'retries':0}
STATES = ('reject','nonreject','unavailable')
LEGACY_KEYS = 'median standard_deviation coefficient_of_variation mad iqr normalized_mad normalized_iqr mean rms range geometric_mean trimmed_mean_20'.split()
EVIDENCE_ACCOUNTING = {'threshold':'uncompressed logical evidence: existing metadata, raw streams, inputs, and reserved result/summary bytes',
                      'transport':'ZIP excluded from logical duplicate accounting; separately bounded at200000000 compressed bytes',
                      'tail':'stop starting new cases at threshold; retain in-flight tail without deletion and report overshoot',
                      'summary_reserve_bytes':1_000_000}



def science_protocol(root):
    root=Path(root)
    require(digest(root/SCIENCE_PROTOCOL)==SCIENCE_SHA,'frozen science protocol SHA changed')
    require(digest(root/SCIENCE_DOCUMENT)==SCIENCE_DOCUMENT_SHA,'frozen science document SHA changed')
    plan=read_json(root/SCIENCE_PROTOCOL)
    require(plan['status']=='frozen' and plan['schema']=='mvs-round50-science-protocol/v1','unfrozen science protocol')
    tasks=plan['tasks'];require(len(tasks)==192,'science task count')
    for i,t in enumerate(tasks):
        c=i%6;r=i//6
        require((t['task_index'],t['condition_index'],t['replicate'],t['variance_seed'],t['legacy_seed'])==(i,c,r,50000000+1000*c+r,51000000+1000*c+r),'science task order/seed drift')
        require(t['outer_seed_sequence']==[20261017,50,50001,c,r],'outer seed drift')
    for key,value in SCIENCE_LIMITS.items():require(plan['limits'][key]==value,'science limit drift: '+key)
    return plan


def science_prepare(root,out,native_dir,runtime_dirs,command,build_evidence):
    import numpy as np
    import scipy
    root,out,native_dir=(Path(p).resolve() for p in (root,out,native_dir))
    require(not out.exists(),'fresh science output directory required')
    plan=science_protocol(root)
    require(len(os.sched_getaffinity(0))>=8,'eight distinct available cores required')
    require(len(command)==2 and Path(command[1]).suffix=='.dll','dotnet and harness DLL required')
    executable=shutil.which(command[0]);taskset=shutil.which('taskset')
    require(executable is not None and taskset is not None,'dotnet/taskset unavailable')
    command=[str(Path(executable).resolve()),str(Path(command[1]).resolve())]
    native=files_in(native_dir);require(command[1] in native,'native DLL not in build inventory')
    runtime_dirs=[str(Path(p).resolve()) for p in runtime_dirs]
    require(runtime_dirs and all(Path(p).is_dir() for p in runtime_dirs),'runtime directories missing')
    runtime=sorted(set(p for directory in runtime_dirs for p in files_in(directory)))
    require(runtime,'runtime inventory empty')
    sources=list(map(str,replay.source_paths(root)))
    packages={'numpy':np.__version__,'scipy':scipy.__version__,'python':sys.version}
    python_dirs=[str(Path(np.__file__).parent),str(Path(scipy.__file__).parent)]
    # Include bundled BLAS/LAPACK shared-library directories alongside packages.
    python_dirs += [str(p) for package in python_dirs[:] for p in Path(package).parent.glob(Path(package).name+'.libs') if p.is_dir()]
    python_files=sorted(set(p for directory in python_dirs for p in files_in(directory) if '__pycache__' not in Path(p).parts and not p.endswith('.pyc')))
    build_evidence=Path(build_evidence).resolve();build=read_json(build_evidence)
    require(type(build) is dict and build,'build evidence missing')
    paths=sources+native+runtime+python_files+[str(root/SCIENCE_PROTOCOL),str(root/SCIENCE_DOCUMENT),command[0],str(Path(sys.executable).resolve()),taskset,str(build_evidence)]
    manifest={'schema':'mvs-variance-science-binding/v1','root':str(root),'native_dir':str(native_dir),
              'command':command,'taskset':taskset,'runtime_dirs':runtime_dirs,'runtime_files':runtime,
              'native_files':native,'sources':sources,'python_dirs':python_dirs,'python_files':python_files,
              'packages':packages,'pins':replay.pin_paths(map(Path,paths)), 'limits':SCIENCE_LIMITS,
              'protocol_sha256':SCIENCE_SHA,'environment_overrides':ENVIRONMENT,'build_evidence':str(build_evidence),'evidence_accounting':EVIDENCE_ACCOUNTING}
    out.mkdir(parents=True);write_json(out/'bind.json',manifest)
    (out/'bind.sha256').write_text(digest(out/'bind.json')+'\n')
    write_json(out/'build-evidence.json',build)
    write_json(out/'protocol.json',plan)
    return manifest


def science_verify(out,approved_sha=None):
    import numpy as np
    import scipy
    out=Path(out);sha=digest(out/'bind.json')
    require(sha==(out/'bind.sha256').read_text().strip(),'science binding seal mismatch')
    if approved_sha is not None:require(sha==approved_sha,'approved science binding mismatch')
    m=read_json(out/'bind.json');require(m['schema']=='mvs-variance-science-binding/v1','binding mode mismatch')
    require(m['limits']==SCIENCE_LIMITS and m['protocol_sha256']==SCIENCE_SHA and m['environment_overrides']==ENVIRONMENT,'science settings changed')
    require(m['packages']=={'numpy':np.__version__,'scipy':scipy.__version__,'python':sys.version},'Python package versions changed')
    require(m['evidence_accounting']==EVIDENCE_ACCOUNTING,'evidence accounting changed')
    science_protocol(m['root'])
    require(list(map(str,replay.source_paths(Path(m['root']))))==m['sources'],'science source inventory changed')
    require(files_in(m['native_dir'])==m['native_files'],'science native inventory changed')
    require(sorted(set(p for directory in m['runtime_dirs'] for p in files_in(directory)))==m['runtime_files'],'science runtime inventory changed')
    require(sorted(set(p for directory in m['python_dirs'] for p in files_in(directory) if '__pycache__' not in Path(p).parts and not p.endswith('.pyc')))==m['python_files'],'Python package inventory changed')
    for path,expected in m['pins'].items():require(digest(path)==expected,'science pinned content changed: '+path)
    require(read_json(out/'protocol.json')==read_json(Path(m['root'])/SCIENCE_PROTOCOL),'retained protocol changed')
    return m


def generate_case(plan,task,rng_factory=None):
    """One independent NumPy stream; intercept draws precede residual draws."""
    import numpy as np
    rng=(np.random.Generator(np.random.PCG64(np.random.SeedSequence(task['outer_seed_sequence'])))
         if rng_factory is None else rng_factory(task['outer_seed_sequence']))
    condition=plan['conditions'][task['condition_index']]
    if condition['latent_distribution']=='gaussian':
        intercept=rng.standard_normal(32).reshape(2,16)
        residual=rng.standard_normal(1280).reshape(2,16,40)
    else:
        require(condition['latent_distribution']=='standardized_t5','unplanned latent distribution')
        intercept=(rng.standard_t(5,32)*math.sqrt(3/5)).reshape(2,16)
        residual=(rng.standard_t(5,1280)*math.sqrt(3/5)).reshape(2,16,40)
    values=np.empty((2,16,40),dtype=np.float64)
    for g in (0,1):
        spec=condition['group'+str(g)]
        values[g]=spec['mean']+spec['between_sd']*intercept[g,:,None]+spec['within_sd']*residual[g]
    raw=np.asarray(values,dtype='<f8').tobytes(order='C'); data_sha=hashlib.sha256(raw).hexdigest()
    encoded=[float(x) if math.isfinite(float(x)) else {'bits':struct.pack('>d',float(x)).hex()} for x in values.flat]
    request={'condition':task['condition_index'],'replicate':task['replicate'],'seed':task['variance_seed'],'dataSha256':data_sha,'values':encoded}
    return request,raw,analytic_references(values,condition)


def analytic_references(values,condition):
    import numpy as np
    from scipy.stats import f
    values=np.asarray(values,dtype=np.float64);require(values.shape==(2,16,40),'reference dimensions')
    if not np.isfinite(values).all() or np.any(np.abs(values)>1_000_000):
        return {'within':{'state':'unavailable','reason':'input_retention_mismatch'},'between':{'state':'unavailable','reason':'input_retention_mismatch'}}
    means=values.mean(axis=2);q=((values-means[:,:,None])**2).sum(axis=(1,2));v=means.var(axis=1,ddof=1)
    result={'moments':{'group_means':values.mean(axis=(1,2)).tolist(),'within_ss':q.tolist(),'entity_mean_variances':v.tolist()}}
    for track,stat,df in [('within',q,624),('between',v,15)]:
        if not condition['gaussian_'+track+'_reference_applicable']:
            result[track]={'state':'unavailable','reason':'reference_not_applicable'};continue
        if stat[0]<=0 or not np.isfinite(stat).all():
            result[track]={'state':'unavailable','reason':'degenerate_reference_statistic'};continue
        ratio=float(stat[1]/stat[0]);p=min(1.,2*min(float(f.cdf(ratio,df,df)),float(f.sf(ratio,df,df))))
        adjusted=min(1.,2*p)
        result[track]={'state':'reject' if adjusted<.05 else 'nonreject','statistic':ratio,'df1':df,'df0':df,'p':p,'adjusted_p':adjusted,
                       'interpretation':'Gaussian model reference; C3 between is an alternative diagnostic' if track=='between' else 'Gaussian within-residual reference'}
    return result


def wilson(k,n=32):
    require(type(k) is int and type(n) is int and n>0 and 0<=k<=n,'Wilson counts')
    z=1.959963984540054;p=k/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,center-half),min(1,center+half)]


def clopper_pearson(k,n,alpha=.025):
    from scipy.stats import beta
    require(type(k) is int and type(n) is int and n>0 and 0<=k<=n,'CP counts')
    return [0. if k==0 else float(beta.ppf(alpha/2,k,n-k+1)),1. if k==n else float(beta.ppf(1-alpha/2,k+1,n-k))]


def marginal(states):
    require(len(states)==32 and all(s in STATES for s in states),'fixed marginal denominator/states')
    counts={s:states.count(s) for s in STATES};k=counts['reject'];u=counts['unavailable']
    return {'requested':32,**counts,'operational_rate':k/32,'pointwise_wilson_95':wilson(k),
            'failure_bounds':[k/32,(k+u)/32],'unavailable_counted_nonreject_for_operational_rate':True}


def paired_summary(left,right):
    require(len(left)==len(right)==32,'paired requested denominator')
    require(all(s in STATES for s in left+right),'invalid paired state')
    table=[[sum(a==s and b==t for a,b in zip(left,right)) for t in STATES] for s in STATES]
    cells=[[sum((a=='reject')==bool(i) and (b=='reject')==bool(j) for a,b in zip(left,right)) for j in range(2)] for i in range(2)]
    n10=cells[1][0];n01=cells[0][1];lo10,hi10=clopper_pearson(n10,32);lo01,hi01=clopper_pearson(n01,32)
    return {'requested':32,'state_order':list(STATES),'paired_3x3':table,
            'operational_2x2':cells,'operational_order':['not_reject_including_unavailable','reject'],
            'difference_left_minus_right':(n10-n01)/32,
            'pointwise_conservative_95_difference_interval':[max(-1,lo10-hi01),min(1,hi10-lo01)],
            'discordance_97_5_cp':{'left_only':[lo10,hi10],'right_only':[lo01,hi01]},
            'left':marginal(left),'right':marginal(right),'simultaneous_coverage_claim':False}


def decode_fp(item):
    require(type(item) is dict and set(item)=={'classification','value','bits'},'invalid native floating encoding')
    bits=item['bits'];require(type(bits) is str and len(bits)==16 and all(c in '0123456789abcdef' for c in bits),'invalid native bits')
    value=struct.unpack('>d',bytes.fromhex(bits))[0]
    classification='finite' if math.isfinite(value) else 'nan' if math.isnan(value) else 'positive_infinity' if value>0 else 'negative_infinity'
    require(item['classification']==classification,'native floating classification mismatch')
    if math.isfinite(value):require(finite_number(item['value']) and struct.pack('>d',item['value']).hex()==bits,'native floating value/bit mismatch')
    else:require(item['value'] is None,'nonfinite native value must be null')
    return value


def member_state(p):
    return 'unavailable' if not math.isfinite(p) else 'reject' if p<.05 else 'nonreject'


def family_state(states):
    require(states and all(s in STATES for s in states),'invalid family members')
    return 'reject' if 'reject' in states else 'nonreject' if all(s=='nonreject' for s in states) else 'unavailable'


def validate_science_identity(row,m):
    require(row['kind']=='worker_ready' and row['protocolSha256']==SCIENCE_SHA,'worker protocol identity mismatch')
    # Reuse embedded/native/runtime identity validation independently of cost mode.
    validate_identity({'identity':row['identity'],'processorCount':row['processorCount'],
                       'protocolId':'round50-variance-cost-v1','protocolSha256':PROTOCOL_SHA},m)


def validate_trace(trace,observations):
    def branch(prefix):
        rows=[r for r in observations if r['Key'].startswith(prefix)]
        return {'attempted':len(rows),'callbacks':sum(r['CallbackCount'] for r in rows),
                'returned':sum(r['Returned'] is True for r in rows),'finite':sum(r['Finite'] is True for r in rows),
                'nonfinite':sum(r['Returned'] is True and r['Finite'] is False for r in rows),
                'converged':sum(r['Converged'] is True for r in rows),'exceptions':sum(r['Returned'] is False for r in rows)}
    require(trace['initial']==branch('initial-fit') and trace['interval']==branch('interval/'),'initial/interval trace mismatch')
    require([t['track'] for t in trace['tracks']]==['within','between'],'trace track order')
    for row in trace['tracks']:
        for name,suffix in [('nullFit','null-fit'),('observed','observed'),('reference','reference/'),('nullEvaluation','null/'),('alternative','alternative/'),('grid','grid/')]:
            require(row[name]==branch(row['track']+'/'+suffix),'trace branch mismatch')
    require(trace['sourceDerivedFitEntryUpperLimit']==2103 and trace['sourceDerivedOptimizerInvocationUpperLimit']==4206,'trace source upper bounds')
    for row in observations:
        require(type(row['Returned']) is bool and (row['Exception'] is None)==row['Returned'],'callback return/exception contradiction')
        if row['Returned'] and row['Converged'] is None:
            require(row['Finite']==math.isfinite(decode_fp(row['Value'])),'scalar trace finite flag mismatch')


def validate_science_case(row,request,observations,tries):
    require(row['kind']=='case_complete','expected completed case')
    for key in ('condition','replicate','seed','dataSha256'):require(row[key]==request[key],'native case identity mismatch: '+key)
    payload=row['payload']
    for key in ('condition','replicate','seed','dataSha256'):require(payload[key]==request[key],'native payload identity mismatch')
    require(payload['rawRows']==1280,'native raw row count')
    require(all(t['hit'] is False for t in tries),'native restored state forbidden')
    keys=[o['Key'] for o in observations];expected=expected_keys()
    require(len(keys)==len(set(keys)) and all(k in expected for k in keys),'unexpected/duplicate native callback key')
    require([expected.index(k) for k in keys]==sorted(expected.index(k) for k in keys),'callback order changed')
    require(all(o['CallbackCount']==1 for o in observations),'native cache replay/callback duplication')
    trace=payload['trace'];require(trace['RestoreHits']==0 and trace['cachedRequests']==len(observations) and trace['callbackCount']==len(observations),'trace actual counts mismatch')
    validate_trace(trace,observations)
    for key in ('buildTiming','runTiming','legacyTiming','serializationTiming'):
        if row[key] is not None:timing(row[key])
    states={'within':'unavailable','between':'unavailable','variance_family':'unavailable','legacy_family':'unavailable','legacy_metrics':['unavailable']*12}
    if payload['inputStatus']=='retained_exactly':
        require(payload['buildError'] is None and (payload['retainedRows'],payload['entities'],payload['groupCounts'])==(1280,32,[16,16]),'native retention contradiction')
    else:
        require(payload['inputStatus']=='input_retention_mismatch' and payload['buildError'] is not None and payload['report'] is None and payload['legacy'] is None and not observations,'invalid failed-input evidence')
        return states
    require(trace['Begins']==trace['Disposals']==1 and len(tries)==1 and tries[0]['key']=='result','science recording ownership')
    report=payload['report']
    require((report is None)==(payload['varianceError'] is not None),'variance report/error mismatch')
    require(trace['Finishes']==int(report is not None),'recording finish count')
    if report is not None:
        require(payload['varianceError'] is None,'report and error contradiction')
        require(report['seed']==request['seed'] and decode_fp(report['alpha'])==.05,'report settings mismatch')
        bykey={o['Key']:o for o in observations}
        require('initial-fit' in bykey and all(o['Returned'] for o in observations),'incomplete returned report trace')
        required=['initial-fit']+(['interval/'+str(i) for i in range(100)] if bykey['initial-fit']['Converged'] else [])
        tracks=report['tracks'];require(len(tracks)==2 and [t['track'] for t in tracks]==['within','between'],'variance track ordering mismatch')
        for tr in tracks:
            track=tr['track'];raw=decode_fp(tr['pValue']);adj=decode_fp(tr['adjustedP'])
            require((math.isnan(raw) and math.isnan(adj)) or (math.isfinite(raw) and 0<=raw<=1 and adj==min(1,2*raw)),'variance fixed-family adjustment mismatch')
            states[track]=member_state(adj)
            nullfit=bykey[track+'/null-fit'];observed=decode_fp(bykey[track+'/observed']['Value'])
            reference=[decode_fp(o['Value']) for o in observations if o['Key'].startswith(track+'/reference/')]
            finite_reference=[v for v in reference if math.isfinite(v)]
            usable=nullfit['Converged'] and math.isfinite(observed) and len(finite_reference)>=.9*199
            expected_p=(1+sum(v>=observed for v in finite_reference))/(len(finite_reference)+1) if usable else math.nan
            require((math.isnan(raw) and math.isnan(expected_p)) or raw==expected_p,'bootstrap plus-one/reference-tail mismatch')
            require(tr['referenceReplications']==len(finite_reference) and tr['referenceFailures']==199-len(finite_reference),'actual finite reference count mismatch')
            for branch,field in [('null','nullFailures'),('alternative','alternativeFailures')]:
                failures=sum(not math.isfinite(decode_fp(o['Value'])) for o in observations if o['Key'].startswith(track+'/'+branch+'/')) if usable else 100
                require(tr[field]==failures,'actual evaluation failure count mismatch: '+field)
            required += [track+'/null-fit',track+'/observed']
            if nullfit['Converged']:required += [track+'/reference/'+str(i) for i in range(199)]
            if usable:required += [track+'/'+branch+'/'+str(i) for i in range(100) for branch in ('null','alternative','grid')]
            for key,maximum in [('referenceReplications',199),('referenceFailures',199),('evaluationReplications',100),('nullFailures',100),('alternativeFailures',100)]:
                require(type(tr[key]) is int and 0<=tr[key]<=maximum,'invalid variance diagnostic counts')
        require(keys==required,'conditional computation path incomplete')
        require(all(tr['evaluationReplications']==100 and tr['referenceReplications']+tr['referenceFailures']==199 for tr in tracks),'fixed evaluation/reference denominator mismatch')
        states['variance_family']=family_state([states['within'],states['between']])
    legacy=payload['legacy']
    require((legacy is None)==(payload['legacyError'] is not None),'legacy output/error mismatch')
    if legacy is not None:
        require(payload['legacyError'] is None and legacy['familySize']==12 and len(legacy['metrics'])==12,'legacy output contradiction')
        metric_states=[]
        for index,metric in enumerate(legacy['metrics']):
            require(metric['index']==index and metric['key']==LEGACY_KEYS[index] and type(metric['applicable']) is bool,'legacy fixed slot mismatch')
            raw=decode_fp(metric['p']);adj=decode_fp(metric['adjustedP'])
            require((math.isnan(raw) and math.isnan(adj)) or (math.isfinite(raw) and 0<=raw<=1 and adj==min(1,12*raw)),'legacy fixed12 adjustment mismatch')
            state=member_state(adj);require(metric['reject']==(state=='reject'),'legacy rejection mismatch')
            require(metric['applicable'] or state=='unavailable','unavailable metric has decision')
            groups=metric['groupAvailability']
            require(len(groups)==2 and [g['Group'] for g in groups]==['G0','G1'],'legacy availability group order')
            require(all(g['RetainedEntities']==16 and 0<=g['UsableEntities']<=16 and g['ExcludedEntities']==16-g['UsableEntities'] for g in groups),'legacy entity availability counts')
            require([g['UsableEntities'] for g in groups]==[metric['firstCount'],metric['secondCount']],'legacy observed usable counts')
            expected_status='available' if metric['applicable'] else 'insufficient_usable_entities' if any(g['UsableEntities']<4 for g in groups) else 'rank_test_unavailable'
            require(metric['observedStatus']==expected_status and metric['applicable']==math.isfinite(raw),'legacy applicability/status mismatch')
            metric_states.append(state)
        states['legacy_metrics']=metric_states;states['legacy_family']=family_state(metric_states)
        require(legacy['anyReject']==(states['legacy_family']=='reject'),'legacy family rejection mismatch')
    return states


def science_summaries(records,plan):
    result=[]
    for c in range(6):
        rows=[r for r in records if r['condition_index']==c]
        require(len(rows)==32,'summary cannot drop requested tasks')
        def states(key):return [r['states'][key] for r in rows]
        item={'condition_index':c,'condition':plan['conditions'][c],
              'global_variance_minus_legacy':paired_summary(states('variance_family'),states('legacy_family')),
              'components':{track:marginal(states(track)) for track in ('within','between')},
              'legacy_metrics':[marginal([r['states']['legacy_metrics'][i] for r in rows]) for i in range(12)],
              'analytic_references':{},'completed_native_cases':sum(r['status']=='completed' for r in rows),
              'status_counts':{s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})}}
        for track in ('within','between'):
            ref=[r.get('analytic_references',{}).get(track,{}).get('state','unavailable') for r in rows]
            item['analytic_references'][track]={'marginal':marginal(ref),'variance_minus_reference':paired_summary(states(track),ref)}
        both=['reject' if r['states']['within']==r['states']['between']=='reject' else 'nonreject' if 'nonreject' in (r['states']['within'],r['states']['between']) else 'unavailable' for r in rows]
        item['both_components_reject']=marginal(both)
        result.append(item)
    return {'conditions':result,'requested':192,'interpretation':plan['interpretation'],
            'intervals':'Pointwise descriptive intervals; no simultaneous coverage or inferential winner claim.',
            'unavailable_policy':'All32 requested datasets remain in each condition denominator.'}


def empty_science_record(task):
    return {**task,'status':'not_started','states':{'within':'unavailable','between':'unavailable','variance_family':'unavailable',
                                                'legacy_family':'unavailable','legacy_metrics':['unavailable']*12}}


def science_execute(out,m,plan):
    """Eight persistent workers, blocking pipes, one global generation-to-exit cap.

    A deadline thread waits on an Event rather than timed process polling. Worker
    threads drain stdout by blocking readline and stderr concurrently. A shared
    FIFO provides each frozen case at most once; no recovery/replacement worker.
    """
    import threading
    from collections import deque
    out=Path(out); started=time.monotonic();deadline=started+SCIENCE_LIMITS['wall_seconds']
    lock=threading.RLock();stop=threading.Event();finished=threading.Event();all_done=threading.Event()
    processes=[];threads=[];stop_reason=[];worker_results=[];done_count=0;byte_count=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())+EVIDENCE_ACCOUNTING['summary_reserve_bytes'];peak_rss=0
    records=[empty_science_record(t) for t in plan['tasks']];requests={};queue=deque()
    cpus=sorted(os.sched_getaffinity(0))[:8];require(len(cpus)==8,'eight distinct CPU affinity slots unavailable')
    env=os.environ.copy();env.update(ENVIRONMENT)
    def halt(reason,kill=False):
        with lock:
            if not stop_reason:stop_reason.append(reason)
            stop.set()
            if kill:
                for proc in processes:replay.kill_group(proc)
    def retained(data,stream):
        nonlocal byte_count
        stream.write(data);stream.flush()
        with lock:
            byte_count+=len(data)
            if byte_count>=SCIENCE_LIMITS['package_max_bytes']:halt('evidence_cap')
    def watchdog():
        if not finished.wait(max(0,deadline-time.monotonic())):halt('wall_timeout',True)
    watcher=threading.Thread(target=watchdog,daemon=True);watcher.start()
    def rss_watch():
        nonlocal peak_rss
        while not finished.wait(.1):
            with lock:pids=[p.pid for p in processes]
            try:peak_rss=max(peak_rss,replay.group_rss(pids))
            except OSError:pass
    rss_thread=threading.Thread(target=rss_watch,daemon=True);rss_thread.start()
    try:
        (out/'inputs').mkdir()
        with (out/'requests.jsonl').open('xb') as input_log:
            for task in plan['tasks']:
                if stop.is_set() or time.monotonic()>=deadline:break
                request,raw,refs=generate_case(plan,task)
                index=task['task_index'];path=out/'inputs'/f'{index:03d}.f64le'
                with path.open('xb') as stream:retained(raw,stream)
                encoded=json.dumps(request,separators=(',',':'),allow_nan=False).encode()+b'\n'
                retained(encoded,input_log)
                records[index].update(data_sha256=request['dataSha256'],raw_input_file=str(path.relative_to(out)),analytic_references=refs)
                requests[index]=(request,encoded);queue.append(index)
        def worker(worker_index):
            nonlocal done_count,byte_count
            proc=None;active=None;stderr_thread=None;stdout=None;stderr=None;seen=[];native_calls=0
            info={'worker':worker_index,'cpu_affinity':[cpus[worker_index]],'status':'failed'}
            stdout_path=out/f'worker-{worker_index}.stdout.jsonl';stderr_path=out/f'worker-{worker_index}.stderr.log'
            try:
                if stop.is_set():info['status']='not_started';return
                command=[m['taskset'],'-c',str(cpus[worker_index]),*m['command'],'worker',str(Path(m['root'])/SCIENCE_PROTOCOL),SCIENCE_SHA]
                launch=time.monotonic()
                proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      cwd=out,env=env,start_new_session=True,bufsize=0)
                with lock:
                    processes.append(proc)
                    if stop.is_set():replay.kill_group(proc)
                stdout=stdout_path.open('xb');stderr=stderr_path.open('xb')
                def drain_stderr():
                    try:
                        while True:
                            data=proc.stderr.read(65536)
                            if not data:break
                            retained(data,stderr)
                    except Exception as exc:
                        info['stderr_capture_error']=str(exc);halt('stderr_capture_failure',True)
                stderr_thread=threading.Thread(target=drain_stderr,daemon=True);stderr_thread.start()
                def read_event():
                    line=proc.stdout.readline(2*1024*1024)
                    if not line:raise ValueError('unexpected native EOF')
                    retained(line,stdout)
                    require(line.endswith(b'\n'),'native line incomplete or oversized')
                    def pairs(items):
                        d={}
                        for k,v in items:require(k not in d,'duplicate native key');d[k]=v
                        return d
                    def bad(v):raise ValueError('nonfinite native literal: '+v)
                    return json.loads(line,object_pairs_hook=pairs,parse_constant=bad)
                ready=read_event();validate_science_identity(ready,m);info['identity']=ready['identity']
                while True:
                    with lock:
                        if stop.is_set() or not queue:break
                        active=queue.popleft();records[active]['status']='started';records[active]['worker']=worker_index
                    request,encoded=requests[active];proc.stdin.write(encoded);proc.stdin.flush()
                    row=read_event();require(row['kind']=='case_start','case_start missing')
                    for key in ('condition','replicate','seed','dataSha256'):require(row[key]==request[key],'case_start identity mismatch')
                    require(row['rawRows']==1280,'case_start raw rows')
                    observations=[];tries=[]
                    while True:
                        row=read_event()
                        if row['kind']=='cached':observations.append(row['observation'])
                        elif row['kind']=='try':tries.append(row)
                        elif row['kind']=='case_complete':break
                        else:raise ValueError('unexpected native case event: '+str(row.get('kind')))
                    states=validate_science_case(row,request,observations,tries)
                    native_calls+=int(row['runTiming'] is not None)
                    with lock:
                        records[active].update(status='completed',states=states,native=row)
                        byte_count+=len(json.dumps(records[active],allow_nan=False,separators=(',',':')).encode())
                        if byte_count>=SCIENCE_LIMITS['package_max_bytes']:halt('evidence_cap')
                    seen.append(active);active=None
                proc.stdin.close()
                end=read_event();require(end['kind']=='worker_complete' and end['cases']==len(seen),'worker completion totals mismatch')
                require(end['runCallCount']==native_calls and end['legacyCallCount']==native_calls,'worker route totals mismatch')
                # Blocking wait has no timeout-polling fallback; outer watchdog owns time.
                trailing=proc.stdout.read()
                if trailing:retained(trailing,stdout)
                require(trailing==b'','unexpected trailing native output')
                proc.wait();require(proc.returncode==0,'native worker nonzero exit')
                stderr_thread.join();info.update(status='completed',native_totals=end)
                info['lifecycle_wall_seconds']=time.monotonic()-launch
            except Exception as exc:
                info['error']=type(exc).__name__+': '+str(exc)
                with lock:
                    if active is not None:records[active].update(status='incomplete',error=info['error'])
                halt('infrastructure_failure',True)
            finally:
                if proc is not None and proc.poll() is None:
                    replay.kill_group(proc);proc.wait()
                if proc is not None and stdout is not None:
                    remaining=proc.stdout.read()
                    if remaining:retained(remaining,stdout)
                if stderr_thread is not None:stderr_thread.join()
                if stdout is not None:stdout.close()
                if stderr is not None:stderr.close()
                info['completed_indices']=seen
                with lock:
                    worker_results.append(info);done_count+=1
                    if done_count==8:all_done.set()
        if not stop.is_set():
            for i in range(8):
                t=threading.Thread(target=worker,args=(i,),daemon=True);threads.append(t);t.start()
            if not all_done.wait(max(0,deadline-time.monotonic())):halt('wall_timeout',True)
            if not all_done.is_set():all_done.wait(SCIENCE_LIMITS['cleanup_seconds'])
            if not all_done.is_set():halt('cleanup_timeout',True)
        else:all_done.set()
    except Exception as exc:
        halt('host_failure: '+type(exc).__name__+': '+str(exc),True)
        if threads:all_done.wait(SCIENCE_LIMITS['cleanup_seconds'])
    finally:
        finished.set();watcher.join();rss_thread.join()
    elapsed=time.monotonic()-started
    cleanup_complete=all_done.is_set()
    if not cleanup_complete:
        # Snapshot under lock; live daemon writers must not race a purported seal.
        with lock:
            records=json.loads(json.dumps(records,allow_nan=False));worker_results=json.loads(json.dumps(worker_results,allow_nan=False))
    for record in records:
        if record['status']!='completed':record.setdefault('reason',stop_reason[0] if stop_reason else 'not_completed')
    return {'status':'completed' if all(r['status']=='completed' for r in records) and not stop_reason else 'incomplete',
            'stop_reason':stop_reason[0] if stop_reason else None,'records':records,'workers':sorted(worker_results,key=lambda r:r['worker']),
            'lifecycle_wall_seconds':elapsed,'global_deadline_seconds':900,'cleanup_seconds':30,'retained_stream_bytes':byte_count,
            'peak_aggregate_rss_bytes_sampled':peak_rss,'rss_sampling_seconds':.1,'memory_limit_bytes':None,
            'requested_cases':192,'generated_cases':len(requests),'completed_cases':sum(r['status']=='completed' for r in records),
            'retries':0,'cpu_affinity':cpus,'cleanup_complete':cleanup_complete,'_deadline_monotonic':deadline,'evidence_accounting':EVIDENCE_ACCOUNTING,'logical_evidence_bytes_with_reserves':byte_count}


def science_seal(out):
    out=Path(out);paths=sorted(p for p in out.rglob('*') if p.is_file() and p.name not in ('seal.json','seal.sha256','evidence.zip'))
    write_json(out/'seal.json',{'schema':'mvs-variance-science-seal/v1','files':{str(p.relative_to(out)):digest(p) for p in paths}})
    (out/'seal.sha256').write_text(digest(out/'seal.json')+'\n')
    with zipfile.ZipFile(out/'evidence.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths+[out/'seal.json',out/'seal.sha256']:archive.write(path,str(path.relative_to(out)))
    return {'archive_bytes':(out/'evidence.zip').stat().st_size,'archive_sha256':digest(out/'evidence.zip'),
            'within_package_cap':(out/'evidence.zip').stat().st_size<SCIENCE_LIMITS['package_max_bytes']}


def science_run(out,approved_sha):
    out=Path(out).resolve();m=science_verify(out,approved_sha)
    require(not any((out/name).exists() for name in ('started.json','result.json','requests.jsonl','seal.json','evidence.zip')),'science already attempted; retries/resume forbidden')
    plan=read_json(out/'protocol.json')
    write_json(out/'started.json',{'approved_binding_sha256':approved_sha,'protocol_sha256':SCIENCE_SHA,'requested_cases':192,'limits':SCIENCE_LIMITS})
    result=science_execute(out,m,plan)
    if not result['cleanup_complete']:
        write_json(out/'cleanup-failure.json',result)
        return {'status':'cleanup_failed_unsealed','requested_cases':192,'completed_cases':result['completed_cases'],'stop_reason':result['stop_reason'],'package':None,'result_path':str(out/'cleanup-failure.json')}
    postprocess=time.monotonic();deadline=result.pop('_deadline_monotonic')
    try:science_verify(out,approved_sha)
    except Exception as exc:
        result['status']='provenance_invalid';result['provenance_error']=str(exc)
    result['summary']=science_summaries(result['records'],plan)
    result['postprocess_seconds_before_serialization']=time.monotonic()-postprocess
    result['timing_scope']='900-second generation, reference, native, aggregation and result-serialization budget; timeout cleanup up to30s; ZIP/hash packaging measured separately.'
    result['retained_bytes_before_result']=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    result_bytes=json.dumps(result,allow_nan=False,sort_keys=True,indent=2).encode()+b'\n'
    if result['retained_bytes_before_result']+len(result_bytes)>=SCIENCE_LIMITS['package_max_bytes']:
        result['status']='incomplete';result['stop_reason']=result['stop_reason'] or 'evidence_cap_finalization'
    result['wall_seconds_through_result_serialization']=900+time.monotonic()-deadline
    if time.monotonic()>=deadline:
        result['status']='incomplete';result['stop_reason']=result['stop_reason'] or 'wall_budget_exhausted_postprocessing'
    serialized=json.dumps(result,allow_nan=False,sort_keys=True,indent=2).encode()+b'\n'
    if time.monotonic()>=deadline and result['status']=='completed':
        result['status']='incomplete';result['stop_reason']='wall_budget_exhausted_serialization'
        serialized=json.dumps(result,allow_nan=False,sort_keys=True,indent=2).encode()+b'\n'
    with (out/'result.json').open('xb') as stream:stream.write(serialized)
    package_started=time.monotonic();package=science_seal(out)
    package['packaging_seconds']=time.monotonic()-package_started
    package['postprocess_total_seconds']=time.monotonic()-postprocess
    package['logical_evidence_final_bytes']=sum(p.stat().st_size for p in out.rglob('*') if p.is_file() and p.name!='evidence.zip')
    package['logical_overshoot_bytes']=max(0,package['logical_evidence_final_bytes']-SCIENCE_LIMITS['package_max_bytes'])
    return {'status':result['status'],'requested_cases':192,'completed_cases':result['completed_cases'],
            'stop_reason':result['stop_reason'],'package':package,'result_path':str(out/'result.json')}


cost_main=main

def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ('prepare-science','verify-science','run-science'):return cost_main(argv)
    parser=argparse.ArgumentParser(description='Separately frozen, write-once paired science pilot')
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare-science')
    for name in ('root','out','native-dir','build-evidence'):p.add_argument('--'+name,required=True)
    p.add_argument('--runtime-dir',action='append',required=True);p.add_argument('--command',nargs=2,required=True)
    p=sub.add_parser('verify-science');p.add_argument('--out',required=True)
    p=sub.add_parser('run-science');p.add_argument('--out',required=True);p.add_argument('--approved-binding-sha256',required=True)
    args=parser.parse_args(argv)
    if args.action=='prepare-science':result=science_prepare(args.root,args.out,args.native_dir,args.runtime_dir,args.command,args.build_evidence)
    elif args.action=='verify-science':result=science_verify(args.out)
    else:result=science_run(args.out,args.approved_binding_sha256)
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0 if args.action!='run-science' or result['status']=='completed' else 2


if __name__=='__main__':sys.exit(main())
