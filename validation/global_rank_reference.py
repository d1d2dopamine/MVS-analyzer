#!/usr/bin/env python3
"""Independent exact rational oracle for the complete-vector global rank null.

No simulation RNG, production import, or automatic native execution. Whole entity
vectors are exchangeable; a single fixed-size label assignment applies to all 12
slots. Exhaustive p values have no Monte Carlo plus-one correction.
"""
from __future__ import annotations
import argparse
from collections import Counter
from fractions import Fraction
from itertools import combinations
import json
import math
import statistics
from pathlib import Path

FIXTURES = Path(__file__).with_name('global-rank-fixtures-v1.json')
FAMILY_SIZE = 12
ALPHA = Fraction(1, 20)


def validate_matrix(rows):
    if not isinstance(rows,(list,tuple)) or len(rows) < 2:
        raise ValueError('at least two complete entity vectors required')
    if any(not isinstance(row,(list,tuple)) or len(row) != FAMILY_SIZE for row in rows):
        raise ValueError('each entity must have all 12 slots')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
           for row in rows for x in row):
        raise ValueError('every slot must be finite and numeric')


def validate_selected(selected, n, size=None):
    if (any(type(i) is not int or not 0 <= i < n for i in selected)
            or len(set(selected)) != len(selected)
            or not 0 < len(selected) < n
            or (size is not None and len(selected) != size)):
        raise ValueError('invalid fixed-size entity assignment')


def rank_matrix(rows):
    """Return integer doubled centered midranks, by entity and slot."""
    validate_matrix(rows)
    n = len(rows)
    out = [[0] * FAMILY_SIZE for _ in rows]
    for j in range(FAMILY_SIZE):
        order = sorted(range(n), key=lambda i: rows[i][j])
        lo = 0
        while lo < n:
            hi = lo + 1
            while hi < n and rows[order[hi]][j] == rows[order[lo]][j]:
                hi += 1
            # Average one-based rank = (lo + 1 + hi)/2.
            for i in order[lo:hi]:
                out[i][j] = lo + hi - n
            lo = hi
    return out


def _rank_scores(a, selected):
    n, m = len(a), len(selected)
    result = []
    for j in range(FAMILY_SIZE):
        d = sum(a[i][j] for i in selected)
        q = sum(row[j] ** 2 for row in a)
        result.append(Fraction(d*d*n*(n-1), m*(n-m)*q) if q else Fraction(0))
    return result


def scores(rows, selected):
    validate_matrix(rows)
    validate_selected(selected, len(rows))
    return _rank_scores(rank_matrix(rows), selected)


def enumerate_orbit(rows, n_case):
    a = rank_matrix(rows)
    if type(n_case) is not int or not 0 < n_case < len(rows):
        raise ValueError('invalid case count')
    result = []
    for selected in combinations(range(len(rows)), n_case):
        s = _rank_scores(a, selected)
        result.append(dict(selected=list(selected), scores=s, maxScore=max(s)))
    return result


def exhaustive_tails(orbit, observed_scores):
    count = len(orbit)
    if not count:
        raise ValueError('empty orbit')
    max_counts = [sum(x['maxScore'] >= observed_scores[j] for x in orbit) for j in range(FAMILY_SIZE)]
    marginal = [sum(x['scores'][j] >= observed_scores[j] for x in orbit)
                for j in range(FAMILY_SIZE)]
    global_count = sum(x['maxScore'] >= max(observed_scores) for x in orbit)
    return dict(maxTCounts=max_counts, maxTP=[Fraction(c,count) for c in max_counts],
                marginalCounts=marginal, globalCount=global_count,
                marginalP=[Fraction(c, count) for c in marginal],
                globalP=Fraction(global_count, count), orbitSize=count)


def monte_carlo(rows, observed, draws):
    validate_selected(observed, len(rows))
    a = rank_matrix(rows)
    for draw in draws:
        validate_selected(draw, len(rows), len(observed))
    obs = _rank_scores(a, observed)
    ds = [_rank_scores(a, draw) for draw in draws]
    counts = [sum(s[j] >= obs[j] for s in ds) for j in range(FAMILY_SIZE)]
    gc = sum(max(s) >= max(obs) for s in ds)
    max_counts = [sum(max(s) >= obs[j] for s in ds) for j in range(FAMILY_SIZE)]
    return dict(maxTCounts=max_counts,maxTP=[Fraction(1+c,len(ds)+1) for c in max_counts],
                observedScores=obs, observedMaxScore=max(obs), drawScores=ds,
                drawMaxScores=[max(s) for s in ds], marginalCounts=counts,
                globalCount=gc, marginalP=[Fraction(1+c, len(ds)+1) for c in counts],
                globalP=Fraction(1+gc, len(ds)+1))


def rejects(count, draws, bonferroni=False):
    if not 0 <= count <= draws:
        raise ValueError('invalid exceedance count')
    return Fraction(1+count, 1+draws) * (12 if bonferroni else 1) < ALPHA


def wilson95(successes, n):
    if not 0 <= successes <= n or n <= 0:
        raise ValueError('invalid binomial counts')
    z = 1.959963984540054
    p, z2 = successes/n, z*z
    center = (p+z2/(2*n))/(1+z2/n)
    half = z*math.sqrt(p*(1-p)/n+z2/(4*n*n))/(1+z2/n)
    return [max(0., center-half), min(1., center+half)]


def mcnemar_one_sided(b, c):
    """Exact P[Binomial(b+c,1/2)>=b]; b denotes gain, c loss."""
    if any(type(x) is not int or x < 0 for x in (b,c)):
        raise ValueError('invalid discordances')
    return Fraction(sum(math.comb(b+c,k) for k in range(b,b+c+1)), 2**(b+c))


def paired_delta_bounds(b, c, n):
    """Conservative simultaneous 95% interval via two 97.5% two-sided CP CIs."""
    if any(type(x) is not int for x in (b,c,n)) or min(b,c)<0 or n<=0 or b+c>n:
        raise ValueError('invalid paired counts')
    import scipy
    from scipy.stats import beta
    tail = .0125
    def cp(k):
        return [0. if k == 0 else float(beta.ppf(tail,k,n-k+1)),
                1. if k == n else float(beta.ppf(1-tail,k+1,n-k))]
    lb,ub = cp(b)
    lc,uc = cp(c)
    return dict(delta=(b-c)/n, bounds=[lb-uc,ub-lc], bInterval=[lb,ub],
                cInterval=[lc,uc], componentConfidence=.975,
                implementation={'library':'scipy','version':scipy.__version__,
                                'function':'scipy.stats.beta.ppf'})


def verify_independent_algebra(rows, n_case):
    """Crosscheck with direct count ranks and tie-block variance, not sorted runs."""
    a = rank_matrix(rows)
    n = len(rows)
    ranks, variances = [], []
    for j in range(12):
        col = [r[j] for r in rows]
        r = [Fraction(2*sum(y<x for y in col)+sum(y==x for y in col)+1,2) for x in col]
        correction = sum(t**3-t for t in Counter(col).values())
        v = Fraction(n_case*(n-n_case),12)*(n+1-Fraction(correction,n*(n-1)))
        if [2*x-(n+1) for x in r] != [row[j] for row in a]:
            raise AssertionError('direct rank versus sorted-run midrank mismatch')
        q = sum(row[j]**2 for row in a)
        if v != Fraction(n_case*(n-n_case)*q,4*n*(n-1)):
            raise AssertionError('tie-correction variance versus Q mismatch')
        ranks.append(r); variances.append(v)
    orbit = enumerate_orbit(rows,n_case)
    for observed in orbit:
        for j,t in enumerate(observed['scores']):
            centered = sum(ranks[j][i] for i in observed['selected'])-Fraction(n_case*(n+1),2)
            direct = centered**2/variances[j] if variances[j] else Fraction(0)
            if t != direct:
                raise AssertionError('independent tie variance score mismatch')
    return dict(passed=True,assignmentsChecked=len(orbit),method='direct-count ranks and Counter tie-correction variance')


def compare_raw_fixtures(fixtures, native):
    """Independent basic summary arithmetic and expected retention/mapping checks."""
    results=[]
    by_id={f['id']:f for f in native['rawFixtures']}
    if set(by_id) != {f['id'] for f in fixtures['rawFixtures']}:
        raise AssertionError('raw fixture IDs mismatch')
    def summaries(values):
        x=sorted(values); n=len(x)
        def quantile(p):
            pos=(n-1)*p; lo=math.floor(pos); hi=math.ceil(pos)
            return x[lo]+(x[hi]-x[lo])*(pos-lo)
        med=statistics.median(x); mean=statistics.mean(x)
        sd=statistics.stdev(x); mad=statistics.median([abs(y-med) for y in x])
        iqr=quantile(.75)-quantile(.25); trim=math.floor(.2*n)
        return [med,sd,sd/abs(mean),mad,iqr,mad/abs(med),iqr/abs(med),mean,
                math.sqrt(sum(y*y for y in x)/n),x[-1]-x[0],
                math.exp(sum(math.log(y) for y in x)/n),statistics.mean(x[trim:n-trim])]
    for f in fixtures['rawFixtures']:
        got=by_id[f['id']]
        if got['status'] != 'ok' or len(got['summaryRows']) != f['expectedRetainedCount']:
            raise AssertionError('raw retention count/status mismatch')
        if got['validRows'] != f['expectedValidRows']:
            raise AssertionError('raw valid row count mismatch')
        expected=f['expectedRetainedEntities']
        if [{'Entity':x['entity'],'Group':x['group']} for x in got['entities']] != expected:
            raise AssertionError('raw entity/group order mismatch')
        validate_matrix(got['summaryRows'])
        max_abs_error = max_rel_error = 0.0
        for entity,actual,mapping in zip(expected,got['summaryRows'],got['entities']):
            values=[o['Value'] for o in f['observations'] if o['Entity']==entity['Entity'] and o['Group']==entity['Group'] and isinstance(o['Value'],(int,float)) and math.isfinite(o['Value']) and -1000000 <= o['Value'] <= 1000000]
            if mapping['measurements'] != len(values):
                raise AssertionError('retained measurement count mismatch')
            for x,y in zip(actual,summaries(values)):
                _close(x,y,'independent raw summary')
                max_abs_error=max(max_abs_error,abs(x-y))
                max_rel_error=max(max_rel_error,abs(x-y)/abs(y) if y else 0.)
        groups=list(dict.fromkeys(x['Group'] for x in expected))
        if got['groupNames'] != groups or got['groupCounts'] != [sum(x['Group']==g for x in expected) for g in groups]:
            raise AssertionError('raw group mapping mismatch')
        results.append(dict(id=f['id'],passed=True,entitiesChecked=len(expected),summarySlotsChecked=12*len(expected),maxAbsoluteError=max_abs_error,maxRelativeError=max_rel_error,absoluteTolerance=2e-13,relativeTolerance=2e-13))
    failures={x['id']:x for x in native['expectedFailureRawFixtures']}
    if set(failures) != {x['id'] for x in fixtures.get('expectedFailureRawFixtures',[])}:
        raise AssertionError('raw expected-failure IDs mismatch')
    for f in fixtures.get('expectedFailureRawFixtures',[]):
        if failures[f['id']]['status'] != 'rejected' or failures[f['id']]['stage'] != f['expectedFailureStage']:
            raise AssertionError('invalid raw candidate was not rejected')
        results.append(dict(id=f['id'],passed=True,expectedFailure=True))
    if not native['invalidInputChecks'] or any(x['rejected'] is not True for x in native['invalidInputChecks']):
        raise AssertionError('native invalid-input rejection failed')
    return results


def _jsonable(value):
    if isinstance(value, Fraction):
        return {'numerator': value.numerator, 'denominator': value.denominator}
    if isinstance(value, dict):
        return {k:_jsonable(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [_jsonable(v) for v in value]
    return value


def _close(actual, expected, where):
    if isinstance(actual, bool) or not isinstance(actual,(int,float)) or not math.isfinite(actual):
        raise AssertionError(f'{where}: invalid native numeric value {actual!r}')
    if not math.isclose(actual,float(expected),rel_tol=2e-13,abs_tol=2e-13):
        raise AssertionError(f'{where}: native {actual!r} != rational {expected}')


def compare_native(fixture, native):
    """Validate native values, exact rational tie/order classes, tails, and max helper."""
    rows, observed = fixture['rows'], fixture['observed']
    orbit = enumerate_orbit(rows, fixture['nCase'])
    mc = monte_carlo(rows, observed, fixture['draws'])
    a = rank_matrix(rows)
    if 'doubledCenteredRanks' in native and native['doubledCenteredRanks'] != a:
        raise AssertionError('native midrank mismatch')
    if 'q' in native and native['q'] != [sum(r[j]**2 for r in a) for j in range(12)]:
        raise AssertionError('native rank Q mismatch')
    assignments = native['allAssignments']
    if len(assignments) != len(orbit):
        raise AssertionError('native orbit size mismatch')
    by_assignment = {tuple(x['selected']):x for x in assignments}
    if len(by_assignment) != len(orbit):
        raise AssertionError('duplicate native orbit assignment')
    classes = {}
    for exact in orbit:
        got = by_assignment[tuple(exact['selected'])]
        if len(got['scores']) != 12:
            raise AssertionError('native incomplete score vector')
        for j,(x,y) in enumerate(zip(got['scores'], exact['scores'])):
            _close(x,y,f'orbit slot {j}')
            classes.setdefault(y,[]).append(x)
        _close(got['maxScore'],exact['maxScore'],'orbit max')
        if got['maxScore'] != max(got['scores']):
            raise AssertionError('double max helper mismatch')
    previous = None
    for rational, doubles in sorted(classes.items()):
        if previous is not None and not previous < min(doubles):
            raise AssertionError('native cross-column score ordering mismatch')
        # Exact comparison ties must not be split by operational rounding.
        if max(doubles) != min(doubles):
            raise AssertionError('native rational tie mismatch')
        previous = max(doubles)
    for key in ('observedScores','drawMaxScores','marginalP','maxTP'):
        if len(native[key]) != len(mc[key]):
            raise AssertionError(f'{key}: length mismatch')
        for x,y in zip(native[key], mc[key]):
            _close(x,y,key)
    if len(native['drawScores']) != len(mc['drawScores']):
        raise AssertionError('draw count mismatch')
    for xs,ys in zip(native['drawScores'],mc['drawScores']):
        if len(xs) != 12:
            raise AssertionError('draw score width mismatch')
        for x,y in zip(xs,ys):
            _close(x,y,'draw score')
    if native['observedMaxScore'] != max(native['observedScores']):
        raise AssertionError('observed double max helper mismatch')
    if any(m != max(s) for m,s in zip(native['drawMaxScores'],native['drawScores'])):
        raise AssertionError('draw double max helper mismatch')
    if native['globalP'] != min(native['maxTP']):
        raise AssertionError('global p versus minimum maxT p mismatch')
    for key in ('observedMaxScore','globalP'):
        _close(native[key],mc[key],key)
    for key in ('marginalCounts','globalCount','maxTCounts'):
        if native[key] != mc[key]:
            raise AssertionError(f'{key}: inclusive MC count mismatch')
    # Every assignment acts as observed; compare native inclusive orbit tails.
    for exact in orbit:
        got = by_assignment[tuple(exact['selected'])]
        tail = exhaustive_tails(orbit,exact['scores'])
        for native_key,oracle_key in [('globalTailCount','globalCount'),('marginalTailCounts','marginalCounts'),('maxTailCounts','maxTCounts')]:
            if got[native_key] != tail[oracle_key]:
                raise AssertionError(f'{native_key}: exact tail mismatch')
        if len(got['otherAssignmentMaxTP']) != 12:
            raise AssertionError('other-assignment maxT width mismatch')
        for x,y in zip(got['otherAssignmentMaxTP'],tail['maxTP']):
            _close(x,y,'other-assignment maxT identity')
            if (x < .05) != (y < ALPHA):
                raise AssertionError('other-assignment strict decision mismatch')
        # Ordering in binary64 can split exact ties. Inclusive comparisons must
        # preserve exact classes, so these counts deliberately use raw >=.
        counts = [sum(x['scores'][j]>=got['scores'][j] for x in assignments) for j in range(12)]
        gc = sum(x['maxScore']>=got['maxScore'] for x in assignments)
        max_counts = [sum(x['maxScore']>=got['scores'][j] for x in assignments) for j in range(12)]
        if counts != tail['marginalCounts'] or gc != tail['globalCount'] or max_counts != tail['maxTCounts']:
            raise AssertionError('native inclusive exhaustive tail mismatch')
    rejected = sum(exhaustive_tails(orbit,x['scores'])['globalP'] < ALPHA for x in orbit)
    if Fraction(rejected,len(orbit)) > ALPHA:
        raise AssertionError('exact strict rejection fraction exceeds alpha')
    return {'id':fixture['id'],'passed':True,'orbitSize':len(orbit),
            'observedAssignmentsChecked':len(orbit)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',type=Path,default=FIXTURES)
    parser.add_argument('--native',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    fixtures=json.loads(args.fixtures.read_text())
    if fixtures['schemaVersion'] != 'mvs-global-rank-fixtures/v1':
        raise ValueError('unsupported fixture schema')
    result={'schemaVersion':'mvs-global-rank-reference/v1','matrixFixtures':[]}
    for f in fixtures['matrixFixtures']:
        validate_selected(f['observed'],len(f['rows']),f['nCase'])
        algebra=verify_independent_algebra(f['rows'],f['nCase'])
        orbit=enumerate_orbit(f['rows'],f['nCase'])
        result['matrixFixtures'].append(dict(id=f['id'],independentAlgebra=algebra,allAssignments=[dict(x,**exhaustive_tails(orbit,x['scores'])) for x in orbit],**monte_carlo(f['rows'],f['observed'],f['draws'])))
    if args.native:
        native=json.loads(args.native.read_text())
        if native['schemaVersion'] != 'mvs-global-rank-native/v1':
            raise ValueError('unsupported native schema')
        native = native.get('evidence',native)
        by_id={x['id']:x for x in native['matrixFixtures']}
        if set(by_id) != {f['id'] for f in fixtures['matrixFixtures']}:
            raise AssertionError('native fixture IDs mismatch')
        result['nativeComparison']=[compare_native(f,by_id[f['id']]) for f in fixtures['matrixFixtures']]
        result['rawComparison']=compare_raw_fixtures(fixtures,native)
    args.out.write_text(json.dumps(_jsonable(result),indent=2)+'\n')

if __name__ == '__main__':
    main()
