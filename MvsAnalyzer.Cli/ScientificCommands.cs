using System.Globalization;
using System.Reflection;

namespace MvsAnalyzer.Cli;

internal static class ScientificCommands
{
    public static int Variance(CliArguments args)
    {
        args.Validate(new[] { "--in", "--out", "--repetitions", "--bootstrap", "--seed", "--alpha", "--within-effect", "--between-effect", "--min-measurements", "--overwrite", "--allow-group-scoped-ids", "--import-profile", "--min-value", "--max-value" });
        string input = args.Require("--in"), folder = Prepare(args, OutputSafety.VarianceFiles, input);
        int minimum = args.Int("--min-value", int.MinValue), maximum = args.Int("--max-value", int.MaxValue);
        CsvImportResult imported = CsvImporter.Import(input, minimum, maximum, Profile(args), cancellationToken: CliCancellation.Token);
        List<Observation> observations = imported.Observations;
        HeadlessRun.CheckIndependentIds(observations, args.Flag("--allow-group-scoped-ids"));
        AnalysisData data = AnalysisEngine.Build(observations, minimum, maximum, args.Int("--min-measurements", 3));
        VarianceReport report = VarianceAnalysis.Run(data, args.Int("--repetitions", 200), args.Int("--bootstrap", 199), args.Number("--within-effect", 1.3),
            args.Number("--between-effect", 1.3), args.Int("--seed", 20260719), args.Number("--alpha", .05), new CliProgress(), CliCancellation.Token);
        CliMachineContext.BeginOutput(folder);
        CliMachineContext.WriteOutput(Path.Combine(folder, "variance_report.json"), () => ScientificJson.Write(Path.Combine(folder, "variance_report.json"), report));
        CliMachineContext.WriteOutput(Path.Combine(folder, "variance_components.csv"), () => ScientificJson.AtomicText(Path.Combine(folder, "variance_components.csv"), VarianceAnalysis.Csv(report)));
        CliMachineContext.WriteOutput(Path.Combine(folder, "variance_tests.csv"), () => ScientificJson.AtomicText(Path.Combine(folder, "variance_tests.csv"), Table(report.Tracks)));
        CliMachineContext.WriteOutput(Path.Combine(folder, "run_manifest.json"), () => Manifest(folder, "variance-components", input, report, new[] { "variance_report.json", "variance_components.csv", "variance_tests.csv" }, imported.SourceSha256));
        CliMachineContext.RecordOutput(folder);
        Console.WriteLine("Variance report saved: " + folder);
        foreach (VarianceTrack track in report.Tracks) Console.WriteLine(track.Track + ": " + track.Verdict + " | " + track.Status);
        bool diagnostic = report.Groups.Any(g => g.Status == "not_converged_or_degenerate") || report.Tracks.Any(t => t.Status == "bootstrap_or_fit_failure" || t.Status == "excess_simulation_failures");
        if (diagnostic) CliMachineContext.Diagnostic("warning", "scientific_diagnostic", "Variance analysis completed with a numerical/scientific diagnostic; inspect variance_report.json.");
        return diagnostic ? 2 : 0;
    }
    public static int Estimation(CliArguments args)
    {
        args.Validate(new[] { "--out", "--target", "--shape", "--entities", "--measurements", "--repetitions", "--bootstrap", "--seed", "--location", "--within-sd", "--between-sd", "--overwrite" });
        string folder = Prepare(args, OutputSafety.EstimationFiles, null), shape = args.Value("--shape") ?? "normal"; bool lognormal = shape == "lognormal";
        var options = new EstimationOptions(args.Value("--target") ?? "mean", shape, args.Int("--entities", 20), args.Int("--measurements", 12),
            args.Int("--repetitions", 500), args.Int("--bootstrap", 199), args.Int("--seed", 20260719),
            args.Number("--location", lognormal ? 1 : 100), args.Number("--within-sd", lognormal ? .3 : 10), args.Number("--between-sd", lognormal ? .2 : 5));
        EstimationReport report = EstimationStudy.Run(options, new CliProgress(), CliCancellation.Token);
        CliMachineContext.BeginOutput(folder);
        CliMachineContext.WriteOutput(Path.Combine(folder, "estimation_report.json"), () => ScientificJson.Write(Path.Combine(folder, "estimation_report.json"), report));
        CliMachineContext.WriteOutput(Path.Combine(folder, "estimation_performance.csv"), () => ScientificJson.AtomicText(Path.Combine(folder, "estimation_performance.csv"), Table(report.Performance)));
        CliMachineContext.WriteOutput(Path.Combine(folder, "estimation_draws.csv"), () => ScientificJson.AtomicText(Path.Combine(folder, "estimation_draws.csv"), Table(report.Draws)));
        CliMachineContext.WriteOutput(Path.Combine(folder, "run_manifest.json"), () => Manifest(folder, "known-truth-estimation", null, options, new[] { "estimation_report.json", "estimation_performance.csv", "estimation_draws.csv" }));
        CliMachineContext.RecordOutput(folder);
        Console.WriteLine("Known-truth estimation report saved: " + folder);
        bool diagnostic = report.Performance.Any(p => p.Status == "excess_failures");
        if (diagnostic) CliMachineContext.Diagnostic("warning", "scientific_diagnostic", "Estimation study completed with excess failures; inspect estimation_report.json.");
        return diagnostic ? 2 : 0;
    }
    public static int Melsm(CliArguments args)
    {
        args.Validate(new[] { "--in", "--out", "--mean-time", "--scale-time", "--correlate", "--no-random-scale", "--quadrature", "--max-iterations", "--overwrite", "--include-entity-ids", "--import-profile", "--min-value", "--max-value" });
        string input = args.Require("--in"), folder = Prepare(args, OutputSafety.MelsmFiles, input);
        CsvImportResult imported = CsvImporter.Import(input, args.Int("--min-value", int.MinValue), args.Int("--max-value", int.MaxValue), Profile(args), allowSingleGroup: true, cancellationToken: CliCancellation.Token);
        List<Observation> rows = imported.Observations;
        if ((args.Flag("--mean-time") || args.Flag("--scale-time")) && !imported.SequenceWasProvided)
            throw new InvalidDataException("A real integer sequence/timepoint column is required for time effects; row order is not a time variable.");
        var options = new MelsmOptions(args.Flag("--mean-time"), args.Flag("--scale-time"), args.Flag("--correlate"), !args.Flag("--no-random-scale"), args.Int("--quadrature", 15), args.Int("--max-iterations", 4000));
        MelsmReport report = MelsmAnalysis.Run(rows, options, new CliProgress(), CliCancellation.Token);
        if (!args.Flag("--include-entity-ids")) report = report with { RandomEffects = report.RandomEffects.Select(r => r with { Entity = "P_" + ScientificMath.Hash(r.Entity)[..12] }).ToArray() };
        CliMachineContext.BeginOutput(folder);
        CliMachineContext.WriteOutput(Path.Combine(folder, "melsm_report.json"), () => ScientificJson.Write(Path.Combine(folder, "melsm_report.json"), report));
        CliMachineContext.WriteOutput(Path.Combine(folder, "melsm_parameters.csv"), () => ScientificJson.AtomicText(Path.Combine(folder, "melsm_parameters.csv"), Table(report.Parameters)));
        CliMachineContext.WriteOutput(Path.Combine(folder, "melsm_random_effects.csv"), () => ScientificJson.AtomicText(Path.Combine(folder, "melsm_random_effects.csv"), Table(report.RandomEffects)));
        CliMachineContext.WriteOutput(Path.Combine(folder, "run_manifest.json"), () => Manifest(folder, "experimental-melsm", input, options, new[] { "melsm_report.json", "melsm_parameters.csv", "melsm_random_effects.csv" }, imported.SourceSha256));
        CliMachineContext.RecordOutput(folder);
        Console.WriteLine("MELSM report saved: " + folder + " | " + report.Status);
        bool diagnostic = report.Status != "converged_experimental";
        if (diagnostic) CliMachineContext.Diagnostic("warning", "scientific_diagnostic", "MELSM completed without the converged_experimental status; inspect melsm_report.json.");
        return diagnostic ? 2 : 0;
    }
    private static ImportProfile? Profile(CliArguments args) => args.Value("--import-profile") is string file ? ScientificJson.Read<ImportProfile>(file) : null;
    private static string Prepare(CliArguments args, IEnumerable<string> outputNames, string? input)
    {
        string folder = Path.GetFullPath(args.Require("--out"));
        OutputSafety.Preflight(folder, outputNames, new[] { input, args.Value("--import-profile") }, args.Flag("--overwrite"), requireEmptyDirectory: true);
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
    private static void Manifest<T>(string folder, string kind, string? input, T configuration, IReadOnlyList<string> producedFiles, string? capturedInputHash = null)
    {
        var files = producedFiles.Select(name => Path.Combine(folder, name)).Select(f => new { FileName = Path.GetFileName(f), sha256 = OutputExporter.HashFile(f), SizeBytes = new FileInfo(f).Length }).ToArray();
        ScientificJson.Write(Path.Combine(folder, "run_manifest.json"), new { schemaVersion = 2, executionEnvironment = new { description = Benchmarking.BenchmarkEnvironment.Describe(), fingerprint = Benchmarking.BenchmarkEnvironment.Hash, replayScope = Benchmarking.BenchmarkEnvironment.Scope }, application = "MVS Analyzer", version = ReleaseInfo.Version,
            engineVersion = ReleaseInfo.EngineVersion, runId = kind + "_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture), created = DateTimeOffset.UtcNow,
            kind, configuration, inputData = new { file = input == null ? "synthetic" : Path.GetFileName(input), sha256 = input == null ? ScientificMath.Hash(ScientificJson.Serialize(configuration)) : capturedInputHash ?? throw new InvalidOperationException("Captured input identity is required.") },
            formula = new { version = "model-specific", hash = "", specification = "See model/configuration in the corresponding report; the summary-metric score is not used here." },
            files, warning = "Numerical and scientific validation status is reported explicitly; a saved result does not by itself certify model adequacy." });
    }
}
