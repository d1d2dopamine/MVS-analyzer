#!/usr/bin/env python3
"""Exact algebra diagnostic, not a statistical test or production replacement.

No random draws, fitted models, external datasets, or MVS native calls.
Finite-support enumerations check the sample-variance identity independently.
"""
from fractions import Fraction as F
from itertools import product
import json


def sample_variance(values):
    if len(values) < 2:
        raise ValueError('at least two values required')
    values = tuple(map(F, values))
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / (len(values) - 1)


def sample_variance_uncertainty(n, variance, fourth):
    if type(n) is not int or n < 2:
        raise ValueError('integer n >= 2 required')
    variance, fourth = F(variance), F(fourth)
    if variance <= 0 or fourth < variance ** 2:
        raise ValueError('invalid second/fourth central moments')
    return (fourth - F(n - 3, n - 1) * variance ** 2) / n


def enumerate_sample_variance(n, probabilities):
    """Enumerate all IID outcomes on support -1,0,1, using rational weights."""
    if type(n) is not int or not 2 <= n <= 5:
        raise ValueError('enumeration is bounded to n=2..5')
    probabilities = tuple(map(F, probabilities))
    if len(probabilities) != 3 or any(p < 0 for p in probabilities) or sum(probabilities) != 1:
        raise ValueError('three probabilities must sum to one')
    support = (-1, 0, 1)
    mean = sum(F(x) * p for x, p in zip(support, probabilities))
    variance = sum((x - mean) ** 2 * p for x, p in zip(support, probabilities))
    fourth = sum((x - mean) ** 4 * p for x, p in zip(support, probabilities))
    first = second = mass = F(0)
    for indices in product(range(3), repeat=n):
        weight = F(1)
        for index in indices:
            weight *= probabilities[index]
        value = sample_variance([support[i] for i in indices])
        mass += weight
        first += weight * value
        second += weight * value ** 2
    return {'n': n, 'outcomes': 3 ** n, 'mass': mass, 'populationVariance': variance,
            'populationFourth': fourth, 'expectedSampleVariance': first,
            'enumeratedVariance': second - first ** 2,
            'formulaVariance': sample_variance_uncertainty(n, variance, fourth)}


def standardized_student_fourth(df):
    """Exact beta-integral moment identity for integer Student degrees of freedom."""
    if type(df) is not int or df <= 4:
        raise ValueError('finite fourth moment requires df > 4')
    return F(3 * (df - 2), df - 4)


def independent_sum_fourth(coefficients, variances, fourths):
    """Direct fourth-power expansion: singleton fourths plus 6 pair products."""
    a, v, q = [tuple(map(F, x)) for x in (coefficients, variances, fourths)]
    if not a or len(a) != len(v) or len(a) != len(q):
        raise ValueError('aligned nonempty arrays required')
    if any(x <= 0 or y < x ** 2 for x, y in zip(v, q)):
        raise ValueError('invalid moments')
    variance = sum(ai ** 2 * vi for ai, vi in zip(a, v))
    fourth = sum(ai ** 4 * qi for ai, qi in zip(a, q))
    fourth += 6 * sum(a[i] ** 2 * a[j] ** 2 * v[i] * v[j]
                      for i in range(len(a)) for j in range(i))
    return variance, fourth


def exact_diagnostic():
    checks = []
    for label, probabilities in [('fourth_ratio_3', (F(1, 6), F(2, 3), F(1, 6))),
                                 ('fourth_ratio_9', (F(1, 18), F(8, 9), F(1, 18)))]:
        for n in range(2, 6):
            row = enumerate_sample_variance(n, probabilities)
            assert row['mass'] == 1
            assert row['expectedSampleVariance'] == row['populationVariance']
            assert row['enumeratedVariance'] == row['formulaVariance']
            checks.append({'fixture': label, **row})
    m, entities = 40, 16
    fourth = standardized_student_fourth(5)
    within_g = sample_variance_uncertainty(m, 1, 3)
    within_t = sample_variance_uncertainty(m, 1, fourth)
    coefficients = [F(1)] + [F(1, m)] * m
    v_g, q_g = independent_sum_fourth(coefficients, [1] * (m + 1), [3] * (m + 1))
    v_t, q_t = independent_sum_fourth(coefficients, [1] * (m + 1), [fourth] * (m + 1))
    assert v_g == v_t == F(41, 40)
    assert q_g == 3 * v_g ** 2
    assert q_t == 3 * v_t ** 2 + 6 + F(6, m ** 3)
    center_g = sample_variance_uncertainty(entities, v_g, q_g)
    center_t = sample_variance_uncertainty(entities, v_t, q_t)
    assert within_t / within_g == F(157, 40)
    assert center_t / center_g == F(19297, 5248)
    return {'schema': 'mvs-component-moment-diagnostic/v1', 'status': 'pass',
            'randomDraws': 0, 'nativeCalls': 0, 'finiteSupportChecks': checks,
            'within': {'normalIndividual': within_g, 't5Individual': within_t,
                       'normalGroupAverage': within_g / entities, 't5GroupAverage': within_t / entities,
                       'uncertaintyVarianceRatio': within_t / within_g},
            'center': {'variance': v_t, 'normalFourth': q_g, 't5Fourth': q_t,
                       'normalSampleVarianceUncertainty': center_g, 't5SampleVarianceUncertainty': center_t,
                       'uncertaintyVarianceRatio': center_t / center_g},
            'limitations': ['Moment identities only, not production likelihood-ratio calibration.',
                            'Finite-support fixtures are not Gaussian or Student samples.',
                            'No attribution of the particular five Round50 rejections.',
                            'No validation or activation of a robust test.']}


def encode(value):
    if isinstance(value, F):
        return {'numerator': value.numerator, 'denominator': value.denominator, 'decimal': float(value)}
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [encode(v) for v in value]
    return value


if __name__ == '__main__':
    print(json.dumps(encode(exact_diagnostic()), indent=2, allow_nan=False))
