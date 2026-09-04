#!/usr/bin/env python3
"""Independent Python math checks, NOT compilation or execution of the C# implementation."""
import json
import math


def quadrature(n):
    a = [[0.] * n for _ in range(n)]
    v = [[float(i == j) for j in range(n)] for i in range(n)]
    for i in range(n - 1):
        a[i][i + 1] = a[i + 1][i] = math.sqrt(i + 1)
    for _ in range(100 * n * n):
        p, q = max(((i, j) for i in range(n) for j in range(i + 1, n)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1e-14:
            break
        angle = .5 * math.atan2(2 * a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(angle), math.sin(angle)
        ap, aq, off = a[p][p], a[q][q], a[p][q]
        a[p][p] = c*c*ap - 2*s*c*off + s*s*aq
        a[q][q] = s*s*ap + 2*s*c*off + c*c*aq
        a[p][q] = a[q][p] = 0.
        for k in range(n):
            if k not in (p, q):
                kp, kq = a[k][p], a[k][q]
                a[k][p] = a[p][k] = c*kp - s*kq
                a[k][q] = a[q][k] = s*kp + c*kq
            vp, vq = v[k][p], v[k][q]
            v[k][p], v[k][q] = c*vp - s*vq, s*vp + c*vq
    order = sorted(range(n), key=lambda i: a[i][i])
    return [a[i][i] for i in order], [v[0][i]**2 for i in order]


def dense_nll(r, d, tau):
    n = len(r)
    l = [[0.] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            value = tau + (d[i] if i == j else 0) - sum(l[i][k]*l[j][k] for k in range(j))
            l[i][j] = math.sqrt(value) if i == j else value/l[j][j]
    z = []
    for i in range(n):
        z.append((r[i] - sum(l[i][j]*z[j] for j in range(i)))/l[i][i])
    return .5*(n*math.log(2*math.pi) + 2*sum(math.log(l[i][i]) for i in range(n)) + sum(x*x for x in z))


def analytic_nll(r, d, tau):
    a = sum(1/v for v in d)
    b = sum(x/v for x, v in zip(r, d))
    c = sum(x*x/v for x, v in zip(r, d))
    return .5*(len(r)*math.log(2*math.pi) + sum(math.log(v) for v in d) + math.log1p(tau*a) + c - tau*b*b/(1+tau*a))


def main():
    result = {'scope': 'Independent Python mathematical identities; C# runtime not tested', 'quadrature': [], 'rankOneCovarianceIdentity': []}
    for count in (3, 9, 15, 31, 61):
        nodes, weights = quadrature(count)
        moments = [sum(w*x**k for x, w in zip(nodes, weights)) for k in (0, 1, 2, 4)]
        error = max(abs(a-b) for a, b in zip(moments, (1, 0, 1, 3)))
        assert error < 1e-8 and all(w > 0 for w in weights), (count, moments)
        result['quadrature'].append({'order': count, 'moments_0_1_2_4': moments, 'maxAbsoluteError': error})
    for tau in (0, .1, 2, 100):
        r, d = [-2, .5, 3, 1.7], [.2, .5, 2, 1.3]
        error = abs(dense_nll(r, d, tau) - analytic_nll(r, d, tau))
        assert error < 1e-10
        result['rankOneCovarianceIdentity'].append({'tau2': tau, 'absoluteDifference': error})
    result['balancedRemlReference'] = {'withinVariance': 4, 'betweenVariance': 1.5, 'repeatsPerEntity': 4}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
