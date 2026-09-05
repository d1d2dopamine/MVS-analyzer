using System.Globalization;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.Cli;

internal static class CliCancellation
{
    internal static readonly CancellationTokenSource Source = new();
    internal static CancellationToken Token => Source.Token;
}
internal sealed class CliProgress : IProgress<ProgressInfo>
{
    private int last = -1;
    public void Report(ProgressInfo info)
    {
        int pct = (int)(100 * info.Fraction);
        if (pct == 0 && info.Action.StartsWith("MELSM", StringComparison.Ordinal)) { Console.WriteLine(info.Action); return; }
        if (pct == last || (pct != 100 && pct % 5 != 0)) return;
        last = pct; Console.WriteLine($"{pct,3}%  {info.Action} — {info.Details}");
    }
}
internal static class HeadlessRun
{
    public const string StateFileName = CalibrationPersistence.FileName;
    private static readonly string[] Common = { "--in", "--out", "--job", "--seed", "--effect", "--scenario", "--alpha", "--outliers", "--missing", "--margin", "--min-measurements", "--min-value", "--max-value", "--split", "--local-settings", "--allow-group-scoped-ids" };
    public static int Calibrate(CliArguments args)
    {
        args.Validate(Common.Concat(new[] { "--repetitions", "--overwrite" }));
        AppSettings settings = Settings(args, out RemoteJobFile? job); string input = Input(args, job), output = args.Require("--out");
        int repetitions = args.Int("--repetitions", job?.Repetitions ?? settings.CustomRepetitions);
        if (repetitions < 100) throw new ArgumentException("Use at least 100 repetitions. Small budgets are smoke checks, not scientific validation.");
        string statePath = Path.Combine(output, StateFileName);
        if (File.Exists(statePath) && !args.Flag("--overwrite")) throw new InvalidDataException("A calibration already exists here. Choose another output folder or pass --overwrite.");
        Console.WriteLine("MVS calibration"); ShowVersions(); Console.WriteLine("Environment: " + BenchmarkEnvironment.Describe());
        List<Observation> observations = CsvImporter.Read(input, settings.MinValue, settings.MaxValue, Profile(settings));
        CheckIndependentIds(observations, args.Flag("--allow-group-scoped-ids"));
        AnalysisData data = AnalysisEngine.Build(observations, settings.MinValue, settings.MaxValue, settings.MinMeasurements);
        data.ImportSummary = CsvImporter.LastImportSummary;
        Console.WriteLine(CsvImporter.LastImportSummary);
        string hash = OutputExporter.HashFile(input);
        if (job != null && job.DatasetHash != hash) throw new InvalidDataException("The input does not match the job's dataset checksum.");
        string[] tracks = AnalysisEngine.NormalizeTracks(settings.SimulationScenario, AnalysisEngine.DefaultTracks);
        Console.WriteLine("Data: " + Path.GetFileName(input) + " | " + data.TotalEntities + " entities | " + data.ValidRows + " rows | " + CsvImporter.LastEncodingName);
        Console.WriteLine("Tracks: " + string.Join(", ", tracks)); Console.WriteLine("Seed: " + settings.CalibrationSeed + " | repetitions: " + repetitions);
        Console.WriteLine("Input SHA256: " + hash);
        foreach (string warning in data.Warnings) Console.WriteLine("Warning: " + warning);
        AnalysisData source = settings.SplitCalibration ? AnalysisEngine.SplitEntities(data, settings.CalibrationSeed).Calibration : data;
        string calibrationSource = settings.SplitCalibration ? "split_half" : "same_dataset";
        List<CalibrationRow> calibration = AnalysisEngine.Calibrate(source, repetitions, settings.CalibrationEffect, settings.CalibrationSeed,
            new CliProgress(), CliCancellation.Token, settings.SimulationScenario, settings.OutlierRate, settings.MissingRate, settings.Alpha, tracks);
        var state = new CalibrationState(Path.GetFileName(input), hash, calibrationSource, repetitions, settings.CalibrationEffect,
            settings.CalibrationSeed, settings.SimulationScenario, settings.OutlierRate, settings.MissingRate, settings.Alpha, settings.EquivalenceMargin,
            settings.SplitCalibration, tracks, ReleaseInfo.Version, AnalysisEngine.EngineVersion, OutputExporter.FormulaVersion, OutputExporter.FormulaHash,
            BenchmarkEnvironment.Hash, DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture), calibration, ProcessingSnapshot.From(settings),
            SettingsHash: SettingsContract.Fingerprint(settings));
        Directory.CreateDirectory(output);
        ScientificJson.AtomicText(Path.Combine(output, "calibration.csv"), OutputExporter.CalibrationCsv(calibration));
        ScientificJson.AtomicText(Path.Combine(output, "calibration_tracks.csv"), OutputExporter.TrackCsv(calibration));
        CalibrationPersistence.Write(statePath, state);
        Console.WriteLine("Calibration saved: " + statePath);
        return 0;
    }
    public static int Analyze(CliArguments args)
    {
        args.Validate(Common.Concat(new[] { "--calibration", "--project", "--description", "--force" }));
        AppSettings settings = Settings(args, out RemoteJobFile? job); string input = Input(args, job), output = args.Require("--out");
        string statePath = args.Require("--calibration"); if (Directory.Exists(statePath)) statePath = Path.Combine(statePath, StateFileName);
        CalibrationState state = CalibrationPersistence.Read(statePath);
        if (state.EnvironmentHash != BenchmarkEnvironment.Hash) Console.Error.WriteLine("Warning: calibration came from a different arithmetic environment. Exact cross-platform replay is not guaranteed; both environments remain recorded.");
        // No silently ignored statistical overrides. Supply them when calibrating, not afterwards.
        foreach (string flag in new[] { "--seed", "--effect", "--scenario", "--alpha", "--outliers", "--missing", "--margin", "--min-measurements", "--min-value", "--max-value", "--split" })
            if (args.Has(flag)) throw new ArgumentException(flag + " is fixed by the calibration. Recalibrate to change it.");
        CalibrationPersistence.Apply(state, settings);
        List<Observation> observations = CsvImporter.Read(input, settings.MinValue, settings.MaxValue, Profile(settings));
        CheckIndependentIds(observations, args.Flag("--allow-group-scoped-ids"));
        Console.WriteLine(CsvImporter.LastImportSummary);
        string hash = OutputExporter.HashFile(input); bool mismatch = !hash.Equals(state.DatasetHash, StringComparison.OrdinalIgnoreCase);
        if (mismatch && !args.Flag("--force")) throw new InvalidDataException("Calibration belongs to different input bytes. Recalibrate, or explicitly use --force for an exploratory comparison.");
        if (mismatch) Console.Error.WriteLine("Warning: forced calibration reuse. Both input hashes will be recorded; compatibility is not established.");
        AnalysisData data = AnalysisEngine.Build(observations, settings.MinValue, settings.MaxValue, settings.MinMeasurements);
        data.ImportSummary = CsvImporter.LastImportSummary;
        AnalysisData analysed = settings.SplitCalibration ? AnalysisEngine.SplitEntities(data, settings.CalibrationSeed).Analysis : data;
        analysed.ImportSummary = data.ImportSummary;
        List<ResultRow> results = AnalysisEngine.Results(analysed, state.Rows, new CliProgress(), CliCancellation.Token, settings.Alpha, settings.EquivalenceMargin, state.Seed);
        settings.GenerateFigures = false; settings.FigureOutputFolder = output; settings.FigureFolderConfirmed = true;
        settings.AutoExportResults = settings.AutoExportCalibration = settings.AutoExportQuality = settings.AutoExportManifest = true;
        string runId = DateTime.UtcNow.ToString("yyyy-MM-dd_HHmmss", CultureInfo.InvariantCulture);
        string folder = OutputExporter.PrepareRunFolder(settings, runId);
        string project = args.Value("--project") ?? job?.Project ?? "Headless analysis";
        string description = args.Value("--description") ?? job?.Description ?? "";
        string copy = Path.Combine(folder, StateFileName); File.Copy(statePath, copy, true);
        var artifacts = new List<OutputArtifact> { OutputExporter.FromFile("Calibration state", copy) };
        try { artifacts.AddRange(PluginAssets.WriteReports(folder, runId, project, Path.GetFileName(input), analysed, results, settings).Select(x => OutputExporter.FromFile("Report", x))); }
        catch (Exception error) { Console.Error.WriteLine("Plugin report was skipped: " + error.Message); }
        artifacts.AddRange(OutputExporter.Export(folder, runId, project, description, "Exploratory; full-registry multiplicity correction",
            Path.GetFileName(input), hash, analysed, state.Rows, results, settings, state.Repetitions, artifacts,
            state.CalibrationSource, state.DatasetHash, mismatch));
        try { RunAuditor.AppendJournal(runId, folder, hash, settings, state.Repetitions, string.Join(",", results.Where(r => r.CandidateInAnyTrack).Select(r => r.Metric))); }
        catch (Exception error) { Console.Error.WriteLine("Warning: journal write failed: " + error.Message); }
        Console.WriteLine("Analysis saved: " + folder);
        foreach (ResultRow row in results) Console.WriteLine(row.Metric.PadRight(25) + row.Verdict.PadRight(16) + " adjusted p=" + Num(row.AdjustedP));
        return 0;
    }
    internal static void CheckIndependentIds(List<Observation> rows, bool explicitlyScoped)
    {
        bool overlap = rows.GroupBy(o => o.Entity, StringComparer.OrdinalIgnoreCase).Any(g => g.Select(o => o.Group).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1);
        if (overlap && !explicitlyScoped) throw new InvalidDataException("Entity IDs repeat across groups. Use melsm for the same subjects in different conditions. If IDs merely restart for INDEPENDENT groups, explicitly pass --allow-group-scoped-ids.");
    }
    private static AppSettings Settings(CliArguments args, out RemoteJobFile? job)
    {
        // CLI runs do not secretly inherit a desktop configuration unless explicitly requested.
        AppSettings settings = args.Flag("--local-settings") ? AppSettings.Load() : new AppSettings(); job = null;
        if (args.Value("--job") is string path) { if (Directory.Exists(path)) path = Path.Combine(path, RemoteJob.JobFileName); job = RemoteJob.Read(path); RemoteJob.Apply(job, settings); }
        settings.CalibrationSeed = args.Int("--seed", settings.CalibrationSeed); settings.CalibrationEffect = args.Number("--effect", settings.CalibrationEffect);
        settings.Alpha = args.Number("--alpha", settings.Alpha); settings.OutlierRate = args.Number("--outliers", settings.OutlierRate); settings.MissingRate = args.Number("--missing", settings.MissingRate);
        settings.EquivalenceMargin = args.Number("--margin", settings.EquivalenceMargin); settings.MinMeasurements = args.Int("--min-measurements", settings.MinMeasurements);
        settings.MinValue = args.Int("--min-value", settings.MinValue); settings.MaxValue = args.Int("--max-value", settings.MaxValue);
        if (args.Flag("--split")) settings.SplitCalibration = true;
        if (args.Value("--scenario") is string scenario) settings.SimulationScenario = SimulationScenarios.Canonicalize(scenario);
        SettingsContract.Validate(settings); return settings;
    }
    private static string Input(CliArguments args, RemoteJobFile? job)
    {
        string? input = args.Value("--in");
        if (input == null && job != null)
        {
            string jobPath = args.Require("--job"); string folder = Directory.Exists(jobPath) ? jobPath : Path.GetDirectoryName(Path.GetFullPath(jobPath))!;
            if (job.Dataset != Path.GetFileName(job.Dataset)) throw new InvalidDataException("A job dataset must be a file name, not a path.");
            input = Path.Combine(folder, job.Dataset);
        }
        if (string.IsNullOrWhiteSpace(input) || !File.Exists(input)) throw new FileNotFoundException("Pass --in with an existing CSV file.");
        return input;
    }
    private static ImportProfile? Profile(AppSettings s) => PluginAssets.Current.ImportProfiles.FirstOrDefault(p => p.Id.Equals(s.ImportProfileId, StringComparison.OrdinalIgnoreCase));
    private static string Num(double value) => double.IsFinite(value) ? value.ToString("0.######", CultureInfo.InvariantCulture) : "unavailable";
    public static int StateCheck(CliArguments args)
    {
        args.Validate(new[] { "--calibration", "--in" });
        string path = args.Require("--calibration"); if (Directory.Exists(path)) path = Path.Combine(path, CalibrationPersistence.FileName);
        CalibrationState state = CalibrationPersistence.Read(path);
        if (args.Value("--in") is string input && OutputExporter.HashFile(input) != state.DatasetHash) throw new InvalidDataException("Calibration input hash mismatch.");
        Console.WriteLine("Calibration checksum, method contract and input identity verified."); return 0;
    }
    public static int ShowVersions() { Console.WriteLine("MVS Analyzer " + ReleaseInfo.Version + " | engine " + AnalysisEngine.EngineVersion + " | formula " + OutputExporter.FormulaVersion); Console.WriteLine("Formula SHA256: " + OutputExporter.FormulaHash); Console.WriteLine("UI/Colab revision: ui-colab-1"); return 0; }
    public static int ShowEnvironment() { ShowVersions(); Console.WriteLine(BenchmarkEnvironment.Describe()); Console.WriteLine("Replay scope: " + BenchmarkEnvironment.Scope); Console.WriteLine("Environment fingerprint: " + BenchmarkEnvironment.Hash); return 0; }
}
