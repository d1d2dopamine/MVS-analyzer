using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using MvsAnalyzer;

namespace MvsVarianceBootstrapContract;

// Test-only friend assembly. All generator and reporting work invokes production Core.
// The recording seam is fail-closed: no calculation delegate can ever execute here.
internal static class Program
{
    private const string ProtocolId = "round49-variance-bootstrap-contract-v1";
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    private static readonly JsonSerializerOptions CacheJson = new() { NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals };
    private sealed record GeneratorCase(string Id, ClusterSummary[] Design, VarianceFit Model, double[] Tape, string Track, double Effect, string? ExpectedException);
    private sealed record RunCase(string Id, AnalysisData Data, int Repetitions, int References, double WithinEffect, double BetweenEffect, int Seed, double Alpha, Dictionary<string, JsonElement> Cache, string? ExpectedException);
    private static int generateCalls, runCalls;

    private sealed class TapeRandom(double[] tape) : Random
    {
        internal int Consumed;
        public override double NextDouble()
        {
            if (Consumed == tape.Length) throw new InvalidDataException("Uniform tape exhausted.");
            return tape[Consumed++];
        }
        protected override double Sample() => throw new InvalidOperationException("Only NextDouble is authorized.");
        public override int Next() => throw new InvalidOperationException("Only NextDouble is authorized.");
        public override int Next(int maxValue) => throw new InvalidOperationException("Only NextDouble is authorized.");
        public override int Next(int minValue, int maxValue) => throw new InvalidOperationException("Only NextDouble is authorized.");
        public override void NextBytes(byte[] buffer) => throw new InvalidOperationException("Only NextDouble is authorized.");
        public override void NextBytes(Span<byte> buffer) => throw new InvalidOperationException("Only NextDouble is authorized.");
    }
    private sealed class Recording(Dictionary<string, JsonElement> cache) : IRunRecording, IRunRecordingFactory
    {
        internal readonly List<string> Events = new();
        internal readonly List<object?> Progress = new();
        internal readonly List<string> RequestedKeys = new(), ConsumedKeys = new(), MissingKeys = new();
        internal BackupRequest? Request;
        internal int CachedRequests, CacheHits, CacheMisses, Disposals, Finishes, Acquisitions, IntervalGenerateCalls;
        // Deliberately has no invocation of calculate, including on a missing key.
        internal int CalculationCallbacks => 0;
        public bool EnvironmentChanged => false;
        public IRunRecording Begin(BackupRequest request)
        { Acquisitions++; Request = request; Events.Add("Begin:" + request.Kind); return this; }
        public bool Try<T>(string key, out T value)
        {
            Events.Add("Try:" + key);
            if (cache.TryGetValue(key, out var stored)) { value = stored.Deserialize<T>(CacheJson)!; return true; }
            value = default!; return false;
        }
        public T Cached<T>(string key, Func<T> calculate)
        {
            CachedRequests++; RequestedKeys.Add(key); Events.Add("Cached:" + key);
            // Production calls Generate immediately before requesting each interval key.
            // This is a source-linked control-flow count, not an injected Generate hook.
            if (key.StartsWith("interval/", StringComparison.Ordinal)) IntervalGenerateCalls++;
            if (Try<T>(key, out var value)) { CacheHits++; ConsumedKeys.Add(key); return value; }
            CacheMisses++; MissingKeys.Add(key); throw new InvalidDataException("Unseeded recording cache key: " + key);
        }
        public void Put<T>(string key, T value) => throw new InvalidOperationException("Unexpected recording Put: " + key);
        public T Finish<T>(T value) { Finishes++; Events.Add("Finish"); return value; }
        public void Dispose() { Disposals++; Events.Add("Dispose"); }
    }
    private sealed class Reporter(Recording recording) : IProgress<ProgressInfo>
    { public void Report(ProgressInfo value) => recording.Progress.Add(Encode(value)); }

    private static object Evaluate(GeneratorCase item)
    {
        string before = JsonSerializer.Serialize(new { item.Design, item.Model }, CacheJson);
        var random = new TapeRandom(item.Tape); ClusterSummary[]? actual = null; Exception? error = null;
        try { generateCalls++; actual = VarianceAnalysis.Generate(item.Design, item.Model, random, item.Track, item.Effect); Require(random.Consumed == item.Tape.Length, "Uniform tape was not exhausted exactly."); Require(before == JsonSerializer.Serialize(new { item.Design, item.Model }, CacheJson), "Generator input mutated."); }
        catch (Exception ex) { error = ex; }
        return new { id = item.Id, status = error == null ? "returned" : "exception", expectedException = item.ExpectedException,
            exception = error == null ? null : Error(error), generateCallCount = 1, uniformConsumption = random.Consumed,
            uniformTapeLength = item.Tape.Length, inputBeforeSha256 = Sha(System.Text.Encoding.UTF8.GetBytes(before)), inputAfterSha256 = Sha(System.Text.Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { item.Design, item.Model }, CacheJson))), output = Encode(actual) };
    }
    private static object Evaluate(RunCase item)
    {
        var recording = new Recording(item.Cache); VarianceReport? report = null; Exception? error = null;
        try { runCalls++; report = VarianceAnalysis.RunWithRecording(recording, item.Data, item.Repetitions, item.References,
            item.WithinEffect, item.BetweenEffect, item.Seed, item.Alpha, new Reporter(recording));
            Require(recording.CachedRequests == item.Cache.Count && recording.ConsumedKeys.Distinct(StringComparer.Ordinal).Count() == item.Cache.Count && recording.CacheMisses == 0, "Cache consumption differs from the complete preseeded dictionary.");
            Require(recording.Request is { Kind: "variance" } request && ReferenceEquals(request.Data, item.Data) && request.Repetitions == item.Repetitions && request.ReferenceReplications == item.References && request.Effect == item.WithinEffect && request.SecondEffect == item.BetweenEffect && request.Seed == item.Seed && request.Alpha == item.Alpha, "Backup Begin request differs.");
            Require(recording.Acquisitions == 1 && recording.Finishes == 1 && recording.Disposals == 1 && recording.IntervalGenerateCalls == 0, "Run ownership or interval-generation budget differs."); }
        catch (Exception ex) { error = ex; }
        return new { id = item.Id, status = error == null ? "returned" : "exception", expectedException = item.ExpectedException,
            exception = error == null ? null : Error(error), beginRequest = Encode(recording.Request), report = Encode(report), events = recording.Events, progress = recording.Progress,
            runCallCount = 1, actualGenerateCallCount = recording.IntervalGenerateCalls,
            generateCountEvidence = "Production Generate precedes each observed interval cache request; all cache delegates are blocked.",
            calculationCallbackCount = recording.CalculationCallbacks, fitCallCount = 0, statisticCallCount = 0,
            seededKeys = item.Cache.Keys.Order(StringComparer.Ordinal).ToArray(), requestedKeys = recording.RequestedKeys, consumedKeys = recording.ConsumedKeys, missingKeys = recording.MissingKeys,
            cachedRequestCount = recording.CachedRequests, cacheHitCount = recording.CacheHits, cacheMissCount = recording.CacheMisses,
            acquisitionCount = recording.Acquisitions, finishCount = recording.Finishes, disposalCount = recording.Disposals };
    }

    // Preserve the complete public record shape while representing every floating value
    // with finite/null JSON, classification, and its exact IEEE-754 payload.
    private static object? Encode(object? value)
    {
        if (value == null) return null;
        if (value is double d) return Fp(d);
        if (value is string or bool or int or long) return value;
        if (value is IEnumerable array) return array.Cast<object?>().Select(Encode).ToArray();
        return value.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .ToDictionary(p => char.ToLowerInvariant(p.Name[0]) + p.Name[1..], p => Encode(p.GetValue(value)), StringComparer.Ordinal);
    }
    private static object Fp(double value) => new {
        classification = double.IsNaN(value) ? "nan" : double.IsPositiveInfinity(value) ? "positive_infinity" : double.IsNegativeInfinity(value) ? "negative_infinity" : "finite",
        value = double.IsFinite(value) ? (double?)value : null,
        bits = unchecked((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("x16", CultureInfo.InvariantCulture)
    };
    private static object Error(Exception ex) => new { type = ex.GetType().FullName, message = ex.Message };
    private static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static void Require(bool condition, string message) { if (!condition) throw new InvalidDataException(message); }
    private static void Properties(JsonElement value, params string[] names)
    { Require(value.ValueKind == JsonValueKind.Object && value.EnumerateObject().Select(p => p.Name).ToHashSet(StringComparer.Ordinal).SetEquals(names), "Properties differ from fixed schema."); }
    private static void NoDuplicates(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object) { var keys = new HashSet<string>(StringComparer.Ordinal); foreach (var p in element.EnumerateObject()) { Require(keys.Add(p.Name), "Duplicate JSON property: " + p.Name); NoDuplicates(p.Value); } }
        else if (element.ValueKind == JsonValueKind.Array) foreach (var item in element.EnumerateArray()) NoDuplicates(item);
    }
    private static object Identity()
    {
        var assembly = typeof(Program).Assembly; var source = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (string name in assembly.GetManifestResourceNames().Where(n => n.StartsWith("source/", StringComparison.Ordinal)))
        { using var stream = assembly.GetManifestResourceStream(name)!; source.Add(name[7..], Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()); }
        Require(source.Count == 9, "Nine build-time source identities required.");
        return new { experimental = true, sourceIdentityScope = "Embedded build-time source bytes, not the complete source tree", sourceSha256 = source,
            runtime = new { framework = RuntimeInformation.FrameworkDescription, version = Environment.Version.ToString(), os = RuntimeInformation.OSDescription,
                processArchitecture = RuntimeInformation.ProcessArchitecture.ToString(), coreLibrarySha256 = Sha(File.ReadAllBytes(typeof(object).Assembly.Location)) },
            harnessAssembly = AssemblyIdentity(assembly), coreAssembly = AssemblyIdentity(typeof(VarianceAnalysis).Assembly) };
    }
    private static object AssemblyIdentity(Assembly assembly) => new { name = assembly.GetName().Name,
        version = assembly.GetName().Version?.ToString(), moduleVersionId = assembly.ManifestModule.ModuleVersionId.ToString("D"),
        fileName = Path.GetFileName(assembly.Location), sha256 = Sha(File.ReadAllBytes(assembly.Location)) };

    private static int Main(string[] args)
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        if (args.Length == 1 && args[0] == "identity")
        { Console.WriteLine(JsonSerializer.Serialize(new { schemaVersion = 1, protocolId = ProtocolId, identity = Identity(), generateCallCount = 0, runCallCount = 0 }, Json)); return 0; }
        var generatorRows = new List<object>(); var runRows = new List<object>();
        try
        {
            Require(args.Length == 3 && args[0] == "contract", "Usage: MvsAnalyzer.Core.Tests.dll contract FROZEN_FIXTURE_JSON EXPECTED_SHA256");
            Require(args[2].Length == 64 && args[2].All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'), "Invalid expected SHA256.");
            Require(new FileInfo(args[1]).Length <= 1024 * 1024, "Fixture exceeds 1 MiB.");
            byte[] bytes = File.ReadAllBytes(args[1]); string inputSha256 = Sha(bytes);
            Require(inputSha256 == args[2], "Fixture SHA256 mismatch.");
            using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
            var root = document.RootElement; NoDuplicates(root);
            Properties(root, "schemaVersion", "protocolId", "status", "budgets", "generatorCases", "runCases");
            Require(root.GetProperty("schemaVersion").GetInt32() == 1 && root.GetProperty("protocolId").GetString() == ProtocolId && root.GetProperty("status").GetString() == "frozen", "Unexpected or unfrozen protocol.");
            var budgets = root.GetProperty("budgets");
            var expectedBudgets = new Dictionary<string, int> { ["generateCalls"] = 6, ["runCalls"] = 14, ["cachedReads"] = 19241,
                ["uniformDraws"] = 106, ["gaussianDraws"] = 53, ["fitCalls"] = 0, ["statisticCalls"] = 0,
                ["optimizerCalls"] = 0, ["calculationCallbacks"] = 0, ["intervalGenerateCalls"] = 0 };
            Properties(budgets, expectedBudgets.Keys.ToArray());
            Require(expectedBudgets.All(p => budgets.GetProperty(p.Key).GetInt32() == p.Value), "Frozen budgets differ.");
            // Validate the entire manifest, including all serialized fit/statistic types, BEFORE production entry.
            var generators = ReadGenerators(root.GetProperty("generatorCases"));
            var runs = ReadRuns(root.GetProperty("runCases"));
            Require(generators.Sum(g => g.Tape.Length) == 106 && runs.Sum(r => r.Cache.Count) == 19241, "Aggregate input budget differs.");
            object identity = Identity(); object selfCheck = RecorderSelfCheck();
            foreach (var item in generators) { var row = Evaluate(item); generatorRows.Add(row); StopOnException(row); }
            foreach (var item in runs) { var row = Evaluate(item); runRows.Add(row); StopOnException(row); }
            Console.WriteLine(JsonSerializer.Serialize(new { schemaVersion = 1, protocolId = ProtocolId, inputSha256, identity, recorderSelfCheck = selfCheck,
                generatorCaseCount = generatorRows.Count, runCaseCount = runRows.Count, generateCallCount = generateCalls, runCallCount = runCalls,
                generatorCases = generatorRows, runCases = runRows }, Json));
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(JsonSerializer.Serialize(new { schema = "mvs-variance-contract-native-error/v1", status = "input_or_harness_error",
                candidateInvoked = generateCalls + runCalls != 0, generateCallCount = generateCalls, runCallCount = runCalls,
                generatorCases = generatorRows, runCases = runRows, exception = Error(ex) }, Json));
            return 2;
        }
    }
    private static void StopOnException(object row)
    { Require((string?)row.GetType().GetProperty("status")!.GetValue(row) == "returned", "Unexpected candidate exception; partial rows retained."); }
    private static object RecorderSelfCheck()
    {
        int callbacks = 0; int rejected = 0;
        foreach (bool wrongType in new[] { false, true })
        {
            var cache = new Dictionary<string, JsonElement>();
            if (wrongType) cache.Add("probe", JsonSerializer.SerializeToElement(new { bad = "type" }));
            var recording = new Recording(cache);
            try { recording.Cached<double>("probe", () => { callbacks++; throw new Exception("Callback must not execute."); }); }
            catch (Exception ex) when (ex is InvalidDataException or JsonException) { rejected++; }
        }
        Require(callbacks == 0 && rejected == 2, "Fail-closed recorder self-check failed.");
        return new { missingKeyRejected = true, wrongTypeRejected = true, calculationCallbackCount = callbacks };
    }
    private static string Id(JsonElement value, string field)
    {
        string text = value.GetProperty(field).GetString() ?? "";
        Require(text.Length is > 0 and <= 128 && text.All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-' or '.'), "Invalid identifier: " + field);
        return text;
    }
    private static double Finite(JsonElement element)
    { double x = element.GetDouble(); Require(double.IsFinite(x) && Math.Abs(x) <= 1e6, "Nonfinite or out-of-bound literal."); return x; }
    private static VarianceFit Fit(JsonElement element, int groups)
    {
        Properties(element, "Means", "Within", "Between", "NegativeLogLikelihood", "Converged", "AtBoundary", "Method", "Iterations");
        var fit = element.Deserialize<VarianceFit>(CacheJson) ?? throw new InvalidDataException("Missing fit.");
        Require(fit.Means != null && fit.Within != null && fit.Between != null && fit.Means.Length == groups && fit.Within.Length == groups && fit.Between.Length == groups, "Fit dimensions differ.");
        Require(fit.Means!.Concat(fit.Within!).Concat(fit.Between!).Append(fit.NegativeLogLikelihood).All(x => double.IsFinite(x) && Math.Abs(x) <= 1e6), "Invalid fit number.");
        Require(fit.Within!.Concat(fit.Between!).All(x => x >= 0) && fit.Method is "ML" or "REML" && fit.Iterations == 0, "Invalid fit metadata.");
        return fit;
    }
    private static GeneratorCase[] ReadGenerators(JsonElement entries)
    {
        Require(entries.ValueKind == JsonValueKind.Array && entries.GetArrayLength() == 6, "Exactly six generator cases required.");
        var result = new List<GeneratorCase>();
        foreach (var item in entries.EnumerateArray())
        {
            Properties(item, "id", "design", "model", "uniformTape", "track", "effect", "expectedException");
            string id = Id(item, "id"); int index = result.Count;
            Require(id == $"G{index + 1:00}" && item.GetProperty("expectedException").ValueKind == JsonValueKind.Null, "Generator order/exception differs.");
            int groups = index == 5 ? 1 : 3; var model = Fit(item.GetProperty("model"), groups);
            var design = item.GetProperty("design"); Require(design.ValueKind == JsonValueKind.Array && design.GetArrayLength() == groups, "Generator design dimensions differ.");
            var clusters = new List<ClusterSummary>();
            foreach (var c in design.EnumerateArray())
            {
                Properties(c, "entity", "group", "count", "mean", "withinSumSquares");
                int g = c.GetProperty("group").GetInt32(), n = c.GetProperty("count").GetInt32();
                Require(g == clusters.Count && n is >= 2 and <= 3, "Invalid generator cluster.");
                double wss = Finite(c.GetProperty("withinSumSquares")); Require(wss >= 0, "Negative WSS.");
                clusters.Add(new ClusterSummary(Id(c, "entity"), g, n, Finite(c.GetProperty("mean")), wss));
            }
            double[] tape = item.GetProperty("uniformTape").EnumerateArray().Select(Finite).ToArray();
            Require(tape.Length == (index == 5 ? 6 : 20) && tape.Length == 2 * clusters.Sum(c => c.Count + 1) && tape.All(x => x >= 0 && x < 1), "Uniform tape dimensions/range differ.");
            string track = Id(item, "track"); double effect = Finite(item.GetProperty("effect"));
            Require(track == new[] { "none", "within", "between", "within", "between", "none" }[index] && effect == (index is 1 or 2 ? 2 : 1), "Generator track/effect differs.");
            result.Add(new(id, clusters.ToArray(), model, tape, track, effect, null));
        }
        return result.ToArray();
    }
    private static RunCase[] ReadRuns(JsonElement entries)
    {
        Require(entries.ValueKind == JsonValueKind.Array && entries.GetArrayLength() == 14, "Exactly fourteen run cases required.");
        int[] expectedReads = { 803, 404, 805, 205, 803, 803, 803, 3197, 3203, 3203, 3203, 803, 803, 203 };
        var result = new List<RunCase>();
        foreach (var item in entries.EnumerateArray())
        {
            Properties(item, "id", "data", "repetitions", "referenceReplications", "withinEffect", "betweenEffect", "seed", "alpha", "cache", "expectedException");
            int index = result.Count; string id = Id(item, "id");
            Require(id == $"R{index + 1:00}" && item.GetProperty("expectedException").ValueKind == JsonValueKind.Null, "Run order/exception differs.");
            int n = item.GetProperty("repetitions").GetInt32(), r = item.GetProperty("referenceReplications").GetInt32();
            Require(n == (index == 7 ? 499 : index is >= 8 and <= 10 ? 500 : 100) && r == (index is 2 or 3 ? 100 : 99), "Run draw budgets differ.");
            double within = Finite(item.GetProperty("withinEffect")), between = Finite(item.GetProperty("betweenEffect")), alpha = Finite(item.GetProperty("alpha"));
            int seed = item.GetProperty("seed").GetInt32();
            Require(within == 2 && between == 3 && seed == 54 && alpha == (index == 0 ? .04 : index == 1 ? .015 : .05), "Run configuration differs.");
            var data = Data(item.GetProperty("data"));
            var cacheElement = item.GetProperty("cache"); Require(cacheElement.ValueKind == JsonValueKind.Object, "Cache must be an object.");
            var cache = cacheElement.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.Clone(), StringComparer.Ordinal);
            Require(cache.Count == expectedReads[index], "Run cache size differs.");
            foreach (var p in cache)
            {
                if (p.Key == "initial-fit" || p.Key is "within/null-fit" or "between/null-fit")
                { var fit = Fit(p.Value, 2); Require(p.Key != "initial-fit" || !fit.Converged, "Converged initial fits are outside this protocol; interval generation forbidden."); }
                else
                {
                    var parts = p.Key.Split('/');
                    Require(parts.Length is 2 or 3 && parts[0] is "within" or "between", "Invalid cache key.");
                    if (parts.Length == 2) Require(parts[1] == "observed", "Invalid scalar cache key.");
                    else Require(parts[1] is "reference" or "null" or "alternative" or "grid" && int.TryParse(parts[2], out int k) && k >= 0 && k < (parts[1] == "reference" ? r : n) && parts[2] == k.ToString(CultureInfo.InvariantCulture), "Invalid indexed cache key.");
                    Require(p.Value.ValueKind == JsonValueKind.Number || p.Value.ValueKind == JsonValueKind.String && p.Value.GetString() == "NaN", "Invalid statistic encoding.");
                    double value = p.Value.Deserialize<double>(CacheJson); Require(double.IsNaN(value) || double.IsFinite(value) && Math.Abs(value) <= 1e6, "Invalid cached statistic.");
                }
            }
            Require(new[] { "initial-fit", "within/null-fit", "within/observed", "between/null-fit", "between/observed" }.All(cache.ContainsKey), "Missing mandatory cache keys.");
            var expectedKeys = new HashSet<string>(new[] { "initial-fit", "within/null-fit", "within/observed", "between/null-fit", "between/observed" }, StringComparer.Ordinal);
            foreach (string track in new[] { "within", "between" })
            {
                // Frozen per-scenario branch map, independently specified before execution.
                bool referencesUsed = !(index == 1 && track == "between");
                bool evaluationsUsed = referencesUsed && index is not (3 or 13);
                if (referencesUsed) for (int k = 0; k < r; k++) expectedKeys.Add(track + "/reference/" + k);
                if (evaluationsUsed) for (int k = 0; k < n; k++) foreach (string kind in new[] { "null", "alternative", "grid" }) expectedKeys.Add(track + "/" + kind + "/" + k);
            }
            Require(expectedKeys.SetEquals(cache.Keys), "Frozen cache key schedule differs.");
            result.Add(new(id, data, n, r, within, between, seed, alpha, cache, null));
        }
        return result.ToArray();
    }
    private static AnalysisData Data(JsonElement item)
    {
        Properties(item, "groupNames", "observations", "warnings");
        string[] groups = item.GetProperty("groupNames").EnumerateArray().Select(x => x.GetString() ?? "").ToArray();
        Require(groups.SequenceEqual(new[] { "G0", "G1" }), "Data groups differ.");
        var observations = new List<Observation>();
        var rows = item.GetProperty("observations"); Require(rows.ValueKind == JsonValueKind.Array && rows.GetArrayLength() == 8, "Exactly eight observations required.");
        double[] values = { -1, 1, 1, 3, 9, 11, 11, 13 };
        foreach (var row in rows.EnumerateArray())
        {
            Properties(row, "entity", "group", "value", "sequence"); int index = observations.Count;
            string entity = Id(row, "entity"), group = Id(row, "group"); double value = Finite(row.GetProperty("value")); int sequence = row.GetProperty("sequence").GetInt32();
            Require(entity == "E" + index / 2 && group == "G" + index / 4 && value == values[index] && sequence == index % 2, "Literal observed data differ.");
            observations.Add(new Observation(entity, group, value, sequence));
        }
        var warnings = item.GetProperty("warnings"); Require(warnings.ValueKind == JsonValueKind.Array && warnings.GetArrayLength() == 0, "Unexpected input warning.");
        // No AnalysisEngine.Build call is needed: Run consumes observations, group names,
        // and warnings only. The remaining bookkeeping is explicit and deterministic.
        return new AnalysisData { GroupNames = groups, Observations = observations, Warnings = Array.Empty<string>(), Entities = new(),
            GroupCounts = new[] { 2, 2 }, ValidRows = 8, MedianMeasurements = 2 };
    }
}
