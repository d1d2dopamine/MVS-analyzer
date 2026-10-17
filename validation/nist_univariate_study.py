"""Frozen, single-attempt NIST numerical study. Discovery never launches native work."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from fractions import Fraction

import nist_univariate_reference as reference

NAMES = ('PiDigits','Lottery','Lew','Mavro','Michelso','NumAcc1','NumAcc2','NumAcc3','NumAcc4')
COUNTS = (5000,218,200,50,100,3,1001,1001,1001)
SCHEMA = 'mvs-nist-study-freeze/v1'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def write_once(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())

def inside(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Unsafe relative source path')
    resolved = (root / p).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Source path escapes root')
    return resolved

def verify_files(root, records):
    for relative, digest in records.items():
        if sha(inside(root, relative)) != digest:
            raise ValueError('Pinned file changed: ' + relative)

def source_pins(root):
    paths = []
    for folder in ('Core', 'Infrastructure', 'Benchmark', 'MvsAnalyzer.Core'):
        paths += [p for p in (root/folder).rglob('*') if p.is_file() and
                  not any(x in {'bin','obj','__pycache__'} for x in p.relative_to(root).parts)]
    paths += [root/'SharedSources.props', root/'docs/ROUND53_NIST_UNIVARIATE_PROTOCOL.md']
    paths += [p for p in (root/'validation').glob('*nist*') if p.is_file()]
    paths += [p for p in (root/'validation/nist_univariate_harness').glob('*') if p.is_file()]
    paths += [root/f'validation/nist_strd/{name}.dat' for name in NAMES]
    return {str(p.relative_to(root)):sha(p) for p in sorted(set(paths))}

def prepare(root, out, native, runtime, smoke_summary):
    root, out, native = root.resolve(strict=True), out.absolute(), native.resolve(strict=True)
    if out.exists():
        raise ValueError('Preparation directory must be new')
    smoke=read_json(smoke_summary)
    if smoke.get('status')!='passed' or smoke.get('processes')!=19 or type(smoke.get('wallSeconds')) not in (int,float) or not math.isfinite(smoke['wallSeconds']) or not 0<=smoke['wallSeconds']<120 or smoke.get('nativeSha256')!=sha(native):
        raise ValueError('Missing/invalid native preflight evidence')
    records=smoke.get('records',[])
    if len(records)!=19 or records[0].get('status')!='completed' or records[0].get('exitCode')!=0 or any(x.get('status')!='failed' or x.get('exitCode')!=1 for x in records[1:]):
        raise ValueError('Native preflight outcomes incomplete')
    expected_identity={'harnessSha256':sha(native),'coreSha256':sha(native.parent/'MvsAnalyzer.Core.dll'),'runtimeVersion':runtime,'architecture':'x64'}
    if smoke.get('nativeIdentity')!=expected_identity or smoke.get('testSourceSha256')!=sha(root/'validation/test_nist_univariate_study.py'):
        raise ValueError('Native preflight build/runtime/test binding mismatch')
    for record in records:
        if len(record.get('files',{}))!=3:raise ValueError('Native preflight files missing')
        verify_files(Path(smoke_summary).resolve().parent,record['files'])
    protocol = read_json(root/'validation/nist-univariate-protocol-v1.json')
    if protocol['id'] != 'MVS-NUM-NIST-UNIVARIATE-1.0.0' or protocol['relativeTolerance'] != '1e-10':
        raise ValueError('Unexpected frozen protocol')
    manifest_path=root/'validation/nist-univariate-inputs.json'
    if sha(manifest_path)!=protocol['inputManifestSha256'] or sha(root/'docs/ROUND53_NIST_UNIVARIATE_PROTOCOL.md')!=protocol['documentSha256']:
        raise ValueError('Protocol document/input manifest changed')
    manifest=read_json(manifest_path)
    if manifest['dataset_order']!=list(NAMES) or len(manifest['datasets'])!=9:raise ValueError('Source manifest order changed')
    for item,name,count in zip(manifest['datasets'],NAMES,COUNTS):
        if item['dataset']!=name or item['observation_count']!=count or sha(root/f'validation/nist_strd/{name}.dat')!=item['original_file']['sha256']:
            raise ValueError('Original input hash/count mismatch')
    parsed = [reference.parse_dataset((root/f'validation/nist_strd/{name}.dat').read_bytes()) for name in NAMES]
    if [p['id'] for p in parsed] != list(NAMES) or [p['count'] for p in parsed] != list(COUNTS):
        raise ValueError('Fixed dataset identity/count mismatch')
    if any(Fraction(p['certified'][key]['text'])==0 for p in parsed for key in ('mean','standardDeviation')):
        raise ValueError('Unexpected zero certified field before evaluation')
    refs = [reference.reference_dataset(p) for p in parsed]
    for item in refs:
        if not item['certifiedValidation']['passed']:
            raise ValueError('Certified reference mismatch: ' + item['id'])
        for key in ('decimalInput','binary64Input'):
            if item[key]['precisionConsistency']['passed'] is not True:
                raise ValueError('Reference precision disagreement: ' + item['id'])
    out.mkdir(parents=True)
    write_once(out/'input.json', {'schema':'mvs-nist-input/v1','cases':[
        {'id':p['id'],'sourceSha256':p['sourceSha256'],'values':p['tokens']} for p in parsed]})
    write_once(out/'references.json', refs)
    binary_files = {p.name:sha(p) for p in sorted(native.parent.iterdir()) if p.is_file() and
                    (p.suffix=='.dll' or p.name.endswith(('.deps.json','.runtimeconfig.json')))}
    if native.name not in binary_files or 'MvsAnalyzer.Core.dll' not in binary_files:
        raise ValueError('Missing native binary identities')
    config = {'schema':SCHEMA,'preparedUtc':datetime.now(timezone.utc).isoformat(),
        'protocolId':protocol['id'],'sourceFiles':source_pins(root),'nativeFile':native.name,
        'binaryFiles':binary_files,'runtimeVersion':runtime,'architecture':'x64',
        'inputSha256':sha(out/'input.json'),'referencesSha256':sha(out/'references.json'),
        'datasetNames':list(NAMES),'datasetCounts':list(COUNTS),'expectedNumericalRows':18,
        'nativeTimeoutSeconds':120,'preflightSmoke':{'sha256':sha(smoke_summary),'processes':19,'wallSeconds':smoke['wallSeconds']},'newScientificSamples':False,
        'host':{'system':platform.system(),'machine':platform.machine(),'python':platform.python_version()}}
    write_once(out/'config.json',config)
    return {'configSha256':sha(out/'config.json'),'datasets':9,'numericalRows':18}

def validate_envelope(envelope, config, parsed, refs):
    expected = {'schema':'mvs-nist-native/v1','status':'completed','inputSha256':config['inputSha256'],
                'harnessSha256':config['binaryFiles'][config['nativeFile']],
                'coreSha256':config['binaryFiles']['MvsAnalyzer.Core.dll'],
                'runtimeVersion':config['runtimeVersion'],'architecture':config['architecture']}
    for key, value in expected.items():
        if type(envelope.get(key)) is not type(value) or envelope[key] != value:
            raise ValueError('Native envelope mismatch: ' + key)
    cases = envelope.get('cases')
    if type(cases) is not list or len(cases)!=9 or any(type(c) is not dict for c in cases) or [c.get('id') for c in cases]!=list(NAMES):
        raise ValueError('Missing, duplicated or reordered native cases')
    if len(parsed)!=9 or len(refs)!=9:raise ValueError('Reference rows incomplete')
    return [reference.compare_native(case, p, ref) for case,p,ref in zip(cases,parsed,refs)]

def run(root, out, native, dotnet, config_hash):
    root, out, native = root.resolve(strict=True), out.resolve(strict=True), native.resolve(strict=True)
    if sha(out/'config.json') != config_hash:
        raise ValueError('Configuration hash mismatch')
    config = read_json(out/'config.json')
    if config['schema']!=SCHEMA or config['nativeFile']!=native.name:
        raise ValueError('Unknown study configuration')
    verify_files(root, config['sourceFiles']);verify_files(native.parent,config['binaryFiles'])
    if sha(out/'input.json')!=config['inputSha256'] or sha(out/'references.json')!=config['referencesSha256']:
        raise ValueError('Prepared evidence changed')
    if config['datasetNames']!=list(NAMES) or config['datasetCounts']!=list(COUNTS) or config['expectedNumericalRows']!=18 or config['nativeTimeoutSeconds']!=120:
        raise ValueError('Frozen dimensions/budget changed')
    parsed = [reference.parse_dataset((root/f'validation/nist_strd/{name}.dat').read_bytes()) for name in NAMES]
    refs = read_json(out/'references.json')
    if any((out/name).exists() for name in ('attempt.json','result.json','native.stdout.json','native.stderr.txt')):
        raise ValueError('Attempt/output paths already exist; no overwrite or replay')
    write_once(out/'attempt.json', {'startedUtc':datetime.now(timezone.utc).isoformat(),'configSha256':config_hash,
                                  'scope':'one fixed NIST execution; no replacement or outcome-based retry'})
    started = time.monotonic();stdout=b'';stderr=b'';code=None
    result={'schema':'mvs-nist-study-result/v1','protocolId':config['protocolId'],
            'configSha256':config_hash,'executionStatus':'technical_failure','numericalContractPassed':False,
            'requestedDatasets':9,'requestedNumericalRows':18,'completedNumericalRows':0,
            'scientificStatus':'NO-GO unchanged','productionChanged':False}
    try:
        completed = subprocess.run([str(dotnet),str(native),'--input',str(out/'input.json')],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120-config['preflightSmoke']['wallSeconds'],check=False)
        stdout,stderr,code=completed.stdout,completed.stderr,completed.returncode
        if code!=0:
            raise ValueError('Native process failed with exit ' + str(code))
        if len(stdout)>4*1024*1024 or len(stderr)>1024*1024:
            raise ValueError('Unexpected evidence size')
        envelope=json.loads(stdout.decode('utf-8'),object_pairs_hook=strict_object,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        rows=validate_envelope(envelope,config,parsed,refs)
        verify_files(root,config['sourceFiles']);verify_files(native.parent,config['binaryFiles'])
        if sha(out/'input.json')!=config['inputSha256'] or sha(out/'references.json')!=config['referencesSha256']:
            raise ValueError('Evidence changed during execution')
        result.update(executionStatus='completed',completedNumericalRows=18,results=rows,
                      numericalContractPassed=all(x['primary']['passed'] for x in rows))
    except subprocess.TimeoutExpired as error:
        stdout=error.stdout or b'';stderr=error.stderr or b''
        result['error']={'type':'TimeoutExpired','message':'Native execution exceeded120seconds; process killed and reaped by subprocess.run'}
    except Exception as error:
        result['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        (out/'native.stdout.json').write_bytes(stdout);(out/'native.stderr.txt').write_bytes(stderr)
        result.update(nativeExitCode=code,wallSeconds=time.monotonic()-started,
                      stdoutSha256=sha(out/'native.stdout.json'),stderrSha256=sha(out/'native.stderr.txt'))
        write_once(out/'result.json',result)
    return result

def retained_fixture_process(command, timeout, stdout_path, stderr_path):
    """Small bounded fixture capture; a failed/timeout attempt retains partial output."""
    stdout=b'';stderr=b'';code=None;error=None
    try:
        completed=subprocess.run(command,capture_output=True,timeout=timeout,check=False)
        stdout,stderr,code=completed.stdout,completed.stderr,completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout,stderr=exc.stdout or b'',exc.stderr or b''
        error={'type':'TimeoutExpired','message':'Fixture timeout; subprocess killed/reaped'}
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
    finally:
        with Path(stdout_path).open('xb') as stream:stream.write(stdout)
        with Path(stderr_path).open('xb') as stream:stream.write(stderr)
    return {'stdout':stdout,'stderr':stderr,'exitCode':code,'error':error}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','run'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--native',type=Path,required=True);p.add_argument('--runtime',default='8.0.31')
    p.add_argument('--smoke-summary',type=Path);p.add_argument('--dotnet',type=Path);p.add_argument('--config-sha256');p.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    try:
        if a.command=='prepare':
            if not a.smoke_summary:raise ValueError('--smoke-summary required')
            result=prepare(a.root,a.out,a.native,a.runtime,a.smoke_summary)
        else:
            if not a.execute or not a.dotnet or not a.config_sha256:raise ValueError('Explicit --execute, --dotnet and --config-sha256 required')
            result=run(a.root,a.out,a.native,a.dotnet,a.config_sha256)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return int(result.get('executionStatus')=='technical_failure')
    except Exception as error:
        print(json.dumps({'executionStatus':'technical_failure','error':{'type':type(error).__name__,'message':str(error)}}))
        return 1

if __name__=='__main__':
    raise SystemExit(main())
