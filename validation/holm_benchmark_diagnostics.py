#!/usr/bin/env python3
"""Post-hoc, development-only fixed-12 Holm diagnostics on frozen round-6 data.

prepare --benchmark FROZEN_DIR --out NEW_DIR
analyze --benchmark FROZEN_DIR --out NEW_DIR \
    --native NEW_DIR/multiplicity-native.json --core-assembly ACTUAL_CORE_DLL

Between these commands run the existing native test exporter's
--export-multiplicity-diagnostics FIXTURES OUTPUT command. No benchmark is run,
no production method is activated, and the original scientific NO-GO is retained.
Exit 0: consistent complete diagnostics; 1: arithmetic/decision disagreement;
2: invalid evidence or incomplete raw diagnostics. Existing evidence is never
overwritten. All discovery counts refer only to completed, retained replications.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re

import check_benchmark_diagnostics as raw_check
import multiplicity_reference

METRICS = raw_check.METRICS
FAMILY_SIZE = 12
ALPHA = .05
PROTOCOL_HASH = 'b81be4a1a86e8ba4b013eb63b75256d16e439fb824e7fa68efae5f28e48de268'
# Pins identify the actual immutable development run, not any self-consistent
# lookalike with a rewritten manifest/checksum file. Synthetic tests exercise the
# frame functions or explicitly replace these pins in their temporary directories.
FROZEN_HASHES = {
    'benchmark_choices.csv': '6cc0c577c53af29116ab1190b978e7e6709811ffbe194d594ff55016e1602f25',
    'benchmark_manifest.json': '4dd862d8aacc3592c018215f33494534ebfb6452b2324968b738521d37f808af',
    'benchmark_metrics.csv': '18d9352b927fdbc65e9b48331a6dea7b29fe4dde7eeff5da54ebb335178228dd',
    'benchmark_protocol.txt': PROTOCOL_HASH,
    'benchmark_replication_metrics.csv': '28e564d6e4acaa43736054b90c14afc5ac015366337dbc6d98e1003b712381f2',
    'benchmark_replication_procedures.csv': '59dfaf350313340d69d1f94be5982a160fa1d548e14be4b3d32fcccf4a242d07',
    'benchmark_replications.csv': 'e22c3d0e7d8151e71e582841c652fcc4b8888a3d2f730ba34e407024ed01bf03',
    'benchmark_report.md': '403742cb85f2e2a45ad693af60f3aaa8635e3f1fd89a3f170a7459d188a3a18c',
    'benchmark_stability.csv': '59be568fe843e8cfae1a8d5c4d7b9400d69948178cfd06dd50e51a065b499104',
    'benchmark_stability_replications.csv': 'f43adc15a64f22386a47684644c1f523d359cb00efa2ceb956564b08cb55621f',
    'benchmark_summary.csv': 'fd7a967562dbf8f7a9d855fe2e4a729be8d201df7833b7cbea144987a03eeb2a',
    'benchmark_verdicts.csv': '723113052de4bec366781dd4487ee650b89973d7015d6be335d53e437d63d76f',
}
IDENTITY = {
    'kind': 'mvs-benchmark', 'appVersion': '1.4.0', 'engineVersion': '1.6.2',
    'formulaVersion': 'MVS-1.4.0',
    'formulaHash': '10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c',
    'protocolVersion': 'MVS-BENCH-1.2.0', 'protocolHash': PROTOCOL_HASH,
    'protocolHashFrozen': PROTOCOL_HASH, 'protocolUnchanged': True,
    'profile': 'full', 'seed': 20260904,
    'diagnosticsVersion': 'MVS-BENCH-DIAGNOSTICS-1', 'overall': 'no-go',
}
PREPARED_FILES = ('multiplicity-fixtures.json', 'provenance.json')
RESULT_FILES = ('multiplicity-comparison.json', 'condition-summary.csv',
                'diagnostics.json', 'SHA256SUMS.txt')
NATIVE_FILE = 'multiplicity-native.json'
LIMITATIONS = [
    'Post-hoc reuse of the frozen MVS-BENCH-1.2.0 development run; not unseen validation.',
    'The original scientific verdict remains NO-GO. No new benchmark scientific verdict is assigned.',
    'No benchmark rerun, production activation, default change, or recalibration occurred.',
    'The complete ordered twelve-member family includes unavailable and missing slots.',
    'Counts use completed replications with retained diagnostics; failed and missing rows remain explicit.',
    'Conditions are reported separately; no heterogeneous pooled scientific rate is calculated.',
    'Replay-first and replay-second are reproducibility passes, not independent scientific replications.',
    'Holm and Bonferroni have the same any-rejection event for this fixed family; additional member discoveries do not improve global-any power.',
    'Arithmetic agreement does not establish valid marginal p-values, strong FWER control, or release readiness.',
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), f'Not a regular evidence file: {path.name}')
    return path


def json_bytes(document):
    return (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def read_json(path):
    # Reject duplicate JSON keys and non-standard NaN/Infinity rather than letting
    # provenance or numeric evidence acquire a parser-dependent interpretation.
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError(f'Non-finite JSON constant: {value}')
    return json.loads(regular_file(path).read_text(encoding='utf-8-sig'),
                      object_pairs_hook=object_pairs, parse_constant=nonfinite)


def source_hashes(folder):
    folder = Path(folder)
    require(folder.is_dir() and not folder.is_symlink(), 'Benchmark must be a regular directory')
    checksum_file = regular_file(folder / 'SHA256SUMS.txt')
    expected = {}
    for line in checksum_file.read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        require(match is not None, 'Unsafe or malformed source checksum entry')
        digest, name = match.groups()
        require(name not in expected, f'Duplicate source checksum target: {name}')
        expected[name] = digest
    require(set(expected) == set(FROZEN_HASHES), 'Missing or unexpected required source checksum targets')
    result = {}
    for name, digest in expected.items():
        require(digest == FROZEN_HASHES[name], f'Not the frozen development source: {name}')
        actual = sha256(regular_file(folder / name))
        require(actual == digest, f'Source checksum mismatch: {name}')
        result[name] = actual
    result['SHA256SUMS.txt'] = sha256(checksum_file)
    return dict(sorted(result.items()))


def validate_identity(manifest):
    for name, value in IDENTITY.items():
        require(type(manifest.get(name)) is type(value) and manifest[name] == value,
                f'Unexpected source identity: {name}')
    require(manifest.get('thresholds', {}).get('alpha') == ALPHA, 'Unexpected source alpha')
    require(manifest.get('replications') == dict(primary=1000, grid=250, calibration=1000,
                                                stability=120, determinism=60),
            'Unexpected frozen replication budgets')
    require(isinstance(manifest.get('files'), list) and
            len(manifest['files']) == len(set(manifest['files'])) and
            set(manifest['files']) == set(FROZEN_HASHES) - {'benchmark_manifest.json'},
            'Manifest file inventory does not match checksummed raw files')


def replication_key(row):
    key = tuple(row[name] for name in raw_check.KEY)
    condition, phase, index = key
    require(isinstance(condition, str) and bool(condition), 'Missing condition')
    require(phase in ('main', 'replay-first', 'replay-second'), f'Invalid phase: {key}')
    require(isinstance(index, str) and index.isascii() and index.isdigit() and
            str(int(index)) == index, f'Invalid replication index: {key}')
    return key


def build_fixtures(replications, metric_rows, procedure_rows, summary_rows):
    """Validate small in-memory frames as well as full raw CSVs; never drop rows."""
    reps = {}
    for row in replications:
        key = replication_key(row)
        require(key not in reps, f'Duplicate replication key: {key}')
        reps[key] = row
    require(bool(reps), 'No replication rows')
    metrics, procedures = {}, {}
    for rows, grouped, label in ((metric_rows, metrics, 'metric'),
                                  (procedure_rows, procedures, 'procedure')):
        for row in rows:
            key = replication_key(row)
            require(key in reps, f'Orphan {label} row: {key}')
            grouped.setdefault(key, []).append(row)
        require(set(grouped) == set(reps), f'Missing {label} rows')
    planned = {}
    summary_keys = set()
    for row in summary_rows:
        key = row['condition'], row['procedure']
        require(key not in summary_keys and key[1] in raw_check.PROCEDURES,
                f'Duplicate or unknown summary procedure: {key}')
        summary_keys.add(key)
        phases = ('replay-first', 'replay-second') if row['stage'] == 'determinism' else ('main',)
        count = int(row['planned'])
        require(count > 0 and str(count) == row['planned'], 'Invalid planned count')
        for phase in phases:
            group = row['condition'], phase
            require(group not in planned or planned[group] == count, 'Inconsistent planned counts')
            planned[group] = count
    require(summary_keys == {(condition, proc) for condition, _ in planned for proc in raw_check.PROCEDURES},
            'Missing summary procedures')
    groups = {}
    cases = []
    for key, row in reps.items():
        condition, phase, index = key
        groups.setdefault((condition, phase), []).append(int(index))
        require([item['metric'] for item in metrics[key]] == list(METRICS),
                f'Missing, duplicate, unknown or reordered fixed-family metric rows: {key}')
        proc = {item['procedure']: item for item in procedures[key]}
        require(len(procedures[key]) == len(raw_check.PROCEDURES) and
                set(proc) == set(raw_check.PROCEDURES), f'Missing or duplicate procedure rows: {key}')
        status, diagnostic_status = row['status'], row['diagnostics_status']
        require(status in ('completed', 'failed', 'unknown_legacy'), f'Invalid replication status: {key}')
        require(diagnostic_status in ('retained', 'legacy_missing'), f'Invalid diagnostics status: {key}')
        require(status != 'unknown_legacy' or diagnostic_status == 'legacy_missing',
                f'Unknown status with retained diagnostics: {key}')
        eligible = status == 'completed' and diagnostic_status == 'retained'
        values, availability, raw_rejections = [], [], []
        for item in metrics[key]:
            p = raw_check.number(item['p_value'])
            available = raw_check.boolean(item['observed_available'], optional=True)
            rejected = raw_check.boolean(item['rejected'], optional=True)
            require(p is None or (0 <= p <= 1 and available is True), f'Invalid p/availability: {key}')
            require(available is not True or p is not None, f'Available test without p: {key}')
            require((status == 'completed') == (rejected is not None), f'Invalid raw decision presence: {key}')
            if eligible:
                require(available is not None and rejected == (p is not None and p < ALPHA),
                        f'Raw metric decision mismatch: {key}')
            values.append(p)
            availability.append(available)
            raw_rejections.append(rejected)
        legacy = {}
        for name, item in proc.items():
            claimed = raw_check.boolean(item['claimed'], optional=True)
            rejected = raw_check.boolean(item['rejected'], optional=True)
            require((status == 'completed') == (rejected is not None and claimed is not None),
                    f'Invalid legacy procedure decision presence: {key}')
            if status != 'completed':
                require(claimed is None and rejected is None and item['chosen_metric'] == '',
                        f'Failed/unknown procedure counted: {key}')
            if name in ('bonferroni', 'mvs_registry_corrected'):
                legacy[name] = rejected
        cases.append(dict(id=json.dumps(key, separators=(',', ':')), condition=condition,
                          phase=phase, replication_index=int(index), family_size=FAMILY_SIZE,
                          p_values=values, observed_available=availability,
                          raw_metric_rejected=raw_rejections, legacy_procedure_rejected=legacy,
                          status=status, diagnostics_status=diagnostic_status,
                          error=row.get('error', ''), analysis_eligible=eligible))
    require(set(groups) == set(planned), 'Missing or unexpected diagnostic phases')
    for key, indices in groups.items():
        require(sorted(indices) == list(range(planned[key])), f'Missing planned replication indices: {key}')
    return dict(schema='MVS-MULTIPLICITY-REFERENCE-1', alpha=ALPHA,
                purpose='post-hoc development diagnostics only', metric_order=list(METRICS),
                family_size=FAMILY_SIZE, original_scientific_verdict='NO-GO', cases=cases)


def load_source(folder):
    hashes = source_hashes(folder)
    manifest = read_json(Path(folder) / 'benchmark_manifest.json')
    validate_identity(manifest)
    reconciliation = raw_check.validate(folder)
    fixture = build_fixtures(*[raw_check.read_csv(folder, name) for name in (
        'benchmark_replications.csv', 'benchmark_replication_metrics.csv',
        'benchmark_replication_procedures.csv', 'benchmark_summary.csv')])
    require(len(fixture['cases']) == 5370, 'Unexpected frozen replication row count')
    require(source_hashes(folder) == hashes, 'Source changed while being read')
    source = dict(identity=dict(IDENTITY), source_sha256=hashes,
                  replication_rows=len(fixture['cases']), metric_rows=len(fixture['cases']) * FAMILY_SIZE,
                  raw_reconciliation=reconciliation)
    return fixture, source


def tool_hashes():
    return {path.name: sha256(path) for path in (Path(__file__), Path(raw_check.__file__),
                                               Path(multiplicity_reference.__file__))}


def provenance_document(source, fixture_digest):
    return dict(schema='MVS-HOLM-BENCHMARK-PROVENANCE-1', source=source,
                fixture_sha256=fixture_digest, tool_sha256=tool_hashes(),
                family_size=FAMILY_SIZE, metric_order=list(METRICS), alpha=ALPHA,
                original_scientific_verdict='NO-GO', limitations=LIMITATIONS)


def check_output_location(benchmark, out):
    benchmark, out = Path(benchmark).resolve(), Path(out).resolve()
    require(out != benchmark and benchmark not in out.parents,
            'Derived output must be outside the immutable benchmark directory')


def write_new(path, content):
    with Path(path).open('xb') as stream:
        stream.write(content)


def prepare(benchmark, out):
    out = Path(out)
    check_output_location(benchmark, out)
    require(not out.exists() and not out.is_symlink(), 'Preparation refuses an existing output directory')
    fixture, source = load_source(benchmark)
    content = json_bytes(fixture)
    provenance = provenance_document(source, hashlib.sha256(content).hexdigest())
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / PREPARED_FILES[0], content)
    write_new(out / PREPARED_FILES[1], json_bytes(provenance))
    return dict(status='prepared', cases=len(fixture['cases']), fixture_sha256=provenance['fixture_sha256'],
                original_scientific_verdict='NO-GO')


def validate_native(fixture, native, fixture_digest, assembly_digest):
    require(native.get('schema') == 'MVS-MULTIPLICITY-NATIVE-1', 'Unexpected native schema')
    require(native.get('fixtureSha256') == fixture_digest, 'Native fixture provenance mismatch')
    require(native.get('coreAssemblySha256') == assembly_digest, 'Actual native Core assembly hash mismatch')
    require(native.get('engineVersion') == '1.6.2' and type(native.get('activeMetricCount')) is int and
            native['activeMetricCount'] == FAMILY_SIZE, 'Unexpected native engine/family identity')
    require(isinstance(native.get('nativeRuntime'), str) and bool(native['nativeRuntime'].strip()),
            'Missing native runtime')
    rows = native.get('results')
    require(isinstance(rows, list) and [x['id'] for x in rows] == [x['id'] for x in fixture['cases']],
            'Native cases missing, duplicate or reordered')
    for row in rows:
        for method in ('bonferroni', 'holm'):
            values, rejected = row.get(method), row.get(method + '_rejected')
            require(isinstance(values, list) and len(values) == FAMILY_SIZE, 'Native vector length mismatch')
            require(all(p is None or (type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1)
                        for p in values), 'Invalid native adjusted p-value')
            require(isinstance(rejected, list) and len(rejected) == FAMILY_SIZE and
                    all(type(item) is bool for item in rejected), 'Invalid native rejection vector')


def summarize(fixture, native):
    """Native counts only; the independent exhaustive comparison is a separate gate."""
    summaries, per_metric, failures, excluded = {}, {}, [], []
    for case, row in zip(fixture['cases'], native['results']):
        key = case['condition'], case['phase']
        if key not in summaries:
            summaries[key] = dict(condition=key[0], phase=key[1], planned=0, completed=0,
                failed=0, unknown_status=0, missing_diagnostics=0, analyzed_completed=0,
                not_analyzed=0, available_slots=0, unavailable_slots=0, unknown_availability_slots=0,
                replications_with_unavailable_metrics=0, bonferroni_any_rejection=0,
                holm_any_rejection=0, bonferroni_member_discoveries=0, holm_member_discoveries=0,
                additional_holm_members=0, replications_with_additional_holm_members=0)
            per_metric[key] = {name: dict(metric=name, available_in_analyzed=0,
                bonferroni_discoveries=0, holm_discoveries=0, additional_holm_discoveries=0) for name in METRICS}
        group = summaries[key]
        group['planned'] += 1
        group[{'completed': 'completed', 'failed': 'failed', 'unknown_legacy': 'unknown_status'}[case['status']]] += 1
        group['missing_diagnostics'] += case['diagnostics_status'] == 'legacy_missing'
        group['available_slots'] += sum(x is True for x in case['observed_available'])
        group['unavailable_slots'] += sum(x is False for x in case['observed_available'])
        group['unknown_availability_slots'] += sum(x is None for x in case['observed_available'])
        group['replications_with_unavailable_metrics'] += any(x is False for x in case['observed_available'])
        bf, holm = row['bonferroni_rejected'], row['holm_rejected']
        if any(bf) != any(holm):
            failures.append(f"{case['id']}: Holm/Bonferroni any-rejection mismatch")
        if any(b and not h for b, h in zip(bf, holm)):
            failures.append(f"{case['id']}: Bonferroni discoveries are not a subset of Holm")
        if not case['analysis_eligible']:
            group['not_analyzed'] += 1
            excluded.append(dict(id=case['id'], status=case['status'], diagnostics_status=case['diagnostics_status'],
                                 error=case['error'], reason='Arithmetic retained, excluded from discovery counts'))
            continue
        group['analyzed_completed'] += 1
        # Raw metric decisions are unadjusted p<alpha. Verify those separately,
        # then check each native corrected decision against the legacy fixed-12
        # raw cutoff and both recorded family procedures on these actual vectors.
        raw_expected = [p is not None and p < ALPHA for p in case['p_values']]
        bf_expected = [p is not None and p < ALPHA / FAMILY_SIZE for p in case['p_values']]
        if case['raw_metric_rejected'] != raw_expected or bf != bf_expected:
            failures.append(f"{case['id']}: Native Bonferroni/raw metric decision mismatch")
        for method, rejected in case['legacy_procedure_rejected'].items():
            if any(bf) != rejected:
                failures.append(f"{case['id']}: Native Bonferroni/legacy {method} procedure mismatch")
        additional = sum(h and not b for b, h in zip(bf, holm))
        group['bonferroni_any_rejection'] += any(bf)
        group['holm_any_rejection'] += any(holm)
        group['bonferroni_member_discoveries'] += sum(bf)
        group['holm_member_discoveries'] += sum(holm)
        group['additional_holm_members'] += additional
        group['replications_with_additional_holm_members'] += additional > 0
        for index, metric in enumerate(METRICS):
            item = per_metric[key][metric]
            item['available_in_analyzed'] += case['observed_available'][index] is True
            item['bonferroni_discoveries'] += bf[index]
            item['holm_discoveries'] += holm[index]
            item['additional_holm_discoveries'] += holm[index] and not bf[index]
    metrics = [dict(condition=key[0], phase=key[1], metrics=list(items.values())) for key, items in per_metric.items()]
    return list(summaries.values()), metrics, excluded, failures


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def analyze(benchmark, out, native_path, core_assembly):
    out, native_path = Path(out), Path(native_path)
    check_output_location(benchmark, out)
    require(out.is_dir() and not out.is_symlink(), 'Missing prepared output directory')
    require(native_path.resolve() == (out / NATIVE_FILE).resolve(),
            'Native evidence must be out/multiplicity-native.json')
    require(all(not (out / name).exists() and not (out / name).is_symlink() for name in RESULT_FILES),
            'Analysis refuses existing result files')
    require({p.name for p in out.iterdir()} == set(PREPARED_FILES) | {NATIVE_FILE},
            'Unexpected files in prepared output directory')
    fixture, source = load_source(benchmark)
    fixture_path, provenance_path = (out / name for name in PREPARED_FILES)
    expected_fixture = json_bytes(fixture)
    require(regular_file(fixture_path).read_bytes() == expected_fixture, 'Prepared fixture was changed')
    fixture_digest = hashlib.sha256(expected_fixture).hexdigest()
    expected_provenance = provenance_document(source, fixture_digest)
    require(regular_file(provenance_path).read_bytes() == json_bytes(expected_provenance),
            'Prepared source, tool or provenance was changed')
    native = read_json(native_path)
    assembly_digest = sha256(regular_file(core_assembly))
    native_digest = sha256(native_path)
    provenance_digest = sha256(provenance_path)
    validate_native(fixture, native, fixture_digest, assembly_digest)
    # Deliberately use the existing exhaustive closed-intersection reference.
    # Do not replace this with another sort/rank implementation of native Holm.
    comparison = multiplicity_reference.compare(fixture_path, native_path)
    summaries, metric_counts, excluded, decision_failures = summarize(fixture, native)
    complete = source['raw_reconciliation']['status'] == 'passed'
    passed = comparison['passed'] and not decision_failures
    status = 'failed' if not passed else 'passed' if complete else 'incomplete'
    comparison.update(native_sha256=native_digest, core_assembly_sha256=assembly_digest,
                      reference_sha256=expected_provenance['tool_sha256']['multiplicity_reference.py'],
                      reference_method='exhaustive closed Bonferroni intersections, every nonempty subset',
                      legacy_decision_agreement=not decision_failures, decision_failures=decision_failures)
    comparison['passed'] = passed
    for row in summaries:
        row['diagnostic_status'] = status
    diagnostics = dict(schema='MVS-HOLM-BENCHMARK-DIAGNOSTICS-1', status=status,
        original_scientific_verdict='NO-GO', new_benchmark_scientific_verdict=None,
        family_size=FAMILY_SIZE, metric_order=list(METRICS), alpha=ALPHA,
        source_sha256=source['source_sha256'], fixture_sha256=fixture_digest,
        provenance_sha256=provenance_digest, native_sha256=native_digest,
        core_assembly_sha256=assembly_digest, native_runtime=native['nativeRuntime'],
        tool_sha256=expected_provenance['tool_sha256'],
        structural_counts=dict(replication_rows=len(fixture['cases']), metric_rows=FAMILY_SIZE * len(fixture['cases']),
                               condition_phase_groups=len(summaries), excluded_replications=len(excluded)),
        raw_reconciliation_status=source['raw_reconciliation']['status'],
        independent_arithmetic_passed=not comparison['failures'],
        legacy_and_family_decisions_passed=not decision_failures,
        condition_phase_summaries=summaries, per_metric_discoveries=metric_counts,
        excluded_replications=excluded, failures=comparison['failures'] + decision_failures,
        limitations=LIMITATIONS)
    # Detect changes during the potentially long reference comparison before
    # committing derived evidence. This includes the exact supplied binary.
    require(source_hashes(benchmark) == source['source_sha256'], 'Source changed during analysis')
    require(sha256(fixture_path) == fixture_digest and sha256(provenance_path) == provenance_digest and
            sha256(native_path) == native_digest and sha256(core_assembly) == assembly_digest and
            tool_hashes() == expected_provenance['tool_sha256'], 'Evidence changed during analysis')
    outputs = {'multiplicity-comparison.json': json_bytes(comparison),
               'condition-summary.csv': csv_bytes(summaries), 'diagnostics.json': json_bytes(diagnostics)}
    for name, content in outputs.items():
        write_new(out / name, content)
    checksums = ''.join(f'{sha256(out / name)}  {name}\n' for name in
                        sorted(set(PREPARED_FILES) | {NATIVE_FILE} | set(outputs)))
    write_new(out / 'SHA256SUMS.txt', checksums.encode('ascii'))
    return dict(status=status, cases=len(fixture['cases']), comparisons=comparison['comparisons'],
                condition_phase_groups=len(summaries), original_scientific_verdict='NO-GO',
                failures=len(diagnostics['failures']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'analyze'):
        command = subcommands.add_parser(name)
        command.add_argument('--benchmark', type=Path, required=True)
        command.add_argument('--out', type=Path, required=True)
        if name == 'analyze':
            command.add_argument('--native', type=Path, required=True)
            command.add_argument('--core-assembly', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (prepare(args.benchmark, args.out) if args.command == 'prepare' else
                  analyze(args.benchmark, args.out, args.native, args.core_assembly))
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        print(json.dumps(dict(status='invalid', error=str(error))))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result['status'] == 'failed' else 2 if result['status'] == 'incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
