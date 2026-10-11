using System.Text.Json;
using MvsAnalyzer;
using MvsAnalyzer.Benchmarking;

internal static class AvailabilityChecks
{
    public static readonly (string Name, Action Run)[] All = {
        ("Unavailable calibration cannot veto an observed rank test", CalibrationIndependence),
        ("Metric availability counts entities and explains individual exclusions", MetricExclusions),
        ("Four usable entities is the observed software boundary", MinimumBoundary),
        ("Metric availability survives JSON and CSV export", AvailabilityExport)
    };
    private sealed class Reporter : IProgress<ProgressInfo> { public void Report(ProgressInfo info) { } }
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static AnalysisData Data(double[] first, double[] second)
    {
        var rows = new List<Observation>();
        foreach (var (name, centres) in new[] { ("A", first), ("B", second) })
            for (int entity = 0; entity < centres.Length; entity++)
                for (int sequence = 1; sequence <= 6; sequence++)
                    rows.Add(new Observation(name + entity, name, centres[entity], sequence));
        return AnalysisEngine.Build(rows);
    }
    private static List<CalibrationRow> SyntheticCalibration(bool applicable) => AnalysisEngine.MetricKeys
        .Select(key => new CalibrationRow(key, .001, .9, 80, Applicable: applicable,
            Tracks: new[] { SimulationScenarios.Location }, TrackPowers: new[] { .9 }, TrackScores: new[] { 80d },
            FprHigh: .005, TrackPowerLow: new[] { .8 })).ToList();
    private static List<ResultRow> Results(AnalysisData data, bool calibrationApplicable = true) =>
        AnalysisEngine.Results(data, SyntheticCalibration(calibrationApplicable), new Reporter(), default);

    private static void CalibrationIndependence()
    {
        AnalysisData data = Data(Enumerable.Range(1, 8).Select(x => (double)x).ToArray(), Enumerable.Range(21, 8).Select(x => (double)x).ToArray());
        // All simulated entities are dropped. This is an actual unavailable calibration,
        // not a low-power selection fixture: all 100 failures must remain accounted for.
        List<CalibrationRow> calibration = AnalysisEngine.Calibrate(data, 100, 1.15, 42, new Reporter(), default, missingRate: 1);
        Check(calibration.All(c => !c.Applicable && c.NullFailures == 100 && double.IsNaN(c.Fpr)), "Missing simulations were hidden or calibration remained available.");
        List<ResultRow> rows = AnalysisEngine.Results(data, calibration, new Reporter(), default);
        ResultRow median = rows.Single(r => r.Metric == "median");
        // Independent SciPy asymptotic, two-sided, continuity-corrected reference.
        const double referenceP = .0009391056991171899;
        Check(median.Applicable && !median.CalibrationApplicable && median.ObservedStatus == "available", "Observed availability is still coupled to calibration.");
        Check(Math.Abs(median.PValue - referenceP) <= 2e-7, "Observed Mann-Whitney differs from the independent reference.");
        Check(Math.Abs(median.AdjustedP - 12 * median.PValue) < 1e-12 && median.Verdict == "difference", "The full-registry decision was lost.");
        Check(rows.All(r => !r.CandidateInAnyTrack), "Unavailable calibration fabricated a recommendation.");
        Check(double.IsFinite(median.Effect) && double.IsFinite(median.EffectLow), "Observed effects were suppressed by calibration.");
        var outcome = new BenchmarkRunner.ReplicationOutcome { Claimed = new bool[BenchmarkProcedures.Ids.Length],
            Rejected = new bool[BenchmarkProcedures.Ids.Length], Chosen = new int[BenchmarkProcedures.Ids.Length] };
        double[] p = AnalysisEngine.MetricKeys.Select(key => rows.Single(r => r.Metric == key).PValue).ToArray();
        BenchmarkRunner.DecideObservedRegistry(outcome, p, .05);
        Check(outcome.Claimed[BenchmarkProcedures.MvsTwoTrack] && outcome.Rejected[BenchmarkProcedures.MvsTwoTrack], "Benchmark shipped comparator suppressed available observed tests.");
        BenchmarkRunner.DecideObservedRegistry(outcome, Enumerable.Repeat(double.NaN, 12).ToArray(), .05);
        Check(!outcome.Claimed[BenchmarkProcedures.MvsTwoTrack] && !outcome.Rejected[BenchmarkProcedures.MvsTwoTrack]
            && outcome.Chosen[BenchmarkProcedures.MvsTwoTrack] == -1, "An unavailable benchmark replication fabricated a claim.");
        double[] oneUsable = Enumerable.Repeat(double.NaN, 12).ToArray(); oneUsable[0] = .01;
        BenchmarkRunner.DecideObservedRegistry(outcome, oneUsable, .05);
        Check(outcome.Claimed[BenchmarkProcedures.MvsTwoTrack] && !outcome.Rejected[BenchmarkProcedures.MvsTwoTrack], "Benchmark shrank the correction family to available metrics.");
        ResultRow withCalibration = Results(data).Single(r => r.Metric == "median");
        Check(median.PValue == withCalibration.PValue && median.AdjustedP == withCalibration.AdjustedP
            && median.Verdict == withCalibration.Verdict && median.EffectLow == withCalibration.EffectLow
            && median.EquivalenceLow == withCalibration.EquivalenceLow, "Calibration changed observed inference or its random stream.");
    }
    private static void MetricExclusions()
    {
        AnalysisData data = Data(new double[] { -3, -2, -1, 0, 0, 1, 2, 3 }, new double[] { 10, 11, 12, 13, 14, 15, 16, 17 });
        List<ResultRow> rows = Results(data);
        ResultRow geometric = rows.Single(r => r.Metric == "geometric_mean");
        MetricGroupAvailability first = geometric.GroupAvailability![0];
        Check(first.RetainedEntities == 8 && first.UsableEntities == 3 && first.ExcludedEntities == 5
            && first.ExclusionReasons["nonpositive_measurements"] == 5, "Geometric exclusions or their denominator are wrong.");
        Check(!geometric.Applicable && geometric.CalibrationApplicable && geometric.ObservedStatus == "insufficient_usable_entities"
            && geometric.Verdict == "not_applicable" && double.IsNaN(geometric.PValue) && double.IsNaN(geometric.AdjustedP)
            && double.IsNaN(geometric.Effect) && geometric.EffectIntervalStatus == "unavailable", "Insufficient observed entities produced an inferential result.");
        foreach (string key in new[] { "coefficient_of_variation", "normalized_mad", "normalized_iqr" })
        {
            ResultRow relative = rows.Single(r => r.Metric == key);
            string reason = key == "coefficient_of_variation" ? "near_zero_mean" : "near_zero_median";
            Check(relative.Applicable && relative.GroupAvailability![0].UsableEntities == 6
                && relative.GroupAvailability[0].ExclusionReasons[reason] == 2, "Relative metric exclusions are not individual.");
        }
        ResultRow median = rows.Single(r => r.Metric == "median");
        Check(median.GroupAvailability![0].UsableEntities == 8 && median.GroupAvailability[0].ExclusionReasons.Count == 0
            && median.AdjustedP == Math.Min(1, 12 * median.PValue), "Unavailable metrics changed another metric or shrank the correction family.");
    }
    private static void MinimumBoundary()
    {
        AnalysisData data = Data(new double[] { -3, -2, -1, 0, 1, 2, 3, 4 }, new double[] { 10, 11, 12, 13, 14, 15, 16, 17 });
        ResultRow geometric = Results(data, false).Single(r => r.Metric == "geometric_mean");
        Check(geometric.GroupAvailability![0].UsableEntities == 4 && geometric.Applicable && double.IsFinite(geometric.PValue), "Exactly four usable entities should pass the software minimum.");
        data = Data(new double[8], new double[8]);
        List<ResultRow> rows = Results(data);
        Check(rows.Single(r => r.Metric == "median").PValue == 1, "All ties lost the explicit p=1 policy.");
        Check(!rows.Single(r => r.Metric == "coefficient_of_variation").Applicable, "All-zero denominators became testable.");
    }
    private static void AvailabilityExport()
    {
        List<ResultRow> rows = Results(Data(new double[] { -3, -2, -1, 0, 0, 1, 2, 3 }, Enumerable.Range(10, 8).Select(x => (double)x).ToArray()), false);
        string json = ScientificJson.Serialize(rows);
        List<ResultRow> restored = JsonSerializer.Deserialize<List<ResultRow>>(json, ScientificJson.Options)!;
        ResultRow geometric = restored.Single(r => r.Metric == "geometric_mean");
        Check(double.IsNaN(geometric.PValue) && !geometric.CalibrationApplicable
            && geometric.GroupAvailability![0].ExclusionReasons["nonpositive_measurements"] == 5, "Availability JSON lost nulls, status or exclusion counts.");
        string csv = OutputExporter.AvailabilityCsv(restored);
        Check(csv.Split('\n', StringSplitOptions.RemoveEmptyEntries).Length == 1 + 12 * 2, "Availability CSV omitted metric/group rows.");
        Check(csv.Contains("\"geometric_mean\",\"A\",8,3,5,\"nonpositive_measurements:5\",\"insufficient_usable_entities\",False"), "Availability CSV lost observed counts or calibration separation.");
        string results = OutputExporter.ResultsCsv(rows);
        Check(results.Split('\n')[0].EndsWith(",observed_status,calibration_applicable"), "Legacy CSV columns were replaced or new statuses omitted.");
        MetricGroupAvailability unsafeGroup = geometric.GroupAvailability![0] with { Group = "=SUM(1,2)" };
        Check(OutputExporter.AvailabilityCsv(new[] { geometric with { GroupAvailability = new[] { unsafeGroup } } }).Contains("\"'=SUM(1,2)\""), "New text export permits spreadsheet formulas.");
    }
}
