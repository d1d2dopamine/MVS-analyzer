"""Round56 prospective outcome validation and exact fixed-denominator reports.

Read-only analysis. No generator, process launcher or scientific execution entry.
Synthetic bundles exercise the contract; they are never scientific evidence.
Native trace validation extends the unchanged Round50 observer contract.
"""
import math
import re
import json
from copy import deepcopy
from functools import lru_cache
import prospective_ademp as design
from variance_sensitivity import (decode_fp, member_state, family_state, expected_keys,
                                  validate_trace, timing, LEGACY_KEYS)

STATES = ("reject", "nonreject", "unavailable")
METHODS = [m["id"] for m in design.METHODS]
IDENTITY_FIELDS = ("protocol_id", "protocol_sha256", "purpose", "case_id", "cell_index",
                   "replication_zero_based", "native_seed", "entities_per_group",
                   "repeats_per_entity", "ordered_binary64_sha256")

def require(condition, message):
    if not condition:
        raise ValueError(message)

def validate_observations(observations):
    for event in observations:
        require(type(event) is dict and set(event) == {'Key','CallbackCount','Returned','Finite','Converged','AtBoundary','Value','Exception'}, 'callback fields')
        require(type(event['Returned']) is bool, 'callback return type')
        if not event['Returned']:
            require(event['Value'] is None and event['Exception'] is not None and
                    all(event[k] is None for k in ('Finite','Converged','AtBoundary')), 'failed callback diagnostics')
            continue
        require(event['Exception'] is None, 'returned callback exception')
        fit=event['Key'] == 'initial-fit' or event['Key'].startswith('interval/') or event['Key'].endswith('/null-fit')
        if fit:
            value=event['Value']
            require(type(value) is dict and set(value) == {'means','within','between','negativeLogLikelihood','converged','atBoundary','method','iterations'}, 'fit encoding fields')
            require(type(value['converged']) is bool and type(value['atBoundary']) is bool and
                    event['Converged'] is value['converged'] and event['AtBoundary'] is value['atBoundary'], 'fit diagnostic contradiction')
            numbers=[]
            for field in ('means','within','between'):
                require(type(value[field]) is list and len(value[field]) == 2, 'fit group dimensions')
                numbers.extend(decode_fp(x) for x in value[field])
            numbers.append(decode_fp(value['negativeLogLikelihood']))
            require(event['Finite'] is all(math.isfinite(x) for x in numbers), 'fit finite contradiction')
            require(type(value['iterations']) is int and value['iterations'] >= 0 and type(value['method']) is str, 'fit method diagnostics')
        else:
            require(event['Converged'] is None and event['AtBoundary'] is None and
                    event['Finite'] is math.isfinite(decode_fp(event['Value'])), 'scalar diagnostic contradiction')


def validate_payload(row, request, observations, tries):
    """Generalized Round50 callback checks; no native execution or data generation."""
    import prospective_cases as cases
    cases.validate_case(request)
    n = request["entities_per_group"]
    rows = 2 * n * request["repeats_per_entity"]
    require(row['kind']=='case_complete','expected completed case')
    payload=row['payload']
    require(type(payload) is dict and set(payload) == set(IDENTITY_FIELDS) | {'schema','rawRows','retainedRows','entities','groupCounts','report','legacy','trace','buildError','varianceError','legacyError','inputStatus'}, 'payload fields')
    require(payload['schema'] == 'mvs-prospective-case-payload/v1', 'payload schema')
    for key in IDENTITY_FIELDS:require(type(payload[key]) is type(request[key]) and payload[key]==request[key],'native payload identity mismatch: '+key)
    require(payload['rawRows']==rows,'native raw row count')
    require(all(t['hit'] is False for t in tries),'native restored state forbidden')
    validate_observations(observations)
    keys=[o['Key'] for o in observations];expected=expected_keys()
    require(len(keys)==len(set(keys)) and all(k in expected for k in keys),'unexpected/duplicate native callback key')
    require([expected.index(k) for k in keys]==sorted(expected.index(k) for k in keys),'callback order changed')
    require(all(type(o['CallbackCount']) is int and o['CallbackCount']==1 for o in observations),'native cache replay/callback duplication')
    trace=payload['trace'];require(trace['RestoreHits']==0 and trace['cachedRequests']==len(observations) and trace['callbackCount']==len(observations),'trace actual counts mismatch')
    validate_trace(trace,observations)
    for key in ('buildTiming','runTiming','legacyTiming'):
        if row[key] is not None:timing(row[key])
    states={'within':'unavailable','between':'unavailable','variance_family':'unavailable','summary_family':'unavailable','legacy_metrics':['unavailable']*12}
    if payload['inputStatus']=='retained_exactly':
        require(payload['buildError'] is None and (payload['retainedRows'],payload['entities'],payload['groupCounts'])==(rows,2*n,[n,n]),'native retention contradiction')
    else:
        require(payload['inputStatus']=='input_retention_mismatch' and payload['buildError'] is not None and payload['report'] is None and payload['legacy'] is None and not observations,'invalid failed-input evidence')
        require(trace['Begins'] == trace['Finishes'] == trace['Disposals'] == 0 and not tries, 'failed input invoked variance')
        return states
    report=payload['report']
    require((report is None)==(payload['varianceError'] is not None),'variance report/error mismatch')
    if report is None:
        # Begin, Try, Finish or Dispose can throw before Run returns its report.
        # These are unknown variance decisions, never partial successful evidence.
        require(all(type(trace[k]) is int and trace[k] in (0,1) for k in ('Begins','Finishes','Disposals')),
                'failed recording lifecycle counts')
        require(trace['Disposals'] <= trace['Begins'] and trace['Finishes'] <= trace['Begins'],
                'failed recording ownership')
        require(len(tries) <= 1 and all(t['key'] == 'result' for t in tries), 'failed restore attempt')
        require(not observations or trace['Begins'] == trace['Disposals'] == 1 and len(tries) == 1,
                'failed callback session ownership')
        require(not tries or trace['Begins'] == trace['Disposals'] == 1, 'failed restore ownership')
        require(not trace['Finishes'] or bool(observations) and len(tries) == 1, 'failed finish without preceding work')
    else:
        require(trace['Begins'] == trace['Finishes'] == trace['Disposals'] == 1 and
                len(tries) == 1 and tries[0]['key'] == 'result', 'successful recording ownership')
    if report is not None:
        require(payload['varianceError'] is None,'report and error contradiction')
        require(report['seed']==request['native_seed'] and decode_fp(report['alpha'])==.05,'report settings mismatch')
        require(report['engineVersion'] == '1.6.2', 'report engine identity')
        bykey={o['Key']:o for o in observations}
        require('initial-fit' in bykey and all(o['Returned'] for o in observations),'incomplete returned report trace')
        required=['initial-fit']+(['interval/'+str(i) for i in range(100)] if bykey['initial-fit']['Converged'] else [])
        tracks=report['tracks'];require(len(tracks)==2 and [t['track'] for t in tracks]==['within','between'],'variance track ordering mismatch')
        for tr in tracks:
            track=tr['track'];raw=decode_fp(tr['pValue']);adj=decode_fp(tr['adjustedP'])
            require((math.isnan(raw) and math.isnan(adj)) or (math.isfinite(raw) and 0<=raw<=1 and adj==min(1,2*raw)),'variance fixed-family adjustment mismatch')
            states[track]=member_state(adj)
            require(tr['verdict'] == ('difference' if adj < .05 else 'insufficient'), 'variance verdict mismatch')
            nullfit=bykey[track+'/null-fit'];observed=decode_fp(bykey[track+'/observed']['Value'])
            reference=[decode_fp(o['Value']) for o in observations if o['Key'].startswith(track+'/reference/')]
            require(tr['statistic'] == bykey[track+'/observed']['Value'], 'observed statistic mismatch')
            require(decode_fp(tr['effectSdMultiplier']) == 2, 'effect configuration')
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
        require(legacy['alpha'] == .05 and legacy['method'] == 'production Metrics/MannWhitneyP/DecisionPolicy.Adjust', 'summary method configuration')
        metric_states=[]
        for index,metric in enumerate(legacy['metrics']):
            require(type(metric['index']) is int and metric['index']==index and metric['key']==LEGACY_KEYS[index] and type(metric['applicable']) is bool,'legacy fixed slot mismatch')
            raw=decode_fp(metric['p']);adj=decode_fp(metric['adjustedP'])
            require((math.isnan(raw) and math.isnan(adj)) or (math.isfinite(raw) and 0<=raw<=1 and adj==min(1,12*raw)),'legacy fixed12 adjustment mismatch')
            state=member_state(adj);require(type(metric['reject']) is bool and metric['reject']==(state=='reject'),'legacy rejection mismatch')
            require(metric['applicable'] or state=='unavailable','unavailable metric has decision')
            require(all(type(metric[k]) is int for k in ('firstCount','secondCount')), 'summary usable count types')
            groups=metric['groupAvailability']
            require(len(groups)==2 and [g['Group'] for g in groups]==['G0','G1'],'legacy availability group order')
            require(all(type(g[k]) is int for g in groups for k in ('RetainedEntities','UsableEntities','ExcludedEntities')), 'summary count types')
            require(all(g['RetainedEntities']==n and 0<=g['UsableEntities']<=n and g['ExcludedEntities']==n-g['UsableEntities'] for g in groups),'legacy entity availability counts')
            require([g['UsableEntities'] for g in groups]==[metric['firstCount'],metric['secondCount']],'legacy observed usable counts')
            expected_status='available' if metric['applicable'] else 'insufficient_usable_entities' if any(g['UsableEntities']<4 for g in groups) else 'rank_test_unavailable'
            require(not metric['applicable'] or all(g['UsableEntities'] >= 4 for g in groups), 'minimum usable entities')
            require(metric['observedStatus']==expected_status and metric['applicable']==math.isfinite(raw),'legacy applicability/status mismatch')
            metric_states.append(state)
        states['legacy_metrics']=metric_states;states['summary_family']=family_state(metric_states)
        require(type(legacy['anyReject']) is bool and legacy['anyReject']==(states['summary_family']=='reject'),'legacy family rejection mismatch')
    return states


@lru_cache(maxsize=32768, typed=True)
def clopper_pearson(k, n, tail=.025):
    """Exact interval; tail is ONE-tail error, never a two-tail alpha."""
    from scipy.stats import beta
    require(type(k) is int and type(n) is int and 0 <= k <= n and n > 0, 'CP counts')
    require(type(tail) in (float, int) and 0 < tail < .5, 'CP tail')
    return (0. if k == 0 else float(beta.ppf(tail, k, n-k+1)),
            1. if k == n else float(beta.ppf(1-tail, k+1, n-k)))


def rate_summary(states, tail=.025):
    require(len(states) == 1000 and all(s in STATES for s in states), 'planned denominator/states')
    r, f = states.count('reject'), states.count('unavailable')
    n = 1000-f
    p = r/n if n else None
    return {'planned': 1000, 'known': n, 'reject': r, 'nonreject': n-r, 'unknown': f,
            'conditional_on_valid_rate': p,
            'conditional_on_valid_mcse': math.sqrt(p*(1-p)/n) if n else None,
            'conditional_on_valid_cp': list(clopper_pearson(r,n,tail)) if n else None,
            'failure_inclusive_rate_bounds': [r/1000, (r+f)/1000],
            'failure_inclusive_cp': [clopper_pearson(r,1000,tail)[0],
                                     clopper_pearson(r+f,1000,tail)[1]],
            'one_tail_error': tail}


def paired_summary(left, right):
    require(len(left) == len(right) == 1000 and all(s in STATES for s in left+right),
            'paired planned denominator/states')
    table = [[sum(a == x and b == y for a,b in zip(left,right)) for y in STATES] for x in STATES]
    n = sum(table[i][j] for i in (0,1) for j in (0,1))
    b,c,u = table[0][1], table[1][0], 1000-n
    conditional = None
    if n:
        lb,ub = clopper_pearson(b,n,.0125)
        lc,uc = clopper_pearson(c,n,.0125)
        conditional = [lb-uc,ub-lc]
    return {'planned':1000, 'complete_pairs':n, 'incomplete_pairs':u,
            'gaussian_only':b, 'summary_only':c,
            'state_order':list(STATES), 'paired_3x3':table,
            'conditional_on_complete_difference': (b-c)/n if n else None,
            'conditional_on_complete_conservative_95_interval':conditional,
            'failure_inclusive_difference_bounds':[(b-c-u)/1000,(b-c+u)/1000],
            'failure_inclusive_conservative_95_interval':[
                clopper_pearson(b,1000,.0125)[0]-clopper_pearson(c+u,1000,.0125)[1],
                clopper_pearson(b+u,1000,.0125)[1]-clopper_pearson(c,1000,.0125)[0]],
            'simultaneous_across_cells':False,
            'interpretation':'descriptive distinct-method nulls; no superiority gate'}


def _both(states):
    a,b = states['within'],states['between']
    return 'reject' if a == b == 'reject' else 'nonreject' if 'nonreject' in (a,b) else 'unavailable'


def aggregate_validated(records, config, *, allow_partial=False, evidence_role):
    """Aggregate normalized, already validated records; not a raw-envelope trust boundary.

    Call analyze_bundle for identity/trace checks. This numerical kernel also supports
    deliberately synthetic records for independently checked hand-count tests.
    """
    require(evidence_role in ('synthetic_contract_only', 'prospective_observed'), 'evidence role')
    import prospective_cases as cases
    require(config == cases.frozen_config(), 'frozen report design mismatch')
    cells = config['cells']
    require(config['outer_repetitions_per_cell'] == 1000 and len(cells) == 12, 'fixed design')
    nulls = design.null_endpoint_pairs(cells)
    require(len(nulls) == 31, 'fixed 31 null endpoints')
    by_id = {}
    for row in records:
        require(set(row) == {'case_id','cell_index','replication_zero_based','states'}, 'normalized fields')
        c,r = row['cell_index'],row['replication_zero_based']
        require(type(c) is int and 0 <= c < 12 and type(r) is int and 0 <= r < 1000, 'out-of-plan case')
        require(row['case_id'] == f'{design.PROTOCOL_ID}/C{c:02d}/R{r:04d}', 'case identity')
        require(row['case_id'] not in by_id, 'duplicate case')
        s = row['states']
        require(set(s) == {'within','between','variance_family','summary_family','legacy_metrics'}, 'endpoint fields')
        require(all(s[k] in STATES for k in ('within','between','variance_family','summary_family')), 'endpoint states')
        require(len(s['legacy_metrics']) == 12 and all(x in STATES for x in s['legacy_metrics']), 'summary states')
        require(s['variance_family'] == family_state([s['within'],s['between']]) and
                s['summary_family'] == family_state(s['legacy_metrics']), 'family state contradiction')
        by_id[row['case_id']] = row
    require(allow_partial or len(by_id) == 12000, 'missing planned cases; explicit allow_partial required')
    out=[]
    null_results=[]
    for cell in cells:
        states={key:[] for key in ('within','between','variance_family','summary_family','both_components')}
        attempted=0
        for r in range(1000):
            row=by_id.get(f'{design.PROTOCOL_ID}/{cell["id"]}/R{r:04d}')
            attempted += row is not None
            for key in states:
                states[key].append('unavailable' if row is None else _both(row['states']) if key == 'both_components' else row['states'][key])
        operating={key:rate_summary(states[key]) for key in ('variance_family','summary_family')}
        power={}
        for key,ids in config['inference']['alternative_endpoints'].items():
            endpoint={'within_component':'within','between_component':'between',
                      'both_components_correctly_detected':'both_components'}.get(key)
            if endpoint and cell['id'] in ids:
                power[key]=rate_summary(states[endpoint])
        paired=paired_summary(states['variance_family'],states['summary_family'])
        paired['negative_control_distinct_null_states'] = cell['id'] == 'C01'
        out.append({'cell_id':cell['id'], 'attempted':attempted,'unattempted':1000-attempted,
                    'truth':deepcopy(cell['truth']),'family_operating_outcomes':operating,
                    'target_detection':power,'paired_family_difference':paired})
        for null in (x for x in nulls if x['cell_id'] == cell['id']):
            item={**null,**rate_summary(states[null['endpoint']], .025/31)}
            item['inflation_status']='detected_inflation' if item['failure_inclusive_cp'][0] > null['nominal_alpha'] else 'inconclusive_not_validation'
            null_results.append(item)
    return {'schema':'mvs-prospective-report/v1', 'protocol_id':design.PROTOCOL_ID,
            'evidence_role':evidence_role, 'scientific_evidence':evidence_role != 'synthetic_contract_only',
            'status':'complete_attempt_accounting' if len(by_id) == 12000 else 'incomplete',
            'execution_ready':False,'scientific_acceptance':'not_assessed_no_go_gate',
            'planned_datasets':12000,'attempted_datasets':len(by_id), 'cells':out,
            'null_endpoint_count':31,'joint_bound_count':62,'joint_confidence_at_least':.95,
            'null_endpoints':null_results,
            'readiness_blockers':['generator/native orchestration not execution-frozen',
                                  'resource admission and authorized study execution required']}


def _sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_provenance(actual, expected, root=design.ROOT):
    """Compare to caller's frozen build/runtime identity and current source bytes."""
    require(type(expected) is dict and set(expected) == {'identity','adapterSourceSha256','configSha256','adapterScope'}, 'expected provenance schema')
    require(actual == expected, 'source/binary/runtime provenance mismatch')
    import prospective_cases as cases
    require(expected['configSha256'] == cases.PROTOCOL_SHA256 and
            expected['adapterScope'] == 'test_only_general_case_seam_no_study_admission', 'provenance protocol/scope')
    identity=expected['identity']
    require(type(identity) is dict and identity.get('experimental') is True, 'native identity missing')
    source=identity.get('sourceSha256',{})
    require(type(source) is dict and len(source) == 14, 'native source bindings')
    adapters=expected['adapterSourceSha256']
    require(set(adapters) == {'validation/prospective_case_adapter/Program.cs',
                              'validation/prospective_case_adapter/ProspectiveCaseAdapter.csproj'}, 'adapter source bindings')
    for path,sha in {**source,**adapters}.items():
        require(_sha(sha) and design.sha256_file(design.local_file(root,path)) == sha, 'source hash drift: '+path)
    for assembly in ('harnessAssembly','coreAssembly'):
        require(_sha(identity.get(assembly,{}).get('sha256')), 'binary hash missing')
    require(_sha(identity.get('runtime',{}).get('coreLibrarySha256')), 'runtime hash missing')


def validate_native_result(envelope, raw_request, expected_provenance, observations, tries,
                           exit_code, *, root=design.ROOT):
    """Fail closed on mismatched identities, partial success, counts, p-values and exits."""
    import hashlib
    import prospective_cases as cases
    request=cases.loads(raw_request)
    require(type(envelope) is dict and set(envelope) == {'schema','protocol_id','protocol_sha256','methods','kind','mode','requestSha256','operationCounts','operationCountScope','provenance','payload','buildTiming','runTiming','legacyTiming','completed','status','scientificStudyExecuted','caseWallSeconds','processTotalCpuSeconds','processPeakWorkingSetBytes','serializedUtf8Bytes'}, 'result fields')
    require(type(exit_code) is int and exit_code == 0, 'nonzero/missing process exit is not successful evidence')
    require(envelope['schema'] == 'mvs-prospective-case-result/v1' and
            envelope['protocol_id'] == design.PROTOCOL_ID and
            envelope['protocol_sha256'] == cases.PROTOCOL_SHA256, 'result schema/protocol')
    require(envelope['methods'] == METHODS, 'method identity mismatch')
    require(envelope['kind'] == 'case_complete' and envelope['completed'] is True, 'partial native result')
    require(envelope['mode'] == 'run-case' and
            envelope['requestSha256'] == hashlib.sha256(raw_request).hexdigest(), 'request byte identity')
    require(envelope['scientificStudyExecuted'] is (request['purpose'] == 'planned_case'), 'purpose contradiction')
    validate_provenance(envelope['provenance'],expected_provenance,root)
    states=validate_payload(envelope,request,observations,tries)
    payload=envelope['payload']
    expected_status=('input_unavailable' if payload['buildError'] is not None else
                     'paired_method_failure_retained' if payload['varianceError'] is not None or payload['legacyError'] is not None
                     else 'paired_methods_returned')
    require(envelope['status'] == expected_status, 'completion status contradiction')
    require(envelope['operationCountScope'] == 'adapter_entry_calls_only_nested_production_calls_not_instrumented', 'operation count scope')
    counts=envelope['operationCounts']
    require(set(counts) == {'fixtureMaterializationCount','buildCallCount','runCallCount','legacyCallCount',
                           'payloadSerializationCount','directGenerateCallCount','directFitCallCount'} and
            all(type(v) is int for v in counts.values()), 'operation count schema')
    require(counts['fixtureMaterializationCount'] == counts['directGenerateCallCount'] == counts['directFitCallCount'] == 0 and
            counts['payloadSerializationCount'] == 1 and counts['buildCallCount'] in (0,1), 'unexpected direct work')
    calls=int(payload['inputStatus'] == 'retained_exactly')
    require(counts['runCallCount'] == counts['legacyCallCount'] == calls, 'paired route attempt count')
    return states


def analyze_bundle(bundle, expected_provenance, *, root=design.ROOT, allow_partial=False):
    """Read-only report contract. Execution permission is deliberately not implemented.

    Each attempt retains raw request bytes and native trace. Process failures require
    retained artifact hashes and are counted unknown; they cannot carry decisions.
    """
    import prospective_cases as cases
    require(type(bundle) is dict and set(bundle) == {'schema','protocol_sha256','methods','evidence_role','attempts'}, 'bundle schema')
    require(bundle['schema'] == 'mvs-prospective-outcome-bundle/v1' and
            bundle['protocol_sha256'] == cases.PROTOCOL_SHA256 and bundle['methods'] == METHODS, 'bundle identity')
    require(bundle['evidence_role'] in ('synthetic_contract_only','prospective_observed'), 'bundle evidence role')
    config,check=design.load_config(design.local_file(root,design.CONFIG_PATH),root)
    require(check['config_sha256'] == cases.PROTOCOL_SHA256, 'frozen config hash')
    validate_provenance(expected_provenance,expected_provenance,root)
    normalized=[]
    for attempt in bundle['attempts']:
        require(type(attempt) is dict and set(attempt) == {'request_json','exit_code','status','result','observations','tries','failure','artifact_sha256'}, 'attempt schema')
        require(type(attempt['request_json']) is str, 'retained request text')
        raw=attempt['request_json'].encode('utf-8')
        request=cases.loads(raw)
        require(request['purpose'] == 'planned_case', 'engineering literals cannot enter planned report')
        require(type(attempt['artifact_sha256']) is dict and set(attempt['artifact_sha256']) == {'stdout','stderr'} and
                all(_sha(v) for v in attempt['artifact_sha256'].values()), 'retained raw artifact hashes')
        if attempt['status'] == 'native_complete':
            require(attempt['failure'] is None, 'success/failure contradiction')
            states=validate_native_result(attempt['result'],raw,expected_provenance,attempt['observations'],
                                          attempt['tries'],attempt['exit_code'],root=root)
        else:
            require(attempt['status'] in ('process_failed','timeout','launch_failed'), 'attempt status')
            require(attempt['result'] is None and type(attempt['failure']) is str and bool(attempt['failure']), 'failed attempt cannot carry successful result')
            require(attempt['exit_code'] is None or type(attempt['exit_code']) is int and attempt['exit_code'] != 0, 'failed exit contradiction')
            states={k:'unavailable' for k in ('within','between','variance_family','summary_family')}
            states['legacy_metrics']=['unavailable']*12
        normalized.append({'case_id':request['case_id'],'cell_index':request['cell_index'],
                           'replication_zero_based':request['replication_zero_based'],'states':states})
    report=aggregate_validated(normalized,config,allow_partial=allow_partial,evidence_role=bundle['evidence_role'])
    report['retained_attempts']=deepcopy(bundle['attempts'])
    report['protocol_sha256']=cases.PROTOCOL_SHA256
    report['methods']=METHODS[:]
    report['provenance']=deepcopy(expected_provenance)
    return report
