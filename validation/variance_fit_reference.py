#!/usr/bin/env python3
"""Fixed, validation-only dense Gaussian variance-component reference.

The independent likelihood constructs the observation-level covariance V and
fixed-effect matrix X from literal observations. It neither imports nor ports
the production sufficient-statistic likelihood or optimizer. This is a bounded
numerical diagnostic, not evidence about bootstrap coverage or model adequacy.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import platform
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

# Set these before importing numerical libraries, including in clean CI runs.
for _key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '1'
import numpy as np
import scipy
import mpmath as mp
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize

PROTOCOL_ID = 'round48-variance-fit-v1'
LOG_BOUNDS = (-23.0, 8.0)
FIT_COUNT = 20
REFERENCE_COUNT = 9
OPTIMIZER_COUNT = 64
MAX_EVALUATIONS = 96000
REFERENCE_SECONDS = 180
NATIVE_SECONDS = 120
MAX_FUNCTION_CALLS = 1500
MAX_ITERATIONS = 1000
STARTS = ((.1, .1), (1.0, .01))
SOURCE_FILES = (
    'Core/VarianceAnalysis.cs', 'Core/NumericalMethods.cs',
    'MvsAnalyzer.Core/MvsAnalyzer.Core.csproj', 'SharedSources.props',
    'validation/variance_fit_reference/Program.cs',
    'validation/variance_fit_reference/VarianceFitReference.csproj',
)


class InvalidEvidence(ValueError):
    """A malformed fixture, export, or provenance identity cannot be scored."""


class OracleInvalid(RuntimeError):
    """Reference self-validity failed; native accuracy must not be judged."""


class BudgetExhausted(OracleInvalid):
    pass


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _object_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InvalidEvidence('Duplicate JSON property: ' + key)
        out[key] = value
    return out


def read_json(raw):
    def reject_constant(value):
        raise InvalidEvidence('Nonstandard JSON number: ' + value)
    return json.loads(raw, object_pairs_hook=_object_pairs, parse_constant=reject_constant)


def require(condition, message):
    if not condition:
        raise InvalidEvidence(message)


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def load_fixtures(path):
    raw = Path(path).read_bytes()
    document = read_json(raw)
    require(set(document) == {'schemaVersion', 'protocolId', 'status', 'scientificFitCallBudget', 'oracleProblemCount', 'cases'},
            'Fixture root fields differ from frozen schema')
    require(document.get('schemaVersion') == 1 and document.get('protocolId') == PROTOCOL_ID,
            'Unknown fixture protocol')
    require(document.get('status') == 'frozen', 'Fixture protocol is not frozen')
    require(document.get('scientificFitCallBudget') == FIT_COUNT and document.get('oracleProblemCount') == REFERENCE_COUNT,
            'Frozen fixture budgets differ')
    cases = document.get('cases')
    require(isinstance(cases, list) and len(cases) == FIT_COUNT, 'Exactly 20 fixed cases required')
    identifiers = [case.get('id') for case in cases]
    require(all(isinstance(x, str) and x for x in identifiers) and len(set(identifiers)) == FIT_COUNT,
            'Invalid or duplicate case identities')
    for case in cases:
        require(case.get('groups') == 2, 'The frozen model has exactly two fixed effects')
        require(all(type(case.get(key)) is bool for key in ('equalWithin', 'equalBetween', 'reml')),
                'Model flags must be Boolean')
        require(case.get('classification') in ('regular', 'degenerate_constant'), 'Unknown classification')
        clusters = case.get('clusters')
        require(isinstance(clusters, list) and 4 <= len(clusters) <= 10, 'Invalid cluster count')
        require(len({c.get('entity') for c in clusters}) == len(clusters), 'Duplicate entity identity')
        count = 0
        for c in clusters:
            values = c.get('values')
            require(type(c.get('group')) is int and c['group'] in (0, 1), 'Invalid cluster group')
            require(type(c.get('count')) is int and c['count'] >= 2 and isinstance(values, list)
                    and len(values) == c['count'] and all(finite(x) for x in values), 'Invalid raw observations')
            count += len(values)
            require(finite(c.get('mean')) and finite(c.get('withinSumSquares')) and c['withinSumSquares'] >= 0,
                    'Invalid summary')
            mean = math.fsum(values) / len(values)
            within = math.fsum((x - mean) ** 2 for x in values)
            require(abs(mean - c['mean']) <= 1e-12 * max(1., abs(c['mean'])), 'Raw/summary mean mismatch')
            require(abs(within - c['withinSumSquares']) <= 1e-12 * max(1., abs(c['withinSumSquares'])),
                    'Raw/summary within sum of squares mismatch')
        require(count <= 40 and all(sum(c['group'] == g for c in clusters) >= 2 for g in (0, 1)),
                'Design exceeds fixed dense 40-observation budget')
    return document, sha256(raw)


class EvaluationBudget:
    def __init__(self, limit=MAX_EVALUATIONS, seconds=REFERENCE_SECONDS):
        self.limit, self.seconds = limit, seconds
        self.count = 0
        self.high_precision_count = 0
        self.optimizer_attempts = 0
        self.optimizer_completed = 0
        self.active_attempt = None
        self.started = time.monotonic()

    def high_precision(self):
        self.high_precision_count += 1
        self.check()
        if self.high_precision_count > 128:
            raise BudgetExhausted('Frozen 128 high-precision evaluation budget exhausted')

    def check(self, evaluate=False):
        if evaluate:
            self.count += 1
        if self.count > self.limit or time.monotonic() - self.started > self.seconds:
            raise BudgetExhausted('Frozen reference evaluation/time budget exhausted')


class DenseModel:
    """Observation-level V/X model with profiled fixed effects and exact score."""
    def __init__(self, case):
        self.case = case
        self.groups = case['groups']
        self.ns = 1 if case['equalWithin'] else self.groups
        self.nt = 1 if case['equalBetween'] else self.groups
        self.dim = self.ns + self.nt
        self.raw = np.array([x for c in case['clusters'] for x in c['values']], dtype=float)
        self.n = len(self.raw)
        self.group_scales = []
        for g in range(self.groups):
            data = [x for c in case['clusters'] if c['group'] == g for x in c['values']]
            mean = math.fsum(data) / len(data)
            self.group_scales.append(math.fsum((x - mean) ** 2 for x in data) / len(data))
        self.p = self.groups
        self.center = math.fsum(float(x) for x in self.raw) / self.n
        self.scale2 = math.fsum((float(x) - self.center) ** 2 for x in self.raw) / self.n
        if not math.isfinite(self.scale2) or self.scale2 <= 0:
            raise OracleInvalid('Constant data have no positive-scale Gaussian optimum')
        self.scale = math.sqrt(self.scale2)
        self.y = (self.raw - self.center) / self.scale
        self.X = np.zeros((self.n, self.groups))
        self.bases = np.zeros((self.dim, self.n, self.n))
        offset = 0
        for cluster in case['clusters']:
            n, g = cluster['count'], cluster['group']
            sl = slice(offset, offset + n)
            self.X[sl, g] = 1
            self.bases[0 if case['equalWithin'] else g, sl, sl] += np.eye(n)
            self.bases[self.ns + (0 if case['equalBetween'] else g), sl, sl] += np.ones((n, n))
            offset += n

    def evaluate(self, logs, *, budget=None, details=False, exact_zero_between=False):
        if budget is not None:
            budget.check(evaluate=True)
        logs = np.asarray(logs, dtype=float)
        if logs.shape != (self.dim,) or not np.isfinite(logs).all():
            raise OracleInvalid('Invalid reference parameter vector')
        variances = np.exp(logs)
        if exact_zero_between:
            variances[self.ns:] = 0
        derivatives = self.bases * variances[:, None, None]
        V = derivatives.sum(axis=0)
        block_max, block_min = [], []
        for c in self.case['clusters']:
            s = variances[0 if self.case['equalWithin'] else c['group']]
            t = variances[self.ns + (0 if self.case['equalBetween'] else c['group'])]
            block_max.append(s + c['count'] * t)
            block_min.append(s)
        condition = float(max(block_max) / min(block_min))
        if condition > 1e8:
            result = self.high_precision(logs, budget=budget, counted=True, details=details)
            if details:
                result['condition'] = condition
                return result
            value, score = result
            return value, np.array(score)
        try:
            factor = cho_factor(V, lower=True, check_finite=False)
            Vinv = cho_solve(factor, np.eye(self.n), check_finite=False)
            W = Vinv @ self.X
            gram = self.X.T @ W
            gf = cho_factor(gram, lower=True, check_finite=False)
            gram_inv = cho_solve(gf, np.eye(self.p), check_finite=False)
            beta = gram_inv @ (W.T @ self.y)
            residual = self.y - self.X @ beta
            u = cho_solve(factor, residual, check_finite=False)
            logdet = 2 * np.log(np.diag(factor[0])).sum()
            q = float(residual @ u)
            nll = .5 * (logdet + q)
            P = Vinv - W @ gram_inv @ W.T
            if self.case['reml']:
                nll += np.log(np.diag(gf[0])).sum()
            metric = P if self.case['reml'] else Vinv
            trace_terms = np.einsum('ij,kji->k', metric, self.bases)
            quadratic_terms = np.einsum('i,kij,j->k', u, self.bases, u)
            linear_scores = .5 * (trace_terms - quadratic_terms)
            score = linear_scores * variances
        except (np.linalg.LinAlgError, ValueError, FloatingPointError) as exc:
            raise OracleInvalid('Dense covariance factorization/solve failed') from exc
        if not math.isfinite(nll) or not np.isfinite(score).all() or q < -1e-10:
            raise OracleInvalid('Nonfinite or invalid dense objective')
        if not details:
            return float(nll), score
        within = [float(variances[0 if self.case['equalWithin'] else g] * self.scale2) for g in range(self.groups)]
        between = [float(variances[self.ns + (0 if self.case['equalBetween'] else g)] * self.scale2) for g in range(self.groups)]
        normalization = .5 * (self.n - (self.p if self.case['reml'] else 0)) * math.log(self.scale2)
        def relative_residual(matrix, solution, rhs):
            denominator = np.linalg.norm(matrix, ord=np.inf) * np.linalg.norm(solution, ord=np.inf) + np.linalg.norm(rhs, ord=np.inf)
            numerator = np.linalg.norm(matrix @ solution - rhs, ord=np.inf)
            return float(numerator / denominator) if denominator else 0.
        solve_residual = max([relative_residual(V, Vinv[:, i], np.eye(self.n)[:, i]) for i in range(self.n)] +
                             [relative_residual(V, u, residual), relative_residual(gram, beta, W.T @ self.y)])
        return dict(normalizedNll=float(nll), rawConstantFreeNll=float(nll + normalization),
                    normalizationCorrection=normalization,
                    means=(self.center + self.scale * beta).tolist(), within=within, between=between,
                    rawFullNll=float(nll + normalization + .5 * (self.n - (self.p if self.case['reml'] else 0)) * math.log(2 * math.pi)),
                    logs=logs.tolist(), gradient=score.tolist(), linearScores=linear_scores.tolist(),
                    traceTerms=trace_terms.tolist(), quadraticTerms=quadratic_terms.tolist(), condition=condition,
                    inverseResidual=float(solve_residual), fixedEffectResidual=float(np.linalg.norm(self.X.T @ u, ord=np.inf)))

    def high_precision(self, logs, budget=None, counted=False, details=False):
        try:
            return self._high_precision(logs, budget, counted, details)
        except (ValueError, ZeroDivisionError, FloatingPointError) as error:
            raise OracleInvalid('High-precision covariance evaluation failed: ' + str(error)) from error

    def _high_precision(self, logs, budget, counted, details):
        if budget is not None:
            budget.check(evaluate=not counted)
            budget.high_precision()
        with mp.workdps(60):
            v = [mp.exp(mp.mpf(float(x))) for x in logs]
            V = mp.matrix(self.n)
            for i in range(self.n):
                for j in range(self.n):
                    V[i, j] = mp.fsum(v[k] * int(self.bases[k, i, j]) for k in range(self.dim))
            X = mp.matrix(self.X.tolist())
            y = mp.matrix([mp.mpf(float(x)) for x in self.y])
            L = mp.cholesky(V)
            Vinv = mp.matrix(self.n)
            offset = 0
            for cluster in self.case['clusters']:
                count = cluster['count']
                block = mp.matrix([[V[offset+i, offset+j] for j in range(count)] for i in range(count)])
                inverse = block ** -1
                for i in range(count):
                    for j in range(count):
                        Vinv[offset+i, offset+j] = inverse[i,j]
                offset += count
            W = Vinv * X
            gram = X.T * W
            gram_inv = gram ** -1
            beta = gram_inv * X.T * Vinv * y
            residual = y - X * beta
            u = Vinv * residual
            value = mp.fsum(mp.log(L[i, i]) for i in range(self.n)) + (residual.T * u)[0] / 2
            metric = Vinv
            if self.case['reml']:
                gf = mp.cholesky(gram)
                value += mp.fsum(mp.log(gf[i, i]) for i in range(self.p))
                metric = Vinv - W * gram_inv * W.T
            traces = [mp.fsum(metric[i, j] * int(self.bases[k, j, i]) for i in range(self.n) for j in range(self.n))
                      for k in range(self.dim)]
            quadratics = [mp.fsum(u[i] * u[j] * int(self.bases[k, i, j]) for i in range(self.n) for j in range(self.n))
                          for k in range(self.dim)]
            linear = [(a-b)/2 for a,b in zip(traces, quadratics)]
            score = [v[k] * linear[k] for k in range(self.dim)]
            if budget is not None:
                budget.check()
            if not math.isfinite(float(value)) or not all(math.isfinite(float(x)) for x in score):
                raise OracleInvalid('Nonfinite high-precision covariance result')
            if not details:
                return float(value), [float(x) for x in score]
            def relative(matrix, solution, rhs):
                denominator = mp.mnorm(matrix, mp.inf) * mp.norm(solution, mp.inf) + mp.norm(rhs, mp.inf)
                return mp.norm(matrix * solution - rhs, mp.inf) / denominator if denominator else mp.mpf(0)
            identity = mp.eye(self.n)
            residual_max = max([relative(V, Vinv[:, i], identity[:, i]) for i in range(self.n)] +
                               [relative(V, u, residual)])
            normalization = .5 * (self.n - (self.p if self.case['reml'] else 0)) * math.log(self.scale2)
            nll = float(value)
            return dict(normalizedNll=nll, rawConstantFreeNll=nll + normalization,
                        normalizationCorrection=normalization,
                        rawFullNll=nll + normalization + .5*(self.n-(self.p if self.case['reml'] else 0))*math.log(2*math.pi),
                        means=[self.center + self.scale*float(x) for x in beta],
                        within=[self.scale2*float(v[0 if self.case['equalWithin'] else g]) for g in range(self.groups)],
                        between=[self.scale2*float(v[self.ns+(0 if self.case['equalBetween'] else g)]) for g in range(self.groups)],
                        logs=list(map(float, logs)), gradient=list(map(float, score)), linearScores=list(map(float, linear)),
                        traceTerms=list(map(float, traces)), quadraticTerms=list(map(float, quadratics)),
                        inverseResidual=float(residual_max), fixedEffectResidual=float(mp.norm(X.T*u, mp.inf)),
                        evaluationPrecision='mpmath60')

    def native_logs(self, row):
        s = row['within'][:1] if self.case['equalWithin'] else row['within']
        t = row['between'][:1] if self.case['equalBetween'] else row['between']
        values = np.array(s + t, dtype=float) / self.scale2
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise InvalidEvidence('Regular candidate variances must be finite and positive')
        return np.log(values)


def projected_gradient(logs, gradient):
    logs, out = np.asarray(logs), np.array(gradient, dtype=float, copy=True)
    out[(logs <= LOG_BOUNDS[0] + 1e-7) & (out > 0)] = 0
    out[(logs >= LOG_BOUNDS[1] - 1e-7) & (out < 0)] = 0
    return float(np.max(np.abs(out)))


def linear_kkt(detail):
    failures = []
    for i, (theta, score, trace, quadratic) in enumerate(zip(detail['logs'], detail['linearScores'],
                                                           detail['traceTerms'], detail['quadraticTerms'])):
        tolerance = 1e-6 * (1 + .5 * abs(trace) + .5 * abs(quadratic))
        valid = (score >= -tolerance if theta <= LOG_BOUNDS[0] + 1e-6 else
                 score <= tolerance if theta >= LOG_BOUNDS[1] - 1e-6 else abs(score) <= tolerance)
        if not valid:
            failures.append(i)
    return failures


def start_agreement(model, first, second):
    if abs(first['normalizedNll'] - second['normalizedNll']) > 1e-8:
        return False
    for g, h in enumerate(model.group_scales):
        if abs(first['means'][g] - second['means'][g]) > 1e-7 * math.sqrt(h):
            return False
        for component, index in (('within', 0 if model.case['equalWithin'] else g),
                                 ('between', model.ns + (0 if model.case['equalBetween'] else g))):
            if first['logs'][index] > LOG_BOUNDS[0] + 1e-6:
                if abs(first[component][g] - second[component][g]) > 1e-6 * abs(first[component][g]) + 1e-9 * h:
                    return False
    return True


def optimize_reference(model, budget):
    """Two predeclared starts on every subset of between-at-floor faces."""
    runs = []
    budget.partial_problem = dict(id=model.case['id'], runs=runs)
    for mask in range(1 << model.nt):
        fixed = {model.ns + t for t in range(model.nt) if mask & (1 << t)}
        free = [j for j in range(model.dim) if j not in fixed]
        face_runs = []
        for start_index, (s, t) in enumerate(STARTS):
            full = np.log([s] * model.ns + [t] * model.nt)
            for j in fixed:
                full[j] = LOG_BOUNDS[0]
            before = budget.count
            local_calls = 0
            budget.optimizer_attempts += 1
            budget.active_attempt = dict(id=model.case['id'], faceMask=mask, startIndex=start_index,
                                         evaluations=0, status='running', latestPoint=None)
            def objective(z):
                nonlocal local_calls
                local_calls += 1
                budget.active_attempt['evaluations'] = local_calls
                if local_calls > MAX_FUNCTION_CALLS:
                    raise BudgetExhausted('Frozen per-start 1500 objective budget exhausted')
                vector = full.copy()
                vector[free] = z
                value, gradient = model.evaluate(vector, budget=budget)
                budget.active_attempt['latestPoint'] = dict(logs=vector.tolist(), normalizedNll=value)
                return value, gradient[free]
            result = minimize(objective, full[free], method='L-BFGS-B', jac=True,
                              bounds=[LOG_BOUNDS] * len(free),
                              options={'maxfun': MAX_FUNCTION_CALLS, 'maxiter': MAX_ITERATIONS,
                                       'ftol': 1e-14, 'gtol': 1e-9, 'maxls': 40})
            full[free] = result.x
            detail = model.evaluate(full, budget=budget, details=True)
            detail['projectedGradient'] = projected_gradient(detail['logs'], detail['gradient'])
            detail['linearKktFailures'] = linear_kkt(detail)
            record = dict(faceMask=mask, startIndex=start_index, success=bool(result.success),
                          message=str(result.message), evaluations=local_calls,
                          iterations=int(result.nit), **detail)
            record['stationary'] = (record['projectedGradient'] <= 1e-6 and not record['linearKktFailures']
                                    and record['condition'] <= 1e8 and record['inverseResidual'] <= 1e-10)
            face_runs.append(record)
            runs.append(record)
            budget.optimizer_completed += 1
            budget.active_attempt = None
        agreement = all(row['success'] for row in face_runs) and start_agreement(model, *face_runs)
        for row in face_runs:
            row['faceStartsAgree'] = agreement
            row['certified'] = agreement and row['stationary']
    certified = [row for row in runs if row['certified']]
    if not certified:
        error = OracleInvalid('No predeclared reference face passed certification for ' + model.case['id'])
        error.details = dict(id=model.case['id'], runs=runs)
        raise error
    lowest = min(row['normalizedNll'] for row in certified)
    tied = [row for row in certified if row['normalizedNll'] <= lowest + 1e-8]
    winner = dict(min(tied, key=lambda row: (-row['faceMask'].bit_count(), row['faceMask'], row['startIndex'])))
    if winner['normalizedNll'] > min(row['normalizedNll'] for row in runs) + 1e-8:
        error = OracleInvalid('A better feasible endpoint was not certified')
        error.details = dict(id=model.case['id'], optimum=winner, runs=runs)
        raise error
    audit_value, audit_gradient = model.high_precision(winner['logs'], budget)
    winner['highPrecisionAudit'] = dict(normalizedNll=audit_value, gradient=audit_gradient,
                                       nllError=abs(audit_value - winner['normalizedNll']),
                                       gradientError=max(abs(a-b) for a,b in zip(audit_gradient, winner['gradient'])))
    if winner['highPrecisionAudit']['nllError'] > 1e-8 or winner['highPrecisionAudit']['gradientError'] > 1e-8:
        error = OracleInvalid('Accepted reference failed the fixed 60-digit audit')
        error.details = dict(id=model.case['id'], optimum=winner, runs=runs)
        raise error
    return dict(id=model.case['id'], optimum=winner, runs=runs)


def verify_fp(value, metadata):
    require(isinstance(metadata, dict), 'Missing numeric classification')
    bits = metadata.get('bits')
    require(isinstance(bits, str) and len(bits) == 16 and all(c in '0123456789abcdef' for c in bits),
            'Invalid binary64 bit evidence')
    decoded = struct.unpack('>d', bytes.fromhex(bits))[0]
    kind = ('nan' if math.isnan(decoded) else 'positive_infinity' if decoded == math.inf
            else 'negative_infinity' if decoded == -math.inf else 'finite')
    require(metadata.get('classification') == kind, 'Numeric classification/bits mismatch')
    if kind == 'finite':
        require(finite(value) and finite(metadata.get('value')),
                'Finite classification requires a finite JSON number')
        require(struct.pack('>d', float(value)).hex() == bits and
                struct.pack('>d', float(metadata['value'])).hex() == bits,
                'Numeric value/bits mismatch')
    else:
        require(value is None and metadata.get('value') is None, 'Nonfinite export must use JSON null')
    return kind


def validate_native(document, fixture_hash, native, root, assembly):
    require(native.get('schemaVersion') == 1 and native.get('protocolId') == PROTOCOL_ID,
            'Unknown native export protocol')
    require(native.get('inputSha256') == fixture_hash, 'Native fixture hash mismatch')
    require(native.get('caseCount') == FIT_COUNT and native.get('fitCallCount') == FIT_COUNT,
            'Native case/fit-call accounting mismatch')
    cases = native.get('cases')
    require(isinstance(cases, list) and len(cases) == FIT_COUNT, 'Incomplete native export')
    require([row.get('id') for row in cases] == [row['id'] for row in document['cases']],
            'Native case identities/order differ from frozen fixtures')
    identity = native.get('identity', {})
    require(identity.get('experimental') is True, 'Missing experimental identity')
    expected = {name: sha256((Path(root) / name).read_bytes()) for name in SOURCE_FILES}
    require(identity.get('sourceSha256') == expected, 'Embedded build-time source identity mismatch')
    assembly = Path(assembly)
    for key, path in (('harnessAssembly', assembly), ('coreAssembly', assembly.with_name('MvsAnalyzer.Core.dll'))):
        data = identity.get(key, {})
        require(data.get('sha256') == sha256(path.read_bytes()), 'Assembly identity mismatch: ' + key)
        require(data.get('fileName') == path.name and bool(data.get('moduleVersionId')), 'Incomplete assembly identity')
    require(all(identity.get('runtime', {}).get(key) for key in
                ('framework', 'version', 'os', 'processArchitecture', 'osArchitecture')), 'Incomplete runtime identity')
    for case, row in zip(document['cases'], cases):
        for key in ('id', 'fixtureId', 'groups', 'equalWithin', 'equalBetween', 'reml'):
            require(row.get(key) == case[key], 'Native case/model mismatch: ' + key)
        require(row.get('candidateInvoked') is True and row.get('requestedClassification') == case['classification'],
                'Native candidate invocation/classification mismatch')
        require(row.get('clusterCount') == len(case['clusters']) and
                row.get('measurementCount') == sum(c['count'] for c in case['clusters']), 'Native design count mismatch')
        require(row.get('status') in ('returned_finite', 'returned_nonfinite', 'exception', 'cancelled'),
                'Unknown native status')
        if row['status'] in ('exception', 'cancelled'):
            require(isinstance(row.get('exception'), dict) and row.get('numeric') is None,
                    'Missing native exception evidence')
            continue
        require(row.get('exception') is None and type(row.get('converged')) is bool and
                type(row.get('atBoundary')) is bool and type(row.get('iterations')) is int and row['iterations'] >= 0,
                'Malformed native flags')
        require(row.get('method') == ('REML' if case['reml'] else 'ML'), 'Native method mismatch')
        classifications = []
        for name in ('means', 'within', 'between'):
            require(isinstance(row.get(name), list) and len(row[name]) == 2 and
                    isinstance(row.get('numeric', {}).get(name), list) and len(row['numeric'][name]) == 2,
                    'Native parameter vector length mismatch')
            classifications += [verify_fp(v, fp) for v, fp in zip(row[name], row['numeric'][name])]
        classifications.append(verify_fp(row.get('negativeLogLikelihood'), row['numeric'].get('negativeLogLikelihood')))
        require((row['status'] == 'returned_finite') == all(k == 'finite' for k in classifications),
                'Native status and numeric classifications disagree')
    return cases


def balanced_truth(case):
    """Exact balanced ANOVA solution in the nonnegative-variance domain.

    The box reference retains exp(-23), so a boundary truth is a limit check,
    never a claim that the native finite floor equals mathematical zero.
    """
    require(not case['equalWithin'] and not case['equalBetween'], 'Analytic truth requires unconstrained groups')
    means, within, between = [], [], []
    for group in range(case['groups']):
        clusters = [c for c in case['clusters'] if c['group'] == group]
        counts = {c['count'] for c in clusters}
        require(len(counts) == 1, 'Analytic truth requires balanced repeats')
        n, k = counts.pop(), len(clusters)
        m = math.fsum(c['mean'] for c in clusters) / k
        W = math.fsum(c['withinSumSquares'] for c in clusters)
        S = math.fsum((c['mean'] - m) ** 2 for c in clusters)
        s = W / (k * (n - 1))
        t = S / (k - 1 if case['reml'] else k) - s / n
        if t < 0:
            t = 0.
            s = (W + n * S) / (n * k - (1 if case['reml'] else 0))
        means.append(m)
        within.append(s)
        between.append(t)
    return dict(means=means, within=within, between=between)


def error_checks(case, actual, expected, scale2):
    scale = math.sqrt(scale2)
    mean_error = max(abs(a - b) for a, b in zip(actual['means'], expected['means'])) / scale
    variance_errors = {name: max(abs(a - b) / scale2 for a, b in zip(actual[name], expected[name]))
                       for name in ('within', 'between')}
    return dict(meanNormalizedError=mean_error, varianceNormalizedErrors=variance_errors)


def conditioning_preflight(budget):
    audits = []
    for n in (2, 3, 4, 5):
        budget.check(evaluate=True)
        budget.high_precision()
        with mp.workdps(60):
            s, t = mp.exp(-23), mp.mpf('.1')
            V = s * mp.eye(n) + t * mp.ones(n)
            factor = mp.cholesky(V)
            A = V ** -1
            X = mp.ones(n, 1)
            y = mp.matrix(list(range(n)))
            beta = (X.T * A * X) ** -1 * X.T * A * y
            residual = y - X * beta
            determinant = mp.fprod(factor[i, i] ** 2 for i in range(n))
            quadratic = (residual.T * A * residual)[0]
            expected_det = s ** (n - 1) * (s + n * t)
            expected_quad = mp.fsum((mp.mpf(i) - mp.mpf(n - 1) / 2) ** 2 for i in range(n)) / s
            determinant_error = abs(determinant - expected_det) / abs(expected_det)
            quadratic_error = abs(quadratic - expected_quad) / max(1, abs(expected_quad))
            if determinant_error > mp.mpf('1e-40') or quadratic_error > mp.mpf('1e-40'):
                raise OracleInvalid('High-condition dense eigenidentity preflight failed')
            binary = {}
            try:
                double_V = float(s)*np.eye(n) + float(t)*np.ones((n,n))
                double_factor = cho_factor(double_V, lower=True)
                double_inverse = cho_solve(double_factor, np.eye(n))
                double_X, double_y = np.ones(n), np.arange(n, dtype=float)
                double_beta = (double_X @ double_inverse @ double_y) / (double_X @ double_inverse @ double_X)
                double_residual = double_y - double_beta
                double_det = float(np.prod(np.diag(double_factor[0]) ** 2))
                double_quad = float(double_residual @ double_inverse @ double_residual)
                binary = dict(determinantRelativeError=float(abs(mp.mpf(double_det)-expected_det)/abs(expected_det)),
                              quadraticScaledError=float(abs(mp.mpf(double_quad)-expected_quad)/max(1,abs(expected_quad))))
            except (ValueError, np.linalg.LinAlgError) as error:
                binary = dict(error=str(error))
            audits.append(dict(blockSize=n, determinantRelativeError=str(determinant_error),
                               quadraticScaledError=str(quadratic_error), binary64Diagnostic=binary))
        budget.check()
    return audits


def analytic_anchor(model, result, budget):
    truth = balanced_truth(model.case)
    optimum = result['optimum']
    for g, h in enumerate(model.group_scales):
        if abs(optimum['means'][g] - truth['means'][g]) > 1e-8 * math.sqrt(h):
            raise OracleInvalid('Balanced analytic mean anchor failed')
        for component in ('within', 'between'):
            if model.case['fixtureId'] == 'B':
                tol = 1e-6 * abs(truth[component][g]) + 1e-9 * h
            elif component == 'within':
                tol = 1e-6 * h
            else:
                continue
            if abs(optimum[component][g] - truth[component][g]) > tol:
                raise OracleInvalid('Balanced analytic variance anchor failed')
    logs = np.log(np.array(truth['within'] + [max(x, model.scale2 * math.exp(-23)) for x in truth['between']]) / model.scale2)
    feasible, _ = model.evaluate(logs, budget=budget)
    if model.case['fixtureId'] == 'B':
        if abs(feasible - optimum['normalizedNll']) > 1e-8:
            raise OracleInvalid('Balanced interior analytic NLL anchor failed')
        return dict(truth=truth, analyticNormalizedNll=feasible, boxNll=optimum['normalizedNll'])
    zero, _ = model.evaluate(logs, budget=budget, exact_zero_between=True)
    if zero > optimum['normalizedNll'] + 1e-8 or optimum['normalizedNll'] > feasible + 1e-8:
        raise OracleInvalid('Exact-zero/finite-box/feasible-point NLL ordering failed')
    return dict(truth=truth, exactZeroNormalizedNll=zero, finiteFloorFeasibleNll=feasible,
                boxNll=optimum['normalizedNll'], exactToBoxGap=optimum['normalizedNll'] - zero)


def nesting(values, slack):
    pairs = [('U_ML', 'U_ML_equalWithin'), ('U_ML', 'U_ML_equalBetween'),
             ('U_ML_equalWithin', 'U_ML_equalBoth'), ('U_ML_equalBetween', 'U_ML_equalBoth')]
    rows = [dict(free=a, restricted=b, difference=values[b] - values[a],
                 passed=values[a] <= values[b] + slack) for a,b in pairs]
    return rows


def atomic_json(path, document):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(document, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def reference_all(document, evidence_path=None, identity=None):
    budget = EvaluationBudget()
    base_cases = [case for case in document['cases'] if case['classification'] == 'regular'
                  and case['referenceCaseId'] is None]
    require(len(base_cases) == REFERENCE_COUNT, 'Exactly nine base reference fits are required')
    report = dict(status='running', identity=identity, references={}, preflight=[], budget={}, caseReferences={})
    def save():
        report['budget'] = dict(objectiveEvaluations=budget.count, highPrecisionEvaluations=budget.high_precision_count,
                               optimizerCalls=budget.optimizer_attempts, completedOptimizerCalls=budget.optimizer_completed,
                               baseReferenceFits=len(report['references']), elapsedSeconds=time.monotonic() - budget.started)
        report['activeAttempt'] = budget.active_attempt
        if evidence_path:
            atomic_json(evidence_path, report)
    try:
        report['preflight'] = conditioning_preflight(budget)
        for case in base_cases:
            model = DenseModel(case)
            result = optimize_reference(model, budget)
            report['references'][case['id']] = result
            if case['fixtureId'] in ('B', 'Z'):
                result['analyticAnchor'] = analytic_anchor(model, result, budget)
            save()
        values = {key: item['optimum']['normalizedNll'] for key, item in report['references'].items()}
        report['nesting'] = nesting(values, 1e-8)
        if not all(row['passed'] for row in report['nesting']):
            raise OracleInvalid('Reference constrained-model nesting failed')
        if sum(len(ref['runs']) for ref in report['references'].values()) != OPTIMIZER_COUNT:
            raise OracleInvalid('Fixed reference optimizer-call accounting mismatch')
        for case in document['cases']:
            if case['classification'] != 'regular':
                continue
            if case['referenceCaseId'] is None:
                report['caseReferences'][case['id']] = report['references'][case['id']]['optimum']
                continue
            base = report['references'][case['referenceCaseId']]['optimum']
            b, a = case['affineScale'], case['affineOffset']
            expected = dict(base, means=[a+b*x for x in base['means']],
                            within=[b*b*x for x in base['within']], between=[b*b*x for x in base['between']])
            model = DenseModel(case)
            detail = model.evaluate(model.native_logs(expected), budget=budget, details=True)
            if abs(detail['normalizedNll'] - base['normalizedNll']) > 1e-8:
                raise OracleInvalid('Derived affine reference dense objective disagrees')
            report['caseReferences'][case['id']] = dict(expected, rawFullNll=detail['rawFullNll'],
                                                       rawConstantFreeNll=detail['rawConstantFreeNll'],
                                                       normalizationCorrection=detail['normalizationCorrection'],
                                                       derivedFrom=case['referenceCaseId'], denseReevaluation=detail)
        report['status'] = 'certified'
        budget.check()
    except OracleInvalid as error:
        report['status'] = 'oracle_inconclusive'
        report['error'] = str(error)
        report['partialProblem'] = getattr(error, 'details', getattr(budget, 'partial_problem', None))
        save()
        raise
    save()
    return report


def native_run(command, fixtures, fixture_digest, out):
    """One ordinary bounded subprocess, preserving its exact output bytes."""
    started = time.monotonic()
    require(sha256(Path(fixtures).read_bytes()) == fixture_digest, 'Fixture bytes changed after reference certification')
    complete_command = list(command) + ['fit', str(Path(fixtures).resolve()), fixture_digest]
    try:
        process = subprocess.run(complete_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=NATIVE_SECONDS, check=False)
        stdout, stderr, code, timeout = process.stdout, process.stderr, process.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code, timeout = error.stdout or b'', error.stderr or b'', None, True
    try:
        (out / 'native.stdout').write_bytes(stdout)
        (out / 'native.stderr').write_bytes(stderr)
        evidence = dict(command=complete_command, exitCode=code, timedOut=timeout,
                        elapsedSeconds=time.monotonic() - started,
                        stdoutSha256=sha256(stdout), stderrSha256=sha256(stderr),
                        stdoutBytes=len(stdout), stderrBytes=len(stderr))
        (out / 'native-process.json').write_text(json.dumps(evidence, indent=2) + '\n')
        if timeout or code != 0:
            error = InvalidEvidence('Native subprocess timed out or exited unsuccessfully; exact output retained')
            error.native_started = True
            raise error
        return read_json(stdout), evidence
    except Exception as error:
        error.native_started = True
        raise


def parameter_checks(model, actual, expected, multiplier=1.):
    checks = []
    for g, h in enumerate(model.group_scales):
        for component in ('means', 'within', 'between'):
            reference = expected[component][g]
            if component == 'means':
                tolerance = 2e-4 * math.sqrt(h) + 1e-10 * max(1, abs(reference))
            elif (component == 'between' and expected['logs'][model.ns + (0 if model.case['equalBetween'] else g)]
                  <= LOG_BOUNDS[0] + 1e-6):
                tolerance = max(5 * model.scale2 * math.exp(-23), 1e-6 * h)
            else:
                tolerance = 5e-4 * abs(reference) + 1e-7 * h
            tolerance *= multiplier
            error = abs(actual[component][g] - reference)
            checks.append(dict(component=component, group=g, actual=actual[component][g], reference=reference,
                               error=error, tolerance=tolerance, passed=error <= tolerance))
    return checks


def compare(document, reference, native):
    require(reference.get('status') == 'certified', 'Native accuracy cannot be judged without certified references')
    result_rows, expected_rows = [], reference['caseReferences']
    inconclusive = False
    native_by_id = {row['id']: row for row in native['cases']}
    models = {}
    for case in document['cases']:
        row = native_by_id[case['id']]
        if case['classification'] == 'degenerate_constant':
            passed = (row['status'] == 'returned_nonfinite' and row['means'] == [7., 7.] and
                      row['within'] == [0., 0.] and row['between'] == [0., 0.] and
                      row['negativeLogLikelihood'] is None and row['numeric']['negativeLogLikelihood']['classification'] == 'nan'
                      and row['converged'] is False and row['atBoundary'] is True and row['iterations'] == 0)
            result_rows.append(dict(id=case['id'], category='degenerate_guard_contract', passed=passed,
                                    failureReasons=[] if passed else ['constant_guard_contract_mismatch'], native=row))
            continue
        model = models[case['id']] = DenseModel(case)
        expected = expected_rows[case['id']]
        reasons = []
        result = dict(id=case['id'], category='numerical_fit', native=row, reference=expected,
                      groupVarianceScales=model.group_scales, failureReasons=reasons)
        result_rows.append(result)
        if row['status'] != 'returned_finite':
            reasons.append('native_nonfinite_or_exception')
            result['passed'] = False
            continue
        if row['converged'] is not True:
            reasons.append('native_not_converged')
        if any(x <= 0 for x in row['within'] + row['between']):
            reasons.append('nonpositive_variance')
            result['passed'] = False
            continue
        logs = model.native_logs(row)
        result['nativeLogs'] = logs.tolist()
        if np.any(logs < LOG_BOUNDS[0] - 1e-10) or np.any(logs > LOG_BOUNDS[1] + 1e-10):
            reasons.append('native_outside_frozen_box')
            result['passed'] = False
            continue
        result['parameters'] = parameter_checks(model, row, expected)
        if not all(check['passed'] for check in result['parameters']):
            reasons.append('native_parameter_accuracy')
        closure = model.evaluate(logs, details=True)
        discrepancy = abs(closure['normalizedNll'] - row['negativeLogLikelihood'])
        tolerance = 2e-8 * (1 + abs(expected['normalizedNll']))
        gap = row['negativeLogLikelihood'] - expected['normalizedNll']
        result['objective'] = dict(denseAtNative=closure, reportedDiscrepancy=discrepancy,
                                   reportedTolerance=tolerance, gapFromReference=gap,
                                   gapLower=-1e-7, gapUpper=2e-5)
        if discrepancy > tolerance:
            reasons.append('native_reported_objective_mismatch')
        if gap > 2e-5:
            reasons.append('native_objective_above_reference')
        if gap < -1e-7:
            reasons.append('native_below_reference_inconclusive')
            inconclusive = True
        gls = dict(expected, means=closure['means'])
        result['glsMeans'] = [check for check in parameter_checks(model, row, gls) if check['component'] == 'means']
        if not all(check['passed'] for check in result['glsMeans']):
            reasons.append('native_returned_means_not_gls')
        distances = np.minimum(np.abs(logs - LOG_BOUNDS[0]), np.abs(logs - LOG_BOUNDS[1]))
        ambiguous = bool(np.any(np.abs(distances - 1e-4) <= 1e-8))
        geometric = bool(np.any(distances < 1e-4))
        result['boundary'] = dict(reconstructed=geometric, thresholdAmbiguous=ambiguous,
                                  status='boundary_flag_threshold_ambiguous' if ambiguous else 'checked',
                                  endpointDistances=distances.tolist(), betweenFloorDistances=(logs[model.ns:] - LOG_BOUNDS[0]).tolist())
        if not ambiguous and row['atBoundary'] != geometric:
            reasons.append('native_boundary_flag_mismatch')
        for flag, component in (('equalWithin', 'within'), ('equalBetween', 'between')):
            if case[flag] and row['numeric'][component][0]['bits'] != row['numeric'][component][1]['bits']:
                reasons.append('shared_component_not_bitwise_equal:' + component)
        result['passed'] = not reasons
    result_by_id = {row['id']: row for row in result_rows}
    affine_checks = []
    for case in document['cases']:
        source_id = case['referenceCaseId']
        if source_id is None:
            continue
        current, source = result_by_id[case['id']], result_by_id[source_id]
        if 'objective' not in current or 'objective' not in source:
            affine_checks.append(dict(id=case['id'], source=source_id, passed=False, reason='unusable_native_fit'))
            continue
        b, a = case['affineScale'], case['affineOffset']
        target_native, source_native = native_by_id[case['id']], native_by_id[source_id]
        mapped = dict(means=[(x-a)/b for x in target_native['means']],
                      within=[x/(b*b) for x in target_native['within']], between=[x/(b*b) for x in target_native['between']])
        comparison_target = dict(source_native, logs=expected_rows[source_id]['logs'])
        checks = parameter_checks(models[source_id], mapped, comparison_target, multiplier=2)
        nll_error = abs(target_native['negativeLogLikelihood'] - source_native['negativeLogLikelihood'])
        degrees = models[source_id].n - (models[source_id].p if case['reml'] else 0)
        raw_shift_error = abs(current['objective']['denseAtNative']['rawFullNll'] -
                              source['objective']['denseAtNative']['rawFullNll'] - degrees * math.log(abs(b)))
        passed = all(check['passed'] for check in checks) and nll_error <= 4e-5 and raw_shift_error <= 4e-5
        affine_checks.append(dict(id=case['id'], source=source_id, passed=passed, parameters=checks,
                                  normalizedNllError=nll_error, rawNllShiftError=raw_shift_error, nllTolerance=4e-5))
        if not passed:
            current['failureReasons'].append('affine_invariance')
            current['passed'] = False
    restriction_ids = ['U_ML', 'U_ML_equalWithin', 'U_ML_equalBetween', 'U_ML_equalBoth']
    nested = []
    likelihood_ratios = []
    if all(finite(native_by_id[key]['negativeLogLikelihood']) for key in restriction_ids):
        native_values = {key: native_by_id[key]['negativeLogLikelihood'] for key in restriction_ids}
        nested = nesting(native_values, 5e-6)
        for key in restriction_ids[1:]:
            actual = 2 * (native_values[key] - native_values['U_ML'])
            expected = 2 * (expected_rows[key]['normalizedNll'] - expected_rows['U_ML']['normalizedNll'])
            likelihood_ratios.append(dict(restriction=key, native=actual, reference=expected,
                                           error=abs(actual-expected), tolerance=1e-4, passed=abs(actual-expected) <= 1e-4))
    all_passed = (all(row['passed'] for row in result_rows) and len(nested) == 4 and all(row['passed'] for row in nested)
                  and len(likelihood_ratios) == 3 and all(row['passed'] for row in likelihood_ratios)
                  and all(row['passed'] for row in affine_checks))
    return dict(schemaVersion=1, protocolId=PROTOCOL_ID,
                status='oracle_or_protocol_inconclusive' if inconclusive else 'passed' if all_passed else 'failed_accuracy',
                numericalFitCount=18, guardContractCount=2, fitCallCount=native['fitCallCount'],
                results=result_rows, affineChecks=affine_checks, nesting=nested, likelihoodRatios=likelihood_ratios,
                scientificConclusion='Fixed-fixture numerical validation only; no coverage, power, model adequacy, or production activation claim.')


def create_evidence_directory(path):
    path = Path(path).resolve()
    require(not path.exists(), 'Evidence directory already exists; refusing to overwrite a prior attempt')
    path.mkdir(parents=True, exist_ok=False)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--protocol', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native-command', nargs='+', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    fixtures = args.fixtures or root / 'validation/variance-fit-fixtures-v1.json'
    protocol = args.protocol or root / 'docs/ROUND48_VARIANCE_FIT_PROTOCOL.md'
    try:
        out = create_evidence_directory(args.out)
    except (InvalidEvidence, OSError) as error:
        print(json.dumps(dict(status='invalid_evidence', nativeInvoked=False, error=str(error))))
        return 2
    report = dict(schemaVersion=1, protocolId=PROTOCOL_ID, status='running', nativeInvoked=False)
    try:
        document, digest = load_fixtures(fixtures)
        report['fixtureSha256'] = digest
        report['protocolSha256'] = sha256(protocol.read_bytes())
        report['oracleSourceSha256'] = sha256(Path(__file__).read_bytes())
        blas_output = io.StringIO()
        with contextlib.redirect_stdout(blas_output):
            np.show_config()
        report['versions'] = dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__, mpmath=mp.__version__,
                                  platform=platform.platform(), blasSingleThread=True, blasConfiguration=blas_output.getvalue())
        reference = reference_all(document, out / 'reference.json', {key: report[key] for key in
                                  ('fixtureSha256', 'protocolSha256', 'oracleSourceSha256', 'versions')})
        report['reference'] = reference
        # A certified, persisted reference is mandatory before this one native process.
        native, process = native_run(args.native_command, fixtures, digest, out)
        report['nativeInvoked'] = True
        assembly = Path(args.native_command[-1])
        validate_native(document, digest, native, root, assembly)
        report['nativeProcess'] = process
        report['nativeIdentity'] = native['identity']
        report['comparison'] = compare(document, reference, native)
        report['status'] = report['comparison']['status']
    except OracleInvalid as error:
        report['status'] = 'oracle_inconclusive'
        report['error'] = str(error)
    except (InvalidEvidence, ValueError, KeyError, TypeError, OSError) as error:
        report['status'] = 'invalid_evidence'
        report['nativeInvoked'] = getattr(error, 'native_started', report['nativeInvoked'])
        report['error'] = str(error)
    atomic_json(out / 'comparison.json', report)
    print(json.dumps(dict(status=report['status'], nativeInvoked=report['nativeInvoked'], report=str(out / 'comparison.json'))))
    return 0 if report['status'] == 'passed' else 1 if report['status'] == 'failed_accuracy' else 2


if __name__ == '__main__':
    raise SystemExit(main())
