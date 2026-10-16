#!/usr/bin/env python3
"""Frozen independent normal-tail reference builder; never invokes native candidates.

Execution requires the reviewed protocol's exact SHA-256 and an explicit permit.
Inputs and references are written once to a new output directory before A/B runs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import struct
import sys
import warnings

import mpmath as mp
import numpy as np
import scipy
from scipy import stats

SCHEMA = 'mvs-normal-tail-input/v1'
EXPECTED_VERSIONS = {'scipy': '1.17.0', 'numpy': '2.3.5', 'mpmath': '1.3.0'}
FIXTURE_SHA = '41cdf8528ae2af97da7a25273c5a5bd156270b63734923a40ae774a49053b781'
ALPHAS = (0.001, 0.01, 0.05, 0.10, 0.20)
SIZES = (2, 4, 8, 16, 64, 256, 1024)
OFFSETS = (1e-12, 1e-10, 1e-8, 1e-6)
FAMILY_SIZE = 12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bits(x: float) -> str:
    return struct.pack('>d', float(x)).hex()


def from_bits(s: str) -> float:
    if len(s) != 16:
        raise ValueError('A binary64 input requires exactly 16 hexadecimal digits')
    return struct.unpack('>d', bytes.fromhex(s))[0]


def exact_float(x: float) -> mp.mpf:
    """Convert binary64 to an exact rational before arbitrary-precision division."""
    if not math.isfinite(x):
        raise ValueError('Finite binary64 required')
    n, d = x.as_integer_ratio()
    return mp.mpf(n) / mp.mpf(d)


def exact_fraction(x: Fraction) -> mp.mpf:
    return mp.mpf(x.numerator) / mp.mpf(x.denominator)


def fraction_record(x: Fraction) -> dict:
    return {'numerator': str(x.numerator), 'denominator': str(x.denominator)}


def round_integer_even(n: int, d: int) -> int:
    q, r = divmod(n, d)
    return q + (2*r > d or (2*r == d and q % 2 == 1))


def round_fraction_binary64(x: Fraction) -> float:
    """Round a nonnegative exact rational to binary64 nearest, ties to even."""
    if x < 0:
        return -round_fraction_binary64(-x)
    if not x:
        return 0.0
    n, d = x.numerator, x.denominator
    e = n.bit_length() - d.bit_length()
    if e >= 0:
        if n < d << e:
            e -= 1
    elif n << -e < d:
        e -= 1
    shift = 1074 if e < -1022 else 52 - e
    q = round_integer_even(n << shift, d) if shift >= 0 else round_integer_even(n, d << -shift)
    if e < -1022:
        # q=2**52 correctly crosses the subnormal/normal boundary.
        raw = q
    else:
        if q == 2**53:
            q >>= 1
            e += 1
        if e > 1023:
            return math.inf
        raw = ((e + 1023) << 52) | (q - 2**52)
    return from_bits(f'{raw:016x}')


def mp_fraction(x: mp.mpf) -> Fraction:
    if not mp.isfinite(x):
        raise ValueError('Finite mpmath input required')
    sign, man, exponent, _ = x._mpf_
    n = -man if sign else man
    return Fraction(n << exponent, 1) if exponent >= 0 else Fraction(n, 1 << -exponent)


def round_mp_binary64(x: mp.mpf) -> float:
    return round_fraction_binary64(mp_fraction(x))


def float_record(x: float) -> dict:
    kind = ('nan' if math.isnan(x) else 'positive_infinity' if x == math.inf else
            'negative_infinity' if x == -math.inf else 'finite')
    return {'bits': bits(x), 'kind': kind, 'value': x if math.isfinite(x) else None,
            'roundTrip': repr(x), 'hex': x.hex()}


def scientific(x: mp.mpf, dps: int) -> str:
    return mp.nstr(x, n=dps+10, strip_zeros=False)


def neighbors(x: float, count: int):
    yield x
    lo = hi = x
    for _ in range(count):
        lo, hi = math.nextafter(lo, -math.inf), math.nextafter(hi, math.inf)
        yield lo
        yield hi


def root_neighborhood(center: float):
    """All offsets are ordinary binary64 arithmetic from a binary64 root."""
    for x in neighbors(center, 16):
        yield x, 'ulp16'
    for offset in OFFSETS:
        for sign in (-1, 1):
            offset_center = center + sign*offset
            for x in neighbors(offset_center, 2):
                yield x, f'offset_{sign:+d}_{offset.hex()}_ulp2'


def root_for_target(target_kind: str, alpha: float | None, dps: int) -> dict:
    """Monotonic bisection of direct erfc; no inverse-normal dependency or RNG."""
    with mp.workdps(dps):
        target = (exact_float(alpha)/FAMILY_SIZE if target_kind == 'decision' else
                  mp.ldexp(mp.mpf(1), -1075 if target_kind == 'half_min_subnormal' else -1022))
        lo, hi = mp.mpf(0), mp.mpf(64)
        for _ in range(4*dps+16):
            mid = (lo+hi)/2
            if mp.erfc(mid/mp.sqrt(2)) > target:
                lo = mid
            else:
                hi = mid
        center = (lo+hi)/2
        return {'target': scientific(target, dps), 'lower': scientific(lo, dps),
                'upper': scientific(hi, dps), 'root': scientific(center, dps),
                'roundedBits': bits(round_mp_binary64(center))}


def build_roots() -> list[dict]:
    roots = []
    specifications = [('decision', a) for a in ALPHAS] + [('half_min_subnormal', None), ('normal_transition', None)]
    for kind, alpha in specifications:
        r100, r200 = root_for_target(kind, alpha, 100), root_for_target(kind, alpha, 200)
        if r100['roundedBits'] != r200['roundedBits']:
            raise RuntimeError(f'Unestablished root rounding: {kind}, {alpha}')
        with mp.workdps(240):
            root_difference = abs(mp.mpf(r100['root'])-mp.mpf(r200['root']))
            if root_difference >= mp.mpf('1e-80'):
                raise RuntimeError(f'Unestablished root precision agreement: {kind}, {alpha}')
            difference_text = scientific(root_difference,220)
        roots.append({'id': f'alpha_{bits(alpha)}' if alpha is not None else kind,
                      'kind': kind, 'alphaBits': bits(alpha) if alpha is not None else None,
                      'precision100': r100, 'precision200': r200, 'rootAgreementAbsolute': difference_text,
                      'roundedBits': r200['roundedBits']})
    return roots


def build_grid(roots: list[dict]) -> list[dict]:
    records = {}
    def add(x, tag, alpha_bits=None):
        b = bits(x)
        rec = records.setdefault(b, {'id': f'z_{b}', 'zBits': b, 'zHex': x.hex(),
                                     'z': x, 'tags': set(), 'thresholds': set()})
        rec['tags'].add(tag)
        if alpha_bits is not None:
            rec['thresholds'].add(alpha_bits)
    for k in range(641):
        add(k/16, 'base_k_over_16')
    for power in (-52, -40, -30, -20, -10):
        add(math.ldexp(1.0, power), f'small_power_{power}')
    for k in range(2049):
        add(37+k/1024, 'tail_37_plus_k_over_1024')
    for root in roots:
        for x, detail in root_neighborhood(from_bits(root['roundedBits'])):
            add(x, f"root_{root['id']}_{detail}", root['alphaBits'])
    result = sorted(records.values(), key=lambda p: p['z'])
    for rec in result:
        rec['tags'], rec['thresholds'] = sorted(rec['tags']), sorted(rec['thresholds'])
    return result


def special_inputs() -> list[dict]:
    rows = [('+zero', '0000000000000000', 'one'),
            ('-zero', '8000000000000000', 'one'),
            ('+infinity', '7ff0000000000000', 'zero'),
            ('-infinity', 'fff0000000000000', 'reject'),
            ('quiet_nan', '7ff8000000000000', 'reject'),
            ('negative_epsilon', bits(-2**-52), 'reject'),
            ('negative_one', bits(-1), 'reject'),
            ('maximum_finite', '7fefffffffffffff', 'zero')]
    return [{'id': f'special_{name}', 'zBits': b, 'expected': expected,
             'expectedTarget': 'adapter' if expected == 'reject' else 'candidateB'} for name,b,expected in rows]


def rank_inputs(fixtures: dict) -> list[dict]:
    output = []
    for case in fixtures['cases']:
        output.append({'id': case['id'], 'method': case['method'], 'origin': 'frozen-fixture',
                       'groupsBits': [[bits(x) for x in g] for g in case['groups']],
                       'fixtureReference': case['reference'], 'fixtureExpectedP': case['expectedP']})
    for n in SIZES:
        families = {'separated': (list(range(n)), list(range(n, 2*n))),
                    'ties_shifted': ([i//4 for i in range(n)], [i//4+1 for i in range(n)]),
                    'identical_range': (list(range(n)), list(range(n))),
                    'identical_constant': ([1]*n, [1]*n)}
        for family,(a,b) in families.items():
            variants = {'original': (a,b), 'swapped': (b,a),
                        'reversed': (list(reversed(a)), list(reversed(b))),
                        'affine_8x_plus_64': ([8*x+64 for x in a], [8*x+64 for x in b])}
            for variant,groups in variants.items():
                output.append({'id': f'mw_n{n}_{family}_{variant}', 'method': 'mann_whitney',
                               'origin': 'deterministic-variant', 'family': family, 'variant': variant,
                               'n': n, 'groupsBits': [[bits(x) for x in g] for g in groups]})
    return output


def exact_rank_summary(a: list[float], b: list[float]) -> dict:
    """Independent rational ranks, not the production implementation or operation order."""
    if not a or not b:
        return {'status': 'empty_policy', 'z': None, 'variance': None}
    counts_a, counts_b = Counter(a), Counter(b)
    values = sorted(counts_a.keys() | counts_b.keys())
    rank_b, ties, previous = Fraction(0), 0, 0
    for value in values:
        count = counts_a[value]+counts_b[value]
        average_rank = Fraction(2*previous+count+1, 2)
        rank_b += counts_b[value]*average_rank
        ties += count**3-count
        previous += count
    n_a, n_b, n = len(a), len(b), len(a)+len(b)
    u_b = rank_b - Fraction(n_b*(n_b+1), 2)
    mean = Fraction(n_a*n_b, 2)
    variance = Fraction(n_a*n_b, 12)*(n+1-Fraction(ties, n*(n-1)))
    numerator = max(Fraction(0), abs(u_b-mean)-Fraction(1,2))
    result = {'status': 'constant_policy' if variance <= 0 else 'finite',
              'rankSumB': fraction_record(rank_b), 'uB': fraction_record(u_b),
              'uA': fraction_record(n_a*n_b-u_b), 'mean': fraction_record(mean),
              'tieSum': str(ties), 'variance': fraction_record(variance),
              'continuityAdjustedDistance': fraction_record(numerator)}
    if variance <= 0:
        result['z'] = {'roundedBits': bits(0.0), 'precision100': '0.0', 'precision200': '0.0'}
    else:
        z_values = {}
        for dps in (100,200):
            with mp.workdps(dps):
                z = exact_fraction(numerator)/mp.sqrt(exact_fraction(variance))
                z_values[str(dps)] = (scientific(z,dps), bits(round_mp_binary64(z)))
        if z_values['100'][1] != z_values['200'][1]:
            raise RuntimeError('Independent exact-rank z rounding not established')
        result['z'] = {'roundedBits': z_values['200'][1], 'precision100': z_values['100'][0],
                       'precision200': z_values['200'][0]}
    return result


def h_value(z: float, dps: int, rank: dict | None = None) -> dict:
    with mp.workdps(dps):
        if rank is None:
            z_mp = exact_float(z)
        else:
            num = rank['continuityAdjustedDistance']
            var = rank['variance']
            numerator = Fraction(int(num['numerator']),int(num['denominator']))
            variance = Fraction(int(var['numerator']),int(var['denominator']))
            z_mp = exact_fraction(numerator)/mp.sqrt(exact_fraction(variance)) if variance > 0 else mp.mpf(0)
        p = mp.erfc(z_mp/mp.sqrt(2))
        return {'p': scientific(p,dps), 'logP': scientific(mp.log(p),dps),
                'roundedBits': bits(round_mp_binary64(p))}


def h_reference(z: float, rank: dict | None = None) -> dict:
    h100, h200 = h_value(z,100,rank), h_value(z,200,rank)
    with mp.workdps(240):
        log_diff = abs(mp.mpf(h100['logP'])-mp.mpf(h200['logP']))
        established = h100['roundedBits']==h200['roundedBits'] and log_diff < mp.mpf('1e-80')
        p = mp.mpf(h200['p'])
        if p >= mp.mpf('1e-8'):
            regime = 'absolute'
        elif p >= mp.ldexp(mp.mpf(1),-1022):
            regime = 'normal_relative_and_log'
        elif h200['roundedBits'] != bits(0.0):
            regime = 'subnormal_8_quanta'
        else:
            regime = 'rounds_to_zero'
        return {'precision100': h100, 'precision200': h200,
                'roundedBits': h200['roundedBits'], 'logAgreementAbsolute': scientific(log_diff,220),
                'established': established, 'regime': regime}


def s_reference(z: float) -> dict:
    with np.errstate(over='ignore', invalid='ignore', under='ignore'):
        p = float(2*stats.norm.sf(z))
        log_p = float(math.log(2)+stats.norm.logsf(z))
    return {'p': float_record(p), 'logP': float_record(log_p)}


def compare_reference_value(value: float, h: dict) -> dict:
    """Exact-binary64-vs-highprecision diagnostic, using fixed protocol criteria."""
    if not h['established']:
        return {'status': 'reference_unestablished'}
    with mp.workdps(240):
        p_h = mp.mpf(h['precision200']['p'])
        log_h = mp.mpf(h['precision200']['logP'])
        value_mp = exact_float(value) if math.isfinite(value) else mp.nan
        absolute = abs(value_mp-p_h)
        relative = absolute/p_h
        log_error = abs(mp.log(value_mp)-log_h) if value > 0 else mp.inf
        r = from_bits(h['roundedBits'])
        distance = abs(value_mp-exact_float(r))
        finite_range = math.isfinite(value) and 0 <= value <= 1
        regime = h['regime']
        if regime == 'absolute':
            criterion = absolute <= mp.mpf('2e-15')
        elif regime == 'normal_relative_and_log':
            criterion = value > 0 and relative <= mp.mpf('2e-12') and log_error <= mp.mpf('2e-12')
        elif regime == 'subnormal_8_quanta':
            criterion = value > 0 and distance <= 8*mp.ldexp(mp.mpf(1),-1074)
        else:
            criterion = value == 0
        return {'status': 'pass' if finite_range and criterion else 'fail', 'regime': regime,
                'absoluteError': scientific(absolute,220), 'relativeError': scientific(relative,220),
                'logErrorOfRoundedP': scientific(log_error,220),
                'distanceFromRoundedReferenceQuanta': scientific(distance/mp.ldexp(mp.mpf(1),-1074),220)}


def mathematical_decisions(h: dict) -> list[dict]:
    decisions = []
    with mp.workdps(240):
        p_h = mp.mpf(h['precision200']['p'])
        for alpha in ALPHAS:
            exact_alpha = exact_float(alpha)
            delta = p_h*FAMILY_SIZE-exact_alpha
            decisions.append({'alphaBits': bits(alpha), 'familySize': FAMILY_SIZE,
                              'reject': bool(delta < 0), 'signedAdjustedMinusAlpha': scientific(delta,220)})
    return decisions


def rank_reference(row: dict) -> dict:
    groups = [[from_bits(x) for x in g] for g in row['groupsBits']]
    out = {'id': row['id'], 'method': row['method']}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        if row['method'] == 'mann_whitney':
            s = stats.mannwhitneyu(*groups, alternative='two-sided', method='asymptotic', use_continuity=True)
            out['scipy'] = {'p': float_record(float(s.pvalue)), 'statistic': float_record(float(s.statistic))}
            rank = exact_rank_summary(*groups)
            out['exactRank'] = rank
            if rank['status'] != 'empty_policy':
                z = from_bits(rank['z']['roundedBits'])
                h_rank = h_reference(z,rank)
                h_rounded_z = h_reference(z)
                out.update({'hExactRankZ': h_rank, 'hRoundedRankZ': h_rounded_z,
                            'mathematicalDecisionsExactRankZ': mathematical_decisions(h_rank),
                            'scipyVsExactRankH': compare_reference_value(float(s.pvalue),h_rank)})
        else:
            try:
                s = stats.kruskal(*groups, nan_policy='propagate')
                out['scipy'] = {'p': float_record(float(s.pvalue)), 'statistic': float_record(float(s.statistic))}
            except ValueError as exc:
                out['scipy'] = {'errorType': type(exc).__name__, 'error': str(exc)}
        out['warnings'] = [str(w.message) for w in caught]
    return out


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def build(args):
    protocol, amendment, fixture = Path(args.protocol), Path(args.amendment), Path(args.fixtures)
    if not args.permit_execution:
        raise SystemExit('Execution is disabled until amended protocol review explicitly permits generation')
    if sha256(protocol) != args.approved_protocol_sha:
        raise SystemExit('Reviewed protocol SHA mismatch')
    if sha256(amendment) != args.approved_amendment_sha:
        raise SystemExit('Reviewed amendment SHA mismatch')
    if sha256(fixture) != FIXTURE_SHA:
        raise SystemExit('Existing frozen rank fixture SHA mismatch')
    versions = {'scipy':scipy.__version__, 'numpy':np.__version__, 'mpmath':mp.__version__}
    if versions != EXPECTED_VERSIONS:
        raise SystemExit(f'Frozen dependency mismatch: {versions}')
    out = Path(args.output)
    if out.exists():
        raise SystemExit('Output directory must not exist: evidence is write-once')
    roots = build_roots()
    points = build_grid(roots)
    fixtures = json.loads(fixture.read_text())
    cases = rank_inputs(fixtures)
    assert len([c for c in cases if c['origin']=='deterministic-variant']) == 112
    references, policy_inputs = [], []
    for point in points:
        z = from_bits(point['zBits'])
        h, s = h_reference(z), s_reference(z)
        point['referenceRoundedPBits'] = h['roundedBits']
        references.append({'id':point['id'], 'zBits':point['zBits'], 'h':h, 'scipy':s,
                           'scipyVsH':compare_reference_value(from_bits(s['p']['bits']),h),
                           'mathematicalDecisions':mathematical_decisions(h)})
        for alpha in ALPHAS:
            policy_inputs.append({'id':f"{point['id']}_alpha_{bits(alpha)}",'pointId':point['id'],
                                  'rawPBits':h['roundedBits'],'alphaBits':bits(alpha),'familySize':FAMILY_SIZE})
    ranks = [rank_reference(c) for c in cases]
    for rank in ranks:
        if 'hExactRankZ' in rank:
            for which in ('hExactRankZ', 'hRoundedRankZ'):
                for alpha in ALPHAS:
                    policy_inputs.append({'id':f"{rank['id']}_{which}_alpha_{bits(alpha)}",'rankId':rank['id'],
                                          'referenceKind':which, 'rawPBits':rank[which]['roundedBits'],
                                          'alphaBits':bits(alpha),'familySize':FAMILY_SIZE})
    inputs = {'schema':SCHEMA, 'points':points, 'specials':special_inputs(), 'rankCases':cases,
              'alphaBits':[bits(a) for a in ALPHAS], 'familySize':FAMILY_SIZE}
    ref = {'schema':'mvs-normal-tail-reference/v1', 'roots':roots, 'points':references, 'rankCases':ranks,
           'maximumFiniteProof':{
               'method':'For z>0, erfc(z/sqrt(2)) <= sqrt(2/pi)*exp(-z^2/2)/z < exp(-z^2/2) for z>=1.',
               'bound':'maximum_finite >= 64; z^2/2 >= 2048 > 1075 > 1075*ln(2), since ln(2)<1.',
               'conclusion':'0 < p < 2^-1075, so binary64 nearest-even is +0.',
               'roundedBits':'0000000000000000', 'logPrecisionAgreement':'not_applicable_by_protocol_amendment'},
           'nativeCandidateOutputsRead':False, 'rngUsed':False}
    out.mkdir(parents=True)
    write_json(out/'grid-inputs.json',inputs)
    write_json(out/'references.json',ref)
    write_json(out/'reference-policy-inputs.json',{'schema':'mvs-normal-tail-policy-input/v1','cases':policy_inputs})
    write_json(out/'roots.json',roots)
    package_versions = sorted((d.metadata.get('Name',''),d.version) for d in importlib.metadata.distributions())
    manifest = {'schema':'mvs-normal-tail-reference-manifest/v1', 'protocol':{'path':str(protocol),'sha256':sha256(protocol)},
                'amendment':{'path':str(amendment),'sha256':sha256(amendment)},
                'fixtures':{'path':str(fixture),'sha256':sha256(fixture)},
                'generator':{'path':str(Path(__file__).resolve()),'sha256':sha256(Path(__file__))},
                'environment':{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
                               'machine':platform.machine(),'versions':versions,'installedDistributions':package_versions},
                'inputRules':{'rngUsed':False,'deduplicate':'binary64 bits only within scalar working grid',
                              'sort':'ascending nonnegative binary64 scalar z',
                              'decimalOffsets':'binary64 z0 +/- nearest binary64 1e-12,1e-10,1e-8,1e-6',
                              'rootSolver':'100/200 decimal-place direct-erfc bisection on [0,64], 4*dps+16 iterations',
                              'rounding':'integer-rational binary64 nearest, ties-to-even',
                              'nativeOutputsRead':False},
                'counts':{'scalar':len(points),'specials':len(inputs['specials']),'rankCases':len(cases),
                          'existingScipyFixtures':sum(c.get('fixtureReference')=='scipy' for c in cases),
                          'existingPolicyFixtures':sum(c.get('fixtureReference')=='mvs-declared-policy' for c in cases),
                          'newDeterministicVariants':112,'policyInputs':len(policy_inputs)},
                'files':{p.name:sha256(p) for p in sorted(out.iterdir()) if p.is_file()},
                'hEstablished':all(p['h']['established'] for p in references) and all(
                    r['hExactRankZ']['established'] and r['hRoundedRankZ']['established'] for r in ranks if 'hExactRankZ' in r)}
    if args.source_manifest:
        sm=Path(args.source_manifest)
        manifest['sourceManifest']={'path':str(sm),'sha256':sha256(sm)}
    write_json(out/'reference-manifest.json',manifest)
    print(json.dumps({'manifest':str(out/'reference-manifest.json'), 'manifestSHA256':sha256(out/'reference-manifest.json'),
                      'counts':manifest['counts'], 'hEstablished':manifest['hEstablished']},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',required=True)
    parser.add_argument('--approved-protocol-sha',required=True)
    parser.add_argument('--amendment',required=True)
    parser.add_argument('--approved-amendment-sha',required=True)
    parser.add_argument('--fixtures',required=True)
    parser.add_argument('--source-manifest')
    parser.add_argument('--output',required=True)
    parser.add_argument('--permit-execution',action='store_true')
    build(parser.parse_args())


if __name__=='__main__':
    main()
