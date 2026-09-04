namespace MvsAnalyzer;

internal sealed record OptimizationResult(double[] Parameters, double Value, bool Converged, int Iterations, bool AtBoundary);

/// <summary>Deterministic bounded Nelder–Mead. Convergence is a numerical diagnostic, not proof of a global optimum.</summary>
internal static class NumericalMethods
{
    public static OptimizationResult Minimize(Func<double[], double> function, double[] start, double[] lower, double[] upper,
        int maximumIterations = 3000, double tolerance = 1e-8, CancellationToken token = default)
    {
        int n = start.Length;
        if (n == 0 || lower.Length != n || upper.Length != n || lower.Where((x, i) => !double.IsFinite(x) || !double.IsFinite(upper[i]) || upper[i] <= x).Any())
            throw new ArgumentException("Invalid optimization bounds.");
        double[] Clamp(double[] x) => x.Select((v, i) => Math.Clamp(v, lower[i], upper[i])).ToArray();
        double Evaluate(double[] x) { double f = function(x); return double.IsFinite(f) ? f : 1e100; }
        var points = new double[n + 1][]; var values = new double[n + 1];
        points[0] = Clamp(start);
        for (int i = 1; i <= n; i++) { points[i] = (double[])points[0].Clone(); double step = .08 * Math.Max(1, Math.Abs(start[i - 1])); points[i][i - 1] = points[0][i - 1] + step <= upper[i - 1] ? points[0][i - 1] + step : points[0][i - 1] - step; points[i] = Clamp(points[i]); }
        for (int i = 0; i <= n; i++) values[i] = Evaluate(points[i]);
        int iterations = 0; bool converged = false;
        for (; iterations < maximumIterations; iterations++)
        {
            token.ThrowIfCancellationRequested(); Array.Sort(values, points);
            double diameter = points.Skip(1).Max(p => p.Select((v, j) => Math.Abs(v - points[0][j])).Max());
            if (values[0] < 1e99 && Math.Abs(values[n] - values[0]) <= tolerance * (1 + Math.Abs(values[0])) && diameter < Math.Sqrt(tolerance) * 5)
            { converged = true; break; }
            var center = new double[n];
            for (int i = 0; i < n; i++) for (int j = 0; j < n; j++) center[j] += points[i][j] / n;
            double[] Trial(double factor) => Clamp(center.Select((v, j) => v + factor * (v - points[n][j])).ToArray());
            double[] reflected = Trial(1); double fr = Evaluate(reflected);
            if (fr < values[0])
            {
                double[] expanded = Trial(2); double fe = Evaluate(expanded);
                points[n] = fe < fr ? expanded : reflected; values[n] = Math.Min(fe, fr); continue;
            }
            if (fr < values[n - 1]) { points[n] = reflected; values[n] = fr; continue; }
            bool outside = fr < values[n]; double[] contracted = Trial(outside ? .5 : -.5); double fc = Evaluate(contracted);
            if (fc < (outside ? fr : values[n])) { points[n] = contracted; values[n] = fc; continue; }
            for (int i = 1; i <= n; i++) { points[i] = Clamp(points[i].Select((v, j) => points[0][j] + .5 * (v - points[0][j])).ToArray()); values[i] = Evaluate(points[i]); }
        }
        Array.Sort(values, points); double[] best = points[0];
        bool boundary = best.Where((v, i) => Math.Abs(v - lower[i]) < 1e-4 || Math.Abs(v - upper[i]) < 1e-4).Any();
        return new OptimizationResult(best, values[0], converged, iterations, boundary);
    }

    /// <summary>Gauss–Hermite nodes for expectation under a STANDARD normal, via Golub–Welsch/Jacobi rotations.</summary>
    public static (double[] Nodes, double[] Weights) NormalQuadrature(int count)
    {
        if (count < 3 || count > 61) throw new ArgumentOutOfRangeException(nameof(count));
        var a = new double[count, count]; var v = new double[count, count];
        for (int i = 0; i < count; i++) { v[i, i] = 1; if (i + 1 < count) a[i, i + 1] = a[i + 1, i] = Math.Sqrt(i + 1); }
        for (int iter = 0; iter < 100 * count * count; iter++)
        {
            int p = 0, q = 1; double largest = 0;
            for (int i = 0; i < count; i++) for (int j = i + 1; j < count; j++) if (Math.Abs(a[i, j]) > largest) { largest = Math.Abs(a[i, j]); p = i; q = j; }
            if (largest < 1e-14) break;
            double angle = .5 * Math.Atan2(2 * a[p, q], a[q, q] - a[p, p]); double c = Math.Cos(angle), s = Math.Sin(angle);
            double ap = a[p, p], aq = a[q, q], apq = a[p, q];
            a[p, p] = c * c * ap - 2 * s * c * apq + s * s * aq;
            a[q, q] = s * s * ap + 2 * s * c * apq + c * c * aq; a[p, q] = a[q, p] = 0;
            for (int k = 0; k < count; k++)
            {
                if (k != p && k != q) { double kp = a[k, p], kq = a[k, q]; a[k, p] = a[p, k] = c * kp - s * kq; a[k, q] = a[q, k] = s * kp + c * kq; }
                double vp = v[k, p], vq = v[k, q]; v[k, p] = c * vp - s * vq; v[k, q] = s * vp + c * vq;
            }
        }
        int[] order = Enumerable.Range(0, count).OrderBy(i => a[i, i]).ToArray();
        return (order.Select(i => a[i, i]).ToArray(), order.Select(i => v[0, i] * v[0, i]).ToArray());
    }

    /// <summary>Observed-information SEs on the optimization scale. Null means singular/non-positive information.</summary>
    public static double[]? StandardErrors(Func<double[], double> objective, double[] parameters)
    {
        int n = parameters.Length; var h = new double[n, n]; double f = objective(parameters);
        for (int i = 0; i < n; i++) for (int j = 0; j <= i; j++)
        {
            double hi = 1e-4 * Math.Max(1, Math.Abs(parameters[i])), hj = 1e-4 * Math.Max(1, Math.Abs(parameters[j]));
            if (i == j)
            { double[] a = (double[])parameters.Clone(), b = (double[])parameters.Clone(); a[i] += hi; b[i] -= hi; h[i, i] = (objective(a) - 2 * f + objective(b)) / (hi * hi); }
            else
            {
                double[] a = (double[])parameters.Clone(), b = (double[])parameters.Clone(), c = (double[])parameters.Clone(), d = (double[])parameters.Clone();
                a[i] += hi; a[j] += hj; b[i] += hi; b[j] -= hj; c[i] -= hi; c[j] += hj; d[i] -= hi; d[j] -= hj;
                h[i, j] = h[j, i] = (objective(a) - objective(b) - objective(c) + objective(d)) / (4 * hi * hj);
            }
        }
        var l = new double[n, n];
        for (int i = 0; i < n; i++) for (int j = 0; j <= i; j++)
        {
            double sum = h[i, j]; for (int k = 0; k < j; k++) sum -= l[i, k] * l[j, k];
            if (!double.IsFinite(sum) || (i == j && sum <= 1e-9)) return null;
            l[i, j] = i == j ? Math.Sqrt(sum) : sum / l[j, j];
        }
        var se = new double[n];
        for (int col = 0; col < n; col++)
        {
            var y = new double[n]; var x = new double[n];
            for (int i = 0; i < n; i++) { double b = i == col ? 1 : 0; for (int k = 0; k < i; k++) b -= l[i, k] * y[k]; y[i] = b / l[i, i]; }
            for (int i = n - 1; i >= 0; i--) { double b = y[i]; for (int k = i + 1; k < n; k++) b -= l[k, i] * x[k]; x[i] = b / l[i, i]; }
            if (!double.IsFinite(x[col]) || x[col] <= 0) return null; se[col] = Math.Sqrt(x[col]);
        }
        return se;
    }
}
