using System.IO.Compression;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;
internal static class BackupChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[] {
        ("Backup archives, integrity and previous snapshot", Archive), ("Saved units execute only once", CachedUnits),
        ("Calibration checkpoint replay matches uninterrupted run", Calibration), ("Analysis checkpoint replay matches uninterrupted run", Analysis),
        ("Estimation checkpoint replay matches uninterrupted run", Estimation), ("Optimizer resumes complete simplex", Optimizer),
        ("Benchmark resume preserves independent determinism passes", Benchmark), ("Variance bootstrap checkpoint replay", Variance)
    };
    private sealed class Reporter(Action<ProgressInfo>? report = null) : IProgress<ProgressInfo> { public void Report(ProgressInfo p) => report?.Invoke(p); }
    private static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
    private static void Rejected(Action action) { try { action(); } catch (Exception e) when (e is InvalidDataException or System.Text.Json.JsonException) { return; } throw new Exception("Unsafe backup accepted."); }
    private static void Isolated(Action<string> test)
    {
        string? old = Environment.GetEnvironmentVariable("MVS_BACKUP_DIR"), disabled = Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS");
        string folder = Path.Combine(Path.GetTempPath(), "mvs-backup-test-" + Guid.NewGuid().ToString("N"));
        Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", folder); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", null);
        try { test(folder); } finally { Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", old); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", disabled); if (Directory.Exists(folder)) Directory.Delete(folder, true); }
    }
    private static BackupDocument Latest(string folder, string kind) => Directory.GetFiles(folder, "*.mvsbackup").Where(f => !f.Contains(".previous."))
        .Select(f => BackupSession.Decode(File.ReadAllBytes(f))).Where(d => d.Request.Kind == kind && !d.CalculationComplete).OrderByDescending(d => d.SavedUtc).First();
    private static AnalysisData Data() => AnalysisEngine.Build(Enumerable.Range(0, 2).SelectMany(g => Enumerable.Range(0, 8)
        .SelectMany(e => Enumerable.Range(0, 6).Select(i => new Observation("G" + g + "E" + e, "G" + g, 100 + g * 3 + e * .7 + Math.Sin(i + e), i)))).ToList());
    private static void Archive() => Isolated(folder => {
        var request = new BackupRequest { Kind = "estimation", Estimation = new() };
        using (var b = BackupSession.Begin(request)) b.Put("one", new[] { 1d, double.NaN, double.PositiveInfinity });
        var restored = Latest(folder, "estimation"); Assert(restored.Units.ContainsKey("one"), "Unit absent.");
        Assert(Directory.GetFiles(folder, "*.previous.mvsbackup").Length == 1, "Previous snapshot absent.");
        Assert(BackupSession.ReadArchive(Path.Combine(folder, "MVS_Backups.zip")).Count == 2, "Flat ZIP cannot be read.");
        Rejected(() => BackupSession.Validate(restored with { Engine = "old" })); Rejected(() => BackupSession.Validate(restored with { Request = request with { Seed = 999 } }));
        byte[] bytes = BackupSession.Encode(restored);
        using (var stream = new MemoryStream()) {
            stream.Write(bytes); stream.Position = 0;
            using (var zip = new ZipArchive(stream, ZipArchiveMode.Update, true)) { zip.GetEntry("SHA256SUMS.txt")!.Delete(); using var w = new StreamWriter(zip.CreateEntry("SHA256SUMS.txt").Open()); w.Write("wrong"); }
            Rejected(() => BackupSession.Decode(stream.ToArray()));
        }
        string bad = Path.Combine(folder, "unsafe.zip"); using (var zip = ZipFile.Open(bad, ZipArchiveMode.Create)) using (var output = zip.CreateEntry("../escape.mvsbackup").Open()) output.Write(bytes);
        Rejected(() => BackupSession.ReadArchive(bad));
    });
    private static void CachedUnits() => Isolated(folder => {
        var r = new BackupRequest { Kind = "estimation", Estimation = new() }; int calls = 0;
        using (var b = BackupSession.Begin(r)) { b.Cached("a", () => ++calls); b.Cached("a", () => ++calls); }
        using (BackupSession.Restore(Latest(folder, "estimation"))) using (var b = BackupSession.Begin(r)) { Assert(b.Cached("a", () => ++calls) == 1, "Saved value changed."); b.Cached("b", () => ++calls); }
        Assert(calls == 2, "A completed unit was executed twice.");
    });
    private static List<CalibrationRow> Cal(AnalysisData d, IProgress<ProgressInfo> p, CancellationToken t) => AnalysisEngine.Calibrate(d, 100, 1.15, 54, p, t, tracks: AnalysisEngine.DefaultTracks);
    private static void Calibration() => Isolated(folder => {
        var d = Data(); using var stop = new CancellationTokenSource();
        try { Cal(d, new Reporter(p => { if (p.Fraction >= .2) stop.Cancel(); }), stop.Token); throw new Exception("Cancellation ignored."); } catch (OperationCanceledException) { }
        var partial = Latest(folder, "calibrate"); Assert(partial.Units.Count > 0, "No partial work.");
        List<CalibrationRow> actual; using (BackupSession.Restore(partial)) actual = Cal(d, new Reporter(), default);
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1"); Assert(ScientificJson.Serialize(actual) == ScientificJson.Serialize(Cal(d, new Reporter(), default)), "Calibration differs.");
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", null);
        var loaded = BackupRunner.Run(partial, folder, new Reporter(), default); Assert(loaded.State != null && loaded.Data != null, "Desktop restore lost state/data."); CalibrationPersistence.Validate(loaded.State!);
    });
    private static void Analysis() => Isolated(folder => {
        var d = Data(); var cal = AnalysisEngine.MetricKeys.Select(m => new CalibrationRow(m, .01, .8, 80)).ToList(); using var stop = new CancellationTokenSource();
        try { AnalysisEngine.Results(d, cal, new Reporter(p => { if (p.Fraction >= .25) stop.Cancel(); }), stop.Token); } catch (OperationCanceledException) { }
        List<ResultRow> actual; using (BackupSession.Restore(Latest(folder, "analyze"))) actual = AnalysisEngine.Results(d, cal, new Reporter(), default);
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1"); Assert(ScientificJson.Serialize(actual) == ScientificJson.Serialize(AnalysisEngine.Results(d, cal, new Reporter(), default)), "Analysis differs.");
    });
    private static void Estimation() => Isolated(folder => {
        var o = new EstimationOptions(Entities: 4, Measurements: 3, Repetitions: 100, BootstrapReplications: 99); using var stop = new CancellationTokenSource();
        try { EstimationStudy.Run(o, new Reporter(p => { if (p.Fraction >= .23) stop.Cancel(); }), stop.Token); } catch (OperationCanceledException) { }
        EstimationReport actual; using (BackupSession.Restore(Latest(folder, "estimation"))) actual = EstimationStudy.Run(o);
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1"); Assert(ScientificJson.Serialize(actual) == ScientificJson.Serialize(EstimationStudy.Run(o)), "Estimation differs.");
    });
    private static void Optimizer() => Isolated(folder => {
        var r = new BackupRequest { Kind = "melsm", Melsm = new() }; double[] start = { 8, -6 }, low = { -10, -10 }, high = { 10, 10 }; int calls = 0;
        double F(double[] p) => p[0] * p[0] + 2 * p[1] * p[1];
        try { using var b = BackupSession.Begin(r); NumericalMethods.Minimize(p => ++calls == 32 ? throw new OperationCanceledException() : F(p), start, low, high, backup: b, checkpointKey: "simplex"); } catch (OperationCanceledException) { }
        OptimizationResult actual; using (BackupSession.Restore(Latest(folder, "melsm"))) using (var b = BackupSession.Begin(r)) actual = NumericalMethods.Minimize(F, start, low, high, backup: b, checkpointKey: "simplex");
        Assert(ScientificJson.Serialize(actual) == ScientificJson.Serialize(NumericalMethods.Minimize(F, start, low, high)), "Simplex replay differs.");
    });
    private static void Benchmark() => Isolated(folder => {
        var profile = new BenchmarkProfile("checkpoint-test", "Test", "Тест", "", "", 2, 1, 100, 1, 2); using var stop = new CancellationTokenSource();
        int threads = BenchmarkRunner.ThreadOverride; BenchmarkRunner.ThreadOverride = 1;
        try {
            try { BenchmarkRunner.Run(profile, 54, "", false, new Reporter(p => { if (p.Fraction > .05) stop.Cancel(); }), stop.Token); } catch (OperationCanceledException) { }
            BenchmarkOutcome actual; using (BackupSession.Restore(Latest(folder, "benchmark"))) actual = BenchmarkRunner.Run(profile, 54, "", false, new Reporter(), default);
            var completed = Directory.GetFiles(folder, "*.mvsbackup").Where(f => !f.Contains(".previous.")).Select(f => BackupSession.Decode(File.ReadAllBytes(f))).First(d => d.CalculationComplete);
            Assert(completed.Units.ContainsKey("replication/replay-first/0") && completed.Units.ContainsKey("replication/replay-second/0"), "Replay shares a cache key.");
            Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1"); var expected = BenchmarkRunner.Run(profile, 54, "", false, new Reporter(), default);
            Assert(ScientificJson.Serialize(actual.Conditions) == ScientificJson.Serialize(expected.Conditions), "Benchmark differs."); Assert(ScientificJson.Serialize(actual.Stability) == ScientificJson.Serialize(expected.Stability), "Stability differs.");
        } finally { BenchmarkRunner.ThreadOverride = threads; }
    });
    private static void Variance() => Isolated(folder => {
        var data = Data(); using var stop = new CancellationTokenSource();
        try { VarianceAnalysis.Run(data, 100, 99, 1.3, 1.3, 54, .05, new Reporter(p => { if (p.Fraction >= .05) stop.Cancel(); }), stop.Token); } catch (OperationCanceledException) { }
        VarianceReport actual; using (BackupSession.Restore(Latest(folder, "variance"))) actual = VarianceAnalysis.Run(data, 100, 99, 1.3, 1.3, 54, .05);
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1"); Assert(ScientificJson.Serialize(actual) == ScientificJson.Serialize(VarianceAnalysis.Run(data, 100, 99, 1.3, 1.3, 54, .05)), "Variance differs.");
    });
}
