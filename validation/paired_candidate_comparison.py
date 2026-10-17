#!/usr/bin/env python3
"""Round46 test-only exact paired candidate comparison; never calibrates.

prepare only hashes retained inputs. run requires the exact approved write-once
binding hash. A supervisor bounds the entire worker, native replay, independent
verification, and post-run pin verification by one global deadline.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
from functools import lru_cache
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import candidate_set_stability as old
import paired_calibration_trace as trace

METRICS = list(trace.METRICS)
TRACKS = list(trace.TRACKS)
FAMILIES = {t:list(old.FAMILIES[t]) for t in TRACKS}
METHODS = {'old':'family-power-ci-overlap-v1','new':'family-power-exact-mcnemar-holm-v1-test-only'}
ALPHA = F(1,20)
LIMITS = {'workers':1,'wall_seconds':300,'cleanup_seconds':5,'aggregate_rss_bytes':1073741824,'output_bytes':67108864,'sampling_seconds':0.05,'dotnet_processor_count':1,'retries':0}
BIND_HASHES = {'43':'36912dcc45f2d2d1d27c0ace940ed2c63125b892088455f9f3d420cca6182eea','44':'726c83813b1d1382a6a7fb08ad44b79e522bddaead7c333eb6587b633c9c7948','45':'5189f7d718c8ae74861b31ee0ce1244c68c5e93719f7ea88fd9a50534de23144'}
TEST_FIELDS = 'case_index side track competitor target family_size hypothesis_count canonical_pair_position n n00 n01 n10 n11 competitor_rejections target_rejections discordances competitor_only target_only power_difference tail_numerator tail_denominator_power_of_two raw_p holm_rank holm_threshold passes_own_rank_threshold prefix_passes adjusted_p rejected competitor_eligible target_eligible eligible_elimination_edge analysis_availability'.split()
HALF_FIELDS = 'case_index side track input_binding analysis_availability unavailable_reason family eligible metric_context old_native_output_reference old_candidates old_qualified old_native_status new_candidates new_qualified new_status old_size new_size old_qualified_size new_qualified_size rejected_edges eligible_elimination_edges surviving_empirical_maxima set_relation cardinality_change old_new_jaccard candidate_power_context invariant_checks'.split()
PAIR_FIELDS = 'case_index track half_references old_sets new_sets old_qualified_sets new_qualified_sets old_sizes new_sizes old_qualified_sizes new_qualified_sizes old_statuses new_statuses old_empty_category new_empty_category old_exact new_exact old_intersection_size old_union_size new_intersection_size new_union_size old_jaccard new_jaccard exact_difference jaccard_difference exact_transition jaccard_change shared_nonempty_conditioning_flags'.split()
OUTPUT_SCHEMA = {'schema':'mvs-paired-candidate-results/v1','fraction':{'numerator':'reduced decimal string','denominator':'positive decimal string'},'ordered_tests':TEST_FIELDS,'half_tracks':HALF_FIELDS,'pair_tracks':PAIR_FIELDS,'summary_schema':'mvs-paired-candidate-summaries/v1','summary_order':TRACKS,'method_order':['old','new'],'counts':{'tests':15840,'halves':720,'pairs':360}}
require = old.require
read_json = trace.read_json
digest = old.digest


def utc(): return datetime.now(timezone.utc).isoformat()
def rational(value):
    value=F(value)
    return {'numerator':str(value.numerator),'denominator':str(value.denominator)}
def from_rational(value):
    require(type(value) is dict and set(value)=={'numerator','denominator'},'fraction shape')
    a,b=value['numerator'],value['denominator']
    require(type(a) is str and type(b) is str and b.isdecimal() and int(b)>0,'fraction encoding')
    v=F(int(a),int(b));require(rational(v)==value,'noncanonical fraction');return v

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2);f.write('\n')

def jsonl(stream,value): stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')

def canonical(values,family):
    require(len(values)==len(set(values)) and set(values)<=set(family),'duplicate/outside-family set')
    return [m for m in family if m in values]


@lru_cache(maxsize=8192,typed=True)
def exact_tail(w,l):
    require(type(w) is int and type(l) is int and w>=0 and l>=0,'nonnegative integer discordances required')
    q=w+l
    numerator=sum(math.comb(q,k) for k in range(w,q+1))
    return numerator,q,F(numerator,1<<q)


def holm(values):
    require(values and all(type(p) is F and 0<=p<=1 for p in values),'invalid p vector')
    m=len(values);result=[None]*m;prefix=True;maximum=F(0)
    for rank,pos in enumerate(sorted(range(m),key=lambda i:(values[i],i)),1):
        p=values[pos];threshold=ALPHA/(m-rank+1);own=p<threshold
        prefix=prefix and own;maximum=max(maximum,(m-rank+1)*p);adj=min(F(1),maximum)
        require(prefix==(adj<ALPHA),'step-down/adjusted disagreement')
        result[pos]={'holm_rank':rank,'holm_threshold':rational(threshold),'passes_own_rank_threshold':own,'prefix_passes':prefix,'adjusted_p':rational(adj),'rejected':prefix}
    return result


def graph_select(family,eligible,edges):
    eligible=canonical(eligible,family);require(len(edges)==len({tuple(e) for e in edges}),'duplicate edge')
    adjacency={m:[] for m in family};indegree={m:0 for m in family}
    for c,t in edges:
        require(c in adjacency and t in adjacency and c!=t,'invalid graph edge')
        adjacency[c].append(t);indegree[t]+=1
    pending=[m for m in family if not indegree[m]];visited=0
    while pending:
        c=pending.pop();visited+=1
        for t in adjacency[c]:
            indegree[t]-=1
            if not indegree[t]:pending.append(t)
    require(visited==len(family),'cyclic rejection graph')
    removed={t for c,t in edges if c in eligible and t in eligible}
    result=[m for m in eligible if m not in removed]
    require(bool(result)==bool(eligible),'empty-set invariant')
    return result


def paired_family(vectors,family,eligible):
    require(list(vectors)==family,'ordered family vectors required')
    eligible=canonical(eligible,family);n=len(vectors[family[0]])
    require(n>0 and all(len(vectors[m])==n for m in family),'unequal/empty vectors')
    require(all(type(v) is int and v in (-1,0,1) for m in family for v in vectors[m]),'invalid family code')
    missing=[{'metric':m,'positions':[i for i,v in enumerate(vectors[m]) if v==-1],'count':vectors[m].count(-1)} for m in family if -1 in vectors[m]]
    if missing:return {'analysis_availability':'unavailable_missing_power_code','unavailable_reason':missing,'tests':None,'candidates':None,'edges':None,'eligible_edges':None,'maxima':None,'invariants':None}
    m=len(family)*(len(family)-1);tests=[];pvalues=[];totals={k:sum(v) for k,v in vectors.items()}
    for c,t in itertools.permutations(family,2):
        cells=[0]*4
        for a,b in zip(vectors[c],vectors[t]):cells[2*a+b]+=1
        n00,n01,n10,n11=cells;numerator,q,p=exact_tail(n10,n01);pvalues.append(p)
        tests.append({'competitor':c,'target':t,'family_size':len(family),'hypothesis_count':m,'canonical_pair_position':len(tests),'n':n,'n00':n00,'n01':n01,'n10':n10,'n11':n11,'competitor_rejections':totals[c],'target_rejections':totals[t],'discordances':q,'competitor_only':n10,'target_only':n01,'power_difference':rational(F(totals[c]-totals[t],n)),'tail_numerator':str(numerator),'tail_denominator_power_of_two':q,'raw_p':rational(p),'competitor_eligible':c in eligible,'target_eligible':t in eligible,'analysis_availability':'available'})
    edges=[];eligible_edges=[]
    for test,adjustment in zip(tests,holm(pvalues)):
        test.update(adjustment);c,t=test['competitor'],test['target']
        test['eligible_elimination_edge']=test['rejected'] and c in eligible and t in eligible
        if test['rejected']:
            require(test['n10']>test['n01'] and totals[c]>totals[t],'non-descending rejection')
            require(20*(m-test['holm_rank']+1)*int(test['tail_numerator'])<(1<<test['discordances']),'exact threshold audit')
            edges.append([c,t])
        if test['eligible_elimination_edge']:eligible_edges.append([c,t])
    bypair={(r['competitor'],r['target']):r for r in tests}
    for (c,t),r in bypair.items():
        reverse=bypair[(t,c)];q=r['discordances']
        require(from_rational(r['raw_p'])+from_rational(reverse['raw_p'])==1+F(math.comb(q,r['n10']),1<<q),'reverse tail identity')
        require(not(r['rejected'] and reverse['rejected']),'reverse rejection')
    candidates=graph_select(family,eligible,edges)
    maxima=[e for e in eligible if totals[e]==max((totals[x] for x in eligible),default=-1)]
    require(set(maxima)<=set(candidates),'empirical maximum eliminated')
    return {'analysis_availability':'available','unavailable_reason':None,'tests':tests,'candidates':candidates,'edges':edges,'eligible_edges':eligible_edges,'maxima':maxima,'invariants':{'strict_count_descent':True,'no_reverse_rejections':True,'acyclic':True,'all_eligible_maxima_survive':True,'subset_of_eligible':True,'empty_iff_eligible_empty':True}}


def family_vectors(records,track):
    t=TRACKS.index(track)
    return {m:[row[12+12*t+METRICS.index(m)] for row in records] for m in FAMILIES[track]}


def jaccard(a,b):
    a,b=set(a),set(b);return F(len(a&b),len(a|b)) if a|b else F(1)

def quantile(values,q):
    require(values and 0<=q<=1,'invalid quantile')
    v=sorted(map(F,values));h=(len(v)-1)*F(q);lo=h.numerator//h.denominator;hi=min(lo+1,len(v)-1)
    return v[lo]+(h-lo)*(v[hi]-v[lo])

def distribution(values,k=None):
    if not values:return {'count':0,'mean':None,'minimum':None,'q1':None,'median':None,'q3':None,'maximum':None,'reason':'zero_denominator','histogram':({str(i):0 for i in range(k+1)} if k is not None else None)}
    out={'count':len(values),'mean':rational(sum(map(F,values))/len(values)),'minimum':rational(min(values)),'q1':rational(quantile(values,F(1,4))),'median':rational(quantile(values,F(1,2))),'q3':rational(quantile(values,F(3,4))),'maximum':rational(max(values)),'reason':None}
    if k is not None:out['histogram']={str(i):values.count(i) for i in range(k+1)}
    return out

def finite_summary(values,empty_reason='no_finite_power_context'):
    finite=sorted(v for v in values if v is not None and math.isfinite(v));n=len(finite)
    return {'total_count':len(values),'finite_count':n,'minimum':finite[0] if n else None,'median':rational(quantile([F.from_float(float(v)) for v in finite],F(1,2))) if n else None,'maximum':finite[-1] if n else None,'reason':None if n else empty_reason}


def power_context(context,selected,empty_reason):
    rows=[r for r in context if r['metric'] in selected]
    return {'metric_half_count':len(rows),'power':finite_summary([r['power'] for r in rows],empty_reason if not rows else 'no_finite_power_context'),'lower':finite_summary([r['power_low'] for r in rows],empty_reason if not rows else 'no_finite_power_context')}


def half_record(index,side,track,rows,records,native,source_binding,native_reference):
    ref=old.reference_selection(rows,track);family=FAMILIES[track];result=paired_family(family_vectors(records,track),family,ref['pool']);j=TRACKS.index(track)
    context=[]
    for r in rows:
        if r['metric'] not in family:continue
        context.append({'metric':r['metric'],'original_applicable':r['applicable'],'applicable':r['metric'] in ref['available'],'null_controlled':r['metric'] in ref['controlled'],'original_fpr_inflated':r['fpr_inflated'],**{k:(r[f] if t is None else r[f][t]) for k,f,t in [('power','track_powers',j),('power_low','track_power_low',j),('power_high','track_power_high',j),('fpr','fpr',None),('fpr_low','fpr_low',None),('fpr_high','fpr_high',None)]}})
    # Preserve nonfinite classes in native sidecars; JSON context uses null and labels.
    for r in context:
        r['nonfinite_fields']={k:('NaN' if math.isnan(v) else 'Infinity' if v>0 else '-Infinity') for k,v in r.items() if type(v) is float and not math.isfinite(v)}
        for k in r['nonfinite_fields']:r[k]=None
    candidates=result['candidates'];qualified=None if candidates is None else [r['metric'] for r in context if r['metric'] in candidates and r['power_low']>=.70]
    oldc,oldq=ref['candidates'],ref['qualified'];available=candidates is not None
    if available:
        require(bool(oldq)==bool(qualified),'qualification-status invariant violated');require(bool(oldc)==bool(candidates),'old/new empty disagreement')
        result['invariants']['qualification_nonempty_unchanged']=True
    a,b=set(oldc),set(candidates or []);relation=None if not available else 'equal' if a==b else 'proper_subset' if b<a else 'proper_superset' if b>a else 'incomparable'
    record={'case_index':index,'side':side,'track':track,'input_binding':source_binding,'analysis_availability':result['analysis_availability'],'unavailable_reason':result['unavailable_reason'],'family':family,'eligible':ref['pool'],'metric_context':context,'old_native_output_reference':native_reference,'old_candidates':oldc,'old_qualified':oldq,'old_native_status':native['summary']['status'],'new_candidates':candidates,'new_qualified':qualified,'new_status':None if not available else 'qualified' if qualified else 'uncertain' if candidates else 'unavailable_no_eligible','old_size':len(oldc),'new_size':len(candidates) if available else None,'old_qualified_size':len(oldq),'new_qualified_size':len(qualified) if available else None,'rejected_edges':result['edges'],'eligible_elimination_edges':result['eligible_edges'],'surviving_empirical_maxima':result['maxima'],'set_relation':relation,'cardinality_change':None if not available else 'decrease' if len(b)<len(a) else 'increase' if len(b)>len(a) else 'equal','old_new_jaccard':rational(jaccard(a,b)) if available else None,'candidate_power_context':{'old':power_context(context,oldc,'no_candidate_metrics'),'new':power_context(context,candidates,'no_candidate_metrics') if available else None,'all_natural':power_context(context,family,'no_finite_power_context'),'eligible':power_context(context,ref['pool'],'no_eligible_metrics')},'invariant_checks':result['invariants']}
    tests=None if result['tests'] is None else [{'case_index':index,'side':side,'track':track,**t} for t in result['tests']]
    require(set(record)==set(HALF_FIELDS),'half schema drift')
    return record,tests


def empty_category(a,b):return 'both_nonempty' if a and b else 'both_empty' if not a and not b else 'left_only_empty' if not a else 'right_only_empty'

def pair_record(left,right):
    require(left['analysis_availability']==right['analysis_availability']=='available','unavailable primary pair')
    out={'case_index':left['case_index'],'track':left['track'],'half_references':{'left':{'case_index':left['case_index'],'side':'left','track':left['track']},'right':{'case_index':right['case_index'],'side':'right','track':right['track']}}}
    for method in ('old','new'):
        a,b=left[method+'_candidates'],right[method+'_candidates'];aa,bb=set(a),set(b)
        out.update({method+'_sets':{'left':a,'right':b},method+'_qualified_sets':{s:r[method+'_qualified'] for s,r in [('left',left),('right',right)]},method+'_sizes':{'left':len(a),'right':len(b)},method+'_qualified_sizes':{s:r[method+'_qualified_size'] for s,r in [('left',left),('right',right)]},method+'_statuses':{s:r['old_native_status' if method=='old' else 'new_status'] for s,r in [('left',left),('right',right)]},method+'_empty_category':empty_category(a,b),method+'_exact':int(aa==bb),method+'_intersection_size':len(aa&bb),method+'_union_size':len(aa|bb),method+'_jaccard':rational(jaccard(a,b))})
    require(out['old_empty_category']==out['new_empty_category'],'shared conditioning changed')
    difference=from_rational(out['new_jaccard'])-from_rational(out['old_jaccard'])
    out.update(exact_difference=out['new_exact']-out['old_exact'],jaccard_difference=rational(difference),exact_transition=f"old_{'yes' if out['old_exact'] else 'no'}_new_{'yes' if out['new_exact'] else 'no'}",jaccard_change='increase' if difference>0 else 'decrease' if difference<0 else 'equal',shared_nonempty_conditioning_flags={'B':bool(out['old_sets']['left'] and out['old_sets']['right']),'U':bool(out['old_union_size'])})
    require(set(out)==set(PAIR_FIELDS),'pair schema drift');return out


def chance(left,right):
    require(len(left)==len(right),'unpaired chance population');n=len(left)
    if not n:return {'n':0,'cross_pairs':0,'exact_matches':0,'jaccard_sum':None,'left_categories':[],'right_categories':[],'exact':{'observed':None,'baseline':None,'excess':None,'adjusted':None,'reason':'zero_denominator'},'jaccard':{'observed':None,'baseline':None,'excess':None,'adjusted':None,'reason':'zero_denominator'}}
    ls,rs=list(map(frozenset,left)),list(map(frozenset,right));exact=sum(a==b for a in ls for b in rs);js=sum((jaccard(a,b) for a in ls for b in rs),F(0));lc,rc=Counter(ls),Counter(rs)
    require(exact==sum(count*rc[s] for s,count in lc.items()),'category-frequency exact baseline mismatch')
    def categories(counts):return [{'set':sorted(s,key=METRICS.index) if set(s)<=set(METRICS) else sorted(s),'count':c,'frequency':rational(F(c,n))} for s,c in sorted(counts.items(),key=lambda p:tuple(sorted(p[0])))]
    result={'n':n,'cross_pairs':n*n,'exact_matches':exact,'jaccard_sum':rational(js),'left_categories':categories(lc),'right_categories':categories(rc)}
    for key,observed,baseline in [('exact',F(sum(a==b for a,b in zip(ls,rs)),n),F(exact,n*n)),('jaccard',sum((jaccard(a,b) for a,b in zip(ls,rs)),F(0))/n,js/(n*n))]:
        excess=observed-baseline;result[key]={'observed':rational(observed),'baseline':rational(baseline),'excess':rational(excess),'adjusted':None if baseline==1 else rational(excess/(1-baseline)),'reason':'degenerate_marginals' if baseline==1 else None}
    return result


def summarize_track(halves,pairs,track,expected=120):
    family=FAMILIES[track];n=len(pairs);require(n==expected and len(halves)==2*n,'track denominators')
    byside={s:[h for h in halves if h['side']==s] for s in ('left','right')};require(all(len(h)==n for h in byside.values()),'side denominators')
    B=[i for i,p in enumerate(pairs) if p['shared_nonempty_conditioning_flags']['B']];U=[i for i,p in enumerate(pairs) if p['shared_nonempty_conditioning_flags']['U']]
    result={'track':track,'family':family,'planned_denominators':{'pairs':expected,'halves':2*expected,'left':expected,'right':expected,'cross_pairs':expected**2},'observed_denominators':{'pairs':n,'halves':len(halves),'left':n,'right':n,'cross_pairs':n*n,'B':len(B),'U':len(U)},'availability':{'available':len(halves),'unavailable':0,'reasons':{}},'methods':{}}
    for method in ('old','new'):
        sides={}
        for side,hs in byside.items():
            sizes=[h[method+'_size'] for h in hs];qs=[h[method+'_qualified_size'] for h in hs];contexts=[r for h in hs for r in h['metric_context']];eligible=[r for h in hs for r in h['metric_context'] if r['metric'] in h['eligible']];candidates=[r for h in hs for r in h['metric_context'] if r['metric'] in h[method+'_candidates']]
            sides[side]={'denominator':n,'candidate_sizes':distribution(sizes,len(family)),'qualified_sizes':distribution(qs,len(family)),'full_family_count':sizes.count(len(family)),'empty_count':sizes.count(0),'no_qualified_count':qs.count(0),'candidate_inclusion':{m:sum(m in h[method+'_candidates'] for h in hs) for m in family},'qualified_inclusion':{m:sum(m in h[method+'_qualified'] for h in hs) for m in family},'status_counts':{s:sum(('unavailable_no_eligible' if h['old_native_status']=='unavailable' else h['old_native_status'])==s if method=='old' else h['new_status']==s for h in hs) for s in ('qualified','uncertain','unavailable_no_eligible')},'power_context':{'all_natural':power_context(contexts,family,'no_finite_power_context'),'eligible':power_context(eligible,family,'no_eligible_metrics'),'candidate_weighted_metric_half':power_context(candidates,family,'no_candidate_metrics')},'per_half_power_context':[{'case_index':h['case_index'],**h['candidate_power_context'][method]} for h in hs]}
        left=[p[method+'_sets']['left'] for p in pairs];right=[p[method+'_sets']['right'] for p in pairs];js=[from_rational(p[method+'_jaccard']) for p in pairs];exact=sum(p[method+'_exact'] for p in pairs);cats={c:sum(p[method+'_empty_category']==c for p in pairs) for c in ('both_empty','left_only_empty','right_only_empty','both_nonempty')};require(sum(cats.values())==n,'empty categories denominator')
        def companion(indices,include_exact=True):
            d=len(indices);return {'denominator':d,'exact_numerator':sum(pairs[i][method+'_exact'] for i in indices) if include_exact else None,'exact':rational(F(sum(pairs[i][method+'_exact'] for i in indices),d)) if d and include_exact else None,'jaccard_sum':rational(sum((js[i] for i in indices),F(0))) if d else None,'jaccard_mean':rational(sum((js[i] for i in indices),F(0))/d) if d else None,'reason':None if d else 'zero_denominator'}
        result['methods'][method]={'method_id':METHODS[method],'sides':sides,'size_pair_crosstab':{f'{a},{b}':sum(len(l)==a and len(r)==b for l,r in zip(left,right)) for a in range(len(family)+1) for b in range(len(family)+1)},'mean_absolute_size_difference':rational(F(sum(abs(len(a)-len(b)) for a,b in zip(left,right)),n)),'empty_categories':cats,'all_pairs':{'denominator':n,'exact_numerator':exact,'exact':rational(F(exact,n)),'jaccard_sum':rational(sum(js,F(0))),'jaccard_distribution':distribution(js),'both_empty_contribution':rational(F(cats['both_empty'],n)),'nonempty_exact_numerator':exact-cats['both_empty'],'nonempty_exact_rate':rational(F(exact-cats['both_empty'],n))},'B':companion(B),'U':companion(U,False),'chance_all':chance(left,right),'chance_B':chance([left[i] for i in B],[right[i] for i in B])}
    def adjusted_difference(pop,key):
        a=result['methods']['old'][pop][key]['adjusted'];b=result['methods']['new'][pop][key]['adjusted']
        return {'value':rational(from_rational(b)-from_rational(a)) if a is not None and b is not None else None,'reason':None if a is not None and b is not None else 'one_or_both_adjustments_undefined'}
    comparisons={'denominator_halves':len(halves),'denominator_pairs':n,'set_relation_counts':{s:sum(h['set_relation']==s for h in halves) for s in ('equal','proper_subset','proper_superset','incomparable')},'cardinality_change_counts':{s:sum(h['cardinality_change']==s for h in halves) for s in ('decrease','equal','increase')},'exact_transition_counts':{f'old_{o}_new_{v}':sum(p['exact_transition']==f'old_{o}_new_{v}' for p in pairs) for o in ('yes','no') for v in ('yes','no')},'jaccard_change_counts':{s:sum(p['jaccard_change']==s for p in pairs) for s in ('increase','equal','decrease')},'qualification_status_invariant':{'checked':len(halves),'passed':sum(bool(h['old_qualified'])==bool(h['new_qualified']) for h in halves)},'all_exact_difference':rational(F(sum(p['exact_difference'] for p in pairs),n)),'all_jaccard_difference':rational(sum((from_rational(p['jaccard_difference']) for p in pairs),F(0))/n),'B_exact_difference':rational(F(sum(pairs[i]['exact_difference'] for i in B),len(B))) if B else None,'B_jaccard_difference':rational(sum((from_rational(pairs[i]['jaccard_difference']) for i in B),F(0))/len(B)) if B else None,'B_reason':None if B else 'zero_denominator','adjusted_differences':{pop:{key:adjusted_difference(pop,key) for key in ('exact','jaccard')} for pop in ('chance_all','chance_B')}}
    result['new_minus_old']=comparisons;return result

PROTOCOL_SHA = 'd45176ba84a1797cc2005a40f5e29eb2c3f141478b4eba5d34fabd43960e28e0'
DOCUMENT_SHA = '6abfdf814332d9547809e8863504764305ed7a319b7cabff28522ce42046b2c7'
BASE_ARTIFACTS = ['bind.json','bind.sha256','protocol.json','protocol.md','run-start.json','run.json','input-validation.json','native-baseline-parity.json','ordered-tests.jsonl.gz','half-tracks.jsonl.gz','pair-tracks.jsonl.gz','summaries.json','independent-audit.json','post-run-pins.json','resources.json','failure.json','cleanup.json','report.md','file-manifest.json','worker.stdout.log','worker.stderr.log','verifier.stdout.log','verifier.stderr.log','postpins.stdout.log','postpins.stderr.log','unavailable-families.json']


def tree_files(directory):
    directory=Path(directory).resolve();result=[]
    for p in directory.rglob('*'):
        require(not p.is_symlink(),'symlink in immutable inventory: '+str(p))
        if p.is_file():result.append(p.resolve())
    return sorted(result)


def partition_input_inventory(declared,observed):
    require(len(declared)==len(set(declared)),'duplicate declared input')
    require(len(observed)==len(set(observed)),'duplicate observed input')
    require(set(declared)<=set(observed),'declared input absent from observed inventory')
    return sorted(declared),sorted(set(observed)-set(declared))


def prepare(root,out,protocol,protocol_sha,r43,r44,r45,native_command,verifier_script,evidence):
    root,out,protocol,r43,r44,r45,verifier_script=map(lambda p:Path(p).resolve(),(root,out,protocol,r43,r44,r45,verifier_script))
    require(not out.exists(),'output directory exists; no overwrite/resume/retry')
    require(sys.platform=='linux' and Path('/proc/self/status').exists(),'Linux process supervision required')
    require(protocol_sha==PROTOCOL_SHA==digest(protocol),'unreviewed protocol')
    plan=read_json(protocol);document=root/plan['document_path']
    require(plan['document_sha256']==DOCUMENT_SHA==digest(document),'unreviewed document')
    require(plan['metric_order']==METRICS and plan['tracks']==TRACKS and plan['families']=={t:[METRICS.index(m) for m in FAMILIES[t]] for t in TRACKS},'protocol order/families')
    require(plan['alpha']==rational(ALPHA) and plan['method_id']==METHODS['new'] and plan['baseline_method_id']==METHODS['old'],'protocol methods')
    require(all(plan['limits'][k]==LIMITS[k] for k in plan['limits'] if k in LIMITS),'protocol limits')
    roots={'r43':r43,'r44':r44,'r45':r45};inventories={key:tree_files(p) for key,p in roots.items()};declared=[]
    for item in plan['input_files']:
        p=roots[item['root']]/item['path'];require(p.resolve().is_relative_to(roots[item['root']]),'input traversal')
        require(p.is_file() and p.stat().st_size==item['bytes'] and digest(p)==item['sha256'],'declared input drift '+str(p));declared.append(p.resolve())
    declared,supplementary=partition_input_inventory(declared,[p for paths in inventories.values() for p in paths])
    prior={}
    for key,directory in roots.items():
        require(digest(directory/'bind.json')==BIND_HASHES[key[1:]]==plan['prior_binding_hashes'][key],'historical binding drift')
        require((directory/'bind.sha256').read_text().strip()==BIND_HASHES[key[1:]],'historical checksum drift')
        prior[key]=read_json(directory/'bind.json')
    native_command=[str(Path(p).resolve()) for p in native_command]
    require(native_command==prior['r44']['command'] and len(native_command)==2,'original Round44 native harness only')
    native_dir=Path(native_command[1]).parent;native_files=tree_files(native_dir)
    require([str(p) for p in native_files]==prior['r44']['native_files'],'native inventory drift')
    runtime_files=[Path(p) for p in prior['r44']['runtime_files']]
    for p in native_files+runtime_files+[Path(native_command[0])]:require(digest(p)==prior['r44']['pins'][str(p)],'old native/runtime pin drift '+str(p))
    identity=prior['r44']['identity'];require(identity['runtime']=='.NET 8.0.31','runtime identity')
    require(identity['harness_sha256']==digest(native_command[1]) and identity['core_sha256']==digest(native_dir/'MvsAnalyzer.Core.dll'),'loaded original assembly identity')
    for rel,sha in plan['source_hashes'].items():require(digest(root/rel)==sha,'source pin '+rel)
    require(verifier_script.is_file() and verifier_script.suffix=='.py','prewritten verifier required')
    evidence=[Path(p).resolve() for p in evidence];require(evidence and all(p.is_file() for p in evidence),'synthetic/review evidence required')
    sources=old.source_paths(root);guard=root.parent.parent/'mvs-r46-before.json';require(guard.is_file(),'original scope baseline absent')
    prior_protocol45=Path(prior['r45']['protocol']).resolve();require(str(prior_protocol45) in prior['r45']['pins'] and digest(prior_protocol45)==prior['r45']['pins'][str(prior_protocol45)],'prior R45 protocol drift')
    paths=set(sources+native_files+runtime_files+[prior_protocol45]+[p for values in inventories.values() for p in values]+[protocol,document,verifier_script,Path(sys.executable).resolve(),Path(native_command[0]),guard]+evidence)
    pins={str(p):digest(p) for p in sorted(paths)}
    plan45=read_json(prior_protocol45);require(len(plan45['inputs'])==120,'prior identity inventory')
    cases=[]
    for i in range(120):
        source=r43/f'case-{i:03d}/native.json';previous=r44/f'case-{i:03d}/native.json';case45=r45/f'case-{i:03d}/native';association=plan45['inputs'][i]
        require(association['index']==i and digest(source)==association['sha256'],'case original association')
        cases.append({'index':i,'r43_input':str(source),'r43_sha256':pins[str(source)],'r44_native':str(previous),'r45_case':str(case45),'half_associations':{s:{'calibration_seed':association[s+'_seed'],'canonical_data_sha256':association[s+'_data_sha256']} for s in ('left','right')}})
    output_inventory=BASE_ARTIFACTS+[f'native/case-{i:03d}/{name}' for i in range(120) for name in ('input-validation.json','parity.json','started.json','attempt.json','stdout.log','stderr.log','native.json')]
    output_inventory += [f'synthetic-evidence/{i:03d}-{p.name}' for i,p in enumerate(evidence)]
    bind={'schema':'mvs-paired-candidate-bind/v1','created_utc':utc(),'root':str(root),'output_dir':str(out),'protocol':str(protocol),'protocol_sha256':PROTOCOL_SHA,'document_sha256':DOCUMENT_SHA,'r43_dir':str(r43),'r44_dir':str(r44),'r45_dir':str(r45),'input_files':[{'path':str(p),'sha256':pins[str(p)],'bytes':p.stat().st_size} for p in declared],'supplementary_input_files':[{'path':str(p),'sha256':pins[str(p)],'bytes':p.stat().st_size} for p in supplementary],'input_inventory_roles':{'input_files':'required scientific/provenance inputs explicitly declared by the reviewed protocol','supplementary_input_files':'other pre-existing retained evidence, preserved and byte-pinned only; not consumed as scientific inputs'},'input_inventories':{k:[str(p) for p in v] for k,v in inventories.items()},'sources':[str(p) for p in sources],'native_files':[str(p) for p in native_files],'runtime_files':[str(p) for p in runtime_files],'pins':pins,'cases':cases,'native_command':native_command,'native_identity':identity,'trace_identity':prior['r45']['identity'],'trace_freeze_sha256':BIND_HASHES['45'],'verifier_command':[str(Path(sys.executable).resolve()),str(verifier_script)],'python':{'executable':str(Path(sys.executable).resolve()),'version':sys.version},'ordered_hypotheses':{t:[list(p) for p in itertools.permutations(FAMILIES[t],2)] for t in TRACKS},'metric_order':METRICS,'tracks':TRACKS,'methods':METHODS,'limits':LIMITS,'output_schema':OUTPUT_SCHEMA,'output_inventory':output_inventory,'evidence':[str(p) for p in evidence],'derived_power_summary':'minimum/maximum preserve binary64; median is exact type-7 Fraction.from_float interpolation; original P/L/U remain binary64','commands':{'worker':[str(Path(sys.executable).resolve()),str(Path(__file__).resolve()),'_worker','--out',str(out)],'verifier':[str(Path(sys.executable).resolve()),str(verifier_script),'--binding',str(out/'bind.json'),'--results',str(out),'--out',str(out/'independent-audit.json')],'postpins':[str(Path(sys.executable).resolve()),str(Path(__file__).resolve()),'_postpins','--out',str(out)]}}
    out.mkdir(parents=True);write_json(out/'bind.json',bind)
    with (out/'bind.sha256').open('x') as f:f.write(digest(out/'bind.json')+'\n')
    for src,dst in [(protocol,out/'protocol.json'),(document,out/'protocol.md')]+[(p,out/f'synthetic-evidence/{i:03d}-{p.name}') for i,p in enumerate(evidence)]:
        dst.parent.mkdir(exist_ok=True,parents=True)
        with dst.open('xb') as f:f.write(src.read_bytes())
    return {'status':'prepared','bind_sha256':digest(out/'bind.json'),'output_dir':str(out),'pins':len(pins),'retained_calculations_executed':False}


def verify(out,all_pins=True):
    out=Path(out).resolve();require(digest(out/'bind.json')==(out/'bind.sha256').read_text().strip(),'binding checksum drift');m=read_json(out/'bind.json')
    require(m['schema']=='mvs-paired-candidate-bind/v1' and m['output_dir']==str(out),'binding identity')
    require(m['protocol_sha256']==PROTOCOL_SHA and m['document_sha256']==DOCUMENT_SHA,'reviewed protocol binding')
    require(m['limits']==LIMITS and m['methods']==METHODS and m['metric_order']==METRICS and m['tracks']==TRACKS and m['output_schema']==OUTPUT_SCHEMA,'bound analysis contract')
    require(m['ordered_hypotheses']=={t:[list(p) for p in itertools.permutations(FAMILIES[t],2)] for t in TRACKS},'hypothesis universe drift')
    require([c['index'] for c in m['cases']]==list(range(120)),'case inventory')
    plan=read_json(m['protocol'])
    expected={str((Path(m[item['root']+'_dir'])/item['path']).resolve()):(item['sha256'],item['bytes']) for item in plan['input_files']}
    require({item['path']:(item['sha256'],item['bytes']) for item in m['input_files']}==expected and len(m['input_files'])==len(expected),'declared protocol input inventory drift')
    _,supplementary=partition_input_inventory([item['path'] for item in m['input_files']],[path for paths in m['input_inventories'].values() for path in paths])
    require([item['path'] for item in m['supplementary_input_files']]==supplementary,'supplementary input inventory drift')
    require(all(m['pins'].get(item['path'])==item['sha256'] for item in m['input_files']+m['supplementary_input_files']),'input role/pin mismatch')
    if all_pins:
        require(all(Path(item['path']).stat().st_size==item['bytes'] for item in m['input_files']+m['supplementary_input_files']),'input role/byte-size mismatch')
        require([str(p) for p in old.source_paths(Path(m['root']))]==m['sources'],'source inventory drift')
        require([str(p) for p in tree_files(Path(m['native_command'][1]).parent)]==m['native_files'],'native inventory drift')
        for key in ('r43','r44','r45'):require([str(p) for p in tree_files(m[key+'_dir'])]==m['input_inventories'][key],'input inventory drift '+key)
        for p,sha in m['pins'].items():require(digest(p)==sha,'pinned byte drift '+p)
    return m


def worker(out):
    out=Path(out).resolve();require(os.environ.get('MVS_R46_SUPERVISED_BIND')==digest(out/'bind.json'),'supervisor-only worker')
    m=verify(out);all_rows={};validation=[];parity=[];start=time.monotonic()
    # Complete every input validation and native baseline before paired inference.
    for c in m['cases']:
        i=c['index'];folder=out/f'native/case-{i:03d}';folder.mkdir(parents=True)
        try:
            raw=read_json(c['r43_input']);rows,rowaudit=old.validate_case(raw,i)
            audit=trace.validate_case(c['r45_case'],c['r43_input'],m['trace_freeze_sha256'],m['trace_identity'])
            for side in ('left','right'):
                require(not audit[side]['row_mismatches'] and not audit[side]['reconstruction']['errors'],'Round45 trace/row reconstruction mismatch')
                require(raw['seeds']['calibration_'+side+'_seed']==c['half_associations'][side]['calibration_seed'] and raw['data'][side]['sha256']==c['half_associations'][side]['canonical_data_sha256'],'seed/data association drift')
            validation.append({'case_index':i,'accepted':True,'halves':{s:{'row_mismatch_count':0,'reconstruction_error_count':0,'coordinate_count':84,'repetitions':1000,'codes_sha256':digest(Path(c['r45_case'])/(s+'.codes.bin')),'rows_sha256':digest(Path(c['r45_case'])/(s+'.rows.json')),'max_validation_absolute_error':audit[s]['reconstruction']['max_absolute_error']} for s in ('left','right')}})
            write_json(folder/'input-validation.json',validation[-1])
        except Exception as exc:
            write_json(folder/'input-validation.json',{'case_index':i,'accepted':False,'error':str(exc)})
            raise
        command=[*m['native_command'],'--input',c['r43_input'],'--index',str(i),'--sha256',c['r43_sha256'],'--out',str(folder/'native.json')]
        write_json(folder/'started.json',{'case_index':i,'utc':utc(),'command':command,'status':'started'})
        native_start=time.monotonic()
        with (folder/'stdout.log').open('xb') as stdout,(folder/'stderr.log').open('xb') as stderr:
            # Inherit supervised process group. The worker sleeps while native computes.
            proc=subprocess.run(command,stdout=stdout,stderr=stderr,env=trace.child_env(m['native_command']))
        write_json(folder/'attempt.json',{'case_index':i,'returncode':proc.returncode,'wall_seconds':time.monotonic()-native_start,'status':'completed' if proc.returncode==0 else 'failed','retry_count':0})
        try:
            require(proc.returncode==0,'original native baseline failed '+str(i));native=read_json(folder/'native.json');historical=read_json(c['r44_native'])
            require(trace.exact_tree(native,historical),'full original native payload differs from Round44 '+str(i))
            old.compare_native(native,{'rows':rows,'raw':raw},i,c['r43_sha256'],m['native_identity'])
            parity.append({'case_index':i,'full_payload_exact':True,'build_invocations':6,'summarize_invocations':6,'fresh_native_sha256':digest(folder/'native.json'),'old_native_sha256':digest(c['r44_native']),'reference_parity':True})
            write_json(folder/'parity.json',parity[-1])
        except Exception as exc:
            write_json(folder/'parity.json',{'case_index':i,'full_payload_exact':False,'error':str(exc)})
            raise
        all_rows[i]=rows
    write_json(out/'input-validation.json',{'schema':'mvs-paired-candidate-input-validation/v1','valid':True,'planned_cases':120,'observed_cases':len(validation),'trace_count':240,'coordinate_mappings_per_trace':84,'cases':validation})
    write_json(out/'native-baseline-parity.json',{'valid':True,'cases':parity,'native_case_processes':len(parity),'explicit_build_invocations':720,'explicit_summarize_invocations':720,'includes_internal_builds':False})
    halves=[];pairs=[];unavailable=[];test_count=0
    with gzip.open(out/'ordered-tests.jsonl.gz','xt',encoding='utf-8') as ts,gzip.open(out/'half-tracks.jsonl.gz','xt',encoding='utf-8') as hs,gzip.open(out/'pair-tracks.jsonl.gz','xt',encoding='utf-8') as ps:
        for c in m['cases']:
            i=c['index'];native_path=out/f'native/case-{i:03d}/native.json';native=read_json(native_path);local={}
            for side in ('left','right'):
                records=trace.frames((Path(c['r45_case'])/(side+'.codes.bin')).read_bytes())
                for track in TRACKS:
                    ev=next(e for e in native['evaluations'] if e['side']==side and e['track']==track)
                    source_binding={'source_input':c['r43_input'],'source_input_sha256':c['r43_sha256'],'codes_file':str(Path(c['r45_case'])/(side+'.codes.bin')),'codes_sha256':m['pins'][str(Path(c['r45_case'])/(side+'.codes.bin'))],**c['half_associations'][side]}
                    nr={'path':str(native_path),'sha256':digest(native_path),'evaluation_position':(0 if side=='left' else 3)+TRACKS.index(track)}
                    h,tests=half_record(i,side,track,all_rows[i][side],records,ev,source_binding,nr);jsonl(hs,h);halves.append(h);local[(side,track)]=h
                    if tests is None:unavailable.append({'case_index':i,'side':side,'track':track,'reason':h['unavailable_reason'],'tests':None,'new_candidates':None,'new_size':None})
                    else:
                        for test in tests:require(set(test)==set(TEST_FIELDS),'ordered test schema drift');jsonl(ts,test);test_count+=1
            for track in TRACKS:
                if all(local[(s,track)]['analysis_availability']=='available' for s in ('left','right')):
                    p=pair_record(local[('left',track)],local[('right',track)]);pairs.append(p);jsonl(ps,p)
    write_json(out/'unavailable-families.json',{'count':len(unavailable),'families':unavailable,'primary_comparison_blocked':bool(unavailable)})
    require(not unavailable,'missing natural-family power code blocks all primary comparisons')
    require((len(halves),len(pairs),test_count)==(720,360,15840),'complete record counts')
    summaries={'schema':'mvs-paired-candidate-summaries/v1','methods':METHODS,'track_order':TRACKS,'counts':{'tests':test_count,'halves':len(halves),'pairs':len(pairs)},'tracks':[summarize_track([h for h in halves if h['track']==t],[p for p in pairs if p['track']==t],t) for t in TRACKS]}
    write_json(out/'summaries.json',summaries)
    # All quantitative report formatting is inside the retained-analysis budget.
    lines=['# Round46 test-only comparison','Posthoc comparison on 120 old synthetic pairs per track. Original powers, calibrations, production decisions, and earlier scientific NO-GO gates are unchanged. Conditional Monte Carlo uncertainty does not describe uncertainty about people or measurement samples. A more selective set alone is not a better scientific recommendation.']
    for s in summaries['tracks']:
        lines += ['\n## '+s['track'],'Half-track denominator: 240; matched-pair denominator: 120.','Cardinality changes (new versus old): '+json.dumps(s['new_minus_old']['cardinality_change_counts'])]
        for method in ('old','new'):
            v=s['methods'][method];lines += [method+': exact='+json.dumps(v['all_pairs']['exact'])+'; mean J='+json.dumps(v['all_pairs']['jaccard_distribution']['mean'])+'; marginal-frequency descriptions='+json.dumps(v['chance_all'])+'; empty categories='+json.dumps(v['empty_categories'])+'; qualified-size and absolute-power context='+json.dumps({side:{'qualified_sizes':a['qualified_sizes'],'no_qualified_count':a['no_qualified_count'],'power_context':a['power_context']} for side,a in v['sides'].items()})]
        lines += ['Differences, including losses and undefined adjustments: '+json.dumps(s['new_minus_old'])]
    with (out/'report.md').open('x') as f:f.write('\n\n'.join(lines)+'\n')
    return {'status':'completed','counts':summaries['counts'],'worker_wall_seconds':time.monotonic()-start}


def own_rss():
    fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split();return int(fields[21])*os.sysconf('SC_PAGE_SIZE')

def output_inventory(out):
    return [{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size} for p in tree_files(out)]


def group_members(pgid):
    members=[]
    for directory in Path('/proc').iterdir():
        if not directory.name.isdecimal():continue
        try:
            fields=(directory/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid:members.append({'pid':int(directory.name),'ppid':int(fields[1]),'state':fields[0],'rss_bytes':int(fields[21])*os.sysconf('SC_PAGE_SIZE')})
        except (FileNotFoundError,ProcessLookupError):pass
    return sorted(members,key=lambda x:x['pid'])


def terminate_owned_group(proc,seconds):
    began=time.monotonic();deadline=began+seconds;before=group_members(proc.pid)
    old.kill_group(proc)
    try:proc.wait(timeout=max(0,deadline-time.monotonic()))
    except subprocess.TimeoutExpired:pass
    remaining=group_members(proc.pid)
    while any(p['state']!='Z' for p in remaining) and time.monotonic()<deadline:
        old.kill_group(proc);time.sleep(min(.01,max(0,deadline-time.monotonic())));remaining=group_members(proc.pid)
    return {'status':'incomplete' if any(p['state']!='Z' for p in remaining) else 'terminated_zombies_await_reaping' if remaining else 'complete','members_before':before,'members_after':remaining,'live_members_after':[p for p in remaining if p['state']!='Z'],'wall_seconds':time.monotonic()-began,'deadline_seconds':seconds}


def termination_signal(signum,frame):
    raise InterruptedError('supervisor received signal '+str(signum))


def supervise(command,out,label,deadline,resources,env):
    require(time.monotonic()<deadline,'global deadline reached before '+label)
    started=time.monotonic();proc=None;reason=None
    attempt={'label':label,'command':command,'pid':None,'start_utc':utc(),'state':'launch_attempt'};resources['processes'].append(attempt)
    try:
        with (out/(label+'.stdout.log')).open('xb') as stdout,(out/(label+'.stderr.log')).open('xb') as stderr:
            proc=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True,env=env)
            attempt.update(pid=proc.pid,state='started')
            while True:
                now=time.monotonic();members=group_members(proc.pid);rss=own_rss()+sum(p['rss_bytes'] for p in members);size=sum(p['bytes'] for p in output_inventory(out))
                resources['samples']+=1;resources['peak_aggregate_rss_bytes']=max(resources['peak_aggregate_rss_bytes'],rss);resources['peak_output_bytes']=max(resources['peak_output_bytes'],size)
                resources['maximum_observed_sample_gap_seconds']=max(resources['maximum_observed_sample_gap_seconds'],now-resources['last_sample_monotonic']);resources['last_sample_monotonic']=now
                reason='global_wall_deadline' if now>=deadline else 'aggregate_rss_limit' if rss>LIMITS['aggregate_rss_bytes'] else 'evidence_output_limit' if size>LIMITS['output_bytes'] else None
                if reason:raise RuntimeError(reason)
                if proc.poll() is not None:
                    remaining=group_members(proc.pid);attempt['members_after_leader_exit']=remaining
                    require(not remaining,'owned descendant remains after leader exit')
                    break
                time.sleep(min(LIMITS['sampling_seconds'],max(0,deadline-time.monotonic())))
            require(proc.returncode==0,label+' failed with exit '+str(proc.returncode))
            attempt.update(state='completed',returncode=proc.returncode,wall_seconds=time.monotonic()-started,cleanup={'status':'complete','members_after':[],'live_members_after':[],'wall_seconds':0})
    except BaseException as exc:
        attempt.update(state='failed',reason=reason or 'launch_failure' if proc is None else reason or 'process_error',error=str(exc),returncode=proc.poll() if proc else None,wall_seconds=time.monotonic()-started)
        attempt['cleanup']=terminate_owned_group(proc,LIMITS['cleanup_seconds']) if proc else {'status':'not_needed_no_process','members_after':[],'live_members_after':[],'wall_seconds':0}
        attempt['cleanup_group_rss_bytes']=sum(p['rss_bytes'] for p in attempt['cleanup']['members_after'])
        raise


def native_case_states(out):
    states=[]
    for i in range(120):
        folder=Path(out)/f'native/case-{i:03d}';attempt=folder/'attempt.json';started=folder/'started.json'
        state={'case_index':i,'state':'started_unfinished' if started.exists() else 'not_started','input_validation_recorded':(folder/'input-validation.json').exists(),'parity_recorded':(folder/'parity.json').exists()}
        if attempt.exists():
            state['attempt_evidence']={'path':str(attempt),'bytes':attempt.stat().st_size,'sha256':digest(attempt)}
            try:
                value=read_json(attempt)
                require(type(value) is dict and type(value.get('returncode')) is int,'missing integer native return code')
                state['state']='completed' if value['returncode']==0 else 'failed'
            except Exception as exc:
                state['state']='unknown_partial_attempt';state['parse_error']=str(exc)
        states.append(state)
    return states


def validate_audit_attestation(audit,approval_bind_sha256,binding):
    require(audit.get('valid') is True and audit.get('status')=='passed','independent verifier did not attest success')
    require(audit.get('binding_sha256')==approval_bind_sha256,'independent audit binding mismatch')
    verifier=binding['verifier_command'][1]
    require(audit.get('verifier_sha256')==binding['pins'][verifier],'independent verifier identity mismatch')
    require(audit.get('counts')=={'half_tracks':720,'ordered_tests':15840,'native_build_invocations':720,'native_summarize_invocations':720,'traces':240,'pair_tracks':360},'independent audit incomplete counts')
    require(audit.get('summary_tracks_checked')==TRACKS and audit.get('all_summary_fields_exact') is True,'independent audit incomplete summaries')


def run(out,approval_bind_sha256):
    out=Path(out).resolve();require(approval_bind_sha256==digest(out/'bind.json'),'exact approved binding hash required')
    require(not (out/'run-start.json').exists(),'one attempt only; no retry/resumption')
    start=time.monotonic();deadline=start+LIMITS['wall_seconds'];m=verify(out,all_pins=False)
    write_json(out/'run-start.json',{'utc':utc(),'approval_bind_sha256':approval_bind_sha256,'approval_utc':utc(),'argv':sys.argv,'global_wall_seconds':300,'monotonic_start':start,'monotonic_deadline':deadline})
    resources={'schema':'mvs-paired-candidate-resources/v1','limits':LIMITS,'samples':0,'peak_aggregate_rss_bytes':own_rss(),'peak_output_bytes':0,'sampling_requested_seconds':LIMITS['sampling_seconds'],'maximum_observed_sample_gap_seconds':0.0,'last_sample_monotonic':start,'processes':[],'rss_scope':'supervisor plus every owned active process-group member; sleeping Python parent remains included','retained_analysis_start_utc':utc()}
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',MVS_R46_SUPERVISED_BIND=approval_bind_sha256)
    status='technical_failure';error=None
    previous_sigterm=signal.getsignal(signal.SIGTERM);signal.signal(signal.SIGTERM,termination_signal)
    try:
        for label,key in [('worker','worker'),('verifier','verifier'),('postpins','postpins')]:supervise(m['commands'][key],out,label,deadline,resources,env)
        audit=read_json(out/'independent-audit.json');validate_audit_attestation(audit,approval_bind_sha256,m)
        require(read_json(out/'post-run-pins.json')['valid'] is True,'post-run pin check failed')
        require(time.monotonic()<deadline,'global deadline before acceptance')
        status='completed'
    except BaseException as exc:
        error=f'{type(exc).__name__}: {exc}'
        write_json(out/'failure.json',{'utc':utc(),'error':error,'status':'technical_failure','retry_permitted':False,'partial_outputs_retained':True})
    signal.signal(signal.SIGTERM,previous_sigterm)
    resources.pop('last_sample_monotonic',None);resources['retained_analysis_wall_seconds']=time.monotonic()-start;resources['retained_analysis_end_utc']=utc();resources['status']=status
    known=[p['label'] for p in resources['processes']]
    cleanup={'status':'incomplete' if any(p.get('cleanup',{}).get('live_members_after') for p in resources['processes']) else 'terminated_zombies_await_reaping' if any(p.get('cleanup',{}).get('members_after') for p in resources['processes']) else 'complete','owned_groups':[{k:p[k] for k in ('label','pid','state','cleanup') if k in p} for p in resources['processes']],'not_started_stages':[p for p in ('worker','verifier','postpins') if p not in known],'partial_outputs_retained':True,'retry_count':0}
    cleanup['native_case_states']=native_case_states(out)
    entries=output_inventory(out);unexpected=[p['path'] for p in entries if p['path'] not in m['output_inventory']]
    final_errors=['unplanned output files '+str(unexpected)] if unexpected else []
    def encode(value):return (json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    def prospective():
        run_record={'schema':'mvs-paired-candidate-run/v1','status':status,'error':error,'bind_sha256':approval_bind_sha256,'commands':m['commands'],'started':known,'not_started':[p for p in ('worker','verifier','postpins') if p not in known],'scientific_go':False,'production_changes':False,'finalization_errors':final_errors}
        pending={'resources.json':encode(resources),'cleanup.json':encode(cleanup),'run.json':encode(run_record)}
        files=[{**p,'sha256':digest(out/p['path'])} for p in entries]+[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in pending.items()]
        manifest={'schema':'mvs-paired-candidate-files/v1','self_excluded':True,'files':files,'total_bytes_before_manifest':sum(p['bytes'] for p in files),'finalization_errors':final_errors,'missing_planned_optional_or_failure_artifacts':[p for p in m['output_inventory'] if p not in {x['path'] for x in files} and p!='file-manifest.json']}
        pending['file-manifest.json']=encode(manifest)
        return pending,sum(p['bytes'] for p in entries)+sum(map(len,pending.values()))
    pending,total=prospective()
    if total>LIMITS['output_bytes']:final_errors.append('final evidence output limit')
    if final_errors:
        status='technical_failure';error='; '.join(([error] if error else [])+final_errors);resources['status']=status;resources['finalization_errors']=final_errors
        if not (out/'failure.json').exists():write_json(out/'failure.json',{'utc':utc(),'error':error,'status':status,'retry_permitted':False,'partial_outputs_retained':True})
        entries=output_inventory(out);pending,total=prospective()
    # Completion is written last, after output inventory/size preflight and all
    # other terminal artifacts. There is never a completed run after a failed gate.
    for name in ('resources.json','cleanup.json','file-manifest.json','run.json'):
        with (out/name).open('xb') as f:f.write(pending[name])
    return {'status':status,'error':error,'output_dir':str(out),'wall_seconds':resources['retained_analysis_wall_seconds']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare')
    for arg in ('root','out','protocol','r43','r44','r45','verifier-script'):p.add_argument('--'+arg,required=True)
    p.add_argument('--protocol-sha256',default=PROTOCOL_SHA);p.add_argument('--native-command',nargs=2,required=True);p.add_argument('--evidence',action='append',required=True)
    for name in ('verify','run','_worker','_postpins'):
        p=sub.add_parser(name);p.add_argument('--out',required=True)
        if name=='run':p.add_argument('--approval-bind-sha256',required=True)
    a=parser.parse_args(argv)
    try:
        if a.mode=='prepare':result=prepare(a.root,a.out,a.protocol,a.protocol_sha256,a.r43,a.r44,a.r45,a.native_command,a.verifier_script,a.evidence)
        elif a.mode=='verify':m=verify(a.out);result={'status':'verified','pins':len(m['pins'])}
        elif a.mode=='run':result=run(a.out,a.approval_bind_sha256)
        elif a.mode=='_worker':result=worker(a.out)
        else:
            require(os.environ.get('MVS_R46_SUPERVISED_BIND')==digest(Path(a.out)/'bind.json'),'supervisor-only postpins');m=verify(a.out);result={'valid':True,'pins_checked':len(m['pins']),'input_source_binary_runtime_unchanged':True};write_json(Path(a.out)/'post-run-pins.json',result)
        print(json.dumps(result,allow_nan=False));return 0 if result.get('status')!='technical_failure' else 1
    except Exception as exc:
        print(json.dumps({'status':'technical_failure','error':str(exc),'mode':a.mode}),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
