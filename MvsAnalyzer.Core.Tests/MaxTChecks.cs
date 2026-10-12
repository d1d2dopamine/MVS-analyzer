using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

internal static class MaxTChecks
{
    internal static readonly (string Name, Action Run)[] All = {
        ("Internal maxT matches hand-counted row maxima", Analytical),
        ("Internal maxT handles negative and extreme finite scores", NegativeAndExtremeScores),
        ("Internal maxT includes exact ties without a tolerance", ExactTies),
        ("Internal maxT retains duplicate and identity-like Monte Carlo draws", DuplicateDraws),
        ("Internal maxT has plus-one resolution and strict alpha decisions", ResolutionAndBoundary),
        ("Internal maxT respects hypothesis and resample permutations", Permutations),
        ("Internal maxT respects common positive affine score transforms", CommonAffineTransform),
        ("Internal maxT handles duplicate and enlarged complete families", FamilyEnlargement),
        ("Internal maxT preserves input bits and returns independent arrays", Immutability),
        ("Internal maxT rejects null, empty and incomplete families", InvalidShapes),
        ("Internal maxT rejects every nonfinite observed or resampled slot", NonfiniteScores),
        ("Internal maxT failure preserves the entire input", FailurePreservesInput),
        ("Internal maxT preserves bounds and score ordering", BoundsAndOrder),
        ("Internal maxT exporter binds hand-counted results and provenance", ExportContract),
        ("Internal maxT exporter rejects malformed fixtures without output writes", ExportFailures),
        ("Internal maxT remains separate from shipped inference", InactiveContract)
    };

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void Equal<T>(T[] actual, T[] expected)
    {
        Check(actual.SequenceEqual(expected), $"Vector mismatch: [{string.Join(", ", actual)}] != [{string.Join(", ", expected)}]");
    }

    private static void Throws<T>(Action action) where T : Exception
    {
        try { action(); } catch (T) { return; }
        throw new Exception($"Expected {typeof(T).Name}");
    }

    private static MaxTResult Adjust(double[] observed, double[][] resamples) =>
        MaxT.MonteCarloSingleStep(observed, resamples, observed.Length);

    private static double[][] Rows(params double[] scores) => scores.Select(x => new[] { x }).ToArray();

    private static void Analytical()
    {
        // Maxima are 4, 2, 1 and 5, supplied by different family members.
        double[] observed = { 4, 2, 6, 4 };
        double[][] draws = { new double[] { 1, 2, 3, 4 }, new double[] { 0, 1, 2, 1 },
            new double[] { -2, -1, 0, 1 }, new double[] { 5, 3, 1, 2 } };
        MaxTResult result = Adjust(observed, draws);
        Check(result.FamilySize == 4 && result.ResampleCount == 4, "Declared dimensions were lost");
        Equal(result.ExceedanceCounts, new[] { 2, 3, 0, 2 });
        Equal(result.AdjustedPValues, new[] { .6, .8, .2, .6 });
        MaxTResult singleton = Adjust(new[] { 2.0 }, Rows(1, 2, 3));
        Equal(singleton.ExceedanceCounts, new[] { 2 });
        Equal(singleton.AdjustedPValues, new[] { .75 });
    }

    private static void NegativeAndExtremeScores()
    {
        // A maximum initialized at zero would incorrectly count every negative score.
        var negative = Adjust(new double[] { -2, -4, -9 }, new[] {
            new double[] { -8, -7, -6 }, new double[] { -3, -5, -4 }, new double[] { -2, -3, -10 } });
        Equal(negative.ExceedanceCounts, new[] { 1, 2, 3 });
        Equal(negative.AdjustedPValues, new[] { .5, .75, 1.0 });
        var extreme = Adjust(new[] { double.MinValue, 0.0, double.MaxValue }, new[] {
            new[] { double.MinValue, double.MinValue, double.MinValue },
            new[] { double.MaxValue, double.MinValue, 0.0 } });
        Equal(extreme.ExceedanceCounts, new[] { 2, 1, 1 });
        Equal(extreme.AdjustedPValues, new[] { 1.0, 2.0 / 3, 2.0 / 3 });
    }

    private static void ExactTies()
    {
        var adjacent = Adjust(new[] { Math.BitDecrement(1.0), 1.0, Math.BitIncrement(1.0) },
            new[] { new[] { 1.0, 0.0, 0.0 } });
        Equal(adjacent.ExceedanceCounts, new[] { 1, 1, 0 });
        Equal(adjacent.AdjustedPValues, new[] { 1.0, 1.0, .5 });
        var zero = Adjust(new[] { -0.0, 0.0, double.Epsilon },
            new[] { new[] { -0.0, -double.Epsilon, -double.Epsilon } });
        Equal(zero.ExceedanceCounts, new[] { 1, 1, 0 });
        var tied = Adjust(new[] { -7.0, -7.0 }, Enumerable.Range(0, 7).Select(_ => new[] { -7.0, -7.0 }).ToArray());
        Equal(tied.ExceedanceCounts, new[] { 7, 7 });
        Equal(tied.AdjustedPValues, new[] { 1.0, 1.0 });
    }

    private static void DuplicateDraws()
    {
        // Draws equal to the observed score vector remain ordinary counted draws.
        var result = Adjust(new[] { 3.0, 1.0 }, new[] {
            new[] { 2.0, 0.0 }, new[] { 3.0, 1.0 }, new[] { 3.0, 1.0 } });
        Check(result.ResampleCount == 3, "Duplicate or identity-like draws were removed");
        Equal(result.ExceedanceCounts, new[] { 2, 3 });
        Equal(result.AdjustedPValues, new[] { .75, 1.0 });
    }

    private static void ResolutionAndBoundary()
    {
        foreach (int count in new[] { 1, 2, 19, 20, 99 })
        {
            var result = Adjust(new[] { 1.0 }, Rows(Enumerable.Repeat(0.0, count).ToArray()));
            Equal(result.ExceedanceCounts, new[] { 0 });
            Equal(result.AdjustedPValues, new[] { 1.0 / (count + 1.0) });
            Check(result.AdjustedPValues[0] > 0, "A Monte Carlo adjusted p-value became zero");
            Check(Multiplicity.IsRejected(result.AdjustedPValues[0], .05) == (count >= 20), "Strict 0.05 boundary changed");
        }
        double boundary = Adjust(new[] { 1.0 }, Rows(Enumerable.Repeat(0.0, 15).ToArray())).AdjustedPValues[0];
        Check(boundary == .0625 && !Multiplicity.IsRejected(boundary, .0625), "Exact binary alpha must not reject");
        Check(Multiplicity.IsRejected(boundary, Math.BitIncrement(.0625)), "Value below alpha must reject");
        Check(!Multiplicity.IsRejected(boundary, Math.BitDecrement(.0625)), "Value above alpha must not reject");
    }

    private static void Permutations()
    {
        double[] observed = { 4, -2, 6, 4 };
        double[][] draws = { new double[] { 1, 2, 3, 4 }, new double[] { 0, 1, 2, 1 },
            new double[] { -2, -1, 0, 1 }, new double[] { 5, 3, 1, 2 } };
        int[] order = { 2, 0, 3, 1 };
        var result = Adjust(observed, draws);
        var permuted = Adjust(order.Select(i => observed[i]).ToArray(),
            draws.Reverse().Select(row => order.Select(i => row[i]).ToArray()).ToArray());
        Equal(permuted.ExceedanceCounts, order.Select(i => result.ExceedanceCounts[i]).ToArray());
        Equal(permuted.AdjustedPValues, order.Select(i => result.AdjustedPValues[i]).ToArray());
        Equal(Adjust(observed, draws.Reverse().ToArray()).AdjustedPValues, result.AdjustedPValues);
    }

    private static void CommonAffineTransform()
    {
        // Exact small binary values isolate the invariant from rounding-induced ties.
        double[] observed = { 1, -2, 3, 1 };
        double[][] draws = { new double[] { -3, -2, -1, -4 }, new double[] { 0, 1, 1, -1 },
            new double[] { 2, 0, -3, 1 } };
        var expected = Adjust(observed, draws);
        foreach ((double scale, double offset) in new[] { (2.0, -32.0), (.5, 8.0), (4.0, 0.0) })
        {
            double Transform(double x) => scale * x + offset;
            var transformed = Adjust(observed.Select(Transform).ToArray(), draws.Select(row => row.Select(Transform).ToArray()).ToArray());
            Equal(transformed.ExceedanceCounts, expected.ExceedanceCounts);
            Equal(transformed.AdjustedPValues, expected.AdjustedPValues);
        }
    }

    private static void Immutability()
    {
        double[] observed = { -0.0, 3, -4 };
        double[][] draws = { new double[] { 1, -0.0, -1 }, new double[] { -2, 3, -4 } };
        long[] originalObserved = observed.Select(BitConverter.DoubleToInt64Bits).ToArray();
        long[][] originalDraws = draws.Select(row => row.Select(BitConverter.DoubleToInt64Bits).ToArray()).ToArray();
        double[][] originalRows = (double[][])draws.Clone();
        var first = Adjust(observed, draws);
        var second = Adjust(observed, draws);
        Check(!ReferenceEquals(first.ExceedanceCounts, second.ExceedanceCounts) &&
            !ReferenceEquals(first.AdjustedPValues, second.AdjustedPValues), "Calls share output arrays");
        Check(!ReferenceEquals(first.AdjustedPValues, observed) && draws.All(row => !ReferenceEquals(first.AdjustedPValues, row)),
            "Returned values alias an input");
        first.ExceedanceCounts[0] = -123;
        first.AdjustedPValues[0] = -.25;
        Equal(second.ExceedanceCounts, new[] { 2, 1, 2 });
        Equal(second.AdjustedPValues, new[] { 1.0, 2.0 / 3, 1.0 });
        Equal(observed.Select(BitConverter.DoubleToInt64Bits).ToArray(), originalObserved);
        for (int i = 0; i < draws.Length; i++)
        {
            Check(ReferenceEquals(draws[i], originalRows[i]), "An input row was replaced");
            Equal(draws[i].Select(BitConverter.DoubleToInt64Bits).ToArray(), originalDraws[i]);
        }
    }

    private static void FamilyEnlargement()
    {
        double[] observed = { 3, 5 };
        double[][] draws = { new double[] { 1, 2 }, new double[] { 4, 0 }, new double[] { -1, -2 } };
        var original = Adjust(observed, draws);
        Equal(original.ExceedanceCounts, new[] { 1, 0 });
        Equal(original.AdjustedPValues, new[] { .5, .25 });
        var duplicate = Adjust(new double[] { 3, 5, 3 }, draws.Select(row => new[] { row[0], row[1], row[0] }).ToArray());
        Equal(duplicate.ExceedanceCounts, new[] { 1, 0, 1 });
        Equal(duplicate.AdjustedPValues, new[] { .5, .25, .5 });
        var enlarged = Adjust(new double[] { 3, 5, 7 }, new[] {
            new double[] { 1, 2, 6 }, new double[] { 4, 0, -1 }, new double[] { -1, -2, 3 } });
        Equal(enlarged.ExceedanceCounts, new[] { 3, 1, 0 });
        Equal(enlarged.AdjustedPValues, new[] { 1.0, .5, .25 });
        for (int i = 0; i < original.FamilySize; i++)
            Check(enlarged.AdjustedPValues[i] >= original.AdjustedPValues[i], "Adding a complete score column lowered an existing adjusted p");
    }

    private static void InvalidShapes()
    {
        Throws<ArgumentNullException>(() => MaxT.MonteCarloSingleStep(null!, Rows(1), 1));
        Throws<ArgumentNullException>(() => MaxT.MonteCarloSingleStep(new[] { 1.0 }, null!, 1));
        Throws<ArgumentException>(() => MaxT.MonteCarloSingleStep(Array.Empty<double>(), new[] { Array.Empty<double>() }, 0));
        foreach (int familySize in new[] { -1, 0, 2, int.MaxValue })
            Throws<ArgumentException>(() => MaxT.MonteCarloSingleStep(new[] { 1.0 }, Rows(1), familySize));
        Throws<ArgumentException>(() => Adjust(new[] { 1.0 }, Array.Empty<double[]>()));
        foreach (double[] invalid in new[] { null!, Array.Empty<double>(), new[] { 1.0 }, new[] { 1.0, 2.0, 3.0 } })
        foreach (int position in new[] { 0, 1 })
        {
            double[][] draws = { new[] { 1.0, 2.0 }, new[] { 1.0, 2.0 } };
            draws[position] = invalid;
            Throws<ArgumentException>(() => Adjust(new[] { 1.0, 2.0 }, draws));
        }
    }

    private static void NonfiniteScores()
    {
        foreach (double invalid in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity })
        for (int column = 0; column < 3; column++)
        {
            double[] observed = { 1, 2, 3 };
            observed[column] = invalid;
            Throws<ArgumentOutOfRangeException>(() => Adjust(observed, new[] { new double[] { 1, 2, 3 } }));
            for (int row = 0; row < 2; row++)
            {
                double[][] draws = { new double[] { 1, 2, 3 }, new double[] { 4, 5, 6 } };
                draws[row][column] = invalid;
                Throws<ArgumentOutOfRangeException>(() => Adjust(new double[] { 1, 2, 3 }, draws));
            }
        }
    }

    private static void FailurePreservesInput()
    {
        double[] observed = { -0.0, 2 };
        double[][] draws = { new double[] { -3, -0.0 }, new[] { 4.0, double.NaN } };
        long[] beforeObserved = observed.Select(BitConverter.DoubleToInt64Bits).ToArray();
        long[][] beforeDraws = draws.Select(row => row.Select(BitConverter.DoubleToInt64Bits).ToArray()).ToArray();
        Throws<ArgumentOutOfRangeException>(() => Adjust(observed, draws));
        Equal(observed.Select(BitConverter.DoubleToInt64Bits).ToArray(), beforeObserved);
        for (int i = 0; i < draws.Length; i++)
            Equal(draws[i].Select(BitConverter.DoubleToInt64Bits).ToArray(), beforeDraws[i]);
    }

    private static void BoundsAndOrder()
    {
        // Hand maxima -3, -1, -1, 2 cover equal observations and every count boundary.
        double[] observed = { -4, -3, -2, -1, -1, 0, 2, 3 };
        double[][] draws = { Enumerable.Repeat(-3.0, 8).ToArray(), Enumerable.Repeat(-1.0, 8).ToArray(),
            Enumerable.Repeat(-1.0, 8).ToArray(), Enumerable.Repeat(2.0, 8).ToArray() };
        var result = Adjust(observed, draws);
        Equal(result.ExceedanceCounts, new[] { 4, 4, 3, 3, 3, 1, 1, 0 });
        Equal(result.AdjustedPValues, new[] { 1.0, 1.0, .8, .8, .8, .4, .4, .2 });
        Check(result.AdjustedPValues.All(p => p >= .2 && p <= 1), "Plus-one bounds failed");
        for (int i = 1; i < observed.Length; i++)
            Check(result.AdjustedPValues[i] <= result.AdjustedPValues[i - 1], "Larger observed score increased adjusted p");
    }

    private const string ValidFixture = """
        {"schemaVersion":"MVS-MAXT-FIXTURES-1","alpha":0.05,"cases":[
          {"id":"hand-counted","family_size":2,"observed":[2,4],"resamples":[[1,0],[2,3],[4,0]],"extra":"ignored"}
        ]}
        """;

    private static void ExportContract()
    {
        WithTemporaryDirectory(directory =>
        {
            string fixture = Path.Combine(directory, "fixture.json"), output = Path.Combine(directory, "out", "native.json");
            File.WriteAllText(fixture, ValidFixture);
            byte[] original = File.ReadAllBytes(fixture);
            Export(fixture, output);
            Equal(File.ReadAllBytes(fixture), original);
            using var document = JsonDocument.Parse(File.ReadAllBytes(output));
            JsonElement root = document.RootElement;
            Check(root.GetProperty("schemaVersion").GetString() == "MVS-MAXT-NATIVE-1", "Wrong native schema");
            Check(root.GetProperty("fixtureSha256").GetString() == Hash(original), "Fixture byte identity lost");
            Check(root.GetProperty("coreAssemblySha256").GetString() == Hash(File.ReadAllBytes(typeof(AnalysisEngine).Assembly.Location)), "Core assembly identity lost");
            Check(root.GetProperty("engineVersion").GetString() == "1.6.2" && root.GetProperty("activeMetricCount").GetInt32() == 12, "Active identity changed");
            Check(root.GetProperty("nativeRuntime").GetString() == Environment.Version.ToString(), "Runtime identity lost");
            JsonElement[] results = root.GetProperty("results").EnumerateArray().ToArray();
            Check(results.Length == 1 && results[0].GetProperty("id").GetString() == "hand-counted", "Case identity changed");
            Check(results[0].GetProperty("family_size").GetInt32() == 2 && results[0].GetProperty("resample_count").GetInt32() == 3, "Case dimensions changed");
            Equal(results[0].GetProperty("exceedance_counts").EnumerateArray().Select(x => x.GetInt32()).ToArray(), new[] { 2, 1 });
            Equal(results[0].GetProperty("adjusted_p").EnumerateArray().Select(x => x.GetDouble()).ToArray(), new[] { .75, .5 });
            Equal(results[0].GetProperty("rejected").EnumerateArray().Select(x => x.GetBoolean()).ToArray(), new[] { false, false });
        });
    }

    private static void ExportFailures()
    {
        WithTemporaryDirectory(directory =>
        {
            string fixture = Path.Combine(directory, "fixture.json"), output = Path.Combine(directory, "native.json");
            foreach (string invalid in new[] {
                ValidFixture.Replace("MVS-MAXT-FIXTURES-1", "unknown"),
                ValidFixture.Replace("0.05", "0.10"),
                ValidFixture.Replace("hand-counted", " "),
                "{\"schemaVersion\":\"MVS-MAXT-FIXTURES-1\",\"alpha\":0.05,\"cases\":[]}",
                "{\"schemaVersion\":\"MVS-MAXT-FIXTURES-1\",\"alpha\":0.05,\"cases\":[{\"id\":\"same\",\"family_size\":1,\"observed\":[1],\"resamples\":[[1]]},{\"id\":\"same\",\"family_size\":1,\"observed\":[1],\"resamples\":[[1]]}]}"
            })
            {
                File.WriteAllText(fixture, invalid);
                Throws<InvalidDataException>(() => Export(fixture, output));
                Check(!File.Exists(output), "An invalid fixture produced output");
                Check(File.ReadAllText(fixture) == invalid, "An invalid fixture changed input");
            }
            string ragged = ValidFixture.Replace("[4,0]", "[4]");
            File.WriteAllText(fixture, ragged);
            Throws<ArgumentException>(() => Export(fixture, output));
            Check(!File.Exists(output), "A failed row produced output");
            File.WriteAllText(fixture, ValidFixture);
            Throws<ArgumentException>(() => Export(fixture, Path.Combine(directory, ".", "fixture.json")));
            Check(File.ReadAllText(fixture) == ValidFixture, "Exporter overwrote its fixture");
            File.WriteAllText(output, "preserve-existing-output");
            Throws<IOException>(() => Export(fixture, output));
            Check(File.ReadAllText(output) == "preserve-existing-output", "Exporter overwrote existing evidence");
        });
    }

    private static void InactiveContract()
    {
        Check(AnalysisEngine.EngineVersion == "1.6.2" && AnalysisEngine.MetricKeys.Length == 12, "Internal maxT changed the active engine or family");
        Equal(Enum.GetNames<MultiplicityMethod>(), new[] { "Bonferroni", "Holm" });
        Check(DecisionPolicy.Adjust(.001, 12) == .012, "Shipped Bonferroni arithmetic changed");
    }

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static void WithTemporaryDirectory(Action<string> action)
    {
        string directory = Path.Combine(Path.GetTempPath(), "mvs-maxt-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try { action(directory); }
        finally { Directory.Delete(directory, true); }
    }

    internal static void Export(string fixturePath, string outputPath)
    {
        if (string.Equals(Path.GetFullPath(fixturePath), Path.GetFullPath(outputPath),
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
            throw new ArgumentException("Diagnostic output must not overwrite the input fixture.", nameof(outputPath));
        if (File.Exists(outputPath) || Directory.Exists(outputPath))
            throw new IOException("Diagnostic output already exists; choose a new evidence path.");
        byte[] bytes = File.ReadAllBytes(fixturePath);
        using var fixture = JsonDocument.Parse(bytes);
        if (fixture.RootElement.GetProperty("schemaVersion").GetString() != "MVS-MAXT-FIXTURES-1")
            throw new InvalidDataException("Unsupported maxT fixture schema.");
        if (fixture.RootElement.GetProperty("alpha").GetDouble() != .05)
            throw new InvalidDataException("maxT diagnostic alpha must be 0.05.");
        var identifiers = new HashSet<string>(StringComparer.Ordinal);
        var results = new List<object>();
        foreach (var item in fixture.RootElement.GetProperty("cases").EnumerateArray())
        {
            string id = item.GetProperty("id").GetString() ?? throw new InvalidDataException("Missing maxT case id.");
            if (string.IsNullOrWhiteSpace(id) || !identifiers.Add(id))
                throw new InvalidDataException("Empty or duplicate maxT case id.");
            int familySize = item.GetProperty("family_size").GetInt32();
            double[] observed = item.GetProperty("observed").EnumerateArray().Select(x => x.GetDouble()).ToArray();
            double[][] resamples = item.GetProperty("resamples").EnumerateArray()
                .Select(row => row.EnumerateArray().Select(x => x.GetDouble()).ToArray()).ToArray();
            MaxTResult result = MaxT.MonteCarloSingleStep(observed, resamples, familySize);
            results.Add(new { id, family_size = result.FamilySize, resample_count = result.ResampleCount,
                exceedance_counts = result.ExceedanceCounts, adjusted_p = result.AdjustedPValues,
                rejected = result.AdjustedPValues.Select(p => Multiplicity.IsRejected(p, .05)).ToArray() });
        }
        if (results.Count == 0) throw new InvalidDataException("maxT fixtures must contain cases.");
        var output = new
        {
            schemaVersion = "MVS-MAXT-NATIVE-1",
            fixtureSha256 = Hash(bytes),
            engineVersion = AnalysisEngine.EngineVersion,
            activeMetricCount = AnalysisEngine.MetricKeys.Length,
            coreAssemblySha256 = Hash(File.ReadAllBytes(typeof(AnalysisEngine).Assembly.Location)),
            nativeRuntime = Environment.Version.ToString(),
            results
        };
        string serialized = JsonSerializer.Serialize(output, new JsonSerializerOptions { WriteIndented = true }) + "\n";
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outputPath))!);
        // Exclusive creation also closes the ordinary check/write race: no prior
        // evidence is truncated if the target appears after the preflight above.
        using (var stream = new FileStream(outputPath, FileMode.CreateNew, FileAccess.Write))
        using (var writer = new StreamWriter(stream)) writer.Write(serialized);
        Console.WriteLine($"Exported {results.Count} native maxT cases. Independent comparison is still required; this is not a scientific-validity claim.");
    }
}
