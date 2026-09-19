namespace MvsAnalyzer;

internal sealed record MetricDefinition(
    string Key,
    string DisplayName,
    string Family,
    string Requirement,
    string Interpretation,
    bool LegacyInference,
    int MinMeasurements = 2,
    int? MaxMeasurements = null,
    bool Relative = false);

/// <summary>
/// Structured metric metadata for the 1.5 development line.
///
/// The first twelve definitions are the frozen 1.4 inference registry. New 1.5 metrics are staged here
/// and independently testable, but are not added to calibration or multiplicity control until the later
/// inference milestones explicitly switch away from LegacyInference.
/// </summary>
internal static class MetricRegistry
{
    internal const string Location = "location";
    internal const string Variability = "variability";
    internal const string Magnitude = "magnitude";
    internal const int MaxExactPairwiseMeasurements = 2048;

    private const double HuberC = 1.345;
    private const double MadNormalConsistency = 1.482602218505602;
    private const double QnNormalConsistency = 2.219144465985076;

    internal static readonly MetricDefinition[] All =
    {
        new("median", "Median", Location, "finite", "Robust central location.", true),
        new("standard_deviation", "Standard deviation", Variability, "finite", "Sample standard deviation within an entity.", true),
        new("coefficient_of_variation", "Coefficient of variation", Variability, "nonzero_mean", "Sample SD divided by the absolute mean.", true, Relative: true),
        new("mad", "Median absolute deviation", Variability, "finite", "Median absolute deviation from the entity median; unscaled.", true),
        new("iqr", "Interquartile range", Variability, "finite", "Type-7 75th percentile minus 25th percentile.", true),
        new("normalized_mad", "Normalized MAD", Variability, "nonzero_median", "MAD divided by the absolute median.", true, Relative: true),
        new("normalized_iqr", "Normalized IQR", Variability, "nonzero_median", "IQR divided by the absolute median.", true, Relative: true),
        new("mean", "Arithmetic mean", Location, "finite", "Arithmetic central location.", true),
        new("rms", "Root mean square", Magnitude, "finite", "Root mean square magnitude; combines location and spread.", true),
        new("range", "Range", Variability, "finite", "Maximum minus minimum.", true),
        new("geometric_mean", "Geometric mean", Location, "positive", "Geometric central location for strictly positive measurements.", true),
        new("trimmed_mean_20", "20% trimmed mean", Location, "finite", "Arithmetic mean after trimming floor(0.2*n) values from each tail.", true),

        new("huber_location", "Huber M location", Location, "finite", "Huber M-estimate of location with c=1.345 and a fixed MAD scale.", false),
        new("hodges_lehmann", "Hodges-Lehmann location", Location, "pairwise", "Median of Walsh averages (x_i+x_j)/2 for i<=j.", false, MaxMeasurements: MaxExactPairwiseMeasurements),
        new("qn", "Qn robust scale", Variability, "pairwise", "Rousseeuw-Croux Qn scale with corrected normal-consistency and finite-sample correction.", false, MaxMeasurements: MaxExactPairwiseMeasurements),
        new("log_sd", "Log-scale SD", Variability, "positive", "Sample standard deviation of natural-log measurements; multiplicative variability.", false, Relative: true)
    };

    internal static readonly MetricDefinition[] LegacyInference = All.Where(m => m.LegacyInference).ToArray();
    internal static readonly string[] LegacyKeys = LegacyInference.Select(m => m.Key).ToArray();

    static MetricRegistry()
    {
        if (All.Select(m => m.Key).Distinct(StringComparer.Ordinal).Count() != All.Length)
            throw new InvalidOperationException("Metric registry contains duplicate keys.");
        if (LegacyInference.Length != 12)
            throw new InvalidOperationException("The frozen 1.4 inference registry must contain exactly twelve metrics during milestone 1.5-A.");
    }

    internal static MetricDefinition Get(string key) =>
        All.FirstOrDefault(m => m.Key.Equals(key, StringComparison.Ordinal))
        ?? throw new ArgumentException("Unknown metric: " + key, nameof(key));

    internal static bool IsApplicable(string key, double[] values)
    {
        MetricDefinition definition = Get(key);
        if (values.Length < definition.MinMeasurements || values.Any(x => !double.IsFinite(x))) return false;
        if (definition.MaxMeasurements is int max && values.Length > max) return false;

        double tolerance = DenominatorTolerance(values);
        return definition.Requirement switch
        {
            "finite" => true,
            "positive" => values.All(x => x > 0),
            "nonzero_mean" => Math.Abs(values.Average()) > tolerance,
            "nonzero_median" => Math.Abs(Quantile(values.OrderBy(x => x).ToArray(), .5)) > tolerance,
            "pairwise" => values.Length >= 2,
            _ => throw new InvalidOperationException("Unknown metric applicability rule: " + definition.Requirement)
        };
    }

    internal static double Compute(string key, double[] values)
    {
        if (!IsApplicable(key, values)) return double.NaN;
        var w = new Workspace(values);
        return key switch
        {
            "median" => w.Median,
            "standard_deviation" => w.Sd,
            "coefficient_of_variation" => w.Sd / Math.Abs(w.Mean),
            "mad" => w.Mad,
            "iqr" => w.Iqr,
            "normalized_mad" => w.Mad / Math.Abs(w.Median),
            "normalized_iqr" => w.Iqr / Math.Abs(w.Median),
            "mean" => w.Mean,
            "rms" => Math.Sqrt(values.Average(x => x * x)),
            "range" => w.Sorted[^1] - w.Sorted[0],
            "geometric_mean" => Math.Exp(values.Average(Math.Log)),
            "trimmed_mean_20" => TrimmedMean(w.Sorted),
            "huber_location" => HuberLocation(w),
            "hodges_lehmann" => HodgesLehmann(values),
            "qn" => Qn(values),
            "log_sd" => Math.Sqrt(ScientificMath.Variance(values.Select(x => Math.Log(x)).ToArray())),
            _ => throw new ArgumentException("Unknown metric: " + key, nameof(key))
        };
    }

    /// <summary>
    /// Computes the exact 1.4 metric vector, in the original index order. Keeping this separate from All
    /// prevents the staged 1.5 metrics from silently changing family size, adjusted p-values, saved states,
    /// or benchmark behavior before the multiplicity redesign is ready.
    /// </summary>
    internal static double[] ComputeLegacy(double[] values)
    {
        if (values.Length == 0) return Enumerable.Repeat(double.NaN, LegacyInference.Length).ToArray();
        var w = new Workspace(values);
        double cv = Math.Abs(w.Mean) <= w.DenominatorTolerance ? double.NaN : w.Sd / Math.Abs(w.Mean);
        double normalizedMad = Math.Abs(w.Median) <= w.DenominatorTolerance ? double.NaN : w.Mad / Math.Abs(w.Median);
        double normalizedIqr = Math.Abs(w.Median) <= w.DenominatorTolerance ? double.NaN : w.Iqr / Math.Abs(w.Median);
        double geometric = values.All(x => x > 0) ? Math.Exp(values.Average(Math.Log)) : double.NaN;

        return new[]
        {
            w.Median,
            w.Sd,
            cv,
            w.Mad,
            w.Iqr,
            normalizedMad,
            normalizedIqr,
            w.Mean,
            Math.Sqrt(values.Average(x => x * x)),
            w.Sorted[^1] - w.Sorted[0],
            geometric,
            TrimmedMean(w.Sorted)
        };
    }

    private sealed class Workspace
    {
        public Workspace(double[] values)
        {
            Values = values;
            Sorted = values.OrderBy(x => x).ToArray();
            Median = Quantile(Sorted, .5);
            Mean = values.Average();
            Sd = Math.Sqrt(ScientificMath.Variance(values));
            Mad = Quantile(values.Select(x => Math.Abs(x - Median)).OrderBy(x => x).ToArray(), .5);
            Iqr = Quantile(Sorted, .75) - Quantile(Sorted, .25);
            DenominatorTolerance = MetricRegistry.DenominatorTolerance(values);
        }

        public double[] Values { get; }
        public double[] Sorted { get; }
        public double Median { get; }
        public double Mean { get; }
        public double Sd { get; }
        public double Mad { get; }
        public double Iqr { get; }
        public double DenominatorTolerance { get; }
    }

    private static double DenominatorTolerance(double[] values) =>
        Math.Max(double.Epsilon, values.Max(x => Math.Abs(x)) * 1e-12);

    private static double Quantile(double[] sorted, double q)
    {
        double p = (sorted.Length - 1) * q;
        int lo = (int)Math.Floor(p), hi = (int)Math.Ceiling(p);
        return sorted[lo] + (sorted[hi] - sorted[lo]) * (p - lo);
    }

    private static double TrimmedMean(double[] sorted)
    {
        int trim = (int)Math.Floor(sorted.Length * .2);
        return sorted.Skip(trim).Take(sorted.Length - 2 * trim).Average();
    }

    private static double HuberLocation(Workspace w)
    {
        double scale = MadNormalConsistency * w.Mad;
        if (!double.IsFinite(scale) || scale <= w.DenominatorTolerance) return w.Median;

        double mu = w.Median;
        for (int iteration = 0; iteration < 100; iteration++)
        {
            double weighted = 0, weightSum = 0;
            foreach (double x in w.Values)
            {
                double residual = (x - mu) / scale;
                double abs = Math.Abs(residual);
                double weight = abs <= HuberC ? 1 : HuberC / abs;
                weighted += weight * x;
                weightSum += weight;
            }
            if (!(weightSum > 0) || !double.IsFinite(weighted)) return double.NaN;
            double next = weighted / weightSum;
            double tolerance = 1e-12 * Math.Max(1, Math.Max(Math.Abs(mu), scale));
            if (Math.Abs(next - mu) <= tolerance) return next;
            mu = next;
        }
        return mu;
    }

    private static double HodgesLehmann(double[] values)
    {
        int n = values.Length;
        int count = checked(n * (n + 1) / 2);
        var walsh = new double[count];
        int at = 0;
        for (int i = 0; i < n; i++)
            for (int j = i; j < n; j++)
                walsh[at++] = values[i] / 2 + values[j] / 2;
        Array.Sort(walsh);
        return Quantile(walsh, .5);
    }

    private static double Qn(double[] values)
    {
        int n = values.Length;
        int count = checked(n * (n - 1) / 2);
        var distances = new double[count];
        int at = 0;
        for (int i = 0; i < n; i++)
            for (int j = i + 1; j < n; j++)
                distances[at++] = Math.Abs(values[i] - values[j]);
        Array.Sort(distances);

        int h = n / 2 + 1;
        int k = checked(h * (h - 1) / 2); // 1-based order statistic
        double raw = distances[k - 1];
        return QnNormalConsistency * QnFiniteCorrection(n) * raw;
    }

    private static double QnFiniteCorrection(int n)
    {
        double[] small = { .399356, .99365, .51321, .84401, .61220, .85877, .66993, .87344, .72014, .88906, .75743 };
        if (n >= 2 && n <= 12) return small[n - 2];
        double d = n;
        double inverse = n % 2 == 1
            ? 1 + 1.60188 / d - 2.1284 / (d * d) - 5.172 / (d * d * d)
            : 1 + 3.67561 / d + 1.9654 / (d * d) + 6.987 / (d * d * d) - 77 / (d * d * d * d);
        return 1 / inverse;
    }
}
