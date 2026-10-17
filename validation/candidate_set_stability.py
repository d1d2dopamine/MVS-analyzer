#!/usr/bin/env python3
"""Round44 fail-closed, fixed-recipe candidate-set diagnostic.

prepare hashes retained bytes without decoding them. run is a separate outcome-access
command requiring the frozen binding hash. Every input is validated before any native
invocation or candidate aggregation. report never launches a process. No calibration,
measurement generation, threshold tuning, reduced-N rescue, or scientific test occurs.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time

COUNT = 120
TRACKS = ('location', 'variability', 'heterogeneity')
KEYS = ('median', 'standard_deviation', 'coefficient_of_variation', 'mad', 'iqr', 'normalized_mad', 'normalized_iqr', 'mean', 'rms', 'range', 'geometric_mean', 'trimmed_mean_20')
FAMILIES = {'location': ('median', 'mean', 'geometric_mean', 'trimmed_mean_20'),
            'variability': ('standard_deviation', 'coefficient_of_variation', 'mad', 'iqr', 'normalized_mad', 'normalized_iqr', 'range'),
            'heterogeneity': ('median', 'mean', 'geometric_mean', 'trimmed_mean_20')}
METHOD = 'family-power-ci-overlap-v1'
PROTOCOL_SHA = 'd0000bfc4ac9a2213dce9f3a666903c91da94e140b8051ffca32b146a1290326'
PROTOCOL_DOCUMENT_SHA = 'b92a56876fd2fc8cbe615c0bbbb37d50fef6158db2d77eb9b7a35e1f7b1502b9'
WALL_SECONDS, CLEANUP_SECONDS, RSS_BYTES = 120, 5, 512 * 1024**2
INTERVAL_TOLERANCE = 1e-15
FPR_LIMIT = min(1, max(1.5 * (.05 / 12), .05 / 12 + .02))
SOURCE_PINS = {
 'Core/CalibrationRecommendations.cs': 'c1b5089a40ba56c5e1bba957216a019d01994bc18729b86afdbf862afe462c1c',
 'Core/Models.cs': 'd4f51d62c5972d866af3bf59a224b7a314df43c02d4475547ed83405a969d706',
 'Core/MetricRegistry.cs': '5a61012f1914f72850df690358a16c1fe162aa09ba5b2a1ce6e9f8f68d05fa04',
 'Core/ScientificInfrastructure.cs': '7e2947c272e7f3aaecade2829367cf0cdfd3206c67006f6c163b826da3d60d1a',
 'Core/SimulationScenarios.cs': 'ef6efee8232388c9ba450f6724f987e12269dbe4338ea262b23dae366e8d57b2',
 'Core/AnalysisEngine.cs': 'bc4caa7600034781861784cedaf64cc19d22ecc5eb26841ada291c0c6d66bd05',
 'SharedSources.props': 'a86d92f474867e834c2c7d6155122a709cae56394d6d4a5f6aa203b691881dd6',
 'MvsAnalyzer.Core/AssemblyInfo.cs': '76fd41a5433081215c3e89869931a0b9e098aef1a8abcb005c29824cb360a5fd'}
SCALARS = ('fpr', 'power', 'score', 'robustness', 'repeatability', 'coverage', 'mde', 'fpr_low', 'fpr_high', 'alpha')
DOUBLE_ARRAYS = ('track_powers', 'track_scores', 'track_mdes', 'track_power_low', 'track_power_high')
STRING_ARRAYS = ('tracks', 'track_curves', 'track_mde_status')
ROW_FIELDS = set(SCALARS + DOUBLE_ARRAYS + STRING_ARRAYS + ('metric', 'applicable', 'fpr_inflated', 'power_curve', 'repetitions', 'null_failures', 'track_failures'))
REASONS = {
 'outside_family': 'Metric belongs to a different summary family for this track.',
 'not_applicable': 'Metric or track power is unavailable for this calibration.',
 'null_control_uncertain': 'The null false-positive upper bound does not satisfy the current diagnostic limit.',
 'lower_sensitivity': 'Its power interval is separated below the best eligible metric under this calibration.',
 'qualified': 'Sensitivity is statistically competitive with the best eligible metric and its lower power bound meets the recommendation target.',
 'uncertain_power': 'Sensitivity is statistically competitive with the best eligible metric, but the lower power bound is below the recommendation target.'}
LIMITATIONS = [
 'Posthoc development diagnosis of historical same-recipe replays; not new prospective scientific evidence.',
 'Wilson overlap is a selection heuristic, not equality/equivalence/noninferiority testing; literal native competitive labels are not established inferential claims.',
 'Both-empty agreement is shared abstention; cross-pair contributions reuse the same halves and are not independent observations.',
 'Candidate-set and singleton targets differ; descriptive differences do not establish scientific superiority.',
 'No p-values, significance tests, new stability threshold, calibration, regeneration, or metric activation; scientific NO-GO unchanged.']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def exact_keys(value, keys, where):
    require(type(value) is dict, where + ': expected object')
    require(set(value) == set(keys), where + ': missing/unknown fields ' + str(sorted(set(value) ^ set(keys))))


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def same_double(a, b):
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return struct.pack('>d', a) == struct.pack('>d', b)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024**2), b''):
            h.update(b)
    return h.hexdigest()


def loads(text):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'duplicate JSON member: ' + k)
            result[k] = v
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON literal: ' + value)
    result = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
    def check(v):
        if type(v) is float:
            require(math.isfinite(v), 'overflow/nonfinite JSON number')
        elif isinstance(v, dict):
            for x in v.values(): check(x)
        elif isinstance(v, list):
            for x in v: check(x)
    check(result)
    return result


def read_json(path):
    return loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())


def sha_value(v, where):
    require(type(v) is str and re.fullmatch('[0-9a-f]{64}', v) is not None, where + ': invalid SHA-256')


def wilson(k, n=1000):
    """Independent algebraic Wilson form; stored bounds are never replaced."""
    z = 1.959963984540054
    denom = n + z*z
    center = (k + z*z / 2) / denom
    half = z * math.sqrt(k * (n-k) / n + z*z / 4) / denom
    return max(0.0, center-half), min(1.0, center+half)


def validate_interval(p, low, high, failures, where):
    require(all(number(x) and 0 <= x <= 1 for x in (p, low, high)), where + ': finite probability required')
    require(low <= high and low - INTERVAL_TOLERANCE <= p <= high + INTERVAL_TOLERANCE, where + ': reversed/non-containing interval')
    k = round(p * 1000)
    require(p == k / 1000 and 0 <= k <= 1000 - failures, where + ': probability is not a feasible integer count/1000')
    a, b = wilson(k)
    require(abs(a-low) <= INTERVAL_TOLERANCE and abs(b-high) <= INTERVAL_TOLERANCE, where + ': count-derived Wilson bounds mismatch')
    return {'successes': k, 'low_delta': low-a, 'high_delta': high-b}


def restore_slots(slots, metadata, where):
    require(type(metadata) is list, where + ': nonfinite_fields must be array')
    labels = {}
    for item in metadata:
        exact_keys(item, ('path', 'value'), where + ' nonfinite entry')
        path, label = item['path'], item['value']
        require(type(path) is str and path in slots and path not in labels, where + ': duplicate/unknown/non-double nonfinite path')
        require(label in ('NaN', 'Infinity', '-Infinity'), where + ': unknown nonfinite class')
        labels[path] = label
    for path, (container, key) in slots.items():
        value = container[key]
        if value is None:
            require(path in labels, where + ': untagged null ' + path)
            container[key] = {'NaN': math.nan, 'Infinity': math.inf, '-Infinity': -math.inf}[labels.pop(path)]
        else:
            require(number(value), where + ': invalid double ' + path)
            require(path not in labels, where + ': nonfinite tag on finite value ' + path)
    require(not labels, where + ': unused nonfinite metadata')


def validate_rows(raw, metadata, where='rows'):
    require(type(raw) is list and len(raw) == 12, where + ': exactly 12 rows required')
    rows = deepcopy(raw)
    slots = {}
    for i, row in enumerate(rows):
        at = where + '[' + str(i) + ']'
        exact_keys(row, ROW_FIELDS, at)
        require(row['metric'] == KEYS[i], at + ': metric missing/duplicate/unknown/reordered')
        for field in ('applicable', 'fpr_inflated'):
            require(type(row[field]) is bool, at + ': boolean required for ' + field)
        for field in ('repetitions', 'null_failures'):
            require(type(row[field]) is int, at + ': integer required for ' + field)
        require(row['repetitions'] == 1000 and 0 <= row['null_failures'] <= 1000, at + ': invalid repetition/failure count')
        require(type(row['power_curve']) is str, at + ': power_curve string required')
        for field in DOUBLE_ARRAYS + STRING_ARRAYS + ('track_failures',):
            require(type(row[field]) is list and len(row[field]) == 3, at + ': complete three-element array required for ' + field)
        for field in STRING_ARRAYS:
            require(all(type(x) is str for x in row[field]), at + ': string array required')
        require(row['tracks'] == list(TRACKS), at + ': missing/duplicate/reordered tracks')
        require(all(type(x) is int and 0 <= x <= 1000 for x in row['track_failures']), at + ': invalid track failures')
        for field in SCALARS:
            slots[f'[{i}].{field}'] = (row, field)
        for field in DOUBLE_ARRAYS:
            for j in range(3): slots[f'[{i}].{field}[{j}]'] = (row[field], j)
    restore_slots(slots, metadata, where)
    audits = []
    for i, row in enumerate(rows):
        at = where + '[' + str(i) + ']'
        require(row['alpha'] == .05, at + ': alpha changed')
        a = {'metric': row['metric'], 'tracks': {}}
        if row['applicable']:
            require(row['null_failures'] <= 100, at + ': applicable despite insufficient null-valid count')
            a['null'] = validate_interval(row['fpr'], row['fpr_low'], row['fpr_high'], row['null_failures'], at + '.fpr')
        else:
            require(all(math.isnan(row[f]) for f in ('fpr', 'fpr_low', 'fpr_high')), at + ': nonapplicable FPR must be explicit NaNs')
        require(row['fpr_inflated'] == (math.isfinite(row['fpr']) and row['fpr'] > FPR_LIMIT), at + ': FprInflated mismatch')
        for j, track in enumerate(TRACKS):
            available = row['applicable'] and row['track_failures'][j] <= 100
            vals = [row[f][j] for f in ('track_powers', 'track_power_low', 'track_power_high', 'track_scores')]
            if available:
                require(number(vals[3]), at + '.' + track + ': finite score required')
                a['tracks'][track] = validate_interval(*vals[:3], row['track_failures'][j], at + '.' + track)
            else:
                require(all(math.isnan(v) for v in vals), at + '.' + track + ': unavailable power/bounds/score must be explicit NaNs')
                a['tracks'][track] = {'available': False}
        for scalar, array in (('power', 'track_powers'), ('score', 'track_scores'), ('mde', 'track_mdes')):
            require(same_double(row[scalar], row[array][0]), at + ': primary scalar/track mismatch ' + scalar)
        require(row['power_curve'] == row['track_curves'][0], at + ': primary curve mismatch')
        audits.append(a)
    return rows, audits


def expected_settings():
    return {'run_seed': 20260904, 'stage': 5, 'stream': 1, 'index_min': 0, 'index_max': 119,
      'design': {'id': 'gait_stride_like', 'label': 'Gait-like: 16 per group, 40 measurements, CV about 2.5%', 'label_ru': 'Как шаг: 16 на группу, 40 измерений, КВ около 2,5%', 'entities_per_group': 16, 'measurements_per_entity': 40, 'base_level': 1.10, 'between_sd': .08, 'within_cv': .025, 'cv_heterogeneity': .25, 'shape': 1, 'variable': 'stride_interval', 'unit': 's'},
      'injection': 'None', 'generation_effect': 1, 'contamination': 0, 'min_value': -1000000, 'max_value': 1000000, 'min_measurements': 6, 'repetitions': 1000, 'effect': 1.15, 'scenario': 'location', 'outlier_rate': .02, 'missing_rate': 0, 'alpha': .05, 'tracks': list(TRACKS),
      'score_projection': 'original BenchmarkRunner.Scores; absent/nonfinite Score becomes zero',
      'canonical_binding': 'UTF-8 compact System.Text.Json snake_case JSON, ordered rows and properties as emitted; SHA-256 over precisely the embedded canonical_json UTF-8 bytes. Replay binding only, not a historical archived-data hash.',
      'nonfinite_encoding': 'null; calibration nonfinite_fields retains path and NaN/Infinity/-Infinity label'}


def require_same_json(a, b, where):
    """Typed recursive equality; JSON bool must never equal numeric 1/0."""
    if type(b) is dict:
        exact_keys(a, b, where)
        for k in b: require_same_json(a[k], b[k], where + '.' + k)
    elif type(b) is list:
        require(type(a) is list and len(a) == len(b), where + ': array shape mismatch')
        for i, (x, y) in enumerate(zip(a, b)): require_same_json(x, y, where + '[' + str(i) + ']')
    elif type(b) in (int, float):
        require(number(a) and a == b and (type(b) is not int or type(a) is int), where + ': numeric value/type mismatch')
        if a == 0 and b == 0: require(same_double(a, b), where + ': signed-zero mismatch')
    else:
        require(type(a) is type(b) and a == b, where + ': value/type mismatch')


def derived_seed(index):
    mask = (1 << 64) - 1
    def scramble(x):
        z = (x + 0x9E3779B97F4A7C15) & mask
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
        return z ^ (z >> 31)
    x = scramble((20260904 + 5 * 0x9E3779B97F4A7C15) & mask)
    x = scramble((x + 0xC2B2AE3D27D4EB4F) & mask)
    return scramble((x + index * 0x165667B19E3779F9) & mask)


def validate_data_binding(binding, kind):
    exact_keys(binding, ('sha256', 'canonical_json', 'values'), 'data.' + kind)
    sha_value(binding['sha256'], 'data binding')
    require(type(binding['canonical_json']) is str, 'canonical_json must be string')
    require(hashlib.sha256(binding['canonical_json'].encode()).hexdigest() == binding['sha256'], 'embedded data hash mismatch')
    require_same_json(loads(binding['canonical_json']), binding['values'], 'canonical data')
    value = binding['values']
    def observations(rows):
        require(type(rows) is list, 'observations must be array')
        for row in rows:
            exact_keys(row, ('entity', 'group', 'value', 'sequence', 'variable', 'unit'), 'observation')
            require(all(type(row[k]) is str for k in ('entity', 'group', 'variable', 'unit')), 'observation string field')
            require(number(row['value']) and type(row['sequence']) is int, 'observation numeric field')
    if kind == 'generated':
        observations(value); return
    exact_keys(value, ('warnings', 'import_summary', 'observations', 'entities', 'total_entities', 'group_names', 'group_counts', 'valid_rows', 'median_measurements', 'entity_column', 'value_column', 'group_column', 'sequence_column', 'measurement_name', 'unit', 'distribution_proxy', 'min_value_applied', 'max_value_applied', 'min_measurements_applied'), 'AnalysisData')
    observations(value['observations'])
    for key in ('warnings', 'group_names'):
        require(type(value[key]) is list and all(type(x) is str for x in value[key]), key + ': string array required')
    for key in ('import_summary', 'entity_column', 'value_column', 'group_column', 'sequence_column', 'measurement_name', 'unit', 'distribution_proxy'):
        require(type(value[key]) is str, key + ': string required')
    for key in ('total_entities', 'valid_rows', 'min_value_applied', 'max_value_applied', 'min_measurements_applied'):
        require(type(value[key]) is int, key + ': integer required')
    require(number(value['median_measurements']), 'median_measurements required')
    require(type(value['group_counts']) is list and all(type(x) is int for x in value['group_counts']), 'group_counts required')
    require(type(value['entities']) is list and value['total_entities'] == len(value['entities']), 'entity count mismatch')
    for row in value['entities']:
        exact_keys(row, ('entity', 'group', 'metrics', 'measurements'), 'entity')
        require(type(row['entity']) is str and type(row['group']) is str and type(row['measurements']) is int, 'entity field type')
        require(type(row['metrics']) is list and len(row['metrics']) == 12 and all(x is None or number(x) for x in row['metrics']), 'entity metrics invalid')
    require(value['valid_rows'] == len(value['observations']), 'valid_rows mismatch')


def validate_case(value, index):
    exact_keys(value, ('schema', 'index', 'status', 'diagnostics_status', 'error', 'seeds', 'settings', 'metric_order', 'identity', 'data', 'calibration_left', 'calibration_right', 'nonfinite_fields', 'scores_left', 'scores_right', 'availability_left', 'availability_right', 'legacy', 'corrected', 'resources'), 'case')
    require(value['schema'] == 'mvs-stability-replay-case/v1' and type(value['index']) is int and value['index'] == index, 'case schema/index mismatch')
    require((value['status'], value['diagnostics_status'], value['error']) == ('completed', 'retained', ''), 'case not completed/retained')
    require(value['metric_order'] == list(KEYS), 'case metric order mismatch')
    require_same_json(value['settings'], expected_settings(), 'settings')
    seeds = value['seeds']
    exact_keys(seeds, ('run_seed', 'derived_seed', 'split_seed', 'calibration_left_seed', 'calibration_right_seed'), 'seeds')
    require(all(type(v) is int for v in seeds.values()), 'seed must be integer')
    require(seeds['run_seed'] == 20260904 and seeds['derived_seed'] == derived_seed(index), 'derived recipe/index seed mismatch')
    require(all(1 <= seeds[k] <= 50000000 for k in ('split_seed', 'calibration_left_seed', 'calibration_right_seed')), 'seed range invalid')
    identity = value['identity']
    exact_keys(identity, ('harness_sha256', 'core_sha256', 'runtime', 'os', 'architecture', 'engine_version', 'benchmark_protocol', 'processor_count', 'environment_fingerprint', 'environment_sha256', 'environment_probe_values'), 'identity')
    for k in ('harness_sha256', 'core_sha256', 'environment_sha256'): sha_value(identity[k], k)
    for k in ('runtime', 'os', 'architecture', 'engine_version', 'benchmark_protocol', 'environment_fingerprint'):
        require(type(identity[k]) is str and identity[k], 'identity string required: ' + k)
    require(identity['runtime'] == '.NET 8.0.31' and identity['architecture'] == 'X64' and type(identity['processor_count']) is int and identity['processor_count'] == 1, 'retained runtime identity mismatch')
    require(hashlib.sha256(identity['environment_fingerprint'].encode()).hexdigest() == identity['environment_sha256'], 'environment fingerprint mismatch')
    require(type(identity['environment_probe_values']) is list and len(identity['environment_probe_values']) == 12 and all(number(x) for x in identity['environment_probe_values']), 'environment probes invalid')
    exact_keys(value['data'], ('generated', 'built', 'left', 'right'), 'data')
    for kind, binding in value['data'].items(): validate_data_binding(binding, kind)
    exact_keys(value['resources'], ('wall_seconds', 'cpu_seconds', 'peak_working_set_bytes'), 'resources')
    require(all(number(x) and x >= 0 for x in value['resources'].values()), 'invalid resources')
    for method in ('legacy', 'corrected'):
        tau = value[method]
        exact_keys(tau, ('kendall_tau', 'defined', 'undefined_reason', 'top_left_index', 'top_right_index', 'top_left', 'top_right', 'matched'), method)
        require(type(tau['defined']) is bool and type(tau['matched']) is bool, 'diagnostic bool missing')
        require((number(tau['kendall_tau']) and tau['undefined_reason'] is None) if tau['defined'] else (tau['kendall_tau'] is None and type(tau['undefined_reason']) is str), 'diagnostic defined state invalid')
        for side in ('left', 'right'):
            i = tau['top_' + side + '_index']
            require(type(i) is int and -1 <= i < 12 and tau['top_' + side] == (KEYS[i] if i >= 0 else None), 'diagnostic winner invalid')
    exact_keys(value['nonfinite_fields'], ('calibration_left', 'calibration_right'), 'nonfinite_fields')
    result, audit = {}, {}
    for side in ('left', 'right'):
        field = 'calibration_' + side
        result[side], audit[side] = validate_rows(value[field], value['nonfinite_fields'][field], str(index) + '.' + side)
        scores = value['scores_' + side]
        require(type(scores) is list and len(scores) == 12 and all(number(v) for v in scores), 'projected scores malformed')
        availability = value['availability_' + side]
        require(type(availability) is list and len(availability) == 12, 'availability malformed')
        for i, row in enumerate(result[side]):
            finite = math.isfinite(row['score'])
            require_same_json(availability[i], {'metric': KEYS[i], 'row_present': True, 'score_finite': finite, 'applicable': row['applicable'], 'projected_to_zero': not finite}, 'availability')
            require(same_double(scores[i], row['score'] if finite else 0.0), 'score projection mismatch')
    return result, audit


def reference_selection(rows, track):
    """Simple independent pool/maximum/filter operations on restored raw fields."""
    require(track in TRACKS, 'unknown track')
    j = TRACKS.index(track)
    natural = set(FAMILIES[track])
    available = {r['metric'] for r in rows if r['applicable'] and all(math.isfinite(r[f][j]) for f in ('track_powers', 'track_power_low', 'track_power_high'))}
    controlled = {r['metric'] for r in rows if r['metric'] in available and not r['fpr_inflated'] and math.isfinite(r['fpr_high']) and r['fpr_high'] <= FPR_LIMIT}
    pool = [r for r in rows if r['metric'] in natural & controlled]
    best = min(pool, key=lambda r: (-r['track_powers'][j], KEYS.index(r['metric']))) if pool else None
    candidates = {r['metric'] for r in pool if r['track_power_high'][j] >= best['track_power_low'][j]} if best else set()
    qualified = {r['metric'] for r in pool if r['metric'] in candidates and r['track_power_low'][j] >= .70}
    canonical = lambda s: [k for k in KEYS if k in s]
    return {'candidates': canonical(candidates), 'qualified': canonical(qualified), 'best': best['metric'] if best else None,
      'best_power': best['track_powers'][j] if best else math.nan, 'best_power_low': best['track_power_low'][j] if best else math.nan,
      'status': 'qualified' if qualified else 'uncertain' if candidates else 'unavailable',
      'pool': canonical({r['metric'] for r in pool}), 'available': canonical(available), 'controlled': canonical(controlled),
      'exclusion_counts': {'natural_unavailable': len(natural-available), 'natural_available_failing_null': len((natural & available)-controlled), 'outside_family': 12-len(natural)},
      'empty_reasons': ([] if candidates else [reason for reason, condition in (('no_applicable_natural_family', not (natural & available)), ('applicable_natural_rows_fail_null_control', bool(natural & available))) if condition])}


def compare_native(native, source, index, expected_sha, expected_identity):
    exact_keys(native, ('schema', 'status', 'index', 'input_sha256', 'method_id', 'identity', 'validation', 'inputs', 'evaluations'), 'native')
    require(native['schema'] == 'mvs-candidate-set-audit/v1' and native['status'] == 'completed' and type(native['index']) is int and native['index'] == index and native['input_sha256'] == expected_sha and native['method_id'] == METHOD, 'native binding/status/method mismatch')
    require_same_json(native['identity'], expected_identity, 'native identity')
    require_same_json(native['validation'], {'accepted': True, 'half_count': 2, 'track_count': 3, 'build_invocations': 6, 'summarize_invocations': 6, 'exact_finite_roundtrip': True}, 'native validation')
    exact_keys(native['inputs'], ('left', 'right'), 'native inputs')
    for side in ('left', 'right'):
        inp = native['inputs'][side]
        exact_keys(inp, ('rows', 'nonfinite_fields'), 'native input')
        raw = source['raw']
        require_same_json(inp['rows'], raw['calibration_' + side], 'roundtrip rows')
        require_same_json(inp['nonfinite_fields'], raw['nonfinite_fields']['calibration_' + side], 'roundtrip metadata')
    evaluations = native['evaluations']
    require(type(evaluations) is list and len(evaluations) == 6, 'six direct evaluations required')
    result = {}
    for evaluation, (side, track) in zip(evaluations, [(s, t) for s in ('left', 'right') for t in TRACKS]):
        exact_keys(evaluation, ('side', 'track', 'build', 'summary', 'nonfinite_fields'), 'evaluation')
        require((evaluation['side'], evaluation['track']) == (side, track), 'native evaluation missing/duplicate/order mismatch')
        ev = deepcopy(evaluation)
        build, summary = ev['build'], ev['summary']
        require(type(build) is list and len(build) == 12, '12 Build records required')
        slots = {}
        for i, rec in enumerate(build):
            exact_keys(rec, ('track', 'family', 'metric', 'family_eligible', 'applicable', 'null_controlled', 'power', 'power_low', 'power_high', 'best_power', 'best_power_low', 'candidate', 'quality', 'reason'), 'Build record')
            for key in ('power', 'power_low', 'power_high', 'best_power', 'best_power_low'): slots[f'build[{i}].{key}'] = (rec, key)
        exact_keys(summary, ('track', 'family', 'status', 'candidates', 'qualified_candidates', 'best_metric', 'best_power', 'best_power_low'), 'summary')
        for key in ('best_power', 'best_power_low'): slots['summary.' + key] = (summary, key)
        restore_slots(slots, ev['nonfinite_fields'], 'native evaluation')
        ref = reference_selection(source['rows'][side], track)
        family = 'variability' if track == 'variability' else 'location'
        j = TRACKS.index(track)
        for i, (rec, row) in enumerate(zip(build, source['rows'][side])):
            metric = KEYS[i]
            family_eligible = metric in FAMILIES[track]
            applicable = metric in ref['available']
            controlled = metric in ref['controlled']
            candidate = metric in ref['candidates']
            quality = ('outside_family' if not family_eligible else 'not_applicable' if not applicable else 'null_control_uncertain' if not controlled else 'lower_sensitivity' if not candidate else 'qualified' if metric in ref['qualified'] else 'uncertain_power')
            expected = {'track': track, 'family': family, 'metric': metric, 'family_eligible': family_eligible, 'applicable': applicable, 'null_controlled': controlled, 'candidate': candidate, 'quality': quality, 'reason': REASONS[quality]}
            for key, val in expected.items(): require_same_json(rec[key], val, f'{index}.{side}.{track}.{metric}.{key}')
            for key, val in {'power': row['track_powers'][j], 'power_low': row['track_power_low'][j], 'power_high': row['track_power_high'][j], 'best_power': ref['best_power'], 'best_power_low': ref['best_power_low']}.items():
                require(same_double(rec[key], val), f'{index}.{side}.{track}.{metric}.{key}: binary64/class mismatch')
        for key, val in {'track': track, 'family': family, 'status': ref['status'], 'best_metric': ref['best']}.items(): require_same_json(summary[key], val, 'summary.' + key)
        for key, refkey in (('candidates', 'candidates'), ('qualified_candidates', 'qualified')):
            arr = summary[key]
            require(type(arr) is list and all(type(x) is str for x in arr) and len(arr) == len(set(arr)) and set(arr) == set(ref[refkey]), 'native duplicate/mismatched ' + key)
        for key in ('best_power', 'best_power_low'): require(same_double(summary[key], ref[key]), 'summary numeric mismatch')
        result[(side, track)] = ref
    return result


def rational(v):
    v = Fraction(v)
    return {'numerator': v.numerator, 'denominator': v.denominator, 'decimal': float(v)}


def rate(n, d):
    return {'count': n, 'denominator': d, 'value': rational(Fraction(n, d)) if d else None, 'undefined_reason': None if d else 'zero_denominator'}


def mean_rational(values):
    total = sum(values, Fraction())
    return {'sum': rational(total), 'denominator': len(values), 'value': rational(total / len(values)) if values else None, 'undefined_reason': None if values else 'zero_denominator'}


def jaccard(a, b):
    a, b = set(a), set(b)
    return Fraction(len(a & b), len(a | b)) if a | b else Fraction(1)


def quantile(values, q):
    if not values: return None
    values = sorted(Fraction(x) for x in values)
    h = (len(values)-1) * Fraction(q)
    lo = h.numerator // h.denominator
    hi = min(lo+1, len(values)-1)
    return rational(values[lo] + (values[hi]-values[lo])*(h-lo))


def distribution(values):
    return {'count': len(values), 'mean': mean_rational([Fraction(x) for x in values]), 'min': rational(min(values)) if values else None, 'max': rational(max(values)) if values else None, 'q1': quantile(values, Fraction(1,4)), 'median': quantile(values, Fraction(1,2)), 'q3': quantile(values, Fraction(3,4)), 'quantile_method': 'type-7 exact rational interpolation'}


def chance_summary(left, right):
    require(len(left) == len(right), 'marginal sample sizes differ')
    n = len(left)
    if not n:
        return {'denominator': 0, 'cross_pair_count': 0, 'exact': None, 'jaccard': None, 'undefined_reason': 'zero_denominator'}
    a, b = Counter(tuple(sorted(x)) for x in left), Counter(tuple(sorted(x)) for x in right)
    product = sum(a[s] * b[s] for s in a)
    cross_exact = sum(x == y for x in left for y in right)
    require(product == cross_exact, 'category-product/cross-pair exact baseline mismatch')
    crosses = [jaccard(x, y) for x in left for y in right]
    observed_a = Fraction(sum(x == y for x, y in zip(left, right)), n)
    observed_j = sum((jaccard(x, y) for x, y in zip(left, right)), Fraction()) / n
    def compare(observed, baseline):
        return {'observed': rational(observed), 'reference': rational(baseline), 'excess': rational(observed-baseline), 'adjusted': rational((observed-baseline)/(1-baseline)) if baseline != 1 else None, 'undefined_reason': 'degenerate_marginals' if baseline == 1 else None}
    return {'denominator': n, 'cross_pair_count': n*n, 'category_product_match_count': product, 'explicit_cross_match_count': cross_exact,
      'left_categories': [{'set': list(s), 'count': v} for s, v in sorted(a.items())], 'right_categories': [{'set': list(s), 'count': v} for s, v in sorted(b.items())],
      'cross_jaccard': mean_rational(crosses), 'exact': compare(observed_a, Fraction(cross_exact, n*n)), 'jaccard': compare(observed_j, sum(crosses, Fraction())/(n*n)), 'undefined_reason': None}


def summarize_track(pairs, track):
    n = len(pairs)
    require(n > 0, 'empty analysis population')
    left = [set(p['left']['candidates']) for p in pairs]; right = [set(p['right']['candidates']) for p in pairs]
    tl = [{p['left']['best']} if p['left']['best'] is not None else set() for p in pairs]
    tr = [{p['right']['best']} if p['right']['best'] is not None else set() for p in pairs]
    require(all(bool(a) == bool(b) for a,b in zip(left,tl)) and all(bool(a) == bool(b) for a,b in zip(right,tr)), 'singleton/candidate availability mismatch')
    both = [i for i in range(n) if left[i] and right[i]]; union = [i for i in range(n) if left[i] or right[i]]
    empty_both = n-len(union)
    js = [jaccard(a,b) for a,b in zip(left,right)]
    exact = sum(a == b for a,b in zip(left,right)); winners = sum(a == b for a,b in zip(tl,tr))
    require(sum((jaccard(a,b) for a,b in zip(tl,tr)), Fraction()) == winners, 'singleton exact/Jaccard mismatch')
    side_results = {}
    for side, sets in (('left',left),('right',right)):
        rs = [p[side] for p in pairs]; qs = [set(r['qualified']) for r in rs]
        size = lambda values: {'histogram': {str(k): rate(sum(len(x)==k for x in values),n) for k in range(len(FAMILIES[track])+1)}, 'summary': distribution([len(x) for x in values])}
        side_results[side] = {'candidates': size(sets), 'qualified': size(qs), 'full_family': rate(sum(len(s)==len(FAMILIES[track]) for s in sets), n),
          'candidate_inclusion': {k:rate(sum(k in s for s in sets),n) for k in KEYS}, 'qualified_inclusion': {k:rate(sum(k in s for s in qs),n) for k in KEYS},
          'statuses': {s:rate(sum(r['status']==s for r in rs),n) for s in ('qualified','uncertain','unavailable')},
          'winner_frequencies': {k:rate(sum(r['best']==(None if k=='none' else k) for r in rs),n) for k in (*KEYS,'none')},
          'empty_reason_counts': {reason:rate(sum(reason in r['empty_reasons'] for r in rs),n) for reason in ('no_applicable_natural_family','applicable_natural_rows_fail_null_control')}}
    def companion(indices):
        m = len(indices)
        aa = sum(left[i] == right[i] for i in indices); tt = sum(tl[i] == tr[i] for i in indices)
        jj = [js[i] for i in indices]
        c = chance_summary([left[i] for i in indices], [right[i] for i in indices])
        t = chance_summary([tl[i] for i in indices], [tr[i] for i in indices])
        return {'denominator':m,'exact_candidate':rate(aa,m),'mean_jaccard':mean_rational(jj),'singleton_agreement':rate(tt,m),
          'candidate_chance':c,'singleton_chance':t,'exact_set_minus_singleton':rational(Fraction(aa-tt,m)) if m else None,
          'set_overlap_minus_singleton':rational((sum(jj,Fraction())-tt)/m) if m else None}
    return {'track':track,'family':list(FAMILIES[track]),'denominator':n,'sides':side_results,
      'size_pair_crosstab':{str(a):{str(b):sum(len(x)==a and len(y)==b for x,y in zip(left,right)) for b in range(len(FAMILIES[track])+1)} for a in range(len(FAMILIES[track])+1)},
      'mean_absolute_size_difference':mean_rational([Fraction(abs(len(a)-len(b))) for a,b in zip(left,right)]),
      'empty_counts':{'left':sum(not x for x in left),'right':sum(not x for x in right),'both_empty':empty_both,'left_only_empty':sum(not a and bool(b) for a,b in zip(left,right)),'right_only_empty':sum(bool(a) and not b for a,b in zip(left,right)),'both_nonempty':len(both)},
      'exact_candidate':rate(exact,n),'both_empty_agreement_contribution':rate(empty_both,n),'nonempty_exact_match':rate(exact-empty_both,n),'real_best_match':rate(winners-empty_both,n),
      'jaccard':distribution(js),'jaccard_empty_contributions':{'both_empty_sum':rational(empty_both),'one_empty_sum':rational(0),'denominator':n},
      'union_nonempty_jaccard':mean_rational([js[i] for i in union]),'all_pairs':companion(list(range(n))),
      'both_nonempty':dict(companion(both), conditioning='Original matched indices with both candidate sets nonempty; marginals and n_B squared cross-pairs restricted to the same indices')}


def source_paths(root):
    return sorted(p.resolve() for p in root.rglob('*') if p.is_file() and p.suffix in {'.cs','.csproj','.py','.props','.targets'} and not {'bin','obj','.git','__pycache__'}.intersection(p.relative_to(root).parts))


def input_paths(root):
    paths = [root / f'case-{i:03d}' / 'native.json' for i in range(COUNT)]
    require(set(root.glob('case-*/native.json')) == set(paths), 'missing or unexpected retained case files')
    require(all(p.is_file() for p in paths), 'missing retained case')
    return paths


def prepare(root, out, protocol, input_root, native_dir, command, evidence, native_self_test):
    root,out,protocol,input_root,native_dir,native_self_test = map(lambda p:Path(p).resolve(),(root,out,protocol,input_root,native_dir,native_self_test))
    require(not out.exists(), 'output directory already exists; no overwrite/resume')
    require(sys.platform == 'linux' and Path('/proc/self/status').exists(), 'Linux process groups and /proc required')
    for rel, sha in SOURCE_PINS.items(): require(digest(root/rel)==sha, 'production source pin changed: '+rel)
    require(digest(protocol)==PROTOCOL_SHA, 'frozen protocol hash mismatch')
    protocol_document=root/'docs/ROUND44_CANDIDATE_SET_STABILITY_PROTOCOL.md'
    require(digest(protocol_document)==PROTOCOL_DOCUMENT_SHA, 'frozen protocol document hash mismatch')
    plan=read_json(protocol)
    require(len(command)==2 and Path(command[1]).suffix=='.dll', 'command must be dotnet HARNESS.dll only')
    executable = shutil.which(command[0]); require(executable is not None, 'dotnet executable missing')
    command = [str(Path(executable).resolve()),str(Path(command[1]).resolve())]
    runtime_root = Path(command[0]).parent
    runtime_dirs = [runtime_root/'shared/Microsoft.NETCore.App/8.0.31',runtime_root/'host/fxr/8.0.31']
    require(all(p.is_dir() for p in runtime_dirs), 'pinned .NET 8.0.31 runtime unavailable')
    runtime_files = sorted(p.resolve() for d in runtime_dirs for p in d.rglob('*') if p.is_file())
    native_files = sorted(p.resolve() for p in native_dir.rglob('*') if p.is_file())
    require(Path(command[1]) in native_files, 'harness outside native build directory')
    selftest = read_json(native_self_test)
    require(selftest.get('status')=='ok' and 'identity' in selftest, 'successful synthetic native self-test required')
    identity = selftest['identity']
    exact_keys(identity, ('harness_sha256','core_sha256','runtime','os','architecture','engine_version'), 'native identity')
    require(identity['harness_sha256']==digest(command[1]), 'self-test harness hash mismatch')
    require(identity['core_sha256']==digest(native_dir/'MvsAnalyzer.Core.dll'), 'self-test loaded Core hash mismatch')
    require(identity['runtime']=='.NET 8.0.31' and identity['architecture']=='X64', 'native runtime mismatch')
    sources = source_paths(root)
    inputs = input_paths(input_root)  # Enumeration and hashing only; no decoding retained outcomes.
    require([x['index'] for x in plan['inputs']]==list(range(COUNT)), 'protocol indices mismatch')
    for i,p in enumerate(inputs):
        require(plan['inputs'][i]['path']==f'case-{i:03d}/native.json' and digest(p)==plan['inputs'][i]['sha256'], 'frozen protocol input hash mismatch: '+str(i))
    evidence = [Path(p).resolve() for p in evidence]
    require(len(evidence)>=2 and all(p.is_file() for p in evidence), 'test and build provenance evidence required')
    paths = set(sources+native_files+runtime_files+inputs+evidence+[protocol,protocol_document,native_self_test,Path(command[0]),Path(sys.executable).resolve()])
    pins = {str(p):digest(p) for p in sorted(paths)}
    manifest = {'schema':'mvs-candidate-set-bind/v1','created_utc':datetime.now(timezone.utc).isoformat(),'root':str(root),'protocol':str(protocol),'protocol_sha256':pins[str(protocol)],'input_root':str(input_root),'native_dir':str(native_dir),'command':command,'identity':identity,
      'python':{'executable':str(Path(sys.executable).resolve()),'version':sys.version,'platform':platform.platform()},'sources':[str(p) for p in sources],'native_files':[str(p) for p in native_files],'runtime_files':[str(p) for p in runtime_files],
      'evidence':[str(p) for p in evidence],'native_self_test':str(native_self_test),'inputs':[{'index':i,'path':str(p),'sha256':pins[str(p)]} for i,p in enumerate(inputs)],'pins':pins,'indices':list(range(COUNT)),'tracks':list(TRACKS),'method_id':METHOD,
      'limits':{'workers':1,'wall_seconds':WALL_SECONDS,'cleanup_seconds':CLEANUP_SECONDS,'child_rss_bytes':RSS_BYTES,'dotnet_processor_count':1},
      'interval_validation':{'containment_absolute_tolerance':INTERVAL_TOLERANCE,'independent_wilson_absolute_tolerance':INTERVAL_TOLERANCE,'stored_selector_values_preserved':True},
      'expected_artifacts':['run-start.json','input-validation.json','attempts.json','post-run-verification.json','report.json','per-case.json']+[f'case-{i:03d}/{f}' for i in range(COUNT) for f in ('started.json','attempt.json','stdout.log','stderr.log','native.json')], 'limitations':LIMITATIONS}
    out.mkdir(parents=True)
    write_json(out/'bind.json',manifest)
    with (out/'bind.sha256').open('x') as f: f.write(digest(out/'bind.json')+'\n')
    return manifest


def verify(out):
    out=Path(out)
    require(digest(out/'bind.json')==(out/'bind.sha256').read_text().strip(),'binding manifest altered')
    m=read_json(out/'bind.json')
    require(m['schema']=='mvs-candidate-set-bind/v1' and m['indices']==list(range(COUNT)) and m['tracks']==list(TRACKS) and m['method_id']==METHOD,'binding contract changed')
    require_same_json(m['limits'],{'workers':1,'wall_seconds':120,'cleanup_seconds':5,'child_rss_bytes':RSS_BYTES,'dotnet_processor_count':1},'resource contract')
    require([str(p) for p in source_paths(Path(m['root']))]==m['sources'],'source file set changed')
    require(sorted(str(p.resolve()) for p in Path(m['native_dir']).rglob('*') if p.is_file())==m['native_files'],'native build file set changed')
    require([str(p) for p in input_paths(Path(m['input_root']))]==[x['path'] for x in m['inputs']],'input set changed')
    require([x['index'] for x in m['inputs']]==list(range(COUNT)),'input indices changed')
    for p,sha in m['pins'].items(): require(digest(p)==sha,'pinned hash changed: '+p)
    for item in m['inputs']: require(item['sha256']==m['pins'][item['path']],'input binding mismatch')
    require(m['protocol_sha256']==m['pins'][m['protocol']]==PROTOCOL_SHA,'protocol binding mismatch')
    require(m['pins'][str(Path(m['root'])/'docs/ROUND44_CANDIDATE_SET_STABILITY_PROTOCOL.md')]==PROTOCOL_DOCUMENT_SHA,'protocol document binding mismatch')
    plan=read_json(m['protocol'])
    for item,frozen in zip(m['inputs'],plan['inputs']):
        require(item['index']==frozen['index'] and item['sha256']==frozen['sha256'] and Path(item['path']).relative_to(m['input_root']).as_posix()==frozen['path'],'frozen input binding mismatch')
    for rel,sha in SOURCE_PINS.items(): require(m['pins'][str(Path(m['root'])/rel)]==sha,'source contract pin mismatch')
    return m


def validate_population(m):
    require([x['index'] for x in m['inputs']]==list(range(COUNT)), 'all 120 ordered cases required')
    rows, audits, errors = {}, [], []
    for item in m['inputs']:
        try:
            require(digest(item['path'])==item['sha256'],'input hash mismatch')
            raw=read_json(item['path'])
            restored,audit=validate_case(raw,item['index'])
            rows[item['index']]={'rows':restored,'raw':{k:raw[k] for k in ('calibration_left','calibration_right','nonfinite_fields')}}
            audits.append({'index':item['index'],'valid':True,'sha256':item['sha256'],'halves':audit})
        except Exception as exc:
            errors.append({'index':item['index'],'error':str(exc)})
    return rows,{'schema':'mvs-candidate-input-validation/v1','requested':COUNT,'valid_pairs':len(rows),'half_track_evaluations_expected':720,'valid':not errors and len(rows)==COUNT,'cases':audits,'errors':errors}


def kill_group(proc):
    try: os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError: pass


def group_rss(pid):
    total=0
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            stat=(entry/'stat').read_text().rsplit(')',1)[1].split()
            if int(stat[2])==pid: total+=int(stat[21])*os.sysconf('SC_PAGE_SIZE')
        except (FileNotFoundError,ProcessLookupError): pass
    return total


def execute_cases(out, command, inputs, wall_seconds=WALL_SECONDS, rss_bytes=RSS_BYTES, start=None):
    """Blocking waits plus independent watchdog; sampling is not a speed estimate."""
    out=Path(out); start=time.monotonic() if start is None else start
    deadline=start+wall_seconds
    attempts=[]; reasons=[]; live={}; lock=threading.Lock(); finished=threading.Event(); stopped=threading.Event(); peak=0; cleanup_deadline=None
    def stop(reason):
        nonlocal cleanup_deadline
        if cleanup_deadline is None: cleanup_deadline=time.monotonic()+CLEANUP_SECONDS
        if reason not in reasons: reasons.append(reason)
        stopped.set()
        with lock:
            for proc in live.values(): kill_group(proc)
    def watchdog():
        nonlocal peak
        while not finished.wait(.02):
            try:
                if cleanup_deadline is not None and time.monotonic()>=cleanup_deadline:
                    with lock: remaining=list(live.values())
                    if remaining:
                        for proc in remaining: kill_group(proc)
                        try: write_json(out/'cleanup-abort.json',{'status':'technical_failure','reason':'owned cleanup exceeded five seconds','active_pids':[p.pid for p in remaining]})
                        finally: os._exit(124)
                if time.monotonic()>=deadline: stop('whole-run wall budget exceeded')
                with lock: pids=list(live)
                rss=sum(group_rss(pid) for pid in pids); peak=max(peak,rss)
                if rss>rss_bytes: stop('child process-group RSS budget exceeded')
            except Exception as exc: stop('watchdog error: '+str(exc))
    watcher=threading.Thread(target=watchdog,daemon=True); watcher.start()
    try:
        for item in inputs:
            if stopped.is_set() or time.monotonic()>=deadline:
                if not stopped.is_set(): stop('whole-run wall budget exceeded')
                break
            directory=out/f"case-{item['index']:03d}"; directory.mkdir()
            argv=[*command,'--input',item['path'],'--index',str(item['index']),'--sha256',item['sha256'],'--out',str(directory/'native.json')]
            env=dict(os.environ,DOTNET_PROCESSOR_COUNT='1',DOTNET_GCHeapHardLimit='0x18000000',DOTNET_ROLL_FORWARD='Disable',DOTNET_ROOT=str(Path(command[0]).parent),MVS_DISABLE_BACKUPS='1')
            begun=time.monotonic(); record={'index':item['index'],'argv':argv,'started':False,'returncode':None,'elapsed_seconds':None}
            write_json(directory/'started.json',dict(record,environment={k:env[k] for k in ('DOTNET_PROCESSOR_COUNT','DOTNET_GCHeapHardLimit','DOTNET_ROLL_FORWARD','DOTNET_ROOT','MVS_DISABLE_BACKUPS')}))
            proc=None
            try:
                with (directory/'stdout.log').open('xb') as stdout,(directory/'stderr.log').open('xb') as stderr:
                    with lock:
                        require(not stopped.is_set() and time.monotonic()<deadline,'budget exhausted before spawn')
                        proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True)
                        live[proc.pid]=proc; record['started']=True; record['pid']=proc.pid
                    # Genuine blocking wait. Independent watchdog owns timeout and SIGKILL.
                    record['returncode']=proc.wait()
                    if record['returncode'] != 0: stop('native process failed at index '+str(item['index']))
            except Exception as exc:
                record['error']=str(exc); stop('process execution failure at index '+str(item['index']))
                if proc is not None:
                    kill_group(proc)
                    record['returncode']=proc.wait()
            finally:
                if proc is not None:
                    # Reap the leader and terminate any remaining owned descendants.
                    kill_group(proc)
                    with lock: live.pop(proc.pid,None)
                record['elapsed_seconds']=time.monotonic()-begun
                write_json(directory/'attempt.json',record); attempts.append(record)
            if stopped.is_set(): break
    finally:
        finished.set(); watcher.join(timeout=CLEANUP_SECONDS)
        with lock:
            for proc in live.values(): kill_group(proc)
    return {'schema':'mvs-candidate-execution/v1','attempts':attempts,'requested':len(inputs),'completed_processes':sum(a['returncode']==0 for a in attempts),'not_started_indices':[x['index'] for x in inputs if x['index'] not in {a['index'] for a in attempts}], 'stop_reasons':reasons,'observed_peak_child_rss_bytes':peak,'rss_observation_interval_seconds':.02,'wall_seconds':time.monotonic()-start,'timing_interpretation':'Actual monotonic wall elapsed; blocking wait plus watchdog, no throughput or poll-bias claim.'}


def run(out, approval_bind_sha256):
    out=Path(out); m=verify(out)
    require(approval_bind_sha256==digest(out/'bind.json'),'explicit frozen binding hash required for authorized run')
    write_json(out/'run-start.json',{'schema':'mvs-candidate-run/v1','bind_sha256':approval_bind_sha256,'utc':datetime.now(timezone.utc).isoformat(),'argv':sys.argv})
    start=time.monotonic()
    rows,validation=validate_population(m)
    write_json(out/'input-validation.json',validation)
    if not validation['valid']:
        write_json(out/'attempts.json',{'requested':COUNT,'attempts':[],'stop_reasons':['input validation failed; no native process started']})
        return {'status':'technical_failure','errors':validation['errors']}
    execution=execute_cases(out,m['command'],m['inputs'],start=start)
    write_json(out/'attempts.json',execution)
    try:
        verify(out)
        post={'valid':True,'input_source_binary_runtime_pins_unchanged':True}
    except Exception as exc: post={'valid':False,'error':str(exc)}
    write_json(out/'post-run-verification.json',post)
    return {'status':'executed' if execution['completed_processes']==COUNT and not execution['stop_reasons'] and post['valid'] else 'technical_failure','completed_processes':execution['completed_processes'],'stop_reasons':execution['stop_reasons']}


def report(out):
    out=Path(out)
    try:
        m=verify(out)
        require(read_json(out/'run-start.json')['bind_sha256']==digest(out/'bind.json'),'run binding mismatch')
        execution=read_json(out/'attempts.json')
        require(execution.get('completed_processes')==COUNT and not execution['stop_reasons'] and [a['index'] for a in execution['attempts']]==list(range(COUNT)),'native execution incomplete/failed')
        require(read_json(out/'post-run-verification.json')['valid'],'post-run hash verification failed')
        sources, validation=validate_population(m)
        require(validation['valid'],'retained input validation failed: '+str(validation['errors']))
        selections={}
        for item in m['inputs']:
            index=item['index']
            selections[index]=compare_native(read_json(out/f'case-{index:03d}'/'native.json'),sources[index],index,item['sha256'],m['identity'])
        records=[]; aggregates={}
        for track in TRACKS:
            pairs=[]
            for index in range(COUNT):
                pair={'index':index,'track':track}
                for side in ('left','right'):
                    ref=selections[index][(side,track)]
                    pair[side]={k:v for k,v in ref.items() if k not in ('best_power','best_power_low')}
                    pair[side].update(candidate_size=len(ref['candidates']),qualified_size=len(ref['qualified']),pool_size=len(ref['pool']))
                a,b=set(pair['left']['candidates']),set(pair['right']['candidates'])
                pair.update(exact_match=a==b,intersection_size=len(a&b),union_size=len(a|b),jaccard=rational(jaccard(a,b)),singleton_exact_match=pair['left']['best']==pair['right']['best'])
                records.append(pair); pairs.append(pair)
            aggregates[track]=summarize_track(pairs,track)
            require(aggregates[track]['all_pairs']['candidate_chance']['cross_pair_count']==14400,'cross-pair denominator mismatch')
        verify(out)
        write_json(out/'per-case.json',{'schema':'mvs-candidate-pairs/v1','pair_track_count':360,'records':records})
        result={'schema':'mvs-candidate-report/v1','status':'completed','technical_acceptance':True,'scientific_acceptance':False,'requested_pairs':120,'validated_pairs':120,'tracks':aggregates,'native_build_invocations':720,'native_summarize_invocations':720,'native_reference_mismatches':0,'best_comparator_mismatches':0,'finite_field_comparison':'binary64 exact; nonfinite classes explicit','interval_validation_tolerance':INTERVAL_TOLERANCE,'source_input_binary_runtime_pins_unchanged':True,'no_calibration_regeneration_or_metric_activation':True,'limitations':LIMITATIONS}
    except Exception as exc:
        result={'schema':'mvs-candidate-report/v1','status':'technical_failure','technical_acceptance':False,'primary_aggregates_published':False,'error':str(exc),'limitations':LIMITATIONS}
    write_json(out/'report.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    p=sub.add_parser('prepare')
    for name in ('root','out','protocol','input-root','native-dir','native-self-test'): p.add_argument('--'+name,required=True)
    p.add_argument('--evidence',action='append',required=True)
    p.add_argument('--command',nargs=argparse.REMAINDER,required=True)
    for name in ('verify','run','report'):
        s=sub.add_parser(name);s.add_argument('--out',required=True)
        if name=='run':s.add_argument('--approved-bind-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        if args.operation=='prepare':
            result=prepare(args.root,args.out,args.protocol,args.input_root,args.native_dir,args.command,args.evidence,args.native_self_test)
            result={'status':'prepared_hashes_only','bind_sha256':digest(Path(args.out)/'bind.json'),'inputs':len(result['inputs'])}
        elif args.operation=='verify':
            verify(args.out);result={'status':'verified_hashes_only'}
        elif args.operation=='run':result=run(args.out,args.approved_bind_sha256)
        else:result=report(args.out)
        print(json.dumps(result,allow_nan=False,sort_keys=True))
        return 1 if result.get('status')=='technical_failure' else 0
    except Exception as exc:
        print(json.dumps({'status':'technical_failure','error':str(exc)}));return 1


if __name__=='__main__':
    raise SystemExit(main())
