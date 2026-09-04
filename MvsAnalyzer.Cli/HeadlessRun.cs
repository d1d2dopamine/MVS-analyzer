using System.Globalization;
using System.Text.Json;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.Cli;

/// <summary>
/// What a calibration is, written down so that a second machine can finish the work a first one
/// started. A calibration is a measurement of how ten metrics behave on one specific dataset under
/// one specific set of settings, and it is worthless attached to anything else. So the dataset hash
/// and every setting that shaped it travel with the numbers, and analysis refuses to proceed when
/// they do not match what is in front of it.
/// </summary>
internal sealed record CalibrationState(
    string Dataset,
    string DatasetHash,
    string CalibrationSource,
    int Repetitions,
    double Effect,
    int Seed,
    string Scenario,
    double OutlierRate,
    double MissingRate,
    double Alpha,
    double EquivalenceMargin,
    bool SplitCalibration,
    string[] Tracks,
    string AppVersion,
    string EngineVersion,
    string FormulaVersion,
    string FormulaHash,
    string EnvironmentHash,
    string CreatedUtc,
    List<CalibrationRow> Rows);

/// <summary>
/// Calibration and analysis without a window.
///
/// The two phases are separate commands on purpose. In a hosted notebook the expensive phase is
/// calibration, and a session can be reclaimed before the work is used; writing the calibration to
/// disk means a lost session costs one cell instead of the whole run. It also makes the split that
/// the window performs silently visible: the numbers the analysis leans on are a file that can be
/// read, checked and archived.
/// </summary>
internal static class HeadlessRun
{
    public const string StateFileName = "calibration_state.json";

    private static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    public static int Calibrate(CliArguments args)
    {
        AppSettings settings = Settings(args, out RemoteJobFile? job);
        string input = Input(args, job);
        string output = args.Require("--out");
        int repetitions = args.Int("--repetitions", job?.Repetitions ?? settings.CustomRepetitions);
        if (repetitions < 100)
        {
            Console.Error.WriteLine("Use at least 100 repetitions; below that the false alarm rate is noise.");
            return 1;
        }

        Console.WriteLine();
        Console.WriteLine("MVS calibration");
        Environment(settings);
        Console.WriteLine("  data            " + input);
        Console.WriteLine("  output          " + output);
        Console.WriteLine("  repetitions     " + repetitions.ToString(CultureInfo.InvariantCulture));
        Console.WriteLine("  seed            " + settings.CalibrationSeed.ToString(CultureInfo.InvariantCulture));
        Console.WriteLine("  effect          " + Num(settings.CalibrationEffect));
        Console.WriteLine("  scenario        " + settings.SimulationScenario);
        Console.WriteLine("  tracks          " + string.Join(", ", AnalysisEngine.DefaultTracks));
        Console.WriteLine("  alpha           " + Num(settings.Alpha));
        Console.WriteLine();

        List<Observation> observations = CsvImporter.Read(input, settings.MinValue, settings.MaxValue, Profile(settings));
        AnalysisData data = AnalysisEngine.Build(observations, settings.MinValue, settings.MaxValue, settings.MinMeasurements);
        string datasetHash = OutputExporter.HashFile(input);

        Console.WriteLine("  encoding read   " + CsvImporter.LastEncodingName);
        Console.WriteLine("  entities        " + data.TotalEntities.ToString(CultureInfo.InvariantCulture));
        Console.WriteLine("  groups          " + string.Join(", ", data.GroupNames));
        Console.WriteLine("  valid rows      " + data.ValidRows.ToString(CultureInfo.InvariantCulture));
        Console.WriteLine("  dataset sha256  " + datasetHash);
        if (job != null && !string.Equals(job.DatasetHash, datasetHash, StringComparison.OrdinalIgnoreCase))
            Console.WriteLine("  note            the data does not match the hash recorded in the job file");
        Console.WriteLine();

        AnalysisData source = data;
        string calibrationSource = "same_dataset";
        if (settings.SplitCalibration)
        {
            var halves = AnalysisEngine.SplitEntities(data, settings.CalibrationSeed);
            source = halves.Calibration;
            calibrationSource = "split_half";
            Console.WriteLine("  calibrating on the first half of the entities, analysing the second");
        }

        var progress = new ConsoleProgress();
        List<CalibrationRow> calibration = AnalysisEngine.Calibrate(
            source,
            repetitions,
            settings.CalibrationEffect,
            settings.CalibrationSeed,
            progress,
            CancellationToken.None,
            settings.SimulationScenario,
            settings.OutlierRate,
            settings.MissingRate,
            settings.Alpha,
            AnalysisEngine.DefaultTracks);

        Directory.CreateDirectory(output);
        var state = new CalibrationState(
            Dataset: Path.GetFileName(input),
            DatasetHash: datasetHash,
            CalibrationSource: calibrationSource,
            Repetitions: repetitions,
            Effect: settings.CalibrationEffect,
            Seed: settings.CalibrationSeed,
            Scenario: settings.SimulationScenario,
            OutlierRate: settings.OutlierRate,
            MissingRate: settings.MissingRate,
            Alpha: settings.Alpha,
            EquivalenceMargin: settings.EquivalenceMargin,
            SplitCalibration: settings.SplitCalibration,
            Tracks: AnalysisEngine.DefaultTracks,
            AppVersion: RemoteJob.AppVersion,
            EngineVersion: AnalysisEngine.EngineVersion,
            FormulaVersion: OutputExporter.FormulaVersion,
            FormulaHash: OutputExporter.FormulaHash,
            EnvironmentHash: BenchmarkEnvironment.Hash,
            CreatedUtc: DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture),
            Rows: calibration);

        string statePath = Path.Combine(output, StateFileName);
        File.WriteAllText(statePath, JsonSerializer.Serialize(state, Json));
        File.WriteAllText(Path.Combine(output, "calibration.csv"), OutputExporter.CalibrationCsv(calibration));

        Console.WriteLine();
        Console.WriteLine("Calibration written.");
        Console.WriteLine("  " + statePath);
        Console.WriteLine();
        Tracks(calibration);
        Console.WriteLine();
        Console.WriteLine("Next: mvs analyze --in " + Path.GetFileName(input) + " --calibration " + output + " --out <folder>");
        Console.WriteLine();
        return 0;
    }

    public static int Analyze(CliArguments args)
    {
        AppSettings settings = Settings(args, out RemoteJobFile? job);
        string input = Input(args, job);
        string output = args.Require("--out");
        string calibrationPath = args.Require("--calibration");
        if (Directory.Exists(calibrationPath)) calibrationPath = Path.Combine(calibrationPath, StateFileName);
        if (!File.Exists(calibrationPath))
            throw new FileNotFoundException("No calibration was found at " + calibrationPath);

        CalibrationState? state = JsonSerializer.Deserialize<CalibrationState>(File.ReadAllText(calibrationPath), Json);
        if (state == null || state.Rows.Count == 0)
            throw new InvalidDataException("The calibration file is empty: " + calibrationPath);

        // The calibration decides the settings, not the command line. Anything else would let a
        // typed flag quietly describe a run that did not happen.
        settings.CalibrationSeed = state.Seed;
        settings.CalibrationEffect = state.Effect;
        settings.SimulationScenario = state.Scenario;
        settings.OutlierRate = state.OutlierRate;
        settings.MissingRate = state.MissingRate;
        settings.Alpha = state.Alpha;
        settings.EquivalenceMargin = state.EquivalenceMargin;
        settings.SplitCalibration = state.SplitCalibration;

        Console.WriteLine();
        Console.WriteLine("MVS analysis");
        Environment(settings);
        Console.WriteLine("  data            " + input);
        Console.WriteLine("  calibration     " + calibrationPath);
        Console.WriteLine("  measured with   " + state.Repetitions.ToString(CultureInfo.InvariantCulture) + " repetitions, seed " + state.Seed.ToString(CultureInfo.InvariantCulture));
        Console.WriteLine("  formula         " + state.FormulaVersion + "  " + state.FormulaHash);
        if (!string.Equals(state.EnvironmentHash, BenchmarkEnvironment.Hash, StringComparison.OrdinalIgnoreCase))
            Console.WriteLine("  note            the calibration was measured in a different environment");
        Console.WriteLine();

        List<Observation> observations = CsvImporter.Read(input, settings.MinValue, settings.MaxValue, Profile(settings));
        AnalysisData data = AnalysisEngine.Build(observations, settings.MinValue, settings.MaxValue, settings.MinMeasurements);
        string datasetHash = OutputExporter.HashFile(input);

        if (!string.Equals(datasetHash, state.DatasetHash, StringComparison.OrdinalIgnoreCase))
        {
            Console.Error.WriteLine("This calibration was measured on different data.");
            Console.Error.WriteLine("  calibration expects  " + state.DatasetHash);
            Console.Error.WriteLine("  this file is         " + datasetHash);
            if (!args.Flag("--force"))
            {
                Console.Error.WriteLine("Calibrate again, or pass --force if you know why the bytes changed.");
                return 1;
            }
            Console.Error.WriteLine("Continuing because --force was passed. The manifest records both hashes.");
        }

        AnalysisData analysed = data;
        if (state.SplitCalibration)
        {
            var halves = AnalysisEngine.SplitEntities(data, state.Seed);
            analysed = halves.Analysis;
            Console.WriteLine("  analysing the half that was held out of calibration");
        }

        var progress = new ConsoleProgress();
        List<ResultRow> results = AnalysisEngine.Results(
            analysed,
            state.Rows,
            progress,
            CancellationToken.None,
            settings.Alpha,
            settings.EquivalenceMargin,
            state.Seed);

        // Figures are the one thing a headless run cannot produce, so the flag is forced off
        // rather than left to fail later inside an exporter.
        settings.GenerateFigures = false;
        settings.FigureOutputFolder = output;
        settings.FigureFolderConfirmed = true;
        Directory.CreateDirectory(output);

        string project = args.Value("--project") ?? job?.Project ?? "Headless run";
        string description = args.Value("--description") ?? job?.Description ?? "";
        string runId = DateTime.Now.ToString("yyyy-MM-dd_HHmmss", CultureInfo.InvariantCulture);
        string runFolder = OutputExporter.PrepareRunFolder(settings, runId);

        var artifacts = new List<OutputArtifact>();
        try
        {
            foreach (string report in PluginAssets.WriteReports(runFolder, runId, project, state.Dataset, analysed, results, settings))
                artifacts.Add(OutputExporter.FromFile("Report", report));
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("A plugin report template failed and was skipped: " + error.Message);
        }

        artifacts.AddRange(OutputExporter.Export(
            runFolder, runId, project, description, settings.InterfaceMode,
            state.Dataset, datasetHash, analysed, state.Rows, results, settings,
            state.Repetitions, artifacts, state.CalibrationSource));

        File.Copy(calibrationPath, Path.Combine(runFolder, StateFileName), true);

        try
        {
            RunAuditor.AppendJournal(runId, runFolder, datasetHash, settings, state.Repetitions,
                string.Join(", ", results.Where(x => x.Candidate).Select(x => x.Metric)));
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("The run journal could not be updated: " + error.Message);
        }

        Console.WriteLine();
        Console.WriteLine("Analysis written.");
        Console.WriteLine("  " + runFolder);
        Console.WriteLine("  " + artifacts.Count.ToString(CultureInfo.InvariantCulture) + " files");
        Console.WriteLine();
        Results(results);
        Console.WriteLine();
        return 0;
    }

    public static int ShowEnvironment()
    {
        Console.WriteLine();
        Console.WriteLine("Environment");
        Console.WriteLine("  " + BenchmarkEnvironment.Describe());
        Console.WriteLine("  processors      " + System.Environment.ProcessorCount.ToString(CultureInfo.InvariantCulture));
        Console.WriteLine("  environment id  " + BenchmarkEnvironment.Hash);
        Console.WriteLine("  replay scope    " + BenchmarkEnvironment.Scope);
        Console.WriteLine();
        Console.WriteLine("  Replay is bit-identical inside one environment. Math.Log, Math.Exp, Math.Pow");
        Console.WriteLine("  and Math.Cos are not required to be correctly rounded, so a run repeated on a");
        Console.WriteLine("  different operating system or architecture can differ in the last bits. When");
        Console.WriteLine("  two determinism hashes disagree, compare the environment id first.");
        Console.WriteLine();
        Console.WriteLine("  fingerprint     " + BenchmarkEnvironment.Fingerprint());
        Console.WriteLine();
        return 0;
    }

    public static int ShowVersions()
    {
        Console.WriteLine();
        Console.WriteLine("  application     " + RemoteJob.AppVersion);
        Console.WriteLine("  engine          " + AnalysisEngine.EngineVersion);
        Console.WriteLine("  formula         " + OutputExporter.FormulaVersion);
        Console.WriteLine("  formula hash    " + OutputExporter.FormulaHash);
        Console.WriteLine("  protocol        " + BenchmarkProtocol.Version);
        Console.WriteLine("  protocol hash   " + BenchmarkProtocol.Hash);
        Console.WriteLine("  protocol frozen " + (BenchmarkProtocol.HashIsFrozen ? "yes" : "NO - results are not comparable"));
        Console.WriteLine("  environment id  " + BenchmarkEnvironment.ShortHash);
        Console.WriteLine();
        return 0;
    }

    private static void Environment(AppSettings settings)
    {
        Console.WriteLine("  version         " + RemoteJob.AppVersion + "   engine " + AnalysisEngine.EngineVersion + "   formula " + OutputExporter.FormulaVersion);
        Console.WriteLine("  environment     " + BenchmarkEnvironment.Describe());
        Console.WriteLine("  environment id  " + BenchmarkEnvironment.ShortHash);
        if (settings.Language == "ru")
            Console.WriteLine("  note            the headless output is English only for now");
    }

    /// <summary>Loads settings, then lets a job file and then the command line override them.</summary>
    private static AppSettings Settings(CliArguments args, out RemoteJobFile? job)
    {
        AppSettings settings = AppSettings.Load();
        job = null;

        string? jobPath = args.Value("--job");
        if (jobPath != null)
        {
            if (Directory.Exists(jobPath)) jobPath = Path.Combine(jobPath, RemoteJob.JobFileName);
            job = RemoteJob.Read(jobPath);
            RemoteJob.Apply(job, settings);
        }

        settings.CalibrationSeed = args.Int("--seed", settings.CalibrationSeed);
        settings.CalibrationEffect = args.Number("--effect", settings.CalibrationEffect);
        settings.Alpha = args.Number("--alpha", settings.Alpha);
        settings.OutlierRate = args.Number("--outliers", settings.OutlierRate);
        settings.MissingRate = args.Number("--missing", settings.MissingRate);
        settings.EquivalenceMargin = args.Number("--margin", settings.EquivalenceMargin);
        settings.MinMeasurements = args.Int("--min-measurements", settings.MinMeasurements);
        if (args.Flag("--split")) settings.SplitCalibration = true;

        string? scenario = args.Value("--scenario");
        if (scenario != null)
        {
            if (!SimulationScenarios.TryCanonical(scenario, out string canonical))
                throw new ArgumentException("Unknown scenario: " + scenario + ". Use one of " + string.Join(", ", SimulationScenarios.All) + ".");
            settings.SimulationScenario = canonical;
        }

        return settings;
    }

    private static string Input(CliArguments args, RemoteJobFile? job)
    {
        string? input = args.Value("--in");
        if (input == null && job != null)
        {
            string? folder = Path.GetDirectoryName(args.Value("--job") ?? "");
            input = string.IsNullOrEmpty(folder) ? job.Dataset : Path.Combine(folder, job.Dataset);
        }
        if (string.IsNullOrWhiteSpace(input)) throw new ArgumentException("Pass --in <file.csv>.");
        if (!File.Exists(input)) throw new FileNotFoundException("The data file was not found: " + input);
        return input;
    }

    private static ImportProfile? Profile(AppSettings settings) =>
        PluginAssets.Current.ImportProfiles.FirstOrDefault(
            x => string.Equals(x.Id, settings.ImportProfileId, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// Prints the calibration one track at a time, because that is the shape of the decision. A
    /// single ranked list is what used to hide the spread metrics below the fold.
    /// </summary>
    private static void Tracks(List<CalibrationRow> calibration)
    {
        foreach (string track in AnalysisEngine.DefaultTracks)
        {
            Console.WriteLine("  " + track);
            foreach (CalibrationRow row in calibration
                .OrderByDescending(x => x.ScoreIn(track))
                .ThenBy(x => x.Metric, StringComparer.Ordinal)
                .Take(4))
            {
                Console.WriteLine("    " + row.Metric.PadRight(26) +
                    "power " + Pct(row.PowerIn(track)).PadLeft(6) +
                    "   score " + Num(row.ScoreIn(track)).PadLeft(6) +
                    "   fpr " + Pct(row.Fpr).PadLeft(6) +
                    (row.PassesGateIn(track) ? "   passes the gate" : ""));
            }
        }
    }

    private static void Results(List<ResultRow> results)
    {
        Console.WriteLine("  metric                    verdict         p        effect    candidate in");
        foreach (ResultRow row in results.Take(12))
        {
            Console.WriteLine("  " + row.Metric.PadRight(26) +
                row.Verdict.PadRight(16) +
                Num(row.PValue).PadRight(9) +
                Num(row.Effect).PadRight(10) +
                (string.IsNullOrEmpty(row.CandidateTracks) ? "-" : row.CandidateTracks));
        }
    }

    private static string Pct(double value) =>
        double.IsFinite(value) ? (value * 100).ToString("0.0", CultureInfo.InvariantCulture) + "%" : "-";

    private static string Num(double value) =>
        double.IsFinite(value) ? value.ToString("0.###", CultureInfo.InvariantCulture) : "-";

    /// <summary>
    /// Progress on one line per five percent. A notebook keeps every line that is printed, so a
    /// per-repetition counter would bury the result under thousands of rows of scrollback.
    /// </summary>
    private sealed class ConsoleProgress : IProgress<ProgressInfo>
    {
        private readonly object gate = new();
        private int lastPrinted = -1;

        public void Report(ProgressInfo value)
        {
            int percent = (int)Math.Round(Math.Clamp(value.Fraction, 0, 1) * 100);
            int bucket = percent / 5;
            lock (gate)
            {
                if (bucket <= lastPrinted && percent < 100) return;
                lastPrinted = bucket;
                Console.WriteLine("  " + percent.ToString(CultureInfo.InvariantCulture).PadLeft(3) + "%  " +
                    value.Action + (string.IsNullOrEmpty(value.Details) ? "" : "  -  " + value.Details));
            }
        }
    }
}
