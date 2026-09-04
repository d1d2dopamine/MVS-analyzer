namespace MvsAnalyzer;

internal record Observation(string Entity, string Group, double Value, int Sequence, string Variable = "measurement", string Unit = "");
internal record EntityResult(string Entity, string Group, double[] Metrics, int Measurements);
internal record CalibrationRow(string Metric, double Fpr, double Power, double Score, double Robustness = 1, double Repeatability = 1, double Coverage = .95, bool Applicable = true, double Mde = double.NaN, bool FprInflated = false, string PowerCurve = "");
internal record ResultRow(string Metric, double FirstGroupMedian, double SecondGroupMedian, double MedianRange, double PValue, double Fpr, double Power, double Score, bool Candidate, string GroupSummary = "", double Robustness = 1, double Repeatability = 1, double Coverage = .95, bool Applicable = true, bool NearMiss = false, double Effect = double.NaN, double EffectLow = double.NaN, double EffectHigh = double.NaN, double EquivalenceP = double.NaN, double Mde = double.NaN, bool FprInflated = false, string Verdict = "insufficient", string EffectPair = "", double EffectPercent = double.NaN);
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
