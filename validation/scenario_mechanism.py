#!/usr/bin/env python3
"""Round47 deterministic mechanism diagnostic, independent reference and bounded driver.

No random draws, calibration, method selection or production changes. Retained
execution needs a reviewed immutable binding and a passed real-native synthetic
run through the same loader, worker, verifier and process supervisor.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import time

import scipy
import numpy
from scipy.stats import norm
import paired_calibration_trace as trace
import paired_candidate_comparison as bounded

METRICS = list(trace.METRICS)
TRACKS = ['location', 'variability', 'heterogeneity']
CONDITIONS = ['identity', *TRACKS]
NATURAL = {'location': [0, 7, 10, 11], 'variability': [1, 2, 3, 4, 5, 6, 9], 'heterogeneity': [0, 7, 10, 11]}
EFFECT, ALPHA, FAMILY = 1.15, .05, 12
ABS_TOL, REL_TOL, POLY_TOL, TAIL_TOL = 1e-12, 1e-10, 1e-12, 2e-7
PLAN_SHA = '72e3696c2973c09ce9ad88630bc153edca3f6c1e01d0f632ceafd0365332bb4e'
DOCUMENT_SHA = 'e78bd68ce8f7f4531049089118c2f0eb3bb510c4b7a94e36607c2216c121a6c6'
LIMITS = dict(bounded.LIMITS)
COUNTS = {'cases': 120, 'halves': 240, 'half_condition_blocks': 960, 'entity_condition_vectors': 15360,
          'observation_values': 614400, 'metric_rank_records': 11520,
          'historical_count_cells': 11520, 'audited_historical_symbols': 20160000}
BIND_SCHEMA = 'mvs-scenario-mechanism-bind/v1'
require, digest, read_json, bits = trace.require, trace.digest, trace.read_json, trace.bits
write_json, utc = bounded.write_json, bounded.utc
BASE_OUTPUTS = ['bind.json', 'bind.sha256', 'protocol.json', 'protocol.md', 'run-start.json', 'run.json',
                'resources.json', 'cleanup.json', 'failure.json', 'file-manifest.json', 'post-run-pins.json',
                'toy-native.json', 'toy-reference.json', 'summaries.json', 'historical-context.jsonl.gz',
                'independent-audit.json', 'worker.stdout.log', 'worker.stderr.log', 'verifier.stdout.log',
                'verifier.stderr.log', 'postpins.stdout.log', 'postpins.stderr.log', 'toys.stdout.log', 'toys.stderr.log', 'synthetic-input.json', 'native-inspect.json',
                'synthetic-input.stdout.log', 'synthetic-input.stderr.log', 'inspect.stdout.log', 'inspect.stderr.log']


def fraction(value):
    value = F(value)
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def mean(values):
    return math.fsum(values) / len(values) if values else math.nan


def variance(values):
    if len(values) < 2:
        return math.nan
    center = mean(values)
    return math.fsum((x-center)**2 for x in values) / (len(values)-1)


def quantile(values, q):
    require(values and 0 <= q <= 1, 'nonempty quantile input required')
    ordered = sorted(values)
    position = (len(ordered)-1)*q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high]-ordered[low])*(position-low)


def value_class(value):
    return 'NaN' if math.isnan(value) else 'Infinity' if value == math.inf else '-Infinity' if value == -math.inf else 'finite'


def nullable(value):
    return value if math.isfinite(value) else None


def close(actual, expected, absolute=ABS_TOL, relative=REL_TOL):
    return value_class(actual) == value_class(expected) and (not math.isfinite(actual) or abs(actual-expected) <= absolute+relative*abs(expected))


def metric_reference(values):
    """Independent formulas using compensated sums; never native expected values."""
    if not values:
        return [math.nan]*12
    ordered = sorted(values)
    center, med = mean(values), quantile(values, .5)
    sd = math.sqrt(variance(values))
    mad = quantile([abs(x-med) for x in values], .5)
    iqr = quantile(values, .75)-quantile(values, .25)
    tolerance = max(float.fromhex('0x0.0000000000001p-1022'), max(map(abs, values))*1e-12)
    trim = math.floor(.2*len(values))
    return [med, sd, sd/abs(center) if abs(center)>tolerance else math.nan,
            mad, iqr, mad/abs(med) if abs(med)>tolerance else math.nan,
            iqr/abs(med) if abs(med)>tolerance else math.nan, center,
            math.sqrt(mean([x*x for x in values])), ordered[-1]-ordered[0],
            math.exp(mean([math.log(x) for x in values])) if min(values)>0 else math.nan,
            mean(ordered[trim:len(values)-trim])]


def requirement_reason(metric, values):
    if len(values)<2:
        return 'too_few_measurements'
    if not all(math.isfinite(x) for x in values):
        return 'nonfinite_measurements'
    tolerance = max(float.fromhex('0x0.0000000000001p-1022'), max(map(abs, values))*1e-12)
    if metric == 'geometric_mean' and min(values)<=0:
        return 'nonpositive_measurements'
    if metric == 'coefficient_of_variation' and abs(mean(values))<=tolerance:
        return 'near_zero_mean'
    if metric in ('normalized_mad','normalized_iqr') and abs(quantile(values,.5))<=tolerance:
        return 'near_zero_median'
    return None


def transform_reference(values, condition, center, scale, effect=EFFECT):
    require(condition in CONDITIONS, 'unknown condition')
    if condition == 'identity':
        return list(values)  # preserve original binary64, including signed zero
    local = mean(values)
    if condition == 'location':
        return [x+scale*(effect-1) for x in values]
    if condition == 'variability':
        return [local+effect*(x-local) for x in values]
    return [center+effect*(local-center)+(x-local) for x in values]


def normal_polynomial(z):
    """Published A&S 26.2.17 order, a consistency check, not the tail oracle."""
    t = 1/(1+.2316419*abs(z))
    density = math.exp(-z*z/2)/math.sqrt(2*math.pi)
    cdf = 1-density*t*(.319381530+t*(-.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))))
    return max(0., min(1., 2*(1-cdf)))


def rank_reference(a, b, minimum=0):
    """Exact cross-pair U, exact tie integers, independent of sorting rank sums.

    Inputs are emitted native entity summaries for native-p parity. This does
    not observe internal native ranks/z or reinterpret near-equal binary64s.
    """
    require(all(math.isfinite(x) for x in [*a,*b]), 'finite rank inputs required')
    na, nb = len(a), len(b)
    base = {'n_a':na, 'n_b':nb, 'u2':None, 'u':None, 'ordering_probability':None,
            'tie_block_sizes':None, 'tie_correction_sum':None, 'variance':None,
            'variance_exact':None, 'z':None, 'polynomial_p':None, 'erfc_p':None,
            'scipy_p':None, 'reference_adjusted_p':None, 'reference_reject':None,
            'available':False, 'unavailable_reason':None}
    if not na or not nb or min(na,nb)<minimum:
        base['unavailable_reason'] = 'insufficient_usable_entities' if minimum else 'empty_group'
        return base
    u2 = sum(2*(y>x)+(y==x) for x in a for y in b)
    blocks = [count for _,count in sorted(Counter([*a,*b]).items())]
    tie_sum = sum(t**3-t for t in blocks)
    n = na+nb
    exact_variance = F(na*nb,12)*(n+1-F(tie_sum,n*(n-1)))
    v = float(exact_variance)
    # Native formula's binary64 ordering is preserved for polynomial parity;
    # exact rational variance is recorded independently beside it.
    native_order_v = na*nb/12*((n+1)-tie_sum/(n*(n-1)))
    z = max(0., (abs(u2/2-na*nb/2)-.5)/math.sqrt(native_order_v)) if v>0 else 0.
    erfc_p = math.erfc(z/math.sqrt(2)) if v>0 else 1.
    scipy_p = float(2*norm.sf(z)) if v>0 else 1.
    require(abs(erfc_p-scipy_p)<=2e-15, 'independent normal tail references disagree')
    base.update(u2=u2, u=u2/2, ordering_probability=u2/(2*na*nb), tie_block_sizes=blocks,
                tie_correction_sum=tie_sum, variance=native_order_v, variance_exact=fraction(exact_variance),
                z=z, polynomial_p=normal_polynomial(z) if v>0 else 1., erfc_p=erfc_p,
                scipy_p=scipy_p, reference_adjusted_p=min(1.,12*scipy_p),
                reference_reject=min(1.,12*scipy_p)<.05, available=True)
    return base


class Audit:
    def __init__(self):
        self.checked = 0
        self.errors = []
        self.maximum_absolute_error = 0.

    def exact(self, actual, expected, path):
        self.checked += 1
        if not trace.exact_tree(actual,expected):
            self.errors.append({'path':path,'actual':actual,'expected':expected,'kind':'exact'})

    def number(self, actual, expected, path, absolute=ABS_TOL, relative=REL_TOL):
        self.checked += 1
        if expected is None:
            if actual is not None:
                self.errors.append({'path':path,'actual':actual,'expected':None,'kind':'availability'})
            return
        actual_number = math.nan if actual is None else actual
        if math.isfinite(expected) and isinstance(actual_number,(int,float)) and math.isfinite(actual_number):
            self.maximum_absolute_error = max(self.maximum_absolute_error,abs(actual_number-expected))
        if not isinstance(actual_number,(int,float)) or not close(actual_number,expected,absolute,relative):
            self.errors.append({'path':path,'actual':actual,'expected':nullable(expected),
                                'expected_class':value_class(expected),'absolute_tolerance':absolute,
                                'relative_tolerance':relative,'kind':'numeric'})

    def record(self):
        return {'checked':self.checked,'maximum_absolute_error':self.maximum_absolute_error,
                'errors':self.errors,'valid':not self.errors}


def audit_metrics(row, expected_values, audit, path):
    audit.exact(row['measurements'],len(expected_values),path+'.measurements')
    require(len(row['values'])==len(expected_values),'raw vector dimension '+path)
    for i,(a,b) in enumerate(zip(row['values'],expected_values)):
        audit.number(a,b,f'{path}.values[{i}]')
    expected = metric_reference(expected_values)
    require(len(row['metrics'])==len(row['metric_availability'])==12,'metric vector dimension '+path)
    for i,(metric,ref,value,availability) in enumerate(zip(METRICS,expected,row['metrics'],row['metric_availability'])):
        reason = '' if math.isfinite(ref) else requirement_reason(metric,expected_values) or 'nonfinite_metric_value'
        audit.number(value,ref,f'{path}.metrics[{i}]')
        audit.exact(availability,{'metric':metric,'available':math.isfinite(ref),'reason':reason,
                                 'nonfinite_class':value_class(ref)},f'{path}.availability[{i}]')
    audit.number(row['mean'],mean(expected_values),path+'.mean')
    audit.number(row['sample_variance'],variance(expected_values),path+'.sample_variance')
    audit.number(row['within_sd'],math.sqrt(variance(expected_values)),path+'.within_sd')
    return expected


def load_source(source, index, expected_sha, synthetic=False):
    source=Path(source)
    require(source.is_file() and digest(source)==expected_sha,'retained input hash mismatch')
    payload=read_json(source)
    require(payload['index']==index and payload['status']=='completed','incomplete or wrong-index input')
    require(payload['metric_order']==METRICS,'reordered metric list')
    require(payload['settings']['effect']==EFFECT and payload['settings']['alpha']==ALPHA and
            payload['settings']['repetitions']==1000 and payload['settings']['missing_rate']==0 and
            payload['settings']['outlier_rate']==.02 and payload['settings']['tracks']==TRACKS,'settings mismatch')
    if not synthetic:
        require(payload['schema']=='mvs-stability-replay-case/v1' and payload['diagnostics_status']=='retained','unretained input')
    halves={}
    for side in ('left','right'):
        require(side in payload['data'],'missing half '+side)
        data=payload['data'][side]
        canonical=data['canonical_json']
        require(type(canonical) is str and hashlib.sha256(canonical.encode()).hexdigest()==data['sha256'],'canonical hash mismatch '+side)
        parsed=trace.parse_json(canonical)
        require(trace.exact_tree(parsed,data['values']),'canonical value binding mismatch '+side)
        names=parsed['group_names']
        require(len(names)==2 and len(set(g.casefold() for g in names))==2,'two distinct groups required')
        entities=parsed['entities']
        require(len(entities)==16,'wrong entity count')
        keys=[(e['group'].casefold(),e['entity'].casefold()) for e in entities]
        require(len(set(keys))==16,'duplicate entity')
        groups={g.casefold():[] for g in names}
        vectors={key:[] for key in keys}
        for observation in parsed['observations']:
            key=(observation['group'].casefold(),observation['entity'].casefold())
            require(key in vectors,'observation outside original membership')
            value=observation['value']
            require(type(value) in (int,float) and math.isfinite(value),'nonfinite observation')
            vectors[key].append(value)
        rows=[]
        for e,key in zip(entities,keys):
            require(key[0] in groups,'entity outside group order')
            groups[key[0]].append(e)
            require(e['measurements']==len(vectors[key])==40,'wrong measurement count')
            require(len(e['metrics'])==12,'stored metric dimensions')
            rows.append({'entity':e['entity'],'group':e['group'],'values':vectors[key],'stored_metrics':e['metrics']})
        require(all(len(v)==8 for v in groups.values()),'wrong group entity count')
        require(len(parsed['observations'])==640 and parsed['total_entities']==16,'half dimensions')
        halves[side]={'canonical_data_sha256':data['sha256'],'group_order':names,'entities':rows,'data':parsed}
    return payload,halves


def audit_rank(native, metric_index, condition, expected_groups, audit, path):
    audit.exact(native['metric'],METRICS[metric_index],path+'.metric')
    audit.exact(native['natural_family'],metric_index in NATURAL.get(condition,[]),path+'.natural_family')
    audit.exact(native['group_values'],expected_groups,path+'.group_values')
    ref=rank_reference(*expected_groups,minimum=4)
    for key in ('n_a','n_b','available','unavailable_reason'):
        audit.exact(native[key],ref[key],path+'.'+key)
    p=native['native_p']
    if ref['available']:
        audit.number(p,ref['polynomial_p'],path+'.polynomial_p',POLY_TOL,0)
        audit.number(p,ref['scipy_p'],path+'.scipy_p',TAIL_TOL,0)
        audit.exact(native['native_adjusted_p'],min(1.,12*p),path+'.native_adjusted_p')
        audit.exact(native['native_reject'],min(1.,12*p)<.05,path+'.native_reject')
    else:
        for key in ('native_p','native_adjusted_p','native_reject'):
            audit.exact(native[key],None,path+'.'+key)
    return {**ref,'metric':METRICS[metric_index],'natural_family':native['natural_family'],
            'native_p':p,'native_adjusted_p':native['native_adjusted_p'],'native_reject':native['native_reject'],
            'native_reference_decision_disagreement':ref['available'] and native['native_reject']!=ref['reference_reject'],
            'rank_input_origin':'exact emitted native metric binary64 values; U/ties/z independently reconstructed'}


def validate_nonfinite_fields(native,audit):
    expected={}
    for hi,half in enumerate(native['halves']):
        collections=[(f'halves[{hi}].entities',half['entities'])]
        collections.extend((f'halves[{hi}].conditions[{ci}].entities',block['entities']) for ci,block in enumerate(half['conditions']))
        for prefix,entities in collections:
            for ei,row in enumerate(entities):
                for mi,value in enumerate(metric_reference(row['values'])):
                    if not math.isfinite(value):expected[f'{prefix}[{ei}].metrics[{mi}]']=value_class(value)
                for name,value in [('mean',mean(row['values'])),('sample_variance',variance(row['values'])),('within_sd',math.sqrt(variance(row['values'])))]:
                    if not math.isfinite(value):expected[f'{prefix}[{ei}].{name}']=value_class(value)
        for ci,block in enumerate(half['conditions']):
            for mi,rank in enumerate(block['ranks']):
                if not rank['available']:
                    for field in ('native_p','native_adjusted_p'):expected[f'halves[{hi}].conditions[{ci}].ranks[{mi}].{field}']='NaN'
    observed={}
    for row in native['nonfinite_fields']:
        require(set(row)=={'path','value'} and row['value'] in ('NaN','Infinity','-Infinity'),'invalid nonfinite metadata')
        require(row['path'] not in observed,'duplicate nonfinite path')
        observed[row['path']]=row['value']
    audit.exact(observed,expected,'nonfinite_fields_path_class_map')


def audit_case(native, source, index, source_sha, freeze_sha, synthetic=False, expected_identity=None, expected_settings=None):
    payload,halves=load_source(source,index,source_sha,synthetic)
    audit=Audit()
    audit.exact(native['index'],index,'index')
    audit.exact(native['status'],'completed','status')
    audit.exact(native['synthetic'],synthetic,'synthetic')
    audit.exact(native['source_input'],str(Path(source).resolve()),'source_input')
    audit.exact(native['source_input_sha256'],source_sha,'source_input_sha256')
    audit.exact(native['freeze_sha256'],freeze_sha,'freeze_sha256')
    audit.exact(native['metric_order'],METRICS,'metric_order')
    audit.exact(native['conditions'],CONDITIONS,'conditions')
    audit.exact(native['schema'],'mvs-scenario-mechanism-case/v1','schema')
    if expected_identity is not None:audit.exact(native['identity'],expected_identity,'identity')
    if expected_settings is not None:audit.exact(native['settings'],expected_settings,'settings')
    require(len(native['halves'])==2,'missing native half')
    report=[]
    for side,half in zip(('left','right'),native['halves']):
        original=halves[side]; rows=original['entities']; names=original['group_order']
        audit.exact(half['side'],side,side+'.side')
        audit.exact(half['canonical_data_sha256'],original['canonical_data_sha256'],side+'.canonical_data_sha256')
        audit.exact(half['build_verified'],True,side+'.build_verified')
        audit.exact(half['group_order'],names,side+'.group_order')
        audit.exact(half['group_counts'],[8,8],side+'.group_counts')
        local_means=[mean(e['values']) for e in rows]
        c=mean(local_means)
        h=max(abs(c),math.sqrt(mean([variance(e['values']) for e in rows])))
        if not math.isfinite(h) or h<=0:
            h=1.
        audit.number(half['pool_center'],c,side+'.pool_center')
        audit.number(half['shift_scale'],h,side+'.shift_scale')
        group_means=[mean([mean(e['values']) for e in rows if e['group'].casefold()==g.casefold()]) for g in names]
        for j,value in enumerate(group_means):
            audit.number(half['original_group_means'][j],value,f'{side}.original_group_means[{j}]')
        audit.number(half['original_group_mean_difference'],group_means[1]-group_means[0],side+'.original_group_mean_difference')
        require(len(half['entities'])==16 and len(half['conditions'])==4,'native half dimension')
        for j,(observed,original_row) in enumerate(zip(half['entities'],rows)):
            audit.exact(observed['entity'],original_row['entity'],f'{side}.entities[{j}].entity')
            audit.exact(observed['group'],original_row['group'],f'{side}.entities[{j}].group')
            audit.exact(observed['values'],original_row['values'],f'{side}.entities[{j}].original_bits')
            audit.exact(observed['metrics'],original_row['stored_metrics'],f'{side}.entities[{j}].original_stored_metric_bits')
            audit_metrics(observed,original_row['values'],audit,f'{side}.entities[{j}]')
        condition_reports=[]
        for condition,block in zip(CONDITIONS,half['conditions']):
            effect=1. if condition=='identity' else EFFECT
            path=side+'.'+condition
            audit.exact(block['condition'],condition,path+'.condition')
            audit.exact(block['effect'],effect,path+'.effect')
            require(len(block['entities'])==16 and len(block['groups'])==2 and len(block['ranks'])==12,'condition dimensions')
            transformed=[]
            for j,(native_row,original_row) in enumerate(zip(block['entities'],rows)):
                affected=original_row['group'].casefold()==names[-1].casefold()
                before=original_row['values']
                expected=transform_reference(before,condition if affected else 'identity',c,h,effect)
                transformed.append(expected)
                ep=f'{path}.entities[{j}]'
                audit.exact(native_row['entity'],original_row['entity'],ep+'.entity')
                audit.exact(native_row['group'],original_row['group'],ep+'.group')
                if not affected or condition=='identity':
                    audit.exact(native_row['values'],before,ep+'.unchanged_bits')
                audit_metrics(native_row,expected,audit,ep)
                original_metrics=metric_reference(before)
                target_mean=mean(before)
                if affected and condition=='location':target_mean+=h*(effect-1)
                if affected and condition=='heterogeneity':target_mean=c+effect*(target_mean-c)
                audit.number(native_row['mean'],target_mean,ep+'.analytic_mean')
                multiplier=effect if affected and condition=='variability' else 1.
                audit.number(native_row['sample_variance'],variance(before)*multiplier**2,ep+'.analytic_variance')
                for metric_index in (1,3,4,9):
                    audit.number(native_row['metrics'][metric_index],original_metrics[metric_index]*multiplier,ep+'.analytic_'+METRICS[metric_index])
                if affected and condition=='variability':
                    target_median=mean(before)+effect*(original_metrics[0]-mean(before))
                    audit.number(native_row['metrics'][0],target_median,ep+'.analytic_median')
                    tolerance=max(float.fromhex('0x0.0000000000001p-1022'),max(map(abs,expected))*1e-12)
                    for mi,spread in ((5,3),(6,4)):
                        target=effect*original_metrics[spread]/abs(target_median) if abs(target_median)>tolerance else math.nan
                        audit.number(native_row['metrics'][mi],target,ep+'.transformed_median_denominator_'+METRICS[mi])
                elif affected and condition in ('location','heterogeneity'):
                    shift=h*(effect-1) if condition=='location' else (effect-1)*(mean(before)-c)
                    for mi in (0,11):
                        audit.number(native_row['metrics'][mi],original_metrics[mi]+shift,ep+'.translation_'+METRICS[mi])
            geometry=[]
            for group_index,group in enumerate(names):
                selected=[j for j,e in enumerate(rows) if e['group'].casefold()==group.casefold()]
                original_centers=[local_means[j] for j in selected]
                observed_centers=[block['entities'][j]['mean'] for j in selected]
                average=mean(observed_centers); v=variance(observed_centers)
                expected_average=group_means[group_index]
                expected_variance=variance(original_centers)
                if group_index==1 and condition=='location':expected_average+=h*(effect-1)
                if group_index==1 and condition=='heterogeneity':
                    expected_average+=(effect-1)*(group_means[group_index]-c)
                    expected_variance*=effect**2
                audit.exact(block['groups'][group_index]['group'],group,f'{path}.groups[{group_index}].group')
                audit.number(block['groups'][group_index]['entity_mean_average'],average,f'{path}.groups[{group_index}].mean')
                audit.number(block['groups'][group_index]['entity_mean_variance'],v,f'{path}.groups[{group_index}].variance')
                audit.number(average,expected_average,f'{path}.groups[{group_index}].analytic_mean')
                audit.number(v,expected_variance,f'{path}.groups[{group_index}].analytic_variance')
                geometry.append({'group':group,'entity_mean_average':average,'entity_mean_variance':v,
                                 'expected_average':expected_average,'expected_variance':expected_variance,
                                 'mean_shift_from_identity':average-group_means[group_index]})
            ranks=[]
            for mi,rank in enumerate(block['ranks']):
                groups=[[e['metrics'][mi] for e in block['entities'] if e['group'].casefold()==g.casefold() and e['metrics'][mi] is not None] for g in names]
                ranks.append(audit_rank(rank,mi,condition,groups,audit,f'{path}.ranks[{mi}]'))
            difference=geometry[1]['entity_mean_average']-geometry[0]['entity_mean_average']
            original_difference=group_means[1]-group_means[0]
            predicted_difference=original_difference+(h*(effect-1) if condition=='location' else 0.)
            if condition=='heterogeneity':predicted_difference=(1+effect)/2*original_difference
            audit.number(difference,predicted_difference,path+'.analytic_group_mean_difference')
            condition_reports.append({'condition':condition,'geometry':geometry,'ranks':ranks,
                'original_group_mean_difference':original_difference,'transformed_group_mean_difference':difference,
                'predicted_group_mean_difference':predicted_difference})
        baseline=condition_reports[0]['ranks']
        for block in condition_reports:
            for rank,identity in zip(block['ranks'],baseline):
                available=rank['available'] and identity['available']
                rank['paired_from_identity']={'available':available,
                    'ordering_probability_delta':rank['ordering_probability']-identity['ordering_probability'] if available else None,
                    'native_p_delta':rank['native_p']-identity['native_p'] if available else None,
                    'decision_change':'gain' if available and rank['native_reject'] and not identity['native_reject'] else
                                      'loss' if available and identity['native_reject'] and not rank['native_reject'] else
                                      'unchanged' if available else 'unavailable'}
        report.append({'side':side,'pool_center':c,'shift_scale':h,'group_order':names,'conditions':condition_reports})
    validate_nonfinite_fields(native,audit)
    return {'schema':'mvs-scenario-mechanism-reference-case/v1','index':index,'synthetic':synthetic,
            'source_sha256':source_sha,'halves':report,'audit':audit.record()}


def exact_toys():
    """27 rational nuisance states; no simulation or random generator."""
    raw=[F(-1),F(0),F(1)]; effect=F(23,20)
    def exact_variance(values):
        center=sum(values,F(0))/len(values)
        return sum(((x-center)**2 for x in values),F(0))/(len(values)-1)
    states=[]; expected_null=F(0); expected_alt=F(0); total=F(0)
    choices=[(F(-5),F(1,100)),(F(0),F(98,100)),(F(5),F(1,100))]
    for parts in itertools.product(choices,repeat=3):
        increments=[v for v,_ in parts]; weight=math.prod(p for _,p in parts)
        vn=exact_variance([x+z for x,z in zip(raw,increments)])
        va=exact_variance([effect*x+z for x,z in zip(raw,increments)])
        total+=weight;expected_null+=weight*vn;expected_alt+=weight*va
        states.append({'increments':[int(x) for x in increments],'weight':fraction(weight),'null_variance':fraction(vn),'alternative_variance':fraction(va)})
    require(len(states)==27 and total==1 and expected_null==F(3,2) and expected_alt==F(729,400) and expected_alt/expected_null==F(243,200),'exact contamination oracle failed')
    offsets=[-7,-5,-3,-1,1,3,5,7]
    blind=rank_reference(offsets,[2*x for x in offsets]);require(blind['u2']==64 and blind['z']==0,'symmetric rank blind spot')
    boundaries=[]
    # A=1..8; B's first value determines three/four pair wins, others win all.
    for target,first in ((59,3.5),(60,4.5)):
        rank=rank_reference(list(range(1,9)),[first,*range(9,16)])
        require(rank['u']==target and rank['reference_reject']==(target==60),'n8 decision boundary')
        boundaries.append({'u':target,**rank})
    return {'schema':'mvs-scenario-mechanism-exact-toys/v1','states':states,'weight_sum':fraction(total),
            'expected_variance_null':fraction(expected_null),'expected_variance_alternative':fraction(expected_alt),
            'expected_variance_ratio':fraction(expected_alt/expected_null),'sd_equivalent':math.sqrt(float(expected_alt/expected_null)),
            'sd_equivalent_meaning':'sqrt(expected variance ratio), not ratio of expected sample SDs or a power result',
            'floor_aware_formula':'E_Z[S_f^2]=f^2*s^2+25*q*max(s,1e-12)^2; missing=0',
            'heterogeneity_blindspot':blind,'n8_boundary':boundaries}


def audit_native_toys(native):
    audit=Audit(); exact=exact_toys()
    require(native['schema']=='mvs-scenario-mechanism-self-test/v1' and native['status']=='passed' and native['test_count']==len(native['tests'])==10 and len(set(native['tests']))==10,'native self-test status/count')
    require(native['metric_order']==METRICS and native['calibration_executed'] is False and native['random_draws']==0,'native self-test scope')
    fixtures=native['rank_fixtures'];require(len(fixtures)==8,'duplicate/missing native rank fixture');require({r['id'] for r in fixtures}=={'u59','u60','heterogeneity_blindspot','location','all_ties','empty','repeated_ties','repeated_ties_swapped'},'native rank toy universe')
    for row in fixtures:
        ref=rank_reference(row['a'],row['b']);path='rank.'+row['id']
        p=row['p']
        audit.exact(row['p_class'],'finite' if ref['available'] else 'NaN',path+'.class')
        if ref['available']:
            audit.number(p,ref['polynomial_p'],path+'.polynomial',POLY_TOL,0)
            audit.number(p,ref['scipy_p'],path+'.scipy',TAIL_TOL,0)
            audit.exact(row['adjusted_p'],min(1,12*p),path+'.adjusted')
            audit.exact(row['reject'],min(1,12*p)<.05,path+'.reject')
        else:
            for key in ('p','adjusted_p','reject'):audit.exact(row[key],None,path+'.'+key)
        if row['id'] in ('u59','u60'):
            audit.exact(ref['u'],int(row['id'][1:]),path+'.U')
            audit.exact(row['reject'],row['id']=='u60',path+'.boundary')
        if row['id']=='heterogeneity_blindspot':audit.exact(ref['u2'],64,path+'.U2')
        if row['id']=='location':audit.exact(ref['u2'],128,path+'.U2');audit.exact(row['reject'],True,path+'.positive_control')
    transforms=native['transform_fixtures'];require(len(transforms)==6 and {r['id'] for r in transforms}=={'symmetric_variability','skewed_variability','noise_variability','zero_center','location','heterogeneity'},'missing/duplicate native transform toys')
    for row in transforms:
        expected=transform_reference(row['values'],row['condition'],row['population_center'],row['shift_scale'],row['effect'])
        audit.number(row['entity_center'],mean(row['values']),row['id']+'.center')
        require(len(expected)==len(row['transformed']),'native toy dimensions')
        for j,(a,b) in enumerate(zip(row['transformed'],expected)):audit.number(a,b,f'{row["id"]}.raw[{j}]')
        require(len(row['metrics'])==len(row['metric_availability'])==12,'native toy metric dimensions')
        for j,(a,b) in enumerate(zip(row['metrics'],metric_reference(expected))):
            audit.number(a,b,f'{row["id"]}.metric[{j}]')
            audit.exact(row['metric_availability'][j],{'metric':METRICS[j],'available':math.isfinite(b),'reason':'' if math.isfinite(b) else requirement_reason(METRICS[j],expected) or 'nonfinite_metric_value','nonfinite_class':value_class(b)},f'{row["id"]}.availability[{j}]')
        if row['id']=='skewed_variability':
            before=metric_reference(row['values'])
            for mi in (5,6):audit.number(row['metrics'][mi]/before[mi],3.,row['id']+'.normalized_ratio')
        if row['id']=='symmetric_variability':
            before=metric_reference(row['values'])
            for mi in NATURAL['variability']:
                audit.number(row['metrics'][mi]/before[mi],2.,row['id']+'.spread_ratio')
                audit.exact(rank_reference([before[mi]]*8,[row['metrics'][mi]]*8)['u2'],128,row['id']+'.spread_U2')
    return {'exact':exact,'native_audit':audit.record(),'native_fixture_count':len(fixtures)+len(transforms)}


def audit_history(case, payload, halves):
    files={Path(p['path']).name:Path(p['path']) for p in case['round45_files']}
    require(len(files)==6,'historical file universe')
    reports=[]
    for side in ('left','right'):
        meta=read_json(files[side+'.meta.json']);rows=read_json(files[side+'.rows.json'])
        require(meta['status']=='completed' and meta['index']==case['index'] and meta['side']==side,'historical half identity')
        require(meta['source_input_sha256']==case['sha256'] and meta['source_input']==case['path'],'historical source binding')
        require(meta['canonical_data_sha256']==halves[side]['canonical_data_sha256']==case[side+'_data_sha256'],'historical canonical binding')
        require(meta['seed']==case[side+'_seed']==payload['seeds']['calibration_'+side+'_seed'],'historical seed binding')
        require(meta['metric_order']==METRICS and meta['tracks']==TRACKS and meta['grid']==trace.GRID,'historical order')
        require(trace.exact_tree(meta['settings'],payload['settings']),'historical settings')
        require(meta['rows_sha256']==digest(files[side+'.rows.json']) and meta['rows_file']==side+'.rows.json','historical row hash')
        require(meta['expected_repetitions']==meta['observed_repetitions']==1000 and meta['expected_symbols']==meta['observed_symbols']==84000 and meta['expected_bytes']==meta['observed_bytes']==21000 and meta['complete_prefix_records']==1000 and meta['residual_bytes']==0,'historical dimensions')
        require(meta['header_bytes']==0 and meta['significant_bits']==168000 and meta['count_code_order']==[-1,0,1] and meta['flattening']=='Null[metric],Power[track][metric],Grid[track][metric]' and meta['bit_order']=='least-significant-symbol-first','historical encoding')
        require(meta['all_field_match'] is True and not meta['mismatches'] and meta['error'] is None,'historical recorded parity')
        records=trace.frames(files[side+'.codes.bin'].read_bytes(),sha256=meta['sha256'])
        errors=trace.compare_rows(payload['calibration_'+side],rows['rows'],payload['nonfinite_fields']['calibration_'+side],rows['nonfinite_fields'])
        require(not errors,'historical native row mismatch')
        reconstruction=trace.reconstruct(records,rows['rows'],halves[side]['data'])
        require(not reconstruction['errors'],'historical count/row reconstruction mismatch')
        require(reconstruction['counts']==meta['counts'] and reconstruction['grid_counts']==meta['grid_counts'],'historical exact counts mismatch')
        reports.append({'case_index':case['index'],'side':side,'label':'historical internal-calibration frequencies; not newly executed outcomes',
                        'symbols_audited':84000,'null_counts':meta['counts'][:12],
                        'alternative_counts':{t:meta['counts'][12+12*j:24+12*j] for j,t in enumerate(TRACKS)},
                        'all_84_counts':meta['counts'],'all_5_grid_counts':meta['grid_counts'],
                        'row_binding_sha256':meta['rows_sha256'],'code_binding_sha256':meta['sha256']})
    return reports


def source_inventory(root):
    # String ordering is explicit and used identically at prepare and verify.
    return sorted(str(p.resolve()) for p in trace.source_paths(Path(root)))


def tree_inventory(root):
    return sorted(str(p) for p in bounded.tree_files(Path(root)))


def pin_files(paths):
    return {p:digest(p) for p in sorted(set(map(lambda p:str(Path(p).resolve()),paths)))}


def version_record():
    return {'python':platform.python_version(),'scipy':scipy.__version__,'numpy':numpy.__version__,'executable':str(Path(sys.executable).resolve())}


def runtime_files(command):
    binary=Path(command[0]).resolve();root=binary.parent
    paths=[binary]
    for directory in (root/'host'/'fxr',root/'shared'/'Microsoft.NETCore.App'):
        require(directory.is_dir(),'runtime directory unavailable '+str(directory))
        paths.extend(Path(p) for p in tree_inventory(directory))
    return sorted(set(map(str,paths)))


def expected_counts(synthetic=False):
    if not synthetic:return dict(COUNTS)
    return {k:(0 if k.startswith('historical_') or k=='audited_historical_symbols' else v//120) for k,v in COUNTS.items()}


def validate_plan(plan, path, root=None):
    require(digest(path)==PLAN_SHA,'unreviewed mechanism plan')
    document=Path(root)/'docs/ROUND47_SCENARIO_MECHANISM_PROTOCOL.md' if root is not None else Path(plan['protocol_path'])
    require(digest(document)==plan['protocol_sha256']==DOCUMENT_SHA,'unreviewed mechanism document')
    require(plan['metric_order']==METRICS and [c['id'] for c in plan['conditions']]==CONDITIONS,'protocol order')
    require(plan['outputs']==COUNTS and plan['alpha']==ALPHA and plan['family_denominator']==FAMILY,'protocol coverage/settings')
    require(all(LIMITS[k]==v for k,v in plan['limits'].items()),'protocol resource limits')
    require(plan['tolerances']['mathematical_erfc_p_absolute']==TAIL_TOL,'protocol numerical gate')
    require([c['index'] for c in plan['inputs']]==list(range(120)),'protocol complete case universe')
    return document


def prepare(root,out,protocol,command,identity_file,evidence,synthetic_input=None,precreated=False):
    root,out,protocol=map(lambda p:Path(p).resolve(),(root,out,protocol))
    require(not out.exists() or (precreated and synthetic_input is not None and not (out/'bind.json').exists()),'fresh result directory required; no overwrite/resume/retry')
    require(sys.platform=='linux' and Path('/proc/self/status').is_file(),'Linux supervision required')
    plan=read_json(protocol);document=validate_plan(plan,protocol,root)
    command=[str(Path(p).resolve()) for p in command]
    require(len(command)==2 and all(Path(p).is_file() for p in command),'native command files missing')
    native_files=tree_inventory(Path(command[1]).parent)
    identity_file=Path(identity_file).resolve();inspection=read_json(identity_file);identity=inspection['identity']
    require(inspection['status']=='ok' and inspection['metric_order']==METRICS and inspection['conditions']==CONDITIONS,'native inspection contract')
    require(identity['harness_sha256']==digest(command[1]) and identity['core_sha256']==digest(Path(command[1]).parent/'MvsAnalyzer.Core.dll'),'native inspect/binary hash mismatch')
    require(identity['runtime']=='.NET 8.0.31' and identity['processor_count']==1,'native runtime identity')
    synthetic=synthetic_input is not None
    if synthetic:
        source=Path(synthetic_input).resolve();payload=read_json(source)
        require(payload.get('synthetic') is True or 'synthetic' in payload.get('schema',''),'synthetic input provenance required')
        cases=[{'index':0,'path':str(source),'sha256':digest(source),'bytes':source.stat().st_size}]
    else:
        cases=plan['inputs']
    inputs=[p for c in cases for p in [c, *c.get('round45_files',[])]]
    require(len({p['path'] for p in inputs})==len(inputs),'duplicate input inventory')
    for item in inputs:
        p=Path(item['path']);require(p.is_file() and p.stat().st_size==item['bytes'] and digest(p)==item['sha256'],'required input pin drift '+str(p))
    for item in plan['source_pins']:
        require(digest(root/item['path'])==item['sha256'],'native source drift '+item['path'])
    sources=source_inventory(root);runtimes=runtime_files(command)
    evidence=[Path(p).resolve() for p in evidence]
    require(all(p.is_file() for p in evidence),'missing synthetic/review evidence')
    if not synthetic:
        passed=[]
        for p in evidence:
            if p.name=='run.json':
                run_record=read_json(p)
                if run_record.get('status')=='completed' and run_record.get('synthetic') is True:
                    previous=read_json(p.parent/'bind.json')
                    require(previous['sources']==sources and all(digest(x)==previous['pins'][x] for x in sources),'synthetic source identity drift')
                    require(previous['native_files']==native_files and all(digest(x)==previous['pins'][x] for x in native_files),'synthetic native identity drift')
                    require(previous['runtime_files']==runtimes and all(digest(x)==previous['pins'][x] for x in runtimes),'synthetic runtime identity drift')
                    require(previous['reference_runtime_files']==reference_runtime_files() and all(digest(x)==previous['pins'][x] for x in previous['reference_runtime_files']),'synthetic Python runtime identity drift')
                    require(previous['versions']==version_record() and trace.exact_tree(previous['identity'],identity),'synthetic runtime/version identity drift')
                    require(read_json(p.parent/'independent-audit.json')['valid'] is True and read_json(p.parent/'post-run-pins.json')['valid'] is True,'synthetic full-driver gate incomplete')
                    passed.append(p)
        require(passed,'actual native synthetic full-driver success required before retained prepare')
    guard=root.parent.parent/'mvs-r47-before.json';require(synthetic or guard.is_file(),'original change guard missing')
    reference_files=reference_runtime_files()
    pins=pin_files([*sources,*native_files,*runtimes,*reference_files,*[x['path'] for x in inputs],protocol,document,identity_file,*([guard] if guard.is_file() else []),Path(sys.executable).resolve(),*evidence])
    output_inventory=BASE_OUTPUTS+[f'case-{c["index"]:03d}/{name}' for c in cases for name in ('native.json','reference.json.gz','started.json','attempt.json','stdout.log','stderr.log')]
    bind={'schema':BIND_SCHEMA,'created_utc':utc(),'root':str(root),'out':str(out),'synthetic':synthetic,
          'protocol':str(protocol),'protocol_sha256':PLAN_SHA,'document_sha256':DOCUMENT_SHA,
          'native_command':command,'identity':identity,'probe_settings':inspection['settings'],'identity_file':str(identity_file),'sources':sources,
          'core_binary_provenance':'Current harness/Core binaries are pinned independently. Historical and current built binary hashes may differ; original production source pins are unchanged and original Build metrics are checked bit-exactly.',
          'native_files':native_files,'runtime_files':runtimes,'reference_runtime_files':reference_files,'pins':pins,'cases':cases,'inputs':inputs,
          'versions':version_record(),'limits':LIMITS,'metric_order':METRICS,'conditions':CONDITIONS,
          'expected_counts':expected_counts(synthetic),'output_inventory':output_inventory,
          'commands':{stage:[str(Path(sys.executable).resolve()),str(Path(__file__).resolve()),'_'+stage,'--out',str(out)] for stage in ('worker','verifier','postpins')},
          'evidence':[str(p) for p in evidence]}
    out.mkdir(parents=True,exist_ok=precreated);write_json(out/'bind.json',bind)
    (out/'bind.sha256').write_text(digest(out/'bind.json')+'\n')
    for source,dest in ((protocol,out/'protocol.json'),(document,out/'protocol.md')):
        with dest.open('xb') as f:f.write(source.read_bytes())
    return {'status':'prepared','bind_sha256':digest(out/'bind.json'),'synthetic':synthetic,'pins':len(pins),'retained_outcomes_executed':False}


def verify(out,all_pins=True):
    out=Path(out).resolve();require(digest(out/'bind.json')==(out/'bind.sha256').read_text().strip(),'binding hash mismatch')
    m=read_json(out/'bind.json')
    require(m['schema']==BIND_SCHEMA and m['out']==str(out),'binding identity')
    require(m['protocol_sha256']==PLAN_SHA and m['document_sha256']==DOCUMENT_SHA,'reviewed protocol binding')
    require(m['limits']==LIMITS and m['versions']==version_record() and m['metric_order']==METRICS and m['conditions']==CONDITIONS,'bound settings/runtime drift')
    require(m['expected_counts']==expected_counts(m['synthetic']),'fixed count drift')
    require([c['index'] for c in m['cases']]==list(range(1 if m['synthetic'] else 120)),'case inventory drift')
    if all_pins:
        require(source_inventory(m['root'])==m['sources'],'source inventory drift')
        require(tree_inventory(Path(m['native_command'][1]).parent)==m['native_files'],'native inventory drift')
        require(runtime_files(m['native_command'])==m['runtime_files'],'runtime inventory drift')
        require(reference_runtime_files()==m['reference_runtime_files'],'Python reference runtime inventory drift')
        for p,sha in m['pins'].items():require(Path(p).is_file() and digest(p)==sha,'pinned byte drift '+p)
        for item in m['inputs']:require(Path(item['path']).stat().st_size==item['bytes'],'input size drift '+item['path'])
        require(digest(out/'protocol.json')==PLAN_SHA and digest(out/'protocol.md')==DOCUMENT_SHA,'copied protocol drift')
    return m


def supervised_binding(out):
    sha=digest(Path(out)/'bind.json')
    require(os.environ.get('MVS_R47_SUPERVISED_BIND')==sha,'supervisor-only stage')
    return sha


def run_native(command,out,label,args):
    started=time.monotonic();cpu=resource.getrusage(resource.RUSAGE_CHILDREN)
    prefix=label+'.' if label else ''
    # Case logs exist at their terminal names from first write. The supervisor
    # samples the directory concurrently; renaming a sampled path creates a
    # FileNotFoundError between enumeration and stat (failed Round47 attempt).
    with (out/(prefix+'stdout.log')).open('xb') as stdout,(out/(prefix+'stderr.log')).open('xb') as stderr:
        result=subprocess.run(command+args,stdout=stdout,stderr=stderr,env=dict(os.environ,DOTNET_PROCESSOR_COUNT='1'))
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    record={'returncode':result.returncode,'wall_seconds':time.monotonic()-started,
            'cpu_seconds':after.ru_utime+after.ru_stime-cpu.ru_utime-cpu.ru_stime}
    require(result.returncode==0,'native process failed with exit '+str(result.returncode))
    return record


def worker(out):
    out=Path(out).resolve();freeze=supervised_binding(out);m=verify(out)
    run_native(m['native_command'],out,'toys',['--self-test'])
    write_json(out/'toy-native.json',read_json(out/'toys.stdout.log'))
    require(trace.exact_tree(read_json(out/'toy-native.json')['identity'],m['identity']),'toy current native identity mismatch')
    toys=audit_native_toys(read_json(out/'toy-native.json'));write_json(out/'toy-reference.json',toys)
    require(toys['native_audit']['valid'],'native exact toy verification failed')
    with gzip.open(out/'historical-context.jsonl.gz','xt',encoding='utf-8') as historical:
        for case in m['cases']:
            folder=out/f'case-{case["index"]:03d}';folder.mkdir()
            write_json(folder/'started.json',{'index':case['index'],'utc':utc(),'input_sha256':case['sha256']})
            args=['--input',case['path'],'--index',str(case['index']),'--sha256',case['sha256'],'--out',str(folder/'native.json'),'--freeze-sha256',freeze]
            if m['synthetic']:args.append('--synthetic')
            try:
                attempt=run_native(m['native_command'],folder,None,args)
                write_json(folder/'attempt.json',attempt)
            except BaseException as exc:
                write_json(folder/'attempt.json',{'returncode':None,'error':str(exc),'failed':True})
                raise
            native=read_json(folder/'native.json')
            report=audit_case(native,case['path'],case['index'],case['sha256'],freeze,m['synthetic'],m['identity'],m['probe_settings'])
            report['native_sha256']=digest(folder/'native.json')
            with gzip.open(folder/'reference.json.gz','xt',encoding='utf-8') as f:json.dump(report,f,allow_nan=False,separators=(',',':'))
            require(report['audit']['valid'],'native/Python/geometry mismatch in case '+str(case['index']))
            if not m['synthetic']:
                payload,halves=load_source(case['path'],case['index'],case['sha256'])
                for row in audit_history(case,payload,halves):bounded.jsonl(historical,row)
    return {'status':'worker_completed','cases':len(m['cases'])}


def summary_records(reports,denominator):
    result=[]
    for condition in CONDITIONS:
        for mi,metric in enumerate(METRICS):
            ranks=[half['conditions'][CONDITIONS.index(condition)]['ranks'][mi] for report in reports for half in report['halves']]
            require(len(ranks)==denominator,'summary fixed denominator')
            changes=Counter(r['paired_from_identity']['decision_change'] for r in ranks)
            available=[r for r in ranks if r['available']]
            result.append({'condition':condition,'metric':metric,'natural_family':mi in NATURAL.get(condition,[]),
                'denominator_halves':denominator,'available':len(available),'unavailable':denominator-len(available),
                'native_rejections':sum(r['native_reject'] for r in available),
                'reference_rejections':sum(r['reference_reject'] for r in available),
                'native_reference_decision_disagreements':sum(r['native_reference_decision_disagreement'] for r in ranks),
                'paired_decision_changes':{k:changes[k] for k in ('gain','loss','unchanged','unavailable')},
                'ordering_probability_mean':mean([r['ordering_probability'] for r in available]) if available else None,
                'interpretation':'descriptive paired deterministic response; not power, independent validation, or a ranking'})
    return result


def verifier(out):
    out=Path(out).resolve();freeze=supervised_binding(out);m=verify(out,all_pins=False)
    reports=[];checks=0;disagreements=[];native_calls=0
    for case in m['cases']:
        folder=out/f'case-{case["index"]:03d}';native=read_json(folder/'native.json')
        # Repeat the independent oracle from source, not a trust of worker flags.
        computed=audit_case(native,case['path'],case['index'],case['sha256'],freeze,m['synthetic'],m['identity'],m['probe_settings']);computed['native_sha256']=digest(folder/'native.json')
        with gzip.open(folder/'reference.json.gz','rt',encoding='utf-8') as f:saved=trace.parse_json(f.read())
        require(trace.exact_tree(computed,saved),'saved independent report mismatch')
        require(computed['audit']['valid'],'independent verification failure')
        checks+=computed['audit']['checked'];native_calls+=1
        for half in computed['halves']:
            for block in half['conditions']:
                for rank in block['ranks']:
                    if rank['native_reference_decision_disagreement']:
                        disagreements.append({'case_index':case['index'],'side':half['side'],'condition':block['condition'],'metric':rank['metric'],'native_p':rank['native_p'],'reference_p':rank['scipy_p'],'native_reject':rank['native_reject'],'reference_reject':rank['reference_reject']})
        reports.append(computed)
    with gzip.open(out/'historical-context.jsonl.gz','rt',encoding='utf-8') as f:history=[trace.parse_json(line) for line in f]
    require(len(history)==(0 if m['synthetic'] else 240),'historical coverage')
    if not m['synthetic']:
        for case in m['cases']:
            payload,halves=load_source(case['path'],case['index'],case['sha256'])
            require(trace.exact_tree(audit_history(case,payload,halves),history[2*case['index']:2*case['index']+2]),'historical saved context mismatch')
    toys=audit_native_toys(read_json(out/'toy-native.json'))
    require(toys['native_audit']['valid'] and trace.exact_tree(toys,read_json(out/'toy-reference.json')),'independent toy audit failed')
    counts=expected_counts(m['synthetic'])
    require(len(reports)==counts['cases'] and sum(len(r['halves']) for r in reports)==counts['halves'],'report count universe')
    summaries={'schema':'mvs-scenario-mechanism-summaries/v1','synthetic':m['synthetic'],'counts':counts,
               'rows':summary_records(reports,counts['halves']),'boundary_disagreements':disagreements,
               'scientific_go':False,'production_changes':False}
    write_json(out/'summaries.json',summaries)
    audit={'schema':'mvs-scenario-mechanism-audit/v1','valid':True,'status':'passed','binding_sha256':freeze,
           'verifier_sha256':digest(__file__),'counts':counts,'checks':checks,'native_case_calls':native_calls,
           'native_reference_boundary_disagreements':disagreements,'synthetic':m['synthetic'],
           'independence':'Python transformations, metrics, rational toys, pair-count U and SciPy normal tails; source mechanics remain conditional diagnostics'}
    write_json(out/'independent-audit.json',audit)
    return audit


def supervise(command,out,label,deadline,resources,env):
    # The reviewed Round46 helper owns descendant cleanup, aggregate RSS/output
    # sampling and failure records. Its identical frozen limits are asserted.
    require(bounded.LIMITS==LIMITS,'supervisor resource contract drift')
    return bounded.supervise(command,out,label,deadline,resources,env)


def validate_attestation(audit,m,freeze):
    require(audit.get('valid') is True and audit.get('status')=='passed','verifier did not attest success')
    require(audit.get('binding_sha256')==freeze and audit.get('verifier_sha256')==m['pins'][str(Path(__file__).resolve())],'unbound independent audit')
    require(audit.get('counts')==m['expected_counts'] and audit.get('native_case_calls')==len(m['cases']) and audit.get('synthetic')==m['synthetic'],'incomplete audit universe')


def run(out,approval_bind_sha256,overall_start=None,initial_resources=None):
    out=Path(out).resolve()
    require(approval_bind_sha256==digest(out/'bind.json'),'exact approved binding hash required')
    require(not (out/'run-start.json').exists(),'single attempt consumed; no retry or resume')
    start=time.monotonic() if overall_start is None else overall_start;deadline=start+LIMITS['wall_seconds'];m=verify(out,all_pins=False)
    write_json(out/'run-start.json',{'utc':utc(),'approval_bind_sha256':approval_bind_sha256,'synthetic':m['synthetic'],'deadline_seconds':300})
    resources=initial_resources or {'schema':'mvs-scenario-mechanism-resources/v1','limits':LIMITS,'samples':0,'peak_aggregate_rss_bytes':bounded.own_rss(),
               'peak_output_bytes':0,'maximum_observed_sample_gap_seconds':0.,'last_sample_monotonic':start,'processes':[]}
    env=dict(os.environ,MVS_DISABLE_BACKUPS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',DOTNET_PROCESSOR_COUNT='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MVS_R47_SUPERVISED_BIND=approval_bind_sha256)
    status='technical_failure';error=None;cpu=resource.getrusage(resource.RUSAGE_CHILDREN);own_cpu=time.process_time()
    previous=signal.getsignal(signal.SIGTERM);signal.signal(signal.SIGTERM,bounded.termination_signal)
    try:
        for label in ('worker','verifier','postpins'):supervise(m['commands'][label],out,label,deadline,resources,env)
        validate_attestation(read_json(out/'independent-audit.json'),m,approval_bind_sha256)
        require(read_json(out/'post-run-pins.json')['valid'] is True,'post-run pin check failed')
        require(time.monotonic()<deadline,'global deadline before acceptance')
        status='completed'
    except BaseException as exc:
        error=f'{type(exc).__name__}: {exc}'
        write_json(out/'failure.json',{'status':'technical_failure','error':error,'partial_outputs_retained':True,'retry_permitted':False})
    finally:signal.signal(signal.SIGTERM,previous)
    resources.pop('last_sample_monotonic',None)
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    resources.update(wall_seconds=time.monotonic()-start,cpu_seconds=time.process_time()-own_cpu+after.ru_utime+after.ru_stime-cpu.ru_utime-cpu.ru_stime,status=status,
                     rss_scope='supervisor plus all active owned process-group members; sampled peak, not a hard kernel cap')
    cleanup={'status':'incomplete' if any(p.get('cleanup',{}).get('live_members_after') for p in resources['processes']) else 'complete',
             'processes':[{k:p[k] for k in ('label','pid','state','cleanup') if k in p} for p in resources['processes']],
             'case_states':[{'index':c['index'],'state':'completed' if (out/f'case-{c["index"]:03d}/reference.json.gz').exists() else 'started_unfinished' if (out/f'case-{c["index"]:03d}/started.json').exists() else 'not_started'} for c in m['cases']],
             'retry_count':0,'partial_outputs_retained':True}
    entries=bounded.output_inventory(out);unexpected=[p['path'] for p in entries if p['path'] not in m['output_inventory']]
    final_errors=['unplanned output files '+str(unexpected)] if unexpected else []
    def encode(value):return (json.dumps(value,allow_nan=False,sort_keys=True,indent=2)+'\n').encode()
    def final_artifacts():
        record={'schema':'mvs-scenario-mechanism-run/v1','status':status,'error':error,'synthetic':m['synthetic'],
                'bind_sha256':approval_bind_sha256,'scientific_go':False,'production_changes':False,'finalization_errors':final_errors}
        pending={'resources.json':encode(resources),'cleanup.json':encode(cleanup),'run.json':encode(record)}
        files=[{**p,'sha256':digest(out/p['path'])} for p in entries]+[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in pending.items()]
        pending['file-manifest.json']=encode({'schema':'mvs-scenario-mechanism-files/v1','self_excluded':True,'files':files,'total_bytes_before_manifest':sum(p['bytes'] for p in files)})
        return pending,sum(p['bytes'] for p in entries)+sum(map(len,pending.values()))
    pending,total=final_artifacts()
    if total>LIMITS['output_bytes']:final_errors.append('final evidence output limit')
    if cleanup['status']!='complete':final_errors.append('owned process cleanup incomplete')
    if final_errors:
        status='technical_failure';error='; '.join(([error] if error else [])+final_errors);resources['status']=status
        if not (out/'failure.json').exists():write_json(out/'failure.json',{'status':status,'error':error,'partial_outputs_retained':True,'retry_permitted':False})
        entries=bounded.output_inventory(out);pending,total=final_artifacts()
    # Terminal success is written last, after every final integrity/size gate.
    for name in ('resources.json','cleanup.json','file-manifest.json','run.json'):
        with (out/name).open('xb') as f:f.write(pending[name])
    return {'status':status,'error':error,'synthetic':m['synthetic'],'output_dir':str(out),'wall_seconds':resources['wall_seconds'],'output_bytes':total}


def reference_runtime_files():
    paths=[]
    for package in (scipy,numpy):
        root=Path(package.__file__).resolve().parent
        paths.extend(str(p.resolve()) for p in root.rglob('*') if p.is_file() and p.suffix in ('.py','.so') and '__pycache__' not in p.parts)
    return sorted(set(paths))


def synthetic(root,out,command):
    root,out=Path(root).resolve(),Path(out).resolve()
    require(not out.exists(),'fresh synthetic directory required')
    out.mkdir(parents=True)
    start=time.monotonic();deadline=start+LIMITS['wall_seconds']
    resources={'schema':'mvs-scenario-mechanism-resources/v1','limits':LIMITS,'samples':0,'peak_aggregate_rss_bytes':bounded.own_rss(),
               'peak_output_bytes':0,'maximum_observed_sample_gap_seconds':0.,'last_sample_monotonic':start,'processes':[]}
    env=dict(os.environ,MVS_DISABLE_BACKUPS='1',DOTNET_PROCESSOR_COUNT='1',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    command=[str(Path(p).resolve()) for p in command]
    try:
        supervise(command+['--write-synthetic-input',str(out/'synthetic-input.json')],out,'synthetic-input',deadline,resources,env)
        supervise(command+['--inspect'],out,'inspect',deadline,resources,env)
        write_json(out/'native-inspect.json',read_json(out/'inspect.stdout.log'))
        prepared=prepare(root,out,root/'validation/scenario-mechanism-protocol-v1.json',command,out/'native-inspect.json',[],out/'synthetic-input.json',precreated=True)
        return run(out,prepared['bind_sha256'],overall_start=start,initial_resources=resources)
    except BaseException as exc:
        if not (out/'failure.json').exists():write_json(out/'failure.json',{'status':'technical_failure','synthetic':True,'error':str(exc),'partial_outputs_retained':True})
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare')
    for key in ('root','out','protocol','identity-file'):p.add_argument('--'+key,required=True)
    p.add_argument('--native-command',nargs=2,required=True);p.add_argument('--evidence',action='append',default=[]);p.add_argument('--synthetic-input')
    for mode in ('verify','run','_worker','_verifier','_postpins'):
        p=sub.add_parser(mode);p.add_argument('--out',required=True)
        if mode=='run':p.add_argument('--approval-bind-sha256',required=True)
    p=sub.add_parser('synthetic');p.add_argument('--root',required=True);p.add_argument('--out',required=True);p.add_argument('--native-command',nargs=2,required=True)
    sub.add_parser('exact-toys')
    args=parser.parse_args(argv)
    try:
        if args.mode=='synthetic':result=synthetic(args.root,args.out,args.native_command)
        elif args.mode=='prepare':result=prepare(args.root,args.out,args.protocol,args.native_command,args.identity_file,args.evidence,args.synthetic_input)
        elif args.mode=='verify':result={'status':'verified','pins':len(verify(args.out)['pins'])}
        elif args.mode=='run':result=run(args.out,args.approval_bind_sha256)
        elif args.mode=='_worker':result=worker(args.out)
        elif args.mode=='_verifier':result=verifier(args.out)
        elif args.mode=='exact-toys':result=exact_toys()
        else:
            supervised_binding(args.out);m=verify(args.out);result={'valid':True,'pins_checked':len(m['pins']),'source_input_runtime_unchanged':True};write_json(Path(args.out)/'post-run-pins.json',result)
        print(json.dumps(result,allow_nan=False));return 1 if result.get('status')=='technical_failure' else 0
    except Exception as exc:
        print(json.dumps({'status':'technical_failure','mode':args.mode,'error':str(exc)}),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
