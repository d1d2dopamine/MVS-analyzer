#!/usr/bin/env python3
"""Bounded, fail-closed global-rank development runner (never a holdout runner).

Modes: replay, development, report. Outputs must be fresh and outside the source
checkout. No resume, retries, replacement cases, reduced pilots, or force option.
See protocol_contract() for the explicit frozen protocol fields. Gate manifests
are evidence attestations, not a substitute for independent scientific review.
Oracle gate schema: schemaVersion=mvs-global-rank-gate/v1, kind=oracle,
passed=true, mismatches=failures=0, allAssignmentsChecked=rawFixturesPassed=true,
orbitSizes=[70,126,252], evidenceFiles={relativeFilename: sha256}, and provenance
exactly as returned by provenance(dll, protocol, fixtures). Parent reviewers issue
this manifest only after inspecting independent/native oracle evidence. Replay
manifests are emitted here and every saved completed replay record is revalidated.
Report mode never launches cases; it validates all saved records and gate hashes.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path
import signal
import statistics
import struct
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
COUNTS = (200, 200, 200, 200, 250, 250)
CONDITIONS = ('primary_null', 'shape_normal_null', 'robust_null_10',
              'design_voice_null', 'power_location_105', 'power_dispersion_130')
NATIVE_CONDITIONS = ('primary_gait_heavy_tail_null', 'gait_normal_null',
                     'gait_heavy_tail_contamination_10pct_null', 'voice_lognormal_null',
                     'gait_location_1.05', 'gait_dispersion_1.30')
METHODS = ('shipped', 'candidate', 'permutationBonferroni', 'fixedMedian', 'fixedCv')
ARCHIVE = ROOT / 'benchmark_history/1.4.0-engine-1.6.2-MVS-BENCH-1.2.0'
METRIC_ORDER = ['median', 'standard_deviation', 'coefficient_of_variation', 'mad', 'iqr', 'normalized_mad', 'normalized_iqr', 'mean', 'rms', 'range', 'geometric_mean', 'trimmed_mean_20']
MEMORY_LIMIT = 1024 ** 3
WALL_LIMIT = 20 * 60


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))


def write(path, obj):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def protocol_contract():
    return {'schemaVersion': 'mvs-global-rank-development/v1',
     'protocolId': 'R27-GLOBAL-MAXRANK-DEV-1',
     'status': 'frozen_pre_pilot',
     'scientificReadiness': 'NO-GO retained',
     'productionActivation': False,
     'conditions': [{'ordinal': 0,
                     'id': 'primary_null',
                     'count': 200,
                     'design': 'gait',
                     'shape': 'heavy_tail',
                     'injection': 'none',
                     'effect': 1,
                     'contamination': 0,
                     'dataStage': 1,
                     'dataStream': 1},
                    {'ordinal': 1,
                     'id': 'shape_normal_null',
                     'count': 200,
                     'design': 'gait',
                     'shape': 'normal',
                     'injection': 'none',
                     'effect': 1,
                     'contamination': 0,
                     'dataStage': 4,
                     'dataStream': 0},
                    {'ordinal': 2,
                     'id': 'robust_null_10',
                     'count': 200,
                     'design': 'gait',
                     'shape': 'heavy_tail',
                     'injection': 'none',
                     'effect': 1,
                     'contamination': 0.1,
                     'dataStage': 3,
                     'dataStream': 1},
                    {'ordinal': 3,
                     'id': 'design_voice_null',
                     'count': 200,
                     'design': 'voice',
                     'shape': 'lognormal',
                     'injection': 'none',
                     'effect': 1,
                     'contamination': 0,
                     'dataStage': 4,
                     'dataStream': 12},
                    {'ordinal': 4,
                     'id': 'power_location_105',
                     'count': 250,
                     'design': 'gait',
                     'shape': 'heavy_tail',
                     'injection': 'location',
                     'effect': 1.05,
                     'contamination': 0,
                     'dataStage': 2,
                     'dataStream': 1},
                    {'ordinal': 5,
                     'id': 'power_dispersion_130',
                     'count': 250,
                     'design': 'gait',
                     'shape': 'heavy_tail',
                     'injection': 'dispersion',
                     'effect': 1.3,
                     'contamination': 0,
                     'dataStage': 2,
                     'dataStream': 1}],
     'dataMasterSeed': 20260904,
     'permutationMasterSeed': 2026102601,
     'permutationStage': 26,
     'draws': 999,
     'alpha': 0.05,
     'familySize': 12,
     'fixedComparators': {'medianIndex': 0,
                          'cvIndex': 2,
                          'method': 'same-draw marginal permutation; strict p<.05'},
     'arithmetic': {'operational': 'exact rational doubled-midrank scores; inclusive rational >=',
                    'doubleHelper': 'double scores and existing MaxT helper must match exact order and '
                                    'counts; mismatch fails entire case',
                    'noContinuityCorrection': True,
                    'maximumEntities': 128,
                    'oracleScalarValueAbsoluteTolerance': 2e-13,
                    'oracleScalarValueRelativeTolerance': 2e-13,
                    'countOrderingTieTolerance': 0},
     'availability': 'Build unchanged; two groups at least4 each; complete12finite summary slots; '
                     'synthetic expected entity count preserved; any candidate failure retained, never '
                     'converted to non-rejection',
     'pilotRequirements': {'oracleMismatches': 0,
                           'unexplainedReplayMismatches': 0,
                           'invalidCases': 0,
                           'allFourNullConditionsEligible': True,
                           'powerDeltaNonnegativeBoth': True,
                           'powerDeltaAtLeastOne': 0.05,
                           'strongerLabelMcNemarAnyEndpointBelow': 0.025},
     'nullIntervals': {'method': 'two-sided Wilson95',
                       'eligibleUpperAtMost': 0.1,
                       'inflationLowerAbove': 0.075,
                       'other': 'inconclusive'},
     'pairedIntervals': {'method': 'conservative discordance Clopper-Pearson difference',
                         'individualBinomialConfidence': 0.975,
                         'betaLowerQuantile': 0.0125,
                         'betaUpperQuantile': 0.9875,
                         'differenceLower': 'L(b)-U(c)',
                         'differenceUpper': 'U(b)-L(c)',
                         'coverage': 'at least95% marginal for each paired difference, not '
                                     'simultaneous across4',
                         'mcnemar': 'sum k=b..b+c choose(b+c,k)/2^(b+c); no discordance =>1'},
     'resources': {'workers': 2, 'maxProcessRssBytes': 1073741824, 'pilotWallSeconds': 1200},
     'holdout': {'generationAllowed': False,
                 'reason': 'Independent evaluation decision gates not yet frozen; reserved seeds are '
                           'not authorization to generate',
                 'reservedDataMaster': 2026102602,
                 'reservedDataStage': 27,
                 'reservedPermutationMaster': 2026102602,
                 'reservedPermutationStage': 28},
     'interpretation': 'Global equality under exchangeability; rank-location maximum not '
                       'omnibus-sensitive; no component/member claims; max-v-marginal gains combine '
                       'joint calibration/dependence/discreteness; reused development only'}


def check_protocol(path):
    p = read(path)
    for key, expected in protocol_contract().items():
        require(p.get(key) == expected, f'frozen protocol mismatch: {key}')
    require(bool(p.get('freezeUtc')), 'protocol freeze timestamp missing')
    require(all(isinstance(p.get(k), str) and len(p[k]) == 64 for k in ('fixturesSha256', 'oracleExpectedSha256')), 'fixture and oracle hashes required')
    return p


def unpack(case):
    if 'evidence' in case:
        evidence = case['evidence']
        return dict(evidence, status=case['status'], timing=dict(evidence.get('timing', {}), **case.get('timing', {})))
    return case


def provenance(dll, protocol, fixtures):
    # Include every checked-in-looking source/configuration involved, but never
    # build products, archived evidence or mutable execution outputs.
    paths = sorted(p for p in ROOT.rglob('*') if p.is_file()
                   and not any(x in p.relative_to(ROOT).parts for x in ('bin', 'obj', '.git', '__pycache__', 'benchmark_history'))
                   and p.suffix in ('.cs', '.csproj', '.props', '.targets', '.py'))
    sources = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    siblings = {p.name: sha(p) for p in sorted(dll.parent.iterdir())
                if p.is_file() and p.suffix in ('.dll', '.json')}
    version = subprocess.run(['dotnet', '--info'], capture_output=True, text=True, timeout=15, check=True).stdout
    runtime_versions = set(re.findall(r'^\s*Microsoft\.NETCore\.App (8\.0\.\d+) ', version, re.MULTILINE))
    require(len(runtime_versions) == 1, 'expected one unambiguous installed net8.0 runtime reference')
    return dict(nativeRuntimeVersion=next(iter(runtime_versions)), protocolSha256=sha(protocol), fixturesSha256=sha(fixtures),
                sourceHashes=sources, binaryHashes=siblings, binarySha256=sha(dll),
                runtimeInfo=version, runtimeSha256=hashlib.sha256(version.encode()).hexdigest(),
                archiveHashes={p.name: sha(p) for p in (ARCHIVE/'benchmark_replications.csv', ARCHIVE/'benchmark_replication_metrics.csv')})


def validate_envelope(envelope, key, mode, binding):
    require(envelope.get('schemaVersion') == 'mvs-global-rank-native/v1', 'native schema mismatch')
    require(envelope.get('status') == 'ok', 'native envelope not successful')
    require(envelope.get('mode') == ('--case' if mode == 'development' else '--replay'), 'native mode mismatch')
    require(type(envelope.get('conditionOrdinal')) is int and type(envelope.get('replication')) is int
            and (envelope['conditionOrdinal'], envelope['replication']) == key, 'native envelope identity mismatch')
    native = envelope['provenance']
    require(native['harnessSha256'] == binding['binarySha256'], 'native harness hash mismatch')
    require(native['coreSha256'] == binding['binaryHashes']['MvsAnalyzer.Core.dll'], 'native core hash mismatch')
    require(native['runtimeVersion'] == binding['nativeRuntimeVersion'], 'native runtime mismatch')


def gate(path, kind, binding):
    g = read(path)
    require(g.get('schemaVersion') == 'mvs-global-rank-gate/v1', 'bad gate schema')
    require(g.get('kind') == kind and g.get('passed') is True, f'{kind} gate not passed')
    require(g.get('provenance') == binding, f'{kind} gate provenance differs')
    require(g.get('mismatches') == 0 and g.get('failures') == 0, f'{kind} gate has failures')
    if kind == 'oracle':
        require(g.get('allAssignmentsChecked') is True and g.get('rawFixturesPassed') is True,
                'oracle must cover every assignment and raw fixtures')
        require(g.get('orbitSizes') == [70, 126, 252], 'oracle dimensions missing')
        require(isinstance(g.get('evidenceFiles'), dict) and bool(g['evidenceFiles']), 'oracle evidence absent')
        native_oracles = []
        for name, digest in g['evidenceFiles'].items():
            evidence_path = Path(path).parent / name
            require(sha(evidence_path) == digest, 'oracle evidence hash mismatch')
            if evidence_path.suffix == '.json':
                evidence = read(evidence_path)
                if isinstance(evidence,dict) and evidence.get('schemaVersion') == 'mvs-global-rank-native/v1':
                    require(evidence.get('mode') == '--oracle' and evidence.get('status') == 'ok', 'invalid native oracle envelope')
                    native = evidence['provenance']
                    require(native['harnessSha256'] == binding['binarySha256'] and native['coreSha256'] == binding['binaryHashes']['MvsAnalyzer.Core.dll'] and native['runtimeVersion'] == binding['nativeRuntimeVersion'], 'native oracle binary/runtime mismatch')
                    native_oracles.append(evidence)
        require(bool(native_oracles), 'hash-bound native oracle runtime reference missing')
    else:
        require(g.get('planned') == 1300 and g.get('completed') == 1300, 'full replay required')
        validate_saved_run(Path(path).parent, binding, 'replay')
    return g


def archives():
    def rows(name):
        with (ARCHIVE/name).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    metrics, seeds = {}, {}
    for r in rows('benchmark_replication_metrics.csv'):
        if r['phase'] == 'main' and r['condition'] in CONDITIONS:
            key = (CONDITIONS.index(r['condition']), int(r['replication_index']))
            if key[1] < COUNTS[key[0]]:
                require(r['observed_available'] == 'true', 'archived slot unavailable')
                entry = metrics.setdefault(key, {})
                require(r['metric'] not in entry, 'duplicate archived metric')
                entry[r['metric']] = (float(r['p_value']), r['rejected'] == 'true')
    for r in rows('benchmark_replications.csv'):
        if r['phase'] == 'main' and r['condition'] in CONDITIONS:
            key = (CONDITIONS.index(r['condition']), int(r['replication_index']))
            if key[1] < COUNTS[key[0]]:
                require(key not in seeds and r['status'] == 'completed', 'invalid archive replication')
                seeds[key] = int(r['derived_seed'])
    require(len(seeds) == len(metrics) == 1300, 'archive does not cover all planned cases')
    require(all(len(v) == 12 for v in metrics.values()), 'archive metric family incomplete')
    return metrics, seeds


def derive(seed, stage, condition, replication):
    mask = (1 << 64)-1
    def scramble(x):
        z = (x + 0x9E3779B97F4A7C15) & mask
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
        return z ^ (z >> 31)
    x = scramble((seed + stage * 0x9E3779B97F4A7C15) & mask)
    x = scramble((x + condition * 0xC2B2AE3D27D4EB4F) & mask)
    return scramble((x + replication * 0x165667B19E3779F9) & mask)


def replay_check(case, key, archive):
    metrics, seeds = archive
    require(case['conditionOrdinal'] == key[0] and case['replication'] == key[1], 'case identity mismatch')
    require(int(case['datasetSeed']) == seeds[key], 'archived dataset seed mismatch')
    order = case['metricOrder']
    require(order == METRIC_ORDER and set(order) == set(metrics[key]), 'metric order/family mismatch')
    require(case['condition'] == NATIVE_CONDITIONS[key[0]], 'condition name mismatch')
    stage = (1,4,3,4,2,2)[key[0]]
    stream = (1,0,1,12,1,1)[key[0]]
    require((case['dataMaster'],case['dataStage'],case['dataStream'],case['labelMaster'],case['labelStage']) == (20260904,stage,stream,2026102601,26), 'seed coordinates mismatch')
    require(case['datasetSeed']==derive(20260904,stage,stream,key[1]), 'derived dataset seed mismatch')
    require(case['labelSeed']==derive(2026102601,26,*key), 'derived label seed mismatch')
    p = case['shipped']['pValues']
    require(len(p) == 12 and all(type(x) in (float, int) and math.isfinite(x) for x in p), 'invalid shipped values')
    require(all(p[j] == metrics[key][m][0] and (p[j] < .05) == metrics[key][m][1]
                for j, m in enumerate(order)), 'archived p-value/raw rejection mismatch')
    require(type(case['shipped']['reject']) is bool and case['shipped']['reject'] == any(x < .05/12 for x in p), 'shipped Bonferroni decision mismatch')
    require(case['shipped']['bonferroniAdjustedPValues'] == [min(1., x * 12) for x in p], 'shipped adjusted values mismatch')


def decisions(case):
    c = case['candidate']
    out = dict(shipped=case['shipped']['reject'], candidate=c['globalReject'],
               permutationBonferroni=c['bonferroniReject'], fixedMedian=c['fixedMedianReject'], fixedCv=c['fixedCvReject'])
    require(all(type(v) is bool for v in out.values()), 'nonboolean rejection')
    ps = c['marginalPValues']
    require(len(ps) == 12 and all(type(p) in (float, int) and math.isfinite(p) and .001 <= p <= 1 for p in ps), 'invalid marginal probabilities')
    require(type(c['globalPValue']) in (float, int) and math.isfinite(c['globalPValue']) and .001 <= c['globalPValue'] <= 1, 'invalid global probability')
    require(out['candidate'] == (c['globalPValue'] < .05), 'global decision mismatch')
    require(out['permutationBonferroni'] == any(p < .05/12 for p in ps), 'marginal Bonferroni mismatch')
    order = case['metricOrder']
    require(out['fixedMedian'] == (ps[order.index('median')] < .05), 'fixed median mismatch')
    cv = next((i for i, name in enumerate(order) if name in ('cv', 'coefficient_of_variation')), None)
    require(cv is not None and out['fixedCv'] == (ps[cv] < .05), 'fixed CV mismatch')
    return out


def validate_case(case, key, archive, mode):
    require(case.get('status') in ('completed', 'ok'), 'native did not complete case')
    replay_check(case, key, archive)
    # Sampled watchdog is not an OS memory sandbox. Check the native high-water
    # accounting too, including replay processes whose peak fell between polls.
    peak = case['timing']['peakWorkingSetBytes']
    require(type(peak) in (int, float) and math.isfinite(peak) and 0 <= peak <= MEMORY_LIMIT,
            'native peak working set exceeds 1 GiB or is invalid')
    if mode == 'development':
        decisions(case)
        require(case['labelSeed'] == derive(2026102601,26,*key), 'permutation seed mismatch')
        rows = case['summaryRows']
        expected_entities = 40 if key[0] == 3 else 32
        require(len(rows) == len(case['entities']) == expected_entities, 'retained entity count mismatch')
        require(all(len(row)==12 and all(type(x) in (float,int) and math.isfinite(x) for x in row) for row in rows), 'invalid summary matrix')
        digest = hashlib.sha256(b''.join(struct.pack('<d', x) for row in rows for x in row)).hexdigest()
        require(digest == case['summarySha256'], 'summary digest mismatch')
        c = case['candidate']
        require(c['drawCount'] == 999 and isinstance(c['sampledLabelHash'],str) and len(c['sampledLabelHash'])==64, 'draw evidence missing')
        require(type(c['globalExceedanceCount']) is int and 0<=c['globalExceedanceCount']<=999 and c['globalPValue']==(1+c['globalExceedanceCount'])/1000, 'global count mismatch')
        require(len(c['marginalExceedanceCounts'])==12 and all(type(k) is int and 0<=k<=999 and p==(1+k)/1000 for k,p in zip(c['marginalExceedanceCounts'],c['marginalPValues'])), 'marginal count mismatch')
        require(len(c['maxTExceedanceCounts'])==len(c['maxTAdjustedPValues'])==12 and all(type(k) is int and 0<=k<=999 and p==(1+k)/1000 for k,p in zip(c['maxTExceedanceCounts'],c['maxTAdjustedPValues'])), 'maxT count mismatch')
        require(c['globalExceedanceCount']==min(c['maxTExceedanceCounts']) and c['globalPValue']==min(c['maxTAdjustedPValues']), 'maximum/helper identity mismatch')
        require(c['bonferroniAdjustedPValues']==[min(1.,p*12) for p in c['marginalPValues']], 'permutation adjusted Bonferroni mismatch')
        for field in ('preprocessingMs', 'shippedMs', 'candidateMs', 'totalMs', 'cpuMs', 'peakWorkingSetBytes'):
            v = case['timing'][field]
            require(type(v) in (int, float) and math.isfinite(v) and v >= 0, 'invalid timing ' + field)


def rss(pid):
    # Fail closed if process accounting cannot be inspected while process lives.
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024
    except FileNotFoundError:
        return None
    return None


def run_case(dll, out, key, mode, deadline, cancel, archive, binding):
    stem = f'{key[0]}-{key[1]:04d}'
    target = out / (stem + '.json')
    rec = dict(conditionOrdinal=key[0], replication=key[1], status='not-started', result=target.name)
    started = time.monotonic()
    if cancel.is_set() or started >= deadline:
        rec['reason'] = 'cancelled-or-wall-limit-before-start'
        return rec
    proc = None
    try:
        with (out/(stem+'.stdout')).open('wb') as stdout, (out/(stem+'.stderr')).open('wb') as stderr:
            proc = subprocess.Popen(['dotnet', str(dll), '--replay' if mode == 'replay' else '--case', str(key[0]), str(key[1]), '--out', str(target)], stdout=stdout, stderr=stderr, env=dict(os.environ, DOTNET_PROCESSOR_COUNT='1'))
            maximum = 0
            while proc.poll() is None:
                if cancel.is_set() or time.monotonic() >= deadline:
                    cancel.set()
                    raise RuntimeError('cancelled or shared 20 minute wall limit')
                current = rss(proc.pid)
                if current is None:
                    # /proc can lose VmRSS before waitpid reports exit. Never
                    # interpret absent accounting for a live process as zero.
                    try:
                        status_text = Path(f'/proc/{proc.pid}/status').read_text()
                    except FileNotFoundError:
                        status_text = ''
                    evidence = dict(pid=proc.pid, statusText=status_text)
                    rec.setdefault('missingRssEvidence', []).append(evidence)
                    remaining = deadline-time.monotonic()
                    if cancel.is_set() or remaining <= 0:
                        cancel.set()
                        raise RuntimeError('cancelled or shared 20 minute wall limit')
                    reap_started = time.monotonic()
                    try:
                        evidence['exitCode'] = proc.wait(timeout=min(.1, remaining))
                    except subprocess.TimeoutExpired:
                        evidence['reapTimedOut'] = True
                        raise RuntimeError('process RSS unavailable; bounded reap did not confirm exit')
                    finally:
                        evidence['reapSeconds'] = time.monotonic()-reap_started
                    # Exit was actually reaped; normal exit/result validation
                    # below still applies. No live accounting was waived.
                    break
                maximum = max(maximum, current)
                if maximum > MEMORY_LIMIT:
                    raise RuntimeError('process RSS exceeds 1 GiB')
                if cancel.is_set() or time.monotonic() >= deadline:
                    cancel.set()
                    raise RuntimeError('cancelled or shared 20 minute wall limit')
                time.sleep(.05)
            rec.update(exitCode=proc.returncode, observedPeakRssBytes=maximum)
            require(proc.returncode == 0, 'native process failed')
        envelope = read(target)
        validate_envelope(envelope, key, mode, binding)
        case = unpack(envelope)
        validate_case(case, key, archive, mode)
        rec.update(status='completed', resultSha256=sha(target))
    except Exception as exc:
        cancel.set()  # Stop before further scheduled cases on infrastructure/data disagreement.
        rec.update(status='failed', reason=f'{type(exc).__name__}: {exc}')
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if target.exists():
            rec['resultSha256'] = sha(target)
    rec['driverWallSeconds'] = time.monotonic() - started
    return rec


def validate_saved_run(directory, binding, mode):
    meta = read(directory/'run.json')
    require(meta['provenance'] == binding and meta['mode'] == mode, 'saved run provenance/mode mismatch')
    records = read(directory/'checkpoint.json')['records']
    require(len(records) == 1300, 'checkpoint missing planned outcomes')
    expected = {(i, j) for i, n in enumerate(COUNTS) for j in range(n)}
    require({(r['conditionOrdinal'], r['replication']) for r in records} == expected, 'checkpoint identities invalid')
    archive = archives()
    for r in records:
        if r['status'] == 'completed':
            target = directory/r['result']
            require(target.resolve().parent == directory.resolve(), 'result outside run directory')
            require(sha(target) == r['resultSha256'], 'saved result modified')
            envelope = read(target)
            key = (r['conditionOrdinal'], r['replication'])
            validate_envelope(envelope, key, mode, binding)
            validate_case(unpack(envelope), key, archive, mode)
    if mode == 'replay':
        require(all(r['status'] == 'completed' for r in records), 'incomplete replay')
    return records


def wilson(k, n):
    z = 1.959963984540054
    mid = (k/n + z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(k/n*(1-k/n)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0., mid-half), min(1., mid+half)]


def binomial_cdf(k, n, p):
    if p <= 0:
        return 1.
    if p >= 1:
        return float(k >= n)
    return min(1., math.fsum(math.exp(math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)+j*math.log(p)+(n-j)*math.log1p(-p)) for j in range(k+1)))


def cp(k, n):
    # Exact binomial inversion, two-sided 97.5% CP (tail .0125).
    def invert(k, target):
        lo, hi = 0., 1.
        for _ in range(65):
            mid = (lo+hi)/2
            if binomial_cdf(k, n, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo+hi)/2
    return (0. if k == 0 else invert(k-1, .9875), 1. if k == n else invert(k, .0125))


def paired(a, b):
    n = len(a)
    table = dict(bothReject=sum(x and y for x,y in zip(a,b)),
                 candidateOnly=sum(x and not y for x,y in zip(a,b)),
                 comparatorOnly=sum(not x and y for x,y in zip(a,b)),
                 neitherReject=sum(not x and not y for x,y in zip(a,b)))
    wins, losses = table['candidateOnly'], table['comparatorOnly']
    lb, ub = cp(wins, n)
    lc, uc = cp(losses, n)
    discordant = wins+losses
    p = sum(math.comb(discordant,k) for k in range(wins, discordant+1))/2**discordant if discordant else 1.
    return dict(n=n, table=table, delta=(wins-losses)/n,
                conservative95PairedInterval=[lb-uc, ub-lc], oneSidedExactMcNemarP=p,
                intervalCoverage='at least 95% per comparison; not simultaneous across four comparisons')


def report(directory, records):
    result = dict(schemaVersion='mvs-global-rank-development-report/v1', planned=1300,
                  completed=sum(r['status']=='completed' for r in records), conditions=[], pairedComparisons=[],
                  interpretation='Reused development screening only; no GO, component attribution, individual discoveries or nominal .05-control certification.',
                  attribution='Maximum-statistic calibration, dependence and discreteness effects are combined.',
                  timingDefinition='Shared preprocessing reported separately; baseline total is preprocessing+shipped, candidate total is preprocessing+candidate. No speed-win claim.')
    all_data = {}
    timing = {x: [] for x in ('preprocessingMs','shippedMs','candidateMs','totalMs','cpuMs','peakWorkingSetBytes','baselineIncludingSharedMs','candidateIncludingSharedMs')}
    for i, n in enumerate(COUNTS):
        data = [unpack(read(directory/r['result'])) for r in records if r['conditionOrdinal']==i and r['status']=='completed']
        all_data[i] = data
        outcomes = [decisions(d) for d in data]
        missing = n-len(data)
        item = dict(condition=CONDITIONS[i], conditionOrdinal=i, planned=n, completed=len(data), missing=missing, methods={})
        for method in METHODS:
            k = sum(d[method] for d in outcomes)
            item['methods'][method] = dict(rejections=k, plannedDenominator=n, rejectionRateBounds=[k/n,(k+missing)/n])
        if i < 4:
            interval = wilson(sum(d['candidate'] for d in outcomes), n) if not missing else None
            item['candidateWilson95'] = interval
            item['nullScreen'] = 'incomplete' if missing else ('stop-inflation' if interval[0] > .075 else 'eligible' if interval[1] <= .10 else 'inconclusive')
        result['conditions'].append(item)
        for d in data:
            for field in timing:
                if field == 'baselineIncludingSharedMs':
                    v = d['timing']['preprocessingMs']+d['timing']['shippedMs']
                elif field == 'candidateIncludingSharedMs':
                    v = d['timing']['preprocessingMs']+d['timing']['candidateMs']
                else:
                    v = d['timing'][field]
                timing[field].append(v)
    for i in (4,5):
        ds = [decisions(d) for d in all_data[i]]
        for comparator in ('shipped', 'permutationBonferroni'):
            item = dict(condition=CONDITIONS[i], comparator=comparator, planned=COUNTS[i], completed=len(ds))
            if len(ds) == COUNTS[i]:
                item.update(paired([d['candidate'] for d in ds], [d[comparator] for d in ds]))
            else:
                b = sum(d['candidate'] and not d[comparator] for d in ds)
                c = sum(not d['candidate'] and d[comparator] for d in ds)
                missing=COUNTS[i]-len(ds)
                item.update(status='incomplete-no-screen', observedDiscordance=dict(candidateOnly=b,comparatorOnly=c), deltaBounds=[(b-c-missing)/COUNTS[i],(b-c+missing)/COUNTS[i]])
            result['pairedComparisons'].append(item)
    baseline = [x for x in result['pairedComparisons'] if x['comparator']=='shipped']
    valid = result['completed']==1300
    promising = valid and all(x.get('nullScreen')=='eligible' for x in result['conditions'][:4]) and all(x['delta']>=0 for x in baseline) and any(x['delta']>=.05 for x in baseline)
    result['promising'] = promising
    result['pilotEvidenceOfImprovement'] = promising and any(x['oneSidedExactMcNemarP']<.025 for x in baseline)
    result['validityGatePassed'] = valid
    result['timingMedians'] = {k: statistics.median(v) if v else None for k,v in timing.items()}
    result['rawTimingLocation'] = 'Each case JSON timing object; never successful-only performance certification when incomplete.'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('replay', 'development', 'report'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dll', type=Path)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--oracle-manifest', type=Path)
    parser.add_argument('--replay-manifest', type=Path)
    parser.add_argument('--input', type=Path, help='Completed or interrupted development directory, report mode only')
    parser.add_argument('--workers', type=int, choices=(1,2), default=2)
    args = parser.parse_args(argv)
    out = args.out.resolve()
    require(out != ROOT and ROOT not in out.parents, 'output must be external to source checkout')
    require(not out.exists(), 'output directory must be fresh (resume not implemented)')
    protocol = check_protocol(args.protocol)
    require(protocol['fixturesSha256'] == sha(args.fixtures), 'frozen fixture hash mismatch')
    require(args.dll is not None and args.dll.is_absolute(), 'explicit absolute trusted project-built DLL path required')
    dll = args.dll.resolve(strict=True)
    require(dll.name == 'MvsAnalyzer.Core.Tests.dll', 'wrong native harness DLL')
    require(sys.platform.startswith('linux') and Path('/proc/self/status').exists(), 'Linux /proc RSS accounting required')
    binding = provenance(dll, args.protocol, args.fixtures)
    require(args.oracle_manifest is not None, 'passed oracle manifest required before replay/development/report')
    gate(args.oracle_manifest, 'oracle', binding)
    if args.mode in ('development','report'):
        require(args.replay_manifest is not None, 'full replay manifest required')
        gate(args.replay_manifest, 'replay', binding)
    if args.mode == 'report':
        require(args.input is not None, '--input required for report')
        directory = args.input.resolve()
        records = validate_saved_run(directory, binding, 'development')
        out.mkdir(parents=True)
        write(out/'report.json', report(directory, records))
        return 0 if all(r['status']=='completed' for r in records) else 1
    require(args.input is None, '--input only accepted by report mode')
    archive = archives()
    out.mkdir(parents=True)
    write(out/'run.json', dict(schemaVersion='mvs-global-rank-run/v1', mode=args.mode, provenance=binding, planned=1300, resumeSupported=False, workers=args.workers, wallSeconds=WALL_LIMIT, processMemoryBytes=MEMORY_LIMIT))
    keys = [(i,j) for i,n in enumerate(COUNTS) for j in range(n)]
    records = {key: dict(conditionOrdinal=key[0], replication=key[1], status='not-started', reason='not-yet-scheduled') for key in keys}
    cancel = threading.Event()
    old = {s: signal.signal(s, lambda *_: cancel.set()) for s in (signal.SIGINT,signal.SIGTERM)}
    deadline=time.monotonic()+WALL_LIMIT
    def checkpoint():
        write(out/'checkpoint.json', dict(records=[records[k] for k in keys], planned=1300, resumeSupported=False))
    checkpoint()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending={pool.submit(run_case,dll,out,k,args.mode,deadline,cancel,archive,binding):k for k in keys}
            for future in as_completed(pending):
                key=pending[future]
                try:
                    records[key]=future.result()
                except Exception as exc:
                    records[key].update(status='failed',reason=str(exc))
                checkpoint()
    finally:
        cancel.set()
        checkpoint()
        for s, handler in old.items():
            signal.signal(s,handler)
    ordered=[records[k] for k in keys]
    complete=sum(r['status']=='completed' for r in ordered)
    if args.mode=='replay':
        write(out/'replay-manifest.json',dict(schemaVersion='mvs-global-rank-gate/v1',kind='replay',passed=complete==1300,provenance=binding,planned=1300,completed=complete,failures=1300-complete,mismatches=sum(r['status']=='failed' for r in ordered)))
    else:
        write(out/'report.json',report(out,ordered))
    return 0 if complete==1300 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Blocked: {exc}', file=sys.stderr)
        sys.exit(2)
