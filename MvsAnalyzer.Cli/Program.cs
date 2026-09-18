using System.Text;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.Cli;

internal static class CliProgram
{
    private static int Main(string[] arguments)
    {
        try { Console.OutputEncoding = Encoding.UTF8; } catch (IOException) { }
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; CliCancellation.Source.Cancel(); };
        var args = new CliArguments(arguments);
        bool machine = args.Flag("--json");
        bool quiet = args.Flag("--quiet");
        CliMachineContext.Reset(machine, quiet);
        TextWriter originalOut = Console.Out;

        if (arguments.Length == 0 || args.Command == "help" || args.Flag("--help") || args.Flag("-h")) { Usage(); return 0; }
        if (args.Command.Length == 0 && args.Flag("--version"))
        {
            if (machine) Console.SetOut(Console.Error);
            int code = machine ? 0 : HeadlessRun.ShowVersions();
            if (machine) { Console.SetOut(originalOut); CliMachineProtocol.Write(originalOut, "version", code); }
            return code;
        }

        if (machine) Console.SetOut(Console.Error);
        try
        {
            int code = args.Command switch {
                "resume" => Resume(args),
                "calibrate" => HeadlessRun.Calibrate(args), "analyze" or "analyse" => HeadlessRun.Analyze(args),
                "variance" => ScientificCommands.Variance(args), "estimation" => ScientificCommands.Estimation(args),
                "melsm" => ScientificCommands.Melsm(args), "benchmark" => RunBenchmark(arguments),
                "state-check" => HeadlessRun.StateCheck(args), "version" => machine ? 0 : HeadlessRun.ShowVersions(), "env" => HeadlessRun.ShowEnvironment(),
                _ => throw new ArgumentException("Unknown command: " + args.Command) };
            if (machine) { Console.SetOut(originalOut); CliMachineProtocol.Write(originalOut, args.Command, code); }
            return code;
        }
        catch (OperationCanceledException error)
        {
            Console.Error.WriteLine("Cancelled. Incomplete output may remain; only a completed manifest identifies a finished run.");
            if (machine) { Console.SetOut(originalOut); CliMachineProtocol.Write(originalOut, args.Command, 1, error); }
            return 1;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
            if (System.Environment.GetEnvironmentVariable("MVS_DEBUG") == "1") Console.Error.WriteLine(error.StackTrace);
            if (machine) { Console.SetOut(originalOut); CliMachineProtocol.Write(originalOut, args.Command, 1, error); }
            return 1;
        }
        finally
        {
            if (machine) Console.SetOut(originalOut);
        }
    }

    private static int RunBenchmark(string[] arguments)
    {
        int code = BenchmarkCommandLine.Run(arguments, folder => CliMachineContext.RecordOutput(folder));
        if (code == 2) CliMachineContext.Diagnostic("warning", "benchmark_threshold", "Benchmark completed but at least one threshold was not satisfied; inspect the benchmark report.");
        return code;
    }
    private static int Resume(CliArguments args)
    {
        args.Validate(new[] { "--in", "--out", "--id" });
        var backups = BackupSession.ReadArchive(args.Require("--in"));
        if (args.Value("--id") is string id) backups = backups.Where(b => b.Id == id).OrderByDescending(b => b.SavedUtc).Take(1).ToList();
        else backups = backups.GroupBy(b => b.Id).Select(g => g.OrderByDescending(b => b.SavedUtc).First()).ToList();
        if (backups.Count != 1) throw new ArgumentException("Choose a backup in MVS Data or pass --id. Available: " + string.Join(", ", backups.Select(b => b.Id + " (" + b.Request.Kind + ")")));
        var result = BackupRunner.Run(backups[0], args.Require("--out"), new CliProgress(), CliCancellation.Token);
        CliMachineContext.RecordOutput(result.Folder);
        if (result.ExitCode == 2) CliMachineContext.Diagnostic("warning", "scientific_diagnostic", "Resumed run completed with a scientific/numerical diagnostic; inspect the saved report.");
        Console.WriteLine("Resumed result saved: " + result.Folder); return result.ExitCode;
    }
    private static void Usage()
    {
        Console.WriteLine("MVS Analyzer " + ReleaseInfo.Version + " | scientific engine " + ReleaseInfo.EngineVersion);
        Console.WriteLine(@"
Summary-metric workflow (independent groups):
  mvs calibrate --in data.csv --out calibration [--repetitions 5000] [--seed 20260719]
      [--scenario location|decrease|variability|heterogeneity] [--effect 1.15]
      [--alpha .05] [--outliers .02] [--missing 0] [--split] [--margin .147]
      [--min-measurements 6] [--min-value -1000000] [--max-value 1000000]
      [--job job.json] [--overwrite] [--allow-group-scoped-ids]
  mvs analyze --in data.csv --calibration calibration --out analysis [--project name]
      [--description text] [--force] [--allow-group-scoped-ids]
  Statistical settings are frozen in calibration; analyze does not accept overrides.
  --force only allows different input bytes, never incompatible methods or schemas.
  Defaults are independent of saved desktop settings; --local-settings opts in explicitly.

Separate Gaussian within/between variance components:
  mvs variance --in data.csv --out variance [--repetitions 200] [--bootstrap 199]
      [--within-effect 1.3] [--between-effect 1.3] [--alpha .05] [--seed 20260719]
      [--min-measurements 3] [--overwrite] [--allow-group-scoped-ids]
  Effects multiply SD, not variance. Evaluation and reference simulations are independent.
  This model can be expensive; a small budget is not a publication-quality validation.

Known-truth estimation study (not the unknown bias of an uploaded CSV):
  mvs estimation --out estimation --target mean|median|geometric_mean|within_variance|between_variance
      [--shape normal|lognormal|student_t5] [--entities 20] [--measurements 12]
      [--repetitions 500] [--bootstrap 199] [--seed 20260719]
      [--location 100] [--within-sd 10] [--between-sd 5] [--overwrite]
  Lognormal defaults are location=1, within-sd=.3, between-sd=.2, all on the log scale.
  Variance targets currently support Gaussian data only.

Optional experimental mixed-effects location-scale model:
  mvs melsm --in repeated.csv --out melsm [--mean-time] [--scale-time] [--correlate]
      [--no-random-scale] [--quadrature 15] [--max-iterations 4000] [--overwrite]
      [--include-entity-ids]
  Entity IDs are GLOBAL in this mode; conditions can change within an entity.
  Time effects require a real integer sequence/timepoint column. No AR(1) or random slopes.

Benchmark and diagnostics:
  mvs benchmark --profile quick|standard|full --out folder [--seed N] [--threads N]
  mvs version [--json]
  mvs --version
  mvs env
  mvs resume --in MVS_Backups.zip --out folder [--id backup-id]
  Automatic checkpoints: MVS_BACKUP_DIR, default local MVS_Analyzer/MVS_Backups.

Exit codes: 0 completed, 1 input/runtime error or cancellation, 2 a numerical diagnostic
or benchmark threshold was not satisfied (inspect the saved report).
Global automation options: --json emits one versioned JSON object on stdout; --quiet suppresses progress.
No figures are rendered on Linux. Ctrl+C cancels cooperative calculations.
MELSM and variance components are model-based; review assumptions and diagnostics.");
    }
}
