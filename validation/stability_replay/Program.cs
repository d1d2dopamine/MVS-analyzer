using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.StabilityReplay;

// Test-only paired replay. There are deliberately no scientific-settings switches.
internal static class Program
{
    private const ulong RunSeed = 20260904UL;
    private const int Repetitions = 1000;
    private const string Schema = "mvs-stability-replay-case/v1";
    private static readonly string[] Keys = { "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad", "normalized_iqr", "mean", "rms", "range", "geometric_mean", "trimmed_mean_20" };
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new FiniteDoubleConverter() }
    };
    private sealed class FiniteDoubleConverter : JsonConverter<double>
    {
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options) => throw new NotSupportedException();
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        {
            if (double.IsFinite(value)) writer.WriteNumberValue(value); else writer.WriteNullValue();
        }
    }
    private sealed record Options(int? Index, string? Output, int TimeoutSeconds, string Mode);
    private static MethodInfo Helper(string name) => typeof(BenchmarkRunner).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static)
        ?? throw new InvalidOperationException("Missing original BenchmarkRunner helper: " + name);
    private static T Invoke<T>(string name, params object[] args)
    {
        try { return (T)Helper(name).Invoke(null, args)!; }
        catch (TargetInvocationException ex) when (ex.InnerException != null)
        { System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(ex.InnerException).Throw(); throw; }
    }
    private static int Seed(BenchmarkRandom random) => Invoke<int>("NextSeed", random);
    private static double[] Scores(List<CalibrationRow> rows) => Invoke<double[]>("Scores", rows, 12);
    private static int Top(double[] scores) => Invoke<int>("ArgMax", scores);
    private static void Require(bool condition, string message)
    { if (!condition) throw new InvalidOperationException(message); }

    public static int Main(string[] args)
    {
        Options? options = null;
        var retained = new Dictionary<string, object>();
        var clock = Stopwatch.StartNew();
        using var process = Process.GetCurrentProcess();
        TimeSpan initialCpu = process.TotalProcessorTime;
        try
        {
            options = Parse(args);
            VerifyRecipe();
            object result;
            if (options.Mode == "inspect") result = new { schema = Schema, status = "ok", settings = Settings(), metric_order = Keys, identity = Identity() };
            else if (options.Mode == "self-test") result = SelfTest();
            else
            {
                Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1", "MVS_DISABLE_BACKUPS=1 is required before replay.");
                // Reserve the result path before expensive work; never replace existing evidence.
                using var output = options.Output == null ? null : new FileStream(options.Output, FileMode.CreateNew, FileAccess.Write, FileShare.None);
                try
                {
                    string? partialPath = options.Output == null ? null : options.Output + ".partial.json";
                    if (partialPath != null)
                    {
                        using var reservation = new FileStream(partialPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
                        Write(new { schema = Schema, index = options.Index, status = "reserved" }, reservation);
                    }
                    using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(options.TimeoutSeconds));
                    result = Replay(options.Index!.Value, cancellation.Token, clock, process, initialCpu, retained, partialPath);
                    Write(result, output);
                    return 0;
                }
                catch (Exception ex)
                {
                    Write(Failure(options.Index, ex, clock, process, initialCpu, retained), output);
                    return 1;
                }
            }
            Write(result, null);
            return 0;
        }
        catch (Exception ex)
        {
            Write(Failure(options?.Index, ex, clock, process, initialCpu, retained), null);
            return 1;
        }
    }
    private static Options Parse(string[] args)
    {
        if (args.Length == 1 && args[0] is "--inspect" or "--self-test") return new(null, null, 900, args[0][2..]);
        int? index = null; string? output = null; int timeout = 900; bool hasTimeout = false;
        for (int i = 0; i < args.Length; i += 2)
        {
            if (i + 1 == args.Length) throw new ArgumentException("Each replay flag requires a value.");
            switch (args[i])
            {
                case "--case" when index == null:
                    if (!int.TryParse(args[i + 1], out int parsed) || parsed < 0 || parsed > 119) throw new ArgumentException("Case index must be 0..119.");
                    index = parsed; break;
                case "--out" when output == null:
                    if (string.IsNullOrWhiteSpace(args[i + 1])) throw new ArgumentException("Output path cannot be empty.");
                    output = args[i + 1]; break;
                case "--timeout-seconds" when !hasTimeout:
                    if (!int.TryParse(args[i + 1], out timeout) || timeout < 1 || timeout > 900) throw new ArgumentException("Timeout must be 1..900 seconds.");
                    hasTimeout = true; break;
                default: throw new ArgumentException("Unknown or duplicate argument: " + args[i]);
            }
        }
        if (index == null) throw new ArgumentException("Use --case INDEX [--out FILE] [--timeout-seconds SECONDS], --inspect, or --self-test.");
        return new(index, output, timeout, "case");
    }
    private static void VerifyRecipe()
    {
        Require(AnalysisEngine.MetricKeys.SequenceEqual(Keys), "The original twelve-key metric order changed.");
        Require(BenchmarkProtocol.CalibrationEffect == 1.15 && BenchmarkProtocol.CalibrationScenario == "location" &&
            BenchmarkProtocol.CalibrationOutlierRate == .02 && BenchmarkProtocol.CalibrationMissingRate == 0 && BenchmarkProtocol.Alpha == .05,
            "Original calibration constants changed.");
        Require(AnalysisEngine.DefaultTracks.SequenceEqual(new[] { "location", "variability", "heterogeneity" }), "DefaultTracks changed.");
        foreach (var (name, expected) in new[] { ("StageStability", 5), ("MinValue", -1000000), ("MaxValue", 1000000), ("MinMeasurements", 6) })
            Require((int)typeof(BenchmarkRunner).GetField(name, BindingFlags.NonPublic | BindingFlags.Static)!.GetRawConstantValue()! == expected, "Original constant changed: " + name);
        Require(Invoke<int>("StreamOf", BenchmarkDatasets.Gait) == 1, "Gait stream changed.");
        var d = BenchmarkDatasets.Gait;
        Require(d.Id == "gait_stride_like" && d.EntitiesPerGroup == 16 && d.MeasurementsPerEntity == 40 && d.BaseLevel == 1.10 &&
            d.BetweenSd == .08 && d.WithinCv == .025 && d.CvHeterogeneity == .25 && d.Shape == DataShape.HeavyTail &&
            d.Variable == "stride_interval" && d.Unit == "s", "Original gait design changed.");
        foreach (string name in new[] { "NextSeed", "Scores", "ArgMax", "Calibrate" }) _ = Helper(name);
    }
    private static object Settings() => new
    {
        run_seed = RunSeed, stage = 5, stream = 1, index_min = 0, index_max = 119, design = BenchmarkDatasets.Gait,
        injection = "None", generation_effect = 1, contamination = 0, min_value = -1000000, max_value = 1000000,
        min_measurements = 6, repetitions = Repetitions, effect = 1.15, scenario = "location", outlier_rate = .02,
        missing_rate = 0, alpha = .05, tracks = AnalysisEngine.DefaultTracks, score_projection = "original BenchmarkRunner.Scores; absent/nonfinite Score becomes zero",
        canonical_binding = "UTF-8 compact System.Text.Json snake_case JSON, ordered rows and properties as emitted; SHA-256 over precisely the embedded canonical_json UTF-8 bytes. Replay binding only, not a historical archived-data hash.",
        nonfinite_encoding = "null; calibration nonfinite_fields retains path and NaN/Infinity/-Infinity label"
    };
    private static object Replay(int index, CancellationToken token, Stopwatch clock, Process process, TimeSpan initialCpu, Dictionary<string, object> retained, string? partialPath)
    {
        ulong derived = BenchmarkRandom.Derive(RunSeed, 5UL, 1UL, (ulong)index);
        retained["identity"] = Identity();
        retained["settings"] = Settings();
        retained["metric_order"] = Keys;
        retained["derived_seed"] = derived;
        var random = new BenchmarkRandom(derived);
        List<Observation> rows = BenchmarkDatasets.Generate(BenchmarkDatasets.Gait, InjectionMode.None, 1, 0, random);
        retained["generated"] = Bind(rows);
        AnalysisData built = AnalysisEngine.Build(rows, -1000000, 1000000, 6);
        retained["built"] = Bind(built);
        int splitSeed = Seed(random);
        retained["split_seed"] = splitSeed;
        var (left, right) = AnalysisEngine.SplitEntities(built, splitSeed);
        retained["left"] = Bind(left); retained["right"] = Bind(right);
        int leftSeed = Seed(random), rightSeed = Seed(random);
        retained["calibration_left_seed"] = leftSeed; retained["calibration_right_seed"] = rightSeed;
        Checkpoint(partialPath, index, "before_calibration", retained);
        token.ThrowIfCancellationRequested();
        var leftCalibration = Invoke<List<CalibrationRow>>("Calibrate", left, Repetitions, leftSeed, token);
        retained["calibration_left"] = leftCalibration;
        retained["calibration_left_nonfinite_fields"] = Nonfinite(leftCalibration);
        Checkpoint(partialPath, index, "left_calibration_completed", retained);
        var rightCalibration = Invoke<List<CalibrationRow>>("Calibrate", right, Repetitions, rightSeed, token);
        retained["calibration_right"] = rightCalibration;
        retained["calibration_right_nonfinite_fields"] = Nonfinite(rightCalibration);
        Checkpoint(partialPath, index, "both_calibrations_completed", retained);
        token.ThrowIfCancellationRequested();
        double[] a = Scores(leftCalibration), b = Scores(rightCalibration);
        Require(a.Length == 12 && b.Length == 12, "Score-vector length changed.");
        int topLeft = Top(a), topRight = Top(b);
        double legacy = BenchmarkMath.LegacyKendallTau(a, b), corrected = BenchmarkMath.KendallTau(a, b);
        return new
        {
            schema = Schema, index, status = "completed", diagnostics_status = "retained", error = "",
            seeds = new { run_seed = RunSeed, derived_seed = derived, split_seed = splitSeed, calibration_left_seed = leftSeed, calibration_right_seed = rightSeed },
            settings = Settings(), metric_order = Keys, identity = Identity(),
            data = new { generated = Bind(rows), built = Bind(built), left = Bind(left), right = Bind(right) },
            calibration_left = leftCalibration, calibration_right = rightCalibration,
            nonfinite_fields = new { calibration_left = Nonfinite(leftCalibration), calibration_right = Nonfinite(rightCalibration) },
            scores_left = a, scores_right = b,
            availability_left = Availability(leftCalibration), availability_right = Availability(rightCalibration),
            legacy = Tau(legacy, topLeft, topRight), corrected = Tau(corrected, topLeft, topRight),
            resources = Resources(clock, process, initialCpu)
        };
    }
    // The owned sidecar is retained even on forced termination. No resume/retry support.
    private static void Checkpoint(string? path, int index, string phase, Dictionary<string, object> retained)
    {
        if (path == null) return;
        string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                Write(new { schema = Schema, index, status = "partial", phase, retained,
                    limitation = "Only completed phases retained; an interrupted calibration has no recoverable partial rows." }, stream);
                stream.Flush(true);
            }
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    private static object[] Availability(List<CalibrationRow> rows) => Enumerable.Range(0, 12).Select(i => (object)new
    { metric = Keys[i], row_present = i < rows.Count, score_finite = i < rows.Count && double.IsFinite(rows[i].Score),
        applicable = i < rows.Count && rows[i].Applicable, projected_to_zero = i >= rows.Count || !double.IsFinite(rows[i].Score) }).ToArray();
    private static object Tau(double value, int left, int right) => new
    {
        kendall_tau = double.IsFinite(value) ? (double?)value : null, defined = double.IsFinite(value),
        undefined_reason = double.IsFinite(value) ? null : "nonfinite scores, insufficient pairs, or zero rank variance under this method",
        top_left_index = left, top_right_index = right, top_left = left < 0 ? null : Keys[left], top_right = right < 0 ? null : Keys[right],
        matched = left >= 0 && left == right
    };
    private static object Bind<T>(T value)
    {
        string canonical = JsonSerializer.Serialize(value, Json);
        return new { sha256 = Hash(Encoding.UTF8.GetBytes(canonical)), canonical_json = canonical, values = value };
    }
    private static List<object> Nonfinite(List<CalibrationRow> rows)
    {
        var found = new List<object>();
        for (int i = 0; i < rows.Count; i++)
            foreach (var property in typeof(CalibrationRow).GetProperties().OrderBy(p => p.Name, StringComparer.Ordinal))
            {
                object? value = property.GetValue(rows[i]);
                string path = $"[{i}].{JsonNamingPolicy.SnakeCaseLower.ConvertName(property.Name)}";
                if (value is double scalar && !double.IsFinite(scalar)) found.Add(new { path, value = scalar.ToString(System.Globalization.CultureInfo.InvariantCulture) });
                if (value is double[] array)
                    for (int j = 0; j < array.Length; j++)
                        if (!double.IsFinite(array[j])) found.Add(new { path = path + $"[{j}]", value = array[j].ToString(System.Globalization.CultureInfo.InvariantCulture) });
            }
        return found;
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static object Identity() => new
    {
        harness_sha256 = Hash(File.ReadAllBytes(typeof(Program).Assembly.Location)),
        core_sha256 = Hash(File.ReadAllBytes(typeof(AnalysisEngine).Assembly.Location)),
        runtime = RuntimeInformation.FrameworkDescription, os = RuntimeInformation.OSDescription,
        architecture = RuntimeInformation.ProcessArchitecture.ToString(), engine_version = AnalysisEngine.EngineVersion,
        benchmark_protocol = BenchmarkProtocol.Version, processor_count = Environment.ProcessorCount,
        environment_fingerprint = BenchmarkEnvironment.Fingerprint(), environment_sha256 = BenchmarkEnvironment.Hash,
        environment_probe_values = BenchmarkEnvironment.ProbeValues()
    };
    private static object Resources(Stopwatch clock, Process process, TimeSpan initialCpu)
    {
        process.Refresh();
        return new { wall_seconds = clock.Elapsed.TotalSeconds, cpu_seconds = (process.TotalProcessorTime - initialCpu).TotalSeconds,
            peak_working_set_bytes = process.PeakWorkingSet64 };
    }
    private static object Failure(int? index, Exception error, Stopwatch clock, Process process, TimeSpan initialCpu, Dictionary<string, object> retained) => new
    {
        schema = Schema, index, status = "failed", diagnostics_status = "failed", error = error.GetType().Name + ": " + error.Message, retained,
        resources = Resources(clock, process, initialCpu)
    };
    private static void Write(object value, Stream? output)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, Json);
        if (output == null) { using var stdout = Console.OpenStandardOutput(); stdout.Write(bytes); stdout.WriteByte(10); }
        else { output.Write(bytes); output.WriteByte(10); output.Flush(); }
    }
    private static object SelfTest()
    {
        Require(Parse(new[] { "--case", "0" }).Index == 0 && Parse(new[] { "--case", "119" }).Index == 119, "Valid boundaries failed.");
        foreach (string[] args in new[] { new[] { "--case", "-1" }, new[] { "--case", "120" }, new[] { "--seed", "1" }, new[] { "--case", "0", "--case", "1" }, new[] { "--case", "0", "--timeout-seconds", "901" } })
        {
            bool rejected = false; try { Parse(args); } catch (ArgumentException) { rejected = true; }
            Require(rejected, "Invalid argument was accepted.");
        }
        Require(BenchmarkRandom.Derive(RunSeed, 5UL, 1UL, 0UL) == 8738233689029321767UL &&
            BenchmarkRandom.Derive(RunSeed, 5UL, 1UL, 119UL) == 5737789723273926856UL, "Derived-seed boundary goldens changed.");
        var r1 = new BenchmarkRandom(20260904UL); var r2 = new BenchmarkRandom(20260904UL);
        for (int i = 0; i < 20; i++) Require(Seed(r1) == (int)(r2.NextUInt64() % 50000000UL) + 1, "NextSeed recipe mismatch.");
        var fixture = new List<CalibrationRow> { new("a", 0, 0, double.NaN), new("b", 0, 0, .7), new("c", 0, 0, double.PositiveInfinity) };
        double[] scores = Scores(fixture);
        Require(scores.Length == 12 && scores[1] == .7 && scores.Where((_, i) => i != 1).All(x => x == 0), "Legacy score projection mismatch.");
        Require(Top(new[] { 1.0, 1.0, 0.0 }) == 0 && Top(new[] { double.NaN }) == -1, "ArgMax mismatch.");
        double[] a = { 0, 0, 1 };
        Require(Math.Abs(BenchmarkMath.LegacyKendallTau(a, a) - 2.0 / 3) < 1e-15 && BenchmarkMath.KendallTau(a, a) == 1, "Joint-tie example failed.");
        Require(BenchmarkMath.LegacyKendallTau(new double[12], new double[12]) == 0 && double.IsNaN(BenchmarkMath.KendallTau(new double[12], new double[12])), "Constant-vector example failed.");
        Require(JsonSerializer.Serialize(new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity }, Json) == "[null,null,null]", "Nonfinite serialization failed.");
        return new { schema = Schema, status = "ok", mode = "self-test", calibration_executed = false,
            tests = new[] { "recipe_constants", "metric_order", "case_boundaries", "invalid_arguments", "derived_seed_goldens", "next_seed", "score_projection", "argmax", "joint_ties", "constant_vectors", "nonfinite_serialization" }, identity = Identity() };
    }
}
