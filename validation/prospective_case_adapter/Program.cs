using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

namespace MvsProspectiveCaseAdapter;

// TEST ONLY. No generator, batch runner, retry, or study admission is implemented here.
internal static class Program
{
    private const string Schema = "mvs-prospective-case-result/v1";
    private const string ProtocolId = "MVS-STAT-COMPONENTS-PROSPECTIVE-1.0.0";
    private const string ProtocolSha = "75d594af6fd2f249ca044340013ea02d16e8cdbae71aef8c4e16ff6853a324ed";
    private const int RequestByteLimit = 65536;
    private static readonly string[] Methods = ["gaussian_component_family_B199_E100_v1", "summary12_asymptotic_MW_Bonferroni_v1"];
    private static readonly JsonSerializerOptions Json = new();
    private static readonly Process Process = Process.GetCurrentProcess();
    private static int fixtureMaterializations, builds, runs, legacyCalls, serializations;
    private static string mode = "unrecognized", phase = "argument_validation";
    private static string? requestSha256;
    private sealed record Timing(double WallSeconds, double CpuSeconds, long PeakWorkingSetBytes);
    private sealed record Case(string Purpose, string Id, int Cell, int Replication, int Seed, int N, int M, string Hash, double[] Values);
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
        internal static object Trace(IRunRecordingFactory observer) => Invoke("TraceSummary", [ObserverType], observer)!;
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

    private static object Counts() => new { fixtureMaterializationCount = fixtureMaterializations, buildCallCount = builds,
        runCallCount = runs, legacyCallCount = legacyCalls, payloadSerializationCount = serializations,
        directGenerateCallCount = 0, directFitCallCount = 0 };
    private static void Emit(string kind, object? detail = null, bool error = false)
    {
        var row = new Dictionary<string, object?> { ["schema"] = Schema, ["protocol_id"] = ProtocolId,
            ["protocol_sha256"] = ProtocolSha, ["methods"] = Methods, ["kind"] = kind, ["mode"] = mode,
            ["requestSha256"] = requestSha256, ["operationCounts"] = Counts(),
            ["operationCountScope"] = "adapter_entry_calls_only_nested_production_calls_not_instrumented" };
        if (detail != null) foreach (var p in detail.GetType().GetProperties()) row.Add(p.Name, p.GetValue(detail));
        var writer = error ? Console.Error : Console.Out;
        writer.WriteLine(JsonSerializer.Serialize(row, Json)); writer.Flush();
    }
    private static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static bool Hex(string s, int n) => s.Length == n && s.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static void Require(bool condition, string message) { if (!condition) throw new InvalidDataException(message); }
    private static object Identity()
    {
        var assembly = typeof(Program).Assembly;
        using var config = assembly.GetManifestResourceStream("case-config/prospective-ademp-v1.json")!;
        Require(Convert.ToHexString(SHA256.HashData(config)).ToLowerInvariant() == ProtocolSha, "Embedded prospective config hash mismatch.");
        var source = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (var name in assembly.GetManifestResourceNames().Where(n => n.StartsWith("adapter-source/", StringComparison.Ordinal)))
        { using var stream = assembly.GetManifestResourceStream(name)!; source.Add(name[15..], Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()); }
        Require(source.Keys.SequenceEqual(new[] { "validation/prospective_case_adapter/Program.cs", "validation/prospective_case_adapter/ProspectiveCaseAdapter.csproj" }), "Adapter source identity mismatch.");
        return new { identity = Round50.Identity(), adapterSourceSha256 = source, configSha256 = ProtocolSha,
            adapterScope = "test_only_general_case_seam_no_study_admission" };
    }
    private static byte[] ReadBounded(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        byte[] buffer = new byte[RequestByteLimit + 1]; int length = 0;
        while (length < buffer.Length) { int n = stream.Read(buffer, length, buffer.Length - length); if (n == 0) break; length += n; }
        Require(length <= RequestByteLimit, "Case exceeds 64 KiB."); return buffer.AsSpan(0, length).ToArray();
    }
    private static string DataHash(double[] values)
    {
        byte[] bytes = new byte[values.Length * 8];
        for (int i = 0; i < values.Length; i++) BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(i * 8, 8), BitConverter.DoubleToInt64Bits(values[i]));
        return Sha(bytes);
    }
    private static Case Validate(string path, string hash)
    {
        Require(Hex(hash, 64), "Invalid request SHA256."); byte[] bytes = ReadBounded(path); requestSha256 = Sha(bytes);
        Require(requestSha256 == hash, "Request SHA256 mismatch.");
        using var doc = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 4 }); var root = doc.RootElement;
        Require(root.ValueKind == JsonValueKind.Object, "Case must be an object.");
        string[] keys = ["schema", "protocol_id", "protocol_sha256", "purpose", "case_id", "cell_index", "replication_zero_based", "native_seed", "entities_per_group", "repeats_per_entity", "value_order", "values_bits", "ordered_binary64_sha256"];
        var props = root.EnumerateObject().ToArray();
        Require(props.Length == keys.Length && props.Select(p => p.Name).Distinct(StringComparer.Ordinal).Count() == keys.Length && props.All(p => keys.Contains(p.Name, StringComparer.Ordinal)), "Case fields missing, duplicated or unknown.");
        string Str(string key) { var v = root.GetProperty(key); Require(v.ValueKind == JsonValueKind.String, "Expected string: " + key); return v.GetString()!; }
        int Int(string key) { var v = root.GetProperty(key); Require(v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out _), "Expected integer: " + key); return v.GetInt32(); }
        Require(Str("schema") == "mvs-prospective-case/v1" && Str("protocol_id") == ProtocolId && Str("protocol_sha256") == ProtocolSha, "Case schema/protocol identity mismatch.");
        string purpose = Str("purpose"); Require(purpose is "engineering_literal" or "planned_case", "Invalid case purpose.");
        int cell = Int("cell_index"), rep = Int("replication_zero_based"), seed = Int("native_seed");
        Require(cell is >= 0 and <= 11 && rep is >= 0 and <= 999 && seed == 1540000000 + 1000 * cell + rep, "Case coordinate or seed mismatch.");
        int n = cell < 10 ? 16 : 8, m = cell < 10 ? 40 : 5;
        Require(Int("entities_per_group") == n && Int("repeats_per_entity") == m && Str("value_order") == "group_entity_repeat", "Case shape/order mismatch.");
        string id = (purpose == "planned_case" ? ProtocolId : "engineering_literal") + $"/C{cell:00}/R{rep:0000}";
        Require(Str("case_id") == id, "Case ID mismatch."); var array = root.GetProperty("values_bits");
        Require(array.ValueKind == JsonValueKind.Array && array.GetArrayLength() == 2 * n * m, "Wrong number of values.");
        double[] values = array.EnumerateArray().Select(v => {
            Require(v.ValueKind == JsonValueKind.String, "Values must be binary64 hex strings."); string bits = v.GetString()!;
            Require(Hex(bits, 16), "Invalid binary64 bits."); double value = BitConverter.Int64BitsToDouble(unchecked((long)ulong.Parse(bits, NumberStyles.HexNumber, CultureInfo.InvariantCulture)));
            Require(double.IsFinite(value), "Nonfinite case value."); return value;
        }).ToArray();
        string dataHash = Str("ordered_binary64_sha256"); Require(Hex(dataHash, 64) && dataHash == DataHash(values), "Ordered binary64 hash mismatch.");
        return new Case(purpose, id, cell, rep, seed, n, m, dataHash, values);
    }
    private static void EnvironmentCheck()
    {
        Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1", "MVS_DISABLE_BACKUPS=1 required.");
        Require(Environment.GetEnvironmentVariable("DOTNET_PROCESSOR_COUNT") == "1" && Environment.ProcessorCount == 1, "DOTNET_PROCESSOR_COUNT=1 required.");
    }
    private static Timing Attempt(Action action, out object? error)
    {
        Process.Refresh(); double cpu = Process.TotalProcessorTime.TotalSeconds; var watch = Stopwatch.StartNew(); error = null;
        try { action(); } catch (Exception ex) { error = Error(ex); }
        watch.Stop(); Process.Refresh(); return new Timing(watch.Elapsed.TotalSeconds, Process.TotalProcessorTime.TotalSeconds - cpu, Process.PeakWorkingSet64);
    }
    private static bool SameRows(IReadOnlyList<Observation> a, IReadOnlyList<Observation> b) => a.Count == b.Count && a.Zip(b).All(p =>
        p.First.Entity == p.Second.Entity && p.First.Group == p.Second.Group && p.First.Sequence == p.Second.Sequence &&
        p.First.Variable == p.Second.Variable && p.First.Unit == p.Second.Unit && BitConverter.DoubleToInt64Bits(p.First.Value) == BitConverter.DoubleToInt64Bits(p.Second.Value));
    private static int Execute(Case input, List<Observation>? literalRows = null)
    {
        EnvironmentCheck(); var identity = Identity(); var total = Stopwatch.StartNew();
        Emit("case_start", new { provenance = identity, case_id = input.Id, ordered_binary64_sha256 = input.Hash,
            scientificStudyExecuted = input.Purpose == "planned_case", processorCount = Environment.ProcessorCount });
        using var cap = new CancellationTokenSource(TimeSpan.FromSeconds(300));
        AnalysisData? data = null; VarianceReport? report = null; object? legacy = null;
        object? buildError = null, varianceError = null, legacyError = null;
        Timing? runTiming = null, legacyTiming = null;
        var observer = Round50.Observer(); phase = "build";
        var buildTiming = Attempt(() => {
            Require(input.Values.All(x => x >= -1000000 && x <= 1000000), "input_retention_mismatch: raw values outside Build bounds; neither method analyzed.");
            var raw = literalRows ?? input.Values.Select((x, k) => new Observation($"E{(k / input.M) % input.N:00}", $"G{k / (input.N * input.M)}", x, k % input.M)).ToList();
            builds++; data = AnalysisEngine.Build(raw, -1000000, 1000000, 2);
            Require(SameRows(raw, data.Observations) && data.ValidRows == input.Values.Length && data.TotalEntities == 2 * input.N &&
                data.GroupCounts.SequenceEqual(new[] { input.N, input.N }) && data.Entities.All(e => e.Measurements == input.M), "input_retention_mismatch: Build changed rows, groups, entities, repeats or binary64 values.");
        }, out buildError);
        if (buildError == null && data != null)
        {
            phase = "variance"; runs++; Round50.SetCall("runCalls", runs);
            runTiming = Attempt(() => report = VarianceAnalysis.RunWithRecording(observer, data, 100, 199, 2, 2, input.Seed, .05, token: cap.Token), out varianceError);
            // The paired summary route is retained even after variance failure/cancellation.
            phase = "legacy"; legacyCalls++; Round50.SetCall("legacyCalls", legacyCalls);
            legacyTiming = Attempt(() => { legacy = Round50.Legacy(data); _ = JsonSerializer.Serialize(legacy, Json); }, out legacyError);
        }
        phase = "serialization"; serializations++;
        var payload = new { schema = "mvs-prospective-case-payload/v1", protocol_id = ProtocolId, protocol_sha256 = ProtocolSha,
            purpose = input.Purpose, case_id = input.Id, cell_index = input.Cell, replication_zero_based = input.Replication,
            native_seed = input.Seed, entities_per_group = input.N, repeats_per_entity = input.M, ordered_binary64_sha256 = input.Hash,
            rawRows = input.Values.Length, retainedRows = data?.ValidRows, entities = data?.TotalEntities, groupCounts = data?.GroupCounts,
            report = Round50.Encode(report), legacy, trace = Round50.Trace(observer), buildError, varianceError, legacyError,
            inputStatus = buildError == null ? "retained_exactly" : "input_retention_mismatch" };
        string serialized = JsonSerializer.Serialize(payload, Json); Process.Refresh();
        Emit("case_complete", new { provenance = identity, payload, buildTiming, runTiming, legacyTiming,
            completed = true, status = buildError != null ? "input_unavailable" : varianceError != null || legacyError != null ? "paired_method_failure_retained" : "paired_methods_returned",
            scientificStudyExecuted = input.Purpose == "planned_case", caseWallSeconds = total.Elapsed.TotalSeconds,
            processTotalCpuSeconds = Process.TotalProcessorTime.TotalSeconds, processPeakWorkingSetBytes = Process.PeakWorkingSet64,
            serializedUtf8Bytes = System.Text.Encoding.UTF8.GetByteCount(serialized) });
        return 0;
    }
    private static int Reference(string size)
    {
        Require(size is "large" or "small", "Reference size must be large or small."); EnvironmentCheck();
        fixtureMaterializations++; var rows = Round50.Fixture(); int cell = size == "large" ? 0 : 10, n = size == "large" ? 16 : 8, m = size == "large" ? 40 : 5;
        if (size == "small") rows = rows.Where(r => int.Parse(r.Entity[1..], CultureInfo.InvariantCulture) < 8 && r.Sequence < 5).ToList();
        var values = rows.Select(r => r.Value).ToArray();
        return Execute(new Case("engineering_literal", $"engineering_literal/C{cell:00}/R0000", cell, 0, 1540000000 + 1000 * cell, n, m, DataHash(values), values), rows);
    }
    private static object Error(Exception ex) => new { type = ex.GetType().FullName, message = ex.Message, stack = ex.StackTrace, inner = ex.InnerException == null ? null : Error(ex.InnerException) };
    private static int Main(string[] args)
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture; CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        try
        {
            if (args.Length == 1 && args[0] == "identity") { mode = "identity"; Emit("identity", Identity()); return 0; }
            if (args.Length == 2 && args[0] == "engineering-reference") { mode = args[0]; return Reference(args[1]); }
            Require(args.Length == 3 && args[0] is "validate-only" or "run-case", "Usage: identity | validate-only CASE SHA256 | run-case CASE SHA256 | engineering-reference large|small.");
            mode = args[0]; phase = "validation"; _ = Identity(); var input = Validate(args[1], args[2]);
            if (mode == "validate-only") { Emit("case_validated", new { valid = true, computationInvoked = false, case_id = input.Id, ordered_binary64_sha256 = input.Hash }); return 0; }
            return Execute(input);
        }
        catch (Exception ex) { Emit("adapter_error", new { completed = false, phase, status = "technical_failure", exception = Error(ex) }, error: true); return 2; }
    }
}
