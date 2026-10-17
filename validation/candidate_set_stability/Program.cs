using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.CandidateSetStability;

// Round44 diagnostic only. Loads retained rows; never generates, splits, or calibrates data.
// The original Core APIs below, not a copied selector, supply every reported recommendation.
internal static class Program
{
    private const string Schema = "mvs-candidate-set-audit/v1";
    private const string InputSchema = "mvs-stability-replay-case/v1";
    private const string MethodId = "family-power-ci-overlap-v1";
    private const int Repetitions = 1000;
    private const double Alpha = .05;
    private const double ValidationTolerance = 1e-15;
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
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options) => throw new NotSupportedException("Use the provenance-aware loader.");
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        { if (double.IsFinite(value)) writer.WriteNumberValue(value); else writer.WriteNullValue(); }
    }
    private sealed record Options(string Input, int Index, string Sha256, string Output);
    private sealed record Loaded(CalibrationRow[] Left, CalibrationRow[] Right, JsonElement LeftNonfinite, JsonElement RightNonfinite);
    private sealed record NonfiniteField(string Path, string Value);
    private static void Require(bool condition, string message)
    { if (!condition) throw new InvalidDataException(message); }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static bool IsHash(string text) => text.Length == 64 && text.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static bool Same(double a, double b) => double.IsNaN(a) ? double.IsNaN(b) : BitConverter.DoubleToInt64Bits(a) == BitConverter.DoubleToInt64Bits(b);
    private static string Name(PropertyInfo property) => JsonNamingPolicy.SnakeCaseLower.ConvertName(property.Name);

    public static int Main(string[] args)
    {
        Options? options = null;
        FileStream? output = null;
        try
        {
            VerifyImplementation();
            if (args.SequenceEqual(new[] { "--self-test" }))
            { Write(SelfTest(), null); return 0; }
            options = Parse(args);
            Require(Path.GetFullPath(options.Input) != Path.GetFullPath(options.Output), "Input and output must differ.");
            // Reserve the destination before reading the input. An existing artifact is never replaced.
            output = new FileStream(options.Output, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            byte[] bytes = File.ReadAllBytes(options.Input);
            Require(Hash(bytes) == options.Sha256, "input: SHA-256 differs from the authorized binding.");
            using JsonDocument document = ParseDocument(bytes);
            Loaded rows = LoadCase(document.RootElement, options.Index);
            object result = Evaluate(rows, options.Index, options.Sha256);
            // Detect mutations during evaluation without replacing the retained input.
            Require(Hash(File.ReadAllBytes(options.Input)) == options.Sha256, "input: SHA-256 changed during evaluation.");
            Write(result, output);
            return 0;
        }
        catch (Exception error)
        {
            var failure = new { schema = Schema, status = "failed", index = options?.Index, input_sha256 = options?.Sha256,
                method_id = MethodId, error = new { type = error.GetType().Name, message = error.Message } };
            try { if (output != null) { output.SetLength(0); output.Position = 0; } Write(failure, output); }
            catch { Console.Error.WriteLine(JsonSerializer.Serialize(failure, Json)); }
            return 1;
        }
        finally { output?.Dispose(); }
    }

    private static Options Parse(string[] args)
    {
        var flags = new Dictionary<string, string>(StringComparer.Ordinal);
        Require(args.Length == 8, "Use --input FILE --index 0..119 --sha256 LOWERCASE_SHA256 --out NEWFILE, or --self-test.");
        for (int i = 0; i < args.Length; i += 2)
        {
            Require(new[] { "--input", "--index", "--sha256", "--out" }.Contains(args[i]), "Unknown argument: " + args[i]);
            Require(!string.IsNullOrWhiteSpace(args[i + 1]) && flags.TryAdd(args[i], args[i + 1]), "Empty or duplicate argument: " + args[i]);
        }
        Require(int.TryParse(flags["--index"], NumberStyles.None, CultureInfo.InvariantCulture, out int index) && index is >= 0 and <= 119, "Index must be 0..119.");
        Require(IsHash(flags["--sha256"]), "Expected SHA-256 must be 64 lowercase hexadecimal characters.");
        return new(flags["--input"], index, flags["--sha256"], flags["--out"]);
    }

    private static void VerifyImplementation()
    {
        Require(Environment.Version.ToString() == "8.0.31", "The frozen runtime must be .NET 8.0.31.");
        Require(CalibrationRecommendations.MethodId == MethodId, "Recommendation method changed.");
        Require(AnalysisEngine.MetricKeys.SequenceEqual(Keys), "Legacy metric order changed.");
        Require(AnalysisEngine.DefaultTracks.SequenceEqual(Tracks), "Track order changed.");
        Require(AnalysisEngine.CandidateMinPower == .70, "Recommendation quality threshold changed.");
        Require(DecisionPolicy.FprLimit(Alpha / Keys.Length) == Math.Min(1, Math.Max(1.5 * (Alpha / 12), Alpha / 12 + .02)), "Null limit changed.");
        Require(typeof(CalibrationRow).GetProperties().Select(Name).ToHashSet().SetEquals(RowFields), "CalibrationRow shape changed.");
        Require(BenchmarkProtocol.Alpha == Alpha && BenchmarkProtocol.CalibrationEffect == 1.15 && BenchmarkProtocol.CalibrationScenario == "location" &&
            BenchmarkProtocol.CalibrationOutlierRate == .02 && BenchmarkProtocol.CalibrationMissingRate == 0, "Original recipe constants changed.");
        string[][] families = { new[] { "median", "mean", "geometric_mean", "trimmed_mean_20" },
            new[] { "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad", "normalized_iqr", "range" },
            new[] { "median", "mean", "geometric_mean", "trimmed_mean_20" } };
        for (int t = 0; t < Tracks.Length; t++)
            Require(Keys.Where(k => MetricRegistry.IsNaturalForTrack(k, Tracks[t])).SequenceEqual(families[t]), "Natural family changed: " + Tracks[t]);
    }

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
            VerifyRow(rows[i], side + prefix);
            EqualJson(row, JsonSerializer.SerializeToElement(rows[i], Json), side + prefix);
        }
        Require(consumed.SetEquals(labels.Keys), side + ": nonfinite metadata contains an unknown, wrong-row, or out-of-range path.");
        // Compare labels as a mapping, but preserve the source metadata order in the result.
        var restored = FindNonfinite(rows).ToDictionary(x => x.Path, x => x.Value, StringComparer.Ordinal);
        Require(restored.Count == labels.Count && labels.All(x => restored.TryGetValue(x.Key, out string? value) && value == x.Value), side + ": nonfinite round-trip changed a class or path.");
        return rows;
    }

    private static void VerifyRow(CalibrationRow row, string path)
    {
        Require(row.Alpha == Alpha && row.Repetitions == Repetitions, path + ": alpha/repetitions differ from frozen recipe.");
        Require(row.Tracks!.SequenceEqual(Tracks), path + ": missing, duplicate, unknown, or reordered tracks.");
        Require(row.NullFailures is >= 0 and <= Repetitions && row.TrackFailures!.All(x => x is >= 0 and <= Repetitions), path + ": invalid failure count.");
        if (row.Applicable)
        {
            Require(Repetitions - row.NullFailures >= .9 * Repetitions, path + ": applicable despite insufficient null-valid replications.");
            VerifyInterval(row.Fpr, row.FprLow, row.FprHigh, row.NullFailures, path + ".fpr");
        }
        else Require(double.IsNaN(row.Fpr) && double.IsNaN(row.FprLow) && double.IsNaN(row.FprHigh), path + ": non-applicable FPR triplet must be explicitly NaN.");
        Require(row.FprInflated == (double.IsFinite(row.Fpr) && row.Fpr > DecisionPolicy.FprLimit(Alpha / Keys.Length)), path + ": retained FprInflated disagrees with original rule.");
        for (int t = 0; t < Tracks.Length; t++)
        {
            double p = row.TrackPowers![t], low = row.TrackPowerLow![t], high = row.TrackPowerHigh![t], score = row.TrackScores![t];
            if (row.Applicable && Repetitions - row.TrackFailures![t] >= .9 * Repetitions)
            { VerifyInterval(p, low, high, row.TrackFailures[t], path + "." + Tracks[t]); Require(double.IsFinite(score), path + "." + Tracks[t] + ": available power requires finite score."); }
            else Require(double.IsNaN(p) && double.IsNaN(low) && double.IsNaN(high) && double.IsNaN(score), path + "." + Tracks[t] + ": unavailable P/L/U/score must all be explicitly NaN.");
        }
        Require(Same(row.Power, row.TrackPowers![0]) && Same(row.Score, row.TrackScores![0]) && Same(row.Mde, row.TrackMdes![0]) && row.PowerCurve == row.TrackCurves![0], path + ": primary scalars do not match first track.");
    }
    private static void VerifyInterval(double point, double low, double high, int failures, string path)
    {
        Require(double.IsFinite(point) && double.IsFinite(low) && double.IsFinite(high), path + ": selector rate/bounds must be finite.");
        Require(point is >= 0 and <= 1 && low is >= 0 and <= 1 && high is >= 0 and <= 1 && low <= high && low - point <= ValidationTolerance && point - high <= ValidationTolerance, path + ": invalid probability interval.");
        int successes = (int)Math.Round(point * Repetitions, MidpointRounding.ToEven);
        Require(successes is >= 0 and <= Repetitions && point == successes / (double)Repetitions && successes <= Repetitions - failures, path + ": point estimate is inconsistent with requested-replication count or failures.");
        // Independent endpoint arithmetic is solely input validation. The selector receives
        // the exact retained doubles, including endpoint roundoff at zero and one.
        var expected = WilsonReference(successes);
        Require(Math.Abs(low - expected.Low) <= ValidationTolerance && Math.Abs(high - expected.High) <= ValidationTolerance, path + ": retained interval disagrees with count-derived Wilson endpoints.");
    }
    private static (double Low, double High) WilsonReference(int successes)
    {
        double zSquared = 1.959963984540054 * 1.959963984540054;
        double point = successes / (double)Repetitions;
        double divisor = 1 + zSquared / Repetitions;
        double center = (point + zSquared / (2 * Repetitions)) / divisor;
        double halfWidth = 1.959963984540054 * Math.Sqrt(point * (1 - point) / Repetitions + zSquared / (4.0 * Repetitions * Repetitions)) / divisor;
        return (Math.Max(0, center - halfWidth), Math.Min(1, center + halfWidth));
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
    private static object Evaluate(Loaded rows, int index, string inputSha256)
    {
        var evaluations = new List<object>();
        foreach (var (side, half) in new[] { ("left", rows.Left), ("right", rows.Right) })
            foreach (string track in Tracks)
            {
                // Required direct calls into the unchanged production Core assembly.
                CalibrationRecommendation[] build = CalibrationRecommendations.Build(half, track);
                CalibrationTrackRecommendation summary = CalibrationRecommendations.Summarize(half, track);
                Require(build.Length == 12 && build.Select(x => x.Metric).SequenceEqual(Keys), side + "/" + track + ": native output order changed.");
                Require(build.All(x => x.Track == track && x.Family == MetricRegistry.FamilyForTrack(track)), side + "/" + track + ": native track/family mismatch.");
                Require(summary.Candidates.SequenceEqual(build.Where(x => x.Candidate).Select(x => x.Metric)) && summary.QualifiedCandidates.SequenceEqual(build.Where(x => x.Candidate && x.Quality == "qualified").Select(x => x.Metric)), side + "/" + track + ": Build/Summarize set mismatch.");
                var nonfinite = FindNonfinite(build, "build"); nonfinite.AddRange(FindNonfinite(summary, "summary"));
                evaluations.Add(new { side, track, build, summary, nonfinite_fields = nonfinite });
            }
        return new { schema = Schema, status = "completed", index, input_sha256 = inputSha256, method_id = MethodId, identity = Identity(),
            validation = new { accepted = true, half_count = 2, track_count = 3, build_invocations = 6, summarize_invocations = 6, exact_finite_roundtrip = true },
            inputs = new { left = new { rows = rows.Left, nonfinite_fields = rows.LeftNonfinite }, right = new { rows = rows.Right, nonfinite_fields = rows.RightNonfinite } }, evaluations };
    }
    private static object Identity() => new { harness_sha256 = Hash(File.ReadAllBytes(typeof(Program).Assembly.Location)), core_sha256 = Hash(File.ReadAllBytes(typeof(AnalysisEngine).Assembly.Location)),
        runtime = RuntimeInformation.FrameworkDescription, os = RuntimeInformation.OSDescription, architecture = RuntimeInformation.ProcessArchitecture.ToString(), engine_version = AnalysisEngine.EngineVersion };
    private static void Write(object value, Stream? output)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, Json);
        if (output == null) { using Stream stdout = Console.OpenStandardOutput(); stdout.Write(bytes); stdout.WriteByte(10); stdout.Flush(); }
        else { output.Write(bytes); output.WriteByte(10); output.Flush(); if (output is FileStream file) file.Flush(true); }
    }

    // Synthetic-only tests. Fixtures are constructed in memory; no retained file is opened.
    private static object SelfTest()
    {
        var tests = new List<string>();
        void Check(string name, Action test) { test(); tests.Add(name); }
        void Reject(Action test, string reason)
        { bool rejected = false; try { test(); } catch (InvalidDataException) { rejected = true; } catch (JsonException) { rejected = true; } Require(rejected, "Self-test accepted " + reason); }
        Check("argument_boundaries", () => {
            foreach (int i in new[] { 0, 119 }) Require(Parse(new[] { "--input", "synthetic.json", "--index", i.ToString(CultureInfo.InvariantCulture), "--sha256", new string('a', 64), "--out", "new.json" }).Index == i, "Index boundary rejected.");
            foreach (string i in new[] { "-1", "120", "1.0", "NaN" }) Reject(() => Parse(new[] { "--input", "x", "--index", i, "--sha256", new string('a', 64), "--out", "y" }), "invalid index");
            Reject(() => Parse(new[] { "--input", "x", "--index", "0", "--sha256", "bad", "--out", "y" }), "bad hash");
            Reject(() => Parse(new[] { "--input", "x", "--index", "0", "--sha256", new string('a', 64), "--index", "1" }), "duplicate flag");
        });
        Check("family_maps_and_magnitude_exclusion", () => {
            CalibrationRow[] rows = SyntheticRows();
            foreach (var (track, size) in new[] { (Tracks[0], 4), (Tracks[1], 7), (Tracks[2], 4) }) {
                var r = CalibrationRecommendations.Build(rows, track); Require(r.Count(x => x.FamilyEligible) == size && !r.Single(x => x.Metric == "rms").Candidate, "Family count or RMS exclusion failed."); }
        });
        Check("unique_best_and_tied_best_legacy_order", () => {
            var rows = SyntheticRows(); rows[7] = SetPower(rows[7], .9, .8, .95);
            Require(CalibrationRecommendations.Summarize(rows, "location").BestMetric == "mean", "Unique best failed.");
            rows[0] = SetPower(rows[0], .9, .75, .95);
            var r = CalibrationRecommendations.Build(rows, "location"); var s = CalibrationRecommendations.Summarize(rows, "location");
            Require(s.BestMetric == "median" && s.BestPowerLow == .75 && r.All(x => x.BestPowerLow == .75) && r[0].BestPower == .9 && r[7].Candidate, "Tie order failed.");
        });
        Check("inclusive_touch_separation_weaker_power_and_full_family", () => {
            var rows = SyntheticRows(); rows[0] = SetPower(rows[0], .9, .8, .95); rows[7] = SetPower(rows[7], .7, .6, .8);
            rows[10] = SetPower(rows[10], .7, .6, Math.BitDecrement(.8)); rows[11] = SetPower(rows[11], .85, .7, .92);
            var r = CalibrationRecommendations.Build(rows, "location"); Require(r[7].Candidate && !r[10].Candidate && r[11].Candidate, "Inclusive overlap boundary failed.");
            Require(CalibrationRecommendations.Summarize(SyntheticRows(), "location").Candidates.Length == 4, "Full family failed.");
        });
        Check("null_limit_adjacent_double_and_inflated_exclusion", () => {
            var rows = SyntheticRows(); double limit = DecisionPolicy.FprLimit(Alpha / 12);
            rows[0] = rows[0] with { FprHigh = limit }; rows[7] = rows[7] with { FprHigh = Math.BitIncrement(limit) }; rows[10] = rows[10] with { FprInflated = true };
            var r = CalibrationRecommendations.Build(rows, "location"); Require(r[0].Candidate && !r[7].Candidate && !r[10].Candidate, "Null control boundary failed.");
        });
        Check("quality_boundary_is_not_membership_gate", () => {
            var rows = SyntheticRows(); rows[0] = SetPower(rows[0], .8, .70, .9); rows[7] = SetPower(rows[7], .8, Math.BitDecrement(.70), .9);
            var r = CalibrationRecommendations.Build(rows, "location"); Require(r[0].Candidate && r[0].Quality == "qualified" && r[7].Candidate && r[7].Quality == "uncertain_power", "Quality/membership boundary failed.");
        });
        Check("no_applicable_and_no_null_controlled_empty", () => {
            var unavailable = SyntheticRows().Select(Unavailable).ToArray();
            var controlled = SyntheticRows().Select(x => x with { FprHigh = .2 }).ToArray();
            foreach (var rows in new[] { unavailable, controlled }) { var s = CalibrationRecommendations.Summarize(rows, "location"); Require(s.Status == "unavailable" && s.BestMetric == null && s.Candidates.Length == 0 && double.IsNaN(s.BestPower), "Valid empty failed."); }
        });
        Check("loader_full_rows_finite_and_nonfinite_roundtrip", () => {
            var rows = SyntheticRows(); rows[0] = Unavailable(rows[0]); rows[1] = rows[1] with { Robustness = double.PositiveInfinity, Repeatability = double.NegativeInfinity };
            var loaded = LoadSyntheticRows(rows); Require(double.IsNaN(loaded[0].Fpr) && double.IsPositiveInfinity(loaded[1].Robustness) && double.IsNegativeInfinity(loaded[1].Repeatability), "Nonfinite class restoration failed.");
            rows[2] = rows[2] with { Coverage = -0.0, Robustness = Math.BitIncrement(.5) }; loaded = LoadSyntheticRows(rows);
            Require(Same(loaded[2].Coverage, -0.0) && Same(loaded[2].Robustness, Math.BitIncrement(.5)), "Finite binary64 or signed zero changed.");
            Reject(() => EqualJson(JsonSerializer.SerializeToElement(-0.0), JsonSerializer.SerializeToElement(0.0), "synthetic"), "signed-zero alteration");
        });
        Check("legitimate_unavailable_track_and_primary_scalars", () => {
            var rows = SyntheticRows(); var row = rows[0];
            row.TrackPowers![1] = double.NaN; row.TrackPowerLow![1] = double.NaN; row.TrackPowerHigh![1] = double.NaN; row.TrackScores![1] = double.NaN; row.TrackFailures![1] = 101;
            var loaded = LoadSyntheticRows(rows); Require(double.IsNaN(loaded[0].TrackPowers![1]) && double.IsFinite(loaded[0].Power), "Unavailable track restoration failed.");
            Require(!CalibrationRecommendations.Build(loaded, "variability")[0].Applicable, "Unavailable track became applicable.");
        });
        Check("wilson_endpoints_zero_one_and_failure_boundary", () => {
            foreach (int k in new[] { 0, 1, 500, 999, 1000 }) { var ci = ScientificMath.Wilson(k, 1000); VerifyInterval(k / 1000.0, ci.Low, ci.High, 0, "synthetic"); }
            var rows = SyntheticRows(); rows[0] = rows[0] with { NullFailures = 100, TrackFailures = new[] { 100, 100, 100 } }; _ = LoadSyntheticRows(rows);
            rows[0] = rows[0] with { NullFailures = 101 }; Reject(() => LoadSyntheticRows(rows), "insufficient null replications");
        });
        Check("duplicate_json_members", () => Reject(() => { using var d = ParseDocument(Encoding.UTF8.GetBytes("{\"outer\":{\"x\":1,\"x\":2}}")); }, "duplicate JSON keys"));
        Check("malformed_rows_tracks_settings_and_intervals", () => {
            var mutations = new Action<JsonArray>[] {
                a => a.RemoveAt(0), a => a[0]!["metric"] = "unknown", a => a[1]!["metric"] = "median",
                a => { var first = a[0]!.DeepClone(); a[0] = a[1]!.DeepClone(); a[1] = first; },
                a => a[0]!.AsObject().Remove("fpr_high"), a => a[0]!["track_power_low"] = null,
                a => a[0]!["tracks"]![1] = "location", a => a[0]!["tracks"]!.AsArray().RemoveAt(1),
                a => a[0]!["track_scores"]!.AsArray().RemoveAt(0), a => a[0]!["alpha"] = .1, a => a[0]!["repetitions"] = 999,
                a => a[0]!["fpr"] = -1, a => a[0]!["fpr_low"] = .5, a => a[0]!["fpr_high"] = 1.1,
                a => a[0]!["track_powers"]![1] = .1234, a => a[0]!["null_failures"] = -1,
                a => a[0]!["track_failures"]![0] = 1001, a => a[0]!["power"] = .3, a => a[0]!["fpr_inflated"] = true,
                a => a[0]!["applicable"] = false, a => a[0]!["track_power_low"]![1] = null,
                a => a[0]!["track_scores"]![1] = "0.5", a => a[0]!["track_mde_status"] = null,
                a => a[0]!["unknown"] = 0, a => a[0]!["track_failures"]![1] = 101
            };
            foreach (var mutate in mutations) { var node = JsonSerializer.SerializeToNode(SyntheticRows(), Json)!.AsArray(); mutate(node); Reject(() => LoadRows(JsonSerializer.SerializeToElement(node), JsonSerializer.SerializeToElement(FindNonfinite(SyntheticRows()), Json), "synthetic"), "malformed rows"); }
        });
        Check("nonfinite_missing_duplicate_wrong_and_infinite_selector_paths", () => {
            var rows = SyntheticRows(); rows[0] = Unavailable(rows[0]);
            var data = JsonSerializer.SerializeToElement(rows, Json); var metadata = JsonSerializer.SerializeToNode(FindNonfinite(rows), Json)!.AsArray();
            foreach (string path in new[] { "[99].fpr", "[0].track_powers[3]", "[0].bogus", "[1].fpr", "[0].tracks[0]" }) {
                var labels = metadata.DeepClone().AsArray(); labels.Add(new JsonObject { ["path"] = path, ["value"] = "NaN" }); Reject(() => LoadRows(data, JsonSerializer.SerializeToElement(labels), "synthetic"), "bad nonfinite path"); }
            var duplicate = metadata.DeepClone().AsArray(); duplicate.Add(duplicate[0]!.DeepClone()); Reject(() => LoadRows(data, JsonSerializer.SerializeToElement(duplicate), "synthetic"), "duplicate nonfinite path");
            var missing = metadata.DeepClone().AsArray(); missing.RemoveAt(0); Reject(() => LoadRows(data, JsonSerializer.SerializeToElement(missing), "synthetic"), "missing nonfinite path");
            var infinite = metadata.DeepClone().AsArray(); foreach (JsonNode? item in infinite) if (item!["path"]!.GetValue<string>() == "[0].fpr") item["value"] = "Infinity";
            Reject(() => LoadRows(data, JsonSerializer.SerializeToElement(infinite), "synthetic"), "Infinity selector value");
        });
        Check("global_scores_do_not_select_candidates", () => {
            var a = SyntheticRows(); var b = SyntheticRows(); for (int i = 0; i < b.Length; i++) b[i] = b[i] with { Score = 10000 - i, TrackScores = new[] { 10000.0 - i, -10000.0 + i, 0.0 } };
            foreach (string track in Tracks) Require(CalibrationRecommendations.Summarize(a, track).Candidates.SequenceEqual(CalibrationRecommendations.Summarize(b, track).Candidates), "Candidate set depends on projected scores.");
        });
        Check("full_synthetic_case_schema_hash_and_pairing", () => {
            JsonElement root = SyntheticCase(); _ = LoadCase(root, 0); Reject(() => LoadCase(root, 1), "wrong pair index");
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(root); byte[] changed = bytes.Concat(new byte[] { 32 }).ToArray(); Require(Hash(bytes) != Hash(changed), "Input mutation not detected.");
            foreach (Action<JsonObject> mutate in new Action<JsonObject>[] { n => n["schema"] = "unknown", n => n["status"] = "partial", n => n.Remove("calibration_right"), n => n["settings"]!["repetitions"] = 999, n => n["seeds"]!["derived_seed"] = 0 }) {
                JsonObject node = JsonNode.Parse(root.GetRawText())!.AsObject(); mutate(node); Reject(() => LoadCase(JsonSerializer.SerializeToElement(node), 0), "invalid envelope"); }
        });
        Check("output_schema_full_apis_and_nonfinite_metadata", () => {
            var rows = LoadCase(SyntheticCase(), 0); JsonElement result = JsonSerializer.SerializeToElement(Evaluate(rows, 0, new string('a', 64)), Json);
            Object(result, "result", "schema", "status", "index", "input_sha256", "method_id", "identity", "validation", "inputs", "evaluations");
            Require(result.GetProperty("evaluations").GetArrayLength() == 6 && result.GetProperty("status").GetString() == "completed", "Output evaluations missing.");
            var empty = SyntheticRows().Select(Unavailable).ToArray(); var summary = CalibrationRecommendations.Summarize(empty, "location");
            var labels = FindNonfinite(summary, "summary"); Require(labels.Any(x => x.Path == "summary.best_power" && x.Value == "NaN") && labels.All(x => x.Path != "summary.best_metric"), "Nullable string/nonfinite output distinction failed.");
        });
        return new { schema = Schema, status = "ok", mode = "self-test", synthetic_only = true, calibration_executed = false, generation_executed = false,
            test_count = tests.Count, tests, identity = Identity() };
    }
    private static CalibrationRow[] SyntheticRows() => Keys.Select(key => {
        var fpr = WilsonReference(1); var power = WilsonReference(800);
        return new CalibrationRow(key, .001, .8, .5, .9, .9, .95, true, double.NaN, false, "synthetic", Tracks.ToArray(), new[] { .8, .8, .8 }, new[] { .5, .5, .5 },
            new[] { double.NaN, double.NaN, double.NaN }, new[] { "synthetic", "synthetic", "synthetic" }, Repetitions, fpr.Low, fpr.High,
            new[] { power.Low, power.Low, power.Low }, new[] { power.High, power.High, power.High }, new[] { 0, 0, 0 },
            new[] { "target_not_reached_or_invalid_curve", "target_not_reached_or_invalid_curve", "target_not_reached_or_invalid_curve" }, Alpha, 0);
    }).ToArray();
    private static CalibrationRow SetPower(CalibrationRow row, double p, double low, double high) => row with { Power = p, TrackPowers = new[] { p, p, p }, TrackPowerLow = new[] { low, low, low }, TrackPowerHigh = new[] { high, high, high } };
    private static CalibrationRow Unavailable(CalibrationRow row) => row with { Applicable = false, Fpr = double.NaN, FprLow = double.NaN, FprHigh = double.NaN, Power = double.NaN, Score = double.NaN,
        TrackPowers = new[] { double.NaN, double.NaN, double.NaN }, TrackPowerLow = new[] { double.NaN, double.NaN, double.NaN }, TrackPowerHigh = new[] { double.NaN, double.NaN, double.NaN },
        TrackScores = new[] { double.NaN, double.NaN, double.NaN } };
    private static CalibrationRow[] LoadSyntheticRows(CalibrationRow[] rows) => LoadRows(JsonSerializer.SerializeToElement(rows, Json), JsonSerializer.SerializeToElement(FindNonfinite(rows), Json), "synthetic");
    private static JsonElement SyntheticCase()
    {
        CalibrationRow[] rows = SyntheticRows();
        object binding = new { sha256 = Hash(Encoding.UTF8.GetBytes("[]")), canonical_json = "[]", values = System.Array.Empty<object>() };
        object tau = new { kendall_tau = (double?)null, defined = false, undefined_reason = "synthetic constant scores", top_left_index = 0, top_right_index = 0, top_left = "median", top_right = "median", matched = true };
        object[] availability = Keys.Select(k => (object)new { metric = k, row_present = true, score_finite = true, applicable = true, projected_to_zero = false }).ToArray();
        return JsonSerializer.SerializeToElement(new { schema = InputSchema, index = 0, status = "completed", diagnostics_status = "retained", error = "",
            seeds = new { run_seed = 20260904UL, derived_seed = BenchmarkRandom.Derive(20260904UL, 5, 1, 0), split_seed = 1, calibration_left_seed = 2, calibration_right_seed = 3 },
            settings = ExpectedSettings(), metric_order = Keys,
            identity = new { harness_sha256 = new string('a', 64), core_sha256 = new string('b', 64), runtime = ".NET 8.0.31", os = "synthetic", architecture = "X64", engine_version = AnalysisEngine.EngineVersion,
                benchmark_protocol = BenchmarkProtocol.Version, processor_count = 1, environment_fingerprint = "synthetic", environment_sha256 = Hash(Encoding.UTF8.GetBytes("synthetic")), environment_probe_values = new double[12] },
            data = new { generated = binding, built = binding, left = binding, right = binding }, calibration_left = rows, calibration_right = rows,
            nonfinite_fields = new { calibration_left = FindNonfinite(rows), calibration_right = FindNonfinite(rows) }, scores_left = Enumerable.Repeat(.5, 12).ToArray(), scores_right = Enumerable.Repeat(.5, 12).ToArray(),
            availability_left = availability, availability_right = availability, legacy = tau, corrected = tau, resources = new { wall_seconds = 0, cpu_seconds = 0, peak_working_set_bytes = 0 } }, Json);
    }
}
