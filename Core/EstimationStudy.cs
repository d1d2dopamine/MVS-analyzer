namespace MvsAnalyzer;

internal sealed record EstimationOptions(string Target = "mean", string Shape = "normal", int Entities = 20,
    int Measurements = 12, int Repetitions = 500, int BootstrapReplications = 199, int Seed = 20260719,
    double Location = 100, double WithinSd = 10, double BetweenSd = 5);
internal sealed record EstimationPerformance(string Estimator, string Target, double Truth, int Requested, int Completed,
    int Failures, double Bias, double BiasMcse, double Mse, double MseMcse, double Rmse, double EmpiricalSd,
    int IntervalsCompleted, double Coverage, double CoverageMcse, double CoverageUnconditional, double MeanIntervalWidth,
    double RelativeMseEfficiency, double RelativeVarianceEfficiency, string Reference, string Status);
internal sealed record EstimationDraw(int Replication, string Estimator, double Estimate, double Low, double High, string Status);
internal sealed record EstimationReport(string EngineVersion, string Scope, EstimationOptions Options, double Truth,
    EstimationPerformance[] Performance, EstimationDraw[] Draws, string[] Warnings);

/// <summary>Known-truth simulation, never an assertion of the unknown bias of the user's real CSV.</summary>
internal static class EstimationStudy
{
    internal static double Truth(EstimationOptions options)
    {
        bool lognormal = options.Shape == "lognormal";
        return options.Target switch
        {
            "mean" => lognormal ? Math.Exp(options.Location + .5 * (options.WithinSd * options.WithinSd + options.BetweenSd * options.BetweenSd)) : options.Location,
            "median" or "geometric_mean" => lognormal ? Math.Exp(options.Location) : options.Location,
            "within_variance" => options.WithinSd * options.WithinSd,
            "between_variance" => options.BetweenSd * options.BetweenSd,
            _ => throw new ArgumentException("Unknown estimand.")
        };
    }
    private static string[] Methods(EstimationOptions options) => options.Target switch
    {
        "mean" => options.Shape == "lognormal" ? new[] { "arithmetic_mean", "lognormal_moment_mean" } : new[] { "arithmetic_mean", "trimmed_entity_mean_20", "median_of_entity_medians" },
        "median" => options.Shape == "lognormal" ? new[] { "median_of_entity_medians", "pooled_median", "exp_mean_log" } : new[] { "median_of_entity_medians", "pooled_median", "arithmetic_mean" },
        "geometric_mean" => new[] { "exp_mean_log", "median_of_entity_medians" },
        "within_variance" => new[] { "pooled_within_variance", "normal_mad_variance" },
        "between_variance" => new[] { "untruncated_moment_between", "nonnegative_moment_between" },
        _ => throw new ArgumentException("Target must be mean, median, geometric_mean, within_variance or between_variance.")
    };
    internal static double Estimate(double[][] entities, string method)
    {
        double Within(double[][] x) => x.Sum(a => { double m = a.Average(); return a.Sum(v => (v - m) * (v - m)); }) / x.Sum(a => a.Length - 1);
        double Between(double[][] x) => ScientificMath.Variance(x.Select(a => a.Average()).ToArray()) - Within(x) * x.Average(a => 1d / a.Length);
        double Trim(double[] x) { double[] s = x.OrderBy(v => v).ToArray(); int k = (int)Math.Floor(s.Length * .2); return s.Skip(k).Take(s.Length - 2 * k).Average(); }
        return method switch
        {
            "arithmetic_mean" => entities.Average(e => e.Average()),
            "trimmed_entity_mean_20" => entities.Average(Trim),
            "median_of_entity_medians" => ScientificMath.Quantile(entities.Select(e => ScientificMath.Quantile(e, .5)), .5),
            "pooled_median" => ScientificMath.Quantile(entities.SelectMany(e => e), .5),
            "exp_mean_log" => entities.All(e => e.All(x => x > 0)) ? Math.Exp(entities.Average(e => e.Average(Math.Log))) : double.NaN,
            "lognormal_moment_mean" => LognormalMean(entities),
            "pooled_within_variance" => Within(entities),
            "normal_mad_variance" => entities.Average(e => { double m = ScientificMath.Quantile(e, .5); double mad = ScientificMath.Quantile(e.Select(x => Math.Abs(x - m)), .5); return Math.Pow(mad / .6744897501960817, 2); }),
            "untruncated_moment_between" => Between(entities),
            "nonnegative_moment_between" => Math.Max(0, Between(entities)),
            _ => throw new ArgumentException("Unknown estimator: " + method)
        };
        double LognormalMean(double[][] x)
        {
            if (x.Any(e => e.Any(v => v <= 0))) return double.NaN;
            double[][] logs = x.Select(e => e.Select(logValue => Math.Log(logValue)).ToArray()).ToArray();
            return Math.Exp(logs.Average(e => e.Average()) + .5 * (Within(logs) + Math.Max(0, Between(logs))));
        }
    }
    private static double[][] Generate(EstimationOptions options, Random random)
    {
        double Residual()
        {
            if (options.Shape != "student_t5") return ScientificMath.Gaussian(random);
            double numerator = ScientificMath.Gaussian(random), chi = 0;
            for (int i = 0; i < 5; i++) { double z = ScientificMath.Gaussian(random); chi += z * z; }
            return numerator / Math.Sqrt(Math.Max(chi, 1e-15) / 3); // standardized t5, variance one
        }
        return Enumerable.Range(0, options.Entities).Select(_ =>
        {
            double b = options.BetweenSd * ScientificMath.Gaussian(random);
            return Enumerable.Range(0, options.Measurements).Select(__ =>
            { double y = options.Location + b + options.WithinSd * Residual(); return options.Shape == "lognormal" ? Math.Exp(y) : y; }).ToArray();
        }).ToArray();
    }
    public static EstimationReport Run(EstimationOptions options, IProgress<ProgressInfo>? progress = null, CancellationToken token = default)
    {
        if (!new[] { "normal", "lognormal", "student_t5" }.Contains(options.Shape)) throw new ArgumentException("Shape must be normal, lognormal or student_t5.");
        if (options.Entities < 4 || options.Measurements < 3 || options.Repetitions < 100 || options.BootstrapReplications < 99)
            throw new ArgumentException("Use at least four entities, three measurements, 100 replications and 99 bootstrap draws.");
        ScientificMath.RequireFinite(options.Location, "location"); ScientificMath.RequireFinite(options.WithinSd, "within SD"); ScientificMath.RequireFinite(options.BetweenSd, "between SD");
        if (options.WithinSd <= 0 || options.BetweenSd < 0) throw new ArgumentException("Within SD must be positive; between SD must be nonnegative.");
        if (options.Target == "geometric_mean" && options.Shape != "lognormal") throw new ArgumentException("The geometric-mean study requires lognormal positive data.");
        if ((options.Target == "within_variance" || options.Target == "between_variance") && options.Shape != "normal")
            throw new ArgumentException("Variance-estimation studies currently use the Gaussian random-intercept model only.");
        string[] methods = Methods(options); double truth = Truth(options); ScientificMath.RequireFinite(truth, "simulation truth");
        var draws = new List<EstimationDraw>();
        for (int rep = 0; rep < options.Repetitions; rep++)
        {
            token.ThrowIfCancellationRequested();
            double[][] data = Generate(options, new Random(ScientificMath.Seed(options.Seed, "estimation-data", rep)));
            var bootstrap = methods.Select(_ => new List<double>()).ToArray();
            var rng = new Random(ScientificMath.Seed(options.Seed, "estimation-cluster-bootstrap", rep));
            for (int b = 0; b < options.BootstrapReplications; b++)
            {
                token.ThrowIfCancellationRequested();
                // The independent sampling unit is the entity; its entire measurement vector is kept.
                double[][] sample = Enumerable.Range(0, data.Length).Select(_ => data[rng.Next(data.Length)]).ToArray();
                for (int m = 0; m < methods.Length; m++) { double value = Estimate(sample, methods[m]); if (double.IsFinite(value)) bootstrap[m].Add(value); }
            }
            for (int m = 0; m < methods.Length; m++)
            {
                double estimate = Estimate(data, methods[m]);
                if (!double.IsFinite((estimate - truth) * (estimate - truth))) estimate = double.NaN;
                bool interval = bootstrap[m].Count >= .9 * options.BootstrapReplications;
                draws.Add(new EstimationDraw(rep + 1, methods[m], estimate,
                    interval ? ScientificMath.Quantile(bootstrap[m], .025) : double.NaN,
                    interval ? ScientificMath.Quantile(bootstrap[m], .975) : double.NaN,
                    !double.IsFinite(estimate) ? "estimate_failed" : !interval ? "interval_failed" : "estimated"));
            }
            progress?.Report(new ProgressInfo((rep + 1d) / options.Repetitions, "Known-truth estimation study", options.Target));
        }
        var performance = new List<EstimationPerformance>();
        foreach (string method in methods)
        {
            EstimationDraw[] all = draws.Where(d => d.Estimator == method).ToArray(), valid = all.Where(d => double.IsFinite(d.Estimate)).ToArray();
            EstimationDraw[] intervals = valid.Where(d => double.IsFinite(d.Low) && double.IsFinite(d.High)).ToArray();
            double[] errors = valid.Select(d => d.Estimate - truth).ToArray(), squared = errors.Select(e => e * e).ToArray();
            int covered = intervals.Count(d => d.Low <= truth && truth <= d.High);
            double bias = errors.Length > 0 ? errors.Average() : double.NaN, mse = squared.Length > 0 ? squared.Average() : double.NaN;
            double sd = valid.Length > 1 ? Math.Sqrt(ScientificMath.Variance(valid.Select(d => d.Estimate).ToArray())) : double.NaN;
            double coverage = intervals.Length > 0 ? covered / (double)intervals.Length : double.NaN;
            performance.Add(new EstimationPerformance(method, options.Target, truth, options.Repetitions, valid.Length, options.Repetitions - valid.Length,
                bias, sd / Math.Sqrt(valid.Length), mse, valid.Length > 1 ? Math.Sqrt(ScientificMath.Variance(squared) / valid.Length) : double.NaN,
                Math.Sqrt(mse), sd, intervals.Length, coverage, ScientificMath.Mcse(coverage, intervals.Length), covered / (double)options.Repetitions,
                intervals.Length > 0 ? intervals.Average(d => d.High - d.Low) : double.NaN, double.NaN, double.NaN, methods[0],
                valid.Length >= .9 * options.Repetitions ? "known_truth_simulation" : "excess_failures"));
        }
        EstimationPerformance baseline = performance[0];
        for (int i = 0; i < performance.Count; i++)
            performance[i] = performance[i] with {
                RelativeMseEfficiency = performance[i].Mse > 0 ? baseline.Mse / performance[i].Mse : double.NaN,
                RelativeVarianceEfficiency = performance[i].EmpiricalSd > 0 ? Math.Pow(baseline.EmpiricalSd / performance[i].EmpiricalSd, 2) : double.NaN };
        return new EstimationReport(ReleaseInfo.EngineVersion, "Synthetic known-truth ADEMP study; NOT the unknown bias of an uploaded dataset", options, truth,
            performance.ToArray(), draws.ToArray(), new[] {
                "All compared methods target the SAME declared estimand under the selected mechanism. Do not compare MSE across different estimands or units.",
                "For lognormal data, location and within/between SD parameters are on the log scale. Normal and t5 parameters are on the outcome scale.",
                "Intervals are 95% percentile entity-bootstrap intervals; coverage is measured rather than assumed. Between-variance boundaries and small cluster counts can impair coverage.",
                "Bias, MSE and variance are conditional on successful point estimates; requested/completed/failed counts are exported. Unconditional coverage counts missing intervals as failures.",
                "Relative MSE efficiency is reference MSE / method MSE. The variance ratio alone must not be interpreted as superior accuracy when bias differs.",
                "Variance targets currently support Gaussian data only. The normal MAD estimator uses the asymptotic normal consistency factor, not a finite-sample unbiasedness correction.",
                "Monte Carlo standard errors describe finite simulation noise. They do not cover misspecification of the data-generating model." });
    }
}
