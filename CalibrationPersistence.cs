namespace MvsAnalyzer;

internal sealed record CalibrationState(string Dataset, string DatasetHash, string CalibrationSource, int Repetitions,
    double Effect, int Seed, string Scenario, double OutlierRate, double MissingRate, double Alpha, double EquivalenceMargin,
    bool SplitCalibration, string[] Tracks, string AppVersion, string EngineVersion, string FormulaVersion, string FormulaHash,
    string EnvironmentHash, string CreatedUtc, List<CalibrationRow> Rows, ProcessingSnapshot? Processing = null,
    int SchemaVersion = ReleaseInfo.StateSchema, string SettingsHash = "", string PayloadHash = "");

internal static class CalibrationPersistence
{
    public const string FileName = "calibration_state.json";
    public static void Write(string path, CalibrationState state)
    {
        state = state with { PayloadHash = "" };
        state = state with { PayloadHash = ScientificMath.Hash(ScientificJson.Serialize(state)) };
        Validate(state);
        ScientificJson.Write(path, state);
    }
    public static CalibrationState Read(string path)
    {
        CalibrationState state = ScientificJson.Read<CalibrationState>(path); Validate(state); return state;
    }
    public static void Validate(CalibrationState state)
    {
        if (state.SchemaVersion != ReleaseInfo.StateSchema || state.Processing == null || string.IsNullOrWhiteSpace(state.SettingsHash))
            throw new InvalidDataException("Legacy or incomplete calibration state. Preserve the old result for history, then recalibrate with this release.");
        if (state.EngineVersion != AnalysisEngine.EngineVersion || state.FormulaVersion != OutputExporter.FormulaVersion || state.FormulaHash != OutputExporter.FormulaHash)
            throw new InvalidDataException("Calibration engine/formula is incompatible with this release. Recalibrate; --force cannot bypass method compatibility.");
        if (state.Repetitions < 100 || state.Rows == null || state.Tracks == null || state.Tracks.Length == 0 || state.DatasetHash?.Length != 64)
            throw new InvalidDataException("Incomplete calibration data.");
        if (state.Tracks.Distinct().Count() != state.Tracks.Length || state.Tracks.Any(t => !SimulationScenarios.TryCanonical(t, out string canonical) || canonical != t))
            throw new InvalidDataException("Invalid calibration track registry.");
        if (state.Rows.Count != AnalysisEngine.MetricKeys.Length || state.Rows.Select(r => r.Metric).Distinct().Count() != state.Rows.Count || AnalysisEngine.MetricKeys.Any(m => !state.Rows.Any(r => r.Metric == m)))
            throw new InvalidDataException("Invalid calibration metric registry.");
        if (state.Tracks[0] != SimulationScenarios.Canonicalize(state.Scenario)) throw new InvalidDataException("Primary calibration track does not match its scenario.");
        int count = state.Tracks.Length;
        foreach (CalibrationRow row in state.Rows)
        {
            if (row.Tracks == null || !row.Tracks.SequenceEqual(state.Tracks) || row.TrackPowers?.Length != count || row.TrackScores?.Length != count || row.TrackMdes?.Length != count || row.TrackCurves?.Length != count || row.TrackPowerLow?.Length != count || row.TrackPowerHigh?.Length != count || row.TrackFailures?.Length != count || row.TrackMdeStatus?.Length != count)
                throw new InvalidDataException("Missing or mismatched per-track values for " + row.Metric);
            if (row.Repetitions != state.Repetitions || row.Alpha != state.Alpha || row.NullFailures < 0 || row.NullFailures > state.Repetitions || row.TrackFailures!.Any(n => n < 0 || n > state.Repetitions))
                throw new InvalidDataException("Invalid simulation counts for " + row.Metric);
            foreach (double score in row.TrackScores!)
                if (double.IsInfinity(score) || (double.IsFinite(score) && (score < 0 || score > 100))) throw new InvalidDataException("Invalid calibration score.");
            foreach (double rate in row.TrackPowers!.Concat(row.TrackPowerLow!).Concat(row.TrackPowerHigh!).Concat(new[] { row.Fpr, row.FprLow, row.FprHigh }))
                if (double.IsInfinity(rate) || (double.IsFinite(rate) && (rate < 0 || rate > 1))) throw new InvalidDataException("Invalid probability in calibration.");
        }
        string digest = ScientificMath.Hash(ScientificJson.Serialize(state with { PayloadHash = "" }));
        if (digest != state.PayloadHash) throw new InvalidDataException("Calibration payload checksum mismatch. The file may have been changed or truncated.");
    }
    public static void Apply(CalibrationState state, AppSettings settings)
    {
        Validate(state);
        state.Processing!.Apply(settings);
        settings.CalibrationSeed = state.Seed; settings.CalibrationEffect = state.Effect; settings.SimulationScenario = state.Scenario;
        settings.OutlierRate = state.OutlierRate; settings.MissingRate = state.MissingRate; settings.Alpha = state.Alpha;
        settings.EquivalenceMargin = state.EquivalenceMargin; settings.SplitCalibration = state.SplitCalibration;
        SettingsContract.Validate(settings);
        if (SettingsContract.Fingerprint(settings) != state.SettingsHash) throw new InvalidDataException("Calibration settings do not match their saved fingerprint.");
    }
}
