using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

namespace MvsProspectiveAdapter;

// TEST ONLY. This seam accepts one fixed engineering fixture, not prospective study data.
// It reuses the old harness implementation; no statistical algorithm is copied here.
internal static class Program
{
    private const string Schema = "mvs-prospective-adapter-envelope-v1";
    private const string ProtocolId = "round55-prospective-adapter-engineering-v1";
    private const string FrozenRequestSha256 = "6aed9dd4fb65af09414db6b245edfe29173b72521807fa3dafa4008ef396e440";
    private const int RequestByteLimit = 16384;
    private static readonly JsonSerializerOptions Json = new();
    private static readonly Process Process = Process.GetCurrentProcess();
    private static int fixtureMaterializations, builds, runs, legacyCalls, completenessCalls, serializations;
    private static string mode = "unrecognized", phase = "argument_validation";
    private static string? requestSha256;
    private sealed record Timing(double WallSeconds, double CpuSeconds, long PeakWorkingSetBytes);

    // An intentionally narrow bridge to the unchanged Round50 test harness. No arbitrary
    // method/type names or input observations are accepted from the request or command line.
    private static class Round50
    {
        private static readonly Type Harness = typeof(MvsVarianceSensitivity.Program);
        private const BindingFlags StaticPrivate = BindingFlags.Static | BindingFlags.NonPublic;
        private static readonly Type ObserverType = Harness.GetNestedType("Observer", BindingFlags.NonPublic)
            ?? throw new MissingMemberException("The original Round50 Observer is missing.");
        private static object? Invoke(string name, Type[] signature, params object?[] values)
        {
            var method = Harness.GetMethod(name, StaticPrivate, binder: null, types: signature, modifiers: null)
                ?? throw new MissingMethodException(Harness.FullName, name);
            try { return method.Invoke(null, values); }
            catch (TargetInvocationException ex) when (ex.InnerException is not null)
            { ExceptionDispatchInfo.Capture(ex.InnerException).Throw(); throw; }
        }
        internal static List<Observation> Fixture() => (List<Observation>)Invoke("Fixture", Type.EmptyTypes)!;
        internal static object Legacy(AnalysisData data) => Invoke("Legacy", [typeof(AnalysisData)], data)!;
        internal static object? Encode(object? value) => Invoke("Encode", [typeof(object)], value);
        internal static object Identity() => Invoke("Identity", Type.EmptyTypes)!;
        internal static IRunRecordingFactory Observer() => (IRunRecordingFactory)(Activator.CreateInstance(ObserverType, nonPublic: true)
            ?? throw new MissingMemberException("The original Round50 Observer could not be created."));
        internal static object Complete(IRunRecordingFactory observer, VarianceReport report) =>
            Invoke("Complete", [ObserverType, typeof(VarianceReport)], observer, report)!;
        internal static void SetCall(string name, int value)
        {
            Require(name is "runCalls" or "legacyCalls", "Unsupported bridge counter.");
            var field = Harness.GetField(name, StaticPrivate) ?? throw new MissingFieldException(Harness.FullName, name);
            Require(field.FieldType == typeof(int), "The Round50 counter type changed.");
            field.SetValue(null, value);
        }
    }

    private static object Counts() => new
    {
        fixtureMaterializationCount = fixtureMaterializations, buildCallCount = builds,
        runCallCount = runs, legacyCallCount = legacyCalls, completenessCallCount = completenessCalls,
        payloadSerializationCount = serializations, directGenerateCallCount = 0, directFitCallCount = 0,
    };

    private static void Emit(string kind, object? detail = null, bool error = false)
    {
        var row = new Dictionary<string, object?>
        {
            ["schema"] = Schema, ["protocolId"] = ProtocolId, ["kind"] = kind,
            ["mode"] = mode, ["requestSha256"] = requestSha256, ["operationCounts"] = Counts(),
            ["operationCountScope"] = "adapter_entry_calls_only_nested_production_calls_not_instrumented",
        };
        if (detail is not null)
            foreach (var property in detail.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
                row.Add(property.Name, property.GetValue(detail));
        var writer = error ? Console.Error : Console.Out;
        writer.WriteLine(JsonSerializer.Serialize(row, Json)); writer.Flush();
    }

    private static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static void Require(bool condition, string message)
    { if (!condition) throw new InvalidDataException(message); }

    private static object Identity()
    {
        var source = new SortedDictionary<string, string>(StringComparer.Ordinal);
        var assembly = typeof(Program).Assembly;
        const string prefix = "adapter-source/";
        foreach (string name in assembly.GetManifestResourceNames().Where(n => n.StartsWith(prefix, StringComparison.Ordinal)))
        {
            using var stream = assembly.GetManifestResourceStream(name)!;
            source.Add(name[prefix.Length..], Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant());
        }
        Require(source.Keys.SequenceEqual(new[] { "validation/prospective_adapter/Program.cs", "validation/prospective_adapter/ProspectiveAdapter.csproj" }),
            "Exactly two adapter source identities required.");
        return new { identity = Round50.Identity(), adapterSourceSha256 = source, frozenEngineeringRequestSha256 = FrozenRequestSha256,
            adapterScope = "test_only_fixed_fixture_no_general_study_execution" };
    }

    private static byte[] ReadBoundedRequest(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        byte[] buffer = new byte[RequestByteLimit + 1]; int length = 0;
        while (length < buffer.Length)
        {
            int read = stream.Read(buffer, length, buffer.Length - length);
            if (read == 0) break;
            length += read;
        }
        Require(length <= RequestByteLimit, "Request exceeds 16 KiB.");
        return buffer.AsSpan(0, length).ToArray();
    }

    private static void ValidateRequest(string path, string expectedSha256)
    {
        Require(expectedSha256.Length == 64 && expectedSha256.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'), "Invalid lowercase SHA256.");
        byte[] bytes = ReadBoundedRequest(path); requestSha256 = Sha(bytes);
        Require(requestSha256 == expectedSha256, "Request SHA256 mismatch.");
        using var doc = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 4 });
        var root = doc.RootElement;
        Require(root.ValueKind == JsonValueKind.Object, "Request must be an object.");
        var expected = new Dictionary<string, object>
        {
            ["schemaVersion"] = 1, ["protocolId"] = ProtocolId, ["mode"] = "engineering-fixed-fixture",
            ["status"] = "frozen", ["fixtureId"] = "round50-fixed-2x16x40-v1", ["seed"] = 52000000,
            ["repetitions"] = 100, ["referenceReplications"] = 199, ["withinEffect"] = 2,
            ["betweenEffect"] = 2, ["alpha"] = .05, ["calls"] = 1, ["wallCapSeconds"] = 180,
        };
        var properties = root.EnumerateObject().ToArray();
        Require(properties.Length == expected.Count && properties.Select(p => p.Name).Distinct(StringComparer.Ordinal).Count() == expected.Count && properties.All(p => expected.ContainsKey(p.Name)),
            "Request fields are missing, unknown or duplicated.");
        foreach (var (name, value) in expected)
        {
            var actual = root.GetProperty(name);
            bool same = value switch
            {
                string s => actual.ValueKind == JsonValueKind.String && actual.GetString() == s,
                int n => actual.ValueKind == JsonValueKind.Number && actual.TryGetInt32(out int i) && i == n,
                double d => actual.ValueKind == JsonValueKind.Number && actual.TryGetDouble(out double x) && double.IsFinite(x) && x == d,
                _ => false,
            };
            Require(same, "Frozen request value or type differs: " + name);
        }
        Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1", "MVS_DISABLE_BACKUPS=1 is required.");
        Require(Environment.GetEnvironmentVariable("DOTNET_PROCESSOR_COUNT") == "1" && Environment.ProcessorCount == 1,
            "DOTNET_PROCESSOR_COUNT=1 and a one-core runtime cap are required.");
        if (mode == "engineering") Require(requestSha256 == FrozenRequestSha256, "Engineering mode requires the exact pinned request bytes.");
    }

    private static Timing Measure(Action action)
    {
        Process.Refresh(); double cpu = Process.TotalProcessorTime.TotalSeconds; var wall = Stopwatch.StartNew();
        action(); wall.Stop(); Process.Refresh();
        return new Timing(wall.Elapsed.TotalSeconds, Process.TotalProcessorTime.TotalSeconds - cpu, Process.PeakWorkingSet64);
    }

    private static bool SameRows(IReadOnlyList<Observation> raw, IReadOnlyList<Observation> retained) =>
        raw.Count == retained.Count && raw.Zip(retained).All(pair =>
            pair.First.Entity == pair.Second.Entity && pair.First.Group == pair.Second.Group && pair.First.Sequence == pair.Second.Sequence &&
            pair.First.Variable == pair.Second.Variable && pair.First.Unit == pair.Second.Unit &&
            BitConverter.DoubleToInt64Bits(pair.First.Value) == BitConverter.DoubleToInt64Bits(pair.Second.Value));

    private static int Engineering()
    {
        phase = "identity";
        var identity = Identity();
        Emit("adapter_start", new { identity = JsonSerializer.SerializeToElement(identity, Json).GetProperty("identity"),
            adapterSourceSha256 = JsonSerializer.SerializeToElement(identity, Json).GetProperty("adapterSourceSha256"),
            frozenEngineeringRequestSha256 = FrozenRequestSha256, processorCount = Environment.ProcessorCount,
            processId = Environment.ProcessId, recording = "unchanged production default factory decorated; backups disabled; no restore" });
        using var cap = new CancellationTokenSource(TimeSpan.FromSeconds(180)); var total = Stopwatch.StartNew();
        List<Observation> raw = null!; AnalysisData data = null!;
        phase = "fixture_and_build";
        Timing buildTiming = Measure(() =>
        {
            fixtureMaterializations++; raw = Round50.Fixture();
            cap.Token.ThrowIfCancellationRequested();
            builds++; data = AnalysisEngine.Build(raw, -1000000, 1000000, 2);
            Require(SameRows(raw, data.Observations) && raw.Count == 1280 && data.ValidRows == 1280 && data.TotalEntities == 32 && data.GroupCounts.SequenceEqual(new[] { 16, 16 }),
                "Build changed the fixed ordered input or binary64 values.");
        });
        string dataHash = Sha(JsonSerializer.SerializeToUtf8Bytes(Round50.Encode(raw), Json));
        Emit("fixture", new { dataSha256 = dataHash, observations = Round50.Encode(raw), rawRows = raw.Count,
            retainedRows = data.ValidRows, entities = data.TotalEntities, data.GroupCounts, exactOrderedBinary64Retention = true, buildTiming });
        cap.Token.ThrowIfCancellationRequested();
        var observer = Round50.Observer(); VarianceReport report = null!;
        phase = "variance_run"; runs++; Round50.SetCall("runCalls", runs);
        Timing runTiming = Measure(() => report = VarianceAnalysis.RunWithRecording(observer, data, 100, 199, 2, 2, 52000000, .05, token: cap.Token));
        Emit("variance_returned", new { call = 1, runTiming, report = Round50.Encode(report) });
        phase = "completeness"; completenessCalls++;
        object completeness = Round50.Complete(observer, report);
        cap.Token.ThrowIfCancellationRequested();
        phase = "legacy"; legacyCalls++; Round50.SetCall("legacyCalls", legacyCalls);
        object legacy = null!; string legacyJson = "";
        Timing legacyTiming = Measure(() => { legacy = Round50.Legacy(data); legacyJson = JsonSerializer.Serialize(legacy, Json); });
        cap.Token.ThrowIfCancellationRequested();
        phase = "payload_serialization"; serializations++; string serialized = "";
        Timing serializationTiming = Measure(() => serialized = JsonSerializer.Serialize(new { call = 1, dataSha256 = dataHash, report = Round50.Encode(report), legacy, completeness }, Json));
        Emit("call_complete", new { call = 1, runTiming, legacyTiming, serializationTiming,
            serializedUtf8Bytes = System.Text.Encoding.UTF8.GetByteCount(serialized),
            legacySerializedUtf8Bytes = System.Text.Encoding.UTF8.GetByteCount(legacyJson), payload = JsonSerializer.Deserialize<JsonElement>(serialized) });
        cap.Token.ThrowIfCancellationRequested();
        Require(fixtureMaterializations == 1 && builds == 1 && runs == 1 && legacyCalls == 1 && completenessCalls == 1 && serializations == 1,
            "A fresh process must execute each adapter operation exactly once.");
        Process.Refresh(); phase = "finished";
        Emit("adapter_complete", new { status = "engineering_fixture_complete", completed = true,
            nativeTotalWallSeconds = total.Elapsed.TotalSeconds, processTotalCpuSeconds = Process.TotalProcessorTime.TotalSeconds,
            processPeakWorkingSetBytes = Process.PeakWorkingSet64, scientificStudyExecuted = false });
        return 0;
    }

    private static object Error(Exception ex) => new
    {
        type = ex.GetType().FullName, message = ex.Message, stack = ex.StackTrace,
        inner = ex.InnerException is null ? null : Error(ex.InnerException),
    };

    private static int Main(string[] args)
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture; CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        try
        {
            if (args.Length == 1 && args[0] == "identity")
            { mode = "identity"; phase = "identity"; Emit("identity", Identity()); return 0; }
            Require(args.Length == 3 && args[0] is "validate-only" or "engineering",
                "Usage: identity | validate-only REQUEST_JSON EXPECTED_SHA256 | engineering REQUEST_JSON EXPECTED_SHA256. No study or arbitrary-data mode exists.");
            mode = args[0]; phase = "request_validation";
            ValidateRequest(args[1], args[2]);
            if (mode == "validate-only")
            { Emit("request_validated", new { valid = true, completed = false, computationInvoked = false, frozenEngineeringRequestSha256 = FrozenRequestSha256 }); return 0; }
            return Engineering();
        }
        catch (Exception ex)
        {
            Emit("adapter_error", new { status = ex is OperationCanceledException ? "cancelled" : "technical_failure",
                completed = false, partialNativeWork = runs != 0, phase, exception = Error(ex) }, error: true);
            return 2;
        }
    }
}
