using System.Text;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.Cli;

/// <summary>
/// The headless entry point. One executable, five commands, no window.
///
/// The benchmark subcommand hands straight over to the parser the desktop build already uses, so
/// there is exactly one implementation of the protocol and one place where its flags are defined.
/// A second copy would drift, and a benchmark whose flags mean different things on two machines is
/// not a benchmark.
/// </summary>
internal static class CliProgram
{
    private static int Main(string[] arguments)
    {
        try { Console.OutputEncoding = Encoding.UTF8; }
        catch (IOException) { }
        catch (System.Security.SecurityException) { }

        var args = new CliArguments(arguments);
        string command = args.Command;

        if (arguments.Length == 0 || command == "help" || args.Flag("--help") || args.Flag("-h"))
        {
            Usage();
            return 0;
        }

        try
        {
            switch (command)
            {
                case "calibrate":
                    return HeadlessRun.Calibrate(args);
                case "analyze":
                case "analyse":
                    return HeadlessRun.Analyze(args);
                case "benchmark":
                    return BenchmarkCommandLine.Run(arguments);
                case "env":
                    return HeadlessRun.ShowEnvironment();
                case "version":
                    return HeadlessRun.ShowVersions();
                default:
                    Console.Error.WriteLine("Unknown command: " + command);
                    Usage();
                    return 1;
            }
        }
        catch (ArgumentException error)
        {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
        catch (FileNotFoundException error)
        {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
        catch (InvalidDataException error)
        {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
        catch (OperationCanceledException)
        {
            Console.Error.WriteLine("Cancelled. Nothing was written.");
            return 1;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("Failed: " + error.Message);
            return 1;
        }
    }

    private static void Usage()
    {
        Console.WriteLine();
        Console.WriteLine("mvs - MVS Analyzer without a window   (" + RemoteJob.AppVersion + ")");
        Console.WriteLine();
        Console.WriteLine("  mvs calibrate --in <file.csv> --out <folder> [options]");
        Console.WriteLine("      Measures how each metric behaves on this dataset, in every track.");
        Console.WriteLine("      --repetitions <n>     simulations per metric (default 5000, minimum 100)");
        Console.WriteLine("      --seed <n>            the same seed reproduces the calibration exactly");
        Console.WriteLine("      --effect <x>          simulated effect size, for example 1.15");
        Console.WriteLine("      --scenario <id>       location | decrease | variability");
        Console.WriteLine("      --alpha <x>           significance level (default 0.05)");
        Console.WriteLine("      --outliers <x>        contamination rate used while calibrating");
        Console.WriteLine("      --missing <x>         missing data rate used while calibrating");
        Console.WriteLine("      --split               calibrate on one half of the entities, analyse the other");
        Console.WriteLine("      --job <job.json>      take every setting from a job file instead");
        Console.WriteLine();
        Console.WriteLine("  mvs analyze --in <file.csv> --calibration <folder> --out <folder> [options]");
        Console.WriteLine("      Applies a calibration to the data and writes the tables and the manifest.");
        Console.WriteLine("      --project <name>      recorded in the manifest");
        Console.WriteLine("      --margin <x>          equivalence margin (default 0.147)");
        Console.WriteLine("      --force               proceed even if the data no longer matches the calibration");
        Console.WriteLine();
        Console.WriteLine("  mvs benchmark --profile <id> --out <folder> [options]");
        Console.WriteLine("      Runs the pre-registered protocol against data whose truth is known.");
        Console.WriteLine("      --seed <n>            the same seed reproduces the run exactly");
        Console.WriteLine("      --threads <n>         workers to use (default: processors minus one)");
        Console.WriteLine("      --real-data <dir>     optional folder of CSV recordings for the plasmode stage");
        Console.WriteLine("      --lang <en|ru>        language of the report");
        Console.WriteLine("      --quiet               do not print progress");
        Console.WriteLine();
        Console.WriteLine("  mvs env        where this build runs and whether replay can be compared");
        Console.WriteLine("  mvs version    versions and frozen hashes");
        Console.WriteLine();
        Console.WriteLine("Figures are not drawn here. System.Drawing.Common does not draw on Linux, so a");
        Console.WriteLine("headless run writes every table, report and manifest, and the images can be made");
        Console.WriteLine("afterwards from the same folder on a Windows machine.");
        Console.WriteLine();
        Console.WriteLine("Exit codes: 0 done, 2 a benchmark threshold was missed, 1 error.");
        Console.WriteLine();
    }
}
