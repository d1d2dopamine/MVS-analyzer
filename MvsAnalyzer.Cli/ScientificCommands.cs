using System.Globalization;
using System.Reflection;

namespace MvsAnalyzer.Cli;

internal static class ScientificCommands
{
    public static int Variance(CliArguments args)
    {
        args.Validate(new[] { "--in", "--out", "--repetitions", "--bootstrap", "--seed", "--alpha", "--within-effect", "--between-effect", "--min-measurements", "--overwrite", "--allow-group-scoped-ids" });
        string input = args.Require("--in"), folder = Prepare(args);
        List<Observation> observations = CsvImporter.Read(input, int.MinValue, int.MaxValue);
        HeadlessRun.CheckIndependentIds(observations, args.Flag("--allow-group-scoped-ids"));
        AnalysisData data = AnalysisEngine.Build(observations, int.MinValue, int.MaxValue, args.Int("--min-measurements", 3));
        VarianceReport report = VarianceAnalysis.Run(data, args.Int("--repetitions", 200), args.Int("--bootstrap", 199), args.Number("--within-effect", 1.3),
            args.Number("--between-effect", 1.3), args.Int("--seed", 20260719), args.Number("--alpha", .05), new CliProgress(), CliCancellation.Token);
        ScientificJson.Write(Path.Combine(folder, "variance_report.json"), report);
        ScientificJson.AtomicText(Path.Combine(folder, "variance_components.csv"), VarianceAnalysis.Csv(report));
        ScientificJson.AtomicText(Path.Combine(folder, "variance_tests.csv"), Table(report.Tracks));
        Manifest(folder, "variance-components", input, report);
        Console.WriteLine("Variance report saved: " + folder);
        foreach (VarianceTrack track in report.Tracks) Console.WriteLine(track.Track + ": " + track.Verdict + " | " + track.Status);
        return report.Groups.Any(g => g.Status == "not_converged_or_degenerate") || report.Tracks.Any(t => t.Status == "bootstrap_or_fit_failure" || t.Status == "excess_simulation_failures") ? 2 : 0;
    }
    public static int Estimation(CliArguments args)
    {
        args.Validate(new[] { "--out", "--target", "--shape", "--entities", "--measurements", "--repetitions", "--bootstrap", "--seed", "--location", "--within-sd", "--between-sd", "--overwrite" });
        string folder = Prepare(args), shape = args.Value("--shape") ?? "normal"; bool lognormal = shape == "lognormal";
        var options = new EstimationOptions(args.Value("--target") ?? "mean", shape, args.Int("--entities", 20), args.Int("--measurements", 12),
            args.Int("--repetitions", 500), args.Int("--bootstrap", 199), args.Int("--seed", 20260719),
            args.Number("--location", lognormal ? 1 : 100), args.Number("--within-sd", lognormal ? .3 : 10), args.Number("--between-sd", lognormal ? .2 : 5));
        EstimationReport report = EstimationStudy.Run(options, new CliProgress(), CliCancellation.Token);
        ScientificJson.Write(Path.Combine(folder, "estimation_report.json"), report);
        ScientificJson.AtomicText(Path.Combine(folder, "estimation_performance.csv"), Table(report.Performance));
        ScientificJson.AtomicText(Path.Combine(folder, "estimation_draws.csv"), Table(report.Draws));
        Manifest(folder, "known-truth-estimation", null, options);
        Console.WriteLine("Known-truth estimation report saved: " + folder);
        return report.Performance.Any(p => p.Status == "excess_failures") ? 2 : 0;
    }
    public static int Melsm(CliArguments args)
    {
        args.Validate(new[] { "--in", "--out", "--mean-time", "--scale-time", "--correlate", "--no-random-scale", "--quadrature", "--max-iterations", "--overwrite", "--include-entity-ids" });
        string input = args.Require("--in"), folder = Prepare(args);
        List<Observation> rows = CsvImporter.Read(input, int.MinValue, int.MaxValue, allowSingleGroup: true);
        if ((args.Flag("--mean-time") || args.Flag("--scale-time")) && !CsvImporter.LastSequenceWasProvided)
            throw new InvalidDataException("A real integer sequence/timepoint column is required for time effects; row order is not a time variable.");
        var options = new MelsmOptions(args.Flag("--mean-time"), args.Flag("--scale-time"), args.Flag("--correlate"), !args.Flag("--no-random-scale"), args.Int("--quadrature", 15), args.Int("--max-iterations", 4000));
        MelsmReport report = MelsmAnalysis.Run(rows, options, new CliProgress(), CliCancellation.Token);
        if (!args.Flag("--include-entity-ids")) report = report with { RandomEffects = report.RandomEffects.Select(r => r with { Entity = "P_" + ScientificMath.Hash(r.Entity)[..12] }).ToArray() };
        ScientificJson.Write(Path.Combine(folder, "melsm_report.json"), report);
        ScientificJson.AtomicText(Path.Combine(folder, "melsm_parameters.csv"), Table(report.Parameters));
        ScientificJson.AtomicText(Path.Combine(folder, "melsm_random_effects.csv"), Table(report.RandomEffects));
        Manifest(folder, "experimental-melsm", input, options);
        Console.WriteLine("MELSM report saved: " + folder + " | " + report.Status);
        return report.Status == "converged_experimental" ? 0 : 2;
    }
    private static string Prepare(CliArguments args)
    {
        string folder = Path.GetFullPath(args.Require("--out"));
        if (Directory.Exists(folder) && Directory.EnumerateFileSystemEntries(folder).Any() && !args.Flag("--overwrite"))
            throw new InvalidDataException("The output directory is not empty. Use a new directory or explicitly pass --overwrite.");
        Directory.CreateDirectory(folder); return folder;
    }
    internal static string Table<T>(IEnumerable<T> rows)
    {
        PropertyInfo[] columns = typeof(T).GetProperties().Where(p => p.PropertyType == typeof(string) || p.PropertyType.IsPrimitive).ToArray();
        string Value(object? value) => value switch {
            null => "", double d => double.IsFinite(d) ? d.ToString("R", CultureInfo.InvariantCulture) : "",
            string text => "\"" + ((text.Length > 0 && "=+-@\t\r".Contains(text[0])) ? "'" + text : text).Replace("\"", "\"\"") + "\"",
            IFormattable f => f.ToString(null, CultureInfo.InvariantCulture), _ => value.ToString() ?? "" };
        return string.Join(",", columns.Select(p => p.Name)) + "\n" + string.Join("\n", rows.Select(r => string.Join(",", columns.Select(p => Value(p.GetValue(r)))))) + "\n";
    }
    private static void Manifest<T>(string folder, string kind, string? input, T configuration)
    {
        var files = Directory.GetFiles(folder).Where(f => Path.GetFileName(f) != "run_manifest.json").Select(f => new { FileName = Path.GetFileName(f), sha256 = OutputExporter.HashFile(f), SizeBytes = new FileInfo(f).Length }).ToArray();
        ScientificJson.Write(Path.Combine(folder, "run_manifest.json"), new { schemaVersion = 2, executionEnvironment = new { description = Benchmarking.BenchmarkEnvironment.Describe(), fingerprint = Benchmarking.BenchmarkEnvironment.Hash, replayScope = Benchmarking.BenchmarkEnvironment.Scope }, application = "MVS Analyzer", version = ReleaseInfo.Version,
            engineVersion = ReleaseInfo.EngineVersion, runId = kind + "_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture), created = DateTimeOffset.UtcNow,
            kind, configuration, inputData = new { file = input == null ? "synthetic" : Path.GetFileName(input), sha256 = input == null ? ScientificMath.Hash(ScientificJson.Serialize(configuration)) : OutputExporter.HashFile(input) },
            formula = new { version = "model-specific", hash = "", specification = "See model/configuration in the corresponding report; the summary-metric score is not used here." },
            files, warning = "Numerical and scientific validation status is reported explicitly; a saved result does not by itself certify model adequacy." });
    }
}
