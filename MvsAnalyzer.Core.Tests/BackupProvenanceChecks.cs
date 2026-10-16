using System.Text.Json;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

// Bounded arithmetic fixture: no random input, optimizer iterations, or user backups.
internal static class BackupProvenanceChecks
{
    internal static IEnumerable<(string Name, Action Run)> All
    {
        get
        {
            foreach (string history in new[] { "foreign", "mixed", "reverse", "empty", "current", "current_repeated" })
            {
                string h = history;
                yield return ($"Restored {h} provenance reevaluates only when required", () => Direct(h));
                foreach (bool late in new[] { false, true })
                {
                    bool l = late;
                    yield return ($"Restored {h} provenance survives {(l ? "late failure" : "Begin publication")} and repeated disk reload", () => Restart(h, l));
                }
            }
            foreach (bool cancel in new[] { false, true })
            {
                bool c = cancel;
                yield return ($"Reevaluation {(c ? "cancellation" : "exception")} cannot finish or cleanse unknown provenance", () => Interrupted(c));
            }
            foreach (string history in new[] { "foreign", "empty", "current" })
            {
                string h = history;
                yield return ($"Converged {h} restored simplex retains exact result", () => Converged(h));
            }
            yield return ("Precancelled optimizer reevaluates then propagates cancellation", TokenCancellation);
            yield return ("Fresh session records current environment", Fresh);
        }
    }
    internal static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
    internal static BackupDocument Fixture(string history)
    {
        var request = new BackupRequest { Kind = "estimation", Estimation = new() };
        var d = new BackupDocument { Request = request, RequestHash = ScientificMath.Hash(BackupSession.Pack(request)), SavedUtc = new DateTime(2020, 1, 2, 3, 4, 5, DateTimeKind.Utc) };
        if (history is "foreign" or "mixed") d.Environments.Add("owned-foreign-runtime");
        if (history is "current" or "current_repeated" or "mixed" or "reverse") d.Environments.Add(BenchmarkEnvironment.Hash);
        if (history == "reverse") d.Environments.Add("owned-foreign-runtime");
        if (history == "current_repeated") d.Environments.Add(BenchmarkEnvironment.Hash); // all-current, not just one entry
        d.Units["simplex"] = JsonSerializer.SerializeToElement(new NumericalMethods.SimplexCheckpoint(new[] { new[] { 1d }, new[] { 2d } }, history.StartsWith("current", StringComparison.Ordinal) ? new[] { 1d, 4d } : new[] { -999d, -998d }, 0), BackupSession.Json);
        return d;
    }
    internal static BackupDocument Load(string folder) => BackupSession.Decode(File.ReadAllBytes(Directory.GetFiles(folder, "*.mvsbackup").Single(p => !p.EndsWith(".previous.mvsbackup", StringComparison.Ordinal))));
    internal static OptimizationResult Minimize(BackupSession b, Func<double[], double> f) => NumericalMethods.Minimize(f, new[] { 1d }, new[] { -10d }, new[] { 10d }, maximumIterations: 0, backup: b, checkpointKey: "simplex");
    internal static (int Calls, OptimizationResult Result, bool Changed) Evaluate(BackupDocument d)
    {
        using (BackupSession.Restore(d)) using (var b = BackupSession.Begin(d.Request))
        {
            int calls = 0; var result = Minimize(b, x => { calls++; return x[0] * x[0]; });
            return (calls, result, b.EnvironmentChanged);
        }
    }
    private static void Verify((int Calls, OptimizationResult Result, bool Changed) actual, string history)
    {
        bool changed = !history.StartsWith("current", StringComparison.Ordinal);
        Assert(actual.Changed == changed, "Environment-change classification differs.");
        Assert(actual.Calls == (changed ? 2 : 0), "Unexpected objective-call count.");
        Assert(actual.Result.Value == 1d, "Unexpected restored objective value.");
        Assert(actual.Result.Parameters.SequenceEqual(new[] { 1d }) && actual.Result.Iterations == 0 && !actual.Result.Converged && !actual.Result.AtBoundary, "Exact optimizer result differs.");
    }
    private static void Isolated(Action<string> test)
    {
        string root = Path.Combine(Path.GetTempPath(), "mvs-provenance-" + Guid.NewGuid().ToString("N"));
        string? old = Environment.GetEnvironmentVariable("MVS_BACKUP_DIR"), disabled = Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS");
        Directory.CreateDirectory(root);
        try { Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", root); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", null); test(root); }
        finally { Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", old); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", disabled); Directory.Delete(root, true); }
    }
    internal static void PublishWithoutEvaluation(BackupDocument d, string root, bool late)
    {
        string obstruction = Path.Combine(root, "MVS_Backups.zip");
        if (late) Directory.CreateDirectory(obstruction);
        string original = BackupSession.Pack(d);
        using (BackupSession.Restore(d))
        {
            if (!late) { using var b = BackupSession.Begin(d.Request); }
            else
            {
                BackupPublicationFault.ExpectDirectoryCollision(() => { using var b = BackupSession.Begin(d.Request); }, obstruction);
                Assert(ReferenceEquals(BackupSession.Pending, d) && BackupSession.Pack(d) == original, "Failed Begin changed pending document.");
            }
        }
        Assert(Directory.GetFiles(root, "*.mvsbackup").Length > 0, "No partial disk publication.");
        if (late) Directory.Delete(obstruction); // only the empty directory owned by this fixture
    }
    private static void Direct(string history) => Isolated(root => Verify(Evaluate(Fixture(history)), history));
    private static void Restart(string history, bool late) => Isolated(root => {
        var source = Fixture(history); PublishWithoutEvaluation(source, root, late);
        for (int pass = 0; pass < 3; pass++)
        {
            var disk = Load(root);
            Assert(disk.Id == source.Id && !disk.CalculationComplete && !disk.Units.ContainsKey("result"), "Publication changed identity or completed calculation.");
            if (history == "empty") Assert(disk.Environments.Count == 0, "Unknown provenance was converted to current provenance.");
            Verify(Evaluate(disk), history);
        }
    });
    private static void Interrupted(bool cancel) => Isolated(root => {
        foreach (string history in new[] { "empty", "foreign" })
        {
            // Keep only this iteration's owned fixture.
            foreach (string file in Directory.GetFiles(root)) File.Delete(file);
            var d = Fixture(history); int calls = 0; bool thrown = false;
            try
            {
                using (BackupSession.Restore(d)) using (var b = BackupSession.Begin(d.Request))
                {
                    var result = Minimize(b, x => { calls++; if (calls == 2) { if (cancel) throw new OperationCanceledException("owned cancellation"); throw new ArithmeticException("owned objective failure"); } return x[0] * x[0]; });
                    b.Finish(result); // unreachable if reevaluation aborts
                }
            }
            catch (OperationCanceledException) when (cancel) { thrown = true; }
            catch (ArithmeticException) when (!cancel) { thrown = true; }
            Assert(thrown && calls == 2, "Objective interruption did not propagate at second reevaluation.");
            var disk = Load(root);
            Assert(!disk.CalculationComplete && !disk.Units.ContainsKey("result"), "Interrupted reevaluation falsely finished.");
            var checkpoint = disk.Units["simplex"].Deserialize<NumericalMethods.SimplexCheckpoint>(BackupSession.Json)!;
            Assert(checkpoint.Values.SequenceEqual(new[] { -999d, -998d }), "Partial reevaluation contaminated stored values.");
            Verify(Evaluate(disk), history);
        }
    });
    private static void Converged(string history) => Isolated(root => {
        var d = Fixture(history);
        d.Units["simplex"] = JsonSerializer.SerializeToElement(new NumericalMethods.SimplexCheckpoint(new[] { new[] { 1d }, new[] { 1d } }, history == "current" ? new[] { 1d, 1d } : new[] { -999d, -998d }, 0), BackupSession.Json);
        using (BackupSession.Restore(d)) using (var b = BackupSession.Begin(d.Request)) {
            int calls = 0;
            var result = NumericalMethods.Minimize(x => { calls++; return x[0] * x[0]; }, new[] { 1d }, new[] { -10d }, new[] { 10d }, maximumIterations: 1, backup: b, checkpointKey: "simplex");
            Assert(calls == (history == "current" ? 0 : 2) && result.Value == 1d && result.Converged && result.Iterations == 0 && !result.AtBoundary && result.Parameters.SequenceEqual(new[] { 1d }), "Converged restore result or call count differs.");
        }
    });
    private static void TokenCancellation() => Isolated(root => {
        var d = Fixture("foreign"); int calls = 0; bool thrown = false;
        using var stop = new CancellationTokenSource(); stop.Cancel();
        try {
            using (BackupSession.Restore(d)) using (var b = BackupSession.Begin(d.Request)) {
                var result = NumericalMethods.Minimize(x => { calls++; return x[0] * x[0]; }, new[] { 1d }, new[] { -10d }, new[] { 10d }, maximumIterations: 1, token: stop.Token, backup: b, checkpointKey: "simplex");
                b.Finish(result);
            }
        } catch (OperationCanceledException) { thrown = true; }
        Assert(thrown && calls == 2, "Precancelled token did not propagate after reevaluation.");
        var disk = Load(root); Assert(!disk.CalculationComplete && !disk.Units.ContainsKey("result"), "Cancelled calculation was finished.");
    });
    private static void Fresh() => Isolated(root => {
        using (var b = BackupSession.Begin(Fixture("empty").Request)) Assert(!b.WasRestored && !b.EnvironmentChanged, "Fresh session classified as restore.");
        Assert(Load(root).Environments.SequenceEqual(new[] { BenchmarkEnvironment.Hash }), "Fresh environment was not recorded.");
    });
}
