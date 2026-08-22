using System.Globalization;

namespace MvsAnalyzer;

internal static class AnalysisEngine
{
    internal const string EngineVersion = "1.2.0";
    /// <summary>Effect multipliers used by the deep calibration. The first entry is a pure null run: it passes through the same</summary>
    /// <summary>simulation pipeline as the others, so a metric that still fires there is inflating its own false alarm rate.</summary>
    internal static readonly double[] EffectGrid = { 1.00, 1.02, 1.05, 1.10, 1.20 };
    internal const double MdePowerTarget = .80;
    internal const double CandidateMaxFpr = .075, CandidateMinPower = .70, CandidateMinScore = 60;
    internal static readonly string[] MetricKeys = { "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad", "normalized_iqr", "mean", "rms", "range" };

    public static AnalysisData Build(List<Observation> observations, int minValue = -1000000, int maxValue = 1000000, int minMeasurements = 6)
    {
        if (maxValue <= minValue) throw new ArgumentOutOfRangeException(nameof(maxValue), "The maximum value must be greater than the minimum value.");
        if (minMeasurements < 2) throw new ArgumentOutOfRangeException(nameof(minMeasurements), "At least two measurements per entity are required.");
        var groups = observations.Select(x => x.Group).Distinct(StringComparer.OrdinalIgnoreCase).Take(11).ToList();
        if (groups.Count < 2 || groups.Count > 10) throw new InvalidDataException("Use 2\u201310 independent groups in one run.");
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
        return new AnalysisData
        {
            Observations = valid,
            Entities = entities,
            GroupNames = groups.ToArray(),
            GroupCounts = counts,
            ValidRows = valid.Count,
            MedianMeasurements = Median(entities.Select(x => (double)x.Measurements).ToArray()),
            DistributionProxy = DistributionProxy(valid.Select(x => x.Value).ToArray()),
            MinValueApplied = minValue,
            MaxValueApplied = maxValue,
            MinMeasurementsApplied = minMeasurements,
            MeasurementName = valid.First().Variable,
            Unit = valid.Select(x => x.Unit).FirstOrDefault(x => !string.IsNullOrWhiteSpace(x)) ?? ""
        };
    }

    public static List<Observation> Demo()
    {
        var r = new Random(7791); var output = new List<Observation>();
        for (int g = 0; g < 3; g++) for (int e = 1; e <= 30; e++) for (int s = 1; s <= 50; s++) output.Add(new Observation($"G{g + 1}_{e}", $"Group {g + 1}", 100 + g * 7 + 12 * Normal(r), s, "demo_measurement", "unit"));
        return output;
    }

    public static List<CalibrationRow> Calibrate(AnalysisData data, int repetitions, double effect, int seed, IProgress<ProgressInfo> progress, CancellationToken token, string scenario = "location", double outlierRate = .02, double missingRate = 0, double alpha = .05)
    {
        if (repetitions < 100) throw new ArgumentOutOfRangeException(nameof(repetitions), "At least 100 simulations are required.");
        if (effect <= 1) throw new ArgumentOutOfRangeException(nameof(effect), "The effect multiplier must be greater than 1.");
        if (alpha is <= 0 or >= 1) throw new ArgumentOutOfRangeException(nameof(alpha), "Alpha must be between 0 and 1.");

        // Raw measurements are indexed once. Without this cache every simulated entity
        // scanned the full observation list, which made calibration quadratic.
        Dictionary<string, double[]> values = ObservationCache(data);
        EntityResult[][] groupEntities = GroupEntities(data);
        double[][][] observed = GroupMetricArrays(data);
        int m = MetricKeys.Length;
        int[] falsePositives = new int[m], detections = new int[m], evaluated = new int[m];
        int[][] gridDetections = Enumerable.Range(0, m).Select(_ => new int[EffectGrid.Length]).ToArray();
        int[][] gridEvaluated = Enumerable.Range(0, m).Select(_ => new int[EffectGrid.Length]).ToArray();
        double[][] pooled = new double[m][];
        bool[] usable = new bool[m];
        for (int metric = 0; metric < m; metric++)
        {
            usable[metric] = observed.All(g => g[metric].Length >= 4);
            pooled[metric] = usable[metric] ? observed.SelectMany(g => g[metric]).ToArray() : Array.Empty<double>();
        }
        // One generator per metric keeps a metric's numbers identical even if the
        // metric list changes length or order in a later version.
        Random[] random = Enumerable.Range(0, m).Select(i => new Random(unchecked(seed + 7919 * (i + 1)))).ToArray();
        int every = Math.Max(1, repetitions / 200);

        for (int rep = 0; rep < repetitions; rep++)
        {
            token.ThrowIfCancellationRequested();
            for (int metric = 0; metric < m; metric++)
            {
                if (!usable[metric]) continue;
                Random r = random[metric];
                double[][] nullGroups = observed.Select(g => Sample(pooled[metric], g[metric].Length, r)).ToArray();
                if (GlobalP(nullGroups) < alpha) falsePositives[metric]++;
                double[][] alternative = SimulatedMetricGroups(data, values, groupEntities, metric, r, effect, scenario, outlierRate, missingRate);
                if (alternative.All(x => x.Length >= 4) && GlobalP(alternative) < alpha) detections[metric]++;
                evaluated[metric]++;
                // Deep calibration: each repetition also tests one point of the effect grid, so the
                // cost stays close to the old single-effect run while a full power curve is collected.
                int gp = rep % EffectGrid.Length;
                double[][] gridGroups = SimulatedMetricGroups(data, values, groupEntities, metric, r, EffectGrid[gp], scenario, outlierRate, missingRate);
                if (gridGroups.All(x => x.Length >= 4)) { gridEvaluated[metric][gp]++; if (GlobalP(gridGroups) < alpha) gridDetections[metric][gp]++; }
            }
            if ((rep + 1) % every == 0 || rep + 1 == repetitions) progress.Report(new ProgressInfo((rep + 1d) / repetitions, $"Simulation {rep + 1:N0} of {repetitions:N0}", "Raw-value scenarios, false alarms and sensitivity"));
        }

        var rows = new List<CalibrationRow>();
        for (int metric = 0; metric < m; metric++)
        {
            if (evaluated[metric] == 0)
            {
                // Not applicable to this dataset (for example a ratio metric on values centred at zero).
                rows.Add(new CalibrationRow(MetricKeys[metric], double.NaN, double.NaN, double.NaN, double.NaN, double.NaN, double.NaN, false));
                continue;
            }
            double f = falsePositives[metric] / (double)evaluated[metric], p = detections[metric] / (double)evaluated[metric];
            double falseAlarm = Math.Exp(-Math.Max(0, f - alpha) / Math.Max(alpha, 1e-9));
            // Repeatability is now measured by split-half resampling instead of being derived from power.
            double repeatability = EstimateRepeatability(observed.Select(g => g[metric]).ToArray(), new Random(unchecked(seed + 15486071 * (metric + 1))));
            double robustness = EstimateRobustness(data, values, metric, seed + metric);
            // Coverage used to be the constant 0.95, which could not tell metrics apart.
            // It is now measured: how often a 95% bootstrap interval really contains the truth.
            double coverage = EstimateCoverage(pooled[metric], new Random(unchecked(seed + 104729 * (metric + 1))));
            if (double.IsNaN(repeatability) || double.IsNaN(coverage))
            {
                // Cannot be judged on this dataset; report it instead of publishing a NaN score.
                rows.Add(new CalibrationRow(MetricKeys[metric], f, p, double.NaN, robustness, repeatability, coverage, false));
                continue;
            }
            double score = 100 * Math.Pow(Math.Max(p, 1e-9), .30) * Math.Pow(falseAlarm, .25) * Math.Pow(robustness, .20) * Math.Pow(repeatability, .15) * Math.Pow(coverage, .10);
            double[] curve = new double[EffectGrid.Length];
            for (int point = 0; point < EffectGrid.Length; point++) curve[point] = gridEvaluated[metric][point] == 0 ? double.NaN : gridDetections[metric][point] / (double)gridEvaluated[metric][point];
            // A metric that fires on the zero-effect grid point is not merely weak, it is wrong.
            // The first grid point is NOT a null: it resimulates the real groups with effect 1.00,
            // so any genuine difference in the data stays in it. Judging inflation by that point
            // marked healthy runs as broken. The honest false alarm rate is f, measured by pooling
            // all groups together and resampling, where no difference can exist by construction.
            bool inflated = double.IsFinite(f) && f > Math.Max(alpha * 1.5, alpha + .02);
            double mde = MdeFromCurve(EffectGrid, curve, MdePowerTarget);
            string curveText = string.Join("|", EffectGrid.Select((e, point) => string.Format(CultureInfo.InvariantCulture, "{0:0.##}:{1:0.###}", e, curve[point])));
            rows.Add(new CalibrationRow(MetricKeys[metric], f, p, score, robustness, repeatability, coverage, true, mde, inflated, curveText));
        }
        return rows;
    }

    public static List<ResultRow> Results(AnalysisData data, List<CalibrationRow> calibration, IProgress<ProgressInfo> progress, CancellationToken token, double alpha = .05, double equivalenceMargin = .147, int seed = 20260719)
    {
        progress.Report(new ProgressInfo(.2, "Calculating entity metrics", "Stage 1 of 4"));
        double[][][] arrays = GroupMetricArrays(data);
        var rows = new List<ResultRow>();
        for (int metric = 0; metric < MetricKeys.Length; metric++)
        {
            token.ThrowIfCancellationRequested();
            CalibrationRow c = calibration.Single(x => x.Metric == MetricKeys[metric]);
            double[] med = arrays.Select(g => Median(g[metric])).ToArray();
            bool applicable = c.Applicable && arrays.All(g => g[metric].Length > 0);
            double low = med.Min(), high = med.Max();
            double p = applicable ? GlobalP(arrays.Select(g => g[metric]).ToArray()) : double.NaN;
            bool candidate = applicable && c.Fpr <= CandidateMaxFpr && c.Power >= CandidateMinPower && c.Score >= CandidateMinScore;
            string summary = string.Join("; ", data.GroupNames.Select((g, i) => string.Format(CultureInfo.InvariantCulture, "{0}={1:0.###}", g, med[i])));
            double effectValue = double.NaN, effectLow = double.NaN, effectHigh = double.NaN, tost = double.NaN;
            string pairText = ""; double pairPercent = double.NaN;
            if (applicable)
            {
                double[][] metricGroups = arrays.Select(g => g[metric]).ToArray();
                var pair = LargestPair(metricGroups);
                effectValue = pair.Delta;
                var interval = DeltaInterval(metricGroups[pair.A], metricGroups[pair.B], equivalenceMargin, new Random(unchecked(seed + 32452843 * (metric + 1))));
                effectLow = interval.Low; effectHigh = interval.High; tost = interval.TostP;
                if (pair.A != pair.B && pair.A < med.Length && pair.B < med.Length)
                {
                    int hi = med[pair.A] >= med[pair.B] ? pair.A : pair.B;
                    int lo = hi == pair.A ? pair.B : pair.A;
                    pairText = data.GroupNames[hi] + " > " + data.GroupNames[lo];
                    double basis = Math.Abs(med[lo]);
                    pairPercent = basis > 1e-12 ? Math.Abs(med[hi] - med[lo]) / basis * 100 : double.NaN;
                }
            }
            string verdict = Verdict(applicable, p, alpha, effectLow, effectHigh, equivalenceMargin);
            rows.Add(new ResultRow(MetricKeys[metric], med[0], med.Length > 1 ? med[1] : double.NaN, high - low, p, c.Fpr, c.Power, c.Score, candidate, summary, c.Robustness, c.Repeatability, c.Coverage, applicable, false, effectValue, effectLow, effectHigh, tost, c.Mde, c.FprInflated, verdict, pairText, pairPercent));
        }
        var ordered = rows.OrderByDescending(x => double.IsNaN(x.Score) ? double.NegativeInfinity : x.Score).ToList();
        int accepted = 0; double lastAccepted = double.NaN;
        for (int i = 0; i < ordered.Count; i++)
        {
            bool passesRules = ordered[i].Candidate;
            bool keep = passesRules && accepted < 4;
            if (keep) { accepted++; lastAccepted = ordered[i].Score; }
            // A metric can pass every rule and still be cut by the four-candidate cap, or land
            // within noise of the last accepted one. Hiding that invites cherry picking.
            bool nearMiss = !keep && ordered[i].Applicable && (passesRules ||
                (double.IsFinite(lastAccepted) && double.IsFinite(ordered[i].Score) && ordered[i].Score >= lastAccepted - 2));
            ordered[i] = ordered[i] with { Candidate = keep, NearMiss = nearMiss };
        }
        progress.Report(new ProgressInfo(1, "Results ready", "Global comparison of all groups"));
        return ordered;
    }

    internal static string Key(string group, string entity) => group + '\u001f' + entity;

    private static Dictionary<string, double[]> ObservationCache(AnalysisData data)
    {
        var buckets = new Dictionary<string, List<double>>(StringComparer.OrdinalIgnoreCase);
        foreach (Observation o in data.Observations)
        {
            string key = Key(o.Group, o.Entity);
            if (!buckets.TryGetValue(key, out List<double>? list)) { list = new List<double>(); buckets[key] = list; }
            list.Add(o.Value);
        }
        var cache = new Dictionary<string, double[]>(StringComparer.OrdinalIgnoreCase);
        foreach (var pair in buckets) cache[pair.Key] = pair.Value.ToArray();
        return cache;
    }

    private static EntityResult[][] GroupEntities(AnalysisData data) => data.GroupNames.Select(g => data.Entities.Where(x => x.Group.Equals(g, StringComparison.OrdinalIgnoreCase)).ToArray()).ToArray();

    private static double[][][] GroupMetricArrays(AnalysisData data) => GroupEntities(data).Select(e => Enumerable.Range(0, MetricKeys.Length).Select(m => e.Select(x => x.Metrics[m]).Where(double.IsFinite).ToArray()).ToArray()).ToArray();

    private static double[][] SimulatedMetricGroups(AnalysisData data, Dictionary<string, double[]> values, EntityResult[][] groupEntities, int metric, Random random, double effect, string scenario, double outlierRate, double missingRate)
    {
        var output = new double[data.GroupNames.Length][];
        for (int gi = 0; gi < data.GroupNames.Length; gi++)
        {
            EntityResult[] entities = groupEntities[gi];
            var simulated = new List<double>(entities.Length);
            for (int n = 0; n < entities.Length; n++)
            {
                EntityResult chosen = entities[random.Next(entities.Length)];
                if (!values.TryGetValue(Key(chosen.Group, chosen.Entity), out double[]? source) || source.Length == 0) continue;
                double[] raw = Sample(source, source.Length, random);
                if (gi == data.GroupNames.Length - 1) ApplyScenario(raw, effect, scenario, random, outlierRate);
                if (missingRate > 0) raw = raw.Where(_ => random.NextDouble() >= missingRate).ToArray();
                if (raw.Length >= 2) { double v = Metrics(raw)[metric]; if (double.IsFinite(v)) simulated.Add(v); }
            }
            output[gi] = simulated.ToArray();
        }
        return output;
    }

    private static void ApplyScenario(double[] x, double effect, string scenario, Random r, double outlierRate)
    {
        if (x.Length == 0) return;
        double center = x.Average(), sd = Math.Sqrt(x.Sum(v => (v - center) * (v - center)) / Math.Max(1, x.Length - 1));
        for (int i = 0; i < x.Length; i++)
        {
            if (scenario == "variability") x[i] = center + (x[i] - center) * effect;
            else if (scenario == "decrease") x[i] -= Math.Max(Math.Abs(center), sd) * (effect - 1);
            else x[i] += Math.Max(Math.Abs(center), sd) * (effect - 1);
            if (r.NextDouble() < outlierRate) x[i] += (r.Next(2) == 0 ? -1 : 1) * Math.Max(sd, 1) * 5;
        }
    }

    private static double EstimateRobustness(AnalysisData data, Dictionary<string, double[]> values, int metric, int seed)
    {
        var r = new Random(seed);
        double[] original = data.Entities.Select(x => x.Metrics[metric]).Where(double.IsFinite).ToArray();
        if (original.Length == 0) return 0;
        var contaminated = new List<double>();
        foreach (EntityResult e in data.Entities)
        {
            if (!values.TryGetValue(Key(e.Group, e.Entity), out double[]? source) || source.Length == 0) continue;
            double[] x = (double[])source.Clone();
            ApplyScenario(x, 1, "location", r, .05);
            double v = Metrics(x)[metric];
            if (double.IsFinite(v)) contaminated.Add(v);
        }
        if (contaminated.Count == 0) return 0;
        double scale = Math.Max(Math.Abs(Median(original)), StandardDeviation(original));
        return Math.Clamp(1 - Math.Abs(Median(contaminated.ToArray()) - Median(original)) / Math.Max(scale, 1e-9), 0, 1);
    }

    /// <summary>
    /// Empirical coverage of the 95% percentile bootstrap interval for the entity-level
    /// median of one metric. A simulated study is drawn from the observed metric values,
    /// an interval is built inside it, and we check whether the observed truth falls inside.
    /// A metric whose intervals are too narrow now scores lower instead of being credited 0.95.
    /// </summary>
    internal static double EstimateCoverage(double[] entityValues, Random random, int outerTrials = 200, int innerResamples = 200)
    {
        if (entityValues.Length < 4) return double.NaN;
        double[] sortedTruth = (double[])entityValues.Clone();
        double truth = MedianDestructive(sortedTruth);
        int n = entityValues.Length, contains = 0;
        var innerMedians = new double[innerResamples];
        int lowIndex = (int)Math.Floor(.025 * (innerResamples - 1)), highIndex = (int)Math.Ceiling(.975 * (innerResamples - 1));
        for (int trial = 0; trial < outerTrials; trial++)
        {
            double[] study = Sample(entityValues, n, random);
            for (int i = 0; i < innerResamples; i++) innerMedians[i] = MedianDestructive(Sample(study, n, random));
            Array.Sort(innerMedians);
            if (truth >= innerMedians[lowIndex] && truth <= innerMedians[highIndex]) contains++;
        }
        return Math.Clamp(contains / (double)outerTrials, .01, 1);
    }

    private static double MedianDestructive(double[] x) { if (x.Length == 0) return double.NaN; Array.Sort(x); return Quantile(x, .5); }


    /// <summary>
    /// Repeatability measured by repeated split-half resampling of the entities.
    /// Each group is randomly split in two; the metric's group median is computed in both
    /// halves and the two answers are compared. A metric that gives a different picture of
    /// the same groups when a different half of the entities is used is not repeatable.
    /// Before 1.1.0 this value was derived from power, which double counted power and made
    /// unrelated metrics identical to many decimal places.
    /// </summary>
    internal static double EstimateRepeatability(double[][] groupValues, Random random, int splits = 50)
    {
        if (groupValues.Length == 0) return double.NaN;
        double[][] clean = groupValues.Select(g => g.Where(double.IsFinite).ToArray()).ToArray();
        if (clean.Any(g => g.Length < 4)) return double.NaN;
        double[] all = clean.SelectMany(x => x).ToArray();
        double scale = Math.Max(Math.Abs(MedianDestructive((double[])all.Clone())), StandardDeviation(all));
        if (!double.IsFinite(scale) || scale <= 1e-12) return 1;
        double total = 0; int used = 0;
        for (int split = 0; split < splits; split++)
        {
            double sum = 0; int counted = 0; bool ok = true;
            foreach (double[] group in clean)
            {
                double[] shuffled = (double[])group.Clone();
                for (int i = shuffled.Length - 1; i > 0; i--) { int j = random.Next(i + 1); (shuffled[i], shuffled[j]) = (shuffled[j], shuffled[i]); }
                int half = shuffled.Length / 2;
                double a = MedianDestructive(shuffled[..half]), b = MedianDestructive(shuffled[half..]);
                if (!double.IsFinite(a) || !double.IsFinite(b)) { ok = false; break; }
                sum += Math.Abs(a - b); counted++;
            }
            if (!ok || counted == 0) continue;
            total += sum / counted; used++;
        }
        if (used == 0) return double.NaN;
        return Math.Clamp(1 - total / used / scale, .01, 1);
    }

    private static double GlobalP(double[][] groups) => groups.Length == 2 ? MannWhitneyP(groups[0], groups[1]) : KruskalWallisP(groups);

    internal static double KruskalWallisP(double[][] groups)
    {
        var all = groups.SelectMany((g, gi) => g.Select(v => (v, gi))).OrderBy(x => x.v).ToArray();
        if (all.Length == 0 || groups.Any(g => g.Length == 0)) return double.NaN;
        double[] rankSums = new double[groups.Length]; double tie = 0; int pos = 0;
        while (pos < all.Length)
        {
            int end = pos + 1; while (end < all.Length && all[end].v == all[pos].v) end++;
            double rank = (pos + 1 + end) / 2d; int t = end - pos; if (t > 1) tie += t * t * t - t;
            for (int i = pos; i < end; i++) rankSums[all[i].gi] += rank;
            pos = end;
        }
        double n = all.Length, h = 12 / (n * (n + 1)) * rankSums.Select((r, i) => r * r / groups[i].Length).Sum() - 3 * (n + 1);
        double correction = 1 - tie / (n * n * n - n); h /= Math.Max(correction, 1e-12);
        return GammaQ((groups.Length - 1) / 2d, h / 2);
    }

    internal static double MannWhitneyP(double[] a, double[] b)
    {
        if (a.Length == 0 || b.Length == 0) return double.NaN;
        var c = a.Select(v => (v, g: 0)).Concat(b.Select(v => (v, g: 1))).OrderBy(x => x.v).ToArray();
        double rb = 0, tie = 0; int pos = 0;
        while (pos < c.Length)
        {
            int end = pos + 1; while (end < c.Length && c[end].v == c[pos].v) end++;
            double rank = (pos + 1 + end) / 2d; int t = end - pos; if (t > 1) tie += t * t * t - t;
            for (int i = pos; i < end; i++) if (c[i].g == 1) rb += rank;
            pos = end;
        }
        double u = rb - b.Length * (b.Length + 1) / 2d, mean = a.Length * b.Length / 2d, n = c.Length;
        double variance = a.Length * b.Length / 12d * ((n + 1) - tie / (n * (n - 1)));
        if (variance <= 0) return 1;
        double z = Math.Max(0, (Math.Abs(u - mean) - .5) / Math.Sqrt(variance));
        return Math.Clamp(2 * (1 - NormalCdf(z)), 0, 1);
    }

    private static double[] Metrics(double[] v)
    {
        double[] s = v.OrderBy(x => x).ToArray();
        double median = Quantile(s, .5), mean = v.Average(), sd = StandardDeviation(v);
        double mad = Median(v.Select(x => Math.Abs(x - median)).ToArray()), iqr = Quantile(s, .75) - Quantile(s, .25);
        double cv = Math.Abs(mean) < 1e-12 ? double.NaN : sd / Math.Abs(mean);
        double nm = Math.Abs(median) < 1e-12 ? double.NaN : mad / Math.Abs(median);
        double ni = Math.Abs(median) < 1e-12 ? double.NaN : iqr / Math.Abs(median);
        double rms = Math.Sqrt(v.Average(x => x * x));
        return new[] { median, sd, cv, mad, iqr, nm, ni, mean, rms, s[^1] - s[0] };
    }

    private static double[] Sample(double[] source, int count, Random r) { var x = new double[count]; for (int i = 0; i < count; i++) x[i] = source[r.Next(source.Length)]; return x; }
    private static double Median(double[] x) => x.Length == 0 ? double.NaN : Quantile(x.OrderBy(v => v).ToArray(), .5);
    private static double Quantile(double[] s, double q) { double p = (s.Length - 1) * q; int lo = (int)Math.Floor(p), hi = (int)Math.Ceiling(p); return s[lo] + (s[hi] - s[lo]) * (p - lo); }
    private static double StandardDeviation(double[] x) { if (x.Length < 2) return 0; double m = x.Average(); return Math.Sqrt(x.Sum(v => (v - m) * (v - m)) / (x.Length - 1)); }
    private static string DistributionProxy(double[] x) { double m = x.Average(), sd = StandardDeviation(x), skew = x.Length < 3 || sd == 0 ? 0 : x.Sum(v => Math.Pow((v - m) / sd, 3)) * x.Length / ((x.Length - 1d) * (x.Length - 2d)); return skew > 1.5 ? "strongly right-skewed" : skew > .7 ? "moderately right-skewed" : "approximately symmetric"; }
    private static double Normal(Random r) { double u = Math.Max(1e-12, r.NextDouble()), v = r.NextDouble(); return Math.Sqrt(-2 * Math.Log(u)) * Math.Cos(2 * Math.PI * v); }
    private static double NormalCdf(double z) { double t = 1 / (1 + .2316419 * Math.Abs(z)), d = .3989422804 * Math.Exp(-z * z / 2), p = 1 - d * t * (.3193815 + t * (-.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return z >= 0 ? p : 1 - p; }
    private static double GammaQ(double a, double x) { if (x < 0 || a <= 0) return double.NaN; if (x < a + 1) return 1 - GammaSeries(a, x); double b = x + 1 - a, c = 1 / 1e-30, d = 1 / b, h = d; for (int i = 1; i <= 100; i++) { double an = -i * (i - a); b += 2; d = an * d + b; if (Math.Abs(d) < 1e-30) d = 1e-30; c = b + an / c; if (Math.Abs(c) < 1e-30) c = 1e-30; d = 1 / d; double del = d * c; h *= del; if (Math.Abs(del - 1) < 3e-7) break; } return Math.Exp(-x + a * Math.Log(x) - LogGamma(a)) * h; }
    private static double GammaSeries(double a, double x) { if (x <= 0) return 0; double sum = 1 / a, del = sum, ap = a; for (int n = 1; n <= 100; n++) { ap++; del *= x / ap; sum += del; if (Math.Abs(del) < Math.Abs(sum) * 3e-7) break; } return sum * Math.Exp(-x + a * Math.Log(x) - LogGamma(a)); }
    private static double LogGamma(double x) { double[] c = { 76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, .1208650973866179e-2, -.5395239384953e-5 }; double y = x, tmp = x + 5.5; tmp -= (x + .5) * Math.Log(tmp); double ser = 1.000000000190015; for (int j = 0; j < 6; j++) ser += c[j] / ++y; return -tmp + Math.Log(2.5066282746310005 * ser / x); }

    /// <summary>
    /// Cliffs delta: how often a value drawn from one group beats a value drawn from the other,
    /// minus the reverse. Ranges from -1 to 1, needs no distribution assumption and matches the
    /// rank tests already used here. 0 means the two groups overlap completely.
    /// </summary>
    internal static double CliffsDelta(double[] a, double[] b)
    {
        if (a.Length == 0 || b.Length == 0) return double.NaN;
        double[] sorted = (double[])b.Clone(); Array.Sort(sorted);
        long greater = 0, less = 0;
        foreach (double v in a)
        {
            less += LowerBound(sorted, v);
            greater += sorted.Length - UpperBound(sorted, v);
        }
        return (greater - less) / (double)((long)a.Length * b.Length);
    }
    private static int LowerBound(double[] s, double v) { int lo = 0, hi = s.Length; while (lo < hi) { int mid = (lo + hi) / 2; if (s[mid] < v) lo = mid + 1; else hi = mid; } return lo; }
    private static int UpperBound(double[] s, double v) { int lo = 0, hi = s.Length; while (lo < hi) { int mid = (lo + hi) / 2; if (s[mid] <= v) lo = mid + 1; else hi = mid; } return lo; }

    /// <summary>The pair of groups that are furthest apart. With two groups this is simply the only pair.</summary>
    internal static (int A, int B, double Delta) LargestPair(double[][] groups)
    {
        int bestA = 0, bestB = groups.Length > 1 ? 1 : 0; double best = double.NaN;
        for (int i = 0; i < groups.Length; i++)
            for (int j = i + 1; j < groups.Length; j++)
            {
                double d = CliffsDelta(groups[i], groups[j]);
                if (!double.IsFinite(d)) continue;
                if (!double.IsFinite(best) || Math.Abs(d) > Math.Abs(best)) { best = d; bestA = i; bestB = j; }
            }
        return (bestA, bestB, best);
    }

    /// <summary>
    /// Percentile bootstrap interval for Cliffs delta plus the two one-sided equivalence tests.
    /// The returned TOST value is the larger of the two one-sided p-values, so a small number is
    /// evidence that the groups really are within the margin of each other.
    /// </summary>
    internal static (double Low, double High, double TostP) DeltaInterval(double[] a, double[] b, double margin, Random random, int resamples = 400)
    {
        if (a.Length < 4 || b.Length < 4) return (double.NaN, double.NaN, double.NaN);
        var draws = new double[resamples];
        for (int i = 0; i < resamples; i++) draws[i] = CliffsDelta(Sample(a, a.Length, random), Sample(b, b.Length, random));
        double[] clean = draws.Where(double.IsFinite).ToArray();
        if (clean.Length < 20) return (double.NaN, double.NaN, double.NaN);
        Array.Sort(clean);
        double low = clean[(int)Math.Floor(.025 * (clean.Length - 1))], high = clean[(int)Math.Ceiling(.975 * (clean.Length - 1))];
        double above = clean.Count(x => x >= margin) / (double)clean.Length;
        double below = clean.Count(x => x <= -margin) / (double)clean.Length;
        return (low, high, Math.Max(above, below));
    }

    /// <summary>Smallest simulated effect whose power reaches the target, interpolated between grid points.</summary>
    internal static double MdeFromCurve(double[] effects, double[] power, double target = MdePowerTarget)
    {
        // Index 0 is the null point (no injected effect). Reaching the target there means the
        // test fires without a real difference, which is a broken calibration, not a small MDE.
        for (int i = 1; i < effects.Length && i < power.Length; i++)
        {
            if (!double.IsFinite(power[i]) || power[i] < target) continue;
            if (i == 1) return effects[i] - 1;
            double p0 = power[i - 1], p1 = power[i];
            if (!double.IsFinite(p0) || p1 <= p0) return effects[i] - 1;
            double t = (target - p0) / (p1 - p0);
            return effects[i - 1] + (effects[i] - effects[i - 1]) * t - 1;
        }
        return double.NaN;
    }

    /// <summary>
    /// Four honest outcomes instead of two. "insufficient" is the one the program could not say before:
    /// the interval covers both a real difference and no difference, so the data cannot decide.
    /// </summary>
    internal static string Verdict(bool applicable, double p, double alpha, double low, double high, double margin)
    {
        if (!applicable) return "not_applicable";
        if (!double.IsFinite(low) || !double.IsFinite(high)) return "insufficient";
        if (low >= -margin && high <= margin) return "equivalent";
        if (double.IsFinite(p) && p < alpha && (low > 0 || high < 0)) return "difference";
        return "insufficient";
    }

    /// <summary>
    /// Splits the entities of every group in half. One half calibrates the metrics, the other half
    /// answers the question, so the metric is never chosen on the same rows that produce the result.
    /// </summary>
    internal static (AnalysisData Calibration, AnalysisData Analysis) SplitEntities(AnalysisData data, int seed)
    {
        var random = new Random(unchecked(seed * 31 + 17));
        var chosen = new List<string>();
        foreach (string group in data.GroupNames)
        {
            var inGroup = data.Entities.Where(x => x.Group.Equals(group, StringComparison.OrdinalIgnoreCase)).Select(x => Key(x.Group, x.Entity)).ToList();
            for (int i = inGroup.Count - 1; i > 0; i--) { int j = random.Next(i + 1); (inGroup[i], inGroup[j]) = (inGroup[j], inGroup[i]); }
            chosen.AddRange(inGroup.Take(inGroup.Count / 2));
        }
        var first = chosen.ToHashSet(StringComparer.OrdinalIgnoreCase);
        var left = data.Observations.Where(o => first.Contains(Key(o.Group, o.Entity))).ToList();
        var right = data.Observations.Where(o => !first.Contains(Key(o.Group, o.Entity))).ToList();
        try
        {
            AnalysisData calibrationHalf = Build(left, data.MinValueApplied, data.MaxValueApplied, data.MinMeasurementsApplied);
            AnalysisData analysisHalf = Build(right, data.MinValueApplied, data.MaxValueApplied, data.MinMeasurementsApplied);
            return (calibrationHalf, analysisHalf);
        }
        catch (Exception ex)
        {
            throw new InvalidDataException("Split calibration needs at least eight usable entities in every group, because each half must still hold four. " + ex.Message);
        }
    }
}
