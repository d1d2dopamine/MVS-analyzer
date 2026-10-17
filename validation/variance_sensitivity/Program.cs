using System.Collections;
using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

namespace MvsVarianceSensitivity;

// Engineering-only harness. Production computations and default recording factory are unchanged.
internal static class Program
{
    private const string ProtocolId = "round50-variance-cost-v1";
    private static readonly JsonSerializerOptions Json = new();
    private static int runCalls, legacyCalls, fixtureMaterializations;
    private static readonly Process Process = Process.GetCurrentProcess();
    private sealed record Timing(double WallSeconds, double CpuSeconds, long PeakWorkingSetBytes);
    private sealed record ObservationEvent(string Key, int CallbackCount, bool Returned, bool? Finite, bool? Converged, bool? AtBoundary, object? Value, object? Exception);
    private sealed class Observer : IRunRecordingFactory
    {
        internal readonly List<ObservationEvent> Events = new();
        internal int Begins, Finishes, Disposals, RestoreHits;
        public IRunRecording Begin(BackupRequest request)
        {
            Begins++;
            return new Session(PortableRunRecordingFactory.Instance.Begin(request), this);
        }
        private sealed class Session(IRunRecording inner, Observer owner) : IRunRecording
        {
            public bool EnvironmentChanged => inner.EnvironmentChanged;
            public bool Try<T>(string key, out T value)
            {
                bool hit = inner.Try(key, out value);
                if (hit) owner.RestoreHits++;
                Emit(new { kind = "try", call = runCalls, key, hit });
                return hit;
            }
            public T Cached<T>(string key, Func<T> calculate)
            {
                int callbacks = 0;
                try
                {
                    T value = inner.Cached(key, () => { callbacks++; return calculate(); });
                    bool? finite = value is double d ? double.IsFinite(d) : value is VarianceFit f ? f.Means.Concat(f.Within).Concat(f.Between).Append(f.NegativeLogLikelihood).All(double.IsFinite) : null;
                    var row = new ObservationEvent(key, callbacks, true, finite, value is VarianceFit fit ? fit.Converged : null, value is VarianceFit fit2 ? fit2.AtBoundary : null, Encode(value), null);
                    owner.Events.Add(row); Emit(new { kind = "cached", call = runCalls, observation = row });
                    return value;
                }
                catch (Exception ex)
                {
                    var row = new ObservationEvent(key, callbacks, false, null, null, null, null, Error(ex));
                    owner.Events.Add(row); Emit(new { kind = "cached", call = runCalls, observation = row }); throw;
                }
            }
            public void Put<T>(string key, T value) => inner.Put(key, value);
            public T Finish<T>(T value) { owner.Finishes++; return inner.Finish(value); }
            public void Dispose() { owner.Disposals++; inner.Dispose(); }
        }
    }
    private static Timing Measure(Action action)
    {
        Process.Refresh(); double cpu = Process.TotalProcessorTime.TotalSeconds; var wall = Stopwatch.StartNew();
        action(); wall.Stop(); Process.Refresh();
        return new Timing(wall.Elapsed.TotalSeconds, Process.TotalProcessorTime.TotalSeconds - cpu, Process.PeakWorkingSet64);
    }
    private static List<Observation> Fixture()
    {
        fixtureMaterializations++;
        var rows = new List<Observation>(1280);
        for (int g = 0; g < 2; g++) for (int i = 0; i < 16; i++) for (int j = 0; j < 40; j++)
        {
            double u = (i - 7.5) / Math.Sqrt(21.25), v = (j - 19.5) / Math.Sqrt(133.25), a = 1 + .02 * ((i % 3) - 1);
            double y = 20 + 2 * g + (1 + .5 * g) * u + (1 + .5 * g) * a * v;
            rows.Add(new Observation($"E{i:00}", $"G{g}", y, j));
        }
        return rows;
    }
    private static object Legacy(AnalysisData data)
    {
        Require(AnalysisEngine.MetricKeys.SequenceEqual(new[] { "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad", "normalized_iqr", "mean", "rms", "range", "geometric_mean", "trimmed_mean_20" }), "Legacy family/order changed.");
        // Recompute through the shipped metric seam, so this phase includes metric work.
        var entities = data.Observations.GroupBy(o => AnalysisEngine.Key(o.Group, o.Entity), StringComparer.OrdinalIgnoreCase)
            .Select(g => new { group = g.First().Group, entity = g.First().Entity, metrics = AnalysisEngine.Metrics(g.Select(o => o.Value).ToArray()) }).ToArray();
        var availability = MetricAvailability.Describe(data);
        var metrics = Enumerable.Range(0, 12).Select(m =>
        {
            double[] a = entities.Where(e => e.group == "G0").Select(e => e.metrics[m]).Where(double.IsFinite).ToArray();
            double[] b = entities.Where(e => e.group == "G1").Select(e => e.metrics[m]).Where(double.IsFinite).ToArray();
            bool applicable = a.Length >= MetricAvailability.MinimumEntitiesPerGroup && b.Length >= MetricAvailability.MinimumEntitiesPerGroup;
            string observedStatus = applicable ? "available" : "insufficient_usable_entities";
            double p = applicable ? AnalysisEngine.MannWhitneyP(a, b) : double.NaN;
            if (applicable && !double.IsFinite(p)) { applicable = false; observedStatus = "rank_test_unavailable"; }
            double adjusted = DecisionPolicy.Adjust(p, 12);
            return new { index = m, key = AnalysisEngine.MetricKeys[m], firstCount = a.Length, secondCount = b.Length,
                applicable, observedStatus, groupAvailability = availability[m], p = Fp(p), adjustedP = Fp(adjusted), reject = double.IsFinite(adjusted) && adjusted < .05 };
        }).ToArray();
        return new { familySize = 12, alpha = .05, method = "production Metrics/MannWhitneyP/DecisionPolicy.Adjust", entities = entities.Select(e => new { e.group, e.entity, metrics = Encode(e.metrics) }), metrics, anyReject = metrics.Any(m => m.reject) };
    }
    private static object Complete(Observer observer, VarianceReport report)
    {
        var expected = new List<string> { "initial-fit" };
        for (int i = 0; i < 100; i++) expected.Add("interval/" + i);
        foreach (string track in new[] { "within", "between" })
        {
            expected.Add(track + "/null-fit"); expected.Add(track + "/observed");
            for (int i = 0; i < 199; i++) expected.Add(track + "/reference/" + i);
            for (int i = 0; i < 100; i++) foreach (string branch in new[] { "null", "alternative", "grid" }) expected.Add(track + "/" + branch + "/" + i);
        }
        bool keys = observer.Events.Count == expected.Count && expected.SequenceEqual(observer.Events.Select(e => e.Key), StringComparer.Ordinal);
        bool callbacks = observer.Events.All(e => e.CallbackCount == 1 && e.Returned);
        bool initial = observer.Events.Any(e => e.Key == "initial-fit" && e.Converged == true && e.Finite == true);
        bool nullFits = new[] { "within", "between" }.All(t => observer.Events.Any(e => e.Key == t + "/null-fit" && e.Converged == true && e.Finite == true));
        bool statistics = observer.Events.Where(e => e.Converged == null).All(e => e.Finite == true);
        bool ownership = observer.Begins == 1 && observer.Finishes == 1 && observer.Disposals == 1 && observer.RestoreHits == 0;
        bool reports = report.Tracks.Length == 2 && report.Tracks.All(t => t.ReferenceReplications == 199 && t.ReferenceFailures == 0 && t.EvaluationReplications == 100 && t.NullFailures == 0 && t.AlternativeFailures == 0);
        bool certified = keys && callbacks && initial && nullFits && statistics && ownership && reports;
        var summary = new { certified, exactKeys = keys, allCallbacksExecutedOnce = callbacks, initialConvergedFinite = initial, nullFitsConvergedFinite = nullFits, allObservedReferenceEvaluationGridStatisticsFinite = statistics, normalOwnershipNoRestore = ownership, reportCountsComplete = reports, expectedCachedRequests = expected.Count, actualCachedRequests = observer.Events.Count,
            intervalConvergedCount = observer.Events.Count(e => e.Key.StartsWith("interval/") && e.Converged == true), intervalFiniteCount = observer.Events.Count(e => e.Key.StartsWith("interval/") && e.Finite == true),
            missingKeys = expected.Except(observer.Events.Select(e => e.Key)).ToArray() };
        Emit(new { kind = "completeness", call = runCalls, summary });
        Require(certified, "Cost-unrepresentative: completeness criterion failed; no replacement or second call permitted.");
        return summary;
    }
    private static int Main(string[] args)
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture; CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        try
        {
            if (args.Length == 1 && args[0] == "identity") { Emit(new { kind = "identity", protocolId = ProtocolId, identity = Identity(), fixtureMaterializationCount = 0, runCallCount = 0, legacyCallCount = 0, generateCallCount = 0, fitCallCount = 0 }); return 0; }
            if (args.Length == 3 && args[0] == "worker") return Worker(args);
            if (args.Length == 3 && args[0] == "legacy-seam-preflight") return LegacyPreflight(args);
            Require(args.Length == 3 && args[0] == "cost", "Usage: identity | cost FROZEN_PROTOCOL_JSON EXPECTED_SHA256. Science mode is unavailable pending separate freeze.");
            Require(args[2].Length == 64 && args[2].All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'), "Invalid SHA256.");
            Require(new FileInfo(args[1]).Length <= 16384, "Protocol exceeds 16 KiB.");
            byte[] bytes = File.ReadAllBytes(args[1]); Require(Sha(bytes) == args[2], "Protocol SHA256 mismatch.");
            using var doc = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 4 });
            var expected = new Dictionary<string, object> { ["schemaVersion"] = 1, ["protocolId"] = ProtocolId, ["status"] = "frozen", ["groups"] = 2, ["entitiesPerGroup"] = 16, ["repeats"] = 40, ["repetitions"] = 100, ["referenceReplications"] = 199, ["withinEffect"] = 2, ["betweenEffect"] = 2, ["alpha"] = .05, ["seed"] = 52000000, ["calls"] = 2, ["wallCapSeconds"] = 180 };
            var properties = doc.RootElement.EnumerateObject().ToArray();
            Require(properties.Length == expected.Count && properties.Select(p => p.Name).Distinct(StringComparer.Ordinal).Count() == expected.Count && properties.All(p => expected.ContainsKey(p.Name)), "Protocol keys differ or duplicate.");
            foreach (var kv in expected) Require(kv.Value is string s ? doc.RootElement.GetProperty(kv.Key).GetString() == s : doc.RootElement.GetProperty(kv.Key).GetDouble() == Convert.ToDouble(kv.Value, CultureInfo.InvariantCulture), "Frozen protocol value differs: " + kv.Key);
            Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1", "MVS_DISABLE_BACKUPS=1 is required.");
            Require(Environment.ProcessorCount == 1, "A one-core runtime cap is required.");
            Emit(new { kind = "start", protocolId = ProtocolId, protocolSha256 = Sha(bytes), identity = Identity(), processorCount = Environment.ProcessorCount, recording = "production default factory decorated; backups disabled" });
            using var cap = new CancellationTokenSource(TimeSpan.FromSeconds(180)); var total = Stopwatch.StartNew();
            List<Observation> raw = null!; AnalysisData data = null!;
            Timing build = Measure(() => { raw = Fixture(); data = AnalysisEngine.Build(raw, -1000000, 1000000, 2); Require(data.Observations.SequenceEqual(raw) && data.ValidRows == 1280 && data.TotalEntities == 32 && data.GroupCounts.SequenceEqual(new[] { 16, 16 }), "Build changed fixed input."); });
            string dataHash = Sha(JsonSerializer.SerializeToUtf8Bytes(Encode(raw), Json));
            Emit(new { kind = "fixture", dataSha256 = dataHash, observations = Encode(raw), rawRows = raw.Count, retainedRows = data.ValidRows, entities = data.TotalEntities, data.GroupCounts, buildTiming = build });
            for (int call = 1; call <= 2; call++)
            {
                cap.Token.ThrowIfCancellationRequested(); var observer = new Observer(); VarianceReport report = null!;
                runCalls++;
                Timing run = Measure(() => report = VarianceAnalysis.RunWithRecording(observer, data, 100, 199, 2, 2, 52000000, .05, token: cap.Token));
                Emit(new { kind = "variance_returned", call, runTiming = run, report = Encode(report) });
                object complete = Complete(observer, report);
                cap.Token.ThrowIfCancellationRequested(); object legacy = null!; string legacyJson = ""; legacyCalls++;
                Timing legacyTiming = Measure(() => { legacy = Legacy(data); legacyJson = JsonSerializer.Serialize(legacy, Json); });
                string serialized = "";
                Timing serialization = Measure(() => serialized = JsonSerializer.Serialize(new { call, dataSha256 = dataHash, report = Encode(report), legacy, completeness = complete }, Json));
                Emit(new { kind = "call_complete", call, runTiming = run, legacyTiming, serializationTiming = serialization, serializedUtf8Bytes = System.Text.Encoding.UTF8.GetByteCount(serialized), legacySerializedUtf8Bytes = System.Text.Encoding.UTF8.GetByteCount(legacyJson), payload = JsonSerializer.Deserialize<JsonElement>(serialized) });
                cap.Token.ThrowIfCancellationRequested();
            }
            Process.Refresh(); Emit(new { kind = "complete", status = "engineering_cost_only", runCallCount = runCalls, legacyCallCount = legacyCalls, nativeTotalWallSeconds = total.Elapsed.TotalSeconds, processTotalCpuSeconds = Process.TotalProcessorTime.TotalSeconds, processPeakWorkingSetBytes = Process.PeakWorkingSet64 }); return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(JsonSerializer.Serialize(new { kind = "error", status = ex is OperationCanceledException ? "timeout" : "input_or_harness_error", fixtureMaterializationCount = fixtureMaterializations, runCallCount = runCalls, legacyCallCount = legacyCalls, candidateInvoked = runCalls != 0, exception = Error(ex) }, Json)); return 2; }
    }
    private sealed class SilentProgress : IProgress<ProgressInfo> { public void Report(ProgressInfo value) { } }
    private static int LegacyPreflight(string[] args)
    {
        Require(new FileInfo(args[1]).Length <= 16384, "Preflight exceeds 16 KiB.");
        byte[] bytes = File.ReadAllBytes(args[1]);
        Require(Sha(bytes) == args[2] && args[2] == "60b3cfc228884167ab393077024bcb0b878b2bfa72fbaf75cf1c925517be59fb", "Preflight freeze hash mismatch.");
        Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1", "Backups must be disabled.");
        var comparisons = new List<object>();
        for (int c = 0; c < 2; c++)
        {
            var observations = new List<Observation>();
            for (int g = 0; g < 2; g++) for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++)
            {
                double x = 10 + 2 * g + i + (1 + .1 * i) * j;
                if (c == 1 && g == 0 && i < 2) x = -x;
                observations.Add(new Observation($"E{i:00}", $"G{g}", x, j));
            }
            var data = AnalysisEngine.Build(observations, -1000000, 1000000, 2);
            Require(data.ValidRows == 32 && data.TotalEntities == 8 && data.Observations.SequenceEqual(observations), "Preflight input retention changed.");
            legacyCalls++; var observed = JsonSerializer.SerializeToElement(Legacy(data), Json);
            var calibration = AnalysisEngine.MetricKeys.Select(k => new CalibrationRow(k, .05, 0, 0)).ToList();
            var production = AnalysisEngine.Results(data, calibration, new SilentProgress(), CancellationToken.None, .05, .147, 52000001 + c);
            Require(production.Count == 12, "Production Results family changed.");
            var metricRows = observed.GetProperty("metrics").EnumerateArray().ToArray();
            for (int m = 0; m < 12; m++)
            {
                var local = metricRows[m]; var actual = production.Single(r => r.Metric == local.GetProperty("key").GetString());
                Require(actual.Metric == local.GetProperty("key").GetString() && actual.Applicable == local.GetProperty("applicable").GetBoolean() && actual.ObservedStatus == local.GetProperty("observedStatus").GetString(), "Legacy metadata parity failed.");
                Require(JsonSerializer.Serialize(Fp(actual.PValue), Json) == local.GetProperty("p").GetRawText() && JsonSerializer.Serialize(Fp(actual.AdjustedP), Json) == local.GetProperty("adjustedP").GetRawText(), "Legacy exact floating parity failed.");
                Require(JsonSerializer.Serialize(actual.GroupAvailability, Json) == local.GetProperty("groupAvailability").GetRawText(), "Legacy availability parity failed.");
            }
            Require(c == 0 ? production.All(r => r.Applicable) : production.Single(r => r.Metric == "geometric_mean").ObservedStatus == "insufficient_usable_entities", "Expected availability branch not exercised.");
            var comparison = new { caseIndex = c, observations = Encode(observations), legacy = observed, production = Encode(production), exactParity = true };
            comparisons.Add(comparison); Emit(new { kind = "legacy_seam_case", comparison });
        }
        Emit(new { kind = "legacy_seam_preflight", planSha256 = Sha(bytes), identity = Identity(), comparisons, resultsCallCount = 2, buildCallCount = 2, legacyCallCount = legacyCalls, runCallCount = 0, varianceFitCallCount = 0, calibrationCallCount = 0, maximumIntervalBootstrapReplications = 105600 });
        return 0;
    }
    private static int Worker(string[] args)
    {
        Require(new FileInfo(args[1]).Length <= 256 * 1024, "Science protocol exceeds 256 KiB.");
        Require(args[2].Length == 64 && args[2].All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'), "Invalid protocol SHA256.");
        byte[] protocolBytes = File.ReadAllBytes(args[1]); Require(Sha(protocolBytes) == args[2], "Science protocol SHA256 mismatch.");
        using var protocol = JsonDocument.Parse(protocolBytes, new JsonDocumentOptions { MaxDepth = 16 });
        ValidateScienceProtocol(protocol.RootElement);
        Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1", "MVS_DISABLE_BACKUPS=1 is required.");
        Require(Environment.ProcessorCount == 1, "Single-core runtime required.");
        Emit(new { kind = "worker_ready", protocolSha256 = args[2], identity = Identity(), processId = Environment.ProcessId, processorCount = Environment.ProcessorCount });
        var seen = new HashSet<(int, int)>();
        while (ReadBoundedLine() is { } line)
        {
            using var document = JsonDocument.Parse(line, new JsonDocumentOptions { MaxDepth = 6 });
            var root = document.RootElement;
            Require(root.ValueKind == JsonValueKind.Object, "Case must be an object.");
            var properties = root.EnumerateObject().ToArray();
            string[] fields = { "condition", "replicate", "seed", "dataSha256", "values" };
            Require(properties.Length == fields.Length && properties.Select(p => p.Name).Distinct(StringComparer.Ordinal).Count() == fields.Length && fields.All(f => root.TryGetProperty(f, out _)), "Case fields differ or duplicate.");
            int condition = root.GetProperty("condition").GetInt32(), replicate = root.GetProperty("replicate").GetInt32(), seed = root.GetProperty("seed").GetInt32();
            Require(condition is >= 0 and < 6 && replicate is >= 0 and < 32 && seed == 50000000 + 1000 * condition + replicate, "Unplanned case coordinate or seed.");
            Require(seen.Add((condition, replicate)), "Duplicate case in worker.");
            var array = root.GetProperty("values"); Require(array.ValueKind == JsonValueKind.Array && array.GetArrayLength() == 1280, "Exactly 1280 supplied values required.");
            double[] values = array.EnumerateArray().Select(ReadValue).ToArray();
            byte[] binary = new byte[values.Length * 8];
            for (int i = 0; i < values.Length; i++) System.Buffers.Binary.BinaryPrimitives.WriteInt64LittleEndian(binary.AsSpan(i * 8, 8), BitConverter.DoubleToInt64Bits(values[i]));
            string dataHash = Sha(binary); Require(root.GetProperty("dataSha256").GetString() == dataHash, "Binary64 input hash mismatch.");
            Emit(new { kind = "case_start", condition, replicate, seed, dataSha256 = dataHash, rawRows = values.Length });
            var total = Stopwatch.StartNew(); Process.Refresh(); double cpuStart = Process.TotalProcessorTime.TotalSeconds;
            AnalysisData? data = null; VarianceReport? report = null; object? legacy = null; object? buildError = null, varianceError = null, legacyError = null;
            Timing? buildTiming = null, runTiming = null, legacyTiming = null; var observer = new Observer();
            bool validInput = values.All(x => double.IsFinite(x) && x >= -1000000 && x <= 1000000);
            if (validInput)
            {
                buildTiming = MeasureAttempt(() =>
                {
                    var raw = values.Select((x, k) => new Observation($"E{(k / 40) % 16:00}", $"G{k / 640}", x, k % 40)).ToList();
                    data = AnalysisEngine.Build(raw, -1000000, 1000000, 2);
                    Require(data.Observations.SequenceEqual(raw) && data.ValidRows == 1280 && data.TotalEntities == 32 && data.GroupCounts.SequenceEqual(new[] { 16, 16 }) && data.Entities.All(e => e.Measurements == 40), "input_retention_mismatch");
                }, out buildError);
            }
            else buildError = new { type = "input_retention_mismatch", message = "Raw values nonfinite or outside frozen Build bounds; neither route analyzed." };
            if (buildError == null && data != null)
            {
                runCalls++;
                runTiming = MeasureAttempt(() => report = VarianceAnalysis.RunWithRecording(observer, data, 100, 199, 2, 2, seed, .05), out varianceError);
                // Both paired procedures retain their outcome independently, even if the other fails.
                legacyCalls++;
                legacyTiming = MeasureAttempt(() => { legacy = Legacy(data); _ = JsonSerializer.Serialize(legacy, Json); }, out legacyError);
            }
            var trace = TraceSummary(observer);
            string serialized = "";
            Timing serializationTiming = Measure(() => serialized = JsonSerializer.Serialize(new { condition, replicate, seed, dataSha256 = dataHash,
                rawRows = 1280, retainedRows = data?.ValidRows, entities = data?.TotalEntities, groupCounts = data?.GroupCounts,
                report = Encode(report), legacy, trace, buildError, varianceError, legacyError,
                inputStatus = buildError == null ? "retained_exactly" : "input_retention_mismatch" }, Json));
            Process.Refresh();
            Emit(new { kind = "case_complete", condition, replicate, seed, dataSha256 = dataHash, buildTiming, runTiming, legacyTiming, serializationTiming,
                caseWallSeconds = total.Elapsed.TotalSeconds, caseCpuSeconds = Process.TotalProcessorTime.TotalSeconds - cpuStart,
                processPeakWorkingSetBytes = Process.PeakWorkingSet64, serializedUtf8Bytes = System.Text.Encoding.UTF8.GetByteCount(serialized), payload = JsonSerializer.Deserialize<JsonElement>(serialized) });
        }
        Process.Refresh(); Emit(new { kind = "worker_complete", cases = seen.Count, runCallCount = runCalls, legacyCallCount = legacyCalls, processTotalCpuSeconds = Process.TotalProcessorTime.TotalSeconds, processPeakWorkingSetBytes = Process.PeakWorkingSet64 });
        return 0;
    }
    private static void ValidateScienceProtocol(JsonElement protocol)
    {
        // The host pins the full reviewed manifest hash. These checks also prevent count/config drift.
        Require(protocol.GetProperty("schema").GetString() == "mvs-round50-science-protocol/v1" && protocol.GetProperty("status").GetString() == "frozen" && protocol.GetProperty("protocol_id").GetString() == "round50-small-paired-variance-legacy-v1", "Unfrozen or different science protocol.");
        var design = protocol.GetProperty("design");
        foreach (var pair in new Dictionary<string, int> { ["entities_per_group"] = 16, ["repeats_per_entity"] = 40, ["total_entities"] = 32, ["total_observations"] = 1280, ["min_value"] = -1000000, ["max_value"] = 1000000, ["min_measurements"] = 2, ["outer_per_condition"] = 32, ["condition_count"] = 6, ["total_paired_datasets"] = 192 })
            Require(design.GetProperty(pair.Key).GetInt32() == pair.Value, "Science design drift: " + pair.Key);
        Require(design.GetProperty("groups").EnumerateArray().Select(e => e.GetString()).SequenceEqual(new[] { "G0", "G1" }) && design.GetProperty("entity_ids").EnumerateArray().Select(e => e.GetString()).SequenceEqual(Enumerable.Range(0, 16).Select(i => $"E{i:00}")), "Group/entity identity drift.");
        var run = protocol.GetProperty("variance_run");
        foreach (var pair in new Dictionary<string, double> { ["repetitions"] = 100, ["reference_replications"] = 199, ["within_effect"] = 2, ["between_effect"] = 2, ["alpha"] = .05 }) Require(run.GetProperty(pair.Key).GetDouble() == pair.Value, "Science Run configuration drift.");
        var tasks = protocol.GetProperty("tasks").EnumerateArray().ToArray(); Require(tasks.Length == 192, "Exactly 192 tasks required.");
        for (int i = 0; i < 192; i++)
        {
            int c = i % 6, r = i / 6; var task = tasks[i];
            Require(task.GetProperty("task_index").GetInt32() == i && task.GetProperty("condition_index").GetInt32() == c && task.GetProperty("replicate").GetInt32() == r && task.GetProperty("variance_seed").GetInt32() == 50000000 + 1000 * c + r && task.GetProperty("legacy_seed").GetInt32() == 51000000 + 1000 * c + r, "Task schedule or seed drift.");
            Require(task.GetProperty("outer_seed_sequence").EnumerateArray().Select(v => v.GetInt32()).SequenceEqual(new[] { 20261017, 50, 50001, c, r }), "Outer seed coordinate drift.");
        }
    }
    private static string? ReadBoundedLine()
    {
        var text = new System.Text.StringBuilder();
        while (true)
        {
            int c = Console.In.Read(); if (c == -1) return text.Length == 0 ? null : text.ToString();
            if (c == '\n') return text.ToString();
            Require(text.Length < 256 * 1024, "Case line exceeds 256 KiB."); text.Append((char)c);
        }
    }
    private static double ReadValue(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Number) return element.GetDouble();
        // Exceptional raw values retain the precise binary64 payload instead of a NaN canonicalization.
        Require(element.ValueKind == JsonValueKind.Object && element.EnumerateObject().Count() == 1 && element.TryGetProperty("bits", out _), "Invalid floating literal.");
        string bits = element.GetProperty("bits").GetString() ?? "";
        Require(bits.Length == 16 && bits.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'), "Invalid binary64 bits.");
        double value = BitConverter.Int64BitsToDouble(unchecked((long)ulong.Parse(bits, NumberStyles.HexNumber, CultureInfo.InvariantCulture)));
        Require(!double.IsFinite(value), "Only nonfinite inputs use explicit bits."); return value;
    }
    private static Timing MeasureAttempt(Action action, out object? error)
    {
        Process.Refresh(); double cpu = Process.TotalProcessorTime.TotalSeconds; var watch = Stopwatch.StartNew(); error = null;
        try { action(); } catch (Exception ex) { error = Error(ex); }
        watch.Stop(); Process.Refresh(); return new Timing(watch.Elapsed.TotalSeconds, Process.TotalProcessorTime.TotalSeconds - cpu, Process.PeakWorkingSet64);
    }
    private static object TraceSummary(Observer observer)
    {
        object Branch(string prefix)
        {
            var rows = observer.Events.Where(e => e.Key.StartsWith(prefix, StringComparison.Ordinal)).ToArray();
            return new { attempted = rows.Length, callbacks = rows.Sum(e => e.CallbackCount), returned = rows.Count(e => e.Returned), finite = rows.Count(e => e.Finite == true), nonfinite = rows.Count(e => e.Returned && e.Finite == false), converged = rows.Count(e => e.Converged == true), exceptions = rows.Count(e => !e.Returned) };
        }
        return new { cachedRequests = observer.Events.Count, callbackCount = observer.Events.Sum(e => e.CallbackCount), observer.Begins, observer.Finishes, observer.Disposals, observer.RestoreHits,
            initial = Branch("initial-fit"), interval = Branch("interval/"), tracks = new[] { "within", "between" }.Select(t => new { track = t, nullFit = Branch(t + "/null-fit"), observed = Branch(t + "/observed"), reference = Branch(t + "/reference/"), nullEvaluation = Branch(t + "/null/"), alternative = Branch(t + "/alternative/"), grid = Branch(t + "/grid/") }),
            sourceDerivedFitEntryUpperLimit = 2103, sourceDerivedOptimizerInvocationUpperLimit = 4206, countInterpretation = "Upper bounds from production control flow, not measured optimizer counts; actual failures and skipped branches retained." };
    }
    private static void Emit(object row) { Console.WriteLine(JsonSerializer.Serialize(row, Json)); Console.Out.Flush(); }
    private static object? Encode(object? value)
    {
        if (value == null) return null; if (value is double d) return Fp(d); if (value is string or bool or int or long) return value;
        if (value is IEnumerable array) return array.Cast<object?>().Select(Encode).ToArray();
        return value.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance).ToDictionary(p => char.ToLowerInvariant(p.Name[0]) + p.Name[1..], p => Encode(p.GetValue(value)), StringComparer.Ordinal);
    }
    private static object Fp(double value) => new { classification = double.IsNaN(value) ? "nan" : double.IsPositiveInfinity(value) ? "positive_infinity" : double.IsNegativeInfinity(value) ? "negative_infinity" : "finite", value = double.IsFinite(value) ? (double?)value : null, bits = unchecked((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("x16", CultureInfo.InvariantCulture) };
    private static object Error(Exception ex) => new { type = ex.GetType().FullName, message = ex.Message };
    private static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static void Require(bool condition, string message) { if (!condition) throw new InvalidDataException(message); }
    private static object Identity()
    {
        var assembly = typeof(Program).Assembly; var source = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (string name in assembly.GetManifestResourceNames().Where(n => n.StartsWith("source/", StringComparison.Ordinal)))
        { using var stream = assembly.GetManifestResourceStream(name)!; source.Add(name[7..], Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()); }
        Require(source.Count == 14, "Fourteen build-time source identities required.");
        return new { experimental = true, sourceIdentityScope = "Embedded build-time source bytes, not the complete source tree", sourceSha256 = source,
            runtime = new { framework = RuntimeInformation.FrameworkDescription, version = Environment.Version.ToString(), os = RuntimeInformation.OSDescription, processArchitecture = RuntimeInformation.ProcessArchitecture.ToString(), coreLibrarySha256 = Sha(File.ReadAllBytes(typeof(object).Assembly.Location)) }, harnessAssembly = AssemblyIdentity(assembly), coreAssembly = AssemblyIdentity(typeof(VarianceAnalysis).Assembly) };
    }
    private static object AssemblyIdentity(Assembly assembly) => new { name = assembly.GetName().Name, version = assembly.GetName().Version?.ToString(), moduleVersionId = assembly.ManifestModule.ModuleVersionId.ToString("D"), fileName = Path.GetFileName(assembly.Location), sha256 = Sha(File.ReadAllBytes(assembly.Location)) };
}
