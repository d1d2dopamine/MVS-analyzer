#!/usr/bin/env python3
"""Independent original-input Decimal1600 staged-Huber repair accuracy gate.

Exit 0: every accuracy/status case passes. Exit 1: valid export fails accuracy
(including any unavailable result). Exit 2: malformed data/provenance. This checks
numerical implementation only, not inferential validity or metric activation.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

C = Decimal('1.345')
MAD_FACTOR = Decimal('1.482602218505602')
D = Decimal.from_float
PRECISION = 1600
REFERENCE_RELATIVE_WIDTH = Decimal('1e-1100')
REFERENCE_MAX_ITERATIONS = 4096
NATIVE_MAX_ITERATIONS = 64
IMPLEMENTATION_ID = 'fixed-mad-huber-normalized-score-v2'
FAILURE_STATUSES = frozenset({
    'invalid_input', 'invalid_normalized_scale', 'invalid_bracket',
    'nonfinite_score', 'nonfinite_coordinate', 'nonfinite_reconstruction', 'iteration_limit',
})
DISPLAY_DIGITS = 40


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def _binary64_values(values):
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise ValueError('At least two finite binary64 inputs are required')
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('Fixture values must be finite binary64 numbers, not booleans or strings')
        try:
            number = float(value)
        except (OverflowError, ValueError):
            raise ValueError('Fixture number is outside finite binary64 range') from None
        if not math.isfinite(number):
            raise ValueError('Fixture values must be finite binary64 numbers')
        result.append(number)
    return tuple(result)


@lru_cache(maxsize=2048)
def _reference_binary64(values):
    with localcontext() as context:
        context.prec = PRECISION
        # These are the original binary64 observations. No production-coordinate
        # transformation, rounded normalized sample, or production algorithm is used.
        data = tuple(D(value) for value in values)
        center = median(data)
        mad = median([abs(value - center) for value in data])
        scale = MAD_FACTOR * mad
        if mad == 0:
            return center, scale, Decimal(0)

        radius = C * scale
        negative_radius = -radius

        def score(location):
            # This original-unit score is exactly s times the specified score:
            # sum clip(x_i - mu, -c*s, c*s). Its roots are therefore identical.
            return sum((min(radius, max(negative_radius, value - location))
                        for value in data), Decimal(0))

        low, high = center - radius, center + radius
        if score(low) < 0 or score(high) > 0:
            raise ArithmeticError('Independent reference could not bracket a root')
        target_width = scale * REFERENCE_RELATIVE_WIDTH
        for _ in range(REFERENCE_MAX_ITERATIONS):
            root = (low + high) / 2
            residual = score(root)
            if residual == 0 or high - low <= target_width:
                return +root, +scale, +(residual / (scale * len(data)))
            if root == low or root == high:
                raise ArithmeticError('Independent reference exhausted Decimal precision')
            if residual > 0:
                low = root
            else:
                high = root
        raise ArithmeticError('Independent reference iteration budget exhausted')


def reference(values):
    """Return (root, original fixed-MAD scale, mean dimensionless score residual).

    Arithmetic uses 1600 significant decimal digits. Exact binary64 conversion,
    median and MAD precede original-coordinate monotone bisection. Its final
    interval is <= 1e-1100 original fixed-MAD scale units, unless score is zero.
    Caller input is never mutated. Decimal results retain the computation precision.
    """
    return _reference_binary64(_binary64_values(values))


def _reject_constant(value):
    raise ValueError(f'Non-finite JSON number {value} is not permitted')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON object key: {key}')
        result[key] = value
    return result


def read_json_bytes(raw):
    return json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object)


def _sha256(value, description):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', value):
        raise ValueError(f'{description} must be a 64-digit SHA-256 hexadecimal string')
    return value.lower()


def load_fixtures(path):
    raw = Path(path).read_bytes()
    document = read_json_bytes(raw)
    if (not isinstance(document, dict) or
        document.get('schema') != 'MVS-HUBER-REFERENCE-1' or
        document.get('metric') != 'huber_location' or
        document.get('tuning_constant') != str(C) or
        document.get('mad_normal_consistency') != str(MAD_FACTOR)):
        raise ValueError('Unknown Huber fixture definition')
    cases = document.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Empty or invalid Huber fixtures')
    identifiers = set()
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get('id'), str) or
            not case['id'] or not isinstance(case.get('category'), str) or not case['category']):
            raise ValueError('Fixture id and category must be nonempty strings')
        if case['id'] in identifiers:
            raise ValueError('Duplicate Huber fixture id')
        identifiers.add(case['id'])
        _binary64_values(case.get('values'))
    return cases, hashlib.sha256(raw).hexdigest()


def _display(value):
    """Bound report size, without rounding the comparison itself."""
    if value is None:
        return None
    if value == 0:
        return '0'
    with localcontext() as context:
        context.prec = DISPLAY_DIGITS
        return str((+value).normalize())


def compare(cases, fixture_hash, native, expected_core_sha256=None):
    """Compare a native document; optionally bind it to an independently hashed DLL.

    `cases, fixture_hash` should come from load_fixtures. The optional expected
    SHA is normally hashlib.sha256(Path(Core.dll).read_bytes()).hexdigest().
    Synthetic test documents are accepted only as test data, never native evidence;
    their testDataOnly marker is retained in the report.
    """
    fixture_hash = _sha256(fixture_hash, 'Expected fixture hash')
    if not isinstance(native, dict) or native.get('schema') != 'MVS-HUBER-NATIVE-1':
        raise ValueError('Native export schema mismatch')
    if _sha256(native.get('fixtureSha256'), 'Native fixture hash') != fixture_hash:
        raise ValueError('Native fixture hash mismatch')
    assembly_hash = _sha256(native.get('coreAssemblySha256'), 'Native Core assembly hash')
    if expected_core_sha256 is not None:
        if assembly_hash != _sha256(expected_core_sha256, 'Expected Core assembly hash'):
            raise ValueError('Native Core assembly hash mismatch')
    if native.get('implementationId') != IMPLEMENTATION_ID:
        raise ValueError('Native staged implementation identity mismatch')
    if native.get('engineVersion') != '1.6.2':
        raise ValueError('Native engine version mismatch')
    if (native.get('metricStaged') is not True or
        type(native.get('activeMetricCount')) is not int or native['activeMetricCount'] != 12):
        raise ValueError('Unexpected metric activation or correction-family change')
    if not isinstance(native.get('nativeRuntime'), str) or not native['nativeRuntime'].strip():
        raise ValueError('Native runtime provenance is missing')
    if 'testDataOnly' in native and type(native['testDataOnly']) is not bool:
        raise ValueError('testDataOnly must be a boolean when provided')

    rows = native.get('results')
    if not isinstance(rows, list):
        raise ValueError('Native results must be a list')
    actual = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or row['id'] in actual:
            raise ValueError('Native case identities are invalid or duplicated')
        if not {'id', 'value', 'status', 'solverStatus', 'iterations'}.issubset(row):
            raise ValueError('Native result is missing a required field')
        actual[row['id']] = row
    identifiers = [case['id'] for case in cases]
    if len(set(identifiers)) != len(identifiers) or set(actual) != set(identifiers):
        raise ValueError('Native case identities differ from the fixture')

    results = []
    for case in cases:
        root, scale, residual = reference(case['values'])
        row = actual[case['id']]
        status, solver_status = row.get('status'), row.get('solverStatus')
        iterations, value = row.get('iterations'), row.get('value')
        if type(iterations) is not int or not 0 <= iterations <= NATIVE_MAX_ITERATIONS:
            raise ValueError('Native iterations must be an integer between 0 and 64')
        if solver_status == 'zero_mad_fallback':
            valid_iterations = iterations == 0
        elif solver_status in ('converged', 'iteration_limit'):
            valid_iterations = iterations >= 1
        else:
            valid_iterations = True
        if not valid_iterations:
            raise ValueError('Native iteration count is inconsistent with solverStatus')
        expected_status = 'zero_mad_fallback' if scale == 0 else 'converged'
        with localcontext() as context:
            context.prec = PRECISION
            tolerance = max(Decimal('1e-10') * scale, Decimal(4) * D(math.ulp(float(root))))
            if status == 'unavailable' and value is None and solver_status in FAILURE_STATUSES:
                error = normalized = None
                passed = False
                reasons = ['unavailable_native_result']
            elif (status == 'finite' and solver_status in ('converged', 'zero_mad_fallback') and
                  isinstance(value, (int, float)) and not isinstance(value, bool)):
                try:
                    value = float(value)
                except (OverflowError, ValueError):
                    raise ValueError('Native value must be finite binary64') from None
                if not math.isfinite(value):
                    raise ValueError('Native value must be finite binary64')
                error = abs(D(value) - root)
                normalized = error / scale if scale else None
                reasons = []
                if error > tolerance:
                    reasons.append('value_outside_tolerance')
                if solver_status != expected_status:
                    reasons.append('wrong_solver_status_for_original_mad')
                passed = not reasons
            else:
                raise ValueError('Inconsistent native value/status/solverStatus')
            results.append(dict(id=case['id'], category=case['category'], passed=passed,
                failureReasons=reasons, native=value, status=status, solverStatus=solver_status,
                expectedSolverStatus=expected_status, iterations=iterations,
                reference=_display(root), fixed_mad_scale=_display(scale),
                absolute_error=_display(error), error_in_scale_units=_display(normalized),
                tolerance=_display(tolerance), reference_mean_score_residual=_display(residual)))
    failures = sum(not row['passed'] for row in results)
    report = dict(schema='MVS-HUBER-COMPARISON-1', status='failed_accuracy' if failures else 'passed',
        cases=len(results), passed=len(results) - failures, failed=failures,
        fixtureSha256=fixture_hash, implementationId=native['implementationId'],
        engineVersion=native['engineVersion'], nativeRuntime=native['nativeRuntime'],
        coreAssemblySha256=assembly_hash, metricStaged=True, activeMetricCount=12,
        coreAssemblyVerification=('matched_supplied_binary_sha256' if expected_core_sha256 is not None
                                  else 'declared_sha256_not_independently_checked'),
        method='Decimal1600 original-input original-coordinate clipped-score bisection; exact binary64 median/MAD; declared exact-zero-MAD median policy',
        referenceRelativeBracketWidth=str(REFERENCE_RELATIVE_WIDTH),
        displaySignificantDigits=DISPLAY_DIGITS,
        displayNote='Decimal strings are rounded for display only; comparisons use full Decimal1600 precision.',
        tolerance='max(1e-10 * fixedMADscale, 4 * ulp(reference rounded to binary64))', results=results)
    if native.get('testDataOnly'):
        report['testDataOnly'] = True
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=Path(__file__).with_name('huber-repair-fixtures-v1.json'))
    parser.add_argument('--native', type=Path, required=True)
    provenance = parser.add_mutually_exclusive_group()
    provenance.add_argument('--core-assembly', type=Path,
                            help='Hash this actual Core assembly and require the export to match it')
    provenance.add_argument('--expected-core-sha256', help='Require this independently obtained Core assembly SHA-256')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        cases, fixture_hash = load_fixtures(args.fixtures)
        expected_hash = (hashlib.sha256(args.core_assembly.read_bytes()).hexdigest()
                         if args.core_assembly else args.expected_core_sha256)
        report = compare(cases, fixture_hash, read_json_bytes(args.native.read_bytes()), expected_hash)
        text = json.dumps(report, indent=2, allow_nan=False) + '\n'
        if args.out:
            args.out.write_text(text, encoding='utf-8')
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
        print(json.dumps({'status': 'invalid', 'error': str(error)}))
        return 2
    print(text, end='')
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
