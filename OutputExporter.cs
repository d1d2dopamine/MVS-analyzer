using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace MvsAnalyzer;

internal static class OutputExporter
{
    public const string FormulaVersion = "MVS-1.4.0";
    public const string FormulaSpecification = "score=100*sqrt(power*exp(-max(0,fpr-alpha/M)/(alpha/M)));M=metricRegistryCount;gate=fprWilsonUpper<=max(1.5*alpha/M,alpha/M+.02)&&powerWilsonLower>=.70;noScoreThreshold;maxCandidatesPerTrack=4;tracks=location,variability,heterogeneity;pooledEntityNullAndAlternative;commonRandomNumbers;location=constantAdditiveShift;within=residualSdMultiplier;between=centerDeviationMultiplier;contamination=symmetric;missingMinimum=processingMinimum;decision=allMetricsBonferroni;effect=cliffsDeltaFirstMinusSecond;selectedPair=descriptiveOnly;effectInterval=percentile400Pointwise95;equivalence=twoGroupsPercentile4000At1-2alpha/MApproximate;noBootstrapTailPValue;mde=firstUpwardCrossing80NoExtrapolationMin100DrawsPerPoint;effectGrid=1,1.02,1.05,1.10,1.20;diagnostics=pooledMedianCoverage,splitEntityRepeatability,pairedContaminationStability;diagnosticsExcludedFromScore";
    public static string FormulaHash => ScientificMath.Hash(FormulaSpecification);
    public static bool AnyAutomaticOutput(AppSettings s) => s.AutoExportResults || s.AutoExportCalibration || s.AutoExportQuality || s.AutoExportManifest || s.GenerateFigures;
    public static string PrepareRunFolder(AppSettings settings, string runId)
    {
        if (string.IsNullOrWhiteSpace(settings.FigureOutputFolder)) throw new InvalidOperationException("Select an output folder.");
        string prefix = Safe(settings.OutputPrefix); if (prefix.Length == 0) prefix = "MVS";
        // A random suffix prevents collisions across processes as well as sequential runs.
        string path = Path.Combine(settings.FigureOutputFolder, prefix + "_" + Safe(runId) + "_" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(path); return path;
    }
    public static List<OutputArtifact> Export(string folder, string runId, string project, string projectDescription, string projectMode,
        string dataset, string datasetHash, AnalysisData data, List<CalibrationRow> calibration, List<ResultRow> results, AppSettings settings,
        int calibrationRepetitions, IEnumerable<OutputArtifact> existing, string calibrationSource = "same_dataset",
        string? calibrationDatasetHash = null, bool forcedCalibrationReuse = false)
    {
        var artifacts = new List<OutputArtifact>();
        if (settings.AutoExportResults)
        {
            artifacts.Add(Write(folder, "results.csv", "Results", ResultsCsv(results)));
            artifacts.Add(Write(folder, "results.json", "Structured results", ScientificJson.Serialize(new { schemaVersion = 2, policy = DecisionPolicy.Id, rows = results,
                note = "Null numerical values are unavailable; effectIntervalStatus identifies descriptive selected-pair intervals. A null equivalence_p is intentional: bootstrap tail fractions are not p-values." })));
        }
        if (settings.AutoExportCalibration)
        {
            artifacts.Add(Write(folder, "calibration.csv", "Calibration", CalibrationCsv(calibration)));
            artifacts.Add(Write(folder, "calibration_tracks.csv", "Calibration tracks", TrackCsv(calibration)));
        }
        if (settings.AutoExportQuality) artifacts.Add(Write(folder, "data_quality.csv", "Data quality", QualityCsv(data, settings.AnonymousReports)));
        if (settings.AutoExportManifest)
        {
            var prior = existing.Concat(artifacts).GroupBy(a => a.FileName).Select(g => g.First()).Select(a => new { a.Kind, a.FileName, a.SizeBytes, sha256 = HashFile(a.FullPath) }).ToArray();
            string[] tracks = calibration.FirstOrDefault()?.Tracks ?? AnalysisEngine.DefaultTracks;
            var manifest = new {
                schemaVersion = 2, executionEnvironment = new { description = Benchmarking.BenchmarkEnvironment.Describe(), fingerprint = Benchmarking.BenchmarkEnvironment.Hash, replayScope = Benchmarking.BenchmarkEnvironment.Scope }, application = "MVS Analyzer", version = ReleaseInfo.Version, engineVersion = AnalysisEngine.EngineVersion, runId, created = DateTimeOffset.UtcNow,
                project = new { name = project, description = projectDescription, mode = projectMode }, dataset = settings.AnonymousReports ? "[hidden]" : dataset,
                inputData = new { file = settings.AnonymousReports ? "[hidden]" : dataset, sha256 = datasetHash },
                calibrationInput = new { sha256 = calibrationDatasetHash ?? datasetHash, forcedReuse = forcedCalibrationReuse },
                processing = ProcessingSnapshot.From(settings),
                figures = new { enabled = settings.GenerateFigures, mode = settings.FigureExportMode, format = settings.FigureFormat, templates = settings.FigureTemplates, generated = prior.Count(a => a.Kind == "Figure" || a.Kind == "График") },
                plugins = new { active = PluginManager.ListInstalled().Where(x => x.Enabled).Select(x => new { x.Id, x.Version, x.PackageHash }).ToArray(), importProfile = settings.ImportProfileId },
                calibration = new { seed = settings.CalibrationSeed, repetitions = calibrationRepetitions, effectMultiplier = settings.CalibrationEffect, scenario = settings.SimulationScenario, tracks,
                    outlierRate = settings.OutlierRate, missingRate = settings.MissingRate, alpha = settings.Alpha, calibrationSource,
                    settingsHash = SettingsContract.Fingerprint(settings), effectGrid = AnalysisEngine.EffectGrid, mdePowerTarget = AnalysisEngine.MdePowerTarget,
                    equivalenceMargin = settings.EquivalenceMargin, inflatedFpr = calibration.Where(c => c.FprInflated).Select(c => c.Metric).ToArray(),
                    powerDefinition = "Per-metric rejection under the all-metrics Bonferroni policy; conditional on the empirical pooled generator; failures count as non-rejections" },
                data = new { importSummary = data.ImportSummary, entities = data.TotalEntities, validRows = data.ValidRows, medianMeasurements = data.MedianMeasurements, groups = data.GroupNames, measurement = data.MeasurementName, unit = data.Unit },
                formula = new { version = FormulaVersion, specification = FormulaSpecification, hash = FormulaHash, weightsFrozen = true,
                    effectDefinition = "Cliffs delta: P(first>second)-P(first<second). For >2 groups the largest pair is descriptive, not a post-hoc significance claim.",
                    coverageDefinition = "Diagnostic coverage of a pooled entity-metric median; not coverage of Cliffs delta or variance components; excluded from score" },
                decision = new { policy = DecisionPolicy.Id, familySize = AnalysisEngine.MetricKeys.Length, alpha = settings.Alpha, sameDataSelection = calibrationSource == "same_dataset",
                    note = "Bonferroni covers the full fixed metric registry, not only chosen candidates. Approximate rank tests/intervals retain their small-sample limitations." },
                candidateRules = new { minPowerLowerWilson = AnalysisEngine.CandidateMinPower, maxFprUpperWilson = DecisionPolicy.FprLimit(settings.Alpha / AnalysisEngine.MetricKeys.Length), maximumCandidatesPerTrack = 4, scoreThreshold = "none" },
                candidateSet = results.Where(r => r.CandidateInAnyTrack).Select(r => r.Metric).ToArray(),
                candidateSetsByTrack = tracks.ToDictionary(t => t, t => results.Where(r => r.CandidateIn(t)).Select(r => r.Metric).ToArray()),
                warnings = data.Warnings.Concat(forcedCalibrationReuse ? new[] { "Calibration deliberately reused on different input bytes; scientific compatibility has NOT been established." } : Array.Empty<string>()).ToArray(),
                files = prior
            };
            artifacts.Add(Write(folder, "run_manifest.json", "Run manifest", ScientificJson.Serialize(manifest)));
        }
        return artifacts;
    }
    public static string HashFile(string path) { using var stream = File.OpenRead(path); return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant(); }
    public static OutputArtifact FromFile(string kind, string path) { var info = new FileInfo(path); return new OutputArtifact(kind, info.Name, info.FullName, info.Length); }
    internal static string ResultsCsv(IEnumerable<ResultRow> rows)
    {
        var s = new StringBuilder("metric,group_summary,range,global_p,effect_cliffs_delta,effect_low,effect_high,equivalence_p,verdict,mde,calibrated_fpr,fpr_inflated,calibrated_power,robustness,repeatability,coverage,mvs_score,applicable,candidate,near_miss,tracks,track_powers,track_scores,track_mdes,candidate_tracks,adjusted_p,effect_pair,effect_interval_status,equivalence_low,equivalence_high\n");
        foreach (ResultRow r in rows) s.Append(string.Join(',', C(r.Metric), C(r.GroupSummary), N(r.MedianRange), N(r.PValue), N(r.Effect), N(r.EffectLow), N(r.EffectHigh), N(r.EquivalenceP), C(r.Verdict), N(r.Mde), N(r.Fpr), r.FprInflated.ToString(), N(r.Power), N(r.Robustness), N(r.Repeatability), N(r.Coverage), N(r.Score), r.Applicable.ToString(), r.Candidate.ToString(), r.NearMiss.ToString(), C(Join(r.Tracks)), C(Join(r.TrackPowers)), C(Join(r.TrackScores)), C(Join(r.TrackMdes)), C(r.CandidateTracks), N(r.AdjustedP), C(r.EffectPair), C(r.EffectIntervalStatus), N(r.EquivalenceLow), N(r.EquivalenceHigh))).Append('\n');
        return s.ToString();
    }
    internal static string CalibrationCsv(IEnumerable<CalibrationRow> rows)
    {
        var s = new StringBuilder("metric,calibrated_fpr,fpr_inflated,calibrated_power,mde,power_curve,robustness,repeatability,coverage,mvs_score,applicable,tracks,track_powers,track_scores,track_mdes,track_curves,repetitions,fpr_low,fpr_high,null_failures,mde_status\n");
        foreach (CalibrationRow r in rows) s.Append(string.Join(',', C(r.Metric), N(r.Fpr), r.FprInflated.ToString(), N(r.Power), N(r.Mde), C(r.PowerCurve), N(r.Robustness), N(r.Repeatability), N(r.Coverage), N(r.Score), r.Applicable.ToString(), C(Join(r.Tracks)), C(Join(r.TrackPowers)), C(Join(r.TrackScores)), C(Join(r.TrackMdes)), C(Join(r.TrackCurves)), r.Repetitions.ToString(CultureInfo.InvariantCulture), N(r.FprLow), N(r.FprHigh), r.NullFailures.ToString(CultureInfo.InvariantCulture), C(Join(r.TrackMdeStatus)))).Append('\n');
        return s.ToString();
    }
    internal static string TrackCsv(IEnumerable<CalibrationRow> rows)
    {
        var s = new StringBuilder("metric,track,power,power_low,power_high,power_mcse,score,mde,mde_status,failures,repetitions\n");
        foreach (CalibrationRow r in rows)
            for (int i = 0; i < (r.Tracks?.Length ?? 0); i++) s.Append(string.Join(',', C(r.Metric), C(r.Tracks![i]), N(r.TrackPowers![i]), N(r.TrackPowerLow![i]), N(r.TrackPowerHigh![i]), N(ScientificMath.Mcse(r.TrackPowers[i], r.Repetitions)), N(r.TrackScores![i]), N(r.TrackMdes![i]), C(r.TrackMdeStatus![i]), r.TrackFailures![i].ToString(CultureInfo.InvariantCulture), r.Repetitions.ToString(CultureInfo.InvariantCulture))).Append('\n');
        return s.ToString();
    }
    private static string QualityCsv(AnalysisData data, bool anonymize)
    {
        var s = new StringBuilder("entity,group,valid_measurements," + string.Join(',', AnalysisEngine.MetricKeys) + "\n");
        foreach (EntityResult e in data.Entities) s.Append(C(anonymize ? "P_" + ScientificMath.Hash(AnalysisEngine.Key(e.Group, e.Entity))[..10] : e.Entity)).Append(',').Append(C(e.Group)).Append(',').Append(e.Measurements).Append(',').Append(string.Join(',', e.Metrics.Select(N))).Append('\n');
        return s.ToString();
    }
    private static OutputArtifact Write(string folder, string name, string kind, string text) { string path = Path.Combine(folder, name); ScientificJson.AtomicText(path, text); return FromFile(kind, path); }
    private static string N(double value) => double.IsFinite(value) ? value.ToString("R", CultureInfo.InvariantCulture) : "";
    private static string Join(double[]? values) => values == null ? "" : string.Join('|', values.Select(N));
    private static string Join(string[]? values) => values == null ? "" : string.Join('|', values);
    // Spreadsheet formula injection is escaped for text fields, never for numerical columns.
    private static string C(string value) { if (value.Length > 0 && "=+-@\t\r".Contains(value[0])) value = "'" + value; return '"' + value.Replace("\"", "\"\"") + '"'; }
    private static string Safe(string value) => string.Concat(value.Where(c => char.IsLetterOrDigit(c) || c is '-' or '_')).Trim('_', '-');
}
