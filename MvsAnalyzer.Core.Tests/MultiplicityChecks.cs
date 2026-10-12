using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

internal static class MultiplicityChecks
{
    internal static readonly (string Name, Action Run)[] All = {
        ("Internal multiplicity matches analytical vectors and tied ranks", Analytical),
        ("Internal multiplicity preserves unavailable full-family slots", Unavailable),
        ("Internal multiplicity is strict at adjacent floating-point boundaries", Boundaries),
        ("Internal multiplicity rejects malformed inputs", InvalidInputs),
        ("Internal multiplicity preserves inputs, order and permutation equivariance", Permutations),
        ("Internal multiplicity obeys bounds, monotonicity and rejection invariants", Invariants),
        ("Internal Bonferroni agrees with the unchanged shipped decision policy", LegacyAgreement)
    };

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }
    private static void Equal(double[] actual, double[] expected, double tolerance = 1e-15)
    {
        Check(actual.Length == expected.Length, "Vector length mismatch");
        for (int i = 0; i < actual.Length; i++)
            Check(double.IsNaN(expected[i]) ? double.IsNaN(actual[i]) :
                double.IsFinite(actual[i]) && Math.Abs(actual[i] - expected[i]) <= tolerance,
                $"Mismatch at {i}: {actual[i]:R} != {expected[i]:R}");
    }
    private static void Throws<T>(Action action) where T : ArgumentException
    {
        try { action(); } catch (T) { return; }
        throw new Exception($"Expected {typeof(T).Name}");
    }
    private static double[] Adjust(double[] p, MultiplicityMethod method) => Multiplicity.Adjust(p, p.Length, method);

    private static void Analytical()
    {
        double[] p = { .04, .01, .03, .002 };
        Equal(Adjust(p, MultiplicityMethod.Bonferroni), new[] { .16, .04, .12, .008 });
        Equal(Adjust(p, MultiplicityMethod.Holm), new[] { .06, .03, .06, .008 });
        Equal(Adjust(new[] { .01, .01, .02, .02 }, MultiplicityMethod.Holm), new[] { .04, .04, .04, .04 });
        Equal(Adjust(new[] { .3, .4, .9, 1.0 }, MultiplicityMethod.Holm), new[] { 1.0, 1.0, 1.0, 1.0 });
        foreach (var method in Enum.GetValues<MultiplicityMethod>())
        {
            Equal(Adjust(new[] { .012 }, method), new[] { .012 }, 0);
            Equal(Adjust(new[] { 0.0, 1.0 }, method), new[] { 0.0, 1.0 }, 0);
        }
        double[] multiple = { .01, .02, .9 };
        Check(Adjust(multiple, MultiplicityMethod.Holm)[1] < .05 &&
            Adjust(multiple, MultiplicityMethod.Bonferroni)[1] >= .05, "Holm should permit an extra member rejection");
    }

    private static void Unavailable()
    {
        double[] p = Enumerable.Repeat(double.NaN, 12).ToArray();
        foreach (var method in Enum.GetValues<MultiplicityMethod>()) Equal(Adjust(p, method), p);
        p[9] = .001; p[2] = .002;
        var expectedBonferroni = (double[])p.Clone(); expectedBonferroni[9] = .012; expectedBonferroni[2] = .024;
        var expectedHolm = (double[])p.Clone(); expectedHolm[9] = .012; expectedHolm[2] = .022;
        Equal(Adjust(p, MultiplicityMethod.Bonferroni), expectedBonferroni);
        Equal(Adjust(p, MultiplicityMethod.Holm), expectedHolm);
        Throws<ArgumentException>(() => Multiplicity.Adjust(new[] { .001, .002 }, 12, MultiplicityMethod.Holm));
        double[] full = { .001, .002, .003, .004, .005, .006, .007, .008, .009, .01, .011, .012 };
        Equal(Adjust(full, MultiplicityMethod.Holm), new[] { .012, .022, .030, .036, .040, .042, .042, .042, .042, .042, .042, .042 });
    }

    private static void Boundaries()
    {
        // A binary-exact alpha and threshold isolate strict inequality from decimal rounding.
        const double alpha = .0625, threshold = alpha / 4;
        foreach (var method in Enum.GetValues<MultiplicityMethod>())
        foreach (double raw in new[] { Math.BitDecrement(threshold), threshold, Math.BitIncrement(threshold) })
        {
            double adjusted = Adjust(new[] { raw, .5, .75, 1.0 }, method)[0];
            Check(Multiplicity.IsRejected(adjusted, alpha) == (raw < threshold), "Boundary rejection changed");
        }
        Check(Multiplicity.IsRejected(Math.BitDecrement(.05), .05), "Adjacent value below alpha must reject");
        Check(!Multiplicity.IsRejected(.05, .05) && !Multiplicity.IsRejected(Math.BitIncrement(.05), .05), "Alpha is strict");
        Check(!Multiplicity.IsRejected(double.NaN, .05), "Unavailable must never reject");
        foreach (var method in Enum.GetValues<MultiplicityMethod>())
        {
            Equal(Adjust(new[] { double.Epsilon }, method), new[] { double.Epsilon }, 0);
            Equal(Adjust(new[] { Math.BitDecrement(1.0), 1.0 }, method), new[] { 1.0, 1.0 }, 0);
        }
    }

    private static void InvalidInputs()
    {
        Throws<ArgumentNullException>(() => Multiplicity.Adjust(null!, 1, MultiplicityMethod.Holm));
        Throws<ArgumentException>(() => Multiplicity.Adjust(Array.Empty<double>(), 0, MultiplicityMethod.Holm));
        foreach (int count in new[] { -1, 0, 2 })
            Throws<ArgumentException>(() => Multiplicity.Adjust(new[] { .1 }, count, MultiplicityMethod.Holm));
        Throws<ArgumentOutOfRangeException>(() => Multiplicity.Adjust(new[] { .1 }, 1, (MultiplicityMethod)17));
        foreach (double bad in new[] { double.PositiveInfinity, double.NegativeInfinity, -double.Epsilon, Math.BitIncrement(1.0) })
        {
            foreach (var method in Enum.GetValues<MultiplicityMethod>())
                Throws<ArgumentOutOfRangeException>(() => Adjust(new[] { .1, bad }, method));
            Throws<ArgumentOutOfRangeException>(() => Multiplicity.IsRejected(bad, .05));
        }
        foreach (double alpha in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity, -1.0, 0.0, 1.0, 2.0 })
            Throws<ArgumentOutOfRangeException>(() => Multiplicity.IsRejected(.1, alpha));
    }

    private static void Permutations()
    {
        double[] original = { .03, double.NaN, .001, .03, 1.0, 0.0 };
        int[] order = { 5, 2, 0, 4, 1, 3 };
        foreach (var method in Enum.GetValues<MultiplicityMethod>())
        {
            double[] input = (double[])original.Clone();
            double[] result = Adjust(input, method);
            Check(!ReferenceEquals(input, result), "Adjustment must return a fresh vector");
            Equal(input, original, 0);
            Equal(Adjust(order.Select(i => input[i]).ToArray(), method), order.Select(i => result[i]).ToArray(), 0);
            result[0] = .99;
            Equal(input, original, 0);
        }
    }

    private static void Invariants()
    {
        // Deterministic fixed-grid families cover ties, zeros, unavailable values and saturation.
        double[] grid = { 0, .001, .01, .02, .05, .2, 1, double.NaN };
        for (int code = 0; code < 4096; code++)
        {
            int value = code;
            double[] p = new double[4];
            for (int i = 0; i < p.Length; i++) { p[i] = grid[value % grid.Length]; value /= grid.Length; }
            double[] b = Adjust(p, MultiplicityMethod.Bonferroni), h = Adjust(p, MultiplicityMethod.Holm);
            int[] order = Enumerable.Range(0, p.Length).Where(i => !double.IsNaN(p[i])).OrderBy(i => p[i]).ToArray();
            for (int rank = 0; rank < order.Length; rank++)
            {
                int i = order[rank];
                Check(p[i] <= h[i] && h[i] <= b[i] && b[i] <= 1, "Adjustment bounds failed");
                if (rank > 0) Check(h[order[rank - 1]] <= h[i], "Holm sorted values must be monotone");
                if (rank > 0 && p[order[rank - 1]] == p[i]) Check(h[order[rank - 1]] == h[i], "Ties must agree");
            }
            foreach (double alpha in new[] { .01, .05, .25, .99 })
            {
                Check(b.Any(x => Multiplicity.IsRejected(x, alpha)) == h.Any(x => Multiplicity.IsRejected(x, alpha)), "Any-rejection events must agree");
                for (int i = 0; i < p.Length; i++)
                    Check(!Multiplicity.IsRejected(b[i], alpha) || Multiplicity.IsRejected(h[i], alpha), "Holm lost a Bonferroni rejection");
            }
        }
    }

    private static void LegacyAgreement()
    {
        foreach (int m in new[] { 1, 2, 4, 12 })
        foreach (double p in new[] { 0, double.Epsilon, .001, .05 / m, Math.BitDecrement(.05 / m), Math.BitIncrement(.05 / m), .5, 1 })
        {
            double adjusted = Adjust(Enumerable.Repeat(p, m).ToArray(), MultiplicityMethod.Bonferroni)[0];
            Check(adjusted == DecisionPolicy.Adjust(p, m), "Valid Bonferroni differs from shipped policy");
            Check(Multiplicity.IsRejected(adjusted, .05) == DecisionPolicy.Reject(p, .05, m), "Strict rejection differs from shipped policy");
        }
        Check(AnalysisEngine.EngineVersion == "1.6.2" && AnalysisEngine.MetricKeys.Length == 12, "Comparator must not change the active engine or family");
    }

    internal static void Export(string fixturePath, string outputPath)
    {
        byte[] bytes = File.ReadAllBytes(fixturePath);
        using var fixture = JsonDocument.Parse(bytes);
        if (fixture.RootElement.GetProperty("schema").GetString() != "MVS-MULTIPLICITY-REFERENCE-1")
            throw new InvalidDataException("Unsupported multiplicity fixture schema.");
        if (fixture.RootElement.GetProperty("alpha").GetDouble() != .05)
            throw new InvalidDataException("Multiplicity diagnostic alpha must be 0.05.");
        var identifiers = new HashSet<string>(StringComparer.Ordinal);
        var results = new List<object>();
        foreach (var item in fixture.RootElement.GetProperty("cases").EnumerateArray())
        {
            string id = item.GetProperty("id").GetString() ?? throw new InvalidDataException("Missing case id.");
            if (string.IsNullOrWhiteSpace(id) || !identifiers.Add(id)) throw new InvalidDataException("Empty or duplicate multiplicity case id.");
            int familySize = item.GetProperty("family_size").GetInt32();
            double[] p = item.GetProperty("p_values").EnumerateArray()
                .Select(x => x.ValueKind == JsonValueKind.Null ? double.NaN : x.GetDouble()).ToArray();
            double[] b = Multiplicity.Adjust(p, familySize, MultiplicityMethod.Bonferroni);
            double[] h = Multiplicity.Adjust(p, familySize, MultiplicityMethod.Holm);
            double?[] ConvertValues(double[] values) => values.Select(x => double.IsNaN(x) ? (double?)null : x).ToArray();
            results.Add(new { id, bonferroni = ConvertValues(b), holm = ConvertValues(h),
                bonferroni_rejected = b.Select(x => Multiplicity.IsRejected(x, .05)).ToArray(),
                holm_rejected = h.Select(x => Multiplicity.IsRejected(x, .05)).ToArray() });
        }
        if (results.Count == 0) throw new InvalidDataException("Multiplicity fixtures must contain cases.");
        var output = new
        {
            schema = "MVS-MULTIPLICITY-NATIVE-1",
            fixtureSha256 = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
            engineVersion = AnalysisEngine.EngineVersion,
            activeMetricCount = AnalysisEngine.MetricKeys.Length,
            coreAssemblySha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(typeof(AnalysisEngine).Assembly.Location))).ToLowerInvariant(),
            nativeRuntime = Environment.Version.ToString(),
            results
        };
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outputPath))!);
        File.WriteAllText(outputPath, JsonSerializer.Serialize(output, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        Console.WriteLine($"Exported {results.Count} native multiplicity cases. Independent comparison is still required.");
    }
}
