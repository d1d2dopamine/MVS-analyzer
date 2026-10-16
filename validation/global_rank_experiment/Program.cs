using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.GlobalRankExperiment;

// Test-only executable. No automatic experiment, holdout, production mode, or fallback.
internal static class Program
{
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = false };
    private static readonly CancellationTokenSource Cancellation = new();
    private static readonly string[] FrozenMetrics = { "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad", "normalized_iqr", "mean", "rms", "range", "geometric_mean", "trimmed_mean_20" };
    private static readonly string[] Conditions = { "primary_gait_heavy_tail_null", "gait_normal_null", "gait_heavy_tail_contamination_10pct_null", "voice_lognormal_null", "gait_location_1.05", "gait_dispersion_1.30" };

    public static int Main(string[] args)
    {
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; Cancellation.Cancel(); };
        int? ordinal = null, replication = null;
        string mode = args.FirstOrDefault() ?? "";
        string? output = null;
        FileStream? destination = null;
        var elapsed = Stopwatch.StartNew();
        var process = Process.GetCurrentProcess();
        TimeSpan cpuStart = process.TotalProcessorTime;
        try
        {
            if (mode == "--oracle" && args.Length == 4 && args[2] == "--out") output = args[3];
            else if ((mode == "--case" || mode == "--replay") && args.Length == 5 && args[3] == "--out")
            {
                ordinal = int.Parse(args[1], System.Globalization.CultureInfo.InvariantCulture);
                replication = int.Parse(args[2], System.Globalization.CultureInfo.InvariantCulture);
                output = args[4];
                if (ordinal < 0 || ordinal > 5 || replication < 0 || replication >= (ordinal < 4 ? 200 : 250))
                    throw new ArgumentOutOfRangeException(nameof(args), "Only the frozen development condition/replication coordinates are accepted.");
            }
            else throw new ArgumentException("Usage: --oracle fixtures.json --out NEW.json | --case ORDINAL REPLICATION --out NEW.json | --replay ORDINAL REPLICATION --out NEW.json");
            // Reserve a new output before any scientific computation. Existing evidence is never overwritten.
            destination = new FileStream(output!, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
            Cancellation.Token.ThrowIfCancellationRequested();
            object evidence = mode == "--oracle" ? Oracle(args[1]) : Case(ordinal!.Value, replication!.Value, mode == "--case");
            process.Refresh();
            Write(destination, new { schemaVersion = "mvs-global-rank-native/v1", status = "ok", mode, conditionOrdinal = ordinal, replication,
                evidence, timing = new { totalMs = elapsed.Elapsed.TotalMilliseconds, cpuMs = (process.TotalProcessorTime - cpuStart).TotalMilliseconds, peakWorkingSetBytes = process.PeakWorkingSet64 }, provenance = Provenance() });
            return 0;
        }
        catch (Exception error)
        {
            // Computation failures produce explicit evidence, never substitute an outcome or a new dataset.
            var failure = new { schemaVersion = "mvs-global-rank-native/v1", status = "failed", mode, conditionOrdinal = ordinal, replication,
                error = error.ToString(), elapsedMs = elapsed.Elapsed.TotalMilliseconds };
            if (destination is not null && destination.Position == 0)
            {
                try { Write(destination, failure); } catch (Exception exportError) { Console.Error.WriteLine("Failure evidence export failed: " + exportError); }
            }
            Console.Error.WriteLine(JsonSerializer.Serialize(failure, Json));
            return 1;
        }
        finally { destination?.Dispose(); }
    }

    private static void Write(Stream stream, object value)
    {
        // Serialize before writing so nonfinite/missing values cannot leave a partial-success JSON.
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, Json);
        stream.Write(bytes); stream.Flush();
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static string FileHash(string path) => Hash(File.ReadAllBytes(path));
    private static object Provenance() => new {
        framework = RuntimeInformation.FrameworkDescription, os = RuntimeInformation.OSDescription,
        architecture = RuntimeInformation.ProcessArchitecture.ToString(), runtimeVersion = Environment.Version.ToString(),
        harnessSha256 = FileHash(Assembly.GetExecutingAssembly().Location), coreSha256 = FileHash(typeof(AnalysisEngine).Assembly.Location),
        engineVersion = AnalysisEngine.EngineVersion, drawScheme = "fresh-identity-Fisher-Yates-BenchmarkRandom.Next-first-nCase-with-replacement", draws = 999
    };

    private static object Case(int ordinal, int replication, bool runCandidate)
    {
        int[] stages = { 1, 4, 3, 4, 2, 2 }, streams = { 1, 0, 1, 12, 1, 1 };
        ulong datasetSeed = BenchmarkRandom.Derive(20260904, (ulong)stages[ordinal], (ulong)streams[ordinal], (ulong)replication);
        ulong labelSeed = BenchmarkRandom.Derive(2026102601, 26, (ulong)ordinal, (ulong)replication);
        BenchmarkDesign design = ordinal == 3 ? BenchmarkDatasets.Voice : BenchmarkDatasets.Gait;
        if (ordinal == 1) design = BenchmarkDatasets.WithShape(design, DataShape.Normal);
        InjectionMode injection = ordinal == 4 ? InjectionMode.Location : ordinal == 5 ? InjectionMode.Dispersion : InjectionMode.None;
        double effect = ordinal == 4 ? 1.05 : ordinal == 5 ? 1.30 : 1;
        var watch = Stopwatch.StartNew();
        var observations = BenchmarkDatasets.Generate(design, injection, effect, ordinal == 2 ? .10 : 0, new BenchmarkRandom(datasetSeed));
        Cancellation.Token.ThrowIfCancellationRequested();
        AnalysisData data = AnalysisEngine.Build(observations, -1000000, 1000000, 6);
        ValidateData(data);
        if (data.TotalEntities != 2 * design.EntitiesPerGroup || data.GroupCounts.Any(n => n != design.EntitiesPerGroup) || data.ValidRows != observations.Count)
            throw new InvalidDataException("Unexpected retention in frozen synthetic design.");
        double[][] rows = data.Entities.Select(e => e.Metrics).ToArray();
        int[] cases = data.Entities.Select((e, i) => (e, i)).Where(x => x.e.Group == "case").Select(x => x.i).ToArray();
        if (cases.Length != design.EntitiesPerGroup) throw new InvalidDataException("Case entity mapping mismatch.");
        double preprocessingMs = watch.Elapsed.TotalMilliseconds;
        watch.Restart();
        double[] p = Enumerable.Range(0, 12).Select(j => AnalysisEngine.MannWhitneyP(
            data.Entities.Where(e => e.Group == data.GroupNames[0]).Select(e => e.Metrics[j]).ToArray(),
            data.Entities.Where(e => e.Group == data.GroupNames[1]).Select(e => e.Metrics[j]).ToArray())).ToArray();
        if (p.Any(v => !double.IsFinite(v) || v < 0 || v > 1)) throw new InvalidDataException("Invalid shipped p-value.");
        double[] adjusted = p.Select(v => Math.Min(1, 12 * v)).ToArray();
        double shippedMs = watch.Elapsed.TotalMilliseconds;
        RankKernel.Result? candidate = null;
        double? candidateMs = null;
        if (runCandidate)
        {
            Cancellation.Token.ThrowIfCancellationRequested(); watch.Restart();
            candidate = RankKernel.Prepare(rows, cases.Length).Run(cases, labelSeed, token: Cancellation.Token);
            candidateMs = watch.Elapsed.TotalMilliseconds;
        }
        return new { conditionOrdinal = ordinal, condition = Conditions[ordinal], replication, plannedConditionCount = ordinal < 4 ? 200 : 250,
            datasetSeed, labelSeed, dataMaster = 20260904, dataStage = stages[ordinal], dataStream = streams[ordinal], labelMaster = 2026102601, labelStage = 26,
            metricOrder = MetricRegistry.LegacyKeys, summaryRows = rows, summarySha256 = MatrixHash(rows),
            entities = data.Entities.Select(e => new { e.Entity, e.Group, e.Measurements }), data.GroupNames, data.GroupCounts, data.ValidRows,
            observedCaseIndices = cases, shipped = new { pValues = p, bonferroniAdjustedPValues = adjusted, reject = p.Any(v => v < .05 / 12), metricReject = p.Select(v => v < .05 / 12).ToArray(), rawMetricReject = p.Select(v => v < .05).ToArray() },
            candidate, observedMaximum = candidate?.Observed.Maximum, timing = new { preprocessingMs, shippedMs, candidateMs } };
    }

    // Digest is SHA256 over row-major little-endian IEEE754 binary64, no header.
    private static string MatrixHash(double[][] rows)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[8];
        foreach (double[] row in rows) foreach (double value in row)
        {
            System.Buffers.Binary.BinaryPrimitives.WriteInt64LittleEndian(buffer, BitConverter.DoubleToInt64Bits(value));
            hash.AppendData(buffer);
        }
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }
    private static void ValidateData(AnalysisData data)
    {
        if (data.TotalEntities > 128 || !MetricRegistry.LegacyKeys.SequenceEqual(FrozenMetrics)) throw new InvalidDataException("Frozen metric family or entity bound mismatch.");
        if (data.GroupNames.Length != 2 || data.GroupCounts.Any(n => n < 4)) throw new InvalidDataException("Exactly two groups of at least four retained entities required.");
        if (data.Entities.Any(e => e.Metrics.Length != 12 || e.Metrics.Any(v => !double.IsFinite(v)))) throw new InvalidDataException("Entire case invalid: missing/nonfinite legacy summary slot.");
        foreach (var entity in data.Entities)
        {
            double[] values = data.Observations.Where(o => o.Group.Equals(entity.Group, StringComparison.OrdinalIgnoreCase) && o.Entity.Equals(entity.Entity, StringComparison.OrdinalIgnoreCase)).Select(o => o.Value).ToArray();
            if (values.Length != entity.Measurements || !MetricRegistry.ComputeLegacy(values).SequenceEqual(entity.Metrics)) throw new InvalidDataException("Build/ComputeLegacy mapping mismatch.");
        }
    }

    private static object Oracle(string input)
    {
        if (new FileInfo(input).Length > 4 * 1024 * 1024) throw new ArgumentException("Oracle fixture input exceeds 4 MiB bound.");
        using JsonDocument document = JsonDocument.Parse(File.ReadAllBytes(input));
        JsonElement root = document.RootElement;
        var matrices = new List<object>();
        foreach (var fixture in root.GetProperty("matrixFixtures").EnumerateArray())
        {
            Cancellation.Token.ThrowIfCancellationRequested();
            string id = fixture.GetProperty("id").GetString()!;
            double[][] rows = fixture.GetProperty("rows").Deserialize<double[][]>()!;
            int nCase = fixture.GetProperty("nCase").GetInt32();
            if (!((rows.Length == 4 && nCase == 2) || (rows.Length == 6 && nCase == 2) || (rows.Length == 8 && nCase == 4) || (rows.Length == 9 && nCase == 4) || (rows.Length == 10 && nCase == 5))) throw new InvalidDataException("Oracle dimensions outside frozen sizes.");
            var prepared = RankKernel.Prepare(rows, nCase);
            int[][] assignments = Combinations(rows.Length, nCase).ToArray();
            var scores = assignments.Select(prepared.Score).ToArray();
            var evidence = new List<object>();
            for (int i = 0; i < assignments.Length; i++)
            {
                Cancellation.Token.ThrowIfCancellationRequested();
                var observed = scores[i];
                int global = scores.Count(s => s.Maximum >= observed.Maximum);
                int[] marginal = Enumerable.Range(0, 12).Select(j => scores.Count(s => s.Values[j] >= observed.Values[j])).ToArray();
                int[] max = Enumerable.Range(0, 12).Select(j => scores.Count(s => s.Maximum >= observed.Values[j])).ToArray();
                var other = prepared.EvaluateAssignments(assignments[i], assignments.Where((_, k) => k != i).ToArray(), Cancellation.Token);
                if (other.GlobalExceedanceCount + 1 != global || other.MarginalExceedanceCounts.Where((c, j) => c + 1 != marginal[j]).Any() || other.MaxTExceedanceCounts.Where((c, j) => c + 1 != max[j]).Any())
                    throw new InvalidDataException("Every-other-assignment plus-one identity failed.");
                evidence.Add(new { selected = assignments[i], scores = observed.Values, exactScores = observed.Exact, maxScore = observed.Maximum,
                    globalTailCount = global, marginalTailCounts = marginal, maxTailCounts = max,
                    globalPValue = (double)global / assignments.Length, marginalPValues = marginal.Select(c => (double)c / assignments.Length).ToArray(), maxTAdjustedPValues = max.Select(c => (double)c / assignments.Length).ToArray(), otherAssignmentMaxTP = other.MaxTAdjustedPValues, otherAssignmentsResult = other });
            }
            int[] literalObserved = fixture.GetProperty("observed").Deserialize<int[]>()!;
            int[][] literalDraws = fixture.GetProperty("draws").Deserialize<int[][]>()!;
            var literal = prepared.EvaluateAssignments(literalObserved, literalDraws, Cancellation.Token);
            var drawScores = literalDraws.Select(prepared.Score).ToArray();
            matrices.Add(new { id, nCase, rows, doubledCenteredRanks = prepared.DoubledCenteredRanks, q = prepared.Q, allAssignments = evidence,
                observed = literalObserved, draws = literalDraws, literalDrawResult = literal,
                observedScores = literal.Observed.Values, observedMaxScore = literal.Observed.Maximum,
                drawScores = drawScores.Select(s => s.Values).ToArray(), drawMaxScores = drawScores.Select(s => s.Maximum).ToArray(),
                marginalCounts = literal.MarginalExceedanceCounts, globalCount = literal.GlobalExceedanceCount,
                marginalP = literal.MarginalPValues, globalP = literal.GlobalPValue, maxTCounts = literal.MaxTExceedanceCounts, maxTP = literal.MaxTAdjustedPValues });
        }
        var raws = new List<object>();
        if (root.TryGetProperty("rawFixtures", out var rawFixtures)) foreach (var fixture in rawFixtures.EnumerateArray()) raws.Add(Raw(fixture));
        var failures = new List<object>();
        if (root.TryGetProperty("expectedFailureRawFixtures", out var badRaw)) foreach (var fixture in badRaw.EnumerateArray())
        {
            RawStageException? rejection = null;
            try { Raw(fixture); } catch (RawStageException e) { rejection = e; }
            if (rejection is null) throw new InvalidDataException("Expected raw fixture failure did not occur: " + fixture.GetProperty("id").GetString());
            string expectedStage = fixture.GetProperty("expectedFailureStage").GetString()!;
            if (rejection.Stage != expectedStage) throw new InvalidDataException("Raw fixture failed at an unexpected stage: " + rejection.Stage);
            failures.Add(new { id = fixture.GetProperty("id").GetString(), status = "rejected", stage = rejection.Stage, expectedFailureStage = expectedStage, error = rejection.Message });
        }
        return new { fixtureSha256 = FileHash(input), metricOrder = MetricRegistry.LegacyKeys, matrixFixtures = matrices, rawFixtures = raws, expectedFailureRawFixtures = failures, invalidInputChecks = InvalidChecks() };
    }
    private sealed class RawStageException : Exception
    {
        internal string Stage { get; }
        internal RawStageException(string stage, string message) : base(message) { Stage = stage; }
    }
    private static object Raw(JsonElement fixture)
    {
        Cancellation.Token.ThrowIfCancellationRequested();
        var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true, NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.AllowNamedFloatingPointLiterals };
        var observations = fixture.GetProperty("observations").Deserialize<List<Observation>>(options)!;
        AnalysisData data;
        try { data = AnalysisEngine.Build(observations, -1000000, 1000000, 6); }
        catch (InvalidDataException e) when (e.Message.StartsWith("Every group needs at least four entities", StringComparison.Ordinal))
        { throw new RawStageException("Build", e.Message); }
        // Only the expected unavailable geometric-mean slot establishes this failure stage.
        // Parsing, registry/mapping, retention, and unrelated Build failures remain fatal.
        if (data.Entities.Any(e => e.Metrics.Length == 12 && !double.IsFinite(e.Metrics[10])))
            throw new RawStageException("complete-summary-validation", "nonfinite geometric_mean slot invalidates entire candidate case");
        ValidateData(data);
        if (fixture.TryGetProperty("expectedValidRows", out var expectedRows) && data.ValidRows != expectedRows.GetInt32()) throw new InvalidDataException("Raw retained measurement count mismatch.");
        if (fixture.TryGetProperty("expectedRetainedCount", out var count) && data.TotalEntities != count.GetInt32()) throw new InvalidDataException("Raw retained entity count mismatch.");
        if (fixture.TryGetProperty("expectedRetainedEntities", out var expected))
        {
            var actual = data.Entities.Select(e => (e.Entity, e.Group)).ToArray();
            var wanted = expected.EnumerateArray().Select(e => (e.GetProperty("Entity").GetString()!, e.GetProperty("Group").GetString()!)).ToArray();
            if (!actual.SequenceEqual(wanted)) throw new InvalidDataException("Raw retained entity order/mapping mismatch.");
        }
        double[][] rows = data.Entities.Select(e => e.Metrics).ToArray();
        return new { id = fixture.GetProperty("id").GetString(), status = "ok", summaryRows = rows, summarySha256 = MatrixHash(rows),
            entities = data.Entities.Select(e => new { e.Entity, e.Group, e.Measurements }), data.GroupNames, data.GroupCounts, data.ValidRows };
    }
    private static object[] InvalidChecks()
    {
        double[][] Good() => Enumerable.Range(0, 8).Select(i => Enumerable.Repeat((double)i, 12).ToArray()).ToArray();
        var checks = new List<object>();
        void Check(string id, Action action)
        {
            bool rejected = false;
            try { action(); } catch (ArgumentException) { rejected = true; }
            if (!rejected) throw new InvalidDataException("Invalid-input check unexpectedly accepted: " + id);
            checks.Add(new { id, rejected });
        }
        Check("null_rows", () => RankKernel.Prepare(null!, 4));
        Check("null_row", () => { var a = Good(); a[0] = null!; RankKernel.Prepare(a, 4); });
        Check("missing_slot", () => { var a = Good(); a[0] = new double[11]; RankKernel.Prepare(a, 4); });
        foreach (double invalid in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity })
            Check("nonfinite_" + invalid, () => { var a = Good(); a[0][0] = invalid; RankKernel.Prepare(a, 4); });
        var prepared = RankKernel.Prepare(Good(), 4);
        Check("duplicate_index", () => prepared.Score(new[] { 0, 0, 1, 2 }));
        Check("wrong_group_size", () => prepared.Score(new[] { 0, 1, 2 }));
        Check("out_of_range_index", () => prepared.Score(new[] { 0, 1, 2, 8 }));
        Check("null_draws", () => prepared.EvaluateAssignments(new[] { 0, 1, 2, 3 }, null!));
        Check("missing_draw", () => prepared.EvaluateAssignments(new[] { 0, 1, 2, 3 }, new int[][] { null! }));
        return checks.ToArray();
    }
    private static IEnumerable<int[]> Combinations(int n, int k)
    {
        int[] indices = Enumerable.Range(0, k).ToArray();
        while (true)
        {
            yield return (int[])indices.Clone();
            int position = k - 1;
            while (position >= 0 && indices[position] == n - k + position) position--;
            if (position < 0) yield break;
            indices[position]++;
            for (int j = position + 1; j < k; j++) indices[j] = indices[j - 1] + 1;
        }
    }
}
