using System.Globalization;
using System.Text;
using System.Runtime.InteropServices;

namespace MvsAnalyzer.Benchmarking;

/// <summary>
/// The headless entry point. A benchmark that can only be started by clicking a button in a window
/// cannot be run by a reviewer on a build server, so the same protocol is reachable from the command
/// line. Argument parsing is written out by hand on purpose: adding a parser package would put a
/// version to babysit into a program that has deliberately kept its dependency list empty.
/// </summary>
internal static class BenchmarkCommandLine
{
    private const int AttachParentProcess = -1;

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AttachConsole(int processId);

    public static bool Handles(string[] args)
    {
        foreach (string argument in args)
            if (string.Equals(argument, "--benchmark", StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    public static int Run(string[] args)
    {
        // There is no parent console to attach to outside Windows, and the P/Invoke would only
        // throw to be swallowed. Asking first says why the call is skipped.
        if (OperatingSystem.IsWindows())
        {
            try { AttachConsole(AttachParentProcess); }
            catch (EntryPointNotFoundException) { }
            catch (DllNotFoundException) { }
        }
        // The attached console inherits the OEM code page, which turned every Russian
        // --lang ru line into question marks. Failures here are cosmetic, never fatal.
        try { Console.OutputEncoding = Encoding.UTF8; }
        catch (IOException) { }
        catch (System.Security.SecurityException) { }

        if (Flag(args, "--help") || Flag(args, "-h"))
        {
            PrintUsage();
            return 0;
        }

        try
        {
            BenchmarkOptions options = BenchmarkOptions.Load();

            string profileId = Value(args, "--profile") ?? options.ProfileId;
            BenchmarkProfile profile = BenchmarkProtocol.ProfileById(profileId);

            string? seedText = Value(args, "--seed");
            int seed = options.Seed;
            if (seedText != null && !int.TryParse(seedText, NumberStyles.Integer, CultureInfo.InvariantCulture, out seed))
            {
                Console.Error.WriteLine("The seed must be a whole number.");
                return 1;
            }
            if (seed <= 0) seed = 20260904;

            string output = Value(args, "--out") ?? options.OutputFolder;
            if (string.IsNullOrWhiteSpace(output))
            {
                Console.Error.WriteLine("Pass --out <folder> to say where the results should be written.");
                return 1;
            }

            string realData = Value(args, "--real-data") ?? options.RealDataFolder;
            bool russian = string.Equals(Value(args, "--lang"), "ru", StringComparison.OrdinalIgnoreCase);
            bool quiet = Flag(args, "--quiet");

            int threads = 0;
            string? threadText = Value(args, "--threads");
            if (threadText != null &&
                (!int.TryParse(threadText, NumberStyles.Integer, CultureInfo.InvariantCulture, out threads) || threads < 1))
            {
                Console.Error.WriteLine("The thread count must be a whole number of at least 1.");
                return 1;
            }
            BenchmarkRunner.ThreadOverride = threads;

            Console.WriteLine();
            Console.WriteLine("MVS benchmark " + BenchmarkProtocol.Version);
            Console.WriteLine("  protocol hash   " + BenchmarkProtocol.Hash);
            Console.WriteLine("  protocol frozen " + (BenchmarkProtocol.HashIsFrozen ? "yes" : "NO - results are not comparable"));
            Console.WriteLine("  profile         " + profile.Id + "  (" + profile.Estimate + ")");
            Console.WriteLine("  seed            " + seed.ToString(CultureInfo.InvariantCulture));
            Console.WriteLine("  output          " + output);
            Console.WriteLine("  threads         " + (threads > 0 ? threads.ToString(CultureInfo.InvariantCulture) : "auto"));
            Console.WriteLine("  environment     " + BenchmarkEnvironment.Describe());
            Console.WriteLine("  environment id  " + BenchmarkEnvironment.ShortHash + "   (replay is bit-identical within one environment)");
            if (!string.IsNullOrWhiteSpace(realData)) Console.WriteLine("  real data       " + realData);
            Console.WriteLine();

            using var cancellation = new CancellationTokenSource();
            ConsoleCancelEventHandler handler = (_, eventArgs) =>
            {
                eventArgs.Cancel = true;
                cancellation.Cancel();
                Console.WriteLine("Stopping after the current repetition...");
            };
            Console.CancelKeyPress += handler;

            IProgress<ProgressInfo>? progress = quiet ? null : new ConsoleProgress();
            BenchmarkReportResult report;
            try
            {
                report = BenchmarkReport.RunAndWrite(profile, seed, output, realData, russian, progress, cancellation.Token);
            }
            finally
            {
                Console.CancelKeyPress -= handler;
            }

            BenchmarkOutcome outcome = report.Outcome;
            Console.WriteLine();
            Console.WriteLine("Done in " + ((int)outcome.Duration.TotalSeconds).ToString(CultureInfo.InvariantCulture) + " s.");
            Console.WriteLine("  " + report.Folder);
            Console.WriteLine("  " + report.Figures.Count.ToString(CultureInfo.InvariantCulture) + " figures written");
            Console.WriteLine();

            ConditionSummary? primary = outcome.Find("primary_null");
            if (primary != null)
            {
                Console.WriteLine("False discoveries when there is nothing to find:");
                for (int procedure = 0; procedure < BenchmarkProcedures.Count; procedure++)
                    Console.WriteLine("  " + BenchmarkProcedures.Ids[procedure].PadRight(16) +
                        BenchmarkRunner.Pct(primary.Rate(procedure)));
                Console.WriteLine();
            }

            foreach (HypothesisVerdict verdict in outcome.Verdicts)
                Console.WriteLine("  " + verdict.Id.PadRight(4) + verdict.Result.ToUpperInvariant().PadRight(14) + verdict.Observed);
            Console.WriteLine();
            Console.WriteLine("Overall: " + outcome.Overall.ToUpperInvariant());

            foreach (string note in outcome.Notes) Console.WriteLine("note: " + note);

            return outcome.Overall == "no-go" ? 2 : 0;
        }
        catch (OperationCanceledException)
        {
            Console.Error.WriteLine("Cancelled. Nothing was written.");
            return 1;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("Benchmark failed: " + error.Message);
            return 1;
        }
    }

    private static void PrintUsage()
    {
        Console.WriteLine();
        Console.WriteLine("MVS_Analyzer.exe --benchmark [options]");
        Console.WriteLine();
        Console.WriteLine("  --profile <id>     " + Ids() + "  (default: quick)");
        Console.WriteLine("  --seed <number>    random seed; the same seed reproduces the run exactly");
        Console.WriteLine("  --out <folder>     where to write the results folder");
        Console.WriteLine("  --real-data <dir>  optional folder of CSV recordings for the plasmode stage");
        Console.WriteLine("  --lang <en|ru>     language of the report and the figures");
        Console.WriteLine("  --threads <n>      workers to use; default is processors minus one");
        Console.WriteLine("  --quiet            do not print progress");
        Console.WriteLine();
        Console.WriteLine("Exit codes: 0 met or inconclusive, 2 at least one threshold missed, 1 error.");
        Console.WriteLine();
    }

    private static string Ids()
    {
        var ids = new List<string>();
        foreach (BenchmarkProfile profile in BenchmarkProtocol.Profiles) ids.Add(profile.Id);
        return string.Join(" | ", ids);
    }

    private static bool Flag(string[] args, string name)
    {
        foreach (string argument in args)
            if (string.Equals(argument, name, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    private static string? Value(string[] args, string name)
    {
        for (int i = 0; i < args.Length; i++)
        {
            if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
                return i + 1 < args.Length ? args[i + 1] : null;
            if (args[i].StartsWith(name + "=", StringComparison.OrdinalIgnoreCase))
                return args[i].Substring(name.Length + 1);
        }
        return null;
    }

    private sealed class ConsoleProgress : IProgress<ProgressInfo>
    {
        private readonly object gate = new();
        private int lastPrinted = -1;

        public void Report(ProgressInfo value)
        {
            int percent = (int)Math.Round(Math.Clamp(value.Fraction, 0, 1) * 100);
            lock (gate)
            {
                if (percent <= lastPrinted && percent < 100) return;
                lastPrinted = percent;
                Console.WriteLine("  " + percent.ToString(CultureInfo.InvariantCulture).PadLeft(3) + "%  " +
                    value.Action + (string.IsNullOrEmpty(value.Details) ? "" : "  -  " + value.Details));
            }
        }
    }
}
