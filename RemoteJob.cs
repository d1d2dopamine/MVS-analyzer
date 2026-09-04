using System.Globalization;
using System.IO.Compression;
using System.Text.Json;

namespace MvsAnalyzer;

/// <summary>
/// Everything a hosted notebook needs in order to repeat a run that was set up in the window.
///
/// The point of a job file is that a remote run is not a different analysis. A person who cannot
/// finish a calibration on a laptop should not have to retype thirteen settings into a notebook and
/// hope they matched; a mistyped seed produces a number that looks like a result and is not one.
/// So the settings travel with the data, and the headless commands read them instead of asking.
///
/// The dataset hash travels too. Analysis refuses to reuse a calibration that was measured on
/// different bytes, because a calibration is a statement about one dataset and nothing else.
/// </summary>
internal sealed record RemoteJobFile(
    string Kind,
    string Dataset,
    string DatasetHash,
    string Project,
    string Description,
    int MinValue,
    int MaxValue,
    int MinMeasurements,
    int Repetitions,
    int Seed,
    double Effect,
    string Scenario,
    double OutlierRate,
    double MissingRate,
    double Alpha,
    double EquivalenceMargin,
    bool SplitCalibration,
    string InterfaceMode,
    string Language,
    string AppVersion,
    string EngineVersion,
    string FormulaVersion,
    string FormulaHash,
    string CreatedUtc);

internal static class RemoteJob
{
    /// <summary>The single place the shipped version number is written for remote work.</summary>
    public const string AppVersion = "1.5.0";

    public const string JobFileName = "job.json";

    /// <summary>
    /// Colab can open a notebook straight out of a public repository, which is the only way to get
    /// "press a button, get a ready notebook" without asking anyone for a Google account token.
    /// The notebook arrives as an unsaved copy in the visitor's own session, so nothing this project
    /// controls can touch their Drive, and no data leaves the browser on the way there.
    /// </summary>
    public const string Repository = "d1d2dopamine/MVS-Analyzer";

    public const string Branch = "main";

    private static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    public static string NotebookPath(string kind) => kind switch
    {
        "benchmark" => "notebooks/MVS_Colab_Benchmark.ipynb",
        "kaggle" => "notebooks/MVS_Kaggle.ipynb",
        _ => "notebooks/MVS_Colab.ipynb",
    };

    public static string ColabUrl(string kind) =>
        "https://colab.research.google.com/github/" + Repository + "/blob/" + Branch + "/" + NotebookPath(kind);

    /// <summary>
    /// Kaggle has no equivalent of the Colab deep link, so the honest thing is to send people to the
    /// import dialog with the repository address rather than pretend a one-click path exists.
    /// </summary>
    public static string KaggleUrl() => "https://www.kaggle.com/code/new";

    public static string RepositoryUrl() => "https://github.com/" + Repository;

    public static RemoteJobFile Describe(
        string kind,
        string datasetPath,
        string datasetHash,
        string project,
        string description,
        AppSettings settings,
        int repetitions)
    {
        return new RemoteJobFile(
            Kind: kind,
            Dataset: Path.GetFileName(datasetPath),
            DatasetHash: datasetHash,
            Project: project,
            Description: description,
            MinValue: settings.MinValue,
            MaxValue: settings.MaxValue,
            MinMeasurements: settings.MinMeasurements,
            Repetitions: repetitions,
            Seed: settings.CalibrationSeed,
            Effect: settings.CalibrationEffect,
            Scenario: settings.SimulationScenario,
            OutlierRate: settings.OutlierRate,
            MissingRate: settings.MissingRate,
            Alpha: settings.Alpha,
            EquivalenceMargin: settings.EquivalenceMargin,
            SplitCalibration: settings.SplitCalibration,
            InterfaceMode: settings.InterfaceMode,
            Language: settings.Language,
            AppVersion: AppVersion,
            EngineVersion: AnalysisEngine.EngineVersion,
            FormulaVersion: OutputExporter.FormulaVersion,
            FormulaHash: OutputExporter.FormulaHash,
            CreatedUtc: DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture));
    }

    public static string Serialize(RemoteJobFile job) => JsonSerializer.Serialize(job, Json);

    public static RemoteJobFile Read(string path)
    {
        RemoteJobFile? job = JsonSerializer.Deserialize<RemoteJobFile>(File.ReadAllText(path), Json);
        if (job == null) throw new InvalidDataException("The job file could not be read: " + path);
        return job;
    }

    /// <summary>Copies the job settings over a settings object so both phases use identical values.</summary>
    public static void Apply(RemoteJobFile job, AppSettings settings)
    {
        settings.MinValue = job.MinValue;
        settings.MaxValue = job.MaxValue;
        settings.MinMeasurements = job.MinMeasurements;
        settings.CalibrationSeed = job.Seed;
        settings.CalibrationEffect = job.Effect;
        settings.SimulationScenario = job.Scenario;
        settings.OutlierRate = job.OutlierRate;
        settings.MissingRate = job.MissingRate;
        settings.Alpha = job.Alpha;
        settings.EquivalenceMargin = job.EquivalenceMargin;
        settings.SplitCalibration = job.SplitCalibration;
        if (!string.IsNullOrWhiteSpace(job.InterfaceMode)) settings.InterfaceMode = job.InterfaceMode;
        if (!string.IsNullOrWhiteSpace(job.Language)) settings.Language = job.Language;
    }

    /// <summary>
    /// Writes a bundle the notebook can accept as a single upload: the data, the settings, and a
    /// readme so that the archive is still understandable a year later when nobody remembers what
    /// it was for.
    /// </summary>
    public static string WriteBundle(
        string destinationFolder,
        string datasetPath,
        string datasetHash,
        string project,
        string description,
        AppSettings settings,
        int repetitions,
        string kind = "calibrate_analyze")
    {
        if (!File.Exists(datasetPath))
            throw new FileNotFoundException("The dataset was not found: " + datasetPath);

        Directory.CreateDirectory(destinationFolder);
        string stamp = DateTime.Now.ToString("yyyy-MM-dd_HHmmss", CultureInfo.InvariantCulture);
        string staging = Path.Combine(destinationFolder, "MVS_job_" + stamp);
        Directory.CreateDirectory(staging);

        RemoteJobFile job = Describe(kind, datasetPath, datasetHash, project, description, settings, repetitions);
        File.Copy(datasetPath, Path.Combine(staging, job.Dataset), true);
        File.WriteAllText(Path.Combine(staging, JobFileName), Serialize(job));
        File.WriteAllText(Path.Combine(staging, "README.txt"), Readme(job));

        string archive = staging + ".zip";
        if (File.Exists(archive)) File.Delete(archive);
        ZipFile.CreateFromDirectory(staging, archive, CompressionLevel.Optimal, false);
        Directory.Delete(staging, true);
        return archive;
    }

    private static string Readme(RemoteJobFile job)
    {
        var lines = new List<string>
        {
            "MVS Analyzer remote job",
            "",
            "Upload this archive into the first cell of the notebook at",
            "  " + ColabUrl(job.Kind == "benchmark" ? "benchmark" : "analysis"),
            "",
            "Contents",
            "  " + job.Dataset + "   the measurements, unchanged",
            "  " + JobFileName + "   the settings the run must use",
            "",
            "dataset sha256   " + job.DatasetHash,
            "seed             " + job.Seed.ToString(CultureInfo.InvariantCulture),
            "repetitions      " + job.Repetitions.ToString(CultureInfo.InvariantCulture),
            "scenario         " + job.Scenario,
            "alpha            " + job.Alpha.ToString(CultureInfo.InvariantCulture),
            "formula          " + job.FormulaVersion + "  " + job.FormulaHash,
            "created          " + job.CreatedUtc,
            "",
            "The results the notebook writes carry the same hashes, so a reviewer can check that",
            "the remote run and a local run were the same analysis.",
            "",
            "Anything uploaded to a hosted notebook leaves this machine. If these measurements are",
            "identifiable or restricted, run the analysis locally instead; the window does the same",
            "work offline and always will.",
        };
        return string.Join(Environment.NewLine, lines) + Environment.NewLine;
    }
}
