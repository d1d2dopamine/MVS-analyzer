namespace MvsAnalyzer;

internal record Observation(string Entity, string Group, double Value, int Sequence, string Variable = "measurement", string Unit = "");
internal record EntityResult(string Entity, string Group, double[] Metrics, int Measurements);
/// <summary>
/// One metric after calibration. Fpr, Robustness, Repeatability and Coverage do not depend on
/// the injected effect, so they hold for every track. Power, Score, Mde and PowerCurve are
/// the values for the primary track, kept as plain properties so older readers still work,
/// while TrackPowers and friends carry the full per-track picture added in 1.4.0.
/// </summary>
internal record CalibrationRow(string Metric, double Fpr, double Power, double Score, double Robustness = 1, double Repeatability = 1, double Coverage = .95, bool Applicable = true, double Mde = double.NaN, bool FprInflated = false, string PowerCurve = "", string[]? Tracks = null, double[]? TrackPowers = null, double[]? TrackScores = null, double[]? TrackMdes = null, string[]? TrackCurves = null)
{
    /// <summary>Index of a track name, or -1. Names are canonical SimulationScenarios values.</summary>
    public int TrackIndex(string track)
    {
        if (Tracks == null) return -1;
        SimulationScenarios.TryCanonical(track, out string canonical);
        for (int i = 0; i < Tracks.Length; i++) if (Tracks[i] == canonical) return i;
        return -1;
    }

    private static double At(double[]? values, int index, double fallback) => values != null && index >= 0 && index < values.Length ? values[index] : fallback;

    public double PowerIn(string track) => At(TrackPowers, TrackIndex(track), Power);
    public double ScoreIn(string track) => At(TrackScores, TrackIndex(track), Score);
    public double MdeIn(string track) => At(TrackMdes, TrackIndex(track), Mde);
    public string CurveIn(string track) { int i = TrackIndex(track); return TrackCurves != null && i >= 0 && i < TrackCurves.Length ? TrackCurves[i] : PowerCurve; }

    /// <summary>The shipped gate, asked separately for each track instead of once for all of them.</summary>
    public bool PassesGateIn(string track)
    {
        double power = PowerIn(track), score = ScoreIn(track);
        return Applicable && double.IsFinite(Fpr) && double.IsFinite(power) && double.IsFinite(score)
            && Fpr <= AnalysisEngine.CandidateMaxFpr && power >= AnalysisEngine.CandidateMinPower && score >= AnalysisEngine.CandidateMinScore;
    }
}
/// <summary>
/// One metric on the results page. Power, Score, Mde and Candidate carry the primary track so
/// that anything written before 1.4.0 keeps its meaning. TrackCandidates is the honest answer
/// for a two-track run: a metric can be a candidate for the spread question and not for the
/// centre question, and saying so is the whole point of splitting the tracks.
/// </summary>
internal record ResultRow(string Metric, double FirstGroupMedian, double SecondGroupMedian, double MedianRange, double PValue, double Fpr, double Power, double Score, bool Candidate, string GroupSummary = "", double Robustness = 1, double Repeatability = 1, double Coverage = .95, bool Applicable = true, bool NearMiss = false, double Effect = double.NaN, double EffectLow = double.NaN, double EffectHigh = double.NaN, double EquivalenceP = double.NaN, double Mde = double.NaN, bool FprInflated = false, string Verdict = "insufficient", string EffectPair = "", double EffectPercent = double.NaN, string[]? Tracks = null, double[]? TrackPowers = null, double[]? TrackScores = null, double[]? TrackMdes = null, bool[]? TrackCandidates = null)
{
    public int TrackIndex(string track)
    {
        if (Tracks == null) return -1;
        SimulationScenarios.TryCanonical(track, out string canonical);
        for (int i = 0; i < Tracks.Length; i++) if (Tracks[i] == canonical) return i;
        return -1;
    }

    public double PowerIn(string track) { int i = TrackIndex(track); return TrackPowers != null && i >= 0 && i < TrackPowers.Length ? TrackPowers[i] : Power; }
    public double ScoreIn(string track) { int i = TrackIndex(track); return TrackScores != null && i >= 0 && i < TrackScores.Length ? TrackScores[i] : Score; }
    public double MdeIn(string track) { int i = TrackIndex(track); return TrackMdes != null && i >= 0 && i < TrackMdes.Length ? TrackMdes[i] : Mde; }
    public bool CandidateIn(string track) { int i = TrackIndex(track); return TrackCandidates != null && i >= 0 && i < TrackCandidates.Length ? TrackCandidates[i] : Candidate; }

    /// <summary>True when the metric answers at least one of the questions that were asked.</summary>
    public bool CandidateInAnyTrack => TrackCandidates == null ? Candidate : TrackCandidates.Any(x => x);

    /// <summary>Best score across the tracks, used only for ordering the page.</summary>
    public double BestTrackScore
    {
        get
        {
            if (TrackScores == null) return Score;
            double best = double.NegativeInfinity;
            foreach (double value in TrackScores) if (double.IsFinite(value) && value > best) best = value;
            return double.IsFinite(best) ? best : Score;
        }
    }

    /// <summary>Comma separated canonical names of the tracks this metric is a candidate for.</summary>
    public string CandidateTracks => Tracks == null || TrackCandidates == null
        ? (Candidate ? SimulationScenarios.Default : "")
        : string.Join(",", Tracks.Where((_, i) => i < TrackCandidates.Length && TrackCandidates[i]));
}
internal record ProgressInfo(double Fraction, string Action, string Details);
internal record RunRecord(DateTime Time, string Project, string Dataset, int Entities, string Profile, string CandidateSet);
internal sealed record FigureTemplateChoice(string Id, string Name) { public override string ToString() => Name; }
internal sealed record OutputArtifact(string Kind, string FileName, string FullPath, long SizeBytes);
internal sealed record AuditFinding(string Severity, string Code, string Message, string MessageRu);
internal sealed record RunAudit(string Folder, string RunId, string Project, string Dataset, string DatasetHash, string EngineVersion, string FormulaHash, int Seed, double Effect, string Scenario, int Repetitions, string CandidateSet, List<AuditFinding> Findings);
internal sealed record AuditReport(List<RunAudit> Runs, List<AuditFinding> Findings, string Verdict, int JournalEntries);

internal sealed class AnalysisData
{
    public required List<Observation> Observations { get; init; }
    public required List<EntityResult> Entities { get; init; }
    public int TotalEntities => Entities.Count;
    public required string[] GroupNames { get; init; }
    public required int[] GroupCounts { get; init; }
    public required int ValidRows { get; init; }
    public required double MedianMeasurements { get; init; }
    public string EntityColumn { get; init; } = "entity";
    public string ValueColumn { get; init; } = "value";
    public string GroupColumn { get; init; } = "group";
    public string SequenceColumn { get; init; } = "sequence";
    public string MeasurementName { get; init; } = "measurement";
    public string Unit { get; init; } = "";
    public string DistributionProxy { get; init; } = "estimated from observed skew";
    public int MinValueApplied { get; init; }
    public int MaxValueApplied { get; init; }
    public int MinMeasurementsApplied { get; init; }
}

internal sealed class AppSettings
{
    public string Language { get; set; } = "en";
    public string Theme { get; set; } = "system";
    public string Density { get; set; } = "adaptive";
    public int MinValue { get; set; } = -1000000;
    public int MaxValue { get; set; } = 1000000;
    public int MinMeasurements { get; set; } = 6;
    public bool AnonymousReports { get; set; } = true;
    public string InterfaceMode { get; set; } = "guided";
    public int CalibrationSeed { get; set; } = 20260719;
    public double CalibrationEffect { get; set; } = 1.15;
    public int CustomRepetitions { get; set; } = 5000;
    public string SimulationScenario { get; set; } = SimulationScenarios.Default;
    public double OutlierRate { get; set; } = .02;
    public double MissingRate { get; set; } = 0;
    public double Alpha { get; set; } = .05;
    public bool GenerateFigures { get; set; }
    public string FigureExportMode { get; set; } = "separate";
    public string FigureFormat { get; set; } = "png";
    public string FigureOutputFolder { get; set; } = "";
    public bool FigureFolderConfirmed { get; set; }
    public string FigureTemplates { get; set; } = "value_distribution,mvs_score,fpr_power,group_comparison";
    public bool AutoExportResults { get; set; } = true;
    public bool AutoExportCalibration { get; set; } = true;
    public bool AutoExportQuality { get; set; } = true;
    public bool AutoExportManifest { get; set; } = true;
    public string OutputPrefix { get; set; } = "MVS";
    public string ImportProfileId { get; set; } = "";
    public bool SplitCalibration { get; set; }
    public double EquivalenceMargin { get; set; } = .147;
    private static string Folder => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer");
    private static string FileName => Path.Combine(Folder, "settings.txt");

    public static AppSettings Load()
    {
        var value = new AppSettings(); if (!File.Exists(FileName)) return value;
        foreach (string line in File.ReadAllLines(FileName))
        {
            string[] pair = line.Split('=', 2); if (pair.Length != 2) continue;
            switch (pair[0])
            {
                case "language": value.Language = pair[1]; break; case "theme": value.Theme = pair[1]; break; case "density": value.Density = pair[1]; break;
                case "minValue": if (int.TryParse(pair[1], out int min)) value.MinValue = min; break;
                case "maxValue": if (int.TryParse(pair[1], out int max)) value.MaxValue = max; break;
                case "minMeasurements": if (int.TryParse(pair[1], out int measurements)) value.MinMeasurements = measurements; break;
                case "anonymous": value.AnonymousReports = pair[1] == "true"; break; case "interfaceMode": value.InterfaceMode = pair[1]; break;
                case "calibrationSeed": if (int.TryParse(pair[1], out int seed)) value.CalibrationSeed = seed; break;
                case "calibrationEffect": if (double.TryParse(pair[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double effect)) value.CalibrationEffect = effect; break;
                case "customRepetitions": if (int.TryParse(pair[1], out int repetitions)) value.CustomRepetitions = repetitions; break;
                case "simulationScenario": value.SimulationScenario = SimulationScenarios.TryCanonical(pair[1], out string scenarioName) ? scenarioName : SimulationScenarios.Default; break;
                case "outlierRate": if (double.TryParse(pair[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double outlier)) value.OutlierRate = outlier; break;
                case "missingRate": if (double.TryParse(pair[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double missing)) value.MissingRate = missing; break;
                case "alpha": if (double.TryParse(pair[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double alpha)) value.Alpha = alpha; break; case "generateFigures": value.GenerateFigures = pair[1] == "true"; break;
                case "figureExportMode": value.FigureExportMode = pair[1]; break; case "figureFormat": value.FigureFormat = pair[1]; break;
                case "figureOutputFolder": value.FigureOutputFolder = pair[1]; break; case "figureFolderConfirmed": value.FigureFolderConfirmed = pair[1] == "true"; break;
                case "figureTemplates": value.FigureTemplates = pair[1]; break; case "autoExportResults": value.AutoExportResults = pair[1] == "true"; break;
                case "autoExportCalibration": value.AutoExportCalibration = pair[1] == "true"; break; case "autoExportQuality": value.AutoExportQuality = pair[1] == "true"; break;
                case "autoExportManifest": value.AutoExportManifest = pair[1] == "true"; break; case "outputPrefix": value.OutputPrefix = pair[1]; break; case "importProfile": value.ImportProfileId = pair[1]; break; case "splitCalibration": value.SplitCalibration = pair[1] == "true"; break; case "equivalenceMargin": if (double.TryParse(pair[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double margin)) value.EquivalenceMargin = margin; break;
            }
        }
        if (value.MinValue >= value.MaxValue) { value.MinValue = -1000000; value.MaxValue = 1000000; }
        value.MinMeasurements = Math.Clamp(value.MinMeasurements, 2, 100000);
        value.OutlierRate = Math.Clamp(value.OutlierRate, 0, .25); value.MissingRate = Math.Clamp(value.MissingRate, 0, .50); value.Alpha = Math.Clamp(value.Alpha, .001, .20); value.EquivalenceMargin = Math.Clamp(value.EquivalenceMargin, .02, .60);
        return value;
    }
    public void Save()
    {
        Directory.CreateDirectory(Folder);
        File.WriteAllLines(FileName, new[] { $"language={Language}", $"theme={Theme}", $"density={Density}", $"minValue={MinValue}", $"maxValue={MaxValue}", $"minMeasurements={MinMeasurements}", $"anonymous={AnonymousReports.ToString().ToLowerInvariant()}", $"interfaceMode={InterfaceMode}", $"calibrationSeed={CalibrationSeed}", $"calibrationEffect={CalibrationEffect.ToString(System.Globalization.CultureInfo.InvariantCulture)}", $"customRepetitions={CustomRepetitions}", $"simulationScenario={SimulationScenario}", $"outlierRate={OutlierRate.ToString(System.Globalization.CultureInfo.InvariantCulture)}", $"missingRate={MissingRate.ToString(System.Globalization.CultureInfo.InvariantCulture)}", $"alpha={Alpha.ToString(System.Globalization.CultureInfo.InvariantCulture)}", $"generateFigures={GenerateFigures.ToString().ToLowerInvariant()}", $"figureExportMode={FigureExportMode}", $"figureFormat={FigureFormat}", $"figureOutputFolder={FigureOutputFolder}", $"figureFolderConfirmed={FigureFolderConfirmed.ToString().ToLowerInvariant()}", $"figureTemplates={FigureTemplates}", $"autoExportResults={AutoExportResults.ToString().ToLowerInvariant()}", $"autoExportCalibration={AutoExportCalibration.ToString().ToLowerInvariant()}", $"autoExportQuality={AutoExportQuality.ToString().ToLowerInvariant()}", $"autoExportManifest={AutoExportManifest.ToString().ToLowerInvariant()}", $"outputPrefix={OutputPrefix}", $"importProfile={ImportProfileId}", $"splitCalibration={SplitCalibration.ToString().ToLowerInvariant()}", $"equivalenceMargin={EquivalenceMargin.ToString(System.Globalization.CultureInfo.InvariantCulture)}" });
    }
}
