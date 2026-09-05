using System.Globalization;

namespace MvsAnalyzer;

/// <summary>Entity-summary analysis. Latent variance components are handled by VarianceAnalysis, not rank tests of centres.</summary>
internal static class AnalysisEngine
{
    internal const string EngineVersion = ReleaseInfo.EngineVersion;
    internal static readonly double[] EffectGrid = { 1.00, 1.02, 1.05, 1.10, 1.20 };
    internal const double MdePowerTarget = .80;
    internal const double CandidateMaxFpr = .075, CandidateMinPower = .70, CandidateMinScore = 0;
    internal static readonly string[] MetricKeys = { "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad", "normalized_iqr", "mean", "rms", "range", "geometric_mean", "trimmed_mean_20" };
    internal static readonly string[] DefaultTracks = { SimulationScenarios.Location, SimulationScenarios.Variability, SimulationScenarios.Heterogeneity };

    public static AnalysisData Build(List<Observation> observations, int minValue = -1000000, int maxValue = 1000000, int minMeasurements = 6)
    {
        if (maxValue <= minValue) throw new ArgumentOutOfRangeException(nameof(maxValue));
        if (minMeasurements < 2) throw new ArgumentOutOfRangeException(nameof(minMeasurements));
        if (observations.Count == 0) throw new InvalidDataException("No observations.");
        if (observations.Any(o => string.IsNullOrWhiteSpace(o.Entity) || string.IsNullOrWhiteSpace(o.Group) || o.Entity.Contains('\u001f') || o.Group.Contains('\u001f')))
            throw new InvalidDataException("Entity/group identifiers are empty or contain a reserved control character.");
        if (observations.Select(x => x.Variable).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1)
            throw new InvalidDataException("Use one outcome variable per run.");
        if (observations.Where(x => !string.IsNullOrWhiteSpace(x.Unit)).Select(x => x.Unit).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1)
            throw new InvalidDataException("Mixed units cannot be analysed together. Convert them explicitly before import.");
        string[] groups = observations.Select(x => x.Group).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (groups.Length < 2 || groups.Length > 10) throw new InvalidDataException("Use 2–10 independent groups. For within-entity conditions use the MELSM command.");
        var entities = new List<EntityResult>();
        foreach (string group in groups)
            foreach (var block in observations.Where(x => x.Group.Equals(group, StringComparison.OrdinalIgnoreCase)).GroupBy(x => x.Entity, StringComparer.OrdinalIgnoreCase))
            {
                double[] values = block.Select(x => x.Value).Where(x => double.IsFinite(x) && x >= minValue && x <= maxValue).ToArray();
                if (values.Length >= minMeasurements) entities.Add(new EntityResult(block.Key, group, Metrics(values), values.Length));
            }
        int[] counts = groups.Select(g => entities.Count(x => x.Group.Equals(g, StringComparison.OrdinalIgnoreCase))).ToArray();
        if (counts.Any(x => x < 4)) throw new InvalidDataException($"Every group needs at least four entities with {minMeasurements} valid measurements.");
        var keys = entities.Select(x => Key(x.Group, x.Entity)).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var valid = observations.Where(x => keys.Contains(Key(x.Group, x.Entity)) && double.IsFinite(x.Value) && x.Value >= minValue && x.Value <= maxValue).ToList();
        var warnings = new List<string>();
        if (valid.Count != observations.Count) warnings.Add($"Scientific processing retained {valid.Count} of {observations.Count} supplied rows; review value limits and excluded small entities.");
        if (valid.GroupBy(x => x.Entity, StringComparer.OrdinalIgnoreCase).Any(g => g.Select(x => x.Group).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1))
            warnings.Add("Entity IDs occur in multiple groups. This mode treats group/entity pairs as independent. If these are the SAME entities under different conditions, use MELSM instead.");
        if (counts.Any(x => x < 20)) warnings.Add("Small groups: asymptotic rank-test p-values and percentile intervals need independent validation; ties can aggravate the approximation.");
        warnings.Add("Summary resampling assumes exchangeable observations within entities; time dependence is not modelled in this mode.");
        return new AnalysisData { Observations = valid, Entities = entities, GroupNames = groups, GroupCounts = counts,
            ValidRows = valid.Count, MedianMeasurements = Median(entities.Select(e => (double)e.Measurements).ToArray()),
            DistributionProxy = DistributionProxy(valid.Select(x => x.Value).ToArray()), MinValueApplied = minValue,
            MaxValueApplied = maxValue, MinMeasurementsApplied = minMeasurements, MeasurementName = valid[0].Variable,
            Unit = valid.Select(x => x.Unit).FirstOrDefault(x => !string.IsNullOrWhiteSpace(x)) ?? "", Warnings = warnings.ToArray() };
    }
    public static List<Observation> Demo()
    {
        var r = new Random(7791); var output = new List<Observation>();
        for (int g = 0; g < 3; g++) for (int e = 1; e <= 30; e++) for (int s = 1; s <= 50; s++)
            output.Add(new Observation($"G{g + 1}_{e}", $"Group {g + 1}", 100 + g * 7 + 12 * ScientificMath.Gaussian(r), s, "demo_measurement", "unit"));
        return output;
    }
    internal static string[] NormalizeTracks(string primary, string[]? tracks)
    {
        var names = new List<string> { SimulationScenarios.Canonicalize(primary) };
        foreach (string track in tracks ?? Array.Empty<string>()) { string name = SimulationScenarios.Canonicalize(track); if (!names.Contains(name)) names.Add(name); }
        return names.ToArray();
    }
    // Detection index only. The three legacy descriptive diagnostics are NOT secretly assigned
    // estimation-quality meaning and no longer enter the ranking or gate.
    internal static double Composite(double power, double falseAlarm, double robustness, double repeatability, double coverage) =>
        100 * Math.Sqrt(Math.Clamp(power, 0, 1) * Math.Clamp(falseAlarm, 0, 1));

    public static List<CalibrationRow> Calibrate(AnalysisData data, int repetitions, double effect, int seed,
        IProgress<ProgressInfo> progress, CancellationToken token, string scenario = "location", double outlierRate = .02,
        double missingRate = 0, double alpha = .05, string[]? tracks = null)
    {
        if (repetitions < 100) throw new ArgumentOutOfRangeException(nameof(repetitions), "At least 100 simulations are required.");
        ScientificMath.RequireFinite(effect, "effect"); if (effect <= 1) throw new ArgumentOutOfRangeException(nameof(effect));
        ScientificMath.RequireRange(alpha, 0, 1, "alpha", false);
        ScientificMath.RequireRange(outlierRate, 0, 1, "outlier rate"); ScientificMath.RequireRange(missingRate, 0, 1, "missing rate");
        string[] names = NormalizeTracks(scenario, tracks);
        var pool = data.Observations.GroupBy(o => Key(o.Group, o.Entity), StringComparer.OrdinalIgnoreCase).Select(g => g.Select(o => o.Value).ToArray()).ToArray();
        double center = pool.Average(x => x.Average());
        double shiftScale = Math.Max(Math.Abs(center), Math.Sqrt(pool.Average(x => ScientificMath.Variance(x))));
        if (!double.IsFinite(shiftScale) || shiftScale <= 0) shiftScale = 1;
        int m = MetricKeys.Length, t = names.Length, k = EffectGrid.Length;
        var falsePositives = new int[m]; var nullValid = new int[m];
        var detected = new int[m, t]; var valid = new int[m, t];
        var gridDetected = new int[m, t, k]; var gridValid = new int[m, t, k]; var gridTotal = new int[k];
        for (int rep = 0; rep < repetitions; rep++)
        {
            token.ThrowIfCancellationRequested();
            int drawSeed = ScientificMath.Seed(seed, "empirical-common-draw", rep);
            double[][][] nullGroups = Simulate(pool, data.GroupCounts, data.MinMeasurementsApplied, new Random(drawSeed), 1, SimulationScenarios.Location, outlierRate, missingRate, center, shiftScale);
            for (int metric = 0; metric < m; metric++)
            {
                double p = MetricP(nullGroups, metric);
                if (!double.IsFinite(p)) continue;
                nullValid[metric]++; if (DecisionPolicy.Reject(p, alpha, m)) falsePositives[metric]++;
            }
            int point = rep % k; gridTotal[point]++;
            for (int track = 0; track < t; track++)
            {
                // Exactly the same resampling/noise stream across effects, tracks and metrics.
                double[][][] alternative = Simulate(pool, data.GroupCounts, data.MinMeasurementsApplied, new Random(drawSeed), effect, names[track], outlierRate, missingRate, center, shiftScale);
                double[][][] grid = Simulate(pool, data.GroupCounts, data.MinMeasurementsApplied, new Random(drawSeed), EffectGrid[point], names[track], outlierRate, missingRate, center, shiftScale);
                for (int metric = 0; metric < m; metric++)
                {
                    double p = MetricP(alternative, metric), gp = MetricP(grid, metric);
                    if (double.IsFinite(p)) { valid[metric, track]++; if (DecisionPolicy.Reject(p, alpha, m)) detected[metric, track]++; }
                    if (double.IsFinite(gp)) { gridValid[metric, track, point]++; if (DecisionPolicy.Reject(gp, alpha, m)) gridDetected[metric, track, point]++; }
                }
            }
            if ((rep + 1) % Math.Max(1, repetitions / 100) == 0 || rep + 1 == repetitions)
                progress.Report(new ProgressInfo(.90 * (rep + 1) / repetitions, $"Simulation {rep + 1} of {repetitions}", "Common pooled null; centre, within and between sensitivity"));
        }
        var rows = new List<CalibrationRow>(); double[][][] observed = GroupMetricArrays(data);
        for (int metric = 0; metric < m; metric++)
        {
            token.ThrowIfCancellationRequested();
            bool applicable = observed.All(g => g[metric].Length >= 4) && nullValid[metric] >= .9 * repetitions;
            double fpr = applicable ? falsePositives[metric] / (double)repetitions : double.NaN;
            double nominal = alpha / m;
            var fci = applicable ? ScientificMath.Wilson(falsePositives[metric], repetitions) : (double.NaN, double.NaN);
            bool inflated = double.IsFinite(fpr) && fpr > DecisionPolicy.FprLimit(nominal);
            double penalty = Math.Exp(-Math.Max(0, fpr - nominal) / nominal);
            double repeatability = applicable ? EstimateRepeatability(observed.Select(g => g[metric]).ToArray(), new Random(ScientificMath.Seed(seed, MetricKeys[metric] + ":repeatability"))) : double.NaN;
            double robustness = applicable ? EstimateRobustness(pool, metric, seed) : double.NaN;
            double coverage = applicable ? EstimateCoverage(observed.SelectMany(g => g[metric]).ToArray(), new Random(ScientificMath.Seed(seed, MetricKeys[metric] + ":coverage")), token: token) : double.NaN;
            var powers = new double[t]; var scores = new double[t]; var mdes = new double[t]; var curves = new string[t];
            var powerLow = new double[t]; var powerHigh = new double[t]; var failures = new int[t]; var mdeStatus = new string[t];
            for (int track = 0; track < t; track++)
            {
                failures[track] = repetitions - valid[metric, track];
                powers[track] = applicable && valid[metric, track] >= .9 * repetitions ? detected[metric, track] / (double)repetitions : double.NaN;
                var ci = double.IsFinite(powers[track]) ? ScientificMath.Wilson(detected[metric, track], repetitions) : (double.NaN, double.NaN);
                powerLow[track] = ci.Item1; powerHigh[track] = ci.Item2;
                scores[track] = double.IsFinite(powers[track]) ? Composite(powers[track], penalty, robustness, repeatability, coverage) : double.NaN;
                double[] curve = Enumerable.Range(0, k).Select(p => applicable && gridValid[metric, track, p] >= .9 * gridTotal[p] ? gridDetected[metric, track, p] / (double)gridTotal[p] : double.NaN).ToArray();
                mdes[track] = !inflated && applicable && gridTotal.All(n => n >= 100) ? MdeFromCurve(EffectGrid, curve) : double.NaN;
                mdeStatus[track] = !applicable ? "not_applicable" : inflated ? "fpr_inflated" : gridTotal.Any(n => n < 100) ? "insufficient_simulations" : double.IsFinite(mdes[track]) ? "estimated_on_grid" : "target_not_reached_or_invalid_curve";
                curves[track] = string.Join("|", EffectGrid.Select((e, p) => e.ToString("R", CultureInfo.InvariantCulture) + ":" + curve[p].ToString("R", CultureInfo.InvariantCulture)));
            }
            rows.Add(new CalibrationRow(MetricKeys[metric], fpr, powers[0], scores[0], robustness, repeatability, coverage, applicable,
                mdes[0], inflated, curves[0], names, powers, scores, mdes, curves,
                Repetitions: repetitions, FprLow: fci.Item1, FprHigh: fci.Item2, TrackPowerLow: powerLow, TrackPowerHigh: powerHigh,
                TrackFailures: failures, TrackMdeStatus: mdeStatus, Alpha: alpha, NullFailures: repetitions - nullValid[metric]));
            progress.Report(new ProgressInfo(.90 + .10 * (metric + 1) / m, "Diagnostics and intervals", MetricKeys[metric]));
        }
        return rows;
    }
    private static double[][][] Simulate(double[][] pool, int[] counts, int minimum, Random random, double effect,
        string scenario, double contamination, double missing, double populationCenter, double shiftScale)
    {
        var groups = new double[counts.Length][][];
        for (int g = 0; g < counts.Length; g++)
        {
            var summaries = new List<double[]>();
            for (int entity = 0; entity < counts[g]; entity++)
            {
                double[] source = pool[random.Next(pool.Length)]; double[] raw = Sample(source, source.Length, random);
                double mean = raw.Average(), sd = Math.Sqrt(ScientificMath.Variance(raw));
                bool affected = g == counts.Length - 1;
                var kept = new List<double>(raw.Length);
                foreach (double x in raw)
                {
                    double value = affected ? Transform(x, mean, populationCenter, shiftScale, effect, scenario) : x;
                    // Always consume all draws, even at zero rates; nuisance noise is symmetric.
                    double outlier = random.NextDouble(), side = random.NextDouble(), drop = random.NextDouble();
                    if (outlier < contamination) value += (side < .5 ? -1 : 1) * Math.Max(sd, 1e-12) * 5;
                    if (drop >= missing) kept.Add(value);
                }
                if (kept.Count >= minimum) summaries.Add(Metrics(kept.ToArray()));
            }
            groups[g] = Enumerable.Range(0, MetricKeys.Length).Select(m => summaries.Select(s => s[m]).Where(double.IsFinite).ToArray()).ToArray();
        }
        return groups;
    }
    internal static double Transform(double x, double entityCenter, double populationCenter, double shiftScale, double effect, string scenario)
    {
        return SimulationScenarios.Canonicalize(scenario) switch
        {
            SimulationScenarios.Variability => entityCenter + effect * (x - entityCenter),
            SimulationScenarios.Heterogeneity => populationCenter + effect * (entityCenter - populationCenter) + (x - entityCenter),
            SimulationScenarios.Decrease => x - shiftScale * (effect - 1),
            _ => x + shiftScale * (effect - 1)
        };
    }
    private static double MetricP(double[][][] groups, int metric)
    {
        double[][] values = groups.Select(g => g[metric]).ToArray();
        return values.All(x => x.Length >= 4) ? GlobalP(values) : double.NaN;
    }

    public static List<ResultRow> Results(AnalysisData data, List<CalibrationRow> calibration, IProgress<ProgressInfo> progress,
        CancellationToken token, double alpha = .05, double equivalenceMargin = .147, int seed = 20260719)
    {
        ScientificMath.RequireRange(alpha, 0, 1, "alpha", false); ScientificMath.RequireRange(equivalenceMargin, 0, 1, "equivalence margin", false);
        if (calibration.Count != MetricKeys.Length || calibration.Select(c => c.Metric).Distinct().Count() != MetricKeys.Length || MetricKeys.Any(key => !calibration.Any(c => c.Metric == key)))
            throw new InvalidDataException("The calibration metric registry is incompatible; recalibrate.");
        string[] tracks = calibration.First().Tracks ?? new[] { SimulationScenarios.Default };
        double[][][] arrays = GroupMetricArrays(data); var rows = new List<ResultRow>();
        for (int metric = 0; metric < MetricKeys.Length; metric++)
        {
            token.ThrowIfCancellationRequested(); CalibrationRow c = calibration.Single(x => x.Metric == MetricKeys[metric]);
            double[][] groups = arrays.Select(g => g[metric]).ToArray(); double[] medians = groups.Select(Median).ToArray();
            bool applicable = c.Applicable && groups.All(g => g.Length >= 4);
            double p = applicable ? GlobalP(groups) : double.NaN, adjusted = DecisionPolicy.Adjust(p, MetricKeys.Length);
            double delta = double.NaN, low = double.NaN, high = double.NaN, equivalenceP = double.NaN, percent = double.NaN;
            double eqLow = double.NaN, eqHigh = double.NaN; string pairText = "";
            if (applicable)
            {
                var pair = LargestPair(groups); delta = pair.Delta;
                var rng = new Random(ScientificMath.Seed(seed, c.Metric + ":effect"));
                var ci = DeltaInterval(groups[pair.A], groups[pair.B], equivalenceMargin, rng);
                low = ci.Low; high = ci.High;
                // Selected pair intervals with >2 groups are descriptive, never a global equivalence claim.
                if (groups.Length == 2)
                {
                    double localAlpha = alpha / MetricKeys.Length;
                    var eq = DeltaInterval(groups[0], groups[1], equivalenceMargin,
                        new Random(ScientificMath.Seed(seed, c.Metric + ":equivalence")), 4000, 2 * localAlpha);
                    eqLow = eq.Low; eqHigh = eq.High;
                }
                pairText = data.GroupNames[pair.A] + " vs " + data.GroupNames[pair.B];
                if (Math.Abs(medians[pair.B]) > 0) percent = (medians[pair.A] - medians[pair.B]) / Math.Abs(medians[pair.B]) * 100;
            }
            string verdict = !applicable ? "not_applicable" : adjusted < alpha ? "difference"
                : groups.Length == 2 && eqLow > -equivalenceMargin && eqHigh < equivalenceMargin ? "equivalent" : "insufficient";
            string summary = string.Join("; ", data.GroupNames.Select((g, i) => g + "=" + medians[i].ToString("0.###", CultureInfo.InvariantCulture)));
            rows.Add(new ResultRow(c.Metric, medians[0], medians[1], medians.Max() - medians.Min(), p, c.Fpr, c.Power, c.Score, false,
                summary, c.Robustness, c.Repeatability, c.Coverage, applicable, false, delta, low, high, equivalenceP,
                c.Mde, c.FprInflated, verdict, pairText, percent, tracks,
                tracks.Select(c.PowerIn).ToArray(), tracks.Select(c.ScoreIn).ToArray(), tracks.Select(c.MdeIn).ToArray(), new bool[tracks.Length],
                AdjustedP: adjusted, EffectIntervalStatus: groups.Length > 2 ? "selected_pair_descriptive" : "pointwise_percentile_95",
                EquivalenceLow: eqLow, EquivalenceHigh: eqHigh));
            progress.Report(new ProgressInfo((metric + 1d) / MetricKeys.Length, "Analysing entity summaries", c.Metric));
        }
        for (int t = 0; t < tracks.Length; t++)
        {
            int accepted = 0;
            foreach (ResultRow row in rows.Where(r => r.Applicable).OrderByDescending(r => r.ScoreIn(tracks[t])))
            {
                CalibrationRow c = calibration.Single(x => x.Metric == row.Metric);
                if (accepted >= 4 || !c.PassesGateIn(tracks[t])) continue;
                row.TrackCandidates![t] = true; accepted++;
            }
        }
        for (int i = 0; i < rows.Count; i++)
        {
            CalibrationRow c = calibration.Single(x => x.Metric == rows[i].Metric);
            rows[i] = rows[i] with { Candidate = rows[i].TrackCandidates![0], NearMiss = !rows[i].CandidateInAnyTrack && tracks.Any(c.PassesGateIn) };
        }
        return rows.OrderByDescending(r => r.CandidateInAnyTrack).ThenByDescending(r => double.IsFinite(r.BestTrackScore) ? r.BestTrackScore : double.NegativeInfinity).ToList();
    }
    internal static string Key(string group, string entity) => group + '\u001f' + entity;
    private static double[][][] GroupMetricArrays(AnalysisData data) => data.GroupNames.Select(g => Enumerable.Range(0, MetricKeys.Length)
        .Select(m => data.Entities.Where(e => e.Group.Equals(g, StringComparison.OrdinalIgnoreCase)).Select(e => e.Metrics[m]).Where(double.IsFinite).ToArray()).ToArray()).ToArray();

    private static double EstimateRobustness(double[][] pool, int metric, int seed)
    {
        var r = new Random(ScientificMath.Seed(seed, MetricKeys[metric] + ":robustness"));
        double[] baseline = pool.Select(x => Metrics(x)[metric]).Where(double.IsFinite).ToArray();
        if (baseline.Length == 0) return double.NaN;
        double scale = Math.Max(Math.Sqrt(ScientificMath.Variance(baseline)), Math.Abs(Median(baseline)) * .01);
        var changes = new List<double>();
        foreach (double[] source in pool)
        {
            double before = Metrics(source)[metric]; if (!double.IsFinite(before)) continue;
            double sd = Math.Sqrt(ScientificMath.Variance(source));
            double[] dirty = source.Select(x => x + (r.NextDouble() < .05 ? (r.Next(2) == 0 ? -1 : 1) * 5 * sd : 0)).ToArray();
            double after = Metrics(dirty)[metric]; if (double.IsFinite(after)) changes.Add(Math.Abs(after - before));
        }
        return changes.Count == 0 ? double.NaN : 1 / (1 + changes.Average() / Math.Max(scale, 1e-12));
    }
    /// <summary>Descriptive pooled-median coverage diagnostic; NOT coverage of a group contrast.</summary>
    internal static double EstimateCoverage(double[] entityValues, Random random, int outerTrials = 200, int innerResamples = 200, CancellationToken token = default)
    {
        if (entityValues.Length < 4) return double.NaN;
        double truth = Median(entityValues); int contains = 0;
        for (int trial = 0; trial < outerTrials; trial++)
        {
            token.ThrowIfCancellationRequested(); double[] study = Sample(entityValues, entityValues.Length, random);
            double[] draws = Enumerable.Range(0, innerResamples).Select(_ => Median(Sample(study, study.Length, random))).ToArray();
            if (truth >= ScientificMath.Quantile(draws, .025) && truth <= ScientificMath.Quantile(draws, .975)) contains++;
        }
        return contains / (double)outerTrials;
    }
    internal static double EstimateRepeatability(double[][] groupValues, Random random, int splits = 50)
    {
        if (groupValues.Length == 0 || groupValues.Any(g => g.Length < 4)) return double.NaN;
        double scale = Math.Sqrt(ScientificMath.Variance(groupValues.SelectMany(g => g).ToArray()));
        if (!double.IsFinite(scale)) return double.NaN;
        if (scale <= 0) return 1;
        var differences = new List<double>();
        for (int split = 0; split < splits; split++) foreach (double[] group in groupValues)
        {
            double[] shuffled = (double[])group.Clone(); Shuffle(shuffled, random); int n = shuffled.Length / 2;
            differences.Add(Math.Abs(Median(shuffled[..n]) - Median(shuffled[n..])));
        }
        return 1 / (1 + differences.Average() / scale);
    }
    internal static double[] Metrics(double[] values)
    {
        if (values.Length == 0) return Enumerable.Repeat(double.NaN, MetricKeys.Length).ToArray();
        double[] sorted = values.OrderBy(x => x).ToArray(); double median = Quantile(sorted, .5), mean = values.Average();
        double sd = Math.Sqrt(ScientificMath.Variance(values)); double mad = Median(values.Select(x => Math.Abs(x - median)).ToArray());
        double iqr = Quantile(sorted, .75) - Quantile(sorted, .25);
        double denominatorTolerance = Math.Max(double.Epsilon, values.Max(x => Math.Abs(x)) * 1e-12);
        double cv = Math.Abs(mean) <= denominatorTolerance ? double.NaN : sd / Math.Abs(mean);
        double nm = Math.Abs(median) <= denominatorTolerance ? double.NaN : mad / Math.Abs(median), ni = Math.Abs(median) <= denominatorTolerance ? double.NaN : iqr / Math.Abs(median);
        double geometric = values.All(x => x > 0) ? Math.Exp(values.Average(Math.Log)) : double.NaN;
        int trim = (int)Math.Floor(values.Length * .2); double trimmed = sorted.Skip(trim).Take(sorted.Length - 2 * trim).Average();
        return new[] { median, sd, cv, mad, iqr, nm, ni, mean, Math.Sqrt(values.Average(x => x * x)), sorted[^1] - sorted[0], geometric, trimmed };
    }
    private static double[] Sample(double[] source, int count, Random random) => Enumerable.Range(0, count).Select(_ => source[random.Next(source.Length)]).ToArray();
    private static double Median(double[] values) => ScientificMath.Quantile(values, .5);
    private static double Quantile(double[] sorted, double q) { double p = (sorted.Length - 1) * q; int lo = (int)Math.Floor(p), hi = (int)Math.Ceiling(p); return sorted[lo] + (sorted[hi] - sorted[lo]) * (p - lo); }
    private static string DistributionProxy(double[] x)
    {
        double mean = x.Average(), sd = Math.Sqrt(ScientificMath.Variance(x));
        double skew = x.Length < 3 || sd <= 0 ? 0 : x.Sum(v => Math.Pow((v - mean) / sd, 3)) * x.Length / ((x.Length - 1d) * (x.Length - 2d));
        return Math.Abs(skew) > 1.5 ? (skew > 0 ? "strongly right-skewed" : "strongly left-skewed") : Math.Abs(skew) > .7 ? "moderately skewed" : "approximately symmetric (pooled diagnostic)";
    }
    private static double GlobalP(double[][] groups) => groups.Length == 2 ? MannWhitneyP(groups[0], groups[1]) : KruskalWallisP(groups);
    internal static double KruskalWallisP(double[][] groups)
    {
        var all = groups.SelectMany((g, gi) => g.Select(v => (v, gi))).OrderBy(x => x.v).ToArray();
        if (all.Length == 0 || groups.Any(g => g.Length == 0)) return double.NaN;
        double[] sums = new double[groups.Length]; double ties = 0; int pos = 0;
        while (pos < all.Length)
        {
            int end = pos + 1; while (end < all.Length && all[end].v == all[pos].v) end++;
            double rank = (pos + 1 + end) / 2d, nTie = end - pos; ties += nTie * nTie * nTie - nTie;
            for (int i = pos; i < end; i++) sums[all[i].gi] += rank; pos = end;
        }
        double n = all.Length, correction = 1 - ties / (n * n * n - n);
        if (correction <= 1e-14) return 1;
        double h = Math.Max(0, (12 / (n * (n + 1)) * sums.Select((r, i) => r * r / groups[i].Length).Sum() - 3 * (n + 1)) / correction);
        return Math.Clamp(GammaQ((groups.Length - 1) / 2d, h / 2), 0, 1);
    }
    internal static double MannWhitneyP(double[] a, double[] b)
    {
        if (a.Length == 0 || b.Length == 0) return double.NaN;
        var all = a.Select(v => (v, g: 0)).Concat(b.Select(v => (v, g: 1))).OrderBy(x => x.v).ToArray();
        double ranks = 0, ties = 0; int pos = 0;
        while (pos < all.Length)
        {
            int end = pos + 1; while (end < all.Length && all[end].v == all[pos].v) end++;
            double rank = (pos + 1 + end) / 2d, nTie = end - pos; ties += nTie * nTie * nTie - nTie;
            for (int i = pos; i < end; i++) if (all[i].g == 1) ranks += rank; pos = end;
        }
        double u = ranks - b.Length * (b.Length + 1d) / 2, mean = (double)a.Length * b.Length / 2, n = all.Length;
        double variance = (double)a.Length * b.Length / 12 * ((n + 1) - ties / (n * (n - 1)));
        if (variance <= 0) return 1;
        double z = Math.Max(0, (Math.Abs(u - mean) - .5) / Math.Sqrt(variance));
        return Math.Clamp(2 * (1 - NormalCdf(z)), 0, 1);
    }
    private static double NormalCdf(double z) { double t = 1 / (1 + .2316419 * Math.Abs(z)), d = .3989422804 * Math.Exp(-z * z / 2), p = 1 - d * t * (.3193815 + t * (-.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return z >= 0 ? p : 1 - p; }
    private static double GammaQ(double a, double x) { if (x < 0 || a <= 0) return double.NaN; if (x < a + 1) return 1 - GammaSeries(a, x); double b = x + 1 - a, c = 1e30, d = 1 / b, h = d; for (int i = 1; i <= 200; i++) { double an = -i * (i - a); b += 2; d = an * d + b; if (Math.Abs(d) < 1e-30) d = 1e-30; c = b + an / c; if (Math.Abs(c) < 1e-30) c = 1e-30; d = 1 / d; double delta = d * c; h *= delta; if (Math.Abs(delta - 1) < 1e-12) break; } return Math.Exp(-x + a * Math.Log(x) - LogGamma(a)) * h; }
    private static double GammaSeries(double a, double x) { if (x <= 0) return 0; double sum = 1 / a, delta = sum, ap = a; for (int n = 1; n <= 200; n++) { ap++; delta *= x / ap; sum += delta; if (Math.Abs(delta) < Math.Abs(sum) * 1e-12) break; } return sum * Math.Exp(-x + a * Math.Log(x) - LogGamma(a)); }
    private static double LogGamma(double x) { double[] c = { 76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, .1208650973866179e-2, -.5395239384953e-5 }; double y = x, t = x + 5.5; t -= (x + .5) * Math.Log(t); double s = 1.000000000190015; foreach (double v in c) s += v / ++y; return -t + Math.Log(2.5066282746310005 * s / x); }
    internal static double CliffsDelta(double[] a, double[] b)
    {
        if (a.Length == 0 || b.Length == 0) return double.NaN;
        double[] sorted = b.OrderBy(v => v).ToArray(); long wins = 0, losses = 0;
        foreach (double value in a) { wins += Bound(sorted, value, false); losses += sorted.Length - Bound(sorted, value, true); }
        return (wins - losses) / (double)((long)a.Length * b.Length);
    }
    private static int Bound(double[] sorted, double value, bool upper) { int lo = 0, hi = sorted.Length; while (lo < hi) { int mid = (lo + hi) / 2; if (sorted[mid] < value || (upper && sorted[mid] == value)) lo = mid + 1; else hi = mid; } return lo; }
    internal static (int A, int B, double Delta) LargestPair(double[][] groups)
    {
        int a = 0, b = 1; double best = double.NaN;
        for (int i = 0; i < groups.Length; i++) for (int j = i + 1; j < groups.Length; j++) { double d = CliffsDelta(groups[i], groups[j]); if (double.IsFinite(d) && (!double.IsFinite(best) || Math.Abs(d) > Math.Abs(best))) { a = i; b = j; best = d; } }
        return (a, b, best);
    }
    // TostP is retained for source compatibility, but a bootstrap tail fraction is NOT a TOST p-value.
    internal static (double Low, double High, double TostP) DeltaInterval(double[] a, double[] b, double margin, Random random, int resamples = 400, double intervalAlpha = .05)
    {
        if (a.Length < 4 || b.Length < 4 || resamples < 20) return (double.NaN, double.NaN, double.NaN);
        double[] draws = Enumerable.Range(0, resamples).Select(_ => CliffsDelta(Sample(a, a.Length, random), Sample(b, b.Length, random))).ToArray();
        return (ScientificMath.Quantile(draws, intervalAlpha / 2), ScientificMath.Quantile(draws, 1 - intervalAlpha / 2), double.NaN);
    }
    internal static double MdeFromCurve(double[] effects, double[] power, double target = MdePowerTarget)
    {
        if (effects.Length != power.Length || effects.Length < 2 || power.Any(x => !double.IsFinite(x)) || power[0] >= target) return double.NaN;
        // Do not manufacture monotonicity. Interpolate the first observed upward crossing and
        // retain the complete noisy curve in the export; this is a grid estimate, not a guarantee.
        for (int i = 1; i < effects.Length; i++)
            if (power[i] >= target && power[i - 1] < target && effects[i] > effects[i - 1])
                return effects[i - 1] + (effects[i] - effects[i - 1]) * (target - power[i - 1]) / (power[i] - power[i - 1]) - 1;
        return double.NaN;
    }
    internal static string Verdict(bool applicable, double adjustedP, double alpha, double low, double high, double margin)
    {
        if (!applicable) return "not_applicable";
        if (double.IsFinite(adjustedP) && adjustedP < alpha) return "difference";
        if (!double.IsFinite(low) || !double.IsFinite(high)) return "insufficient";
        return low > -margin && high < margin ? "equivalent" : "insufficient";
    }
    internal static (AnalysisData Calibration, AnalysisData Analysis) SplitEntities(AnalysisData data, int seed)
    {
        if (data.GroupCounts.Any(n => n < 8)) throw new InvalidDataException("Split calibration requires at least eight usable entities per independent group.");
        var rng = new Random(ScientificMath.Seed(seed, "split-entities")); var selected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string group in data.GroupNames)
        {
            string[] keys = data.Entities.Where(e => e.Group.Equals(group, StringComparison.OrdinalIgnoreCase)).Select(e => Key(e.Group, e.Entity)).OrderBy(x => x, StringComparer.OrdinalIgnoreCase).ToArray();
            Shuffle(keys, rng); foreach (string key in keys.Take(keys.Length / 2)) selected.Add(key);
        }
        AnalysisData Part(bool first) => Build(data.Observations.Where(o => selected.Contains(Key(o.Group, o.Entity)) == first).ToList(), data.MinValueApplied, data.MaxValueApplied, data.MinMeasurementsApplied);
        return (Part(true), Part(false));
    }
    private static void Shuffle<T>(T[] values, Random random) { for (int i = values.Length - 1; i > 0; i--) { int j = random.Next(i + 1); (values[i], values[j]) = (values[j], values[i]); } }
}
