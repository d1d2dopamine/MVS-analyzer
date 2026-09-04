using System.Globalization;

namespace MvsAnalyzer;

internal sealed record ClusterSummary(string Entity, int Group, int Count, double Mean, double WithinSumSquares);
internal sealed record VarianceFit(double[] Means, double[] Within, double[] Between, double NegativeLogLikelihood,
    bool Converged, bool AtBoundary, string Method, int Iterations);
internal sealed record VarianceGroup(string Group, int Entities, int Measurements, double Mean, double WithinVariance,
    double BetweenVariance, double ObservedCenterVariance, double MomentBetweenUntruncated, double Icc, string Status, double WithinLow = double.NaN, double WithinHigh = double.NaN, double BetweenLow = double.NaN, double BetweenHigh = double.NaN, int IntervalReplications = 0, string IntervalStatus = "not_computed");
internal sealed record VarianceTrack(string Track, double Statistic, double PValue, double AdjustedP, double Fpr,
    double FprLow, double FprHigh, double Power, double PowerLow, double PowerHigh, double EffectSdMultiplier,
    int ReferenceReplications, int ReferenceFailures, int EvaluationReplications, int NullFailures, int AlternativeFailures,
    string Verdict, string Status, double[] EffectGrid, double[] PowerCurve, double Mde, string MdeStatus);
internal sealed record VarianceReport(string EngineVersion, string Model, string DecisionFamily, int Seed, double Alpha,
    VarianceGroup[] Groups, VarianceTrack[] Tracks, string[] Warnings);

/// <summary>
/// Gaussian independent-group random intercept model, y_gij = mu_g + b_gi + e_gij.
/// Uses sufficient statistics and profile ML/REML, allowing unbalanced repeated measurements.
/// Equality of within/between components is tested while the OTHER component remains group-specific.
/// </summary>
internal static class VarianceAnalysis
{
    public static ClusterSummary[] Summaries(AnalysisData data) => data.Observations
        .GroupBy(o => AnalysisEngine.Key(o.Group, o.Entity), StringComparer.OrdinalIgnoreCase)
        .Select(g => { double mean = g.Average(o => o.Value); return new ClusterSummary(g.First().Entity,
            Array.FindIndex(data.GroupNames, n => n.Equals(g.First().Group, StringComparison.OrdinalIgnoreCase)), g.Count(), mean,
            g.Sum(o => (o.Value - mean) * (o.Value - mean))); }).ToArray();

    internal static VarianceFit Fit(ClusterSummary[] clusters, int groups, bool equalWithin = false, bool equalBetween = false,
        bool reml = false, CancellationToken token = default)
    {
        if (clusters.Length < 4 || clusters.Any(c => c.Count < 2) || Enumerable.Range(0, groups).Any(g => clusters.Count(c => c.Group == g) < 2))
            throw new InvalidDataException("Variance estimation needs repeated measurements and multiple entities in every group.");
        double overall = clusters.Sum(c => c.Mean * c.Count) / clusters.Sum(c => c.Count);
        double scale2 = clusters.Sum(c => c.WithinSumSquares + c.Count * Math.Pow(c.Mean - overall, 2)) / clusters.Sum(c => c.Count);
        if (!double.IsFinite(scale2) || scale2 <= 0)
            return new VarianceFit(Enumerable.Repeat(overall, groups).ToArray(), new double[groups], new double[groups], double.NaN, false, true, reml ? "REML" : "ML", 0);
        double scale = Math.Sqrt(scale2);
        ClusterSummary[] normalized = clusters.Select(c => c with { Mean = (c.Mean - overall) / scale, WithinSumSquares = c.WithinSumSquares / scale2 }).ToArray();
        int ns = equalWithin ? 1 : groups, nt = equalBetween ? 1 : groups, dim = ns + nt;
        var start = new double[dim];
        for (int g = 0; g < groups; g++)
        {
            ClusterSummary[] part = normalized.Where(c => c.Group == g).ToArray();
            double sigma = part.Sum(c => c.WithinSumSquares) / part.Sum(c => c.Count - 1);
            double tau = ScientificMath.Variance(part.Select(c => c.Mean).ToArray()) - sigma * part.Average(c => 1d / c.Count);
            start[equalWithin ? 0 : g] += Math.Log(Math.Max(sigma, 1e-6)) / (equalWithin ? groups : 1);
            start[ns + (equalBetween ? 0 : g)] += Math.Log(Math.Max(tau, 1e-5)) / (equalBetween ? groups : 1);
        }
        double[] Means(double[] parameters)
        {
            var weighted = new double[groups]; var weights = new double[groups];
            foreach (ClusterSummary c in normalized)
            {
                double s = Math.Exp(parameters[equalWithin ? 0 : c.Group]), t = Math.Exp(parameters[ns + (equalBetween ? 0 : c.Group)]);
                double w = 1 / (t + s / c.Count); weighted[c.Group] += w * c.Mean; weights[c.Group] += w;
            }
            return weighted.Select((x, g) => x / weights[g]).ToArray();
        }
        double Objective(double[] parameters)
        {
            double[] means = Means(parameters); var weights = new double[groups]; double nll = 0;
            foreach (ClusterSummary c in normalized)
            {
                double s = Math.Exp(parameters[equalWithin ? 0 : c.Group]), t = Math.Exp(parameters[ns + (equalBetween ? 0 : c.Group)]);
                double varianceMean = t + s / c.Count; weights[c.Group] += 1 / varianceMean;
                nll += .5 * ((c.Count - 1) * Math.Log(s) + Math.Log(s + c.Count * t)
                    + c.WithinSumSquares / s + Math.Pow(c.Mean - means[c.Group], 2) / varianceMean);
            }
            if (reml) nll += .5 * weights.Sum(Math.Log);
            return nll;
        }
        double[] lower = Enumerable.Repeat(-23.0, dim).ToArray(), upper = Enumerable.Repeat(8.0, dim).ToArray();
        OptimizationResult fit = NumericalMethods.Minimize(Objective, start, lower, upper, 4000, 1e-8, token);
        if (!fit.Converged)
        {
            var retry = NumericalMethods.Minimize(Objective, fit.Parameters, lower, upper, 6000, 1e-8, token);
            if (retry.Value <= fit.Value + 1e-7) fit = retry;
        }
        return new VarianceFit(Means(fit.Parameters).Select(x => overall + scale * x).ToArray(),
            Enumerable.Range(0, groups).Select(g => scale2 * Math.Exp(fit.Parameters[equalWithin ? 0 : g])).ToArray(),
            Enumerable.Range(0, groups).Select(g => scale2 * Math.Exp(fit.Parameters[ns + (equalBetween ? 0 : g)])).ToArray(),
            fit.Value, fit.Converged, fit.AtBoundary, reml ? "REML" : "ML", fit.Iterations);
    }

    internal static ClusterSummary[] Generate(ClusterSummary[] design, VarianceFit model, Random random,
        string track = "none", double effect = 1)
    {
        int last = model.Means.Length - 1;
        return design.Select(c =>
        {
            double s2 = model.Within[c.Group], t2 = model.Between[c.Group];
            if (c.Group == last && track == "within") s2 *= effect * effect;
            if (c.Group == last && track == "between") t2 *= effect * effect;
            double mean = model.Means[c.Group] + Math.Sqrt(t2) * ScientificMath.Gaussian(random) + Math.Sqrt(s2 / c.Count) * ScientificMath.Gaussian(random);
            double chi = 0; for (int j = 0; j < c.Count - 1; j++) { double z = ScientificMath.Gaussian(random); chi += z * z; }
            return c with { Mean = mean, WithinSumSquares = s2 * chi };
        }).ToArray();
    }
    private static double Statistic(ClusterSummary[] data, int groups, string track, CancellationToken token)
    {
        VarianceFit alternative = Fit(data, groups, token: token);
        VarianceFit nullModel = Fit(data, groups, equalWithin: track == "within", equalBetween: track == "between", token: token);
        if (!alternative.Converged || !nullModel.Converged) return double.NaN;
        // A materially worse unconstrained fit signals a failed optimization, not a negative LR.
        double statistic = 2 * (nullModel.NegativeLogLikelihood - alternative.NegativeLogLikelihood);
        return statistic < -1e-5 ? double.NaN : Math.Max(0, statistic);
    }
    public static VarianceReport Run(AnalysisData data, int repetitions, int referenceReplications, double withinEffect,
        double betweenEffect, int seed, double alpha, IProgress<ProgressInfo>? progress = null, CancellationToken token = default)
    {
        if (repetitions < 100 || referenceReplications < 99) throw new ArgumentException("Use at least 100 evaluation and 99 reference replications.");
        ScientificMath.RequireRange(alpha, 0, 1, "alpha", false); ScientificMath.RequireFinite(withinEffect, "within effect"); ScientificMath.RequireFinite(betweenEffect, "between effect");
        if (withinEffect <= 1 || betweenEffect <= 1) throw new ArgumentException("SD multipliers must exceed one.");
        ClusterSummary[] clusters = Summaries(data); int groups = data.GroupNames.Length;
        VarianceFit estimates = Fit(clusters, groups, reml: true, token: token);
        var rows = new List<VarianceGroup>();
        for (int g = 0; g < groups; g++)
        {
            ClusterSummary[] part = clusters.Where(c => c.Group == g).ToArray();
            double observed = ScientificMath.Variance(part.Select(c => c.Mean).ToArray());
            double withinMoment = part.Sum(c => c.WithinSumSquares) / part.Sum(c => c.Count - 1);
            double betweenMoment = observed - withinMoment * part.Average(c => 1d / c.Count);
            double total = estimates.Within[g] + estimates.Between[g];
            rows.Add(new VarianceGroup(data.GroupNames[g], part.Length, part.Sum(c => c.Count), estimates.Means[g],
                estimates.Converged ? estimates.Within[g] : double.NaN, estimates.Converged ? estimates.Between[g] : double.NaN,
                observed, betweenMoment, estimates.Converged && total > 0 ? estimates.Between[g] / total : double.NaN,
                !estimates.Converged ? "not_converged_or_degenerate" : estimates.AtBoundary ? "boundary_estimate" : "estimated"));
        }
        if (estimates.Converged)
        {
            var withinDraws = Enumerable.Range(0, groups).Select(_ => new List<double>()).ToArray();
            var betweenDraws = Enumerable.Range(0, groups).Select(_ => new List<double>()).ToArray();
            int successful = 0;
            for (int rep = 0; rep < repetitions; rep++)
            {
                token.ThrowIfCancellationRequested();
                var draw = Generate(clusters, estimates, new Random(ScientificMath.Seed(seed, "variance-estimate-interval", rep)));
                VarianceFit estimateDraw = Fit(draw, groups, reml: true, token: token);
                if (estimateDraw.Converged)
                { successful++; for (int g = 0; g < groups; g++) { withinDraws[g].Add(estimateDraw.Within[g]); betweenDraws[g].Add(estimateDraw.Between[g]); } }
                progress?.Report(new ProgressInfo(.15 * (rep + 1d) / repetitions, "Variance-estimate intervals", "Parametric entity bootstrap"));
            }
            for (int g = 0; g < groups; g++) rows[g] = rows[g] with {
                WithinLow = successful >= .9 * repetitions ? ScientificMath.Quantile(withinDraws[g], .025) : double.NaN,
                WithinHigh = successful >= .9 * repetitions ? ScientificMath.Quantile(withinDraws[g], .975) : double.NaN,
                BetweenLow = successful >= .9 * repetitions ? ScientificMath.Quantile(betweenDraws[g], .025) : double.NaN,
                BetweenHigh = successful >= .9 * repetitions ? ScientificMath.Quantile(betweenDraws[g], .975) : double.NaN,
                IntervalReplications = successful, IntervalStatus = successful < .9 * repetitions ? "excess_bootstrap_failures" : estimates.AtBoundary ? "pointwise_percentile_boundary_caution" : "pointwise_parametric_percentile_95" };
        }
        var tracks = new List<VarianceTrack>(); string[] names = { "within", "between" };
        for (int tr = 0; tr < names.Length; tr++)
        {
            string track = names[tr]; double effect = tr == 0 ? withinEffect : betweenEffect;
            VarianceFit nullModel = Fit(clusters, groups, equalWithin: track == "within", equalBetween: track == "between", token: token);
            double observedStat = Statistic(clusters, groups, track, token);
            var reference = new List<double>();
            if (nullModel.Converged)
                for (int i = 0; i < referenceReplications; i++)
                {
                    token.ThrowIfCancellationRequested(); var rng = new Random(ScientificMath.Seed(seed, track + ":variance-reference", i));
                    double statistic = Statistic(Generate(clusters, nullModel, rng), groups, track, token);
                    if (double.IsFinite(statistic)) reference.Add(statistic);
                    progress?.Report(new ProgressInfo(.15 + .85 * (tr + .35 * (i + 1) / referenceReplications) / 2, "Variance-component null bootstrap", track));
                }
            bool usable = nullModel.Converged && double.IsFinite(observedStat) && reference.Count >= .9 * referenceReplications;
            double BootstrapP(double statistic) => double.IsFinite(statistic) && reference.Count > 0 ? (1d + reference.Count(x => x >= statistic)) / (reference.Count + 1d) : double.NaN;
            int f = 0, a = 0, invalidNull = 0, invalidAlternative = 0;
            var gridTotal = new int[AnalysisEngine.EffectGrid.Length]; var gridReject = new int[gridTotal.Length]; var gridFailed = new int[gridTotal.Length];
            if (usable)
                for (int i = 0; i < repetitions; i++)
                {
                    token.ThrowIfCancellationRequested(); int draw = ScientificMath.Seed(seed, track + ":variance-evaluation", i);
                    double nstat = Statistic(Generate(clusters, nullModel, new Random(draw)), groups, track, token);
                    double astat = Statistic(Generate(clusters, nullModel, new Random(draw), track, effect), groups, track, token);
                    if (!double.IsFinite(nstat)) invalidNull++; else if (BootstrapP(nstat) < alpha / 2) f++;
                    if (!double.IsFinite(astat)) invalidAlternative++; else if (BootstrapP(astat) < alpha / 2) a++;
                    int point = i % gridTotal.Length; gridTotal[point]++;
                    double gs = Statistic(Generate(clusters, nullModel, new Random(draw), track, AnalysisEngine.EffectGrid[point]), groups, track, token);
                    if (!double.IsFinite(gs)) gridFailed[point]++; else if (BootstrapP(gs) < alpha / 2) gridReject[point]++;
                    progress?.Report(new ProgressInfo(.15 + .85 * (tr + .35 + .65 * (i + 1) / repetitions) / 2, "Separate component power", track));
                }
            else { invalidNull = repetitions; invalidAlternative = repetitions; }
            bool validRates = usable && invalidNull <= .1 * repetitions && invalidAlternative <= .1 * repetitions;
            double fp = validRates ? f / (double)repetitions : double.NaN, power = validRates ? a / (double)repetitions : double.NaN;
            var fci = validRates ? ScientificMath.Wilson(f, repetitions) : (double.NaN, double.NaN);
            var pci = validRates ? ScientificMath.Wilson(a, repetitions) : (double.NaN, double.NaN);
            double p = usable ? BootstrapP(observedStat) : double.NaN;
            double[] curve = gridTotal.Select((n, i) => n > 0 && gridFailed[i] <= .1 * n ? gridReject[i] / (double)n : double.NaN).ToArray();
            double mde = validRates && gridTotal.All(n => n >= 100) ? AnalysisEngine.MdeFromCurve(AnalysisEngine.EffectGrid, curve) : double.NaN;
            bool componentAtBoundary = (track == "within" ? nullModel.Within : nullModel.Between).Any(v => v <= 1e-8 * Math.Max(1e-300, nullModel.Within.Concat(nullModel.Between).Max()));
            // A multiplicative effect on a zero baseline does not define a meaningful design alternative.
            if (componentAtBoundary) { power = double.NaN; mde = double.NaN; pci = (double.NaN, double.NaN); curve = Enumerable.Repeat(double.NaN, curve.Length).ToArray(); }
            tracks.Add(new VarianceTrack(track, observedStat, p, DecisionPolicy.Adjust(p, 2), fp, fci.Item1, fci.Item2,
                power, pci.Item1, pci.Item2, effect, reference.Count, referenceReplications - reference.Count, repetitions, invalidNull, invalidAlternative,
                !usable ? "insufficient" : DecisionPolicy.Adjust(p, 2) < alpha ? "difference" : "insufficient",
                !usable ? "bootstrap_or_fit_failure" : componentAtBoundary ? "boundary_baseline_power_not_identifiable" : validRates ? "conditional_plugin_bootstrap" : "excess_simulation_failures",
                AnalysisEngine.EffectGrid, curve, mde, double.IsFinite(mde) ? "estimated_on_grid" : componentAtBoundary ? "zero_baseline" : gridTotal.Any(n => n < 100) ? "insufficient_simulations" : "target_not_reached_or_invalid_curve"));
        }
        return new VarianceReport(ReleaseInfo.EngineVersion, "Gaussian random intercept; group-specific mean and variance components; REML estimates / ML bootstrap tests",
            "Two component hypotheses, Bonferroni alpha/2; separate from the summary-metric family", seed, alpha, rows.ToArray(), tracks.ToArray(),
            data.Warnings.Concat(new[] {
                "Conditional Gaussian errors, independent entities and conditionally independent repeats are assumptions, not facts established by this fit.",
                "Power/FPR use fitted null nuisance parameters and an independent evaluation stream against one reference distribution; uncertainty is conditional on that reference and fitted model.",
                "Failed evaluation fits count as non-rejections; failure counts are exported. Rates are suppressed above 10% failures.",
                "Observed SD of entity means includes measurement error. The untruncated method-of-moments estimate is included for transparency.",
                "Variance-estimate intervals are pointwise parametric percentile intervals conditional on the fitted model; boundary coverage is not guaranteed.",
                "No global equivalence conclusion follows from a non-significant variance test. Small samples and boundary estimates require external validation." }).ToArray());
    }
    public static string Csv(VarianceReport report) => ScientificTables.Csv(report.Groups);
}
