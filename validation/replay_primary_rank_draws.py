#!/usr/bin/env python3
"""Bounded independent replay of saved Round 27 primary-null label assignments.

No native engine, dataset generation, new seeds, new draws, or holdout access.
Integer cross-products determine every tail; floating values are checked only as
an additional compatibility assertion. Saved files contain aggregate counts, not
individual draw scores: assignment equivalence is established by SHA256.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
import signal
from pathlib import Path
import platform
import resource
import struct
import sys
import time

MASK = (1 << 64) - 1
GOLDEN = 0x9E3779B97F4A7C15
METRICS = ['median', 'standard_deviation', 'coefficient_of_variation', 'mad',
           'iqr', 'normalized_mad', 'normalized_iqr', 'mean', 'rms', 'range',
           'geometric_mean', 'trimmed_mean_20']
SCHEME = 'fresh-identity-Fisher-Yates-BenchmarkRandom.Next-first-nCase-with-replacement'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scramble(x):
    z = (x + GOLDEN) & MASK
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return z ^ (z >> 31)


def derive(seed, stage, condition, replication):
    for coordinate, multiplier in [(stage, GOLDEN), (condition, 0xC2B2AE3D27D4EB4F),
                                   (replication, 0x165667B19E3779F9)]:
        seed = scramble((seed + coordinate * multiplier) & MASK)
    return seed


def rotl(x, n):
    x &= MASK
    return ((x << n) | (x >> (64 - n))) & MASK


class Random:
    def __init__(self, seed):
        require(type(seed) is int and 0 <= seed <= MASK, 'invalid UInt64 seed')
        self.state = [scramble((seed + i * GOLDEN) & MASK) for i in range(4)]
        if not any(self.state):
            self.state[0] = GOLDEN

    def next64(self):
        a, b, c, d = self.state
        result = (rotl(b * 5, 7) * 9) & MASK
        t = (b << 17) & MASK
        c ^= a
        d ^= b
        b ^= c
        a ^= d
        c ^= t
        self.state = [a, b, c, rotl(d, 45)]
        return result

    def next(self, bound):
        require(type(bound) is int and 0 < bound <= 2**31 - 1, 'invalid bound')
        threshold = (1 << 64) % bound
        while True:
            value = self.next64()
            if value >= threshold:
                return value % bound


def assignments(n, m, count, rng):
    require(type(n) is int and type(m) is int and 0 < m < n <= 128,
            'invalid assignment size')
    require(type(count) is int and count > 0, 'invalid draw count')
    for _ in range(count):
        p = list(range(n))
        for i in range(n - 1, 0, -1):
            k = rng.next(i + 1)
            p[i], p[k] = p[k], p[i]
        yield p[:m]


def label_bytes(selected, n, m):
    require(len(selected) == m and len(set(selected)) == m and
            all(type(i) is int and 0 <= i < n for i in selected), 'invalid selection')
    return bytes(int(i in selected) for i in range(n))


def ranks(rows):
    require(isinstance(rows, list) and 2 <= len(rows) <= 128, 'invalid matrix height')
    require(all(isinstance(r, list) and len(r) == 12 for r in rows), 'incomplete matrix')
    require(all(type(v) in (int, float) and math.isfinite(v) for r in rows for v in r),
            'nonfinite/nonnumeric matrix')
    n = len(rows)
    # Direct counts, independent of the native sorted tie-block implementation.
    return [[2 * sum(r[j] < row[j] for r in rows) +
             sum(r[j] == row[j] for r in rows) - n for j in range(12)] for row in rows]


def compare(left, right):
    delta = left[0] * right[1] - right[0] * left[1]
    return (delta > 0) - (delta < 0)


def score(a, selected, q):
    n, m = len(a), len(selected)
    label_bytes(selected, n, m)
    return [(sum(a[i][j] for i in selected)**2 * n * (n - 1), m * (n - m) * q[j])
            if q[j] else (0, 1) for j in range(12)]


def maximum(scores):
    best = 0
    for j in range(1, 12):
        if compare(scores[j], scores[best]) > 0:
            best = j
    return best


def checked_compare(x, y):
    exact = compare(x, y)
    a, b = x[0] / x[1], y[0] / y[1]
    require(exact == (a > b) - (a < b), 'binary64 splits exact ordering/tie')
    return exact


def evaluate(rows, observed, draws, count):
    a = ranks(rows)
    n, m = len(rows), len(observed)
    q = [sum(r[j]**2 for r in a) for j in range(12)]
    obs = score(a, observed, q)
    oi = maximum(obs)
    digest = hashlib.sha256(struct.pack('<iii', n, m, count))
    marginal, max_t, global_count = [0]*12, [0]*12, 0
    seen, identities, duplicates = set(), 0, 0
    actual_count = 0
    for selected in draws:
        labels = label_bytes(selected, n, m)
        digest.update(labels)
        identities += labels == label_bytes(observed, n, m)
        duplicates += labels in seen
        seen.add(labels)
        s = score(a, selected, q)
        mi = maximum(s)
        for j in range(12):
            checked_compare(s[j], s[mi])
            marginal[j] += checked_compare(s[j], obs[j]) >= 0
            max_t[j] += checked_compare(s[mi], obs[j]) >= 0
        global_count += checked_compare(s[mi], obs[oi]) >= 0
        actual_count += 1
    require(actual_count == count, 'draw count mismatch')
    return dict(ranks=a, q=q, exact=obs, maximumIndex=oi,
                marginalExceedanceCounts=marginal, maxTExceedanceCounts=max_t,
                globalExceedanceCount=global_count, sampledLabelHash=digest.hexdigest(),
                identities=identities, duplicateAssignments=duplicates, drawsChecked=actual_count)


def validate_input(document, replication):
    require(document['schemaVersion'] == 'mvs-global-rank-native/v1' and
            document['status'] == 'ok' and document['mode'] == '--case', 'invalid native envelope')
    e = document['evidence']
    for obj in [document, e]:
        require(type(obj['conditionOrdinal']) is int and obj['conditionOrdinal'] == 0 and
                type(obj['replication']) is int and obj['replication'] == replication,
                'coordinate mismatch')
    expected = dict(condition='primary_gait_heavy_tail_null', plannedConditionCount=200,
                    dataMaster=20260904, dataStage=1, dataStream=1,
                    labelMaster=2026102601, labelStage=26,
                    datasetSeed=derive(20260904, 1, 1, replication),
                    labelSeed=derive(2026102601, 26, 0, replication), metricOrder=METRICS,
                    groupNames=['control', 'case'], groupCounts=[16, 16], validRows=1280,
                    observedCaseIndices=list(range(16, 32)))
    for key, value in expected.items():
        require(e[key] == value and type(e[key]) is type(value), f'{key} mismatch')
    require(e['entities'] == [dict(entity=f'{g}_{i:02}', group=g, measurements=40)
                            for g in ['control', 'case'] for i in range(1, 17)], 'entity mapping mismatch')
    rows = e['summaryRows']
    ranks(rows)
    require(len(rows) == 32, 'primary sample size mismatch')
    require(sha(b''.join(struct.pack('<d', x) for r in rows for x in r)) == e['summarySha256'],
            'matrix digest mismatch')
    require(e['candidate']['drawCount'] == 999, 'saved B mismatch')
    provenance = document['provenance']
    require(provenance['drawScheme'] == SCHEME and provenance['draws'] == 999,
            'draw provenance mismatch')
    return e


def check_case(document, replication, evidence_callback=None):
    e = validate_input(document, replication)
    candidate = e['candidate']
    result = evaluate(e['summaryRows'], e['observedCaseIndices'],
                      assignments(32, 16, 999, Random(e['labelSeed'])), 999)
    if evidence_callback is not None:
        evidence_callback(result)
    observed = candidate['observed']
    require(observed['exact'] == [dict(numerator=n, denominator=d) for n, d in result['exact']],
            'exact observed scores mismatch')
    values = [n/d for n, d in result['exact']]
    require(observed['values'] == values and observed['maximumIndex'] == result['maximumIndex'] and
            e['observedMaximum'] == values[result['maximumIndex']], 'observed values/max mismatch')
    for x in result['exact']:
        for y in result['exact']:
            checked_compare(x, y)
    for key in ['sampledLabelHash', 'marginalExceedanceCounts', 'maxTExceedanceCounts',
                'globalExceedanceCount']:
        require(candidate[key] == result[key], f'{key} mismatch: saved={candidate[key]!r}, replay={result[key]!r}')
    marginal = [Fraction(c+1, 1000) for c in result['marginalExceedanceCounts']]
    max_p = [Fraction(c+1, 1000) for c in result['maxTExceedanceCounts']]
    gp = Fraction(result['globalExceedanceCount']+1, 1000)
    for key, value in [('globalPValue', float(gp)), ('marginalPValues', list(map(float, marginal))),
                       ('maxTAdjustedPValues', list(map(float, max_p))),
                       # Native multiplication uses binary64; exact decisions checked below.
                       ('bonferroniAdjustedPValues', [min(1., 12*float(p)) for p in marginal])]:
        require(candidate[key] == value, f'{key} mismatch')
    decisions = dict(globalReject=gp < Fraction(1, 20),
                     bonferroniReject=any(12*p < Fraction(1, 20) for p in marginal),
                     fixedMedianReject=marginal[0] < Fraction(1, 20),
                     fixedCvReject=marginal[2] < Fraction(1, 20))
    for key, value in decisions.items():
        require(type(candidate[key]) is bool and candidate[key] == value, f'{key} mismatch')
    require(gp == min(max_p), 'global/maxT identity mismatch')
    return dict(replication=replication, status='passed', summarySha256=e['summarySha256'],
                datasetSeed=e['datasetSeed'], labelSeed=e['labelSeed'], **result, **decisions,
                globalPExact=[gp.numerator, gp.denominator])


def load(path):
    require(path.stat().st_size <= 4*1024*1024, 'input exceeds 4 MiB')
    return json.loads(path.read_bytes())


def checkpoint_records(checkpoint):
    records = checkpoint['records']
    require(checkpoint['planned'] == 1300 and len(records) == 1300, 'incomplete checkpoint')
    expected = {(o, r) for o in range(6) for r in range(200 if o < 4 else 250)}
    require({(r['conditionOrdinal'], r['replication']) for r in records} == expected,
            'checkpoint coordinates missing/duplicated')
    primary = sorted((r for r in records if r['conditionOrdinal'] == 0), key=lambda r:r['replication'])
    for r in primary:
        require(r['status'] == 'completed' and r['exitCode'] == 0 and
                r['result'] == f"0-{r['replication']:04}.json", 'invalid primary checkpoint record')
    return primary


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    require(not out.is_relative_to(root) and not out.is_relative_to(args.inputs.resolve()),
            'output must be outside source and saved inputs')
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    # Single process; hard address-space and CPU caps, cooperative wall deadline.
    resource.setrlimit(resource.RLIMIT_AS, (1024*1024*1024, 1024*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (600, 605))
    os.sched_setaffinity(0, {0, 1})
    def timeout(signum, frame):
        raise TimeoutError('600-second wall-time limit reached')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(600)
    summary = dict(schemaVersion='mvs-primary-label-replay/v1', status='running',
                   inputDirectory=str(args.inputs.resolve()), casesCompleted=0, plannedDenominator=200,
                   scope='all 200 existing primary null cases; same 999 labels per case',
                   python=sys.version, platform=platform.platform(),
                   programSha256=sha(Path(__file__).read_bytes()),
                   limits=dict(workers=1, memoryMiB=1024, cpuSeconds=600, wallSeconds=600, cpuAffinity=sorted(os.sched_getaffinity(0))),
                   inputs=[], sourceHashes={})
    current = None
    try:
        require(sha(args.plan.read_bytes()) == args.plan_sha256, 'plan SHA256 mismatch')
        plan = load(args.plan)
        summary['planSha256'] = args.plan_sha256
        summary['planId'] = plan['id']
        for file, key in [('checkpoint.json', 'stage27CheckpointSha256'),
                          ('run.json', 'stage27RunSha256'), ('report.json', 'stage27ReportSha256')]:
            require(sha((args.inputs/file).read_bytes()) == plan['inputs'][key], f'{file} SHA256 mismatch')
        summary['metadataHashes'] = {k:v for k,v in plan['inputs'].items() if k != 'files'}
        run = load(args.inputs/'run.json')
        require(run['mode'] == 'development' and run['planned'] == 1300, 'invalid saved run')
        checkpoint = args.inputs/'checkpoint.json'
        records = checkpoint_records(load(checkpoint))
        for name in ['Benchmark/BenchmarkRandom.cs', 'validation/global_rank_experiment/Program.cs',
                     'validation/global_rank_experiment/RankKernel.cs',
                     'validation/test_replay_primary_rank_draws.py']:
            summary['sourceHashes'][name] = sha((root/name).read_bytes())
            if name != 'validation/test_replay_primary_rank_draws.py':
                require(summary['sourceHashes'][name] == run['provenance']['sourceHashes'][name],
                        f'saved run source binding mismatch: {name}')
        require(plan['inputs']['files'] == {r['result']:r['resultSha256'] for r in records},
                'plan/checkpoint primary bindings mismatch')
        provenance = None
        rejections = 0
        for record in records:
            current = record['replication']
            require(time.monotonic()-started < 600, 'wall-time limit reached')
            file = args.inputs/record['result']
            digest = sha(file.read_bytes())
            require(digest == record['resultSha256'], f'checkpoint file SHA256 mismatch: {file.name}')
            summary['inputs'].append(dict(file=file.name, sha256=digest))
            document = load(file)
            if provenance is None:
                provenance = document['provenance']
                summary['savedNativeProvenance'] = provenance
            require(document['provenance'] == provenance, 'mixed native provenance')
            require(document['provenance']['harnessSha256'] == run['provenance']['binarySha256'] and
                    document['provenance']['coreSha256'] == run['provenance']['binaryHashes']['MvsAnalyzer.Core.dll'],
                    'saved native binary binding mismatch')
            case_started = time.monotonic()
            result = check_case(document, current,
                                lambda result: write(out/f'reconstruction-{current:04}.json', result))
            result['elapsedSeconds'] = time.monotonic()-case_started
            result['peakRssKiB'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            result['inputSha256'] = digest
            write(out/file.name, result)
            rejections += result['globalReject']
            summary['casesCompleted'] += 1
        require(rejections == 19, 'saved primary 19/200 rejection tally mismatch')
        summary.update(status='passed', globalRejections=rejections, globalNonrejections=200-rejections,
                       assignmentsChecked=200*999)
    except Exception as error:
        summary.update(status='failed', failedReplication=current,
                       error=f'{type(error).__name__}: {error}')
    if summary['status'] == 'failed':
        write(out/'failure.json', dict(replication=current, error=summary['error']))
    summary['notStartedReplications'] = list(range((current+1) if current is not None else 0, 200))
    summary['failedReplications'] = [current] if summary['status'] == 'failed' and current is not None else []
    summary['elapsedSeconds'] = time.monotonic()-started
    signal.alarm(0)
    summary['peakRssKiB'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    write(out/'summary.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs', 'sourceHashes']}, indent=2))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
