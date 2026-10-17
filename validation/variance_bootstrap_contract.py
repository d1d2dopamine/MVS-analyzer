#!/usr/bin/env python3
"""Bounded deterministic audit of existing variance Generate and Run contracts.

The oracle uses literal cache values and a scripted uniform tape. It does not fit
models, invoke a production Gaussian generator, or estimate statistical power.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

PROTOCOL_ID = 'round49-variance-bootstrap-contract-v1'
NATIVE_SECONDS = 30
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
EFFECT_GRID = [1.0, 1.02, 1.05, 1.10, 1.20]
ABS_TOL = 2e-12
REL_TOL = 2e-12

class InvalidEvidence(ValueError):
    """Malformed, incomplete, or unbound evidence must not pass."""

def require(condition, message):
    if not condition:
        raise InvalidEvidence(message)

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def read_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON property: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise InvalidEvidence('Nonstandard JSON number: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)

def atomic_json(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    require(len(raw) <= MAX_ARTIFACT_BYTES, 'JSON artifact exceeds bound')
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)

def create_evidence_directory(path):
    path = Path(path).resolve()
    require(not path.exists(), 'Evidence directory already exists; refusing to overwrite a prior attempt')
    path.mkdir(parents=True, exist_ok=False)
    return path

def bootstrap_p(reference, statistic):
    valid = [x for x in reference if finite(x)]
    return (1 + sum(x >= statistic for x in valid)) / (len(valid) + 1) if valid and finite(statistic) else None

def wilson(successes, requested):
    """95% score interval, computed from integer counts and requested denominator."""
    if requested <= 0:
        return [None, None]
    z2 = 1.959963984540054 ** 2
    # Algebraically independent quadratic-score form.
    denominator = requested + z2
    middle = (successes + z2 / 2) / denominator
    half = math.sqrt(z2 * (successes * (requested-successes)/requested + z2/4)) / denominator
    return [max(0., middle-half), min(1., middle+half)]

def quantile(values, probability):
    data = sorted(x for x in values if finite(x))
    if not data:
        return None
    position = (len(data)-1)*probability
    lower, upper = math.floor(position), math.ceil(position)
    return data[lower] + (data[upper]-data[lower])*(position-lower)

def mde_from_curve(effects, curve):
    if len(effects) != len(curve) or len(curve) < 2 or not all(finite(x) for x in curve) or curve[0] >= .8:
        return None
    for i in range(1, len(curve)):
        if curve[i-1] < .8 <= curve[i] and effects[i] > effects[i-1]:
            return effects[i-1] - 1 + (effects[i]-effects[i-1])*(.8-curve[i-1])/(curve[i]-curve[i-1])
    return None

def compare_value(actual, expected, path='$'):
    """Compare every field and list element, never accepting only a p-value."""
    failures = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            return [path + ': object fields differ']
        for key in expected:
            failures += compare_value(actual[key], expected[key], path+'.'+key)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [path + ': array length differs']
        for i, (a, e) in enumerate(zip(actual, expected)):
            failures += compare_value(a, e, path+'['+str(i)+']')
    elif finite(expected) and type(expected) is float:
        if not finite(actual) or abs(actual-expected) > ABS_TOL*max(1.,abs(expected)):
            failures.append(path + ': numeric mismatch')
    elif type(actual) is not type(expected) or actual != expected:
        failures.append(path + ': value/type mismatch')
    return failures

SOURCE_FILES = ('Core/VarianceAnalysis.cs', 'Core/ScientificInfrastructure.cs', 'Core/AnalysisEngine.cs',
    'Core/RunRecording.cs', 'Core/Models.cs', 'MvsAnalyzer.Core/MvsAnalyzer.Core.csproj', 'SharedSources.props',
    'validation/variance_bootstrap_contract/Program.cs',
    'validation/variance_bootstrap_contract/VarianceBootstrapContract.csproj')
BUDGETS = dict(generateCalls=6, runCalls=14, cachedReads=19241, uniformDraws=106,
    gaussianDraws=53, fitCalls=0, statisticCalls=0, optimizerCalls=0,
    calculationCallbacks=0, intervalGenerateCalls=0)
PROTOCOL_ID = 'round49-variance-bootstrap-contract-v1'

WARNINGS = [
 'Conditional Gaussian errors, independent entities and conditionally independent repeats are assumptions, not facts established by this fit.',
 'Power/FPR use fitted null nuisance parameters and an independent evaluation stream against one reference distribution; uncertainty is conditional on that reference and fitted model.',
 'Failed evaluation fits count as non-rejections; failure counts are exported. Rates are suppressed above 10% failures.',
 'Observed SD of entity means includes measurement error. The untruncated method-of-moments estimate is included for transparency.',
 'Variance-estimate intervals are pointwise parametric percentile intervals conditional on the fitted model; boundary coverage is not guaranteed.',
 'No global equivalence conclusion follows from a non-significant variance test. Small samples and boundary estimates require external validation.']

def literal_number(value):
    if value == 'NaN':
        return None
    require(finite(value), 'Invalid numeric cache literal')
    return float(value)

def expected_generate(case):
    tape, model = case['uniformTape'], case['model']
    require(len(tape) % 2 == 0, 'Uniform tape must contain radial/angle pairs')
    normals = []
    for radius, angle in zip(tape[::2], tape[1::2]):
        require(radius in (0, .5) and angle in (0, .5), 'Unfrozen uniform tape angle/radius')
        # Only axis angles are allowed: avoid copying production cosine/Gaussian.
        length = math.sqrt(30*math.log(10)) if radius == 0 else math.sqrt(2*math.log(2))
        normals.append(length if angle == 0 else -length)
    offset, rows = 0, []
    for cluster in case['design']:
        group, count = cluster['group'], cluster['count']
        within, between = model['Within'][group], model['Between'][group]
        if group == len(model['Means'])-1:
            if case['track'] == 'within': within *= case['effect']**2
            if case['track'] == 'between': between *= case['effect']**2
        draw = normals[offset:offset+count+1]
        require(len(draw) == count+1, 'Uniform tape exhausted')
        rows.append(dict(entity=cluster['entity'], group=group, count=count,
            mean=model['Means'][group]+math.sqrt(between)*draw[0]+math.sqrt(within/count)*draw[1],
            withinSumSquares=within*math.fsum(x*x for x in draw[2:])))
        offset += count+1
    require(offset == len(normals), 'Unused uniform tape')
    return rows

def expected_run(case, engine_version):
    n, r, alpha = case['repetitions'], case['referenceReplications'], case['alpha']
    cache, requested, progress = case['cache'], [], []
    def get(key):
        require(key in cache, 'Missing scripted cache key: '+key)
        requested.append(key)
        return cache[key]
    initial = get('initial-fit')
    require(initial['Converged'] is False, 'Intervals are outside this frozen contract')
    groups = []
    for name in case['data']['groupNames']:
        clusters = {}
        for obs in case['data']['observations']:
            if obs['group'] == name:
                clusters.setdefault(obs['entity'], []).append(obs['value'])
        means = [math.fsum(v)/len(v) for v in clusters.values()]
        center = math.fsum(means)/len(means)
        observed = math.fsum((v-center)**2 for v in means)/(len(means)-1)
        wss = math.fsum(math.fsum((x-math.fsum(v)/len(v))**2 for x in v) for v in clusters.values())
        moment = wss/sum(len(v)-1 for v in clusters.values())
        between = observed-moment*math.fsum(1/len(v) for v in clusters.values())/len(clusters)
        i = case['data']['groupNames'].index(name)
        groups.append(dict(group=name, entities=len(clusters), measurements=sum(map(len,clusters.values())),
            mean=float(initial['Means'][i]),withinVariance=None,betweenVariance=None,
            observedCenterVariance=observed,momentBetweenUntruncated=between,icc=None,
            status='not_converged_or_degenerate',withinLow=None,withinHigh=None,betweenLow=None,betweenHigh=None,
            intervalReplications=0,intervalStatus='not_computed'))
    tracks = []
    for tr, track in enumerate(('within','between')):
        null = get(track+'/null-fit')
        observed = literal_number(get(track+'/observed'))
        refs = []
        if null['Converged']:
            for i in range(r):
                refs.append(literal_number(get(track+'/reference/'+str(i))))
                progress.append(dict(fraction=.15+.85*(tr+.35*(i+1)/r)/2,
                    action='Variance-component null bootstrap',details=track))
        m = sum(finite(x) for x in refs)
        usable = null['Converged'] and finite(observed) and m >= .9*r
        failures, successes = [0,0], [0,0]
        grid_total, grid_failed, grid_reject = [0]*5, [0]*5, [0]*5
        if usable:
            for i in range(n):
                for j, label in enumerate(('null','alternative')):
                    value = literal_number(get(track+'/'+label+'/'+str(i)))
                    if value is None: failures[j] += 1
                    elif bootstrap_p(refs,value) < alpha/2: successes[j] += 1
                point = i % 5
                grid_total[point] += 1
                value = literal_number(get(track+'/grid/'+str(i)))
                if value is None: grid_failed[point] += 1
                elif bootstrap_p(refs,value) < alpha/2: grid_reject[point] += 1
                progress.append(dict(fraction=.15+.85*(tr+.35+.65*(i+1)/n)/2,
                    action='Separate component power',details=track))
        else:
            failures = [n,n]
        valid = usable and all(x <= .1*n for x in failures)
        fpr, power = [float(x/n) if valid else None for x in successes]
        fci, pci = [wilson(x,n) if valid else [None,None] for x in successes]
        p = bootstrap_p(refs,observed) if usable else None
        adjusted = min(1.,2*p) if p is not None else None
        curve = [float(k/t) if t and f <= .1*t else None for k,t,f in zip(grid_reject,grid_total,grid_failed)]
        mde = mde_from_curve(EFFECT_GRID,curve) if valid and min(grid_total)>=100 else None
        scale = max(null['Within']+null['Between'])
        boundary = any(x <= 1e-8*max(1e-300,scale) for x in null[track.title()])
        if boundary:
            power,mde,pci,curve = None,None,[None,None],[None]*5
        tracks.append(dict(track=track,statistic=observed,pValue=p,adjustedP=adjusted,fpr=fpr,
            fprLow=fci[0],fprHigh=fci[1],power=power,powerLow=pci[0],powerHigh=pci[1],
            effectSdMultiplier=float(case[track+'Effect']), referenceReplications=m, referenceFailures=r-m,
            evaluationReplications=n,nullFailures=failures[0],alternativeFailures=failures[1],
            verdict='difference' if usable and adjusted < alpha else 'insufficient',
            status='bootstrap_or_fit_failure' if not usable else 'boundary_baseline_power_not_identifiable' if boundary else 'conditional_plugin_bootstrap' if valid else 'excess_simulation_failures',
            effectGrid=EFFECT_GRID,powerCurve=curve,mde=mde,
            mdeStatus='estimated_on_grid' if mde is not None else 'zero_baseline' if boundary else 'insufficient_simulations' if min(grid_total)<100 else 'target_not_reached_or_invalid_curve'))
    require(set(requested)==set(cache) and len(requested)==len(cache), 'Unused/repeated cache entries')
    report = dict(engineVersion=engine_version,
        model='Gaussian random intercept; group-specific mean and variance components; REML estimates / ML bootstrap tests',
        decisionFamily='Two component hypotheses, Bonferroni alpha/2; separate from the summary-metric family',
        seed=case['seed'],alpha=float(alpha),groups=groups,tracks=tracks,warnings=case['data']['warnings']+WARNINGS)
    return dict(report=report,requestedKeys=requested,progress=progress)

def load_fixtures(path):
    raw = Path(path).read_bytes()
    require(len(raw)<=MAX_ARTIFACT_BYTES, 'Oversized fixture')
    document = read_json(raw)
    require(set(document)=={'schemaVersion','protocolId','status','budgets','generatorCases','runCases'}, 'Fixture root fields differ')
    require(document['schemaVersion']==1 and document['protocolId']==PROTOCOL_ID and document['status']=='frozen', 'Unfrozen/unknown fixture')
    require(document['budgets']==BUDGETS, 'Fixture budget mismatch')
    for key, prefix, count in [('generatorCases','G',6),('runCases','R',14)]:
        rows = document[key]
        require(isinstance(rows,list) and [c.get('id') for c in rows]==[prefix+f'{i:02}' for i in range(1,count+1)], 'Fixture identities/order differ')
        require(all(c.get('expectedException') is None for c in rows), 'Frozen scenarios must return normally')
    require(sum(len(c['uniformTape']) for c in document['generatorCases'])==106, 'Uniform count mismatch')
    require(sum(len(c['cache']) for c in document['runCases'])==19241, 'Cache count mismatch')
    for case in document['generatorCases']:
        require(set(case)=={'id','design','model','uniformTape','track','effect','expectedException'}, 'Generator fields differ')
        expected_generate(case)
    for case in document['runCases']:
        require(set(case)=={'id','data','repetitions','referenceReplications','withinEffect','betweenEffect','seed','alpha','cache','expectedException'}, 'Run fields differ')
        require(type(case['repetitions']) is int and 100<=case['repetitions']<=500 and case['referenceReplications'] in (99,100), 'Replication bound mismatch')
        require(finite(case['alpha']) and 0<case['alpha']<1 and case['seed']==54, 'Run configuration mismatch')
        require(case['withinEffect']==2 and case['betweenEffect']==3, 'Effect mismatch')
        expected_run(case,'1.6.2')
    return document, sha256(raw)

def decode_numeric(value):
    import struct
    if isinstance(value,list): return [decode_numeric(x) for x in value]
    if not isinstance(value,dict):
        require(not isinstance(value,float), 'Raw floating field lacks numeric provenance')
        return value
    if 'classification' not in value:
        return {k:decode_numeric(v) for k,v in value.items()}
    require(set(value)=={'classification','value','bits'}, 'Numeric provenance shape mismatch')
    bits = value['bits']
    require(isinstance(bits,str) and len(bits)==16 and all(c in '0123456789abcdef' for c in bits), 'Malformed floating bits')
    number = struct.unpack('>d',bytes.fromhex(bits))[0]
    kind = 'nan' if math.isnan(number) else 'positive_infinity' if number==math.inf else 'negative_infinity' if number==-math.inf else 'finite'
    require(kind==value['classification'], 'Floating bits/classification mismatch')
    if kind=='finite':
        require(finite(value['value']) and struct.pack('>d',value['value']).hex()==bits, 'Finite floating value/bits mismatch')
        return float(value['value'])
    require(value['value'] is None, 'Nonfinite floating value must be null')
    require(kind=='nan', 'Unexpected infinite report value')
    return None

def decode_expected(value, expected):
    # Report/Generate numeric fields must retain explicit FP provenance even for NaN.
    if type(expected) is float or expected is None:
        require(isinstance(value,dict) and 'classification' in value, 'Numeric report field lacks FP provenance')
        return decode_numeric(value)
    if isinstance(expected,dict):
        require(isinstance(value,dict) and set(value)==set(expected), 'Report object fields differ')
        return {k:decode_expected(value[k],v) for k,v in expected.items()}
    if isinstance(expected,list):
        require(isinstance(value,list) and len(value)==len(expected), 'Report array length differs')
        return [decode_expected(a,e) for a,e in zip(value,expected)]
    return value

def validate_native(document, digest, native, root, assembly):
    require(native.get('schemaVersion')==1 and native.get('protocolId')==PROTOCOL_ID, 'Unknown native protocol')
    require(native.get('inputSha256')==digest, 'Native fixture hash mismatch')
    for key, expected in [('generatorCaseCount',6),('runCaseCount',14),('generateCallCount',6),('runCallCount',14)]:
        require(type(native.get(key)) is int and native[key]==expected, 'Native count mismatch: '+key)
    require(native.get('recorderSelfCheck')==dict(missingKeyRejected=True,wrongTypeRejected=True,calculationCallbackCount=0),'Recorder fail-closed self-check missing/failed')
    identity = native.get('identity',{})
    require(identity.get('experimental') is True, 'Missing experimental identity')
    require(identity.get('sourceSha256')=={name:sha256((Path(root)/name).read_bytes()) for name in SOURCE_FILES}, 'Build-time source identity mismatch')
    for key, path in [('harnessAssembly',Path(assembly)),('coreAssembly',Path(assembly).with_name('MvsAnalyzer.Core.dll'))]:
        item = identity.get(key,{})
        require(item.get('sha256')==sha256(path.read_bytes()) and item.get('fileName')==path.name and bool(item.get('moduleVersionId')), 'Assembly identity mismatch: '+key)
    runtime = identity.get('runtime',{})
    require(all(runtime.get(k) for k in ['framework','version','os','processArchitecture','coreLibrarySha256']), 'Incomplete runtime identity')
    for key in ('generatorCases','runCases'):
        rows = native.get(key)
        require(isinstance(rows,list) and [row.get('id') for row in rows]==[c['id'] for c in document[key]], 'Native identities/order mismatch')
        for case,row in zip(document[key],rows):
            require(row.get('expectedException')==case['expectedException'], 'Exception expectation mismatch')
            require(row.get('status')=='returned' and row.get('exception') is None, 'Unexpected exception; native details retained')
    return native

def compare(document, native):
    results=[]
    for case,row in zip(document['generatorCases'],native['generatorCases']):
        expected=expected_generate(case)
        errors=compare_value(decode_expected(row['output'],expected),expected)
        before,after=row.get('inputBeforeSha256'),row.get('inputAfterSha256')
        if not isinstance(before,str) or len(before)!=64 or before!=after: errors.append('Generator inputs mutated or missing immutability hash')
        for key,value in [('generateCallCount',1),('uniformConsumption',len(case['uniformTape'])),('uniformTapeLength',len(case['uniformTape']))]:
            if type(row.get(key)) is not int or row[key]!=value: errors.append(key+': count mismatch')
        results.append(dict(id=case['id'],passed=not errors,failureReasons=errors,expected=expected))
    total=0
    for case,row in zip(document['runCases'],native['runCases']):
        expected=expected_run(case,'1.6.2'); keys=expected['requestedKeys']; total+=len(keys)
        errors=compare_value(decode_expected(row['report'],expected['report']),expected['report'])
        errors+=compare_value(decode_expected(row['progress'],expected['progress']),expected['progress'],'$.progress')
        begin=decode_numeric(row['beginRequest'])
        for key,value in dict(kind='variance',repetitions=case['repetitions'],referenceReplications=case['referenceReplications'],seed=case['seed'],effect=float(case['withinEffect']),secondEffect=float(case['betweenEffect']),alpha=float(case['alpha'])).items():
            errors+=compare_value(begin.get(key),value,'$.beginRequest.'+key)
        require(isinstance(begin.get('data'),dict),'Missing Begin data')
        errors+=compare_value(begin['data'].get('groupNames'),case['data']['groupNames'],'$.beginRequest.data.groupNames')
        events=['Begin:variance','Try:result']+[event for key in keys for event in ('Cached:'+key,'Try:'+key)]+['Finish','Dispose']
        for key,value in [('events',events),('seededKeys',sorted(keys)),('requestedKeys',keys),('consumedKeys',keys),('missingKeys',[])]:
            errors+=compare_value(row.get(key),value,'$.'+key)
        for key,value in [('runCallCount',1),('actualGenerateCallCount',0),('calculationCallbackCount',0),('fitCallCount',0),('statisticCallCount',0),('cachedRequestCount',len(keys)),('cacheHitCount',len(keys)),('cacheMissCount',0),('acquisitionCount',1),('finishCount',1),('disposalCount',1)]:
            if type(row.get(key)) is not int or row[key]!=value: errors.append(key+': count mismatch')
        results.append(dict(id=case['id'],passed=not errors,failureReasons=errors,expected=expected))
    require(total==BUDGETS['cachedReads'], 'Independent expected cache budget mismatch')
    return dict(status='passed' if all(r['passed'] for r in results) else 'failed_contract',results=results,
        scientificConclusion='Deterministic Generate and cache-only Run aggregation/output contract only. Equality-fit argument wiring is source-reviewed; skipped delegates do not validate it. No calibration, power accuracy, coverage, model adequacy, or end-to-end simulated-refit claim.')

def native_run(command, fixtures, digest, out):
    require(sha256(Path(fixtures).read_bytes())==digest, 'Fixture bytes changed after reference preparation')
    complete=list(command)+['contract',str(Path(fixtures).resolve()),digest]
    started=time.monotonic()
    try:
        process=subprocess.run(complete,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=NATIVE_SECONDS,check=False)
        stdout,stderr,code,timedout=process.stdout,process.stderr,process.returncode,False
    except subprocess.TimeoutExpired as error:
        stdout,stderr,code,timedout=error.stdout or b'',error.stderr or b'',None,True
    except OSError as error:
        atomic_json(out/'native-process.json',dict(command=complete,launchError=str(error),nativeInvoked=False))
        raise
    try:
        (out/'native.stdout').write_bytes(stdout)
        (out/'native.stderr').write_bytes(stderr)
        evidence=dict(command=complete,exitCode=code,timedOut=timedout,elapsedSeconds=time.monotonic()-started,
            stdoutSha256=sha256(stdout),stderrSha256=sha256(stderr),stdoutBytes=len(stdout),stderrBytes=len(stderr))
        atomic_json(out/'native-process.json',evidence)
        require(len(stdout)<=MAX_ARTIFACT_BYTES and len(stderr)<=MAX_ARTIFACT_BYTES,'Native artifact exceeds fixed size bound; exact output retained')
        require(not timedout and code==0,'Native subprocess timeout/nonzero exit; exact output retained')
        return read_json(stdout),evidence
    except Exception as error:
        error.native_started=True
        raise

def prepare_seal(root, fixtures, protocol, assembly, identity_export):
    """Record reviewed bytes from a zero-case identity export; never run/refresh a seal.

    This is a local pre-execution content record, not external preregistration.
    The caller persists it before invoking main and reviews any changed inputs.
    """
    root,fixtures,protocol,assembly=map(Path,(root,fixtures,protocol,assembly))
    require(identity_export.get('schemaVersion')==1 and identity_export.get('protocolId')==PROTOCOL_ID,
        'Identity-only protocol mismatch')
    require(type(identity_export.get('generateCallCount')) is int and identity_export['generateCallCount']==0 and
        type(identity_export.get('runCallCount')) is int and identity_export['runCallCount']==0,
        'Seal preparation requires zero-case identity export')
    identity=identity_export.get('identity',{})
    native_sources={name:sha256((root/name).read_bytes()) for name in SOURCE_FILES}
    require(identity.get('experimental') is True and identity.get('sourceSha256')==native_sources,
        'Identity-only source mismatch')
    harness_hash=sha256(assembly.read_bytes())
    core_hash=sha256(assembly.with_name('MvsAnalyzer.Core.dll').read_bytes())
    require(identity.get('harnessAssembly',{}).get('sha256')==harness_hash and identity.get('coreAssembly',{}).get('sha256')==core_hash,
        'Identity-only assembly mismatch')
    runtime=identity.get('runtime',{})
    require(isinstance(runtime.get('version'),str) and bool(runtime['version']) and isinstance(runtime.get('coreLibrarySha256'),str) and len(runtime['coreLibrarySha256'])==64,
        'Identity-only runtime incomplete')
    return dict(fixtureSha256=sha256(fixtures.read_bytes()),protocolSha256=sha256(protocol.read_bytes()),
        sourceSha256={name:sha256((root/name).read_bytes()) for name in SOURCE_FILES+('validation/variance_bootstrap_contract.py','validation/test_variance_bootstrap_contract.py')},
        harnessAssemblySha256=harness_hash,coreAssemblySha256=core_hash,
        runtimeVersion=runtime['version'],runtimeCoreLibrarySha256=runtime['coreLibrarySha256'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--seal',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--native-command',nargs='+',required=True)
    args=parser.parse_args()
    try: out=create_evidence_directory(args.out)
    except (InvalidEvidence,OSError) as error:
        print(json.dumps(dict(status='invalid_evidence',nativeInvoked=False,error=str(error))))
        return 2
    report=dict(schemaVersion=1,protocolId=PROTOCOL_ID,status='running',nativeInvoked=False)
    try:
        document,digest=load_fixtures(args.fixtures)
        assembly=Path(args.native_command[-1]).resolve()
        binding=dict(fixtureSha256=digest,protocolSha256=sha256(args.protocol.read_bytes()),
            sourceSha256={name:sha256((args.root/name).read_bytes()) for name in SOURCE_FILES+('validation/variance_bootstrap_contract.py','validation/test_variance_bootstrap_contract.py')},
            harnessAssemblySha256=sha256(assembly.read_bytes()),coreAssemblySha256=sha256(assembly.with_name('MvsAnalyzer.Core.dll').read_bytes()))
        seal=read_json(args.seal.read_bytes())
        require(set(seal)==set(binding)|{'runtimeVersion','runtimeCoreLibrarySha256'}, 'Seal fields differ')
        require({k:seal[k] for k in binding}==binding,'Pre-execution seal differs from fixture/protocol/source/binaries')
        require(isinstance(seal['runtimeVersion'],str) and bool(seal['runtimeVersion']) and isinstance(seal['runtimeCoreLibrarySha256'],str) and len(seal['runtimeCoreLibrarySha256'])==64,'Incomplete runtime seal')
        report['binding']=binding; report['sealSha256']=sha256(args.seal.read_bytes())
        report['versions']=dict(python=sys.version,platform=platform.platform())
        reference=dict(generatorCases=[dict(id=c['id'],output=expected_generate(c)) for c in document['generatorCases']],
            runCases=[dict(id=c['id'],**expected_run(c,'1.6.2')) for c in document['runCases']])
        atomic_json(out/'reference.json',reference)
        native,process=native_run(args.native_command,args.fixtures,digest,out)
        report['nativeInvoked']=True; report['nativeProcess']=process
        require(sha256(args.fixtures.read_bytes())==digest,'Fixture changed during native run')
        require(binding['sourceSha256']=={name:sha256((args.root/name).read_bytes()) for name in binding['sourceSha256']},'Source changed during native run')
        validate_native(document,digest,native,args.root,assembly)
        require(native['identity']['runtime']['version']==seal['runtimeVersion'] and native['identity']['runtime']['coreLibrarySha256']==seal['runtimeCoreLibrarySha256'],'Runtime identity differs from seal')
        report['nativeIdentity']=native['identity']
        report['comparison']=compare(document,native)
        report['status']=report['comparison']['status']
    except (InvalidEvidence,ValueError,KeyError,TypeError,OSError,IndexError) as error:
        report['status']='invalid_evidence'; report['error']=str(error)
        report['nativeInvoked']=getattr(error,'native_started',report['nativeInvoked'])
    atomic_json(out/'comparison.json',report)
    print(json.dumps(dict(status=report['status'],nativeInvoked=report['nativeInvoked'],report=str(out/'comparison.json'))))
    return 0 if report['status']=='passed' else 1 if report['status']=='failed_contract' else 2

if __name__=='__main__':
    raise SystemExit(main())
