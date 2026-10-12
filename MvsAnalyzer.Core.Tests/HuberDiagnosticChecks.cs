using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

// Native diagnostic export, not an accuracy gate or a second production estimator.
internal static class HuberDiagnosticChecks
{
    public static void Export(string fixturePath, string outputPath) =>
        ExportCore(fixturePath, outputPath, MetricRegistry.HuberMaxIterations);

    // No command-line override: this seam only exercises failure serialization in tests.
    internal static void ExportWithIterationBudgetForTesting(string fixturePath, string outputPath, int maxIterations) =>
        ExportCore(fixturePath, outputPath, maxIterations);

    private static void ExportCore(string fixturePath, string outputPath, int maxIterations)
    {
        byte[] fixtureBytes = File.ReadAllBytes(fixturePath);
        using var fixture = JsonDocument.Parse(fixtureBytes);
        if (fixture.RootElement.GetProperty("schema").GetString() != "MVS-HUBER-REFERENCE-1")
            throw new InvalidDataException("Unsupported Huber fixture schema.");
        var results = new List<object>();
        var identifiers = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in fixture.RootElement.GetProperty("cases").EnumerateArray())
        {
            string id = item.GetProperty("id").GetString() ?? throw new InvalidDataException("Missing case id.");
            if (!identifiers.Add(id)) throw new InvalidDataException("Duplicate Huber case id.");
            double[] values = item.GetProperty("values").EnumerateArray().Select(x => x.GetDouble()).ToArray();
            if (values.Length < 2 || values.Any(x => !double.IsFinite(x)))
                throw new InvalidDataException("Huber fixtures require at least two finite values.");
            MetricRegistry.HuberResult result = MetricRegistry.HuberLocation(values, maxIterations);
            results.Add(new { id, value = double.IsFinite(result.Value) ? (double?)result.Value : null,
                status = double.IsFinite(result.Value) ? "finite" : "unavailable",
                solverStatus = result.Status, iterations = result.Iterations });
        }
        string assemblyPath = typeof(AnalysisEngine).Assembly.Location;
        var output = new
        {
            schema = "MVS-HUBER-NATIVE-1",
            implementationId = MetricRegistry.HuberImplementationId,
            fixtureSha256 = Convert.ToHexString(SHA256.HashData(fixtureBytes)).ToLowerInvariant(),
            coreAssemblySha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(assemblyPath))).ToLowerInvariant(),
            engineVersion = AnalysisEngine.EngineVersion,
            nativeRuntime = Environment.Version.ToString(),
            metricStaged = !MetricRegistry.Get("huber_location").LegacyInference,
            activeMetricCount = AnalysisEngine.MetricKeys.Length,
            results
        };
        string? directory = Path.GetDirectoryName(Path.GetFullPath(outputPath));
        if (directory != null) Directory.CreateDirectory(directory);
        File.WriteAllText(outputPath, JsonSerializer.Serialize(output, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        Console.WriteLine($"Exported {results.Count} native Huber diagnostic cases. Compare independently; export success is not an accuracy pass.");
    }
}
