#!/usr/bin/env python3
"""Fail-closed, post-hoc diagnostics on the pinned retained 5,370 vectors.

Phases: prepare freezes validated inputs; compare checks an externally executed
native harness field for field; report summarizes only a successful comparison.
No subprocesses, simulation, new scientific data, family selection, or activation.
All phases require the protocol SHA supplied at its freeze. Outputs are exclusive.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import check_benchmark_diagnostics as raw
import holm_benchmark_diagnostics as archived

METRICS = tuple(raw.METRICS)
ALPHA = .05
FAMILIES = {
    'all12': tuple(range(12)),
    'location4': (0, 7, 10, 11),
    'variability7': (1, 2, 3, 4, 5, 6, 9),
    'absolute4': (1, 3, 4, 9),
    'relative3': (2, 5, 6),
    'magnitude1': (8,),
}
PARTITION = ('location4', 'absolute4', 'relative3', 'magnitude1')
MAIN_CONDITIONS = dict(primary_null=1000, **{name: 250 for name in (
    'power_location_100', 'power_location_102', 'power_location_105',
    'power_location_110', 'power_location_120', 'power_dispersion_102',
    'power_dispersion_105', 'power_dispersion_110', 'power_dispersion_120',
    'power_dispersion_130', 'robust_null_2', 'robust_null_5', 'robust_null_10',
    'shape_normal_null', 'shape_lognormal_null', 'design_voice_null',
    'design_voice_location_105')})
NULL_CONDITIONS = ('primary_null', 'power_location_100', 'robust_null_2',
    'robust_null_5', 'robust_null_10', 'shape_normal_null', 'shape_lognormal_null',
    'design_voice_null')
EXPECTED_GROUPS = {(key, 'main'): count for key, count in MAIN_CONDITIONS.items()}
EXPECTED_GROUPS.update({('determinism_replay', phase): 60
                       for phase in ('replay-first', 'replay-second')})
PROTOCOL_SOURCES = ('Core/MetricRegistry.cs', 'Core/ScientificInfrastructure.cs',
    'Core/AnalysisEngine.cs', 'Benchmark/BenchmarkRunner.cs',
    'Core/CalibrationRecommendations.cs')
PROTOCOL_INPUTS = ('benchmark_replications.csv', 'benchmark_replication_metrics.csv',
    'benchmark_replication_procedures.csv', 'benchmark_stability_replications.csv',
    'benchmark_summary.csv', 'benchmark_manifest.json', 'benchmark_protocol.txt',
    'SHA256SUMS.txt')
INPUT_FILE = 'focused-family-input.json'
PROVENANCE_FILE = 'provenance.json'
NATIVE_FILE = 'focused-family-native.json'
COMPARISON_FILE = 'focused-family-comparison.json'
CASES_FILE = 'focused-family-cases.json'
SUMMARY_FILE = 'focused-family-summary.json'
CHECKSUM_FILE = 'SHA256SUMS.txt'
PRIOR_INSPECTED = {
    'location105': {'all12': 35, 'location4': 66, 'denominator': 250},
    'dispersion130': {'all12': 72, 'variability7': 97, 'denominator': 250},
    'primaryNull': {'all12': 18, 'location4': 16, 'variability7': 23, 'denominator': 1000},
    'twoFamilyHalfAlpha': {'location105': 42, 'dispersion130': 69},
    'stability': {'exactMatches': 27, 'registeredFamilyMatches': 97, 'splits': 120},
}
LIMITATIONS = [
    'Post-hoc development diagnostics on a previously inspected archive, not unseen validation or a preregistered experiment.',
    'The fixed-family definitions were frozen after the disclosed exploratory results had been seen; no candidate is selected by this report.',
    'Scientific NO-GO is unchanged. No production activation, recalibration, default change, new data, or random draws.',
    'Each standalone family spends alpha=0.05 for its own question; their unbudgeted union is diagnostic only and is not a valid data-selected default.',
    'The simultaneous partition directly multiplies p by 4*m within location4/absolute4/relative3/magnitude1, retaining unavailable slots in each fixed denominator.',
    'Arithmetic agreement does not establish marginal p-value calibration, strong FWER control, valid scientific power, or release readiness.',
    'Conditions and replay phases are separate. Replay-first and replay-second are reproducibility passes, not independent scientific replications.',
    'All-requested rates are operational discovery rates, with failed cases counted as no discovery, not as observed scientific nonrejections. Completed-only rates, failures, and missingness are explicit. Wilson intervals are descriptive, not simultaneous guarantees.',
    'Paired gains, losses, and deltas are descriptive only; they are not candidate-selection or GO gates.',
    'Stability uses retained top IDs and the archived whole-registry stability statistic only. The archived Kendall computation has a known joint-tie normalization issue; it is not interpreted here as standard tau-b.',
    'Coarsening top IDs can increase agreement mechanically. Chance agreement and kappa do not establish better metric selection, ranking, or candidate-set stability; candidate rankings are not reconstructed.',
]

require = archived.require
sha256 = archived.sha256
regular_file = archived.regular_file
json_bytes = archived.json_bytes
read_json = archived.read_json
write_new = archived.write_new


def require_keys(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), f'Invalid fields: {label}')


def valid_digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_vector(values, available):
    require(type(values) is list and len(values) == 12, 'pValues must have twelve slots')
    require(type(available) is list and len(available) == 12 and
            all(type(item) is bool for item in available), 'available must have twelve booleans')
    for p, is_available in zip(values, available):
        require((p is None) == (not is_available), 'Invalid p/availability pairing')
        require(p is None or (type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1),
                'Invalid p-value: expected finite [0,1] or unavailable null')


def family_reference(values, available, indices, budget=1):
    """Independent literal binary64 multiplication, never a threshold division."""
    multiplier = budget * len(indices)
    members = []
    for index in indices:
        p = values[index]
        adjusted = None if p is None else min(1.0, p * multiplier)
        members.append(dict(index=index, name=METRICS[index], available=available[index],
                            rawP=p, adjustedP=adjusted,
                            rejected=adjusted is not None and adjusted < ALPHA))
    observed = [member['adjustedP'] for member in members if member['available']]
    rejected = [member['name'] for member in members if member['rejected']]
    return dict(minAdjustedP=min(observed) if observed else None,
                anyRejected=bool(rejected), availableCount=len(observed),
                fullDenominator=len(indices), multiplier=multiplier,
                members=members, rejectedMembers=rejected)


def case_reference(case):
    require_keys(case, ('id', 'pValues', 'available'), 'input case')
    require(type(case['id']) is str and bool(case['id']), 'Invalid case id')
    values, available = case['pValues'], case['available']
    validate_vector(values, available)
    families = {name: family_reference(values, available, indices)
                for name, indices in FAMILIES.items()}
    partition = {name: family_reference(values, available, FAMILIES[name], 4)
                 for name in PARTITION}
    partition_members = {member for family in partition.values() for member in family['rejectedMembers']}
    partition_minima = [family['minAdjustedP'] for family in partition.values()
                        if family['minAdjustedP'] is not None]
    naive_members = {member for name in PARTITION for member in families[name]['rejectedMembers']}
    return dict(id=case['id'], availabilityStatus=('all-available' if all(available) else
        'partially-available' if any(available) else 'all-unavailable'), families=families,
        simultaneousPartition=dict(familyCount=4, families=partition,
            anyRejected=bool(partition_members),
            minAdjustedP=min(partition_minima) if partition_minima else None,
            rejectedMembers=[metric for metric in METRICS if metric in partition_members]),
        naiveFocusedUnion=dict(interpretation='diagnostic-only-not-globally-controlled',
            anyRejected=bool(naive_members),
            rejectedFamilies=[name for name in PARTITION if families[name]['anyRejected']],
            rejectedMembers=[metric for metric in METRICS if metric in naive_members]))


def family_definitions():
    return [dict(name=name, memberIndices=list(indices),
                 memberNames=[METRICS[index] for index in indices], fullDenominator=len(indices))
            for name, indices in FAMILIES.items()]


def build_input(replications, metrics, procedures, summaries):
    """Small-frame entry point used by synthetic tests; no scientific sampling."""
    fixture = archived.build_fixtures(replications, metrics, procedures, summaries)
    for case in fixture['cases']:
        require(case['diagnostics_status'] == 'retained', 'Missing retained diagnostics')
        require(case['status'] in ('completed', 'failed'), 'Unknown retained status')
        validate_vector(case['p_values'], case['observed_available'])
    document = dict(schemaVersion='mvs-focused-family-input/v1', cases=[
        dict(id=case['id'], pValues=case['p_values'], available=case['observed_available'])
        for case in fixture['cases']])
    return document, fixture['cases']


def validate_stability(rows, expected_count=None):
    require(type(rows) is list and bool(rows), 'Missing stability rows')
    result = []
    for row in rows:
        index = row['split_index']
        require(type(index) is str and index.isascii() and index.isdigit() and str(int(index)) == index,
                'Invalid stability index')
        status, diagnostic_status = row['status'], row['diagnostics_status']
        require(status in ('completed', 'failed') and diagnostic_status == 'retained',
                'Missing or invalid retained stability status')
        tau = raw.number(row['kendall_tau'])
        matched = raw.boolean(row['matched'], optional=True)
        require(tau is None or -1 <= tau <= 1, 'Stability statistic out of range')
        left, right = row['top_left'], row['top_right']
        if status == 'completed':
            require(tau is not None and left in METRICS and right in METRICS and
                    matched is not None and matched == (left == right), 'Invalid completed stability row')
        else:
            require(tau is None and matched is None and left == right == '', 'Failed stability row has results')
        result.append(dict(splitIndex=int(index), status=status, diagnosticsStatus=diagnostic_status,
                           error=row.get('error', ''), archivedWholeRegistryStatistic=tau,
                           topLeft=left, topRight=right, exactMatched=matched))
    require(sorted(row['splitIndex'] for row in result) == list(range(len(result))),
            'Duplicate or missing stability indices')
    require(expected_count is None or len(result) == expected_count, 'Unexpected stability row count')
    return result


def validate_protocol(path, expected_sha, repository, source_hashes):
    require(valid_digest(expected_sha), 'Protocol expected SHA-256 is required')
    require(sha256(regular_file(path)) == expected_sha, 'Frozen protocol SHA-256 mismatch')
    protocol = read_json(path)
    require(protocol.get('schemaVersion') == 'mvs-focused-family-protocol/v1' and
            protocol.get('protocolId') == 'R41-RETAINED-FOCUSED-FAMILIES-1', 'Unknown protocol identity')
    require(protocol.get('studyStatus') == 'posthoc_development_diagnostic_not_preregistered_validation',
            'Invalid study status')
    require(protocol.get('metricKeys') == list(METRICS), 'Protocol registry changed')
    require(protocol.get('families') == {name: list(indices) for name, indices in FAMILIES.items()} and
            list(protocol['families']) == list(FAMILIES), 'Protocol family definitions/order changed')
    require(protocol.get('partition') == list(PARTITION) and
            type(protocol.get('simultaneousPartitionMultiplier')) is int and
            protocol['simultaneousPartitionMultiplier'] == 4, 'Protocol partition changed')
    require(type(protocol.get('alpha')) is float and protocol['alpha'] == ALPHA, 'Protocol alpha changed')
    require(protocol.get('mainConditions') == MAIN_CONDITIONS and
            protocol.get('replayConditions') == {'determinism_replay': {'replay-first': 60, 'replay-second': 60}},
            'Protocol conditions changed')
    for key, value in dict(expectedCases=5370, expectedMainCases=5250, expectedMetricsPerCase=12,
                           expectedProceduresPerCase=8, expectedStabilitySplits=120).items():
        require(type(protocol.get(key)) is int and protocol[key] == value, f'Protocol budget changed: {key}')
    require(protocol.get('nullConditions') == list(NULL_CONDITIONS), 'Protocol null labels changed')
    require(protocol.get('executionBudget', {}).get('noNewDataOrRandomDraws') is True,
            'Protocol does not prohibit new draws')
    disclosures = protocol.get('priorInspectedResults', {})
    require(all(disclosures.get(key) == value for key, value in PRIOR_INSPECTED.items()),
            'Prior inspected results missing or changed')
    hashes = protocol.get('inputSha256')
    require_keys(hashes, PROTOCOL_INPUTS, 'protocol input hashes')
    require(all(valid_digest(hashes[name]) and hashes[name] == source_hashes[name] for name in hashes),
            'Protocol input hash mismatch')
    sources = protocol.get('sourceSha256')
    require_keys(sources, PROTOCOL_SOURCES, 'protocol source hashes')
    for name, digest in sources.items():
        require(valid_digest(digest) and sha256(regular_file(Path(repository) / name)) == digest,
                f'Protocol source hash mismatch: {name}')
    return protocol


def tool_hashes():
    paths = [Path(__file__), Path(__file__).with_name('test_focused_family_diagnostics.py'),
             Path(archived.__file__), Path(raw.__file__), Path(archived.multiplicity_reference.__file__)]
    # Harness source and project are additionally frozen before native execution.
    harness = Path(__file__).parent / 'focused_family_experiment'
    paths.extend((harness / 'Program.cs', harness / 'FocusedFamilyExperiment.csproj',
                  Path(__file__).resolve().parents[1] / 'MvsAnalyzer.Core/MvsAnalyzer.Core.csproj',
                  Path(__file__).resolve().parents[1] / 'SharedSources.props'))
    return {str(path.resolve()): sha256(regular_file(path)) for path in paths}


def load_source(benchmark, protocol_path, protocol_sha):
    benchmark = Path(benchmark)
    hashes = archived.source_hashes(benchmark)
    repository = Path(__file__).resolve().parents[1]
    protocol = validate_protocol(protocol_path, protocol_sha, repository, hashes)
    require(benchmark.resolve() == (repository / protocol['archiveRoot']).resolve(),
            'Benchmark must be the protocol-pinned archive root')
    archived.validate_identity(read_json(benchmark / 'benchmark_manifest.json'))
    reconciliation = raw.validate(benchmark)
    require(reconciliation['status'] == 'passed', 'Incomplete retained source diagnostics')
    frames = [raw.read_csv(benchmark, name) for name in ('benchmark_replications.csv',
        'benchmark_replication_metrics.csv', 'benchmark_replication_procedures.csv', 'benchmark_summary.csv')]
    inputs, cases = build_input(*frames)
    group_counts = Counter((case['condition'], case['phase']) for case in cases)
    require(dict(group_counts) == EXPECTED_GROUPS, 'Unexpected condition/phase rectangular budgets')
    require(len(cases) == 5370 and len(frames[1]) == 5370 * 12 and len(frames[2]) == 5370 * 8,
            'Unexpected retained evidence dimensions')
    stability = validate_stability(raw.read_csv(benchmark, 'benchmark_stability_replications.csv'), 120)
    require(archived.source_hashes(benchmark) == hashes, 'Source changed while reading')
    require(sha256(protocol_path) == protocol_sha, 'Protocol changed while reading')
    source = dict(archivePath=str(benchmark.resolve()), identity=dict(archived.IDENTITY),
        fileBindings={name: dict(path=str((benchmark / name).resolve()), sha256=digest)
                      for name, digest in hashes.items()}, rawReconciliation=reconciliation,
        protocol=dict(path=str(Path(protocol_path).resolve()), sha256=protocol_sha),
        protocolSourceBindings={name: dict(path=str((repository / name).resolve()), sha256=digest)
                                for name, digest in protocol['sourceSha256'].items()})
    return inputs, cases, stability, source, protocol


def provenance_document(source, inputs):
    return dict(schemaVersion='mvs-focused-family-provenance/v1', source=source,
        inputSha256=hashlib.sha256(json_bytes(inputs)).hexdigest(), toolSha256=tool_hashes(),
        familyDefinitions=family_definitions(), alpha=ALPHA,
        scientificReadiness='NO-GO unchanged', limitations=LIMITATIONS)


def check_output(benchmark, out):
    archived.check_output_location(benchmark, out)
    require(not Path(out).is_symlink(), 'Output directory must not be a symlink')


def prepare(benchmark, out, protocol_path, protocol_sha):
    check_output(benchmark, out)
    out = Path(out)
    require(not out.exists(), 'Preparation refuses an existing output directory')
    inputs, cases, stability, source, _ = load_source(benchmark, protocol_path, protocol_sha)
    provenance = provenance_document(source, inputs)
    require(len(json_bytes(inputs)) <= 8 * 1024 * 1024, 'Prepared input exceeds native 8 MiB limit')
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / INPUT_FILE, json_bytes(inputs))
    write_new(out / PROVENANCE_FILE, json_bytes(provenance))
    return dict(status='prepared', cases=len(cases), stabilitySplits=len(stability),
                inputSha256=provenance['inputSha256'], scientificReadiness='NO-GO unchanged')


def read_prepared(benchmark, out, protocol_path, protocol_sha):
    check_output(benchmark, out)
    out = Path(out)
    require(out.is_dir(), 'Missing prepared directory')
    inputs, cases, stability, source, protocol = load_source(benchmark, protocol_path, protocol_sha)
    provenance = provenance_document(source, inputs)
    require(regular_file(out / INPUT_FILE).read_bytes() == json_bytes(inputs), 'Prepared input changed')
    require(regular_file(out / PROVENANCE_FILE).read_bytes() == json_bytes(provenance),
            'Prepared provenance/source/tool binding changed')
    return inputs, cases, stability, provenance, protocol


def exact_compare(expected, actual, path='$', failures=None):
    """Compare every field, including exact binary64 values and scalar types."""
    if failures is None:
        failures = []
    if type(expected) is dict:
        if type(actual) is not dict or set(actual) != set(expected):
            failures.append(f'{path}: object fields differ')
        elif len(failures) < 100:
            for key in expected:
                exact_compare(expected[key], actual[key], f'{path}.{key}', failures)
    elif type(expected) is list:
        if type(actual) is not list or len(actual) != len(expected):
            failures.append(f'{path}: list length/type differs')
        elif len(failures) < 100:
            for index, value in enumerate(expected):
                exact_compare(value, actual[index], f'{path}[{index}]', failures)
    elif type(expected) is float:
        if type(actual) not in (int, float) or not math.isfinite(actual) or actual != expected:
            failures.append(f'{path}: numeric value differs')
    elif type(actual) is not type(expected) or actual != expected:
        failures.append(f'{path}: scalar value/type differs')
    return failures


def native_reference(inputs, input_digest, core_digest, harness_digest):
    return dict(schemaVersion='mvs-focused-family-diagnostic/v1',
        status='isolated-development-diagnostic', decisionStatus='no-go', alpha=ALPHA,
        registryKeys=list(METRICS), provenance=dict(harnessSha256=harness_digest,
        coreSha256=core_digest, inputSha256=input_digest), familyDefinitions=family_definitions(),
        cases=[case_reference(case) for case in inputs['cases']])


def baseline_failures(cases, results):
    failures = []
    for case, result in zip(cases, results):
        if case['analysis_eligible']:
            baseline = result['families']['all12']['anyRejected']
            for name in ('bonferroni', 'mvs_registry_corrected'):
                if baseline is not case['legacy_procedure_rejected'][name]:
                    failures.append(f"{case['id']}: all12 disagrees with archived {name}")
    return failures


def comparison_evidence(benchmark, out, protocol_path, protocol_sha, native_path, core_assembly, harness_assembly):
    out, native_path = Path(out), Path(native_path)
    inputs, cases, stability, provenance, protocol = read_prepared(benchmark, out, protocol_path, protocol_sha)
    require(native_path.resolve() == (out / NATIVE_FILE).resolve(), 'Native evidence must be out/' + NATIVE_FILE)
    core_digest, harness_digest, native_digest = [sha256(regular_file(path))
        for path in (core_assembly, harness_assembly, native_path)]
    native = read_json(native_path)
    reference = native_reference(inputs, provenance['inputSha256'], core_digest, harness_digest)
    failures = exact_compare(reference, native)
    baseline = baseline_failures(cases, reference['cases'])
    failures.extend(baseline)
    bindings = dict(input=dict(path=str((out / INPUT_FILE).resolve()), sha256=provenance['inputSha256']),
        provenance=dict(path=str((out / PROVENANCE_FILE).resolve()), sha256=sha256(out / PROVENANCE_FILE)),
        native=dict(path=str(native_path.resolve()), sha256=native_digest),
        coreAssembly=dict(path=str(Path(core_assembly).resolve()), sha256=core_digest),
        harnessAssembly=dict(path=str(Path(harness_assembly).resolve()), sha256=harness_digest),
        protocol=provenance['source']['protocol'], tools=provenance['toolSha256'])
    comparison = dict(schemaVersion='mvs-focused-family-comparison/v1',
        status='passed' if not failures else 'failed', exactNativeReferenceAgreement=not failures,
        nativeArithmeticAgreement=not exact_compare(reference, native),
        archivedBaselineAgreement=not baseline, casesCompared=len(cases),
        archivedBaselineDecisionsCompared=2 * sum(case['analysis_eligible'] for case in cases),
        nativeMemberResultsCompared=len(cases) * (sum(map(len, FAMILIES.values())) + 12),
        method='Independent Python binary64 min(1,p*fixed_multiplier), strict adjusted p < 0.05; every output field exact',
        numericTolerance=0, bindings=bindings, failures=failures, scientificReadiness='NO-GO unchanged')
    # Re-read all provenance before committing derived evidence, including source files.
    read_prepared(benchmark, out, protocol_path, protocol_sha)
    require(all(sha256(path) == digest for path, digest in ((native_path, native_digest),
        (core_assembly, core_digest), (harness_assembly, harness_digest))), 'Native evidence changed during comparison')
    return comparison, cases, reference['cases'], stability, protocol


def per_case_document(cases, results, stability, comparison):
    # Native evidence retains all per-member adjusted values. Avoid duplicating
    # those large arrays here; the full native document was compared fieldwise.
    concise = []
    for case, result in zip(cases, results):
        methods = {name: {key: value for key, value in family.items() if key != 'members'}
                   for name, family in result['families'].items()}
        partition = dict(result['simultaneousPartition'])
        partition['families'] = {name: {key: value for key, value in family.items() if key != 'members'}
                                for name, family in partition['families'].items()}
        concise.append(dict(retained=case, availabilityStatus=result['availabilityStatus'],
            families=methods, simultaneousPartition=partition, naiveFocusedUnion=result['naiveFocusedUnion']))
    return dict(schemaVersion='mvs-focused-family-cases/v1', status=comparison['status'],
        bindings=comparison['bindings'], cases=concise, stability=stability,
        perMemberAdjustedValues='All per-member adjusted values are retained in the hash-bound native evidence and compared exactly.',
        scientificReadiness='NO-GO unchanged', limitations=LIMITATIONS)


def compare(benchmark, out, protocol_path, protocol_sha, native_path, core_assembly, harness_assembly):
    out = Path(out)
    require({path.name for path in out.iterdir()} == {INPUT_FILE, PROVENANCE_FILE, NATIVE_FILE},
            'Unexpected files before comparison; existing results are never overwritten')
    comparison, cases, results, stability, _ = comparison_evidence(benchmark, out, protocol_path,
        protocol_sha, native_path, core_assembly, harness_assembly)
    per_case = per_case_document(cases, results, stability, comparison)
    write_new(out / COMPARISON_FILE, json_bytes(comparison))
    write_new(out / CASES_FILE, json_bytes(per_case))
    return comparison


def wilson(successes, denominator):
    require(type(successes) is int and type(denominator) is int and 0 <= successes <= denominator,
            'Invalid rate counts')
    if not denominator:
        return dict(count=successes, denominator=0, rate=None, wilson95=None)
    z = 1.959963984540054
    p = successes / denominator
    scale = 1 + z*z/denominator
    center = (p + z*z/(2*denominator)) / scale
    half = z*math.sqrt(p*(1-p)/denominator + z*z/(4*denominator*denominator)) / scale
    return dict(count=successes, denominator=denominator, rate=p,
                wilson95=[max(0.0, center-half), min(1.0, center+half)])


def result_events(result):
    events = {name: family['anyRejected'] for name, family in result['families'].items()}
    events.update({f'partition4.{name}': result['simultaneousPartition']['families'][name]['anyRejected']
                   for name in PARTITION})
    events['partition4.union'] = result['simultaneousPartition']['anyRejected']
    events['uncontrolledFocusedUnion'] = result['naiveFocusedUnion']['anyRejected']
    return events


def summarize_conditions(cases, results):
    require(len(cases) == len(results), 'Case/result count mismatch')
    grouped = {}
    for case, result in zip(cases, results):
        require(case['id'] == result['id'], 'Case/result identity mismatch')
        grouped.setdefault((case['condition'], case['phase']), []).append((case, result))
    summaries = []
    for (condition, phase), pairs in grouped.items():
        completed = [pair for pair in pairs if pair[0]['analysis_eligible']]
        n = len(pairs)
        events = [result_events(result) for _, result in completed]
        method_names = list(result_events(pairs[0][1]))
        methods = {}
        for name in method_names:
            count = sum(event[name] for event in events)
            gains = sum(event[name] and not event['all12'] for event in events)
            losses = sum(event['all12'] and not event[name] for event in events)
            methods[name] = dict(allRequested=wilson(count, n),
                allRequestedInterpretation='operational discovery rate; failed cases have no discovery, not observed scientific nonrejections',
                completedOnly=wilson(count, len(completed)), pairedVersusAll12=dict(
                    candidateOnly=gains, baselineOnly=losses,
                    bothRejected=sum(event[name] and event['all12'] for event in events),
                    neitherRejected=sum(not event[name] and not event['all12'] for event in events),
                    requestedRateDelta=(gains-losses)/n,
                    completedRateDelta=(gains-losses)/len(completed) if completed else None,
                    interpretation='descriptive-only-no-selection-gate'))
        summaries.append(dict(condition=condition, phase=phase,
            scientificRole='reproducibility-only' if phase != 'main' else
                'null-condition' if condition in NULL_CONDITIONS else 'alternative-condition',
            requested=n, completed=sum(case['status'] == 'completed' for case, _ in pairs),
            failed=sum(case['status'] == 'failed' for case, _ in pairs),
            analyzedCompleted=len(completed), notAnalyzed=n-len(completed),
            missingDiagnostics=sum(case['diagnostics_status'] != 'retained' for case, _ in pairs),
            availabilityStatusCounts=dict(Counter(result['availabilityStatus'] for _, result in pairs)),
            availableMetricSlots=sum(sum(case['observed_available']) for case, _ in pairs),
            unavailableMetricSlots=sum(12-sum(case['observed_available']) for case, _ in pairs),
            methods=methods))
    return summaries


def agreement(rows, labels, mapping):
    matrix = [[0 for _ in labels] for _ in labels]
    index = {name: i for i, name in enumerate(labels)}
    for row in rows:
        matrix[index[mapping[row['topLeft']]]][index[mapping[row['topRight']]]] += 1
    n = len(rows)
    left = [sum(row) for row in matrix]
    right = [sum(row[col] for row in matrix) for col in range(len(labels))]
    matches = sum(matrix[i][i] for i in range(len(labels)))
    chance = sum(a*b for a, b in zip(left, right))/(n*n) if n else None
    observed = matches/n if n else None
    kappa = (observed-chance)/(1-chance) if chance is not None and 1-chance > 0 else None
    return dict(labels=list(labels), confusionMatrix=matrix, rowMeaning='left top ID label',
        columnMeaning='right top ID label', leftMarginals=dict(zip(labels, left)),
        rightMarginals=dict(zip(labels, right)), agreement=wilson(matches, n),
        independentMarginalChanceAgreement=chance, cohenKappa=kappa,
        kappaUndefinedReason='zero completed pairs' if not n else
            'expected agreement equals one' if chance == 1 else None)


def summarize_stability(rows):
    completed = [row for row in rows if row['status'] == 'completed']
    metric_map = {metric: metric for metric in METRICS}
    coarse = ('location4', 'variability7', 'magnitude1')
    family_map = {METRICS[index]: name for name in coarse for index in FAMILIES[name]}
    partition_map = {METRICS[index]: name for name in PARTITION for index in FAMILIES[name]}
    values = [row['archivedWholeRegistryStatistic'] for row in completed]
    return dict(requested=len(rows), completed=len(completed),
        failed=sum(row['status'] == 'failed' for row in rows),
        retainedArchivedWholeRegistryStatistic=dict(count=len(values),
            mean=statistics.mean(values) if values else None,
            median=statistics.median(values) if values else None,
            minimum=min(values) if values else None, maximum=max(values) if values else None,
            interpretation='Retained archived statistic only; known joint-tie issue; not standard tau-b or candidate-set recomputation'),
        exactMetric=agreement(completed, METRICS, metric_map),
        registeredFamilyCoarsening=agreement(completed, coarse, family_map),
        partition4Coarsening=agreement(completed, PARTITION, partition_map),
        interpretation='Descriptive top-ID coarsening; no improved selection or candidate-set ranking claim')


def report(benchmark, out, protocol_path, protocol_sha, native_path, core_assembly, harness_assembly):
    out = Path(out)
    require({path.name for path in out.iterdir()} ==
            {INPUT_FILE, PROVENANCE_FILE, NATIVE_FILE, COMPARISON_FILE, CASES_FILE},
            'Unexpected files before report; existing reports are never overwritten')
    comparison, cases, results, stability, protocol = comparison_evidence(benchmark, out,
        protocol_path, protocol_sha, native_path, core_assembly, harness_assembly)
    require(comparison['status'] == 'passed', 'Failed comparison cannot produce accepted aggregate report')
    require(regular_file(out / COMPARISON_FILE).read_bytes() == json_bytes(comparison),
            'Comparison evidence changed')
    per_case = per_case_document(cases, results, stability, comparison)
    require(regular_file(out / CASES_FILE).read_bytes() == json_bytes(per_case), 'Per-case evidence changed')
    summary = dict(schemaVersion='mvs-focused-family-summary/v1', status='passed',
        scientificReadiness='NO-GO unchanged', newScientificVerdict=None, candidateSelected=None,
        alpha=ALPHA, familyDefinitions=family_definitions(), bindings=comparison['bindings'],
        structuralCounts=dict(cases=len(cases), mainCases=sum(case['phase'] == 'main' for case in cases),
            conditionPhaseGroups=len({(case['condition'], case['phase']) for case in cases}),
            metricRows=len(cases)*12, procedureRows=len(cases)*8, stabilityRows=len(stability)),
        conditionPhaseSummaries=summarize_conditions(cases, results),
        stability=summarize_stability(stability), priorInspectedResults=protocol['priorInspectedResults'],
        engineeringAcceptance=comparison, limitations=LIMITATIONS)
    write_new(out / SUMMARY_FILE, json_bytes(summary))
    filenames = (INPUT_FILE, PROVENANCE_FILE, NATIVE_FILE, COMPARISON_FILE, CASES_FILE, SUMMARY_FILE)
    write_new(out / CHECKSUM_FILE, ''.join(f'{sha256(out / name)}  {name}\n'
        for name in sorted(filenames)).encode('ascii'))
    return dict(status='passed', cases=len(cases), conditionPhaseGroups=len(summary['conditionPhaseSummaries']),
                stabilitySplits=len(stability), scientificReadiness='NO-GO unchanged')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'compare', 'report'):
        command = subcommands.add_parser(name)
        command.add_argument('--benchmark', type=Path, required=True)
        command.add_argument('--out', type=Path, required=True)
        command.add_argument('--protocol', type=Path, required=True)
        command.add_argument('--protocol-sha256', required=True)
        if name != 'prepare':
            command.add_argument('--native', type=Path, required=True)
            command.add_argument('--core-assembly', type=Path, required=True)
            command.add_argument('--harness-assembly', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        common = (args.benchmark, args.out, args.protocol, args.protocol_sha256)
        if args.command == 'prepare':
            result = prepare(*common)
        else:
            function = compare if args.command == 'compare' else report
            result = function(*common, args.native, args.core_assembly, args.harness_assembly)
    except (ValueError, KeyError, TypeError, OSError, IndexError, OverflowError) as error:
        print(json.dumps(dict(status='invalid', error=str(error))))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    sys.exit(main())
