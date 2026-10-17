using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.ScenarioMechanism;

// Test-only Round47 deterministic mechanism probe. No calibration, resampling or random draws.
// Strict JSON/binding validation is adapted from the existing Round45 test harness.
internal static class Program
{
    private const string Schema = "mvs-scenario-mechanism-case/v1";
    private const string InputSchema = "mvs-stability-replay-case/v1";
    private const string SyntheticSchema = "mvs-scenario-mechanism-synthetic-input/v1";
    private const double Effect = 1.15;
    private static readonly string[] Conditions = { "identity", "location", "variability", "heterogeneity" };
    private const int Repetitions = 1000;
    private const double Alpha = .05;
    private static readonly string[] Tracks = { "location", "variability", "heterogeneity" };
    private static readonly string[] Keys = { "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad", "normalized_iqr", "mean", "rms", "range", "geometric_mean", "trimmed_mean_20" };
    private static readonly string[] RowFields = { "metric", "fpr", "power", "score", "robustness", "repeatability", "coverage", "applicable", "mde", "fpr_inflated", "power_curve", "tracks", "track_powers", "track_scores", "track_mdes", "track_curves", "repetitions", "fpr_low", "fpr_high", "track_power_low", "track_power_high", "track_failures", "track_mde_status", "alpha", "null_failures" };
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new FiniteDoubleConverter() }
    };
    private sealed class FiniteDoubleConverter : JsonConverter<double>
    {
        private readonly bool nullAsNaN;
        public FiniteDoubleConverter(bool nullAsNaN = false) { this.nullAsNaN = nullAsNaN; }
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options) => reader.TokenType == JsonTokenType.Number && double.IsFinite(reader.GetDouble()) ? reader.GetDouble() : nullAsNaN && reader.TokenType == JsonTokenType.Null ? double.NaN : throw new InvalidDataException("AnalysisData requires finite numbers.");
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        { if (double.IsFinite(value)) writer.WriteNumberValue(value); else writer.WriteNullValue(); }
    }
    private sealed record Options(string Input, int Index, string Sha256, string Output, string FreezeSha256, bool Synthetic);
    private sealed record Loaded(CalibrationRow[] Left, CalibrationRow[] Right, JsonElement LeftNonfinite, JsonElement RightNonfinite);
    private sealed record NonfiniteField(string Path, string Value);
    private static void Require(bool condition, string message)
    { if (!condition) throw new InvalidDataException(message); }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static bool IsHash(string text) => text.Length == 64 && text.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static bool Same(double a, double b) => double.IsNaN(a) ? double.IsNaN(b) : BitConverter.DoubleToInt64Bits(a) == BitConverter.DoubleToInt64Bits(b);
    private static string Name(PropertyInfo property) => JsonNamingPolicy.SnakeCaseLower.ConvertName(property.Name);

    private static JsonDocument ParseDocument(byte[] bytes)
    {
        JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions { AllowTrailingCommas = false, CommentHandling = JsonCommentHandling.Disallow, MaxDepth = 128 });
        try { RejectDuplicates(document.RootElement, "$", 0); return document; }
        catch { document.Dispose(); throw; }
    }
    private static void RejectDuplicates(JsonElement node, string path, int depth)
    {
        Require(depth <= 128, path + ": nesting exceeds 128.");
        if (node.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in node.EnumerateObject())
            { Require(names.Add(property.Name), path + ": duplicate JSON member " + property.Name); RejectDuplicates(property.Value, path + "." + property.Name, depth + 1); }
        }
        else if (node.ValueKind == JsonValueKind.Array)
        { int i = 0; foreach (JsonElement element in node.EnumerateArray()) RejectDuplicates(element, path + "[" + i++ + "]", depth + 1); }
    }
    private static void Object(JsonElement node, string path, params string[] fields)
    {
        Require(node.ValueKind == JsonValueKind.Object, path + ": expected object.");
        Require(node.EnumerateObject().Select(x => x.Name).ToHashSet(StringComparer.Ordinal).SetEquals(fields), path + ": missing or unknown fields.");
        Require(node.EnumerateObject().Count() == fields.Length, path + ": duplicate fields.");
    }
    private static JsonElement Field(JsonElement node, string name, string path) => node.TryGetProperty(name, out JsonElement value) ? value : throw new InvalidDataException(path + ": missing " + name);
    private static string Text(JsonElement node, string path)
    { Require(node.ValueKind == JsonValueKind.String, path + ": expected string."); return node.GetString()!; }
    private static bool Boolean(JsonElement node, string path)
    { Require(node.ValueKind is JsonValueKind.True or JsonValueKind.False, path + ": expected boolean."); return node.GetBoolean(); }
    private static int Integer(JsonElement node, string path)
    { Require(node.ValueKind == JsonValueKind.Number && node.TryGetInt32(out _), path + ": expected integer."); return node.GetInt32(); }
    private static ulong Unsigned(JsonElement node, string path)
    { Require(node.ValueKind == JsonValueKind.Number && node.TryGetUInt64(out _), path + ": expected unsigned integer."); return node.GetUInt64(); }
    private static double Finite(JsonElement node, string path)
    { Require(node.ValueKind == JsonValueKind.Number && node.TryGetDouble(out double value) && double.IsFinite(value), path + ": expected finite number."); return node.GetDouble(); }
    private static JsonElement[] Array(JsonElement node, string path, int count)
    { Require(node.ValueKind == JsonValueKind.Array && node.GetArrayLength() == count, path + ": expected array of length " + count); return node.EnumerateArray().ToArray(); }
    private static string[] Strings(JsonElement node, string path, int count) => Array(node, path, count).Select((v, i) => Text(v, path + "[" + i + "]")).ToArray();
    private static void EqualJson(JsonElement expected, JsonElement actual, string path)
    {
        Require(expected.ValueKind == actual.ValueKind, path + ": round-trip type mismatch.");
        if (expected.ValueKind == JsonValueKind.Object)
        {
            Object(actual, path, expected.EnumerateObject().Select(x => x.Name).ToArray());
            foreach (JsonProperty p in expected.EnumerateObject()) EqualJson(p.Value, actual.GetProperty(p.Name), path + "." + p.Name);
        }
        else if (expected.ValueKind == JsonValueKind.Array)
        {
            JsonElement[] items = Array(actual, path, expected.GetArrayLength());
            int i = 0; foreach (JsonElement e in expected.EnumerateArray()) { EqualJson(e, items[i], path + "[" + i + "]"); i++; }
        }
        else if (expected.ValueKind == JsonValueKind.Number)
        {
            // Preserve exact integer seed values beyond the binary64 mantissa too.
            if (expected.TryGetUInt64(out ulong u) && actual.TryGetUInt64(out ulong v) && (u > 9007199254740992UL || v > 9007199254740992UL)) Require(u == v, path + ": integer mismatch.");
            else Require(Same(Finite(expected, path), Finite(actual, path)), path + ": binary64 round-trip mismatch.");
        }
        else Require(expected.ToString() == actual.ToString(), path + ": round-trip value mismatch.");
    }

    private static Loaded LoadCase(JsonElement root, int index, bool synthetic)
    {
        Object(root, "$", "schema", "index", "status", "diagnostics_status", "error", "seeds", "settings", "metric_order", "identity", "data", "calibration_left", "calibration_right", "nonfinite_fields", "scores_left", "scores_right", "availability_left", "availability_right", "legacy", "corrected", "resources");
        Require(Text(root.GetProperty("schema"), "schema") == (synthetic ? SyntheticSchema : InputSchema), "Unknown input schema/version.");
        Require(Integer(root.GetProperty("index"), "index") == index, "Input index does not match requested pair.");
        Require(Text(root.GetProperty("status"), "status") == "completed" && Text(root.GetProperty("diagnostics_status"), "diagnostics_status") == (synthetic ? "synthetic" : "retained") && Text(root.GetProperty("error"), "error") == "", "Input is not a complete retained case.");
        Require(Strings(root.GetProperty("metric_order"), "metric_order", 12).SequenceEqual(Keys), "Input metric order changed.");
        VerifySettings(root.GetProperty("settings"));
        JsonElement seeds = root.GetProperty("seeds");
        Object(seeds, "seeds", "run_seed", "derived_seed", "split_seed", "calibration_left_seed", "calibration_right_seed");
        Require(Unsigned(seeds.GetProperty("run_seed"), "seeds.run_seed") == 20260904UL, "Run seed changed.");
        Require(Unsigned(seeds.GetProperty("derived_seed"), "seeds.derived_seed") == BenchmarkRandom.Derive(20260904UL, 5, 1, (ulong)index), "Derived seed/index association mismatch.");
        foreach (string name in new[] { "split_seed", "calibration_left_seed", "calibration_right_seed" }) Require(Integer(seeds.GetProperty(name), "seeds." + name) is >= 1 and <= 50000000, "Invalid seed: " + name);
        VerifyInputIdentity(root.GetProperty("identity"));
        JsonElement data = root.GetProperty("data"); Object(data, "data", "generated", "built", "left", "right");
        foreach (string side in new[] { "generated", "built", "left", "right" })
        {
            JsonElement binding = data.GetProperty(side); Object(binding, "data." + side, "sha256", "canonical_json", "values");
            string canonical = Text(binding.GetProperty("canonical_json"), "data." + side + ".canonical_json");
            Require(Text(binding.GetProperty("sha256"), "data." + side + ".sha256") == Hash(Encoding.UTF8.GetBytes(canonical)), "Invalid data binding: " + side);
            using JsonDocument canonicalDocument = ParseDocument(Encoding.UTF8.GetBytes(canonical));
            EqualJson(canonicalDocument.RootElement, binding.GetProperty("values"), "data." + side + ".values");
        }
        JsonElement nonfinite = root.GetProperty("nonfinite_fields"); Object(nonfinite, "nonfinite_fields", "calibration_left", "calibration_right");
        var left = LoadRows(root.GetProperty("calibration_left"), nonfinite.GetProperty("calibration_left"), "left");
        var right = LoadRows(root.GetProperty("calibration_right"), nonfinite.GetProperty("calibration_right"), "right");
        foreach (var (side, rows) in new[] { ("left", left), ("right", right) })
        {
            JsonElement[] scores = Array(root.GetProperty("scores_" + side), "scores_" + side, 12);
            JsonElement[] availability = Array(root.GetProperty("availability_" + side), "availability_" + side, 12);
            for (int i = 0; i < rows.Length; i++)
            {
                Require(Same(Finite(scores[i], "scores_" + side + "[" + i + "]"), double.IsFinite(rows[i].Score) ? rows[i].Score : 0), "Stored historical score projection mismatch: " + side + "[" + i + "]");
                JsonElement a = availability[i]; string path = "availability_" + side + "[" + i + "]";
                Object(a, path, "metric", "row_present", "score_finite", "applicable", "projected_to_zero");
                Require(Text(a.GetProperty("metric"), path) == Keys[i] && Boolean(a.GetProperty("row_present"), path) &&
                    Boolean(a.GetProperty("score_finite"), path) == double.IsFinite(rows[i].Score) && Boolean(a.GetProperty("applicable"), path) == rows[i].Applicable &&
                    Boolean(a.GetProperty("projected_to_zero"), path) == !double.IsFinite(rows[i].Score), path + ": availability mismatch.");
            }
        }
        foreach (string name in new[] { "legacy", "corrected" })
        {
            JsonElement tau = root.GetProperty(name); Object(tau, name, "kendall_tau", "defined", "undefined_reason", "top_left_index", "top_right_index", "top_left", "top_right", "matched");
            bool defined = Boolean(tau.GetProperty("defined"), name + ".defined");
            Require(defined == (tau.GetProperty("kendall_tau").ValueKind != JsonValueKind.Null), name + ": tau availability mismatch.");
            if (defined) { double value = Finite(tau.GetProperty("kendall_tau"), name); Require(value is >= -1 and <= 1 && tau.GetProperty("undefined_reason").ValueKind == JsonValueKind.Null, name + ": invalid defined tau."); }
            else _ = Text(tau.GetProperty("undefined_reason"), name + ".undefined_reason");
            foreach (string side in new[] { "left", "right" })
            {
                int winner = Integer(tau.GetProperty("top_" + side + "_index"), name + ".top_index"); Require(winner is >= -1 and < 12, name + ": invalid historical winner index.");
                Require(winner < 0 ? tau.GetProperty("top_" + side).ValueKind == JsonValueKind.Null : Text(tau.GetProperty("top_" + side), name) == Keys[winner], name + ": historical winner/index mismatch.");
            }
            _ = Boolean(tau.GetProperty("matched"), name + ".matched");
        }
        JsonElement resources = root.GetProperty("resources"); Object(resources, "resources", "wall_seconds", "cpu_seconds", "peak_working_set_bytes");
        foreach (string name in new[] { "wall_seconds", "cpu_seconds" }) Require(Finite(resources.GetProperty(name), "resources." + name) >= 0, "Negative resource accounting.");
        _ = Unsigned(resources.GetProperty("peak_working_set_bytes"), "resources.peak_working_set_bytes");
        return new(left, right, nonfinite.GetProperty("calibration_left").Clone(), nonfinite.GetProperty("calibration_right").Clone());
    }

    private static object ExpectedSettings() => new
    {
        run_seed = 20260904UL, stage = 5, stream = 1, index_min = 0, index_max = 119, design = BenchmarkDatasets.Gait,
        injection = "None", generation_effect = 1, contamination = 0, min_value = -1000000, max_value = 1000000,
        min_measurements = 6, repetitions = Repetitions, effect = 1.15, scenario = "location", outlier_rate = .02,
        missing_rate = 0, alpha = Alpha, tracks = Tracks, score_projection = "original BenchmarkRunner.Scores; absent/nonfinite Score becomes zero",
        canonical_binding = "UTF-8 compact System.Text.Json snake_case JSON, ordered rows and properties as emitted; SHA-256 over precisely the embedded canonical_json UTF-8 bytes. Replay binding only, not a historical archived-data hash.",
        nonfinite_encoding = "null; calibration nonfinite_fields retains path and NaN/Infinity/-Infinity label"
    };
    private static void VerifySettings(JsonElement settings) => EqualJson(JsonSerializer.SerializeToElement(ExpectedSettings(), Json), settings, "settings");
    private static void VerifyInputIdentity(JsonElement identity)
    {
        Object(identity, "identity", "harness_sha256", "core_sha256", "runtime", "os", "architecture", "engine_version", "benchmark_protocol", "processor_count", "environment_fingerprint", "environment_sha256", "environment_probe_values");
        foreach (string field in new[] { "harness_sha256", "core_sha256", "environment_sha256" }) Require(IsHash(Text(identity.GetProperty(field), "identity." + field)), "Invalid identity hash: " + field);
        foreach (string field in new[] { "runtime", "os", "architecture", "engine_version", "benchmark_protocol", "environment_fingerprint" }) Require(Text(identity.GetProperty(field), "identity." + field).Length > 0, "Empty identity field: " + field);
        Require(Text(identity.GetProperty("runtime"), "identity.runtime") == ".NET 8.0.31", "Retained runtime differs from fixed recipe.");
        Require(Text(identity.GetProperty("engine_version"), "identity.engine_version") == AnalysisEngine.EngineVersion && Text(identity.GetProperty("benchmark_protocol"), "identity.benchmark_protocol") == BenchmarkProtocol.Version, "Retained engine/protocol identity mismatch.");
        Require(Integer(identity.GetProperty("processor_count"), "identity.processor_count") > 0, "Invalid processor count.");
        foreach (JsonElement value in Array(identity.GetProperty("environment_probe_values"), "identity.environment_probe_values", 12)) _ = Finite(value, "identity.environment_probe_values");
        Require(Hash(Encoding.UTF8.GetBytes(Text(identity.GetProperty("environment_fingerprint"), "identity.environment_fingerprint"))) == Text(identity.GetProperty("environment_sha256"), "identity.environment_sha256"), "Environment fingerprint hash mismatch.");
    }

    private static CalibrationRow[] LoadRows(JsonElement array, JsonElement metadata, string side)
    {
        JsonElement[] items = Array(array, side, 12);
        Require(metadata.ValueKind == JsonValueKind.Array, side + ": nonfinite_fields must be an array.");
        var labels = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (JsonElement item in metadata.EnumerateArray())
        {
            Object(item, side + ".nonfinite_fields", "path", "value");
            string path = Text(item.GetProperty("path"), side + ".nonfinite_fields.path");
            string label = Text(item.GetProperty("value"), side + ".nonfinite_fields.value");
            Require(label is "NaN" or "Infinity" or "-Infinity", side + ": unknown nonfinite label " + label);
            Require(labels.TryAdd(path, label), side + ": duplicate nonfinite path " + path);
        }
        var consumed = new HashSet<string>(StringComparer.Ordinal);
        double Number(JsonElement value, string path)
        {
            if (value.ValueKind == JsonValueKind.Null)
            {
                Require(labels.TryGetValue(path, out string? label), side + path + ": null lacks nonfinite provenance.");
                Require(consumed.Add(path), side + path + ": nonfinite path consumed twice.");
                return label switch { "NaN" => double.NaN, "Infinity" => double.PositiveInfinity, "-Infinity" => double.NegativeInfinity, _ => throw new InvalidDataException("Invalid nonfinite label.") };
            }
            Require(!labels.ContainsKey(path), side + path + ": nonfinite label points to a finite or wrong-type value.");
            return Finite(value, side + path);
        }
        var rows = new CalibrationRow[items.Length];
        for (int i = 0; i < items.Length; i++)
        {
            JsonElement row = items[i]; string prefix = "[" + i + "]";
            Object(row, side + prefix, RowFields);
            JsonElement F(string key) => Field(row, key, side + prefix);
            double D(string key) => Number(F(key), prefix + "." + key);
            string S(string key) => Text(F(key), side + prefix + "." + key);
            bool B(string key) => Boolean(F(key), side + prefix + "." + key);
            int I(string key) => Integer(F(key), side + prefix + "." + key);
            double[] DA(string key) => Array(F(key), side + prefix + "." + key, 3).Select((v, j) => Number(v, prefix + "." + key + "[" + j + "]")).ToArray();
            string[] SA(string key) => Strings(F(key), side + prefix + "." + key, 3);
            int[] IA(string key) => Array(F(key), side + prefix + "." + key, 3).Select((v, j) => Integer(v, side + prefix + "." + key + "[" + j + "]")).ToArray();
            // Every constructor parameter is supplied explicitly: no null-to-zero or default recovery.
            rows[i] = new CalibrationRow(S("metric"), D("fpr"), D("power"), D("score"), D("robustness"), D("repeatability"), D("coverage"), B("applicable"),
                D("mde"), B("fpr_inflated"), S("power_curve"), SA("tracks"), DA("track_powers"), DA("track_scores"), DA("track_mdes"), SA("track_curves"),
                I("repetitions"), D("fpr_low"), D("fpr_high"), DA("track_power_low"), DA("track_power_high"), IA("track_failures"), SA("track_mde_status"), D("alpha"), I("null_failures"));
            Require(rows[i].Metric == Keys[i], side + prefix + ": missing, duplicate, unknown, or reordered metric.");
            Require(rows[i].Repetitions == Repetitions && Same(rows[i].Alpha, Alpha) && rows[i].Tracks!.SequenceEqual(Tracks), "Row recipe mismatch.");
            EqualJson(row, JsonSerializer.SerializeToElement(rows[i], Json), side + prefix);
        }
        Require(consumed.SetEquals(labels.Keys), side + ": nonfinite metadata contains an unknown, wrong-row, or out-of-range path.");
        // Compare labels as a mapping, but preserve the source metadata order in the result.
        var restored = FindNonfinite(rows).ToDictionary(x => x.Path, x => x.Value, StringComparer.Ordinal);
        Require(restored.Count == labels.Count && labels.All(x => restored.TryGetValue(x.Key, out string? value) && value == x.Value), side + ": nonfinite round-trip changed a class or path.");
        return rows;
    }

    private static List<NonfiniteField> FindNonfinite(object value, string path = "")
    {
        var found = new List<NonfiniteField>();
        if (value is double scalar)
        { if (!double.IsFinite(scalar)) found.Add(new(path, double.IsNaN(scalar) ? "NaN" : scalar > 0 ? "Infinity" : "-Infinity")); }
        else if (value is System.Array array)
        { for (int i = 0; i < array.Length; i++) if (array.GetValue(i) is object item) found.AddRange(FindNonfinite(item, path + "[" + i + "]")); }
        else if (value is not string && value.GetType().IsClass)
            foreach (PropertyInfo property in value.GetType().GetProperties().OrderBy(p => p.Name, StringComparer.Ordinal))
                if (property.GetValue(value) is object item) found.AddRange(FindNonfinite(item, path.Length == 0 ? Name(property) : path + "." + Name(property)));
        return found;
    }
    private static readonly double[] Grid = { 1, 1.02, 1.05, 1.10, 1.20 };
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
    private static void Write(object value, Stream? output)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, Json);
        if (output == null) { using Stream stdout = Console.OpenStandardOutput(); stdout.Write(bytes); stdout.WriteByte(10); stdout.Flush(); }
        else { output.Write(bytes); output.WriteByte(10); output.Flush(); }
    }
    private static Options Parse(string[] args)
    {
        bool synthetic = args.Length == 11 && args[^1] == "--synthetic";
        string[] flagsOnly = synthetic ? args[..^1] : args;
        var flags = new Dictionary<string, string>(StringComparer.Ordinal);
        Require(flagsOnly.Length == 10, "Required: --input PATH --index N --sha256 HASH --out FILE --freeze-sha256 HASH [--synthetic].");
        for (int i = 0; i < flagsOnly.Length; i += 2)
            Require(new[] { "--input", "--index", "--sha256", "--out", "--freeze-sha256" }.Contains(flagsOnly[i]) && flags.TryAdd(flagsOnly[i], flagsOnly[i + 1]), "Unknown or duplicate flag.");
        Require(int.TryParse(flags["--index"], out int index) && index is >= 0 and < 120, "Index must be 0..119.");
        Require(IsHash(flags["--sha256"]) && IsHash(flags["--freeze-sha256"]), "Hashes must be lowercase SHA-256.");
        Require(!string.IsNullOrWhiteSpace(flags["--input"]) && !string.IsNullOrWhiteSpace(flags["--out"]), "Empty path.");
        Require(!synthetic || index == 0, "Synthetic fixture index must be zero.");
        return new(flags["--input"], index, flags["--sha256"], flags["--out"], flags["--freeze-sha256"], synthetic);
    }
    private static void VerifyImplementation()
    {
        Require(Environment.Version.ToString() == "8.0.31", "Runtime must be .NET 8.0.31.");
        Require(AnalysisEngine.MetricKeys.SequenceEqual(Keys) && AnalysisEngine.DefaultTracks.SequenceEqual(Tracks) && AnalysisEngine.EffectGrid.SequenceEqual(Grid), "Metric/track/grid order changed.");
        Require(typeof(CalibrationRow).GetProperties().Select(Name).ToHashSet().SetEquals(RowFields), "Row schema changed.");
        Require(BenchmarkProtocol.CalibrationEffect == 1.15 && BenchmarkProtocol.CalibrationScenario == "location" && BenchmarkProtocol.CalibrationOutlierRate == .02 && BenchmarkProtocol.CalibrationMissingRate == 0 && BenchmarkProtocol.Alpha == Alpha, "Recipe changed.");
    }
    private static AnalysisData LoadData(JsonElement root, string side, bool synthetic)
    {
        JsonElement binding = root.GetProperty("data").GetProperty(side);
        string canonical = binding.GetProperty("canonical_json").GetString()!;
        Require(Hash(Encoding.UTF8.GetBytes(canonical)) == binding.GetProperty("sha256").GetString(), "Canonical data hash mismatch.");
        using var doc = ParseDocument(Encoding.UTF8.GetBytes(canonical));
        EqualJson(doc.RootElement, binding.GetProperty("values"), side + ".canonical");
        AnalysisData data = JsonSerializer.Deserialize<AnalysisData>(canonical, synthetic ? SyntheticJson : Json) ?? throw new InvalidDataException("Missing AnalysisData.");
        EqualJson(doc.RootElement, JsonSerializer.SerializeToElement(data, Json), side + ".roundtrip");
        Require(data.MinValueApplied == -1000000 && data.MaxValueApplied == 1000000 && data.MinMeasurementsApplied == 6, "Preprocessing changed.");
        Require(data.ValidRows == data.Observations.Count && data.GroupNames.Length == data.GroupCounts.Length && data.GroupCounts.Sum() == data.Entities.Count, "Derived data counts inconsistent.");
        Require(data.GroupNames.Distinct(StringComparer.OrdinalIgnoreCase).Count() == data.GroupNames.Length, "Duplicate groups.");
        for (int i = 0; i < data.GroupNames.Length; i++)
            Require(data.Entities.Count(e => string.Equals(e.Group, data.GroupNames[i], StringComparison.OrdinalIgnoreCase)) == data.GroupCounts[i], "Group count mismatch.");
        var entityIds = new HashSet<(string, string)>();
        foreach (var entity in data.Entities)
        {
            Require(entityIds.Add((entity.Group.ToUpperInvariant(), entity.Entity.ToUpperInvariant())), "Duplicate entity.");
            Require(entity.Metrics.Length == 12 && entity.Metrics.All(v => double.IsFinite(v) || synthetic && double.IsNaN(v)), "Metric shape/nonfinite AnalysisData.");
            Require(data.Observations.Count(o => string.Equals(o.Group, entity.Group, StringComparison.OrdinalIgnoreCase) && string.Equals(o.Entity, entity.Entity, StringComparison.OrdinalIgnoreCase)) == entity.Measurements, "Entity observation count mismatch.");
        }
        Require(data.Entities.Sum(e => e.Measurements) == data.Observations.Count, "Orphan observations.");
        int[] sizes = data.Entities.Select(e => e.Measurements).Order().ToArray();
        Require(sizes.Length > 0 && sizes.All(n => n >= 6), "Invalid entity measurement count.");
        double median = sizes.Length % 2 == 0 ? (sizes[sizes.Length / 2 - 1] + (double)sizes[sizes.Length / 2]) / 2 : sizes[sizes.Length / 2];
        Require(Same(median, data.MedianMeasurements), "Derived median count mismatch.");
        AnalysisData rebuilt = AnalysisEngine.Build(data.Observations, data.MinValueApplied, data.MaxValueApplied, data.MinMeasurementsApplied);
        EqualJson(JsonSerializer.SerializeToElement(rebuilt, Json), doc.RootElement, side + ".recomputed_build");
        for (int i = 0; i < data.Entities.Count; i++)
            for (int m = 0; m < Keys.Length; m++)
                Require(Same(rebuilt.Entities[i].Metrics[m], data.Entities[i].Metrics[m]), side + ": original metric is not bit-exact Build output.");
        if (side is "left" or "right")
            Require(data.GroupNames.Length == 2 && data.GroupCounts.SequenceEqual(new[] { 8, 8 }) && data.Entities.All(e => e.Measurements == 40), "Half must retain two groups of eight entities and forty measurements.");
        return data;
    }
    private static void VerifyRuntime(JsonElement input)
    {
        var current = JsonSerializer.SerializeToElement(Identity(), Json);
        foreach (string field in new[] { "runtime", "os", "architecture", "engine_version", "benchmark_protocol", "processor_count", "environment_fingerprint", "environment_sha256", "environment_probe_values" })
            EqualJson(input.GetProperty(field), current.GetProperty(field), "identity." + field);
        // Core byte hash is retained on both sides. Build-path-dependent binaries may differ;
        // the frozen source/build provenance must explicitly account for this in the driver.
    }
    private static readonly JsonSerializerOptions SyntheticJson = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new FiniteDoubleConverter(true) }
    };
    private sealed record Availability(string Metric, bool Available, string Reason, string NonfiniteClass);
    private sealed record EntityProbe(string Entity, string Group, int Measurements, double[] Values,
        double Mean, double SampleVariance, double WithinSd, double[] Metrics, Availability[] MetricAvailability);
    private sealed record GroupGeometry(string Group, double EntityMeanAverage, double EntityMeanVariance);
    private sealed record RankProbe(string Metric, bool NaturalFamily, double[][] GroupValues, [property: JsonPropertyName("n_a")] int NA, [property: JsonPropertyName("n_b")] int NB,
        bool Available, string? UnavailableReason, double NativeP, double NativeAdjustedP, bool? NativeReject);
    private sealed record ConditionProbe(string Condition, double Effect, GroupGeometry[] Groups,
        EntityProbe[] Entities, RankProbe[] Ranks);
    private sealed record HalfProbe(string Side, string CanonicalDataSha256, bool BuildVerified, string[] GroupOrder,
        int[] GroupCounts, double PoolCenter, double ShiftScale, double[] OriginalGroupMeans,
        double OriginalGroupMeanDifference, EntityProbe[] Entities, ConditionProbe[] Conditions);
    private static string Class(double value) => double.IsFinite(value) ? "finite" : double.IsNaN(value) ? "NaN" : value > 0 ? "Infinity" : "-Infinity";
    private static object ProbeSettings() => new
    {
        effect = Effect, alpha = Alpha, family_size = Keys.Length, min_usable_entities = 4,
        condition_order = Conditions, modified_group = "last_in_original_order", clipping = false,
        calibration_executed = false, resampling_executed = false, random_draws = 0,
        contamination = 0, missingness = 0,
        rank_diagnostics = "U, ties and z are reconstructed independently in Python from emitted native metric arrays"
    };
    private static EntityProbe ProbeEntity(string entity, string group, double[] values)
    {
        double[] metrics = AnalysisEngine.Metrics(values);
        var availability = metrics.Select((v, m) =>
        {
            string reason = MetricRegistry.UnavailabilityReason(Keys[m], values);
            if (reason.Length == 0 && !double.IsFinite(v)) reason = "nonfinite_metric_value";
            return new Availability(Keys[m], double.IsFinite(v), reason, Class(v));
        }).ToArray();
        double variance = ScientificMath.Variance(values);
        return new(entity, group, values.Length, values, values.Average(), variance, Math.Sqrt(variance), metrics, availability);
    }
    private static bool InGroup(string a, string b) => a.Equals(b, StringComparison.OrdinalIgnoreCase);
    private static GroupGeometry[] Geometry(EntityProbe[] entities, string[] groups) => groups.Select(g =>
    {
        double[] means = entities.Where(e => InGroup(e.Group, g)).Select(e => e.Mean).ToArray();
        return new GroupGeometry(g, means.Average(), ScientificMath.Variance(means));
    }).ToArray();
    private static HalfProbe ProbeHalf(AnalysisData data, string side, string canonicalHash)
    {
        // Match Calibrate's pool construction and operation ordering, without invoking it.
        double[][] pool = data.Observations.GroupBy(o => o.Group + "\u001f" + o.Entity, StringComparer.OrdinalIgnoreCase)
            .Select(g => g.Select(o => o.Value).ToArray()).ToArray();
        double center = pool.Average(x => x.Average());
        double scale = Math.Max(Math.Abs(center), Math.Sqrt(pool.Average(x => ScientificMath.Variance(x))));
        if (!double.IsFinite(scale) || scale <= 0) scale = 1;
        EntityProbe[] original = data.Entities.Select(e => ProbeEntity(e.Entity, e.Group,
            data.Observations.Where(o => InGroup(o.Group, e.Group) && InGroup(o.Entity, e.Entity)).Select(o => o.Value).ToArray())).ToArray();
        var conditions = Conditions.Select(condition =>
        {
            EntityProbe[] entities = original.Select(e =>
            {
                // Identity and unaffected groups copy exact binary64 values, including signed zero.
                double[] values = condition == "identity" || !InGroup(e.Group, data.GroupNames[^1])
                    ? e.Values.ToArray()
                    : e.Values.Select(x => AnalysisEngine.Transform(x, e.Mean, center, scale, Effect, condition)).ToArray();
                return ProbeEntity(e.Entity, e.Group, values);
            }).ToArray();
            RankProbe[] ranks = Keys.Select((key, m) =>
            {
                double[][] vectors = data.GroupNames.Select(g => entities.Where(e => InGroup(e.Group, g))
                    .Select(e => e.Metrics[m]).Where(double.IsFinite).ToArray()).ToArray();
                bool sufficient = vectors.All(v => v.Length >= 4);
                double p = sufficient ? AnalysisEngine.MannWhitneyP(vectors[0], vectors[1]) : double.NaN;
                bool available = sufficient && double.IsFinite(p);
                return new RankProbe(key, condition != "identity" && MetricRegistry.IsNaturalForTrack(key, condition), vectors,
                    vectors[0].Length, vectors[1].Length, available,
                    available ? null : sufficient ? "rank_test_unavailable" : "insufficient_usable_entities",
                    p, DecisionPolicy.Adjust(p, Keys.Length), available ? DecisionPolicy.Reject(p, Alpha, Keys.Length) : null);
            }).ToArray();
            return new ConditionProbe(condition, condition == "identity" ? 1 : Effect, Geometry(entities, data.GroupNames), entities, ranks);
        }).ToArray();
        double[] means = Geometry(original, data.GroupNames).Select(g => g.EntityMeanAverage).ToArray();
        return new(side, canonicalHash, true, data.GroupNames, data.GroupCounts, center, scale, means,
            means[1] - means[0], original, conditions);
    }
    private static void ValidatePartition(AnalysisData built, AnalysisData left, AnalysisData right)
    {
        Require(built.GroupNames.SequenceEqual(left.GroupNames) && built.GroupNames.SequenceEqual(right.GroupNames), "Half group order changed.");
        string Key(EntityResult e) => e.Group.ToUpperInvariant() + "\u001f" + e.Entity.ToUpperInvariant();
        var a = left.Entities.Select(Key).ToHashSet(StringComparer.Ordinal);
        var b = right.Entities.Select(Key).ToHashSet(StringComparer.Ordinal);
        Require(!a.Overlaps(b) && a.Union(b).ToHashSet(StringComparer.Ordinal).SetEquals(built.Entities.Select(Key)), "Halves do not partition the original entities.");
        foreach (AnalysisData half in new[] { left, right })
        {
            var members = half.Entities.Select(Key).ToHashSet(StringComparer.Ordinal);
            var rows = built.Observations.Where(o => members.Contains(o.Group.ToUpperInvariant() + "\u001f" + o.Entity.ToUpperInvariant())).ToList();
            EqualJson(JsonSerializer.SerializeToElement(rows, Json), JsonSerializer.SerializeToElement(half.Observations, Json), "half.original_observation_order");
        }
    }
    private static object RunCase(Options options)
    {
        Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1" && Environment.ProcessorCount == 1,
            "Backups must be disabled and processor count fixed to one.");
        byte[] bytes = File.ReadAllBytes(options.Input);
        Require(Hash(bytes) == options.Sha256, "Input SHA mismatch.");
        using var document = ParseDocument(bytes);
        JsonElement root = document.RootElement;
        _ = LoadCase(root, options.Index, options.Synthetic);
        VerifyRuntime(root.GetProperty("identity"));
        AnalysisData built = LoadData(root, "built", options.Synthetic);
        AnalysisData left = LoadData(root, "left", options.Synthetic), right = LoadData(root, "right", options.Synthetic);
        string generated = root.GetProperty("data").GetProperty("generated").GetProperty("canonical_json").GetString()!;
        var observations = JsonSerializer.Deserialize<List<Observation>>(generated, Json) ?? throw new InvalidDataException("Missing generated observations.");
        EqualJson(JsonSerializer.SerializeToElement(AnalysisEngine.Build(observations, -1000000, 1000000, 6), Json),
            JsonSerializer.SerializeToElement(built, Json), "generated.recomputed_build");
        ValidatePartition(built, left, right);
        HalfProbe[] halves = new[] { ("left", left), ("right", right) }.Select(x =>
            ProbeHalf(x.Item2, x.Item1, root.GetProperty("data").GetProperty(x.Item1).GetProperty("sha256").GetString()!)).ToArray();
        Require(Hash(File.ReadAllBytes(options.Input)) == options.Sha256, "Input changed during diagnostic.");
        return new
        {
            schema = Schema, index = options.Index, status = "completed", synthetic = options.Synthetic,
            source_input = Path.GetFullPath(options.Input), source_input_sha256 = options.Sha256,
            freeze_sha256 = options.FreezeSha256, identity = Identity(), settings = ProbeSettings(), metric_order = Keys,
            conditions = Conditions, halves, nonfinite_fields = FindNonfinite(halves, "halves").ToArray()
        };
    }
    private static object Bind<T>(T value)
    {
        string canonical = JsonSerializer.Serialize(value, Json);
        return new { sha256 = Hash(Encoding.UTF8.GetBytes(canonical)), canonical_json = canonical, values = value };
    }
    private static object SyntheticInput()
    {
        var observations = new List<Observation>();
        for (int g = 0; g < 2; g++) for (int e = 0; e < 16; e++) for (int j = 0; j < 40; j++)
        {
            double[] residual = e % 8 == 2 ? new[] { -5d, -4, -3, -2, -1, 0, 1, 14 } : new[] { -3d, -1, 1, 3 };
            double center = (e % 8) switch { 0 => 0, 1 => -10 - g, _ => 100 + e * 2 + g * 3 };
            // Right-half failure-path fixture: only three finite relative/geometric summaries remain.
            if (e is >= 8 and < 13) { center = 0; residual = new[] { -3d, -1, 1, 3 }; }
            double value = center + residual[j % residual.Length] * (1 + (e % 3) * .25);
            observations.Add(new Observation("entity-" + g + "-" + e, "group-" + g, value, j + 1));
        }
        AnalysisData built = AnalysisEngine.Build(observations, -1000000, 1000000, 6);
        AnalysisData Half(bool first) => AnalysisEngine.Build(observations.Where(o => int.Parse(o.Entity.Split('-')[2], CultureInfo.InvariantCulture) < 8 == first).ToList(), -1000000, 1000000, 6);
        AnalysisData left = Half(true), right = Half(false);
        // These rows test the historical envelope only; they are explicitly synthetic and never calibrated.
        CalibrationRow[] rows = Keys.Select(k => new CalibrationRow(k, 0, 0, 0, 1, 1, 1, true, 1, false, "synthetic", Tracks.ToArray(),
            new double[3], new double[3], new[] { 1d, 1, 1 }, new[] { "synthetic", "synthetic", "synthetic" }, Repetitions,
            0, 0, new double[3], new double[3], new int[3], new[] { "synthetic", "synthetic", "synthetic" }, Alpha, 0)).ToArray();
        object AvailabilityRows() => Keys.Select(k => new { metric = k, row_present = true, score_finite = true, applicable = true, projected_to_zero = false }).ToArray();
        object Tau() => new { kendall_tau = 0, defined = true, undefined_reason = (string?)null, top_left_index = 0, top_right_index = 0, top_left = Keys[0], top_right = Keys[0], matched = true };
        return new
        {
            schema = SyntheticSchema, index = 0, status = "completed", diagnostics_status = "synthetic", error = "",
            seeds = new { run_seed = 20260904UL, derived_seed = BenchmarkRandom.Derive(20260904UL, 5, 1, 0), split_seed = 1, calibration_left_seed = 2, calibration_right_seed = 3 },
            settings = ExpectedSettings(), metric_order = Keys, identity = Identity(),
            data = new { generated = Bind(observations), built = Bind(built), left = Bind(left), right = Bind(right) },
            calibration_left = rows, calibration_right = rows,
            nonfinite_fields = new { calibration_left = System.Array.Empty<NonfiniteField>(), calibration_right = System.Array.Empty<NonfiniteField>() },
            scores_left = new double[12], scores_right = new double[12], availability_left = AvailabilityRows(), availability_right = AvailabilityRows(),
            legacy = Tau(), corrected = Tau(), resources = new { wall_seconds = 0, cpu_seconds = 0, peak_working_set_bytes = 0 }
        };
    }
    private sealed record RankFixture(string Id, double[] A, double[] B, double P, string PClass, double AdjustedP, bool? Reject);
    private static RankFixture Fixture(string id, double[] a, double[] b)
    {
        double p = AnalysisEngine.MannWhitneyP(a, b);
        return new(id, a, b, p, Class(p), DecisionPolicy.Adjust(p, Keys.Length), double.IsFinite(p) ? DecisionPolicy.Reject(p, Alpha, Keys.Length) : null);
    }
    private static void Close(double actual, double expected, string message) => Require(
        double.IsFinite(actual) && double.IsFinite(expected) && Math.Abs(actual - expected) <= 1e-12 + 1e-10 * Math.Abs(expected), message);
    private static object TransformFixture(string id, double[] values, double center, double populationCenter, double scale, double effect, string condition)
    {
        double[] transformed = values.Select(x => AnalysisEngine.Transform(x, center, populationCenter, scale, effect, condition)).ToArray();
        EntityProbe row = ProbeEntity(id, "toy", transformed);
        return new { id, values, entity_center = center, population_center = populationCenter, shift_scale = scale, effect, condition,
            transformed, metrics = row.Metrics, metric_availability = row.MetricAvailability };
    }
    private static object SelfTest()
    {
        var tests = new List<string>();
        void Test(string name, Action action) { action(); tests.Add(name); }
        void Reject(Action action)
        {
            bool rejected = false;
            try { action(); } catch (Exception e) when (e is InvalidDataException or JsonException or IOException) { rejected = true; }
            Require(rejected, "Expected fail-closed rejection.");
        }
        double[] offsets = { -7, -5, -3, -1, 1, 3, 5, 7 };
        double[] a = Enumerable.Range(1, 8).Select(i => (double)i).ToArray();
        RankFixture[] rankFixtures =
        {
            Fixture("u59", a, new[] { 3.5, 9, 10, 11, 12, 13, 14, 15 }),
            Fixture("u60", a, new[] { 4.5, 9, 10, 11, 12, 13, 14, 15 }),
            Fixture("heterogeneity_blindspot", offsets, offsets.Select(x => x * 2).ToArray()),
            Fixture("location", offsets, offsets.Select(x => x + 32).ToArray()),
            Fixture("all_ties", Enumerable.Repeat(1d, 8).ToArray(), Enumerable.Repeat(1d, 8).ToArray()),
            Fixture("empty", System.Array.Empty<double>(), a),
            Fixture("repeated_ties", new[] { 1d, 1, 2, 3 }, new[] { 1d, 2, 2, 4 }),
            Fixture("repeated_ties_swapped", new[] { 1d, 2, 2, 4 }, new[] { 1d, 1, 2, 3 })
        };
        Test("native_8_by_8_u59_nonreject_u60_reject", () => Require(rankFixtures[0].Reject == false && rankFixtures[1].Reject == true, "8x8 boundary changed."));
        Test("native_symmetric_scale_rank_blindspot", () => Require(Math.Abs(rankFixtures[2].P - 1) <= 2e-7 && rankFixtures[2].Reject == false, "Symmetric rank toy."));
        Test("native_location_positive_control", () => Require(rankFixtures[3].Reject == true, "Location toy."));
        Test("all_ties_empty_and_swapped_groups", () => Require(rankFixtures[4].P == 1 && double.IsNaN(rankFixtures[5].P) && Same(rankFixtures[6].P, rankFixtures[7].P), "Rank boundaries."));
        double[] symmetric = Enumerable.Range(0, 40).Select(i => 100 + new[] { -3d, -1, 1, 3 }[i % 4]).ToArray();
        double[] skewed = { 1, 2, 3, 4, 5, 6, 7, 20 };
        object[] transformFixtures =
        {
            TransformFixture("symmetric_variability", symmetric, 100, 100, 100, 2, "variability"),
            TransformFixture("skewed_variability", skewed, 6, 6, 6, 2, "variability"),
            TransformFixture("noise_variability", new[] { -1d, 0, 1 }, 0, 0, 1, Effect, "variability"),
            TransformFixture("zero_center", new[] { -3d, -1, 1, 3 }, 0, 0, 1, 2, "variability"),
            TransformFixture("location", symmetric, 100, 100, 100, Effect, "location"),
            TransformFixture("heterogeneity", symmetric, 100, 80, 80, 2, "heterogeneity")
        };
        Test("native_variability_affine_positive_control_all_seven", () =>
        {
            double[] before = AnalysisEngine.Metrics(symmetric);
            double[] after = AnalysisEngine.Metrics(symmetric.Select(x => AnalysisEngine.Transform(x, 100, 100, 100, 2, "variability")).ToArray());
            foreach (int m in new[] { 1, 2, 3, 4, 5, 6, 9 })
            {
                Close(after[m], 2 * before[m], "Symmetric spread scaling.");
                double p = AnalysisEngine.MannWhitneyP(Enumerable.Repeat(before[m], 8).ToArray(), Enumerable.Repeat(after[m], 8).ToArray());
                Require(DecisionPolicy.Reject(p, Alpha, Keys.Length), "Symmetric spread positive control.");
            }
        });
        Test("native_skewed_relative_denominator_and_geometric_availability", () =>
        {
            double[] after = skewed.Select(x => AnalysisEngine.Transform(x, 6, 6, 6, 2, "variability")).ToArray();
            Require(after.SequenceEqual(new[] { -4d, -2, 0, 2, 4, 6, 8, 34 }), "Skewed transform.");
            double[] x = AnalysisEngine.Metrics(skewed), y = AnalysisEngine.Metrics(after);
            Close(y[0], 3, "Changed median."); Close(y[5], 3 * x[5], "Normalized MAD."); Close(y[6], 3 * x[6], "Normalized IQR.");
            Require(double.IsFinite(x[10]) && double.IsNaN(y[10]), "Geometric availability.");
        });
        Test("native_heterogeneity_embedded_means_medians_trimmed_and_within", () =>
        {
            EntityProbe[] original = offsets.Select(c => ProbeEntity(c.ToString(CultureInfo.InvariantCulture), "A", symmetric.Select(x => x + c).ToArray())).ToArray();
            EntityProbe[] changed = original.Select(e => ProbeEntity(e.Entity, "B", e.Values.Select(x => AnalysisEngine.Transform(x, e.Mean, 100, 100, 2, "heterogeneity")).ToArray())).ToArray();
            for (int i = 0; i < original.Length; i++)
            {
                Close(changed[i].Mean, 100 + 2 * offsets[i], "Heterogeneity mean.");
                Close(changed[i].SampleVariance, original[i].SampleVariance, "Heterogeneity within variance.");
            }
            foreach (int m in new[] { 0, 7, 11 })
                Require(Math.Abs(AnalysisEngine.MannWhitneyP(original.Select(x => x.Metrics[m]).ToArray(), changed.Select(x => x.Metrics[m]).ToArray()) - 1) <= 2e-7, "Embedded heterogeneity rank blind spot.");
            Close(ScientificMath.Variance(changed.Select(x => x.Mean).ToArray()) / ScientificMath.Variance(original.Select(x => x.Mean).ToArray()), 4, "Between variance ratio.");
        });
        Test("identity_and_untouched_group_bit_preservation_no_clipping", () =>
        {
            using var document = ParseDocument(JsonSerializer.SerializeToUtf8Bytes(SyntheticInput(), Json));
            AnalysisData data = LoadData(document.RootElement, "left", true);
            HalfProbe half = ProbeHalf(data, "left", document.RootElement.GetProperty("data").GetProperty("left").GetProperty("sha256").GetString()!);
            foreach (ConditionProbe condition in half.Conditions) for (int i = 0; i < half.Entities.Length; i++)
                if (condition.Condition == "identity" || half.Entities[i].Group == half.GroupOrder[0])
                    Require(half.Entities[i].Values.Zip(condition.Entities[i].Values).All(p => Same(p.First, p.Second)), "Raw identity changed.");
            double extreme = AnalysisEngine.Transform(999999, 999999, 999999, 999999, Effect, "location");
            Require(extreme > 1000000, "Transform value was clipped.");
        });
        Test("strict_duplicate_json_and_reordered_metrics_fail_closed", () =>
        {
            Reject(() => { using var d = ParseDocument(Encoding.UTF8.GetBytes("{\"a\":1,\"a\":2}")); });
            JsonNode fixture = JsonSerializer.SerializeToNode(SyntheticInput(), Json)!;
            var order = (JsonArray)fixture["metric_order"]!; JsonNode? first = order[0]!.DeepClone(); order[0] = order[1]!.DeepClone(); order[1] = first;
            using var doc = ParseDocument(Encoding.UTF8.GetBytes(fixture.ToJsonString()));
            Reject(() => LoadCase(doc.RootElement, 0, true));
        });
        Test("strict_original_metric_recomputation_rejects_tampering", () =>
        {
            JsonNode fixture = JsonSerializer.SerializeToNode(SyntheticInput(), Json)!;
            JsonNode value = fixture["data"]!["left"]!["values"]!;
            value["entities"]![0]!["metrics"]![7] = 123;
            string canonical = value.ToJsonString(Json); fixture["data"]!["left"]!["canonical_json"] = canonical;
            fixture["data"]!["left"]!["sha256"] = Hash(Encoding.UTF8.GetBytes(canonical));
            using var doc = ParseDocument(Encoding.UTF8.GetBytes(fixture.ToJsonString()));
            Reject(() => LoadData(doc.RootElement, "left", true));
        });
        return new { schema = "mvs-scenario-mechanism-self-test/v1", status = "passed", test_count = tests.Count,
            tests, metric_order = Keys, rank_fixtures = rankFixtures, transform_fixtures = transformFixtures,
            nonfinite_fields = FindNonfinite(rankFixtures, "rank_fixtures").Concat(FindNonfinite(transformFixtures, "transform_fixtures")).ToArray(),
            identity = Identity(), calibration_executed = false, random_draws = 0 };
    }
    public static int Main(string[] args)
    {
        FileStream? output = null;
        Options? options = null;
        try
        {
            VerifyImplementation();
            if (args.SequenceEqual(new[] { "--inspect" }))
            { Write(new { schema = Schema, status = "ok", identity = Identity(), settings = ProbeSettings(), metric_order = Keys, conditions = Conditions }, null); return 0; }
            if (args.SequenceEqual(new[] { "--self-test" })) { Write(SelfTest(), null); return 0; }
            if (args.Length == 2 && args[0] == "--write-synthetic-input")
            {
                Require(!string.IsNullOrWhiteSpace(args[1]), "Empty synthetic path.");
                using var file = new FileStream(args[1], FileMode.CreateNew, FileAccess.Write, FileShare.Read);
                Write(SyntheticInput(), file); file.Flush(true);
                Write(new { schema = SyntheticSchema, status = "written", path = Path.GetFullPath(args[1]), sha256 = Hash(File.ReadAllBytes(args[1])), calibration_executed = false }, null); return 0;
            }
            options = Parse(args);
            // Reserve the final path before reading/processing; never overwrite or retry a case.
            output = new FileStream(options.Output, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
            object result = RunCase(options);
            Write(result, output); output.Flush(true);
            Write(new { schema = Schema, index = options.Index, status = "completed", synthetic = options.Synthetic, output = Path.GetFullPath(options.Output) }, null);
            return 0;
        }
        catch (Exception ex)
        {
            var failure = new { schema = Schema, index = options?.Index, status = "failed", synthetic = options?.Synthetic,
                source_input_sha256 = options?.Sha256, freeze_sha256 = options?.FreezeSha256, error = ex.ToString() };
            if (output != null && output.Length == 0) { Write(failure, output); output.Flush(true); }
            Write(failure, null); return 1;
        }
        finally { output?.Dispose(); }
    }
}
