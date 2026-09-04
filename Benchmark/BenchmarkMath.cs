namespace MvsAnalyzer.Benchmarking;

/// <summary>Small statistics helpers the benchmark needs and the analysis engine does not expose.</summary>
internal static class BenchmarkMath
{
    /// <summary>
    /// Kendall tau-b between two rankings. Used to ask whether MVS picks the same metric order
    /// when it only sees half of the entities. Ties are handled, because scores can be equal.
    /// </summary>
    public static double KendallTau(double[] a, double[] b)
    {
        if (a.Length != b.Length || a.Length < 2) return double.NaN;
        long concordant = 0;
        long discordant = 0;
        long tiedA = 0;
        long tiedB = 0;
        for (int i = 0; i < a.Length; i++)
            for (int j = i + 1; j < a.Length; j++)
            {
                double da = a[i] - a[j];
                double db = b[i] - b[j];
                if (!double.IsFinite(da) || !double.IsFinite(db)) return double.NaN;
                double product = da * db;
                if (da == 0 && db == 0) { tiedA++; tiedB++; continue; }
                if (da == 0) { tiedA++; continue; }
                if (db == 0) { tiedB++; continue; }
                if (product > 0) concordant++; else discordant++;
            }
        double pairs = concordant + discordant;
        double denominator = Math.Sqrt((pairs + tiedA) * (pairs + tiedB));
        if (denominator <= 0) return double.NaN;
        return (concordant - discordant) / denominator;
    }

    /// <summary>Standard error of a proportion. Reported next to every rate so small gaps are not over-read.</summary>
    public static double ProportionStandardError(double rate, int trials)
    {
        if (trials <= 0 || !double.IsFinite(rate)) return double.NaN;
        double clamped = Math.Clamp(rate, 0, 1);
        return Math.Sqrt(clamped * (1 - clamped) / trials);
    }

    /// <summary>Wilson interval, which stays inside [0, 1] even when a rate is zero.</summary>
    public static (double Low, double High) WilsonInterval(int successes, int trials, double z = 1.959963984540054)
    {
        if (trials <= 0) return (double.NaN, double.NaN);
        double n = trials;
        double p = successes / n;
        double denominator = 1 + z * z / n;
        double centre = (p + z * z / (2 * n)) / denominator;
        double spread = z * Math.Sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator;
        return (Math.Max(0, centre - spread), Math.Min(1, centre + spread));
    }

    public static double Median(double[] values)
    {
        double[] clean = values.Where(double.IsFinite).ToArray();
        if (clean.Length == 0) return double.NaN;
        Array.Sort(clean);
        int half = clean.Length / 2;
        return clean.Length % 2 == 1 ? clean[half] : (clean[half - 1] + clean[half]) / 2;
    }

    public static double Quantile(double[] values, double q)
    {
        double[] clean = values.Where(double.IsFinite).ToArray();
        if (clean.Length == 0) return double.NaN;
        Array.Sort(clean);
        if (clean.Length == 1) return clean[0];
        double position = Math.Clamp(q, 0, 1) * (clean.Length - 1);
        int low = (int)Math.Floor(position);
        int high = Math.Min(clean.Length - 1, low + 1);
        return clean[low] + (clean[high] - clean[low]) * (position - low);
    }
}
