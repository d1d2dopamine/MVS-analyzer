namespace MvsAnalyzer;

/// <summary>
/// Development-stage 1.5 recommendation for one metric on one calibration track.
/// This is a diagnostic recommendation layer only. It does not change the shipped
/// 1.4 Bonferroni decision family or the raw/adjusted p-values.
/// </summary>
internal sealed record CalibrationRecommendation(
    string Track,
    string Family,
    string Metric,
    bool FamilyEligible,
    bool Applicable,
    bool NullControlled,
    double Power,
    double PowerLow,
    double PowerHigh,
    double BestPower,
    double BestPowerLow,
    bool Candidate,
    string Quality,
    string Reason);

internal sealed record CalibrationTrackRecommendation(
    string Track,
    string Family,
    string Status,
    string[] Candidates,
    string[] QualifiedCandidates,
    string? BestMetric,
    double BestPower,
    double BestPowerLow);

/// <summary>
/// Family-aware, uncertainty-aware metric recommendations for the 1.5 development line.
///
/// Candidate membership uses overlap with the best metric's Wilson power interval:
/// an eligible, null-controlled metric remains in the set when its power upper bound is
/// at least the best metric's power lower bound. The old >=.70 lower-power gate is retained
/// only as a recommendation-quality label (qualified vs uncertain), not as a switch that
/// suppresses the candidate set.
/// </summary>
internal static class CalibrationRecommendations
{
    internal const string MethodId = "family-power-ci-overlap-v1";

    internal static CalibrationRecommendation[] Build(IReadOnlyList<CalibrationRow> rows, string track)
    {
        string canonical = SimulationScenarios.Canonicalize(track);
        string family = MetricRegistry.FamilyForTrack(canonical);
        double alpha = rows.Count == 0 ? .05 : rows[0].Alpha;
        double nullLimit = DecisionPolicy.FprLimit(alpha / AnalysisEngine.MetricKeys.Length);

        var working = rows.Select(row =>
        {
            bool familyEligible = MetricRegistry.IsNaturalForTrack(row.Metric, canonical);
            int index = row.TrackIndex(canonical);
            double power = row.PowerIn(canonical);
            double low = At(row.TrackPowerLow, index, power);
            double high = At(row.TrackPowerHigh, index, power);
            double upperFpr = double.IsFinite(row.FprHigh) ? row.FprHigh : row.Fpr;
            bool applicable = row.Applicable && double.IsFinite(power) && double.IsFinite(low) && double.IsFinite(high);
            bool nullControlled = applicable && !row.FprInflated && double.IsFinite(upperFpr) && upperFpr <= nullLimit;
            return new Working(row, familyEligible, applicable, nullControlled, power, low, high);
        }).ToArray();

        Working? best = working
            .Where(x => x.FamilyEligible && x.NullControlled)
            .OrderByDescending(x => x.Power)
            .ThenBy(x => Array.IndexOf(AnalysisEngine.MetricKeys, x.Row.Metric))
            .FirstOrDefault();

        double bestPower = best?.Power ?? double.NaN;
        double bestLow = best?.Low ?? double.NaN;

        return working.Select(x =>
        {
            bool candidate = best != null && x.FamilyEligible && x.NullControlled && x.High >= bestLow;
            string quality;
            string reason;
            if (!x.FamilyEligible)
            {
                quality = "outside_family";
                reason = "Metric belongs to a different summary family for this track.";
            }
            else if (!x.Applicable)
            {
                quality = "not_applicable";
                reason = "Metric or track power is unavailable for this calibration.";
            }
            else if (!x.NullControlled)
            {
                quality = "null_control_uncertain";
                reason = "The null false-positive upper bound does not satisfy the current diagnostic limit.";
            }
            else if (!candidate)
            {
                quality = "lower_sensitivity";
                reason = "Its power interval is separated below the best eligible metric under this calibration.";
            }
            else if (x.Low >= AnalysisEngine.CandidateMinPower)
            {
                quality = "qualified";
                reason = "Sensitivity is statistically competitive with the best eligible metric and its lower power bound meets the recommendation target.";
            }
            else
            {
                quality = "uncertain_power";
                reason = "Sensitivity is statistically competitive with the best eligible metric, but the lower power bound is below the recommendation target.";
            }

            return new CalibrationRecommendation(canonical, family, x.Row.Metric, x.FamilyEligible, x.Applicable, x.NullControlled,
                x.Power, x.Low, x.High, bestPower, bestLow, candidate, quality, reason);
        }).ToArray();
    }

    internal static CalibrationRecommendation[] Build(IReadOnlyList<CalibrationRow> rows, IEnumerable<string> tracks) =>
        tracks.SelectMany(track => Build(rows, track)).ToArray();

    internal static CalibrationTrackRecommendation Summarize(IReadOnlyList<CalibrationRow> rows, string track)
    {
        CalibrationRecommendation[] recommendations = Build(rows, track);
        string[] candidates = recommendations.Where(x => x.Candidate).Select(x => x.Metric).ToArray();
        string[] qualified = recommendations.Where(x => x.Candidate && x.Quality == "qualified").Select(x => x.Metric).ToArray();
        CalibrationRecommendation? best = recommendations.Where(x => x.Candidate).OrderByDescending(x => x.Power).FirstOrDefault();
        string status = qualified.Length > 0 ? "qualified" : candidates.Length > 0 ? "uncertain" : "unavailable";
        return new CalibrationTrackRecommendation(
            SimulationScenarios.Canonicalize(track),
            recommendations.FirstOrDefault()?.Family ?? MetricRegistry.FamilyForTrack(track),
            status,
            candidates,
            qualified,
            best?.Metric,
            best?.BestPower ?? double.NaN,
            best?.BestPowerLow ?? double.NaN);
    }

    internal static CalibrationTrackRecommendation[] Summaries(IReadOnlyList<CalibrationRow> rows, IEnumerable<string> tracks) =>
        tracks.Select(track => Summarize(rows, track)).ToArray();

    private static double At(double[]? values, int index, double fallback) =>
        values != null && index >= 0 && index < values.Length ? values[index] : fallback;

    private sealed record Working(CalibrationRow Row, bool FamilyEligible, bool Applicable, bool NullControlled,
        double Power, double Low, double High);
}
