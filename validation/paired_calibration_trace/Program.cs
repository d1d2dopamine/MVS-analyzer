using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.PairedCalibrationTrace;

// Test-only Round45 recorder. No retained execution is authorized by building or self-testing.
internal static class Program
{
    private const string Schema = "mvs-paired-calibration-case/v1";
    private const string InputSchema = "mvs-stability-replay-case/v1";
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
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options) => reader.TokenType == JsonTokenType.Number && double.IsFinite(reader.GetDouble()) ? reader.GetDouble() : throw new InvalidDataException("AnalysisData requires finite numbers.");
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        { if (double.IsFinite(value)) writer.WriteNumberValue(value); else writer.WriteNullValue(); }
    }
    private sealed record Options(string Input, int Index, string Sha256, string Output, string FreezeSha256);
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

    private static Loaded LoadCase(JsonElement root, int index)
    {
        Object(root, "$", "schema", "index", "status", "diagnostics_status", "error", "seeds", "settings", "metric_order", "identity", "data", "calibration_left", "calibration_right", "nonfinite_fields", "scores_left", "scores_right", "availability_left", "availability_right", "legacy", "corrected", "resources");
        Require(Text(root.GetProperty("schema"), "schema") == InputSchema, "Unknown input schema/version.");
        Require(Integer(root.GetProperty("index"), "index") == index, "Input index does not match requested pair.");
        Require(Text(root.GetProperty("status"), "status") == "completed" && Text(root.GetProperty("diagnostics_status"), "diagnostics_status") == "retained" && Text(root.GetProperty("error"), "error") == "", "Input is not a complete retained case.");
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
        var flags = new Dictionary<string, string>(StringComparer.Ordinal);
        Require(args.Length == 10, "Required: --input PATH --index N --sha256 HASH --out DIR --freeze-sha256 HASH.");
        for (int i = 0; i < args.Length; i += 2)
            Require(new[] { "--input", "--index", "--sha256", "--out", "--freeze-sha256" }.Contains(args[i]) && flags.TryAdd(args[i], args[i + 1]), "Unknown or duplicate flag.");
        Require(int.TryParse(flags["--index"], out int index) && index is >= 0 and < 120, "Index must be 0..119.");
        Require(IsHash(flags["--sha256"]) && IsHash(flags["--freeze-sha256"]), "Hashes must be lowercase SHA-256.");
        Require(!string.IsNullOrWhiteSpace(flags["--input"]) && !string.IsNullOrWhiteSpace(flags["--out"]), "Empty path.");
        return new(flags["--input"], index, flags["--sha256"], flags["--out"], flags["--freeze-sha256"]);
    }
    private static void VerifyImplementation()
    {
        Require(Environment.Version.ToString() == "8.0.31", "Runtime must be .NET 8.0.31.");
        Require(AnalysisEngine.MetricKeys.SequenceEqual(Keys) && AnalysisEngine.DefaultTracks.SequenceEqual(Tracks) && AnalysisEngine.EffectGrid.SequenceEqual(Grid), "Metric/track/grid order changed.");
        Require(typeof(CalibrationRow).GetProperties().Select(Name).ToHashSet().SetEquals(RowFields), "Row schema changed.");
        Require(BenchmarkProtocol.CalibrationEffect == 1.15 && BenchmarkProtocol.CalibrationScenario == "location" && BenchmarkProtocol.CalibrationOutlierRate == .02 && BenchmarkProtocol.CalibrationMissingRate == 0 && BenchmarkProtocol.Alpha == Alpha, "Recipe changed.");
    }
    private static AnalysisData LoadData(JsonElement root, string side)
    {
        JsonElement binding = root.GetProperty("data").GetProperty(side);
        string canonical = binding.GetProperty("canonical_json").GetString()!;
        Require(Hash(Encoding.UTF8.GetBytes(canonical)) == binding.GetProperty("sha256").GetString(), "Canonical data hash mismatch.");
        using var doc = ParseDocument(Encoding.UTF8.GetBytes(canonical));
        EqualJson(doc.RootElement, binding.GetProperty("values"), side + ".canonical");
        AnalysisData data = JsonSerializer.Deserialize<AnalysisData>(canonical, Json) ?? throw new InvalidDataException("Missing AnalysisData.");
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
            Require(entity.Metrics.Length == 12 && entity.Metrics.All(double.IsFinite), "Metric shape/nonfinite AnalysisData.");
            Require(data.Observations.Count(o => string.Equals(o.Group, entity.Group, StringComparison.OrdinalIgnoreCase) && string.Equals(o.Entity, entity.Entity, StringComparison.OrdinalIgnoreCase)) == entity.Measurements, "Entity observation count mismatch.");
        }
        Require(data.Entities.Sum(e => e.Measurements) == data.Observations.Count, "Orphan observations.");
        int[] sizes = data.Entities.Select(e => e.Measurements).Order().ToArray();
        Require(sizes.Length > 0 && sizes.All(n => n >= 6), "Invalid entity measurement count.");
        double median = sizes.Length % 2 == 0 ? (sizes[sizes.Length / 2 - 1] + (double)sizes[sizes.Length / 2]) / 2 : sizes[sizes.Length / 2];
        Require(Same(median, data.MedianMeasurements), "Derived median count mismatch.");
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
    private sealed class QuietProgress : IProgress<ProgressInfo> { public void Report(ProgressInfo value) { } }

    // Codec is deliberately independent of engine RNG and keeps no reference to native arrays.
    private static byte[] Encode(IReadOnlyList<int> codes)
    {
        var bytes = new byte[(codes.Count + 3) / 4];
        for (int i = 0; i < codes.Count; i++)
        {
            Require(codes[i] is >= -1 and <= 1, "Invalid code.");
            bytes[i / 4] |= (byte)((codes[i] + 1) << (2 * (i % 4)));
        }
        return bytes;
    }
    private static int[] Decode(byte[] bytes, int symbols)
    {
        Require(symbols >= 0 && bytes.Length == (symbols + 3) / 4, "Wrong codec length.");
        if (symbols % 4 != 0) Require((bytes[^1] >> (2 * (symbols % 4))) == 0, "Nonzero padding.");
        var result = new int[symbols];
        for (int i = 0; i < symbols; i++)
        {
            int code = (bytes[i / 4] >> (2 * (i % 4))) & 3;
            Require(code != 3, "Reserved code 11."); result[i] = code - 1;
        }
        return result;
    }
    private static int[] Flatten(AnalysisEngine.CalibrationStep step)
    {
        Require(step.Null is { Length: 12 } && step.Power is { Length: 3 } && step.Grid is { Length: 3 }, "Wrong simulation shape.");
        Require(step.Power.All(a => a is { Length: 12 }) && step.Grid.All(a => a is { Length: 12 }), "Wrong track shape.");
        return step.Null.Concat(step.Power.SelectMany(a => a)).Concat(step.Grid.SelectMany(a => a)).ToArray();
    }
    private sealed class Recorder : IRunRecording, IRunRecordingFactory
    {
        private readonly Stream output;
        private bool began, disposed, finished;
        private int diagnostic;
        public int Observed { get; private set; }
        public int[][] Counts { get; } = Enumerable.Range(0, 84).Select(_ => new int[3]).ToArray();
        public int[][][] GridCounts { get; } = Enumerable.Range(0, 5).Select(_ => Enumerable.Range(0, 84).Select(_ => new int[3]).ToArray()).ToArray();
        public bool EnvironmentChanged => false;
        public Recorder(Stream output) { this.output = output; }
        private void Active() => Require(began && !disposed && !finished, "Recorder lifecycle violation.");
        public IRunRecording Begin(BackupRequest request)
        {
            Require(!began && !disposed, "Session cannot be reused.");
            Require(request.Kind == "calibrate" && request.Repetitions == 1000 && request.Effect == 1.15 && request.Scenario == "location" && request.Outliers == .02 && request.Missing == 0 && request.Alpha == Alpha && request.Tracks != null && request.Tracks.SequenceEqual(Tracks), "Unexpected recording request.");
            began = true; return this;
        }
        public bool Try<T>(string key, out T value) { Active(); Require(key == "result", "Unexpected restoration key."); value = default!; return false; }
        public T Cached<T>(string key, Func<T> calculate)
        {
            Active();
            bool simulation = key.StartsWith("simulation/", StringComparison.Ordinal);
            if (simulation) Require(Observed < Repetitions && diagnostic == 0 && key == "simulation/" + Observed && typeof(T) == typeof(AnalysisEngine.CalibrationStep), "Unexpected simulation key/order/type.");
            else Require(Observed == Repetitions && diagnostic < 12 && key == "diagnostic/" + diagnostic && typeof(T) == typeof(CalibrationRow), "Unexpected diagnostic key/order/type.");
            // Invoke precisely once, return that exact instance unchanged, and never cache it.
            T value = calculate();
            if (simulation)
            {
                Require(value is AnalysisEngine.CalibrationStep, "Null step.");
                int[] codes = Flatten((AnalysisEngine.CalibrationStep)(object)value!);
                byte[] frame = Encode(codes);
                Require(frame.Length == 21, "Unexpected frame length.");
                output.Write(frame); output.Flush(); // OS visibility, not per-frame fsync.
                for (int i = 0; i < 84; i++) { Counts[i][codes[i] + 1]++; GridCounts[Observed % 5][i][codes[i] + 1]++; }
                Observed++;
            }
            else diagnostic++;
            return value;
        }
        public void Put<T>(string key, T value) { Active(); throw new InvalidDataException("Unexpected Put call: " + key); }
        public T Finish<T>(T value) { Active(); Require(Observed == Repetitions && diagnostic == 12, "Premature Finish."); finished = true; return value; }
        public void Dispose() { if (!disposed) { disposed = true; output.Flush(); } }
    }
    private static List<object> RowMismatches(CalibrationRow[] expected, CalibrationRow[] actual)
    {
        var mismatches = new List<object>();
        void Compare(object? a, object? b, string path)
        {
            if (a is double x && b is double y)
            {
                if (!Same(x, y)) mismatches.Add(new { path, expected_type = "double", actual_type = "double", expected_bits = BitConverter.DoubleToInt64Bits(x).ToString("x16"), actual_bits = BitConverter.DoubleToInt64Bits(y).ToString("x16"), expected = x.ToString("R", CultureInfo.InvariantCulture), actual = y.ToString("R", CultureInfo.InvariantCulture) });
            }
            else if (a is System.Array aa && b is System.Array bb)
            {
                if (aa.Length != bb.Length) mismatches.Add(new { path, error = "array_length", expected = aa.Length, actual = bb.Length });
                for (int i = 0; i < Math.Min(aa.Length, bb.Length); i++) Compare(aa.GetValue(i), bb.GetValue(i), path + "[" + i + "]");
            }
            else if (!Equals(a, b)) mismatches.Add(new { path, expected_type = a?.GetType().Name ?? "null", actual_type = b?.GetType().Name ?? "null", expected = a, actual = b });
        }
        if (expected.Length != actual.Length) mismatches.Add(new { path = "$", error = "row_count", expected = expected.Length, actual = actual.Length });
        for (int i = 0; i < Math.Min(expected.Length, actual.Length); i++)
            foreach (var property in typeof(CalibrationRow).GetProperties()) Compare(property.GetValue(expected[i]), property.GetValue(actual[i]), $"[{i}].{Name(property)}");
        return mismatches;
    }
    public static int Main(string[] args)
    {
        var files = new Dictionary<string, FileStream>(StringComparer.Ordinal);
        var halves = new Dictionary<string, string> { ["left"] = "not_started", ["right"] = "not_started" };
        Options? options = null;
        try
        {
            VerifyImplementation();
            if (args.SequenceEqual(new[] { "--inspect" })) { Write(new { schema = Schema, status = "ok", settings = ExpectedSettings(), metric_order = Keys, tracks = Tracks, grid = Grid, identity = Identity(), calibration_executed = false }, null); return 0; }
            if (args.SequenceEqual(new[] { "--self-test" })) { Write(SelfTest(), null); return 0; }
            options = Parse(args);
            Require(Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS") == "1" && Environment.ProcessorCount == 1, "Backups must be disabled and processor count fixed to one.");
            Require(!Directory.Exists(options.Output) || !Directory.EnumerateFileSystemEntries(options.Output).Any(), "Output must be new or empty.");
            Directory.CreateDirectory(options.Output);
            foreach (string name in new[] { "reservation.json", "left.started.json", "right.started.json", "left.codes.bin", "right.codes.bin", "left.rows.json", "right.rows.json", "left.meta.json", "right.meta.json", "result.json" })
                files.Add(name, new FileStream(Path.Combine(options.Output, name), FileMode.CreateNew, FileAccess.ReadWrite, FileShare.Read));
            Write(new { schema = Schema, index = options.Index, source_input = Path.GetFullPath(options.Input), source_input_sha256 = options.Sha256, freeze_sha256 = options.FreezeSha256, status = "reserved", identity = Identity(), utc = DateTimeOffset.UtcNow }, files["reservation.json"]);
            byte[] bytes = File.ReadAllBytes(options.Input);
            Require(Hash(bytes) == options.Sha256, "Input SHA mismatch.");
            using var document = ParseDocument(bytes);
            var root = document.RootElement;
            Loaded expected = LoadCase(root, options.Index);
            VerifyRuntime(root.GetProperty("identity"));
            AnalysisData left = LoadData(root, "left"), right = LoadData(root, "right");
            foreach (var (side, data, saved) in new[] { ("left", left, expected.Left), ("right", right, expected.Right) })
            {
                int seed = root.GetProperty("seeds").GetProperty("calibration_" + side + "_seed").GetInt32();
                string canonicalHash = root.GetProperty("data").GetProperty(side).GetProperty("sha256").GetString()!;
                halves[side] = "started";
                Write(new { schema = Schema, index = options.Index, side, seed, canonical_data_sha256 = canonicalHash, source_input_sha256 = options.Sha256, freeze_sha256 = options.FreezeSha256, utc = DateTimeOffset.UtcNow, status = "started" }, files[side + ".started.json"]);
                var recording = new Recorder(files[side + ".codes.bin"]);
                string? error = null;
                List<object> mismatches = new();
                try
                {
                    var rows = AnalysisEngine.CalibrateWithRecording(recording, data, Repetitions, 1.15, seed, new QuietProgress(), CancellationToken.None, "location", .02, 0, Alpha, Tracks.ToArray()).ToArray();
                    Write(new { rows, nonfinite_fields = FindNonfinite(rows) }, files[side + ".rows.json"]);
                    mismatches = RowMismatches(saved, rows);
                    Require(mismatches.Count == 0, "Native replay all-field mismatch.");
                    Require(recording.Observed == 1000 && files[side + ".codes.bin"].Length == 21000, "Incomplete trace.");
                    Require(Hash(File.ReadAllBytes(options.Input)) == options.Sha256, "Source input changed during replay.");
                    halves[side] = "completed";
                }
                catch (Exception ex) { halves[side] = "failed"; error = ex.ToString(); throw; }
                finally
                {
                    var raw = files[side + ".codes.bin"]; raw.Flush(); raw.Position = 0;
                    string sha = Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();
                    Write(new { schema = "mvs-calibration-codes-2bit/v1", index = options.Index, side, status = halves[side], seed,
                        source_input = Path.GetFullPath(options.Input), source_input_sha256 = options.Sha256, canonical_data_sha256 = canonicalHash, freeze_sha256 = options.FreezeSha256,
                        identity = Identity(), settings = ExpectedSettings(), metric_order = Keys, tracks = Tracks, grid = Grid,
                        code_mapping = new[] { new { code = -1, bits = "00" }, new { code = 0, bits = "01" }, new { code = 1, bits = "10" } },
                        flattening = "Null[metric],Power[track][metric],Grid[track][metric]", bit_order = "least-significant-symbol-first", header_bytes = 0,
                        expected_repetitions = 1000, observed_repetitions = recording.Observed, expected_symbols = 84000, observed_symbols = recording.Observed * 84,
                        expected_bytes = 21000, observed_bytes = raw.Length, significant_bits = recording.Observed * 168, complete_prefix_records = raw.Length / 21, residual_bytes = raw.Length % 21,
                        sha256 = sha, counts = recording.Counts, grid_counts = recording.GridCounts, count_code_order = new[] { -1, 0, 1 },
                        rows_file = side + ".rows.json", rows_sha256 = Hash(File.ReadAllBytes(Path.Combine(options.Output, side + ".rows.json"))),
                        all_field_match = halves[side] == "completed", mismatches, error }, files[side + ".meta.json"]);
                }
            }
            Write(new { schema = Schema, index = options.Index, status = "completed", halves, error = (string?)null }, files["result.json"]);
            Write(new { schema = Schema, index = options.Index, status = "completed", halves }, null); return 0;
        }
        catch (Exception ex)
        {
            var failure = new { schema = Schema, index = options?.Index, status = "failed", halves, error = ex.ToString() };
            if (files.TryGetValue("result.json", out var output) && output.Length == 0) Write(failure, output);
            Write(failure, null); return 1;
        }
        finally { foreach (var file in files.Values) file.Dispose(); }
    }
    private static BackupRequest SyntheticRequest() => new() { Kind = "calibrate", Repetitions = 1000, Effect = 1.15, Scenario = "location", Outliers = .02, Missing = 0, Alpha = Alpha, Tracks = Tracks.ToArray() };
    private static AnalysisEngine.CalibrationStep Step(int[] x) => new(x.Take(12).ToArray(), Enumerable.Range(0, 3).Select(t => x.Skip(12 + t * 12).Take(12).ToArray()).ToArray(), Enumerable.Range(0, 3).Select(t => x.Skip(48 + t * 12).Take(12).ToArray()).ToArray());
    private sealed class TornStream : MemoryStream
    {
        public override void Write(byte[] buffer, int offset, int count)
        {
            if (Length >= 21) { base.Write(buffer, offset, 5); throw new IOException("Synthetic torn write."); }
            base.Write(buffer, offset, count);
        }
        public override void Write(ReadOnlySpan<byte> buffer)
        {
            if (Length >= 21) { base.Write(buffer[..5]); throw new IOException("Synthetic torn write."); }
            base.Write(buffer);
        }
    }
    private static object SelfTest()
    {
        var tests = new List<string>();
        void Test(string name, Action action) { action(); tests.Add(name); }
        void Reject(Action action) { bool rejected = false; try { action(); } catch (Exception e) when (e is InvalidDataException or IOException or JsonException or NotSupportedException) { rejected = true; } Require(rejected, "Expected rejection."); }
        Test("codec_exact_bytes_roundtrip_padding_reserved", () =>
        {
            Require(Encode(new[] { -1, 0, 1, -1 }).SequenceEqual(new byte[] { 0x24 }), "0x24 fixture.");
            Require(Encode(new[] { 1, 0, -1, 1 }).SequenceEqual(new byte[] { 0x86 }), "0x86 fixture.");
            for (int a = -1; a <= 1; a++) for (int b = -1; b <= 1; b++) Require(Decode(Encode(new[] { a, b }), 2).SequenceEqual(new[] { a, b }), "Nine cells.");
            Reject(() => Decode(new byte[] { 3 }, 1)); Reject(() => Decode(new byte[] { 0x40 }, 1)); Reject(() => Decode(new byte[] { 0, 0 }, 1)); Reject(() => Decode(System.Array.Empty<byte>(), 1)); Reject(() => Encode(new[] { 2 }));
        });
        Test("recorder_1000_frames_all_84_positions_order_counts_no_alias_finish_dispose", () =>
        {
            using var stream = new MemoryStream(); var recorder = new Recorder(stream); Require(ReferenceEquals(recorder, recorder.Begin(SyntheticRequest())), "Own session.");
            Require(!recorder.Try<object>("result", out var _) && !recorder.EnvironmentChanged, "No restoration.");
            int calls = 0; var expected = new List<int[]>();
            for (int rep = 0; rep < 1000; rep++)
            {
                int divisor = (int)Math.Pow(3, rep % 5);
                int[] codes = Enumerable.Range(0, 84).Select(i => (i / divisor) % 3 - 1).ToArray(); expected.Add(codes);
                var value = Step(codes); int[] before = Flatten(value);
                var result = recorder.Cached("simulation/" + rep, () => { calls++; return value; });
                Require(ReferenceEquals(result, value) && Flatten(value).SequenceEqual(before), "Changed native result.");
                // A subsequent caller mutation must not alias retained bytes or counts.
                value.Null[0] = 1;
                Require(stream.Length == (rep + 1) * 21, "Frame not visible before delegate return.");
            }
            Require(calls == 1000, "Delegate executed more than once.");
            byte[] bytes = stream.ToArray();
            for (int rep = 0; rep < 1000; rep++) Require(Decode(bytes.AsSpan(rep * 21, 21).ToArray(), 84).SequenceEqual(expected[rep]), "Position/track transpose.");
            Require(Enumerable.Range(0, 84).Select(i => string.Join(",", expected.Take(5).Select(c => c[i]))).Distinct().Count() == 84, "Position patterns not unique.");
            Require(recorder.Counts.All(c => c.Sum() == 1000) && recorder.GridCounts.All(g => g.All(c => c.Sum() == 200)), "rep%5 allocation.");
            for (int i = 0; i < 84; i++) for (int c = -1; c <= 1; c++) Require(recorder.Counts[i][c + 1] == expected.Count(v => v[i] == c), "Native count mismatch.");
            for (int m = 0; m < 12; m++)
            {
                var row = new CalibrationRow(Keys[m], 0, 0, 0);
                Require(ReferenceEquals(row, recorder.Cached("diagnostic/" + m, () => { calls++; return row; })), "Diagnostic not passed through.");
            }
            var rows = new List<CalibrationRow>(); Require(ReferenceEquals(rows, recorder.Finish(rows)) && calls == 1012, "Finish changed result.");
            Reject(() => recorder.Cached("simulation/1000", () => Step(new int[84])));
            recorder.Dispose(); recorder.Dispose(); Reject(() => recorder.Try<object>("result", out _)); Reject(() => recorder.Begin(SyntheticRequest()));
        });
        Test("wrong_key_order_type_shape_and_delegate_failure", () =>
        {
            using var s = new MemoryStream(); var r = new Recorder(s); r.Begin(SyntheticRequest()); int calls = 0;
            Reject(() => r.Cached("simulation/1", () => { calls++; return Step(new int[84]); }));
            Reject(() => r.Cached("simulation/00", () => { calls++; return Step(new int[84]); }));
            Reject(() => r.Cached("simulation/0", () => { calls++; return 1; })); Require(calls == 0, "Invalid requests called delegate.");
            Reject(() => r.Cached<AnalysisEngine.CalibrationStep>("simulation/0", () => { calls++; throw new IOException("delegate"); })); Require(calls == 1 && s.Length == 0, "Delegate failure retried.");
            Reject(() => r.Cached("simulation/0", () => new AnalysisEngine.CalibrationStep(new int[11], new[] { new int[12], new int[12], new int[12] }, new[] { new int[12], new int[12], new int[12] })));
            r.Cached("simulation/0", () => Step(new int[84]));
            Reject(() => r.Cached("simulation/0", () => Step(new int[84]))); Reject(() => r.Cached("diagnostic/0", () => new CalibrationRow("median", 0, 0, 0))); Reject(() => r.Finish(1)); Reject(() => r.Put("x", 1)); r.Dispose();
        });
        Test("physical_complete_prefix_and_torn_suffix_survive_failure", () =>
        {
            string path = Path.Combine(Path.GetTempPath(), "mvs-r45-synthetic-" + Guid.NewGuid().ToString("N") + ".bin");
            try
            {
                using (var file = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.Read))
                {
                    var r = new Recorder(file); r.Begin(SyntheticRequest()); r.Cached("simulation/0", () => Step(new int[84]));
                    Require(File.ReadAllBytes(path).Length == 21, "Physical prefix buffered.");
                    Reject(() => r.Cached<AnalysisEngine.CalibrationStep>("simulation/1", () => throw new IOException("synthetic"))); r.Dispose();
                }
                Require(File.ReadAllBytes(path).Length == 21, "Prefix lost on dispose.");
            }
            finally { File.Delete(path); } // Synthetic fixture only; retained failures are never deleted.
            using var torn = new TornStream(); var recorder = new Recorder(torn); recorder.Begin(SyntheticRequest());
            recorder.Cached("simulation/0", () => Step(new int[84]));
            Reject(() => recorder.Cached("simulation/1", () => Step(new int[84])));
            Require(torn.Length == 26 && recorder.Observed == 1 && torn.Length / 21 == 1 && torn.Length % 21 == 5, "Torn suffix accounting."); recorder.Dispose();
        });
        Test("exact_rows_all_25_fields_types_ulp_signedzero_nonfinite", () =>
        {
            var original = new CalibrationRow("median", 0, .5, .2, Tracks: Tracks.ToArray(), TrackPowers: new[] { .5, .4, .3 }, TrackScores: new[] { .2, .1, 0.0 }, TrackMdes: new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity }, TrackCurves: new[] { "a", "b", "c" }, TrackPowerLow: new[] { 0.0, 0.0, 0.0 }, TrackPowerHigh: new[] { 1.0, 1.0, 1.0 }, TrackFailures: new[] { 0, 0, 0 }, TrackMdeStatus: new[] { "a", "b", "c" });
            foreach (var property in typeof(CalibrationRow).GetProperties())
            {
                var changed = original with { }; object? value = property.GetValue(original);
                object replacement = value switch { double d => double.IsNaN(d) ? 0.0 : Math.BitIncrement(d), int n => n + 1, bool b => !b, string s => s + "x", double[] a => a.Append(0).ToArray(), int[] a => a.Append(0).ToArray(), string[] a => a.Reverse().Append("x").ToArray(), _ => throw new InvalidDataException("Unhandled row property.") };
                property.SetValue(changed, replacement); Require(RowMismatches(new[] { original }, new[] { changed }).Count > 0, "Missed field: " + property.Name);
            }
            Require(RowMismatches(new[] { original }, new[] { original with { Fpr = -0.0 } }).Count == 1, "Signed zero.");
            Require(RowMismatches(new[] { original }, new[] { original with { Mde = double.PositiveInfinity } }).Count == 1, "Nonfinite class.");
            var labels = FindNonfinite(new[] { original }); Require(labels.Count == 6 && labels.Any(x => x.Value == "-Infinity"), "Nonfinite labels.");
            using var docA = ParseDocument(Encoding.UTF8.GetBytes("{\"a\":1,\"b\":true}")); using var docB = ParseDocument(Encoding.UTF8.GetBytes("{\"b\":true,\"a\":1}")); EqualJson(docA.RootElement, docB.RootElement, "$synthetic");
            Reject(() => ParseDocument(Encoding.UTF8.GetBytes("{\"a\":1,\"a\":2}")));
        });
        Test("typed_row_loader_rejects_nonfinite_metadata_and_schema_corruption", () =>
        {
            var rows = Keys.Select(key => new CalibrationRow(key, 0, .5, .25, Tracks: Tracks.ToArray(), TrackPowers: new[] { .5, .4, .3 }, TrackScores: new[] { .25, .2, .1 }, TrackMdes: new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity }, TrackCurves: new[] { "1:0", "1:0", "1:0" }, Repetitions: 1000, FprLow: 0, FprHigh: .1, TrackPowerLow: new[] { .4, .3, .2 }, TrackPowerHigh: new[] { .6, .5, .4 }, TrackFailures: new[] { 0, 1, 2 }, TrackMdeStatus: new[] { "a", "b", "c" })).ToArray();
            JsonElement encoded = JsonSerializer.SerializeToElement(rows, Json), labels = JsonSerializer.SerializeToElement(FindNonfinite(rows), Json);
            Require(RowMismatches(rows, LoadRows(encoded, labels, "synthetic")).Count == 0, "Typed restore mismatch.");
            JsonNode rowNode = JsonNode.Parse(encoded.GetRawText())!, labelNode = JsonNode.Parse(labels.GetRawText())!;
            JsonElement Element(JsonNode node) => JsonSerializer.SerializeToElement(node);
            var wrong = labelNode.DeepClone().AsArray(); wrong.RemoveAt(0); Reject(() => LoadRows(encoded, Element(wrong), "missing_label"));
            wrong = labelNode.DeepClone().AsArray(); wrong.Add(wrong[0]!.DeepClone()); Reject(() => LoadRows(encoded, Element(wrong), "duplicate_label"));
            wrong = labelNode.DeepClone().AsArray(); wrong[0]!["path"] = "[0].fpr"; Reject(() => LoadRows(encoded, Element(wrong), "finite_label"));
            wrong = labelNode.DeepClone().AsArray(); wrong[0]!["value"] = "unknown"; Reject(() => LoadRows(encoded, Element(wrong), "unknown_class"));
            var changed = rowNode.DeepClone(); changed[0]!["repetitions"] = true; Reject(() => LoadRows(Element(changed), labels, "bool_as_int"));
            changed = rowNode.DeepClone(); changed[0]!.AsObject().Remove("fpr"); Reject(() => LoadRows(Element(changed), labels, "missing_property"));
            changed = rowNode.DeepClone(); changed[0]!["unexpected"] = 1; Reject(() => LoadRows(Element(changed), labels, "extra_property"));
            changed = rowNode.DeepClone(); changed[0]!["tracks"]!.AsArray().RemoveAt(0); Reject(() => LoadRows(Element(changed), labels, "short_array"));
        });
        Test("analysis_data_direct_deserialization_roundtrip_derived_counts", () =>
        {
            var entities = Enumerable.Range(0, 8).Select(i => new EntityResult("e" + i, i < 4 ? "a" : "b", Enumerable.Repeat(1.0, 12).ToArray(), 6)).ToList();
            var observations = entities.SelectMany(e => Enumerable.Range(0, 6).Select(n => new Observation(e.Entity, e.Group, 1, n))).ToList();
            var data = new AnalysisData { Observations = observations, Entities = entities, GroupNames = new[] { "a", "b" }, GroupCounts = new[] { 4, 4 }, ValidRows = 48, MedianMeasurements = 6, MinValueApplied = -1000000, MaxValueApplied = 1000000, MinMeasurementsApplied = 6 };
            JsonElement Wrap(AnalysisData value) { string canonical = JsonSerializer.Serialize(value, Json); return JsonSerializer.SerializeToElement(new { data = new { left = new { canonical_json = canonical, sha256 = Hash(Encoding.UTF8.GetBytes(canonical)), values = value } } }, Json); }
            AnalysisData restored = LoadData(Wrap(data), "left"); Require(restored.Observations.SequenceEqual(observations), "Observation order altered.");
            data.GroupCounts[0] = 5; Reject(() => LoadData(Wrap(data), "left")); data.GroupCounts[0] = 4;
            data.Entities[0] = entities[0] with { Measurements = 7 }; Reject(() => LoadData(Wrap(data), "left"));
        });
        Test("recorder_has_no_random_state_or_rng_references", () =>
        {
            Require(typeof(Recorder).GetFields(BindingFlags.Instance | BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public).All(f => !typeof(Random).IsAssignableFrom(f.FieldType)), "Recorder owns RNG.");
            // No recorder method contains a metadata token resolving to any Random type member.
            foreach (var method in typeof(Recorder).GetMethods(BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic))
            {
                byte[] il = method.GetMethodBody()?.GetILAsByteArray() ?? System.Array.Empty<byte>();
                for (int i = 0; i + 4 < il.Length; i++) if (il[i] is 0x28 or 0x6f or 0x73)
                {
                    try { var member = method.Module.ResolveMethod(BitConverter.ToInt32(il, i + 1)); Require(member?.DeclaringType != typeof(Random) && member?.DeclaringType != typeof(BenchmarkRandom), "Recorder invokes RNG."); }
                    catch (ArgumentException) { } // Byte within an operand, not a method token.
                }
            }
        });
        return new { schema = Schema, status = "ok", mode = "self-test", calibration_executed = false, tests, identity = Identity() };
    }
}
