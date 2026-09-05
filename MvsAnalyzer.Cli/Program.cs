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
        if (arguments.Length == 0 || args.Command == "help" || args.Flag("--help") || args.Flag("-h")) { Usage(); return 0; }
        try
        {
            return args.Command switch {
                "calibrate" => HeadlessRun.Calibrate(args), "analyze" or "analyse" => HeadlessRun.Analyze(args),
                "variance" => ScientificCommands.Variance(args), "estimation" => ScientificCommands.Estimation(args),
                "melsm" => ScientificCommands.Melsm(args), "benchmark" => BenchmarkCommandLine.Run(arguments),
                "state-check" => HeadlessRun.StateCheck(args), "version" => args.Flag("--json") ? ColabCompatibility.PrintCliManifest() : HeadlessRun.ShowVersions(), "env" => HeadlessRun.ShowEnvironment(),
                _ => throw new ArgumentException("Unknown command: " + args.Command) };
        }
        catch (OperationCanceledException) { Console.Error.WriteLine("Cancelled. Incomplete output may remain; only a completed manifest identifies a finished run."); return 1; }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
            if (System.Environment.GetEnvironmentVariable("MVS_DEBUG") == "1") Console.Error.WriteLine(error.StackTrace);
            return 1;
        }
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
  mvs version
  mvs env

Exit codes: 0 completed, 1 input/runtime error or cancellation, 2 a numerical diagnostic
or benchmark threshold was not satisfied (inspect the saved report).
No figures are rendered on Linux. Ctrl+C cancels cooperative calculations.
MELSM and variance components are model-based; review assumptions and diagnostics.");
    }
}
