using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MvsAnalyzer;

internal static class ReleaseInfo
{
    public const string Version = "1.4.0";
    public const string EngineVersion = "1.6.0";
    public const int StateSchema = 2;
    public const string DevelopmentScope = "Consolidated 1.6/1.7/1.8 development; public release 1.4.0";
}

/// <summary>Finite JSON numbers or null; never emit bare NaN/Infinity or silently replace them by zero.</summary>
internal static class ScientificJson
{
    public static readonly JsonSerializerOptions Options = CreateOptions();
    private static JsonSerializerOptions CreateOptions()
    {
        var options = new JsonSerializerOptions { WriteIndented = true, PropertyNameCaseInsensitive = true };
        options.Converters.Add(new FiniteDoubleConverter());
        return options;
    }
    public static string Serialize<T>(T value) => JsonSerializer.Serialize(value, Options);
    public static T Read<T>(string path) => JsonSerializer.Deserialize<T>(File.ReadAllText(path), Options)
        ?? throw new InvalidDataException("Empty JSON document: " + path);
    public static void Write<T>(string path, T value) => AtomicText(path, Serialize(value));
    public static void AtomicText(string path, string text)
    {
        string full = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(full)!);
        string temporary = full + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temporary, text, new UTF8Encoding(false));
            File.Move(temporary, full, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    private sealed class FiniteDoubleConverter : JsonConverter<double>
    {
        public override bool HandleNull => true;
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
        {
            if (reader.TokenType == JsonTokenType.Null) return double.NaN;
            if (reader.TokenType == JsonTokenType.Number)
            { double number = reader.GetDouble(); if (!double.IsFinite(number)) throw new JsonException("Nonfinite JSON number."); return number; }
            // Legacy named literals can be read, but new documents always write null.
            if (reader.TokenType == JsonTokenType.String && reader.GetString() is string value &&
                (value == "NaN" || value == "Infinity" || value == "-Infinity"))
                return double.Parse(value, CultureInfo.InvariantCulture);
            throw new JsonException("Expected a finite number or null.");
        }
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        {
            if (double.IsFinite(value)) writer.WriteNumberValue(value); else writer.WriteNullValue();
        }
    }
}

internal sealed record ProcessingSnapshot(int MinValue, int MaxValue, int MinMeasurements, string ImportProfile,
    string ImportProfileHash, string AnalysisPolicy)
{
    public static ProcessingSnapshot From(AppSettings settings)
    {
        ImportProfile? profile = PluginAssets.Current.ImportProfiles.FirstOrDefault(p => p.Id.Equals(settings.ImportProfileId, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(settings.ImportProfileId) && profile == null)
            throw new InvalidDataException("The selected import profile is not installed: " + settings.ImportProfileId);
        return new(settings.MinValue, settings.MaxValue, settings.MinMeasurements, settings.ImportProfileId,
            profile == null ? "built-in-v2" : ScientificMath.Hash(ScientificJson.Serialize(profile)), DecisionPolicy.Id);
    }
    public void Apply(AppSettings settings)
    {
        settings.MinValue = MinValue; settings.MaxValue = MaxValue;
        settings.MinMeasurements = MinMeasurements; settings.ImportProfileId = ImportProfile;
        if (this != From(settings)) throw new InvalidDataException("The import profile or analysis policy differs from the saved calibration. Recalibrate.");
    }
}

internal static class SettingsContract
{
    public static void Validate(AppSettings settings)
    {
        if (settings.MaxValue <= settings.MinValue || settings.MinMeasurements < 2)
            throw new ArgumentException("Invalid processing limits or minimum measurement count.");
        ScientificMath.RequireFinite(settings.CalibrationEffect, "effect");
        if (settings.CalibrationEffect <= 1) throw new ArgumentException("Effect must exceed 1.");
        ScientificMath.RequireRange(settings.Alpha, 0, 1, "alpha", false);
        ScientificMath.RequireRange(settings.OutlierRate, 0, 1, "outlier rate");
        ScientificMath.RequireRange(settings.MissingRate, 0, 1, "missing rate");
        ScientificMath.RequireRange(settings.EquivalenceMargin, 0, 1, "equivalence margin", false);
        _ = SimulationScenarios.Canonicalize(settings.SimulationScenario);
    }
    public static string Fingerprint(AppSettings settings)
    {
        Validate(settings);
        return ScientificMath.Hash(ScientificJson.Serialize(new { processing = ProcessingSnapshot.From(settings),
            settings.CalibrationSeed, settings.CalibrationEffect, settings.SimulationScenario, settings.OutlierRate,
            settings.MissingRate, settings.Alpha, settings.EquivalenceMargin, settings.SplitCalibration,
            engine = ReleaseInfo.EngineVersion, formula = OutputExporter.FormulaHash }));
    }
}

internal static class DecisionPolicy
{
    public const string Id = "all-metrics-bonferroni-v1";
    // All metrics are corrected, including metrics not selected by calibration. Thus selecting a
    // candidate on the same data cannot buy an additional uncorrected rejection opportunity.
    public static double Adjust(double p, int familySize) => double.IsFinite(p) ? Math.Min(1, Math.Max(0, p) * Math.Max(1, familySize)) : double.NaN;
    public static bool Reject(double rawP, double alpha, int familySize) => double.IsFinite(rawP) && Adjust(rawP, familySize) < alpha;
    public static double FprLimit(double alpha) => Math.Min(1, Math.Max(1.5 * alpha, alpha + .02));
}

internal static class ScientificMath
{
    public static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    public static int Seed(int seed, string scope, int index = 0, int sub = 0)
    {
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(seed.ToString(CultureInfo.InvariantCulture) + ":" + scope + ":" + index.ToString(CultureInfo.InvariantCulture) + ":" + sub.ToString(CultureInfo.InvariantCulture)));
        return System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(hash);
    }
    public static void RequireFinite(double x, string name) { if (!double.IsFinite(x)) throw new ArgumentException(name + " must be finite."); }
    public static void RequireRange(double x, double min, double max, string name, bool inclusive = true)
    {
        RequireFinite(x, name);
        if (inclusive ? x < min || x > max : x <= min || x >= max) throw new ArgumentException(name + " is outside its allowed range.");
    }
    public static double Gaussian(Random random) => Math.Sqrt(-2 * Math.Log(Math.Max(random.NextDouble(), 1e-15))) * Math.Cos(2 * Math.PI * random.NextDouble());
    public static double Quantile(IEnumerable<double> values, double q)
    {
        double[] sorted = values.Where(double.IsFinite).OrderBy(v => v).ToArray();
        if (sorted.Length == 0) return double.NaN;
        double p = Math.Clamp(q, 0, 1) * (sorted.Length - 1); int lo = (int)p, hi = (int)Math.Ceiling(p);
        return sorted[lo] + (sorted[hi] - sorted[lo]) * (p - lo);
    }
    public static double Variance(double[] values)
    {
        if (values.Length < 2) return double.NaN;
        double mean = values.Average(); return values.Sum(x => (x - mean) * (x - mean)) / (values.Length - 1);
    }
    public static double Mcse(double p, int n) => n > 0 && double.IsFinite(p) ? Math.Sqrt(Math.Max(0, p * (1 - p)) / n) : double.NaN;
    public static (double Low, double High) Wilson(int successes, int n)
    {
        if (n <= 0) return (double.NaN, double.NaN);
        const double z = 1.959963984540054;
        double p = successes / (double)n, den = 1 + z * z / n;
        double center = (p + z * z / (2 * n)) / den;
        double radius = z * Math.Sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / den;
        return (Math.Max(0, center - radius), Math.Min(1, center + radius));
    }
    public static double LogSumExp(double[] values)
    {
        double max = values.Max();
        if (!double.IsFinite(max)) return max;
        return max + Math.Log(values.Sum(x => Math.Exp(x - max)));
    }
}
