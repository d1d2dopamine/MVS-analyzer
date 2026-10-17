using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

namespace MvsVarianceFitReference;

// Test-only friend assembly: invokes the actual Core Fit and contains no likelihood,
// optimizer, resampling, or variance-component estimator implementation.
internal static class Program
{
    private const string ProtocolId = "round48-variance-fit-v1";
    private const int FixedCaseCount = 20;
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private sealed record FitCase(string Id, string FixtureId, int Groups, bool EqualWithin, bool EqualBetween,
        bool Reml, string Classification, ClusterSummary[] Clusters);

    private static int Main(string[] args)
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        int fitCalls = 0;
        try
        {
            if (args.Length != 3 || args[0] != "fit") throw new ArgumentException("Usage: MvsAnalyzer.Core.Tests.dll fit FROZEN_FIXTURE_JSON EXPECTED_SHA256");
            Require(args[2].Length == 64 && args[2].All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'), "Expected SHA256 must be 64 lowercase hexadecimal characters.");
            Require(new FileInfo(args[1]).Length <= 1024 * 1024, "Fixture file exceeds the fixed 1 MiB bound.");
            byte[] inputBytes = File.ReadAllBytes(args[1]);
            string inputSha256 = Sha(inputBytes);
            Require(inputSha256 == args[2], "Fixture bytes do not match the expected SHA256.");
            using JsonDocument input = JsonDocument.Parse(inputBytes, new JsonDocumentOptions { MaxDepth = 16 });
            // Validate all cases and capture identity before the first candidate invocation.
            FitCase[] cases = ReadCases(input.RootElement);
            object identity = Identity();
            var rows = new List<object>(FixedCaseCount);
            foreach (FitCase item in cases)
            {
                fitCalls++;
                rows.Add(Evaluate(item));
            }
            Require(fitCalls == FixedCaseCount && rows.Count == FixedCaseCount, "Fixed fit-call accounting failed.");
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                schemaVersion = 1,
                protocolId = ProtocolId,
                inputSha256,
                identity,
                caseCount = rows.Count,
                fitCallCount = fitCalls,
                cases = rows
            }, JsonOptions));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(JsonSerializer.Serialize(new
            {
                schema = "mvs-variance-fit-native-error/v1",
                status = "input_or_harness_error",
                candidateInvoked = fitCalls != 0,
                fitCallCount = fitCalls,
                exception = Error(error)
            }, JsonOptions));
            return 2;
        }
    }

    private static object Evaluate(FitCase item)
    {
        VarianceFit? fit = null;
        Exception? exception = null;
        try
        {
            fit = VarianceAnalysis.Fit(item.Clusters, item.Groups, item.EqualWithin, item.EqualBetween, item.Reml);
        }
        catch (Exception error) { exception = error; }
        bool finite = fit != null && fit.Means.Concat(fit.Within).Concat(fit.Between)
            .Append(fit.NegativeLogLikelihood).All(double.IsFinite);
        return new
        {
            id = item.Id,
            fixtureId = item.FixtureId,
            configurationId = (item.Reml ? "reml" : "ml") + "_" + (item.EqualWithin && item.EqualBetween ? "equal_both" : item.EqualWithin ? "equal_within" : item.EqualBetween ? "equal_between" : "unconstrained"),
            groups = item.Groups,
            equalWithin = item.EqualWithin,
            equalBetween = item.EqualBetween,
            reml = item.Reml,
            requestedClassification = item.Classification,
            status = exception is OperationCanceledException ? "cancelled" : exception != null ? "exception" : finite ? "returned_finite" : "returned_nonfinite",
            candidateInvoked = true,
            clusterCount = item.Clusters.Length,
            measurementCount = item.Clusters.Sum(c => c.Count),
            means = fit?.Means.Select(FiniteOrNull).ToArray(),
            within = fit?.Within.Select(FiniteOrNull).ToArray(),
            between = fit?.Between.Select(FiniteOrNull).ToArray(),
            negativeLogLikelihood = fit == null ? null : FiniteOrNull(fit.NegativeLogLikelihood),
            converged = fit?.Converged,
            atBoundary = fit?.AtBoundary,
            method = fit?.Method,
            iterations = fit?.Iterations,
            numeric = fit == null ? null : new
            {
                means = fit.Means.Select(Fp).ToArray(),
                within = fit.Within.Select(Fp).ToArray(),
                between = fit.Between.Select(Fp).ToArray(),
                negativeLogLikelihood = Fp(fit.NegativeLogLikelihood)
            },
            exception = exception == null ? null : Error(exception)
        };
    }

    private static FitCase[] ReadCases(JsonElement root)
    {
        RejectDuplicateProperties(root);
        RequireProperties(root, "schemaVersion", "protocolId", "status", "scientificFitCallBudget", "oracleProblemCount", "cases");
        Require(root.GetProperty("schemaVersion").GetInt32() == 1, "Unsupported fixture schemaVersion.");
        Require(root.GetProperty("protocolId").GetString() == ProtocolId, "Unexpected protocolId.");
        Require(root.GetProperty("status").GetString() == "frozen", "Only reviewed frozen fixtures can be executed.");
        Require(root.GetProperty("scientificFitCallBudget").GetInt32() == FixedCaseCount && root.GetProperty("oracleProblemCount").GetInt32() == 9,
            "Frozen call/problem budgets must be exactly 20 and 9.");
        JsonElement entries = root.GetProperty("cases");
        Require(entries.ValueKind == JsonValueKind.Array && entries.GetArrayLength() == FixedCaseCount, "Exactly 20 frozen cases are required.");
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var cases = new List<FitCase>(FixedCaseCount);
        foreach (JsonElement entry in entries.EnumerateArray())
        {
            RequireProperties(entry, "id", "fixtureId", "groups", "equalWithin", "equalBetween", "reml", "classification", "referenceCaseId", "affineScale", "affineOffset", "clusters");
            string id = ReadId(entry, "id"), fixtureId = ReadId(entry, "fixtureId");
            Require(ids.Add(id), "Duplicate case id: " + id);
            JsonElement reference = entry.GetProperty("referenceCaseId");
            Require(reference.ValueKind == JsonValueKind.Null || reference.ValueKind == JsonValueKind.String,
                "referenceCaseId must be null or a case identifier.");
            if (reference.ValueKind == JsonValueKind.String) ReadId(entry, "referenceCaseId");
            double affineScale = entry.GetProperty("affineScale").GetDouble(), affineOffset = entry.GetProperty("affineOffset").GetDouble();
            Require(double.IsFinite(affineScale) && affineScale != 0 && double.IsFinite(affineOffset), "Invalid affine metadata.");
            int groups = entry.GetProperty("groups").GetInt32();
            Require(groups == 2, "This protocol contains exactly two groups per case.");
            bool equalWithin = entry.GetProperty("equalWithin").GetBoolean(), equalBetween = entry.GetProperty("equalBetween").GetBoolean();
            bool reml = entry.GetProperty("reml").GetBoolean();
            string classification = entry.GetProperty("classification").GetString() ?? "";
            Require(classification is "regular" or "degenerate_constant", "Unknown case classification.");
            JsonElement clusterEntries = entry.GetProperty("clusters");
            Require(clusterEntries.ValueKind == JsonValueKind.Array && clusterEntries.GetArrayLength() is >= 4 and <= 10,
                "A case requires 4 to 10 explicitly listed clusters.");
            var clusters = new List<ClusterSummary>();
            var entities = new HashSet<(int, string)>();
            foreach (JsonElement cluster in clusterEntries.EnumerateArray())
            {
                RequireProperties(cluster, "entity", "group", "count", "mean", "withinSumSquares", "values");
                string entity = ReadId(cluster, "entity");
                int group = cluster.GetProperty("group").GetInt32(), count = cluster.GetProperty("count").GetInt32();
                Require(group is >= 0 and < 2 && count is >= 2 and <= 64, "Invalid cluster group or repeat count.");
                Require(entities.Add((group, entity)), "Duplicate entity within a group.");
                double mean = cluster.GetProperty("mean").GetDouble(), sumSquares = cluster.GetProperty("withinSumSquares").GetDouble();
                Require(double.IsFinite(mean) && double.IsFinite(sumSquares) && sumSquares >= 0, "Invalid literal cluster summary.");
                JsonElement raw = cluster.GetProperty("values");
                Require(raw.ValueKind == JsonValueKind.Array && raw.GetArrayLength() == count, "Literal raw repeat count does not match summary.");
                double[] values = raw.EnumerateArray().Select(v => v.GetDouble()).ToArray();
                Require(values.All(double.IsFinite), "Every literal measurement must be finite.");
                double rawMean = values.Sum() / count;
                double rawSumSquares = values.Sum(value => (value - rawMean) * (value - rawMean));
                Require(Close(rawMean, mean) && Close(rawSumSquares, sumSquares), "Literal raw values and summary disagree.");
                clusters.Add(new ClusterSummary(entity, group, count, mean, sumSquares));
            }
            Require(Enumerable.Range(0, groups).All(g => clusters.Count(c => c.Group == g) >= 2), "Each group needs at least two clusters.");
            Require(clusters.Sum(c => c.Count) <= 40, "A case exceeds the fixed 40-observation bound.");
            cases.Add(new FitCase(id, fixtureId, groups, equalWithin, equalBetween, reml, classification, clusters.ToArray()));
        }
        return cases.ToArray();
    }

    private static bool Close(double actual, double expected) => double.IsFinite(actual) && Math.Abs(actual - expected) <= 1e-12 * Math.Max(1, Math.Abs(expected));
    private static double? FiniteOrNull(double value) => double.IsFinite(value) ? value : null;
    private static string ReadId(JsonElement value, string field)
    {
        string id = value.GetProperty(field).GetString() ?? "";
        Require(id.Length is > 0 and <= 128 && id.All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-' or '.'), "Invalid identifier: " + field);
        return id;
    }

    private static void RequireProperties(JsonElement value, params string[] names)
    {
        Require(value.ValueKind == JsonValueKind.Object, "Expected a JSON object.");
        var actual = value.EnumerateObject().Select(p => p.Name).ToHashSet(StringComparer.Ordinal);
        Require(actual.SetEquals(names), "Object properties differ from the fixed schema: " + string.Join(",", actual));
    }

    private static object Identity()
    {
        Assembly harness = typeof(Program).Assembly;
        var sourceHashes = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (string name in harness.GetManifestResourceNames().Where(n => n.StartsWith("source/", StringComparison.Ordinal)))
        {
            using Stream stream = harness.GetManifestResourceStream(name) ?? throw new InvalidDataException("Missing embedded source: " + name);
            sourceHashes.Add(name[7..], Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant());
        }
        if (sourceHashes.Count != 6) throw new InvalidDataException("The six required build-time source identities are missing.");
        return new
        {
            experimental = true,
            purpose = "Fixed-fixture numerical validation of existing VarianceAnalysis.Fit only",
            sourceIdentityScope = "Embedded build-time Fit, optimizer, project, source-registry, and harness bytes; not the complete source tree",
            sourceSha256 = sourceHashes,
            runtime = new
            {
                framework = RuntimeInformation.FrameworkDescription,
                version = Environment.Version.ToString(),
                os = RuntimeInformation.OSDescription,
                processArchitecture = RuntimeInformation.ProcessArchitecture.ToString(),
                osArchitecture = RuntimeInformation.OSArchitecture.ToString()
            },
            harnessAssembly = AssemblyIdentity(harness),
            coreAssembly = AssemblyIdentity(typeof(VarianceAnalysis).Assembly)
        };
    }

    private static object AssemblyIdentity(Assembly assembly) => new
    {
        name = assembly.GetName().Name,
        version = assembly.GetName().Version?.ToString(),
        informationalVersion = assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
        moduleVersionId = assembly.ManifestModule.ModuleVersionId.ToString("D"),
        fileName = Path.GetFileName(assembly.Location),
        sha256 = Sha(File.ReadAllBytes(assembly.Location))
    };

    private static object Fp(double value) => new
    {
        classification = double.IsNaN(value) ? "nan" : double.IsPositiveInfinity(value) ? "positive_infinity" : double.IsNegativeInfinity(value) ? "negative_infinity" : "finite",
        value = double.IsFinite(value) ? (double?)value : null,
        bits = unchecked((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("x16", CultureInfo.InvariantCulture)
    };

    private static object Error(Exception error) => new { type = error.GetType().FullName, message = error.Message };
    private static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidDataException(message);
    }

    private static void RejectDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                Require(seen.Add(property.Name), "Duplicate JSON property: " + property.Name);
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (JsonElement child in element.EnumerateArray()) RejectDuplicateProperties(child);
    }
}
