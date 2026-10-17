using System.Reflection;
using System.Text.Json;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

// Fixed engineering fixtures only: no calibrations, simulations or new benchmark evidence.
internal static class BenchmarkTauChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[]
    {
        ("Tau-b joint ties, extreme finite values and undefined ranks", Arithmetic),
        ("Tau-b agrees with independent pair-count oracle", Oracle),
        ("Benchmark stability identity and old request serialization are frozen", Identity),
        ("Benchmark cached legacy and corrected outcomes retain provenance", CachedResults),
        ("Benchmark cached splits preserve finite-tau aggregation and all records", CachedSplits),
        ("Benchmark mismatches reject before publication and cached return", RejectMixed),
        ("Fresh benchmark requests explicitly select corrected stability", Fresh)
    };
    private static void Assert(bool value, string reason) { if (!value) throw new Exception(reason); }
    private static void Near(double expected, double actual) => Assert(double.IsNaN(expected) ? double.IsNaN(actual) : Math.Abs(expected - actual) < 1e-14, $"Expected {expected}; actual {actual}");
    private static void Reject(Action action)
    {
        try { action(); } catch (Exception ex) when (ex is InvalidDataException or JsonException) { return; }
        throw new Exception("Incompatible benchmark provenance accepted.");
    }
    private static void Arithmetic()
    {
        foreach (double[] values in new[] { new[] { 1d, 1, 2 }, new[] { -double.MaxValue, 0, double.MaxValue }, new[] { 0d, double.Epsilon }, new[] { 0d, -0d, 1 } })
        {
            Near(1, BenchmarkMath.KendallTau(values, values));
            Near(-1, BenchmarkMath.KendallTau(values, values.Select(x => -x).ToArray()));
        }
        Near(2d / 3, BenchmarkMath.LegacyKendallTau(new[] { 1d, 1, 2 }, new[] { 1d, 1, 2 }));
        Near(0, BenchmarkMath.LegacyKendallTau(new[] { 1d, 1 }, new[] { 1d, 1 }));
        Near(-1, BenchmarkMath.LegacyKendallTau(new[] { 0d, double.Epsilon }, new[] { 0d, double.Epsilon }));
        Near(double.NaN, BenchmarkMath.LegacyKendallTau(new[] { -double.MaxValue, double.MaxValue }, new[] { -double.MaxValue, double.MaxValue }));
        foreach (double[] a in new[] { Array.Empty<double>(), new[] { 1d }, new[] { 1d, 1, 1 }, new[] { 1d, 2 } })
            Near(double.NaN, BenchmarkMath.KendallTau(a, new[] { 1d, 1, 1 }));
        foreach (double bad in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity })
        { Near(double.NaN, BenchmarkMath.KendallTau(new[] { bad, 1d }, new[] { 1d, 2 })); Near(double.NaN, BenchmarkMath.KendallTau(new[] { 1d, 2 }, new[] { 1d, bad })); }
        Near(1, BenchmarkStabilityMethod.Calculate(new[] { 1d, 1, 2 }, new[] { 1d, 1, 2 }, BenchmarkStabilityMethod.CurrentId));
        Near(2d / 3, BenchmarkStabilityMethod.Calculate(new[] { 1d, 1, 2 }, new[] { 1d, 1, 2 }, null));
    }
    private static void Oracle()
    {
        // Exhaust all ternary rank vectors of length four. Count margin ties independently.
        var vectors = Enumerable.Range(0, 81).Select(n => Enumerable.Range(0, 4).Select(i => (double)(n / (int)Math.Pow(3, i) % 3)).ToArray()).ToArray();
        foreach (var a in vectors) foreach (var b in vectors)
        {
            double tiesA = a.GroupBy(x => x).Sum(g => g.Count() * (g.Count() - 1) / 2);
            double tiesB = b.GroupBy(x => x).Sum(g => g.Count() * (g.Count() - 1) / 2);
            double numerator = 0;
            for (int i = 0; i < 4; i++) for (int j = i + 1; j < 4; j++) numerator += Math.Sign(a[i] - a[j]) * Math.Sign(b[i] - b[j]);
            double denominator = Math.Sqrt((6 - tiesA) * (6 - tiesB));
            Near(denominator == 0 ? double.NaN : numerator / denominator, BenchmarkMath.KendallTau(a, b));
        }
    }
    private static void Identity()
    {
        Assert(ScientificMath.Hash(BenchmarkStabilityMethod.CurrentSpecification) == BenchmarkStabilityMethod.CurrentHash, "Corrected method specification changed.");
        Assert(ScientificMath.Hash(BenchmarkStabilityMethod.LegacySpecification) == BenchmarkStabilityMethod.LegacyHash, "Compatibility specification changed.");
        Assert(BenchmarkProtocol.HashIsFrozen, "Protocol 1.2.0 changed.");
        Assert(BenchmarkStabilityMethod.ComparisonKey(null) != BenchmarkStabilityMethod.ComparisonKey(BenchmarkStabilityMethod.CurrentId), "Distinct methods share a comparison key.");
        Reject(() => BenchmarkStabilityMethod.ResolveId("unknown"));
        Reject(() => BenchmarkStabilityMethod.ValidateRequest(new BackupRequest { Kind = "analyze", BenchmarkStabilityMethod = BenchmarkStabilityMethod.CurrentId }));
        const string old = "{\"Kind\":\"benchmark\",\"Data\":null,\"Observations\":null,\"Calibration\":null,\"Repetitions\":0,\"ReferenceReplications\":0,\"Seed\":0,\"Effect\":1.15,\"SecondEffect\":1.3,\"Alpha\":0.05,\"Margin\":0.147,\"Outliers\":0.02,\"Missing\":0,\"Scenario\":\"location\",\"Tracks\":null,\"Estimation\":null,\"Melsm\":null,\"Benchmark\":null,\"RealData\":null,\"RealDataNotes\":null,\"Context\":null}";
        Assert(BackupSession.Pack(new BackupRequest { Kind = "benchmark" }) == old, "Legacy request bytes/hash changed.");
        Assert(BackupSession.Pack(new BackupRequest { Kind = "analyze" }) == old.Replace("benchmark", "analyze"), "Nonbenchmark serialization changed.");
        Assert(BackupSession.Pack(new BackupRequest { Kind = "benchmark", BenchmarkStabilityMethod = BenchmarkStabilityMethod.CurrentId }).StartsWith(old[..^1] + ",\"BenchmarkStabilityMethod\":"), "New marker was not appended.");
        var checkpoint = new BenchmarkRunner.StabilityCheckpoint(double.NaN, true, 3, false, "undefined_tau", 3, true, BenchmarkStabilityMethod.CurrentId);
        var restored = JsonSerializer.Deserialize<BenchmarkRunner.StabilityCheckpoint>(BackupSession.Pack(checkpoint), BackupSession.Json)!;
        Assert(restored == checkpoint, "Checkpoint undefined values/diagnostics/identity changed.");
        Assert(!BackupSession.Pack(checkpoint with { StabilityMethod = null }).Contains("StabilityMethod"), "Legacy checkpoint marker synthesized.");
    }
    private static BenchmarkOutcome Outcome(string? marker) => new()
    {
        Profile = BenchmarkProtocol.ProfileById("quick"), Seed = 54, RunId = "synthetic_tau_contract_only",
        StartedUtc = DateTime.UnixEpoch, FinishedUtc = DateTime.UnixEpoch, Conditions = new(),
        Stability = new() { Tau = new[] { .625 }, Repeats = 1, TopOneMatches = 1, TopMetricCounts = new int[12], Failed = 0,
            ReplicationRecords = new[] { new BenchmarkRunner.StabilityCheckpoint(.625, true, 0, false, "retained", 0, true, marker) } },
        DeterminismFirst = "synthetic", DeterminismSecond = "synthetic", LockedPilotMetric = new(), Threads = 0,
        Notes = new() { "Synthetic cached result. No scientific work executed." }, Verdicts = new(), Overall = "no-go", StabilityMethod = marker
    };
    private static BackupDocument Document(string? marker)
    {
        var outcome = Outcome(marker);
        var request = new BackupRequest { Kind = "benchmark", Benchmark = outcome.Profile, Seed = 54, RealData = new(), RealDataNotes = new(), BenchmarkStabilityMethod = marker };
        return new BackupDocument { Request = request, RequestHash = ScientificMath.Hash(BackupSession.Pack(request)), CalculationComplete = true,
            Units = new() { ["result"] = JsonSerializer.SerializeToElement(outcome, BackupSession.Json),
                ["stability/0"] = JsonSerializer.SerializeToElement(outcome.Stability.ReplicationRecords![0], BackupSession.Json) } };
    }
    private static void Isolated(Action<string> action)
    {
        string folder = Path.Combine(Path.GetTempPath(), "mvs-tau-contract-" + Guid.NewGuid().ToString("N"));
        string? old = Environment.GetEnvironmentVariable("MVS_BACKUP_DIR"), disabled = Environment.GetEnvironmentVariable("MVS_DISABLE_BACKUPS");
        Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", folder); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", null);
        try { action(folder); } finally { Environment.SetEnvironmentVariable("MVS_BACKUP_DIR", old); Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", disabled); if (Directory.Exists(folder)) Directory.Delete(folder, true); }
    }
    private static void CachedResults() => Isolated(folder =>
    {
        foreach (string? marker in new[] { null, BenchmarkStabilityMethod.CurrentId })
        {
            var document = BackupSession.Decode(BackupSession.Encode(Document(marker)));
            string saved = document.Units["result"].GetRawText();
            using (BackupSession.Restore(document))
            {
                var outcome = BenchmarkRunner.Run(document.Request.Benchmark!, 54, "", false, null, default);
                Assert(BackupSession.Pack(outcome) == saved, "Cached result recomputed or relabeled.");
                Assert(outcome.Stability.Tau[0] == .625 && outcome.Stability.ReplicationRecords![0].Error == "retained", "Cached values changed.");
            }
            Assert(document.Units.Count == 2 && document.Units["result"].GetRawText() == saved, "New work or cached mutation occurred.");
        }
    });
    private static void CachedSplits() => Isolated(folder =>
    {
        var runner = typeof(BenchmarkRunner);
        var counterType = runner.GetNestedType("WorkCounter", BindingFlags.NonPublic)!;
        var run = runner.GetMethod("RunStability", BindingFlags.NonPublic | BindingFlags.Static)!;
        foreach (string? marker in new[] { null, BenchmarkStabilityMethod.CurrentId })
        {
            var records = new[]
            {
                new BenchmarkRunner.StabilityCheckpoint(.625, true, 2, false, "retained finite", 2, true, marker),
                new BenchmarkRunner.StabilityCheckpoint(double.NaN, true, 4, false, "undefined_tau: zero rank variance", 4, true, marker),
                new BenchmarkRunner.StabilityCheckpoint(-.25, false, 1, false, "retained disagreement", 3, true, marker)
            };
            var document = Document(marker) with { CalculationComplete = false };
            document.Units.Clear();
            for (int i = 0; i < records.Length; i++) document.Units.Add("stability/" + i, JsonSerializer.SerializeToElement(records[i], BackupSession.Json));
            string requestBefore = BackupSession.Pack(document.Request), requestHashBefore = document.RequestHash;
            var unitsBefore = document.Units.ToDictionary(x => x.Key, x => x.Value.GetRawText());
            using (BackupSession.Restore(document))
            using (var backup = BackupSession.Begin(document.Request))
            {
                foreach (int threads in new[] { 1, 2 })
                {
                    var counter = Activator.CreateInstance(counterType, nonPublic: true)!;
                    counterType.GetProperty("Total")!.SetValue(counter, records.Length);
                    // Null design is intentional: a cache miss fails in StreamOf before Generate/Calibrate.
                    var summary = (StabilitySummary)run.Invoke(null, new object?[]
                        { null, 54UL, records.Length, 0, threads, counter, null, false, CancellationToken.None, backup, marker })!;
                    Assert(summary.Tau.SequenceEqual(new[] { .625, -.25 }), "Cached finite tau changed or undefined split included.");
                    Assert(summary.Repeats == 2 && summary.Failed == 1 && summary.TopOneMatches == 1 && summary.TopOneAgreement == .5,
                        "Finite-tau denominator/failed count/top-one policy changed.");
                    Assert(summary.TopMetricCounts.Sum() == 2 && summary.TopMetricCounts[1] == 1 && summary.TopMetricCounts[2] == 1 && summary.TopMetricCounts[4] == 0,
                        "Undefined split contributed to top-metric counts.");
                    Assert(summary.ReplicationRecords!.SequenceEqual(records), "Cached split values, diagnostics or identities were recomputed/relabeled.");
                    Assert((int)counterType.GetProperty("Done")!.GetValue(counter)! == records.Length, "Cached split progress omitted units.");
                }
            }
            Assert(BackupSession.Pack(document.Request) == requestBefore && document.RequestHash == requestHashBefore,
                "Cached split request bytes or hash changed.");
            Assert(document.Units.Count == unitsBefore.Count && document.Units.All(x => unitsBefore[x.Key] == x.Value.GetRawText()),
                "Cached split units were added or rewritten.");
        }
    });
    private static void RejectMixed() => Isolated(folder =>
    {
        foreach (string? marker in new[] { null, BenchmarkStabilityMethod.CurrentId })
        {
            string? other = marker is null ? BenchmarkStabilityMethod.CurrentId : null;
            foreach (string target in new[] { "unit", "result", "nested", "unknown" })
            {
                var doc = Document(marker);
                if (target == "unknown") { var r = doc.Request with { BenchmarkStabilityMethod = "future" }; doc = doc with { Request = r, RequestHash = ScientificMath.Hash(BackupSession.Pack(r)) }; }
                else if (target == "unit") doc.Units["stability/99"] = JsonSerializer.SerializeToElement(new BenchmarkRunner.StabilityCheckpoint(.9, false, 0, false, StabilityMethod: other), BackupSession.Json);
                else
                {
                    var result = Outcome(target == "result" ? other : marker);
                    if (target == "nested") result.Stability.ReplicationRecords![0] = result.Stability.ReplicationRecords[0] with { StabilityMethod = other };
                    doc.Units["result"] = JsonSerializer.SerializeToElement(result, BackupSession.Json);
                }
                string before = BackupSession.Pack(doc);
                Reject(() => BackupSession.Validate(doc)); Reject(() => BackupSession.Decode(BackupSession.Encode(doc))); Reject(() => { using var restore = BackupSession.Restore(doc); });
                Assert(BackupSession.Pack(doc) == before && !Directory.Exists(folder), "Rejected input mutated state or published backup.");
            }
            // Mutation after selection must be caught again before Begin and before cached return.
            var pending = Document(marker);
            using (BackupSession.Restore(pending))
            {
                pending.Units["stability/7"] = JsonSerializer.SerializeToElement(new BenchmarkRunner.StabilityCheckpoint(.1, false, 0, false, StabilityMethod: other), BackupSession.Json);
                string before = BackupSession.Pack(pending);
                Reject(() => BenchmarkRunner.Run(pending.Request.Benchmark!, 54, "", false, null, default));
                Assert(BackupSession.Pack(pending) == before && ReferenceEquals(BackupSession.Pending, pending) && !Directory.Exists(folder), "Pre-Begin rejection consumed or mutated pending state.");
            }
        }
    });
    private static void Fresh() => Isolated(folder =>
    {
        using var stop = new CancellationTokenSource(); stop.Cancel();
        try { BenchmarkRunner.Run(BenchmarkProtocol.ProfileById("quick"), 54, "", false, null, stop.Token); throw new Exception("Cancellation ignored."); }
        catch (OperationCanceledException) { }
        var doc = Directory.GetFiles(folder, "*.mvsbackup").Where(x => !x.Contains(".previous.")).Select(x => BackupSession.Decode(File.ReadAllBytes(x))).Single();
        Assert(doc.Request.BenchmarkStabilityMethod == BenchmarkStabilityMethod.CurrentId && doc.Units.Count == 0, "Fresh request lacked corrected method or performed scientific work.");
    });
}
