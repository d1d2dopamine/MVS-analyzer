using System.Globalization;
using System.Text.Json.Nodes;
using MvsAnalyzer.Benchmarking;
namespace MvsAnalyzer;
internal sealed record BackupRunResult(string Folder, AnalysisData? Data = null, List<CalibrationRow>? Calibration = null,
    List<ResultRow>? Results = null, CalibrationState? State = null, int ExitCode = 0);

// Whitelisted in-process operations only. No execution of commands or plugins from an archive.
internal static class BackupRunner
{
    internal static BackupRunResult Run(BackupDocument document, string parent, IProgress<ProgressInfo> progress, CancellationToken token, bool russian = false)
        => RunWithOutputObserver(document, parent, progress, token, null, null, russian);

    internal static BackupRunResult RunWithOutputObserver(BackupDocument document, string parent, IProgress<ProgressInfo> progress,
        CancellationToken token, Action<string>? outputStarted, Action<string, bool>? observeWrite, bool russian = false)
    {
        BackupSession.Validate(document);
        DateTime resumedFrom = document.SavedUtc; int retainedUnits = document.Units.Count;
        using var restore = BackupSession.Restore(document);
        BackupRequest r = document.Request;
        string folder = Path.Combine(Path.GetFullPath(parent), "MVS_restored_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture) + "_" + Guid.NewGuid().ToString("N")[..6]);
        Directory.CreateDirectory(folder);
        AnalysisData? full = r.Context?.FullData ?? r.Data;
        string dataset = r.Context?.DatasetName ?? "Restored data", hash = r.Context?.DatasetHash ?? "";
        if (hash.Length != 64) hash = ScientificMath.Hash(ScientificJson.Serialize(full?.Observations ?? r.Observations ?? new()));
        void Provenance(string target) => ScientificJson.Write(Path.Combine(target, "backup_resume.json"), new {
            backupId = document.Id, requestHash = document.RequestHash, resumedFromUtc = resumedFrom, retainedUnits,
            environments = document.Environments, originalProcessing = r.Context?.Processing,
            note = "Completed units retained; unfinished work after the last durable checkpoint repeated. Stored observations are already imported, not parsed again. Mixed-platform floating-point replay is not guaranteed bit-identical. Benchmark duration covers the final execution segment only." });
        bool outputObserved = false;
        void Observe(string path, bool completed)
        {
            if (!outputObserved)
            {
                outputStarted?.Invoke(folder);
                outputObserved = true;
            }
            observeWrite?.Invoke(path, completed);
        }
        void Write(string name, Action write)
        {
            string path = Path.Combine(folder, name);
            Observe(path, false); write(); Observe(path, true);
        }
        object? modelReport = null; int exitCode = 0;
        switch (r.Kind)
        {
            case "benchmark":
                var report = BenchmarkReport.RunAndWriteWithOutputObserver(r.Benchmark ?? throw new InvalidDataException("Missing benchmark profile."), r.Seed, folder, "", russian, progress, token, outputStarted, observeWrite);
                // The initial checksum describes the pre-resume export. It is no longer a
                // completed artifact once provenance/manifest publication begins, even if
                // its old bytes survive a later failure. Do not delete those old bytes.
                observeWrite?.Invoke(Path.Combine(report.Folder, "SHA256SUMS.txt"), false);
                string provenance = Path.Combine(report.Folder, "backup_resume.json");
                observeWrite?.Invoke(provenance, false);
                Provenance(report.Folder);
                observeWrite?.Invoke(provenance, true);
                RefreshBenchmarkChecksums(report, provenance, observeWrite);
                return new(report.Folder, ExitCode: report.Outcome.Overall == "no-go" ? 2 : 0);
            case "calibrate":
                var calibration = AnalysisEngine.Calibrate(Data(r), r.Repetitions, r.Effect, r.Seed, progress, token, r.Scenario, r.Outliers, r.Missing, r.Alpha, r.Tracks);
                CalibrationState state = State(r, calibration, dataset, hash, document);
                Write(CalibrationPersistence.FileName, () => CalibrationPersistence.Write(Path.Combine(folder, CalibrationPersistence.FileName), state));
                state = CalibrationPersistence.Read(Path.Combine(folder, CalibrationPersistence.FileName));
                Write("calibration.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "calibration.csv"), OutputExporter.CalibrationCsv(calibration)));
                Write("calibration_tracks.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "calibration_tracks.csv"), OutputExporter.TrackCsv(calibration)));
                Write("backup_resume.json", () => Provenance(folder)); return new(folder, full, calibration, State: state);
            case "analyze":
                List<CalibrationRow> rows = r.Calibration ?? throw new InvalidDataException("Missing calibration.");
                var results = AnalysisEngine.Results(Data(r), rows, progress, token, r.Alpha, r.Margin, r.Seed);
                CalibrationState analysisState = State(r, rows, dataset, hash, document);
                var settings = Settings(r); settings.FigureOutputFolder = folder; settings.FigureFolderConfirmed = true; settings.GenerateFigures = false;
                settings.AutoExportResults = settings.AutoExportCalibration = settings.AutoExportQuality = settings.AutoExportManifest = true;
                Write(CalibrationPersistence.FileName, () => CalibrationPersistence.Write(Path.Combine(folder, CalibrationPersistence.FileName), analysisState));
                analysisState = CalibrationPersistence.Read(Path.Combine(folder, CalibrationPersistence.FileName)); Write("backup_resume.json", () => Provenance(folder));
                var files = new List<OutputArtifact> { OutputExporter.FromFile("Calibration state", Path.Combine(folder, CalibrationPersistence.FileName)), OutputExporter.FromFile("Resume provenance", Path.Combine(folder, "backup_resume.json")) };
                OutputExporter.Export(folder, "restored_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture), r.Context?.Project ?? "Restored project", r.Context?.Description ?? "", "Exploratory; resumed from checkpoint",
                    dataset, hash, Data(r), rows, results, settings, analysisState.Repetitions, files, analysisState.CalibrationSource, observeWrite: Observe);
                return new(folder, full, rows, results, analysisState);
            case "variance":
                var variance = VarianceAnalysis.Run(Data(r), r.Repetitions, r.ReferenceReplications, r.Effect, r.SecondEffect, r.Seed, r.Alpha, progress, token);
                Write("variance_report.json", () => ScientificJson.Write(Path.Combine(folder, "variance_report.json"), variance));
                Write("variance_components.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "variance_components.csv"), VarianceAnalysis.Csv(variance)));
                Write("variance_tests.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "variance_tests.csv"), ScientificTables.Csv(variance.Tracks)));
                modelReport = variance; exitCode = variance.Groups.Any(g => g.Status == "not_converged_or_degenerate") || variance.Tracks.Any(t => t.Status is "bootstrap_or_fit_failure" or "excess_simulation_failures") ? 2 : 0; break;
            case "estimation":
                var estimation = EstimationStudy.Run(r.Estimation ?? throw new InvalidDataException("Missing estimation options."), progress, token);
                Write("estimation_report.json", () => ScientificJson.Write(Path.Combine(folder, "estimation_report.json"), estimation));
                Write("estimation_performance.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "estimation_performance.csv"), ScientificTables.Csv(estimation.Performance)));
                Write("estimation_draws.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "estimation_draws.csv"), ScientificTables.Csv(estimation.Draws)));
                modelReport = estimation; exitCode = estimation.Performance.Any(p => p.Status == "excess_failures") ? 2 : 0; break;
            case "melsm":
                var melsm = MelsmAnalysis.Run(r.Observations ?? throw new InvalidDataException("Missing observations."), r.Melsm ?? throw new InvalidDataException("Missing model options."), progress, token);
                melsm = melsm with { RandomEffects = melsm.RandomEffects.Select(x => x with { Entity = "P_" + ScientificMath.Hash(x.Entity)[..12] }).ToArray() };
                Write("melsm_report.json", () => ScientificJson.Write(Path.Combine(folder, "melsm_report.json"), melsm));
                Write("melsm_parameters.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "melsm_parameters.csv"), ScientificTables.Csv(melsm.Parameters)));
                Write("melsm_random_effects.csv", () => ScientificJson.AtomicText(Path.Combine(folder, "melsm_random_effects.csv"), ScientificTables.Csv(melsm.RandomEffects)));
                modelReport = melsm; exitCode = melsm.Status == "converged_experimental" ? 0 : 2; break;
            default: throw new InvalidDataException("Unsupported backup operation.");
        }
        Write("backup_resume.json", () => Provenance(folder));
        Write("run_manifest.json", () => ScientificTables.WriteManifest(folder, "resumed-" + r.Kind, modelReport, hash));
        return new(folder, ExitCode: exitCode);
    }
    private static void RefreshBenchmarkChecksums(BenchmarkReportResult report, string provenance, Action<string, bool>? observeWrite)
    {
        string folder = report.Folder;
        string manifest = Path.Combine(folder, "benchmark_manifest.json");
        JsonNode document = JsonNode.Parse(File.ReadAllText(manifest)) ?? throw new InvalidDataException("Missing benchmark manifest.");
        if (document["files"] is not JsonArray files) throw new InvalidDataException("Invalid benchmark manifest files.");
        files.Add("backup_resume.json");
        observeWrite?.Invoke(manifest, false);
        ScientificJson.AtomicText(manifest, document.ToJsonString(ScientificJson.Options));
        observeWrite?.Invoke(manifest, true);
        string[] names = report.Files.Concat(report.Figures).Append(provenance)
            .Where(p => Path.GetFileName(p) != "SHA256SUMS.txt").Distinct(StringComparer.Ordinal)
            .OrderBy(p => p, StringComparer.Ordinal).ToArray();
        string checksums = Path.Combine(folder, "SHA256SUMS.txt");
        observeWrite?.Invoke(checksums, false);
        ScientificJson.AtomicText(checksums, string.Join("\n", names.Select(p => OutputExporter.HashFile(p) + "  " + Path.GetRelativePath(folder, p).Replace('\\', '/'))) + "\n");
        observeWrite?.Invoke(checksums, true);
    }
    private static AnalysisData Data(BackupRequest r) => r.Data ?? throw new InvalidDataException("Missing analysis data.");
    internal static AppSettings Settings(BackupRequest r)
    {
        AnalysisData d = r.Context?.FullData ?? Data(r); CalibrationState? old = r.Context?.Calibration;
        // Inputs have already been imported. Do not require/install an external parsing plugin.
        return new AppSettings { MinValue = d.MinValueApplied, MaxValue = d.MaxValueApplied, MinMeasurements = d.MinMeasurementsApplied,
            ImportProfileId = "", CalibrationSeed = r.Seed, CalibrationEffect = old?.Effect ?? r.Effect,
            SimulationScenario = old?.Scenario ?? r.Scenario, OutlierRate = old?.OutlierRate ?? r.Outliers, MissingRate = old?.MissingRate ?? r.Missing,
            Alpha = r.Alpha, EquivalenceMargin = r.Kind == "analyze" ? r.Margin : r.Context?.Margin ?? .147,
            SplitCalibration = r.Context?.Split ?? old?.SplitCalibration ?? false };
    }
    private static CalibrationState State(BackupRequest r, List<CalibrationRow> rows, string dataset, string hash, BackupDocument document)
    {
        AppSettings s = Settings(r); string[] tracks = rows.First().Tracks ?? AnalysisEngine.NormalizeTracks(s.SimulationScenario, r.Tracks);
        string environment = document.Environments.Distinct().Count() == 1 ? document.Environments[0] : ScientificMath.Hash("mixed-resume:" + string.Join(";", document.Environments));
        return new(dataset, hash, s.SplitCalibration ? "split_half" : "same_dataset", rows.First().Repetitions, s.CalibrationEffect, s.CalibrationSeed,
            s.SimulationScenario, s.OutlierRate, s.MissingRate, s.Alpha, s.EquivalenceMargin, s.SplitCalibration, tracks, ReleaseInfo.Version,
            ReleaseInfo.EngineVersion, OutputExporter.FormulaVersion, OutputExporter.FormulaHash, environment, DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture), rows,
            ProcessingSnapshot.From(s), SettingsHash: SettingsContract.Fingerprint(s));
    }
}
