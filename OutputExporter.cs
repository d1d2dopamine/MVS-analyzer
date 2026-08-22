using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace MvsAnalyzer;

internal static class OutputExporter
{
    public const string FormulaVersion = "MVS-1.2.0";
    public const string FormulaSpecification = "score=100*power^.30*falseAlarm^.25*robustness^.20*repeatability^.15*coverage^.10;rawValueScenario;globalRankTest;repeatability=splitHalfGroupMedianAgreement;coverage=bootstrapIntervalCoverage;candidate=fpr<=.075&&power>=.70&&score>=60;maxCandidates=4;nearMissReported;effect=cliffsDelta;interval=percentileBootstrap400;equivalence=tostOnBootstrapDelta;verdict=difference|equivalent|insufficient|not_applicable;mde=interpolatedFromEffectGrid@power.80;effectGrid=1.00,1.02,1.05,1.10,1.20;inflatedFpr=nullGridPointAboveAlpha";
    public static string FormulaHash => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(FormulaSpecification))).ToLowerInvariant();
    public static bool AnyAutomaticOutput(AppSettings s) => s.AutoExportResults || s.AutoExportCalibration || s.AutoExportQuality || s.AutoExportManifest || s.GenerateFigures;

    public static string PrepareRunFolder(AppSettings settings, string runId)
    {
        if (string.IsNullOrWhiteSpace(settings.FigureOutputFolder)) throw new InvalidOperationException("Output folder was not selected.");
        string prefix = Safe(settings.OutputPrefix); if (prefix.Length == 0) prefix = "MVS";
        string basePath = Path.Combine(settings.FigureOutputFolder, $"{prefix}_{runId}"), folder = basePath; int suffix = 2;
        while (Directory.Exists(folder)) folder = basePath + "_" + suffix++;
        Directory.CreateDirectory(folder); return folder;
    }

    public static List<OutputArtifact> Export(string folder, string runId, string project, string projectDescription, string projectMode, string dataset, string datasetHash, AnalysisData data, List<CalibrationRow> calibration, List<ResultRow> results, AppSettings settings, int calibrationRepetitions, IEnumerable<OutputArtifact> existing, string calibrationSource = "same_dataset")
    {
        var artifacts = new List<OutputArtifact>();
        if (settings.AutoExportResults) artifacts.Add(Write(folder, "results.csv", "Results", ResultsCsv(results)));
        if (settings.AutoExportCalibration) artifacts.Add(Write(folder, "calibration.csv", "Calibration", CalibrationCsv(calibration)));
        if (settings.AutoExportQuality) artifacts.Add(Write(folder, "data_quality.csv", "Data quality", QualityCsv(data, settings.AnonymousReports)));
        if (settings.AutoExportManifest)
        {
            var prior = existing.Concat(artifacts).Select(a => new { a.Kind, a.FileName, a.SizeBytes, sha256 = Hash(a.FullPath) }).ToArray();
            var manifest = new
            {
                application = "MVS Analyzer", version = "1.3.2", engineVersion = AnalysisEngine.EngineVersion, runId, created = DateTimeOffset.Now,
                project = new { name = project, description = projectDescription, mode = projectMode }, dataset = settings.AnonymousReports ? "[hidden]" : dataset,
                // Without a hash of the INPUT file a run cannot be tied to the data it claims to describe.
                inputData = new { file = settings.AnonymousReports ? "[hidden]" : dataset, sha256 = datasetHash },
                // Without this block a run with zero figures is indistinguishable from a run that never asked for any.
                figures = new { enabled = settings.GenerateFigures, mode = settings.FigureExportMode, format = settings.FigureFormat, templates = settings.FigureTemplates, generated = prior.Count(a => a.Kind == "Figure" || a.Kind == "График") },
                // Plugins can change how data enters and how the report reads, so a run records them.
                plugins = new { active = PluginManager.ListInstalled().Where(x => x.Enabled).Select(x => new { x.Id, x.Name, x.Version, x.Type, x.PackageHash }).ToArray(), importProfile = string.IsNullOrWhiteSpace(settings.ImportProfileId) ? "built-in" : settings.ImportProfileId, figureTemplates = PluginAssets.Current.FigureTemplates.Count, reportTemplates = PluginAssets.Current.ReportTemplates.Count, validationRules = PluginAssets.Current.ValidationRules.Count, terms = PluginAssets.Current.Terms.Count, rejectedFiles = PluginAssets.Current.Errors.Select(x => x.Plugin + "/" + x.File).ToArray() },
                processing = new { minValue = data.MinValueApplied, maxValue = data.MaxValueApplied, minMeasurements = data.MinMeasurementsApplied },
                // calibrationSource records whether the metrics were chosen on the same rows that produced the answer.
                calibration = new { seed = settings.CalibrationSeed, repetitions = calibrationRepetitions, effectMultiplier = settings.CalibrationEffect, scenario = settings.SimulationScenario, outlierRate = settings.OutlierRate, missingRate = settings.MissingRate, alpha = settings.Alpha, calibrationSource, effectGrid = AnalysisEngine.EffectGrid, mdePowerTarget = AnalysisEngine.MdePowerTarget, equivalenceMargin = settings.EquivalenceMargin, powerCurves = calibration.Where(x => !string.IsNullOrEmpty(x.PowerCurve)).ToDictionary(x => x.Metric, x => x.PowerCurve), inflatedFpr = calibration.Where(x => x.FprInflated).Select(x => x.Metric).ToArray() },
                data = new { entities = data.TotalEntities, validRows = data.ValidRows, medianMeasurements = data.MedianMeasurements, groups = data.GroupNames, measurement = data.MeasurementName, unit = data.Unit },
                formula = new { version = FormulaVersion, specification = FormulaSpecification, hash = FormulaHash, weightsFrozen = true, effectDefinition = "Cliffs delta between the two most separated groups, with a 95% percentile bootstrap interval over entities (400 resamples)", verdictDefinition = "equivalent = whole interval inside the equivalence margin; difference = p < alpha and the interval excludes zero; insufficient = the interval covers both; not_applicable = the metric could not be computed", mdeDefinition = "smallest simulated effect reaching power 0.80, interpolated on the effect grid", repeatabilityDefinition = "measured: repeated split-half resampling of entities (50 splits); agreement of the group median of the metric between the two halves", coverageDefinition = "measured: empirical coverage of the 95% percentile bootstrap interval for the entity-level median of the metric (200 outer trials x 200 inner resamples)" },
                candidateRules = new { maxFpr = AnalysisEngine.CandidateMaxFpr, minPower = AnalysisEngine.CandidateMinPower, minScore = AnalysisEngine.CandidateMinScore, maximumCandidates = 4 },
                // A run now states what it could and could not conclude, instead of leaving silence to be read as "no difference".
                verdicts = new { difference = results.Where(r => r.Verdict == "difference").Select(r => r.Metric).ToArray(), equivalent = results.Where(r => r.Verdict == "equivalent").Select(r => r.Metric).ToArray(), insufficient = results.Where(r => r.Verdict == "insufficient").Select(r => r.Metric).ToArray(), notApplicable = results.Where(r => r.Verdict == "not_applicable").Select(r => r.Metric).ToArray() },
                candidateSet = results.Where(r => r.Candidate).Select(r => r.Metric).ToArray(), files = prior
            };
            artifacts.Add(Write(folder, "run_manifest.json", "Run manifest", JsonSerializer.Serialize(manifest, new JsonSerializerOptions { WriteIndented = true })));
        }
        return artifacts;
    }

    public static string HashFile(string path) => Hash(path);
    public static OutputArtifact FromFile(string kind, string path) { var info = new FileInfo(path); return new OutputArtifact(kind, info.Name, info.FullName, info.Exists ? info.Length : 0); }
    internal static string ResultsCsv(IEnumerable<ResultRow> rows) { var s = new StringBuilder("metric,group_summary,range,global_p,effect_cliffs_delta,effect_low,effect_high,equivalence_p,verdict,mde,calibrated_fpr,fpr_inflated,calibrated_power,robustness,repeatability,coverage,mvs_score,applicable,candidate,near_miss\r\n"); foreach (var r in rows) s.AppendLine(string.Join(',', Csv(r.Metric), Csv(r.GroupSummary), N(r.MedianRange), N(r.PValue), N(r.Effect), N(r.EffectLow), N(r.EffectHigh), N(r.EquivalenceP), Csv(r.Verdict), N(r.Mde), N(r.Fpr), r.FprInflated.ToString(), N(r.Power), N(r.Robustness), N(r.Repeatability), N(r.Coverage), N(r.Score), r.Applicable.ToString(), r.Candidate.ToString(), r.NearMiss.ToString())); return s.ToString(); }
    internal static string CalibrationCsv(IEnumerable<CalibrationRow> rows) { var s = new StringBuilder("metric,calibrated_fpr,fpr_inflated,calibrated_power,mde,power_curve,robustness,repeatability,coverage,mvs_score,applicable\r\n"); foreach (var r in rows) s.AppendLine(string.Join(',', Csv(r.Metric), N(r.Fpr), r.FprInflated.ToString(), N(r.Power), N(r.Mde), Csv(r.PowerCurve), N(r.Robustness), N(r.Repeatability), N(r.Coverage), N(r.Score), r.Applicable.ToString())); return s.ToString(); }
    private static string QualityCsv(AnalysisData data, bool anonymize)
    {
        var s = new StringBuilder("entity,group,valid_measurements,median,standard_deviation,coefficient_of_variation,mad,iqr,normalized_mad,normalized_iqr,mean,rms,range\r\n");
        foreach (var p in data.Entities) { string id = anonymize ? "P_" + HashText(p.Group + "\u001f" + p.Entity)[..10] : p.Entity; s.Append(Csv(id)).Append(',').Append(Csv(p.Group)).Append(',').Append(p.Measurements).Append(',').AppendLine(string.Join(',', p.Metrics.Select(N))); }
        return s.ToString();
    }
    private static OutputArtifact Write(string folder, string name, string kind, string text) { string path = Path.Combine(folder, name); File.WriteAllText(path, text, new UTF8Encoding(true)); return FromFile(kind, path); }
    // "R" gives the shortest string that still round-trips, so 0.0477 instead of 0.047699999999999999.
    private static string N(double value) => value.ToString("R", CultureInfo.InvariantCulture);
    private static string Csv(string value) => '"' + value.Replace("\"", "\"\"") + '"';
    private static string Safe(string value) => string.Concat(value.Where(c => char.IsLetterOrDigit(c) || c is '-' or '_')).Trim('_', '-');
    private static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private static string HashText(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
