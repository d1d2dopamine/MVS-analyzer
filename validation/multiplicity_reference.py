#!/usr/bin/env python3
"""Independent exhaustive closed-Bonferroni reference for internal Holm arithmetic.

Enumerates every nonempty intersection of at most twelve hypotheses, rather than
using production sort/rank/cumulative-max logic. Null slots count in every family
and act as p=1 inside intersections, but remain unavailable in output. This checks
arithmetic only; valid marginal p-values remain a separate scientific requirement.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


def reference(values, family_size):
    if isinstance(family_size, bool) or not isinstance(family_size, int) or not 1 <= family_size <= 12 or len(values) != family_size:
        raise ValueError('A complete family of one to twelve hypotheses is required')
    for p in values:
        if p is not None and (isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1):
            raise ValueError('P-values must be finite in [0,1] or null')
    effective = [1.0 if p is None else float(p) for p in values]
    closed = [0.0] * family_size
    for mask in range(1, 1 << family_size):
        members = [i for i in range(family_size) if mask & (1 << i)]
        local = min(1.0, len(members) * min(effective[i] for i in members))
        for i in members:
            closed[i] = max(closed[i], local)
    return {
        'bonferroni': [None if p is None else min(1.0, family_size * p) for p in values],
        'holm': [None if p is None else closed[i] for i, p in enumerate(values)],
    }


def load_fixtures(path):
    raw = Path(path).read_bytes()
    doc = json.loads(raw)
    if doc.get('schema') != 'MVS-MULTIPLICITY-REFERENCE-1' or doc.get('alpha') != .05:
        raise ValueError('Unknown fixture schema or alpha')
    cases = doc['cases']
    ids = [c['id'] for c in cases]
    if not cases or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Empty or duplicate fixture identifiers')
    for case in cases:
        reference(case['p_values'], case['family_size'])
    return doc, hashlib.sha256(raw).hexdigest()


def compare(fixtures, native):
    doc, digest = load_fixtures(fixtures)
    actual = json.loads(Path(native).read_text())
    if actual.get('schema') != 'MVS-MULTIPLICITY-NATIVE-1' or actual.get('fixtureSha256') != digest:
        raise ValueError('Native fixture provenance mismatch')
    if actual.get('engineVersion') != '1.6.2' or actual.get('activeMetricCount') != 12:
        raise ValueError('Unexpected engine identity')
    if not isinstance(actual.get('coreAssemblySha256'), str) or len(actual['coreAssemblySha256']) != 64 or not actual.get('nativeRuntime'):
        raise ValueError('Missing native binary provenance')
    rows = actual['results']
    if [x['id'] for x in rows] != [x['id'] for x in doc['cases']]:
        raise ValueError('Native cases missing, duplicate or reordered')
    failures = []
    for case, row in zip(doc['cases'], rows):
        expected = reference(case['p_values'], case['family_size'])
        for method, values in expected.items():
            got = row[method]
            if len(got) != len(values):
                raise ValueError('Native vector length mismatch')
            for i, (a, e) in enumerate(zip(got, values)):
                # Identical integer*binary64 operations permit exact agreement.
                if a != e or (a is not None and (isinstance(a, bool) or not math.isfinite(a))):
                    failures.append(f"{case['id']} {method}[{i}]: {a!r} != {e!r}")
            reject = [p is not None and p < doc['alpha'] for p in values]
            observed = row[method + '_rejected']
            if observed != reject or any(type(x) is not bool for x in observed):
                failures.append(f"{case['id']} {method}: rejection mismatch")
    return dict(schema='MVS-MULTIPLICITY-COMPARISON-1', fixtureSha256=digest,
                cases=len(rows), comparisons=sum(2*c['family_size'] for c in doc['cases']),
                passed=not failures, failures=failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', default=str(Path(__file__).with_name('multiplicity-fixtures-v1.json')))
    parser.add_argument('--native', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        result = compare(args.fixtures, args.native)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Invalid multiplicity evidence: {exc}')
        return 2
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        Path(args.output).write_text(text)
    print(text, end='')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
