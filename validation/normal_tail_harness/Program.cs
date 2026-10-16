using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

namespace MvsNormalTailExperiment;

// Test-only friend assembly. No rank implementation or NormalCdf coefficients
// are copied here. BuildIdentity.g.cs is generated from verified source bytes.
internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private static readonly double[] ThroughputZ = { 0, .5, 1, 2, 3, 4, 6, 8, 10, 20, 30, 37, 38, 39, 40 };
    private static Func<double, double> primitive = null!;
    private static Func<double, double> tail = null!;

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0) throw new ArgumentException("Expected inspect, scalar INPUT, rank INPUT, policy INPUT, startup, or throughput.");
            // Startup measures only its fixed actual-MW work. Rank and policy
            // modes also call the unchanged friend APIs without tail binding.
            if (args[0] is "inspect" or "scalar" or "throughput") Bind();
            object result = args[0] switch
            {
                "inspect" when args.Length == 1 => new { schema = "mvs-normal-tail-inspection/v1", identity = Identity(), boundNormalCdf = true },
                "scalar" when args.Length == 2 => Scalar(args[1]),
                "rank" when args.Length == 2 => Rank(args[1]),
                "policy" when args.Length == 2 => Policy(args[1]),
                "startup" when args.Length == 1 => Startup(),
                "throughput" when args.Length == 1 => Throughput(),
                _ => throw new ArgumentException("Unknown mode or incorrect argument count.")
            };
            Console.WriteLine(JsonSerializer.Serialize(result, JsonOptions));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(JsonSerializer.Serialize(new { schema = "mvs-normal-tail-error/v1", experimental = true, variant = BuildIdentity.Variant, error = error.GetType().FullName, message = error.Message }));
            return 2;
        }
    }

    private static void Bind()
    {
        MethodInfo? cdf = typeof(AnalysisEngine).GetMethod("NormalCdf", BindingFlags.NonPublic | BindingFlags.Static, null, new[] { typeof(double) }, null);
        if (cdf is null || !cdf.IsPrivate || cdf.ReturnType != typeof(double) || cdf.IsGenericMethod)
            throw new MissingMethodException("Expected exact private static double AnalysisEngine.NormalCdf(double).");
        Func<double, double> normalCdf = cdf.CreateDelegate<Func<double, double>>();
#if EXPERIMENTAL_MATHNET
        if (BuildIdentity.Variant != "B") throw new InvalidDataException("Variant identity mismatch.");
        MethodInfo? erfc = typeof(MathNet.Numerics.SpecialFunctions).GetMethod("Erfc", BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(double) }, null);
        if (erfc is null || erfc.ReturnType != typeof(double) || erfc.IsGenericMethod) throw new MissingMethodException("Expected Math.NET Erfc(double).");
        primitive = erfc.CreateDelegate<Func<double, double>>();
#else
        if (BuildIdentity.Variant != "A") throw new InvalidDataException("Variant identity mismatch.");
        primitive = normalCdf;
#endif
        // Both variants invoke the same two delegate levels in the timed loop.
        tail = TailUnchecked;
    }

    private static double TailUnchecked(double z)
    {
#if EXPERIMENTAL_MATHNET
        return Math.Clamp(primitive(z / Math.Sqrt(2)), 0, 1);
#else
        return Math.Clamp(2 * (1 - primitive(z)), 0, 1);
#endif
    }

    private static object Scalar(string path)
    {
        using JsonDocument input = JsonDocument.Parse(File.ReadAllBytes(path));
        JsonElement root = input.RootElement;
        RequireSchema(root, "mvs-normal-tail-input/v1");
        var rows = new List<object>();
        int familySize = root.GetProperty("familySize").GetInt32();
        foreach (string collection in new[] { "points", "specials" })
        {
            foreach (JsonElement point in root.GetProperty(collection).EnumerateArray())
            {
                string zBits = point.GetProperty("zBits").GetString()!;
                double z = FromBits(zBits);
                string id = point.GetProperty("id").GetString()!;
                if (double.IsNaN(z) || z < 0)
                {
                    rows.Add(new { id, collection, z = Fp(z), status = "rejected_domain", candidateInvoked = false, input = point.Clone() });
                    continue;
                }
                double p = tail(z);
                var decisions = new List<object>();
                if (point.TryGetProperty("thresholds", out JsonElement thresholds))
                {
                    foreach (JsonElement threshold in thresholds.EnumerateArray())
                    {
                        string alphaBits = threshold.GetString()!;
                        double alpha = FromBits(alphaBits);
                        decisions.Add(new { alphaBits, familySize, adjustedP = Fp(DecisionPolicy.Adjust(p, familySize)), reject = DecisionPolicy.Reject(p, alpha, familySize) });
                    }
                }
                rows.Add(new { id, collection, z = Fp(z), status = "evaluated", candidateInvoked = true, p = Fp(p), decisions, input = point.Clone() });
            }
        }
        return new { schema = "mvs-normal-tail-scalar/v1", identity = Identity(), inputSha256 = Sha(path), rows };
    }

    private static object Rank(string path)
    {
        using JsonDocument input = JsonDocument.Parse(File.ReadAllBytes(path));
        JsonElement root = input.RootElement;
        RequireSchema(root, "mvs-normal-tail-input/v1");
        int familySize = root.GetProperty("familySize").GetInt32();
        string[] alphaBits = root.GetProperty("alphaBits").EnumerateArray().Select(x => x.GetString()!).ToArray();
        var rows = new List<object>();
        foreach (JsonElement item in root.GetProperty("rankCases").EnumerateArray())
        {
            double[][] groups = item.GetProperty("groupsBits").EnumerateArray().Select(g => g.EnumerateArray().Select(v => FromBits(v.GetString()!)).ToArray()).ToArray();
            if (groups.SelectMany(x => x).Any(x => !double.IsFinite(x))) throw new InvalidDataException("Rank input must be finite, including empty groups where specified.");
            string method = item.GetProperty("method").GetString()!;
            double p = method switch
            {
                "mann_whitney" when groups.Length == 2 => AnalysisEngine.MannWhitneyP(groups[0], groups[1]),
                "kruskal_wallis" => AnalysisEngine.KruskalWallisP(groups),
                _ => throw new InvalidDataException("Unsupported rank method or group count.")
            };
            object[] decisions = alphaBits.Select(bits => (object)new { alphaBits = bits, familySize, adjustedP = Fp(DecisionPolicy.Adjust(p, familySize)), reject = DecisionPolicy.Reject(p, FromBits(bits), familySize) }).ToArray();
            rows.Add(new { id = item.GetProperty("id").GetString(), method, p = Fp(p), decisions, nativeZStatus = "not_exposed_by_unchanged_api", input = item.Clone() });
        }
        return new { schema = "mvs-normal-tail-ranks/v1", identity = Identity(), inputSha256 = Sha(path), rows };
    }

    private static object Policy(string path)
    {
        using JsonDocument input = JsonDocument.Parse(File.ReadAllBytes(path));
        RequireSchema(input.RootElement, "mvs-normal-tail-policy-input/v1");
        var rows = new List<object>();
        foreach (JsonElement item in input.RootElement.GetProperty("cases").EnumerateArray())
        {
            double p = FromBits(item.GetProperty("rawPBits").GetString()!);
            double alpha = FromBits(item.GetProperty("alphaBits").GetString()!);
            int familySize = item.GetProperty("familySize").GetInt32();
            rows.Add(new { id = item.GetProperty("id").GetString(), rawP = Fp(p), alpha = Fp(alpha), familySize, adjustedP = Fp(DecisionPolicy.Adjust(p, familySize)), reject = DecisionPolicy.Reject(p, alpha, familySize), input = item.Clone() });
        }
        return new { schema = "mvs-normal-tail-policy/v1", identity = Identity(), inputSha256 = Sha(path), rows };
    }

    private static object Startup()
    {
        double[] a = Enumerable.Range(0, 8).Select(x => (double)x).ToArray();
        double[] b = Enumerable.Range(8, 8).Select(x => (double)x).ToArray();
        double p = AnalysisEngine.MannWhitneyP(a, b);
        // No assembly-file hashing or unrelated numerics in startup mode.
        return new { schema = "mvs-normal-tail-startup/v1", experimental = true, variant = BuildIdentity.Variant, sourceTreeSha256 = BuildIdentity.SourceTreeSha256, p = Fp(p), valid = double.IsFinite(p) && p >= 0 && p <= 1 };
    }

    private static object Throughput()
    {
        const int count = 100000;
        double warmupChecksum = 0;
        for (int i = 0; i < count; ++i) warmupChecksum += tail(ThroughputZ[i % ThroughputZ.Length]);
        double checksum = 0;
        long start = Stopwatch.GetTimestamp();
        for (int i = 0; i < count; ++i) checksum += tail(ThroughputZ[i % ThroughputZ.Length]);
        long ticks = Stopwatch.GetTimestamp() - start;
        GC.KeepAlive(checksum);
        GC.KeepAlive(warmupChecksum);
        return new { schema = "mvs-normal-tail-throughput/v1", identity = Identity(), warmupCalls = count, measuredCalls = count, elapsedTicks = ticks, stopwatchFrequency = Stopwatch.Frequency, elapsedSeconds = (double)ticks / Stopwatch.Frequency, checksum = Fp(checksum), warmupChecksum = Fp(warmupChecksum), zBits = ThroughputZ.Select(ToBits).ToArray() };
    }

    private static object Identity() => new
    {
        experimental = true,
        variant = BuildIdentity.Variant,
        scientificStatus = "NO-GO retained; isolated numerical primitive experiment only",
        sourceTreeSha256 = BuildIdentity.SourceTreeSha256,
        sourceAnalysisSha256 = BuildIdentity.SourceAnalysisSha256,
        variantAnalysisSha256 = BuildIdentity.VariantAnalysisSha256,
        programSourceSha256 = BuildIdentity.ProgramSourceSha256,
        buildManifestSha256 = BuildIdentity.BuildManifestSha256,
        engineVersion = AnalysisEngine.EngineVersion,
        formulaVersion = OutputExporter.FormulaVersion,
        formulaHash = OutputExporter.FormulaHash,
        decisionPolicy = DecisionPolicy.Id,
        runtime = RuntimeInformation.FrameworkDescription,
        architecture = RuntimeInformation.ProcessArchitecture.ToString(),
        coreDllSha256 = Sha(typeof(AnalysisEngine).Assembly.Location),
        harnessDllSha256 = Sha(typeof(Program).Assembly.Location),
#if EXPERIMENTAL_MATHNET
        mathNetVersion = typeof(MathNet.Numerics.SpecialFunctions).Assembly.GetName().Version?.ToString(),
        mathNetDllSha256 = Sha(typeof(MathNet.Numerics.SpecialFunctions).Assembly.Location),
#else
        mathNetVersion = (string?)null,
        mathNetDllSha256 = (string?)null,
#endif
        mathNetPackageSha256 = BuildIdentity.MathNetPackageSha256
    };

    private static void RequireSchema(JsonElement root, string expected)
    {
        if (root.GetProperty("schema").GetString() != expected) throw new InvalidDataException("Unexpected input schema.");
    }
    private static double FromBits(string bits)
    {
        if (bits.Length != 16 || !ulong.TryParse(bits, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out ulong value)) throw new InvalidDataException("Expected exactly 16 hexadecimal binary64 bits.");
        return BitConverter.UInt64BitsToDouble(value);
    }
    private static string ToBits(double value) => BitConverter.DoubleToUInt64Bits(value).ToString("x16", CultureInfo.InvariantCulture);
    private static object Fp(double value) => new { bits = ToBits(value), kind = double.IsNaN(value) ? "nan" : double.IsPositiveInfinity(value) ? "positive_infinity" : double.IsNegativeInfinity(value) ? "negative_infinity" : "finite", value = double.IsFinite(value) ? (double?)value : null, roundTrip = value.ToString("R", CultureInfo.InvariantCulture) };
    private static string Sha(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
}
