using System.Globalization;
using System.Text;
using System.Text.Json;
using MvsAnalyzer;

// Synthetic persistence fixtures only. The numerical rows below are NOT calibration evidence.
internal static class SerializationChecks
{
    public static IEnumerable<(string Name, Action Run)> All => new (string, Action)[]
    {
        ("JSON formatting and embedded string newlines are portable", JsonLineEndings),
        ("Legacy LF and CRLF states migrate without repeating calibration", LegacyStates),
        ("Legacy profile and settings hashes migrate together", LegacyProfiles),
        ("Tampering is rejected before normalization", RejectTampering),
        ("A re-signed state cannot hide mismatched settings", RejectMismatchedSettings)
    };
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void Reject(Action action)
    {
        try { action(); } catch (InvalidDataException) { return; }
        throw new Exception("Invalid state was accepted");
    }
    private static string Temp() => Path.Combine(Path.GetTempPath(), "mvs-json-" + Guid.NewGuid().ToString("N"));
    private static string LegacyJson<T>(T value, string newline) =>
        ScientificJson.NormalizeLineEndings(JsonSerializer.Serialize(value, ScientificJson.Options)).Replace("\n", newline, StringComparison.Ordinal);
    private static ImportProfile Profile() => new("portability-fixture", "Тест\r\nprofile", "serialization-test", ',', false,
        new Dictionary<string, string[]> { ["entity"] = new[] { "entity" }, ["group"] = new[] { "group" }, ["value"] = new[] { "value" }, ["sequence"] = new[] { "sequence" } });
    private static CalibrationState Fixture(AppSettings settings, string? dataHash = null)
    {
        string[] tracks = AnalysisEngine.DefaultTracks;
        var rows = AnalysisEngine.MetricKeys.Select(metric => new CalibrationRow(metric, .005, .8, 70,
            Tracks: tracks, TrackPowers: Enumerable.Repeat(.8, tracks.Length).ToArray(),
            TrackScores: Enumerable.Repeat(70d, tracks.Length).ToArray(), TrackMdes: Enumerable.Repeat(double.NaN, tracks.Length).ToArray(),
            TrackCurves: Enumerable.Repeat("synthetic-schema-fixture", tracks.Length).ToArray(), Repetitions: 150,
            FprLow: .001, FprHigh: .01, TrackPowerLow: Enumerable.Repeat(.7, tracks.Length).ToArray(),
            TrackPowerHigh: Enumerable.Repeat(.9, tracks.Length).ToArray(), TrackFailures: new int[tracks.Length],
            TrackMdeStatus: Enumerable.Repeat("synthetic-schema-fixture", tracks.Length).ToArray(), Alpha: settings.Alpha)).ToList();
        return new("data.csv", dataHash ?? ScientificMath.Hash("synthetic-schema-fixture"), "synthetic-schema-fixture-not-for-inference", 150,
            settings.CalibrationEffect, settings.CalibrationSeed, settings.SimulationScenario, settings.OutlierRate, settings.MissingRate,
            settings.Alpha, settings.EquivalenceMargin, settings.SplitCalibration, tracks, ReleaseInfo.Version, ReleaseInfo.EngineVersion,
            OutputExporter.FormulaVersion, OutputExporter.FormulaHash, "synthetic", "2026-09-05T00:00:00Z", rows,
            ProcessingSnapshot.From(settings), SettingsHash: SettingsContract.Fingerprint(settings));
    }
    private static CalibrationState LegacyState(CalibrationState state, ImportProfile? profile, string newline)
    {
        if (profile != null) state = state with { Processing = state.Processing! with { ImportProfileHash = ScientificMath.Hash(LegacyJson(profile, newline)) } };
        string settingsJson = SettingsContract.FingerprintJson(state).Replace("\n", newline, StringComparison.Ordinal);
        state = state with { SettingsHash = ScientificMath.Hash(settingsJson), PayloadHash = "" };
        return state with { PayloadHash = ScientificMath.Hash(LegacyJson(state, newline)) };
    }
    private static void JsonLineEndings()
    {
        string json = ScientificJson.Serialize(new { A = 1, Text = "a\r\nb" });
        Check(json == "{\n  \"A\": 1,\n  \"Text\": \"a\\r\\nb\"\n}", "JSON formatting or embedded string contents changed");
        Check(ScientificJson.MatchesPortableOrLegacyHash(json, ScientificMath.Hash(json.Replace("\n", "\r\n"))), "Legacy Windows hash rejected");
        Check(!ScientificJson.MatchesPortableOrLegacyHash(json.Replace("a", "z"), ScientificMath.Hash(json)), "Changed contents accepted");
    }
    private static void RoundTrip(AppSettings settings, ImportProfile? profile)
    {
        string folder = Temp(); Directory.CreateDirectory(folder);
        try
        {
            foreach (string newline in new[] { "\n", "\r\n" })
            {
                CalibrationState original = Fixture(settings), legacy = LegacyState(original, profile, newline);
                string raw = LegacyJson(legacy, newline), path = Path.Combine(folder, "legacy.json");
                File.WriteAllText(path, raw, new UTF8Encoding(false));
                CalibrationState restored = CalibrationPersistence.Read(path);
                Check(File.ReadAllText(path) == raw, "Read modified the original file");
                var applied = new AppSettings(); CalibrationPersistence.Apply(restored, applied);
                Check(restored.SettingsHash == SettingsContract.Fingerprint(settings), "Settings did not become portable");
                Check(SettingsContract.Fingerprint(applied) == restored.SettingsHash, "Restored settings differ");
                Check(restored.Processing == ProcessingSnapshot.From(settings), "Profile hash did not become portable");
                Check(restored.Rows.Count == 12 && double.IsNaN(restored.Rows[0].Mde), "Rows/null MDE changed");
                string portable = Path.Combine(folder, "portable.json"); CalibrationPersistence.Write(portable, restored);
                string first = File.ReadAllText(portable); Check(!first.Contains('\r'), "New file uses platform line endings");
                CalibrationPersistence.Write(portable, CalibrationPersistence.Read(portable));
                Check(File.ReadAllText(portable) == first, "Write/read/write changed signed bytes");
            }
        }
        finally { Directory.Delete(folder, true); }
    }
    private static void LegacyStates() => RoundTrip(new AppSettings(), null);
    private static void LegacyProfiles()
    {
        ImportProfile profile = Profile(); PluginAssets.Current.ImportProfiles.Add(profile);
        try { RoundTrip(new AppSettings { ImportProfileId = profile.Id }, profile); }
        finally { PluginAssets.Current.ImportProfiles.Remove(profile); }
    }
    private static void RejectTampering()
    {
        var state = LegacyState(Fixture(new AppSettings()), null, "\r\n");
        Reject(() => CalibrationPersistence.Validate(state with { Dataset = "changed.csv" }));
        Reject(() => CalibrationPersistence.Validate(state with { PayloadHash = new string('0', 64) }));
    }
    private static void RejectMismatchedSettings()
    {
        var state = Fixture(new AppSettings()) with { SettingsHash = new string('0', 64), PayloadHash = "" };
        state = state with { PayloadHash = ScientificMath.Hash(ScientificJson.Serialize(state)) };
        Reject(() => CalibrationPersistence.Validate(state));
    }
    public static void ExportFixtures(string folder)
    {
        Directory.CreateDirectory(folder);
        foreach (bool custom in new[] { false, true })
        {
            ImportProfile? profile = custom ? Profile() : null;
            if (profile != null) PluginAssets.Current.ImportProfiles.Add(profile);
            try
            {
                string root = Path.Combine(folder, custom ? "custom" : "builtin"); Directory.CreateDirectory(root);
                var csv = new StringBuilder("entity,group,value,sequence\n");
                foreach (string group in new[] { "A", "B" }) for (int entity = 1; entity <= 4; entity++) for (int sequence = 1; sequence <= 6; sequence++)
                    csv.Append(group).Append(entity).Append(',').Append(group).Append(',').Append((100 + entity + sequence).ToString(CultureInfo.InvariantCulture)).Append(',').Append(sequence).Append('\n');
                string input = Path.Combine(root, "data.csv"); File.WriteAllText(input, csv.ToString(), new UTF8Encoding(false));
                var settings = new AppSettings { ImportProfileId = profile?.Id ?? "" };
                var state = Fixture(settings, OutputExporter.HashFile(input));
                CalibrationPersistence.Write(Path.Combine(root, "portable.json"), state);
                foreach (var item in new[] { ("legacy-lf.json", "\n"), ("legacy-crlf.json", "\r\n") })
                    File.WriteAllText(Path.Combine(root, item.Item1), LegacyJson(LegacyState(state, profile, item.Item2), item.Item2), new UTF8Encoding(false));
                RemoteJobFile job = RemoteJob.Describe("standard", input, state.DatasetHash, "serialization fixture", "Not scientific calibration", settings, 150);
                if (profile != null)
                {
                    string oldProfile = LegacyJson(profile, "\r\n");
                    File.WriteAllText(Path.Combine(root, "import_profile.json"), oldProfile, new UTF8Encoding(false));
                    job = job with { Processing = job.Processing! with { ImportProfileHash = ScientificMath.Hash(oldProfile) } };
                }
                File.WriteAllText(Path.Combine(root, "job.json"), LegacyJson(job, "\r\n"), new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(root, "expected-settings.sha256"), state.SettingsHash, new UTF8Encoding(false));
            }
            finally { if (profile != null) PluginAssets.Current.ImportProfiles.Remove(profile); }
        }
        Console.WriteLine("Exported synthetic serialization fixtures, not scientific calibration results.");
    }
    public static void VerifyFixtures(string folder)
    {
        Check(Directory.Exists(Path.Combine(folder, "builtin")) && Directory.Exists(Path.Combine(folder, "custom")), "Missing peer-host fixtures");
        foreach (string root in new[] { Path.Combine(folder, "builtin"), Path.Combine(folder, "custom") })
        {
            RemoteJobFile job = RemoteJob.Read(Path.Combine(root, "job.json"));
            var settings = new AppSettings(); RemoteJob.Apply(job, settings);
            string expected = File.ReadAllText(Path.Combine(root, "expected-settings.sha256"));
            Check(SettingsContract.Fingerprint(settings) == expected, "Peer settings fingerprint differs");
            foreach (string name in new[] { "portable.json", "legacy-lf.json", "legacy-crlf.json" })
            {
                CalibrationState state = CalibrationPersistence.Read(Path.Combine(root, name));
                Check(state.SettingsHash == expected, "Peer calibration fingerprint differs");
                Check(state.DatasetHash == OutputExporter.HashFile(Path.Combine(root, "data.csv")), "Peer input differs");
                var restored = new AppSettings(); CalibrationPersistence.Apply(state, restored);
                Check(SettingsContract.Fingerprint(restored) == expected, "Peer restored settings differ");
            }
        }
        Console.WriteLine("Verified peer-host calibration and profile fingerprints.");
    }
}
