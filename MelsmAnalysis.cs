namespace MvsAnalyzer;

internal sealed record MelsmOptions(bool MeanTime = false, bool ScaleTime = false, bool Correlate = false,
    bool RandomScale = true, int QuadraturePoints = 15, int MaxIterations = 4000);
internal sealed record ModelParameter(string Name, double Estimate, double StandardError, double Low, double High, string Scale, string Status);
internal sealed record MelsmEntity(string Entity, int Observations, double LocationEffect, double LogVarianceEffect);
internal sealed record MelsmReport(string EngineVersion, string Model, string Status, bool Converged, int Iterations,
    double LogLikelihood, double QuadratureDifference, int QuadraturePoints, int Subjects, int Observations,
    double TimeCenter, double TimeScale, MelsmOptions Options, ModelParameter[] Parameters, MelsmEntity[] RandomEffects, string[] Warnings);

/// <summary>
/// Optional Gaussian mixed-effects location-scale model, estimated by marginal ML.
/// b and v are correlated normal random effects. b is integrated analytically using
/// Sherman–Morrison; v is integrated with subject-adaptive normal quadrature.
/// This is not a regression on estimated entity SDs. It is an experimental numerical implementation.
/// </summary>
internal static class MelsmAnalysis
{
    private sealed record Row(int Group, double Y, double Time);
    private sealed record Cell(int Group, int Count, double Mean, double SumSquares);
    private sealed record Subject(string Id, Row[] Rows, Cell[] Cells);
    private sealed record Integral(double LogLikelihood, double Location, double LogScale);

    public static MelsmReport Run(List<Observation> observations, MelsmOptions options, IProgress<ProgressInfo>? progress = null, CancellationToken token = default)
    {
        if (options.Correlate && !options.RandomScale) throw new ArgumentException("Correlation requires a random scale effect.");
        if (options.QuadraturePoints < 7 || options.QuadraturePoints > 31 || options.MaxIterations < 100)
            throw new ArgumentException("Use 7–31 quadrature points and at least 100 optimization iterations.");
        if (observations.Count == 0 || observations.Any(o => !double.IsFinite(o.Value))) throw new InvalidDataException("MELSM requires finite observations.");
        if (observations.Select(o => o.Variable).Distinct(StringComparer.OrdinalIgnoreCase).Count() != 1 ||
            observations.Where(o => !string.IsNullOrWhiteSpace(o.Unit)).Select(o => o.Unit).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1)
            throw new InvalidDataException("MELSM requires one outcome in consistent units.");
        string[] groups = observations.Select(o => o.Group).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (groups.Length > 10) throw new InvalidDataException("This MELSM implementation supports at most ten conditions.");
        if (observations.GroupBy(o => o.Group, StringComparer.OrdinalIgnoreCase).Any(g => g.Count() < 4 || g.Select(o => o.Entity).Distinct(StringComparer.OrdinalIgnoreCase).Count() < 2))
            throw new InvalidDataException("Each condition needs at least four observations from at least two subjects.");
        var grouped = observations.GroupBy(o => o.Entity, StringComparer.OrdinalIgnoreCase).ToArray();
        if (grouped.Length < 8 || grouped.Any(g => g.Count() < 3)) throw new InvalidDataException("MELSM requires at least eight distinct entity IDs and at least three observations per entity. More are usually needed for reliable variance inference.");
        if ((options.MeanTime || options.ScaleTime) && observations.GroupBy(o => o.Group, StringComparer.OrdinalIgnoreCase).All(g => g.Select(o => o.Sequence).Distinct().Count() < 2))
            throw new InvalidDataException("Time is collinear with condition; a mean time coefficient is not identifiable.");
        double center = observations.Average(o => o.Value), scale = Math.Sqrt(ScientificMath.Variance(observations.Select(o => o.Value).ToArray()));
        if (!double.IsFinite(scale) || scale <= 0) throw new InvalidDataException("The outcome is constant; the model is not identifiable.");
        double timeCenter = observations.Average(o => (double)o.Sequence), timeScale = Math.Sqrt(ScientificMath.Variance(observations.Select(o => (double)o.Sequence).ToArray()));
        if ((options.MeanTime || options.ScaleTime) && timeScale < 1e-12) throw new InvalidDataException("No time variation is available.");
        timeScale = Math.Max(timeScale, 1);
        Subject[] subjects = grouped.Select(g =>
        {
            Row[] rows = g.Select(o => new Row(Array.FindIndex(groups, x => x.Equals(o.Group, StringComparison.OrdinalIgnoreCase)), (o.Value - center) / scale, (o.Sequence - timeCenter) / timeScale)).ToArray();
            Cell[] cells = rows.GroupBy(r => r.Group).Select(c => { double mean = c.Average(r => r.Y); return new Cell(c.Key, c.Count(), mean, c.Sum(r => (r.Y - mean) * (r.Y - mean))); }).ToArray();
            return new Subject(g.Key, rows, cells);
        }).ToArray();
        int gcount = groups.Length, tauIndex = 2 * gcount, next = tauIndex + 1;
        int omegaIndex = options.RandomScale ? next++ : -1, rhoIndex = options.Correlate && options.RandomScale ? next++ : -1;
        int meanTimeIndex = options.MeanTime ? next++ : -1, scaleTimeIndex = options.ScaleTime ? next++ : -1, dimension = next;
        var start = new double[dimension]; var lower = new double[dimension]; var upper = new double[dimension];
        for (int i = 0; i < dimension; i++) { lower[i] = -8; upper[i] = 8; }
        for (int g = 0; g < gcount; g++)
        {
            double[] values = subjects.SelectMany(s => s.Rows).Where(r => r.Group == g).Select(r => r.Y).ToArray();
            start[g] = values.Average(); lower[g] = -20; upper[g] = 20;
            start[gcount + g] = Math.Log(Math.Max(.05, Math.Sqrt(ScientificMath.Variance(values)) * .8)); lower[gcount + g] = -10; upper[gcount + g] = 4;
        }
        start[tauIndex] = Math.Log(.3); lower[tauIndex] = -10; upper[tauIndex] = 4;
        if (omegaIndex >= 0) { start[omegaIndex] = Math.Log(.25); lower[omegaIndex] = -8; upper[omegaIndex] = 1.5; }
        if (rhoIndex >= 0) { start[rhoIndex] = 0; lower[rhoIndex] = -2.65; upper[rhoIndex] = 2.65; }
        var quadrature = NumericalMethods.NormalQuadrature(options.QuadraturePoints);
        bool time = options.MeanTime || options.ScaleTime;

        (double Log, double ConditionalLocation) Conditional(Subject subject, double[] p, double z)
        {
            double tau = Math.Exp(p[tauIndex]), omega = omegaIndex >= 0 ? Math.Exp(p[omegaIndex]) : 0;
            double rho = rhoIndex >= 0 ? Math.Tanh(p[rhoIndex]) : 0;
            double randomMean = rho * tau * z, randomVariance = tau * tau * (1 - rho * rho);
            double a = 0, b = 0, c = 0, logDet = 0;
            if (!time)
                foreach (Cell cell in subject.Cells)
                {
                    double logV = 2 * p[gcount + cell.Group] + omega * z, weight = Math.Exp(-logV), residual = cell.Mean - p[cell.Group] - randomMean;
                    a += cell.Count * weight; b += cell.Count * weight * residual;
                    c += weight * (cell.SumSquares + cell.Count * residual * residual); logDet += cell.Count * logV;
                }
            else
                foreach (Row row in subject.Rows)
                {
                    double logV = 2 * p[gcount + row.Group] + omega * z + (scaleTimeIndex >= 0 ? p[scaleTimeIndex] * row.Time : 0);
                    double weight = Math.Exp(-logV), residual = row.Y - p[row.Group] - (meanTimeIndex >= 0 ? p[meanTimeIndex] * row.Time : 0) - randomMean;
                    a += weight; b += weight * residual; c += weight * residual * residual; logDet += logV;
                }
            double denominator = 1 + randomVariance * a;
            double quad = c - randomVariance * b * b / denominator;
            if (quad < -1e-6 || !double.IsFinite(quad)) return (double.NegativeInfinity, double.NaN);
            double log = -.5 * (subject.Rows.Length * Math.Log(2 * Math.PI) + logDet + Math.Log(denominator) + Math.Max(0, quad));
            return (log, randomMean + randomVariance * b / denominator);
        }
        Integral Integrate(Subject subject, double[] p, (double[] Nodes, double[] Weights) rule, bool predict = false)
        {
            if (omegaIndex < 0) { var value = Conditional(subject, p, 0); return new Integral(value.Log, value.ConditionalLocation, 0); }
            double LogPosterior(double z) => Conditional(subject, p, z).Log - .5 * z * z;
            // One-dimensional adaptive mode search. Coarse bracketing avoids assuming concavity.
            double mode = 0, best = LogPosterior(0);
            for (int i = -8; i <= 8; i++) { double value = LogPosterior(i); if (value > best) { best = value; mode = i; } }
            double left = Math.Max(-12, mode - 1.5), right = Math.Min(12, mode + 1.5);
            const double golden = .6180339887498949;
            double x1 = right - golden * (right - left), x2 = left + golden * (right - left), f1 = LogPosterior(x1), f2 = LogPosterior(x2);
            for (int i = 0; i < 28; i++)
            {
                if (f1 > f2) { right = x2; x2 = x1; f2 = f1; x1 = right - golden * (right - left); f1 = LogPosterior(x1); }
                else { left = x1; x1 = x2; f1 = f2; x2 = left + golden * (right - left); f2 = LogPosterior(x2); }
            }
            mode = (left + right) / 2; const double h = .002;
            double curvature = -(LogPosterior(mode + h) - 2 * LogPosterior(mode) + LogPosterior(mode - h)) / (h * h);
            double width = double.IsFinite(curvature) && curvature > .01 ? Math.Clamp(1 / Math.Sqrt(curvature), .01, 3) : 1;
            var logWeights = new double[rule.Nodes.Length]; var locations = new double[rule.Nodes.Length]; var scales = new double[rule.Nodes.Length];
            for (int i = 0; i < logWeights.Length; i++)
            {
                double node = rule.Nodes[i], z = mode + width * node; var value = Conditional(subject, p, z);
                logWeights[i] = Math.Log(rule.Weights[i]) + Math.Log(width) + value.Log - .5 * z * z + .5 * node * node;
                if (predict) { locations[i] = value.ConditionalLocation; scales[i] = Math.Exp(p[omegaIndex]) * z; }
            }
            double likelihood = ScientificMath.LogSumExp(logWeights), location = 0, logScale = 0;
            if (predict && double.IsFinite(likelihood))
                for (int i = 0; i < logWeights.Length; i++) { double weight = Math.Exp(logWeights[i] - likelihood); location += weight * locations[i]; logScale += weight * scales[i]; }
            return new Integral(likelihood, location, logScale);
        }
        int evaluations = 0;
        double Objective(double[] p)
        {
            token.ThrowIfCancellationRequested(); double value = 0;
            foreach (Subject subject in subjects) value -= Integrate(subject, p, quadrature).LogLikelihood;
            if (++evaluations % 100 == 0) progress?.Report(new ProgressInfo(0, "MELSM likelihood evaluations: " + evaluations, "Adaptive quadrature; convergence is checked, not assumed"));
            return double.IsFinite(value) ? value : 1e100;
        }
        OptimizationResult bestFit = NumericalMethods.Minimize(Objective, start, lower, upper, options.MaxIterations, 1e-8, token);
        // Independent scale starting values are important for the random-scale likelihood.
        if (omegaIndex >= 0)
        {
            double[] alternate = (double[])start.Clone(); alternate[omegaIndex] = Math.Log(.8); alternate[tauIndex] = Math.Log(.6);
            OptimizationResult second = NumericalMethods.Minimize(Objective, alternate, lower, upper, options.MaxIterations, 1e-8, token);
            if (second.Value < bestFit.Value) bestFit = second;
        }
        var refined = NumericalMethods.NormalQuadrature(Math.Min(61, options.QuadraturePoints * 2 + 1));
        double refinedValue = -subjects.Sum(s => Integrate(s, bestFit.Parameters, refined).LogLikelihood);
        double quadratureDifference = Math.Abs(refinedValue - bestFit.Value);
        if (quadratureDifference > .01 && double.IsFinite(refinedValue))
        {
            quadrature = refined;
            bestFit = NumericalMethods.Minimize(Objective, bestFit.Parameters, lower, upper, options.MaxIterations, 1e-8, token);
            var check = NumericalMethods.NormalQuadrature(quadrature.Nodes.Length == 61 ? 47 : Math.Min(61, quadrature.Nodes.Length + 16));
            refinedValue = -subjects.Sum(s => Integrate(s, bestFit.Parameters, check).LogLikelihood);
            quadratureDifference = Math.Abs(refinedValue - bestFit.Value);
        }
        bool quadratureOk = double.IsFinite(quadratureDifference) && quadratureDifference <= .01;
        double[]? standardErrors = bestFit.Converged && !bestFit.AtBoundary && quadratureOk ? NumericalMethods.StandardErrors(Objective, bestFit.Parameters) : null;
        string status = !bestFit.Converged ? "not_converged" : !quadratureOk ? "quadrature_unstable" : bestFit.AtBoundary ? "boundary_fit" : standardErrors == null ? "singular_information" : "converged_experimental";
        double[] parameters = bestFit.Parameters; var output = new List<ModelParameter>();
        void Add(string name, int index, Func<double, double> transform, Func<double, double> derivative, string unit)
        {
            double se = standardErrors == null ? double.NaN : standardErrors[index];
            output.Add(new ModelParameter(name, transform(parameters[index]), double.IsFinite(se) ? Math.Abs(derivative(parameters[index])) * se : double.NaN,
                double.IsFinite(se) ? transform(parameters[index] - 1.95996398454 * se) : double.NaN,
                double.IsFinite(se) ? transform(parameters[index] + 1.95996398454 * se) : double.NaN, unit,
                standardErrors == null ? "interval_unavailable_" + status : "approximate_pointwise_wald_95"));
        }
        for (int g = 0; g < gcount; g++)
        {
            Add("mean:" + groups[g], g, x => center + scale * x, _ => scale, "outcome units at centred time, random effects zero");
            Add("residual_variance_at_v0:" + groups[g], gcount + g, x => scale * scale * Math.Exp(2 * x), x => 2 * scale * scale * Math.Exp(2 * x), "outcome units squared; conditional at random scale zero");
        }
        Add("between_entity_variance", tauIndex, x => scale * scale * Math.Exp(2 * x), x => 2 * scale * scale * Math.Exp(2 * x), "outcome units squared; common across conditions");
        if (omegaIndex >= 0) Add("random_log_variance_sd", omegaIndex, Math.Exp, Math.Exp, "SD of v in log residual variance");
        if (rhoIndex >= 0) Add("location_scale_correlation", rhoIndex, Math.Tanh, x => 1 - Math.Pow(Math.Tanh(x), 2), "correlation");
        if (meanTimeIndex >= 0) Add("mean_time_slope", meanTimeIndex, x => x * scale / timeScale, _ => scale / timeScale, "outcome units per sequence unit");
        if (scaleTimeIndex >= 0) Add("log_variance_time_slope", scaleTimeIndex, x => x / timeScale, _ => 1 / timeScale, "log variance per sequence unit");
        MelsmEntity[] predictions = bestFit.Converged && quadratureOk ? subjects.Select(s => { Integral v = Integrate(s, parameters, quadrature, true); return new MelsmEntity(s.Id, s.Rows.Length, scale * v.Location, v.LogScale); }).ToArray() : Array.Empty<MelsmEntity>();
        progress?.Report(new ProgressInfo(1, "MELSM finished", status));
        return new MelsmReport(ReleaseInfo.EngineVersion,
            "y_ij = condition_mean + beta_time*t + b_i + e_ij; log Var(e_ij|b_i,v_i) = condition_log_variance + gamma_time*t + v_i; (b_i,v_i) jointly Gaussian",
            status, bestFit.Converged, bestFit.Iterations, bestFit.Value < 1e99 ? -bestFit.Value - observations.Count * Math.Log(scale) : double.NaN,
            quadratureDifference, quadrature.Nodes.Length, subjects.Length, observations.Count, timeCenter, timeScale, options,
            output.ToArray(), predictions, new[] {
                "Experimental native marginal-ML implementation, not independently certified. Convergence does not prove a global optimum or adequate model fit.",
                "Entity IDs are global: the same ID in different conditions denotes the SAME subject. Prefix IDs if they refer to independent subjects.",
                "Errors are conditionally Gaussian and independent over time. No AR(1), random slopes, ordinal/count outcomes or arbitrary covariate formulas are implemented.",
                "Wald intervals are pointwise and approximate, not multiplicity-adjusted. They are suppressed for numerical boundaries, unstable quadrature or non-positive observed information.",
                "Residual variances are conditional at v=0. With random scale, the marginal residual variance additionally contains exp(omega^2/2).",
                "The time term uses sequence values; no implicit date conversion or missing-observation imputation is performed. Missing outcomes require an ignorable missingness assumption.",
                "Random-effect predictions are empirical-Bayes posterior means, not observed entity effects or independent outcomes for subsequent testing." });
    }
}
