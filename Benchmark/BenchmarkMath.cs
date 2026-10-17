using System.Text.Json;

namespace MvsAnalyzer.Benchmarking;

/// <summary>Small statistics helpers the benchmark needs and the analysis engine does not expose.</summary>
internal static class BenchmarkMath
{
    /// <summary>
    /// Kendall tau-b between two rankings. Used to ask whether MVS picks the same metric order
    /// when it only sees half of the entities. Ties are handled, because scores can be equal.
    /// </summary>
    public static double LegacyKendallTau(double[] a, double[] b)
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

    /// <summary>Tau-b for finite scores; joint ties are excluded from both tie counts.</summary>
    public static double KendallTau(double[] a, double[] b)
    {
        if (a.Length != b.Length || a.Length < 2 || a.Any(x => !double.IsFinite(x)) || b.Any(x => !double.IsFinite(x)))
            return double.NaN;
        long concordant = 0, discordant = 0, tiedA = 0, tiedB = 0;
        for (int i = 0; i < a.Length; i++)
            for (int j = i + 1; j < a.Length; j++)
            {
                // Compare operands directly: subtraction can overflow and products can underflow.
                int da = a[i].CompareTo(a[j]), db = b[i].CompareTo(b[j]);
                if (da == 0 && db == 0) continue;
                if (da == 0) { tiedA++; continue; }
                if (db == 0) { tiedB++; continue; }
                if (da == db) concordant++; else discordant++;
            }
        double pairs = concordant + discordant;
        double denominator = Math.Sqrt((pairs + tiedA) * (pairs + tiedB));
        return denominator > 0 ? (concordant - discordant) / denominator : double.NaN;
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

/// <summary>Benchmark-only identity boundary. Null markers remain historical, never upgraded.</summary>
internal static class BenchmarkStabilityMethod
{
    public const string CurrentId = "kendall-tau-b-v2";
    public const string LegacyId = "kendall-legacy-v1";
    public const string CurrentSpecification = "benchmark-stability-kendall-tau-b-v2: finite equal-length arrays with n>=2; direct operand comparisons; joint ties excluded; tau=(C-D)/sqrt((C+D+T_a_only)*(C+D+T_b_only)); zero denominator or nonfinite input is undefined; existing finite-tau summary denominator retained.";
    public const string CurrentHash = "408d7cf64a8910cd90a423d7f995eaf756d1f687310cb7f1ea0ecf362b619a4f";
    public const string LegacySpecification = "benchmark-stability-kendall-legacy-v1: historical subtract-and-multiply implementation; joint ties counted in both tie totals; nonfinite differences undefined; zero denominator undefined; retained only for unmarked historical checkpoints.";
    public const string LegacyHash = "39169e17ca56ce431c5695a955d0593efa9df5ad5b8a8da1308d85cb2db77a89";

    public static string ResolveId(string? marker) => marker switch
    {
        null => LegacyId,
        CurrentId => CurrentId,
        _ => throw new InvalidDataException("Unknown benchmark stability method: " + marker)
    };
    public static string SpecificationFor(string? marker) => ResolveId(marker) == CurrentId ? CurrentSpecification : LegacySpecification;
    public static string HashFor(string? marker) => ResolveId(marker) == CurrentId ? CurrentHash : LegacyHash;
    public static string ComparisonKey(string? marker) => BenchmarkProtocol.Hash + "/" + ResolveId(marker) + "/" + HashFor(marker);
    public static double Calculate(double[] a, double[] b, string? marker) => ResolveId(marker) == CurrentId
        ? BenchmarkMath.KendallTau(a, b) : BenchmarkMath.LegacyKendallTau(a, b);

    private static void Match(string? expected, string? actual)
    {
        if (ResolveId(expected) != ResolveId(actual))
            throw new InvalidDataException("Benchmark stability method provenance mismatch.");
    }
    public static void ValidateOutcome(BenchmarkOutcome outcome)
    {
        ResolveId(outcome.StabilityMethod);
        if (outcome.Stability is null) throw new InvalidDataException("Invalid benchmark stability summary.");
        if (outcome.Stability.ReplicationRecords is { } records)
            foreach (var record in records)
            {
                if (record is null) throw new InvalidDataException("Invalid benchmark stability record.");
                Match(outcome.StabilityMethod, record.StabilityMethod);
            }
    }
    public static void ValidateRequest(BackupRequest request)
    {
        if (request.Kind == "benchmark") ResolveId(request.BenchmarkStabilityMethod);
        else if (request.BenchmarkStabilityMethod is not null)
            throw new InvalidDataException("Benchmark stability identity is not valid for a nonbenchmark request.");
    }
    public static void ValidateBackup(BackupDocument document)
    {
        ValidateRequest(document.Request);
        if (document.Request.Kind != "benchmark") return;
        string? marker = document.Request.BenchmarkStabilityMethod;
        ResolveId(marker);
        foreach (var unit in document.Units)
            if (unit.Key.StartsWith("stability/", StringComparison.Ordinal))
            {
                var record = unit.Value.Deserialize<BenchmarkRunner.StabilityCheckpoint>(BackupSession.Json)
                    ?? throw new InvalidDataException("Invalid benchmark stability checkpoint.");
                Match(marker, record.StabilityMethod);
            }
        if (document.Units.TryGetValue("result", out var result))
        {
            var outcome = result.Deserialize<BenchmarkOutcome>(BackupSession.Json)
                ?? throw new InvalidDataException("Invalid benchmark result checkpoint.");
            Match(marker, outcome.StabilityMethod);
            ValidateOutcome(outcome);
        }
    }
}
