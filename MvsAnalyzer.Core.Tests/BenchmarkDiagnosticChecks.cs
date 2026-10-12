using System.Globalization;
using System.Text.Json;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

internal static class BenchmarkDiagnosticChecks
{
    public static readonly (string Name, Action Run)[] All =
    {
        ("Benchmark diagnostic CSV preserves nulls and excludes failed partial decisions", Csv),
        ("Benchmark diagnostics round-trip and mark missing legacy checkpoints", RoundTrip),
        ("Benchmark instrumentation preserves seed draws and legacy decisions", Decisions),
        ("Benchmark replication tables reconstruct summaries across worker counts", Reconstruction),
        ("All-failed benchmark stability exports valid JSON nulls", Manifest)
    };

    private static void Assert(bool condition, string message)
    { if (!condition) throw new InvalidOperationException(message); }
    private static string[][] Rows(string csv) => csv.TrimEnd('\n').Split('\n').Skip(1).Select(line => line.Split(',')).ToArray();
    private static BenchmarkRunner.ReplicationOutcome Item(bool failed = false) => new()
    {
        Rejected = Enumerable.Repeat(true, BenchmarkProcedures.Count).ToArray(),
        Claimed = Enumerable.Repeat(true, BenchmarkProcedures.Count).ToArray(),
        Chosen = new int[BenchmarkProcedures.Count],
        MetricRejected = Enumerable.Repeat(true, AnalysisEngine.MetricKeys.Length).ToArray(),
        Failed = failed,
        Diagnostics = new BenchmarkRunner.ReplicationDiagnostics
        {
            RunSeed = 54, SeedStage = 1, SeedStream = 1,
            DerivedSeed = BenchmarkRandom.Derive(54, 1, 1, 0), CalibrationSeed = 123,
            PValues = new double?[] { 0.012345678901234567, null }.Concat(Enumerable.Repeat<double?>(.01, 10)).ToArray(),
            Calibration = Enumerable.Range(0, 12).Select(i => new BenchmarkRunner.CalibrationDiagnostic(i != 1, i == 1 ? null : 2.5, false, true, false)).ToArray()
        }
    };
    private static ConditionSummary Summary(BenchmarkRunner.ReplicationOutcome?[]? items, string stage = "primary") => new()
    {
        Condition = new(stage == "determinism" ? "determinism_replay" : "fixture", stage, "fixture", "normal", "none", 1, 0, items?.Length ?? 2, "synthetic"),
        Replications = items, Completed = 1, Failed = 1,
        Rejections = new int[8], Claims = new int[8], MetricRejections = new int[12],
        CompletedHalf = new int[2], MetricRejectionsHalf = new[] { new int[12], new int[12] },
        ChosenCounts = Enumerable.Range(0, 8).Select(_ => new int[13]).ToArray(),
        DecisionDigest = "fixture", FirstError = ""
    };
    private static BenchmarkOutcome Outcome(ConditionSummary summary, StabilitySummary? stability = null) => new()
    {
        Profile = new("diagnostic-test", "Test", "Test", "", "", 2, 1, 100, stability?.ReplicationRecords?.Length ?? 1, 2),
        Seed = 54, RunId = "fixture", StartedUtc = DateTime.UnixEpoch, FinishedUtc = DateTime.UnixEpoch,
        Conditions = new() { summary }, Stability = stability ?? new() { Tau = Array.Empty<double>(), Repeats = 0, TopOneMatches = 0, TopMetricCounts = new int[12], Failed = 1 },
        DeterminismFirst = "", DeterminismSecond = "", LockedPilotMetric = new(), Threads = 1,
        Notes = new(), Verdicts = new(), Overall = "pending"
    };

    private static void Csv()
    {
        var completed = Item(); completed.MetricRejected[1] = false;
        var failed = Item(true); failed.Error = "=failed,\"quoted\"\r\nline";
        var outcome = Outcome(Summary(new[] { completed, failed }));
        string csv = BenchmarkReport.ReplicationsCsv(outcome);
        Assert(csv.Contains("failed,retained,\"'=failed,\"\"quoted\"\"\r\nline\""), "Failure text not CSV/spreadsheet safe.");
        var procedures = Rows(BenchmarkReport.ReplicationProceduresCsv(outcome));
        Assert(procedures.Length == 16 && procedures.Take(8).All(r => r[5] == "true" && r[6] == "true"), "Completed decisions lost.");
        Assert(procedures.Skip(8).All(r => r.Skip(4).All(string.IsNullOrEmpty)), "Failed partial decisions leaked.");
        var metrics = Rows(BenchmarkReport.ReplicationMetricsCsv(outcome));
        Assert(metrics.Length == 24 && metrics[0][4] == "0.012345678901234567", "Raw p-value precision lost.");
        Assert(metrics[1][4] == "" && metrics[1][5] == "false" && metrics[1][6] == "false" && metrics[1][8] == "", "Unavailable value fabricated.");
        Assert(metrics.Skip(12).All(r => r[6] == "") && metrics[12][4] != "", "Failed partial raw values/decisions confused.");
        var early = Item(true); early.Diagnostics!.PValues = null; early.Diagnostics.Calibration = null; early.Diagnostics.CalibrationSeed = null;
        var earlyRows = Rows(BenchmarkReport.ReplicationMetricsCsv(Outcome(Summary(new[] { early }))));
        Assert(earlyRows.All(r => r.Skip(4).All(string.IsNullOrEmpty)), "Unreached step fabricated values.");
        var stability = new StabilitySummary
        {
            Tau = new[] { .5, .75 }, Repeats = 2, Failed = 1, TopOneMatches = 1, TopMetricCounts = new int[12],
            ReplicationRecords = new[]
            {
                new BenchmarkRunner.StabilityCheckpoint(.5, true, 0, false, "", 0, true),
                new BenchmarkRunner.StabilityCheckpoint(double.NaN, false, -1, true, "injected failure", null, true),
                new BenchmarkRunner.StabilityCheckpoint(.75, false, 0, false, "", 1, true)
            }
        };
        var stabilityOutcome = Outcome(Summary(new[] { completed }), stability);
        var splitRows = Rows(BenchmarkReport.StabilityReplicationsCsv(stabilityOutcome));
        Assert(splitRows.Length == 3 && splitRows[1][0] == "1" && splitRows[1][1] == "failed" && splitRows[1].Skip(4).All(string.IsNullOrEmpty), "Failed stability split lost or counted.");
        Assert(splitRows[2][0] == "2" && splitRows[2][7] == "false", "Stability split indices compressed.");
        var stabilityRestored = JsonSerializer.Deserialize<BenchmarkOutcome>(JsonSerializer.Serialize(stabilityOutcome, BackupSession.Json), BackupSession.Json)!;
        Assert(BenchmarkReport.StabilityReplicationsCsv(stabilityOutcome) == BenchmarkReport.StabilityReplicationsCsv(stabilityRestored), "Failed stability checkpoint round trip differs.");
    }

    private static void RoundTrip()
    {
        var outcome = Outcome(Summary(new[] { Item(), Item(true) }));
        string json = JsonSerializer.Serialize(outcome, BackupSession.Json);
        var restored = JsonSerializer.Deserialize<BenchmarkOutcome>(json, BackupSession.Json)!;
        Assert(BenchmarkReport.ReplicationsCsv(restored) == BenchmarkReport.ReplicationsCsv(outcome), "Replication checkpoint round trip differs.");
        Assert(BenchmarkReport.ReplicationMetricsCsv(restored) == BenchmarkReport.ReplicationMetricsCsv(outcome), "Metric checkpoint round trip differs.");
        Assert(BenchmarkReport.ReplicationProceduresCsv(restored) == BenchmarkReport.ReplicationProceduresCsv(outcome), "Procedure checkpoint round trip differs.");
        var legacyItem = JsonSerializer.Deserialize<BenchmarkRunner.ReplicationOutcome>("{\"Rejected\":[true],\"Claimed\":[true],\"Chosen\":[0],\"MetricRejected\":[true],\"Failed\":false,\"Error\":\"\"}", BackupSession.Json)!;
        Assert(legacyItem.Diagnostics == null, "Old checkpoint synthesized diagnostics.");
        var legacy = Outcome(Summary(new[] { legacyItem }));
        Assert(Rows(BenchmarkReport.ReplicationsCsv(legacy))[0][5] == "legacy_missing", "Missing marker lost.");
        Assert(Rows(BenchmarkReport.ReplicationMetricsCsv(legacy)).All(r => r[4] == "" && r[5] == "" && r.Skip(7).All(string.IsNullOrEmpty)), "Legacy diagnostic blanks fabricated.");
        var oldSummary = Outcome(Summary(null, "determinism"));
        var rows = Rows(BenchmarkReport.ReplicationsCsv(oldSummary));
        Assert(rows.Length == 4 && rows.All(r => r[4] == "unknown_legacy" && r[5] == "legacy_missing") && rows[2][1] == "replay-second", "Legacy summary/replay placeholders lost.");
        Assert(Rows(BenchmarkReport.ReplicationProceduresCsv(oldSummary)).All(r => r.Skip(4).All(string.IsNullOrEmpty)), "Old summary fabricated decisions.");
    }

    private sealed class Progress : IProgress<ProgressInfo> { public void Report(ProgressInfo value) { } }
    private static void Decisions()
    {
        var design = BenchmarkDatasets.Gait;
        var plan = new BenchmarkRunner.ConditionPlan { Condition = new("fixture", "primary", design.Id, "heavy", "none", 1, 0, 1, "synthetic"), Design = design, Mode = InjectionMode.None, Stage = 1, Stream = 1, LockedMetric = 0 };
        var actual = BenchmarkRunner.RunReplication(plan, 54, 0, 100, default);
        Assert(!actual.Failed, actual.Error);
        var random = new BenchmarkRandom(BenchmarkRandom.Derive(54, 1, 1, 0));
        var data = AnalysisEngine.Build(BenchmarkDatasets.Generate(design, InjectionMode.None, 1, 0, random), -1000000, 1000000, 6);
        double[] p = Enumerable.Range(0, 12).Select(m => AnalysisEngine.MannWhitneyP(
            data.Entities.Where(e => e.Group == data.GroupNames[0]).Select(e => e.Metrics[m]).Where(double.IsFinite).ToArray(),
            data.Entities.Where(e => e.Group == data.GroupNames[1]).Select(e => e.Metrics[m]).Where(double.IsFinite).ToArray())).ToArray();
        int seed = (int)(random.NextUInt64() % 50000000UL) + 1;
        Assert(actual.Diagnostics!.CalibrationSeed == seed && actual.Diagnostics.PValues!.Select(v => v ?? double.NaN).SequenceEqual(p), "Seed allocation or raw p changed.");
        var cal = AnalysisEngine.Calibrate(data, 100, BenchmarkProtocol.CalibrationEffect, seed, new Progress(), default,
            BenchmarkProtocol.CalibrationScenario, BenchmarkProtocol.CalibrationOutlierRate, BenchmarkProtocol.CalibrationMissingRate, BenchmarkProtocol.Alpha, AnalysisEngine.DefaultTracks);
        int strict = Enumerable.Range(0, 12).Where(i => cal[i].Applicable && double.IsFinite(cal[i].Score) && cal[i].PassesGateIn(SimulationScenarios.Location)).OrderByDescending(i => cal[i].Score).DefaultIfEmpty(-1).First();
        int lenient = Enumerable.Range(0, 12).Where(i => cal[i].Applicable && double.IsFinite(cal[i].Score)).OrderByDescending(i => cal[i].Score).DefaultIfEmpty(0).First();
        int smallest = Enumerable.Range(0, 12).OrderBy(i => p[i]).First();
        int[] chosen = { smallest, smallest, 0, 2, 0, strict, lenient, smallest };
        for (int i = 0; i < 8; i++)
        {
            bool claim = chosen[i] >= 0;
            bool rejection = claim && p[chosen[i]] < (i == 1 || i == 7 ? BenchmarkProtocol.Alpha / 12 : BenchmarkProtocol.Alpha);
            Assert(actual.Chosen[i] == chosen[i] && actual.Claimed[i] == claim && actual.Rejected[i] == rejection, "Legacy procedure decision changed: " + i);
        }
        var repeat = BenchmarkRunner.RunReplication(plan, 54, 0, 100, default);
        Assert(JsonSerializer.Serialize(actual, BackupSession.Json) == JsonSerializer.Serialize(repeat, BackupSession.Json), "Diagnostic replication not deterministic.");
        var invalid = new BenchmarkRunner.ConditionPlan { Condition = plan.Condition, Design = design with { EntitiesPerGroup = 0 }, Mode = plan.Mode, Stage = 1, Stream = 1, LockedMetric = 0 };
        var failure = BenchmarkRunner.RunReplication(invalid, 54, 0, 100, default);
        Assert(failure.Failed && failure.Error.Length > 0 && failure.Diagnostics != null && failure.Diagnostics.PValues == null, "Early generation/build failure not retained.");
    }

    private static void Reconstruction()
    {
        var profile = new BenchmarkProfile("diagnostic-test", "Test", "Test", "", "", 2, 1, 100, 1, 2);
        int previous = BenchmarkRunner.ThreadOverride;
        try
        {
            BenchmarkRunner.ThreadOverride = 1;
            var first = BenchmarkRunner.Run(profile, 54, "", false, null, default);
            BenchmarkRunner.ThreadOverride = 2;
            var second = BenchmarkRunner.Run(profile, 54, "", false, null, default);
            Assert(BenchmarkReport.ReplicationsCsv(first) == BenchmarkReport.ReplicationsCsv(second), "Worker count changed records.");
            Assert(BenchmarkReport.ReplicationMetricsCsv(first) == BenchmarkReport.ReplicationMetricsCsv(second), "Worker count changed metrics.");
            Assert(BenchmarkReport.ReplicationProceduresCsv(first) == BenchmarkReport.ReplicationProceduresCsv(second), "Worker count changed decisions.");
            foreach (var summary in first.Conditions)
            {
                var good = summary.Replications!.Where(r => r != null && !r.Failed).Select(r => r!).ToArray();
                Assert(good.Length == summary.Completed && summary.Replications!.Length - good.Length == summary.Failed, "Counts not reconstructible.");
                for (int p = 0; p < 8; p++)
                {
                    Assert(good.Count(r => r.Rejected[p]) == summary.Rejections[p] && good.Count(r => r.Claimed[p]) == summary.Claims[p], "Procedure aggregates differ.");
                    for (int m = 0; m < 13; m++) Assert(good.Count(r => (r.Chosen[p] < 0 ? 12 : r.Chosen[p]) == m) == summary.ChosenCounts[p][m], "Choice aggregate differs.");
                }
                for (int m = 0; m < 12; m++) Assert(good.Count(r => r.MetricRejected[m]) == summary.MetricRejections[m], "Metric aggregate differs.");
                for (int half = 0; half < 2; half++)
                {
                    var halfGood = summary.Replications!.Where((r, i) => i % 2 == half && r != null && !r.Failed).Select(r => r!).ToArray();
                    Assert(halfGood.Length == summary.CompletedHalf[half], "Half count differs.");
                    for (int m = 0; m < 12; m++) Assert(halfGood.Count(r => r.MetricRejected[m]) == summary.MetricRejectionsHalf[half][m], "Half metric count differs.");
                }
            }
            Assert(BenchmarkReport.StabilityReplicationsCsv(first) == BenchmarkReport.StabilityReplicationsCsv(second), "Worker count changed stability records.");
            var savedStability = JsonSerializer.Deserialize<StabilitySummary>(JsonSerializer.Serialize(first.Stability, BackupSession.Json), BackupSession.Json)!;
            Assert(savedStability.ReplicationRecords!.Length == profile.StabilityRepeats && savedStability.ReplicationRecords.All(r => r.DiagnosticsRetained), "Stability records lost in checkpoint.");
            var replay = first.Find("determinism_replay")!;
            Assert(first.DeterminismSecondSummary != null && JsonSerializer.Serialize(replay.Replications, BackupSession.Json) == JsonSerializer.Serialize(first.DeterminismSecondSummary.Replications, BackupSession.Json), "Second replay details not retained independently.");
        }
        finally { BenchmarkRunner.ThreadOverride = previous; }
    }

    public static void ExportFixtures(string folder)
    {
        Environment.SetEnvironmentVariable("MVS_DISABLE_BACKUPS", "1");
        var profile = new BenchmarkProfile("diagnostic-export", "Test", "Test", "", "", 2, 1, 100, 1, 2);
        int previous = BenchmarkRunner.ThreadOverride;
        BenchmarkOutcome outcome;
        try { BenchmarkRunner.ThreadOverride = 2; outcome = BenchmarkReport.RunAndWrite(profile, 54, Path.Combine(folder, "pipeline"), "", false, null, default).Outcome; }
        finally { BenchmarkRunner.ThreadOverride = previous; }
        // Deliberately marked injected fixture: prove failed partial data cannot inflate aggregates.
        var good = Item(); good.MetricRejected[1] = false;
        good.Rejected[BenchmarkProcedures.Bonferroni] = false;
        good.Rejected[BenchmarkProcedures.MvsTwoTrack] = false;
        good.Rejected[BenchmarkProcedures.MvsStrict] = false;
        good.Claimed[BenchmarkProcedures.MvsStrict] = false;
        good.Chosen[BenchmarkProcedures.MvsStrict] = -1;
        foreach (int i in new[] { BenchmarkProcedures.CherryPick, BenchmarkProcedures.Bonferroni, BenchmarkProcedures.MvsTwoTrack }) good.Chosen[i] = 2;
        var late = Item(true); late.Error = "Injected diagnostic fixture failure after partial decisions";
        late.Diagnostics = new BenchmarkRunner.ReplicationDiagnostics
        {
            RunSeed = 54, SeedStage = 1, SeedStream = 1, DerivedSeed = BenchmarkRandom.Derive(54, 1, 1, 1),
            CalibrationSeed = 123, PValues = good.Diagnostics!.PValues, Calibration = good.Diagnostics.Calibration
        };
        var early = Item(true); early.Error = "Injected diagnostic fixture failure before observed tests";
        early.Diagnostics = new BenchmarkRunner.ReplicationDiagnostics
        { RunSeed = 54, SeedStage = 1, SeedStream = 1, DerivedSeed = BenchmarkRandom.Derive(54, 1, 1, 2) };
        var choices = Enumerable.Range(0, 8).Select(p => Enumerable.Range(0, 13).Select(m => (good.Chosen[p] < 0 ? 12 : good.Chosen[p]) == m ? 1 : 0).ToArray()).ToArray();
        outcome.Conditions.Add(new ConditionSummary
        {
            Condition = new("injected_failure_fixture", "fixture", "fixture", "normal", "none", 1, 0, 3, "injected-test-only"),
            Replications = new[] { good, late, early }, Completed = 1, Failed = 2,
            Rejections = good.Rejected.Select(v => v ? 1 : 0).ToArray(), Claims = good.Claimed.Select(v => v ? 1 : 0).ToArray(),
            MetricRejections = good.MetricRejected.Select(v => v ? 1 : 0).ToArray(),
            CompletedHalf = new[] { 1, 0 }, MetricRejectionsHalf = new[] { good.MetricRejected.Select(v => v ? 1 : 0).ToArray(), new int[12] },
            ChosenCounts = choices, DecisionDigest = "injected-test-only", FirstError = late.Error
        });
        Directory.CreateDirectory(folder);
        var files = new Dictionary<string, string>
        {
            ["benchmark_replications.csv"] = BenchmarkReport.ReplicationsCsv(outcome),
            ["benchmark_replication_procedures.csv"] = BenchmarkReport.ReplicationProceduresCsv(outcome),
            ["benchmark_replication_metrics.csv"] = BenchmarkReport.ReplicationMetricsCsv(outcome),
            ["benchmark_summary.csv"] = BenchmarkReport.SummaryCsv(outcome),
            ["benchmark_metrics.csv"] = BenchmarkReport.MetricsCsv(outcome),
            ["benchmark_choices.csv"] = BenchmarkReport.ChoicesCsv(outcome),
            ["benchmark_stability.csv"] = BenchmarkReport.StabilityCsv(outcome),
            ["benchmark_stability_replications.csv"] = BenchmarkReport.StabilityReplicationsCsv(outcome),
            ["benchmark_manifest.json"] = BenchmarkReport.Manifest(outcome, new(), new())
        };
        foreach (var pair in files) File.WriteAllText(Path.Combine(folder, pair.Key), pair.Value);
    }

    private static void Manifest()
    {
        var legacyStability = Rows(BenchmarkReport.StabilityReplicationsCsv(Outcome(Summary(null))));
        Assert(legacyStability.Length == 1 && legacyStability[0][1] == "unknown_legacy" && legacyStability[0][2] == "legacy_missing", "Old stability summary fabricated repeat data.");
        using var json = JsonDocument.Parse(BenchmarkReport.Manifest(Outcome(Summary(null)), new(), new()));
        Assert(json.RootElement.GetProperty("stability").GetProperty("medianTau").ValueKind == JsonValueKind.Null, "Nonfinite stability not JSON null.");
        Assert(json.RootElement.GetProperty("diagnosticsVersion").GetString() == BenchmarkReport.DiagnosticsVersion, "Diagnostics identity absent.");
        Assert(json.RootElement.GetProperty("diagnosticsMissingReplications").GetInt32() == 2, "Missing legacy diagnostics not counted.");
    }
}
