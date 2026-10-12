#!/usr/bin/env python3
"""Independent checks for unused, single-step maxT finite-matrix arithmetic.

The oracle counts a per-hypothesis union of indicators, without computing row
maxima or calling the native implementation. Counts and adjusted probabilities
are exact integers/Fractions. Scores are supplied finite binary64 values with a
common larger-is-more-extreme ordering. This does not choose an MVS null, score
normalization, resampling generator, or missing-value policy for real data.

The tiny exchangeable-label orbit below is a conditional toy calculation only.
Its omit-observed-row plus-one identity is special to that complete orbit; it
does not make exhaustive enumeration and Monte Carlo conventions interchangeable.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path


FIXTURE_SCHEMA = 'MVS-MAXT-FIXTURES-1'
NATIVE_SCHEMA = 'MVS-MAXT-NATIVE-1'
ALPHA = Fraction(1, 20)
DEFAULT_FIXTURES = Path(__file__).with_name('maxt-fixtures-v1.json')
TOY_FEATURES = ((0, 1, 3), (1, 4, 0), (2, 0, 5),
                (3, 5, 1), (4, 2, 4), (5, 3, 2))
TOY_ALPHA_GRID = (Fraction(1, 20), Fraction(1, 10), Fraction(1, 5),
                  Fraction(1, 4), Fraction(1, 2), Fraction(1))


def _score(value):
    if type(value) not in (int, float):
        raise ValueError('Scores must be finite numbers; no unavailable/null slots')
    try:
        score = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError('Scores must be finite binary64 numbers') from exc
    if not math.isfinite(score):
        raise ValueError('Scores must be finite binary64 numbers')
    return score


def reference(observed, resamples, family_size):
    """Return exact exceedance counts and plus-one probabilities for every slot."""
    if type(family_size) is not int or family_size < 1:
        raise ValueError('A positive, fixed integer family_size is required')
    if not isinstance(observed, list) or len(observed) != family_size:
        raise ValueError('Observed vector must contain the entire declared family')
    if not isinstance(resamples, list) or not resamples:
        raise ValueError('At least one complete resample row is required')
    observed_scores = [_score(value) for value in observed]
    rows = []
    for row in resamples:
        if not isinstance(row, list) or len(row) != family_size:
            raise ValueError('Every resample row must contain the entire family')
        # Validate every cell before counting. Short-circuiting an indicator must
        # never hide a NaN/unavailable cell elsewhere in a row.
        rows.append([_score(value) for value in row])
    counts = [sum(any(score >= threshold for score in row) for row in rows)
              for threshold in observed_scores]
    return dict(exceedance_counts=counts,
                adjusted_p=[Fraction(count + 1, len(rows) + 1) for count in counts])


def toy_orbit():
    """Enumerate all C(6,3) entity assignments, preserving three joint columns.

    Each feature column is a permutation of 0..5 on the same six entities.
    Its score is the absolute group-sum contrast, equivalently three times the
    absolute group-mean contrast. These deterministic integer scores have the
    same range/scale by construction. They are not selected MVS test statistics.
    """
    assignments = list(itertools.combinations(range(6), 3))
    scores = []
    for selected in assignments:
        selected = set(selected)
        scores.append([abs(sum(TOY_FEATURES[i][j] for i in selected) -
                           sum(TOY_FEATURES[i][j] for i in range(6) if i not in selected))
                       for j in range(3)])
    return assignments, scores


def build_fixtures():
    """Declarative frozen cases; hand counts are independent of the oracle."""
    cases = []

    def add(identifier, observed, rows, counts, **metadata):
        cases.append(dict(id=identifier, family_size=len(observed), observed=observed,
                          resamples=rows, expected_exceedance_counts=counts,
                          expected_adjusted_p=[str(Fraction(n + 1, len(rows) + 1))
                                               for n in counts], **metadata))

    observed = [2, 1, 4]
    rows = [[1, 0, -1], [2, -1, -1], [0, 1, -1], [3, 0, 1]]
    add('hand_ties', observed, rows, [2, 4, 0])
    add('hand_all_above', [0, 1, 2], [[2, -8, -8], [-8, 3, -8]], [2, 2, 2])
    add('hand_all_below', [4, 5, 6], [[1, 2, 3], [0, 0, 0]], [0, 0, 0])
    add('hand_all_equal', [2, 2, 2], [[2, 2, 2]] * 3, [3, 3, 3])
    add('hand_negative_finite', [-2, -1, 0],
        [[-3, -2, -4], [-1, -6, -5], [-3, -3, -3]], [2, 1, 0])
    add('hand_family_one', [2], [[0], [2], [3], [-1]], [2])
    add('hand_minimum_rows', [2, 0], [[1, -1]], [0, 1])
    for label, factor in [('tiny', 1e-100), ('large', 1e100)]:
        add('common_scale_' + label, [value * factor for value in observed],
            [[value * factor for value in row] for row in rows], [2, 4, 0],
            relation='common positive scale of hand_ties')
    add('common_translation', [value + 100 for value in observed],
        [[value + 100 for value in row] for row in rows], [2, 4, 0])
    order = [2, 0, 1]
    add('joint_column_permutation', [observed[i] for i in order],
        [[row[i] for i in order] for row in rows], [0, 2, 4])
    add('row_permutation', observed, list(reversed(rows)), [2, 4, 0])
    # Identical marginal multisets, distinct joint matrices. Dependence is part
    # of the supplied data, not a reason to generate columns independently.
    add('correlation_perfect', [2, 2], [[i, i] for i in range(4) for _ in range(4)], [8, 8])
    add('correlation_product', [2, 2], [list(pair) for pair in itertools.product(range(4), repeat=2)], [12, 12])
    add('correlation_opposed', [2, 2], [[i, 3 - i] for i in range(4) for _ in range(4)], [16, 16])
    for count in (18, 19, 20):
        add('resolution_B' + str(count), [1], [[0]] * count, [0])
    for count in (39, 40):
        add('nonzero_tail_B' + str(count), [1], [[1]] + [[0]] * (count - 1), [1])
    assignments, scores = toy_orbit()
    for index, assignment in enumerate(assignments):
        observed_score = scores[index]
        remaining = scores[:index] + scores[index + 1:]
        # A separate full-orbit union count supplies the exact tail. The observed
        # assignment necessarily contributes one for every hypothesis.
        full_counts = [sum(any(value >= threshold for value in row) for row in scores)
                       for threshold in observed_score]
        add('toy_assignment_' + ''.join(map(str, assignment)), observed_score,
            remaining, [count - 1 for count in full_counts],
            toy_assignment=list(assignment), exact_orbit_tail_counts=full_counts)
    return dict(schemaVersion=FIXTURE_SCHEMA, alpha=float(ALPHA),
                scoreConvention='complete finite binary64 joint matrix; larger is more extreme',
                tieConvention='inclusive >=', rejectionConvention='adjusted_p < alpha',
                unavailablePolicy='reject entire invalid input; never omit a family slot or row',
                scope='unused arithmetic only; no production activation or MVS FWER claim',
                toy=dict(entity_features=[list(row) for row in TOY_FEATURES],
                         independent_unit='entity', group_sizes=[3, 3], assignments=20,
                         score='absolute difference of group sums in each common-scale feature column',
                         convention='remove the one observed assignment, then apply plus one',
                         qualification='special full-orbit identity, not a general Monte Carlo/exhaustive interchange',
                         alpha_grid=[str(value) for value in TOY_ALPHA_GRID]), cases=cases)


def _reject_constant(value):
    raise ValueError('Nonstandard nonfinite JSON number: ' + value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def read_json(path):
    raw = Path(path).read_bytes()
    try:
        document = json.loads(raw, parse_constant=_reject_constant,
                              object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Malformed JSON evidence') from exc
    if not isinstance(document, dict):
        raise ValueError('Evidence must be a JSON object')
    return document, hashlib.sha256(raw).hexdigest()


def load_fixtures(path=DEFAULT_FIXTURES):
    document, digest = read_json(path)
    if document.get('schemaVersion') != FIXTURE_SCHEMA or type(document.get('alpha')) not in (int, float) or document['alpha'] != float(ALPHA):
        raise ValueError('Unknown fixture schema or alpha')
    cases = document.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Fixture cases must be a nonempty list')
    identifiers = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not case['id']:
            raise ValueError('Missing fixture identifier')
        identifiers.append(case['id'])
        try:
            reference(case['observed'], case['resamples'], case['family_size'])
        except KeyError as exc:
            raise ValueError('Missing fixture matrix field') from exc
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate fixture identifiers')
    return document, digest


def audit_frozen_fixtures(path=DEFAULT_FIXTURES):
    """Check frozen definitions, hand answers, transformations and the full toy."""
    document, digest = load_fixtures(path)
    if document != build_fixtures():
        raise ValueError('Frozen fixture definition mismatch')
    for case in document['cases']:
        result = reference(case['observed'], case['resamples'], case['family_size'])
        if result['exceedance_counts'] != case['expected_exceedance_counts'] or result['adjusted_p'] != [Fraction(value) for value in case['expected_adjusted_p']]:
            raise ValueError('Frozen hand/orbit expectation mismatch: ' + case['id'])
    assignments, scores = toy_orbit()
    probabilities = []
    with_identity_differences = 0
    for index, assignment in enumerate(assignments):
        remaining = scores[:index] + scores[index + 1:]
        actual = reference(scores[index], remaining, 3)['adjusted_p']
        exact = [Fraction(sum(any(score >= threshold for score in row) for row in scores),
                          len(assignments)) for threshold in scores[index]]
        if actual != exact:
            raise ValueError('Omit-observed plus-one toy identity failed')
        # The global event corresponds to the largest observed threshold. This
        # identity checks the family-any event in addition to marginal values.
        largest_threshold = sorted(scores[index])[-1]
        global_tail = Fraction(sum(any(score >= largest_threshold for score in row)
                                   for row in scores), len(assignments))
        if min(actual) != global_tail:
            raise ValueError('Family-any/global-tail toy identity failed')
        # Supplying ALL N assignments to the Monte Carlo formula deliberately
        # yields (c+1)/(N+1), not c/N. Record that these differ when c<N.
        with_identity = reference(scores[index], scores, 3)['adjusted_p']
        if any(left != right for left, right in zip(with_identity, exact)):
            with_identity_differences += 1
        probabilities.append(exact)
    if not with_identity_differences:
        raise ValueError('Toy does not distinguish full-orbit and plus-one conventions')
    bounds = []
    for alpha in TOY_ALPHA_GRID:
        count = sum(any(value < alpha for value in row) for row in probabilities)
        rate = Fraction(count, len(assignments))
        if rate > alpha:
            raise ValueError('Conditional toy family-any bound failed')
        bounds.append(dict(alpha=str(alpha), family_any_count=count,
                           assignment_count=len(assignments), family_any_rate=str(rate)))
    return dict(schemaVersion='MVS-MAXT-REFERENCE-CHECK-1', fixtureSha256=digest,
                passed=True, cases=len(document['cases']),
                adjusted_values=sum(case['family_size'] for case in document['cases']),
                toy_identity_cases=len(assignments), toy_conditional_bounds=bounds,
                toy_full_orbit_plus_one_differs_cases=with_identity_differences,
                qualification='Conditional complete-null toy only; not MVS FWER or partial-null proof; native parity not checked')


def compare(fixtures, native, core_assembly):
    """Check every supplied native result and bind it to fixture and binary bytes.

    Hash equality binds documents to supplied bytes, not an authenticated record
    of execution. Native-shaped unit-test documents are not native evidence.
    """
    document, digest = load_fixtures(fixtures)
    frozen_fixture = Path(fixtures).resolve() == DEFAULT_FIXTURES.resolve()
    if frozen_fixture:
        audit_frozen_fixtures(fixtures)
    actual, native_digest = read_json(native)
    assembly_digest = hashlib.sha256(Path(core_assembly).read_bytes()).hexdigest()
    if actual.get('schemaVersion') != NATIVE_SCHEMA or actual.get('fixtureSha256') != digest:
        raise ValueError('Native schema or fixture hash mismatch')
    if actual.get('engineVersion') != '1.6.2' or type(actual.get('activeMetricCount')) is not int or actual['activeMetricCount'] != 12:
        raise ValueError('Native engine identity or active family mismatch')
    if actual.get('coreAssemblySha256') != assembly_digest:
        raise ValueError('Native Core assembly hash mismatch against supplied binary')
    if not isinstance(actual.get('nativeRuntime'), str) or not actual['nativeRuntime'].strip():
        raise ValueError('Missing native runtime provenance')
    rows = actual.get('results')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows) or [row.get('id') for row in rows] != [case['id'] for case in document['cases']]:
        raise ValueError('Native cases missing, extra, duplicate or reordered')
    failures = []
    checked = []
    for case, row in zip(document['cases'], rows):
        size, count = case['family_size'], len(case['resamples'])
        if type(row.get('family_size')) is not int or row['family_size'] != size:
            raise ValueError('Native family_size mismatch: ' + case['id'])
        if type(row.get('resample_count')) is not int or row['resample_count'] != count:
            raise ValueError('Native resample_count mismatch: ' + case['id'])
        for key in ('exceedance_counts', 'adjusted_p', 'rejected'):
            if not isinstance(row.get(key), list) or len(row[key]) != size:
                raise ValueError('Native vector length or missing field: ' + key)
        expected = reference(case['observed'], case['resamples'], size)
        for i, (got_count, got_p, got_rejected, expected_count, rational) in enumerate(zip(
                row['exceedance_counts'], row['adjusted_p'], row['rejected'],
                expected['exceedance_counts'], expected['adjusted_p'])):
            if type(got_count) is not int or not 0 <= got_count <= count:
                raise ValueError('Native exceedance count is not a bounded integer')
            if type(got_p) not in (int, float) or not 0 <= got_p <= 1 or not math.isfinite(got_p):
                raise ValueError('Native adjusted probability must be finite in [0,1]')
            if type(got_rejected) is not bool:
                raise ValueError('Native rejection decision must be boolean')
            prefix = f"{case['id']}[{i}]"
            if got_count != expected_count:
                failures.append(prefix + ': exceedance count mismatch')
            # Both sides convert the same exact small integer ratio to binary64;
            # one correctly rounded conversion allows exact equality here.
            if got_p != float(rational):
                failures.append(prefix + ': adjusted probability mismatch')
            if got_rejected != (rational < ALPHA):
                failures.append(prefix + ': strict-alpha rejection mismatch')
        checked.append(dict(id=case['id'], family_size=size, resample_count=count,
                            expected_exceedance_counts=expected['exceedance_counts'],
                            expected_adjusted_p=[str(value) for value in expected['adjusted_p']]))
    return dict(schemaVersion='MVS-MAXT-COMPARISON-1', fixtureSha256=digest,
                nativeEvidenceSha256=native_digest, coreAssemblySha256=assembly_digest,
                engineVersion=actual['engineVersion'], activeMetricCount=actual['activeMetricCount'],
                nativeRuntime=actual['nativeRuntime'], cases=len(rows),
                comparisons=sum(case['family_size'] for case in document['cases']),
                frozenFixtureDefinitionChecked=frozen_fixture,
                probabilityComparison='exact equality to binary64 conversion of independent integer ratio',
                passed=not failures, failures=failures, results=checked,
                qualification='Supplied finite-matrix arithmetic parity only; no MVS null validity, partial-null FWER, production activation or power claim')


def write_report(path, result, inputs):
    destination = Path(path)
    if destination.resolve() in {Path(source).resolve() for source in inputs}:
        raise ValueError('Output must be separate from every input')
    # Exclusive creation also refuses existing files and symlinks: historical
    # evidence is never replaced, including on a failing comparison.
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', default=str(DEFAULT_FIXTURES))
    parser.add_argument('--native', help='Actual native exporter JSON, never a reference-generated substitute')
    parser.add_argument('--core-assembly', help='Actual Core DLL used by the native exporter')
    parser.add_argument('--out', help='New comparison/check path; existing files are refused')
    args = parser.parse_args(argv)
    if bool(args.native) != bool(args.core_assembly):
        parser.error('--native and --core-assembly must be supplied together')
    try:
        if args.native:
            result = compare(args.fixtures, args.native, args.core_assembly)
            inputs = [args.fixtures, args.native, args.core_assembly]
        else:
            result = audit_frozen_fixtures(args.fixtures)
            inputs = [args.fixtures]
        if args.out:
            write_report(args.out, result, inputs)
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        print('Invalid maxT evidence: ' + str(exc))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
