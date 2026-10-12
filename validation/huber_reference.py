#!/usr/bin/env python3
"""Independent Decimal80 fixed-MAD Huber score solver for staged-metric diagnostics.

Native comparisons return 1 when accuracy cases fail, 0 only if all pass, 2 for
invalid input/provenance. This is numerical validation, not inferential validity.
No production IRLS code is used. Binary64 fixture inputs are interpreted exactly.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path

C = Decimal('1.345')
MAD_FACTOR = Decimal('1.482602218505602')
D = Decimal.from_float


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def reference(values):
    if len(values) < 2 or any(not math.isfinite(float(x)) for x in values):
        raise ValueError('At least two finite binary64 inputs are required')
    with localcontext() as context:
        context.prec = 80
        data = [D(float(x)) for x in values]
        center = median(data)
        scale = MAD_FACTOR * median([abs(x - center) for x in data])
        if scale == 0:
            return center, scale, Decimal(0)
        standardized = [(x - center) / scale for x in data]
        low, high = -C, C
        # Score is monotone. At median +/- c*scale its signs bracket a root.
        # If a zero interval exists, the initial midpoint selects the median.
        for _ in range(280):
            offset = (low + high) / 2
            score = sum(max(-C, min(C, x - offset)) for x in standardized)
            if score == 0 or offset == low or offset == high:
                break
            if score > 0:
                low = offset
            else:
                high = offset
        root = center + scale * offset
        return +root, +scale, +(score / len(data))


def load_fixtures(path):
    raw = Path(path).read_bytes()
    document = json.loads(raw)
    if (document.get('schema') != 'MVS-HUBER-REFERENCE-1' or
        document.get('metric') != 'huber_location' or
        document.get('tuning_constant') != str(C) or
        document.get('mad_normal_consistency') != str(MAD_FACTOR)):
        raise ValueError('Unknown Huber fixture definition')
    cases = document['cases']
    identifiers = [case['id'] for case in cases]
    if not cases or len(set(identifiers)) != len(identifiers):
        raise ValueError('Empty or duplicate Huber fixtures')
    for case in cases:
        reference(case['values'])
    return cases, hashlib.sha256(raw).hexdigest()


def compare(cases, fixture_hash, native):
    if native.get('schema') != 'MVS-HUBER-NATIVE-1' or native.get('fixtureSha256') != fixture_hash:
        raise ValueError('Native export schema or fixture hash mismatch')
    if native.get('metricStaged') is not True or native.get('activeMetricCount') != 12:
        raise ValueError('Unexpected metric activation or correction-family change')
    rows = native['results']
    actual = {row['id']: row for row in rows}
    if len(actual) != len(rows) or set(actual) != {case['id'] for case in cases}:
        raise ValueError('Native case identities differ from the fixture')
    results = []
    for case in cases:
        root, scale, residual = reference(case['values'])
        row = actual[case['id']]
        value = row.get('value')
        with localcontext() as context:
            context.prec = 80
            tolerance = max(Decimal('1e-10') * scale, Decimal(4) * D(math.ulp(float(root))))
            if row['status'] == 'unavailable' and value is None:
                error = normalized = None
                passed = False
            elif row['status'] == 'finite' and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                error = abs(D(float(value)) - root)
                normalized = error / scale if scale else None
                passed = error <= tolerance
            else:
                raise ValueError('Inconsistent native value/status')
            results.append(dict(id=case['id'], category=case['category'], passed=passed,
                native=value, reference=str(root), fixed_mad_scale=str(scale),
                absolute_error=str(error) if error is not None else None,
                error_in_scale_units=str(normalized) if normalized is not None else None,
                tolerance=str(tolerance), reference_mean_score_residual=str(residual)))
    failures = sum(not row['passed'] for row in results)
    return dict(schema='MVS-HUBER-COMPARISON-1', status='failed_accuracy' if failures else 'passed',
        cases=len(results), passed=len(results) - failures, failed=failures,
        fixtureSha256=fixture_hash, engineVersion=native.get('engineVersion'),
        nativeRuntime=native.get('nativeRuntime'), coreAssemblySha256=native.get('coreAssemblySha256'),
        method='Decimal80 normalized clipped-score bisection; exact binary64 inputs; declared zero-MAD median policy',
        tolerance='max(1e-10 * fixedMADscale, 4 * ulp(reference rounded to binary64))', results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=Path(__file__).with_name('huber-fixtures-v1.json'))
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    try:
        cases, fixture_hash = load_fixtures(args.fixtures)
        report = compare(cases, fixture_hash, json.loads(args.native.read_text()))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'invalid', 'error': str(error)}))
        return 2
    text = json.dumps(report, indent=2) + '\n'
    if args.out:
        args.out.write_text(text)
    print(text, end='')
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
