using MvsAnalyzer;
using System.Text.Json;

internal static class ScientificChecks
{
    public static readonly (string Name, Action Run)[] All = {
        ("JSON writes nonfinite values as null and reads them back", JsonRoundTrip),
        ("CLI rejects malformed explicit numbers and unknown options", StrictArguments),
        ("Cliffs delta has the documented first-minus-second sign", DeltaSign),
        ("Rank test handles all ties", TiedRanks),
        ("Relative summary metrics are invariant to physical units", MetricUnits),
        ("Location, within and between transforms are separate", PureTransforms),
        ("Full-registry adjustment is used for decisions", Multiplicity),
        ("A missing track is not silently replaced by the primary track", MissingTrack),
        ("Gauss-normal quadrature reproduces known moments", Quadrature),
        ("Bounded optimizer and Hessian pass a known quadratic", Optimization),
        ("Balanced REML separates within noise from entity-centre variance", BalancedVariance),
        ("Variance fit respects a change of measurement units", VarianceScaling),
        ("Estimation targets use the declared scale", EstimationTruth),
        ("Bias and MSE study exports complete draw accounting", EstimationAccounting),
        ("Calibration state, null MDE and settings survive replay", CalibrationReplay),
        ("MELSM uses global IDs and supports the analytic random-intercept special case", MelsmSpecialCase),
        ("MELSM refuses a constant outcome", MelsmConstant),
        ("One-condition import is opt-in and time availability is explicit", SingleConditionImport),
        ("CSV export neutralizes spreadsheet formulas in text fields", CsvSafety),
        ("Saved processing fingerprint responds to changes", SettingsChange)
    };
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void Near(double a, double b, double tolerance = 1e-8) => Check(double.IsFinite(a) && Math.Abs(a - b) <= tolerance, $"{a:R} != {b:R}");
    private static void Throws(Action action) { bool threw = false; try { action(); } catch (ArgumentException) { threw = true; } catch (InvalidDataException) { threw = true; } catch (JsonException) { threw = true; } Check(threw, "Expected a validation failure"); }
    private static string Temp() => Path.Combine(Path.GetTempPath(), "mvs_science_" + Guid.NewGuid().ToString("N"));
    private static void JsonRoundTrip()
    {
        var source = new[] { 1.25, double.NaN, double.PositiveInfinity, double.NegativeInfinity };
        string json = ScientificJson.Serialize(source); using JsonDocument doc = JsonDocument.Parse(json);
        Check(doc.RootElement[1].ValueKind == JsonValueKind.Null, "NaN was not written as null");
        double[] back = JsonSerializer.Deserialize<double[]>(json, ScientificJson.Options)!;
        Near(back[0], 1.25); Check(back.Skip(1).All(double.IsNaN), "Null must remain unavailable, never zero");
        double[] legacy = JsonSerializer.Deserialize<double[]>("[\"NaN\",\"Infinity\",\"-Infinity\"]", ScientificJson.Options)!;
        Check(double.IsNaN(legacy[0]) && double.IsPositiveInfinity(legacy[1]), "Legacy literals were not read");
        Throws(() => JsonSerializer.Deserialize<double>("1e999", ScientificJson.Options));
    }
    private static void StrictArguments()
    {
        Throws(() => new CliArguments(new[] { "--seed", "abc" }).Int("--seed", 7));
        Throws(() => new CliArguments(new[] { "--effect=NaN" }).Number("--effect", 1.15));
        Throws(() => new CliArguments(new[] { "--alpha" }).Number("--alpha", .05));
        Throws(() => new CliArguments(new[] { "--alpah=.05" }).Validate(new[] { "--alpha" }));
        Throws(() => new CliArguments(new[] { "--seed=1", "--seed=2" }).Validate(new[] { "--seed" }));
    }
    private static void DeltaSign() { Near(AnalysisEngine.CliffsDelta(new double[] { 3, 4 }, new double[] { 1, 2 }), 1); Near(AnalysisEngine.CliffsDelta(new double[] { 1, 2 }, new double[] { 3, 4 }), -1); }
    private static void MetricUnits()
    {
        double[] values = { 1, 2, 3, 4, 5, 6 };
        double[] first = AnalysisEngine.Metrics(values), small = AnalysisEngine.Metrics(values.Select(x => x * 1e-15).ToArray());
        foreach (int index in new[] { 2, 5, 6 }) Near(first[index], small[index], 1e-10);
    }
    private static void TiedRanks() { Near(AnalysisEngine.KruskalWallisP(new[] { new double[] { 2, 2, 2, 2 }, new double[] { 2, 2, 2, 2 }, new double[] { 2, 2, 2, 2 } }), 1); Near(AnalysisEngine.MannWhitneyP(new double[] { 2, 2, 2, 2 }, new double[] { 2, 2, 2, 2 }), 1); }
    private static void PureTransforms()
    {
        double[] raw = { 8, 10, 12 }; double mean = raw.Average();
        double[] location = raw.Select(x => AnalysisEngine.Transform(x, mean, 5, 100, 1.2, SimulationScenarios.Location)).ToArray();
        Near(location.Average(), 30); Near(ScientificMath.Variance(location), ScientificMath.Variance(raw));
        double[] within = raw.Select(x => AnalysisEngine.Transform(x, mean, 5, 100, 1.2, SimulationScenarios.Variability)).ToArray();
        Near(within.Average(), mean); Near(ScientificMath.Variance(within), 1.44 * ScientificMath.Variance(raw));
        double[] between = raw.Select(x => AnalysisEngine.Transform(x, mean, 5, 100, 1.2, SimulationScenarios.Heterogeneity)).ToArray();
        Near(between.Average(), 11); Near(ScientificMath.Variance(between), ScientificMath.Variance(raw));
    }
    private static void Multiplicity() { Near(DecisionPolicy.Adjust(.01, 12), .12); Check(!DecisionPolicy.Reject(.01, .05, 12), "Uncorrected decision leaked through"); Check(DecisionPolicy.Reject(.001, .05, 12), "Strong corrected effect disappeared"); }
    private static void MissingTrack()
    {
        var row = new CalibrationRow("mean", .01, .8, 70, Tracks: new[] { "location" }, TrackPowers: new[] { .8 }, TrackScores: new[] { 70d });
        Check(double.IsNaN(row.PowerIn("between")), "Missing between power reused location power");
    }
    private static void Quadrature()
    {
        foreach (int count in new[] { 3, 9, 15, 31, 61 })
        {
            var q = NumericalMethods.NormalQuadrature(count); Near(q.Weights.Sum(), 1, 1e-10);
            double Moment(int power) => q.Nodes.Select((x, i) => Math.Pow(x, power) * q.Weights[i]).Sum();
            Near(Moment(1), 0, 1e-10); Near(Moment(2), 1, 1e-9); Near(Moment(4), 3, 1e-8);
            Check(q.Weights.All(w => w > 0), "Invalid quadrature weight");
        }
    }
    private static void Optimization()
    {
        double F(double[] x) => .5 * Math.Pow(x[0] - 1, 2) + 2 * Math.Pow(x[1] + 2, 2);
        var fit = NumericalMethods.Minimize(F, new double[] { -3, 5 }, new double[] { -10, -10 }, new double[] { 10, 10 });
        Check(fit.Converged, "Known quadratic did not converge"); Near(fit.Parameters[0], 1, 1e-4); Near(fit.Parameters[1], -2, 1e-4);
        double[] se = NumericalMethods.StandardErrors(F, new double[] { 1, -2 }) ?? throw new Exception("Quadratic Hessian was singular"); Near(se[0], 1, 1e-4); Near(se[1], .5, 1e-4);
    }
    private static ClusterSummary[] Clusters(double units = 1) => Enumerable.Range(0, 2).SelectMany(g => Enumerable.Range(1, 5).Select(e => new ClusterSummary(g + ":" + e, g, 4, (100 * g + e) * units, 12 * units * units))).ToArray();
    private static void BalancedVariance()
    {
        VarianceFit fit = VarianceAnalysis.Fit(Clusters(), 2, reml: true); Check(fit.Converged, "Balanced REML did not converge");
        foreach (double v in fit.Within) Near(v, 4, .003); foreach (double v in fit.Between) Near(v, 1.5, .003);
    }
    private static void VarianceScaling()
    {
        var fit = VarianceAnalysis.Fit(Clusters(1000), 2, reml: true); Check(fit.Converged, "Scaled REML did not converge");
        Near(fit.Within[0] / 1e6, 4, .003); Near(fit.Between[0] / 1e6, 1.5, .003);
    }
    private static void EstimationTruth()
    {
        var log = new EstimationOptions(Shape: "lognormal", Location: 1, WithinSd: .3, BetweenSd: .2);
        Near(EstimationStudy.Truth(log), Math.Exp(1 + .5 * (.09 + .04))); Near(EstimationStudy.Truth(log with { Target = "median" }), Math.E);
        Near(EstimationStudy.Truth(new EstimationOptions(Target: "within_variance", WithinSd: 3)), 9);
    }
    private static void EstimationAccounting()
    {
        var report = EstimationStudy.Run(new EstimationOptions(Entities: 8, Measurements: 6, Repetitions: 100, BootstrapReplications: 99));
        Check(report.Draws.Length == report.Performance.Length * 100, "Draw accounting is incomplete");
        foreach (var row in report.Performance) { Check(row.Completed + row.Failures == row.Requested, "Failed fits vanished from the denominator"); Check(row.Mse >= 0 && double.IsFinite(row.BiasMcse), "Invalid performance estimate"); }
        var baseline = report.Performance[0]; Near(baseline.RelativeMseEfficiency, 1); Near(baseline.RelativeVarianceEfficiency, 1);
    }
    private static void CalibrationReplay()
    {
        var observations = new List<Observation>(); var random = new Random(81);
        for (int g = 0; g < 2; g++) for (int e = 0; e < 8; e++) for (int j = 0; j < 6; j++) observations.Add(new Observation($"{g}:{e}", "G" + g, 100 + e + ScientificMath.Gaussian(random), j));
        AnalysisData data = AnalysisEngine.Build(observations); var settings = new AppSettings();
        var rows = AnalysisEngine.Calibrate(data, 100, settings.CalibrationEffect, settings.CalibrationSeed, new ImmediateProgress(), CancellationToken.None, tracks: AnalysisEngine.DefaultTracks);
        Check(rows.All(r => r.TrackMdeStatus!.All(s => s != "estimated_on_grid")), "A smoke budget invented an MDE");
        var state = new CalibrationState("fixture.csv", ScientificMath.Hash("fixture"), "same_dataset", 100, settings.CalibrationEffect,
            settings.CalibrationSeed, settings.SimulationScenario, settings.OutlierRate, settings.MissingRate, settings.Alpha, settings.EquivalenceMargin,
            false, rows[0].Tracks!, ReleaseInfo.Version, AnalysisEngine.EngineVersion, OutputExporter.FormulaVersion, OutputExporter.FormulaHash, "test", "2026-09-05T00:00:00Z", rows,
            ProcessingSnapshot.From(settings), SettingsHash: SettingsContract.Fingerprint(settings));
        string folder = Temp(); Directory.CreateDirectory(folder);
        try
        {
            string path = Path.Combine(folder, CalibrationPersistence.FileName); CalibrationPersistence.Write(path, state);
            var restored = CalibrationPersistence.Read(path); var target = new AppSettings { MinMeasurements = 7 }; CalibrationPersistence.Apply(restored, target);
            Check(SettingsContract.Fingerprint(target) == state.SettingsHash, "Configuration did not round trip");
            Check(restored.Rows.Count == 12 && restored.Rows.Any(r => double.IsNaN(r.Mde)), "Metric registry or null MDE was lost");
            string text = File.ReadAllText(path); Check(!text.Contains("Infinity") && !text.Contains("NaN"), "Nonstandard output literal");
            Throws(() => CalibrationPersistence.Apply(restored with { EngineVersion = "0.0.0" }, target));
            File.WriteAllText(path, text.Replace("fixture.csv", "tampered.csv")); Throws(() => CalibrationPersistence.Read(path));
        }
        finally { Directory.Delete(folder, true); }
    }
    private static void MelsmSpecialCase()
    {
        var rows = new List<Observation>(); var random = new Random(56);
        for (int e = 0; e < 16; e++) { double b = 2 * ScientificMath.Gaussian(random); for (int j = 0; j < 8; j++) rows.Add(new Observation("P" + e, j < 4 ? "A" : "B", 100 + (j < 4 ? 0 : 2) + b + ScientificMath.Gaussian(random), j)); }
        var report = MelsmAnalysis.Run(rows, new MelsmOptions(RandomScale: false, MaxIterations: 4000));
        Check(report.Subjects == 16 && report.Observations == 128, "Conditions split the same subject into separate entities");
        Check(report.Converged && double.IsFinite(report.LogLikelihood), "Analytic special-case model did not converge");
        Check(report.Parameters.All(p => double.IsFinite(p.Estimate)), "A fitted parameter is not finite");
    }
    private static void MelsmConstant()
    {
        var rows = Enumerable.Range(0, 8).SelectMany(e => Enumerable.Range(0, 4).Select(j => new Observation("P" + e, "A", 1, j))).ToList();
        Throws(() => MelsmAnalysis.Run(rows, new MelsmOptions()));
    }
    private static void SingleConditionImport()
    {
        string path = Temp() + ".csv"; File.WriteAllText(path, "entity,group,value,sequence\nP1,A,10,1\nP1,A,11,2\n");
        try { var rows = CsvImporter.Read(path, 0, 100, allowSingleGroup: true); Check(rows.Count == 2 && CsvImporter.LastSequenceWasProvided, "Single-condition import failed"); Throws(() => CsvImporter.Read(path, 0, 100)); }
        finally { File.Delete(path); }
    }
    private static void CsvSafety() => Check(ScientificTables.Csv(new[] { new MelsmEntity("=HYPERLINK(1)", 3, 0, 0) }).Contains("'=HYPERLINK"), "Untrusted ID became a spreadsheet formula");
    private static void SettingsChange() { var settings = new AppSettings(); string before = SettingsContract.Fingerprint(settings); settings.MinMeasurements++; Check(before != SettingsContract.Fingerprint(settings), "Preprocessing was not frozen"); }
}
