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

    internal const string HuberImplementationId = "fixed-mad-huber-normalized-score-v2";
    internal const int HuberMaxIterations = 64;
    internal readonly record struct HuberResult(double Value, string Status, int Iterations);

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

    internal static string FamilyForTrack(string track) => SimulationScenarios.Canonicalize(track) switch
    {
        SimulationScenarios.Location => Location,
        SimulationScenarios.Decrease => Location,
        SimulationScenarios.Variability => Variability,
        // The heterogeneity generator perturbs entity centres, so location estimators are the
        // natural entity-level summaries. The final family-level inferential test is redesigned later.
        SimulationScenarios.Heterogeneity => Location,
        _ => throw new ArgumentException("Unknown calibration track: " + track, nameof(track))
    };

    internal static bool IsNaturalForTrack(string key, string track) =>
        Get(key).Family == FamilyForTrack(track);

    internal static bool IsApplicable(string key, double[] values) => UnavailabilityReason(key, values).Length == 0;

    /// <summary>Requirement failure only; a finite computed result is checked separately.</summary>
    internal static string UnavailabilityReason(string key, double[] values)
    {
        MetricDefinition definition = Get(key);
        if (values.Length < definition.MinMeasurements) return "too_few_measurements";
        if (values.Any(x => !double.IsFinite(x))) return "nonfinite_measurements";
        if (definition.MaxMeasurements is int max && values.Length > max) return "measurement_limit_exceeded";

        double tolerance = DenominatorTolerance(values);
        return definition.Requirement switch
        {
            "finite" => "",
            "positive" => values.All(x => x > 0) ? "" : "nonpositive_measurements",
            "nonzero_mean" => Math.Abs(values.Average()) > tolerance ? "" : "near_zero_mean",
            "nonzero_median" => Math.Abs(Quantile(values.OrderBy(x => x).ToArray(), .5)) > tolerance ? "" : "near_zero_median",
            "pairwise" => "",
            _ => throw new InvalidOperationException("Unknown metric applicability rule: " + definition.Requirement)
        };
    }

    internal static double Compute(string key, double[] values)
    {
        if (!IsApplicable(key, values)) return double.NaN;
        // The staged Huber solver owns its coordinates: shared Workspace arithmetic can
        // overflow on finite extreme inputs and must remain unchanged for active metrics.
        if (key == "huber_location") return HuberLocation(values).Value;
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

    /// <summary>
    /// Staged fixed-MAD Huber root. Power-of-two coordinates depend on robust distance,
    /// not input magnitude, so units, common offsets and remote outliers do not set the
    /// stopping rule. The bounded iteration override is internal for failure tests only.
    /// </summary>
    internal static HuberResult HuberLocation(double[] values, int maxIterations = HuberMaxIterations)
    {
        if (maxIterations < 1 || maxIterations > HuberMaxIterations)
            throw new ArgumentOutOfRangeException(nameof(maxIterations));
        if (values.Length < 2 || values.Any(x => !double.IsFinite(x)))
            return new(double.NaN, "invalid_input", 0);

        double[] sorted = values.OrderBy(x => x).ToArray();
        int middle = sorted.Length / 2;
        double anchor = sorted[middle]; // An input value, even for an even sample.
        double[] distances = sorted.Select(x => Math.Abs(x - anchor)).OrderBy(x => x).ToArray();
        double distance = distances[middle];
        // This is exactly a strict majority equal to the anchor, iff the exact sample
        // MAD is zero. A tiny positive MAD, including half a subnormal, is not zero.
        if (distance == 0) return new(anchor, "zero_mad_fallback", 0);
        int exponent = double.IsPositiveInfinity(distance) ? 1024 : Math.ILogB(distance);
        double[] normalized = sorted.Select(x => HuberNormalizedDifference(x, anchor, exponent)).ToArray();
        if (normalized.Any(double.IsNaN)) return new(double.NaN, "invalid_normalized_scale", 0);
        double center = HuberMedian(normalized);
        double mad = HuberMedian(normalized.Select(x => Math.Abs(x - center)).OrderBy(x => x).ToArray());
        double scale = MadNormalConsistency * mad;
        if (!double.IsFinite(center) || !double.IsFinite(scale) || scale <= 0)
            return new(double.NaN, "invalid_normalized_scale", 0);
        double[] residuals = normalized.Select(x => (x - center) / scale).ToArray();

        double low = -HuberC, high = HuberC;
        double lowScore = HuberScore(residuals, low), highScore = HuberScore(residuals, high);
        if (!double.IsFinite(lowScore) || !double.IsFinite(highScore))
            return new(double.NaN, "nonfinite_score", 0);
        if (lowScore < 0 || highScore > 0) return new(double.NaN, "invalid_bracket", 0);
        for (int iteration = 1; iteration <= maxIterations; iteration++)
        {
            double offset = low + (high - low) / 2;
            double score = HuberScore(residuals, offset);
            if (!double.IsFinite(score)) return new(double.NaN, "nonfinite_score", iteration);
            if (score == 0 || high - low <= 1e-13 || offset == low || offset == high)
            {
                double coordinate = center + scale * offset;
                if (!double.IsFinite(coordinate)) return new(double.NaN, "nonfinite_coordinate", iteration);
                // Only a converged root can be confined to its known data hull. This
                // does not turn a failed solve into a successful last iterate.
                coordinate = Math.Clamp(coordinate, normalized[0], normalized[^1]);
                double normalizedAnchor = Math.ScaleB(anchor, -exponent);
                double result = double.IsFinite(normalizedAnchor)
                    ? Math.ScaleB(normalizedAnchor + coordinate, exponent)
                    : anchor + Math.ScaleB(coordinate, exponent);
                if (double.IsNaN(result)) return new(double.NaN, "nonfinite_reconstruction", iteration);
                // Finite original bounds also repair outward final rounding to infinity.
                result = Math.Clamp(result, sorted[0], sorted[^1]);
                return new(result, "converged", iteration);
            }
            if (score > 0) low = offset;
            else high = offset;
        }
        return new(double.NaN, "iteration_limit", maxIterations);
    }

    private static double HuberNormalizedDifference(double value, double anchor, int exponent)
    {
        double difference = value - anchor;
        return double.IsFinite(difference)
            ? Math.ScaleB(difference, -exponent)
            : Math.ScaleB(value, -exponent) - Math.ScaleB(anchor, -exponent);
        // An enormous outlier may be a signed infinity in these coordinates; the
        // bounded score clips it. Original nonfinite inputs are rejected separately.
    }

    private static double HuberMedian(double[] sorted) => sorted.Length % 2 != 0
        ? sorted[sorted.Length / 2]
        : (sorted[sorted.Length / 2 - 1] + sorted[sorted.Length / 2]) / 2;

    private static double HuberScore(double[] sortedResiduals, double offset)
    {
        // Neumaier compensation retains small central terms across cancellation of
        // bounded tails. Input order is deterministic and each summand is bounded.
        double sum = 0, correction = 0;
        foreach (double residual in sortedResiduals)
        {
            double term = Math.Clamp(residual - offset, -HuberC, HuberC);
            double next = sum + term;
            correction += Math.Abs(sum) >= Math.Abs(term)
                ? (sum - next) + term
                : (term - next) + sum;
            sum = next;
        }
        return sum + correction;
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
