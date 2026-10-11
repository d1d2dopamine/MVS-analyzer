namespace MvsAnalyzer;

internal sealed record MetricGroupAvailability(string Group, int RetainedEntities, int UsableEntities,
    int ExcludedEntities, Dictionary<string, int> ExclusionReasons);

/// <summary>Observed entity-summary availability, independent of calibration quality or selection.</summary>
internal static class MetricAvailability
{
    internal const int MinimumEntitiesPerGroup = 4;

    internal static MetricGroupAvailability[][] Describe(AnalysisData data)
    {
        var measurements = data.Observations
            .GroupBy(o => AnalysisEngine.Key(o.Group, o.Entity), StringComparer.OrdinalIgnoreCase)
            .ToDictionary(g => g.Key, g => g.Select(o => o.Value).ToArray(), StringComparer.OrdinalIgnoreCase);
        return Enumerable.Range(0, AnalysisEngine.MetricKeys.Length).Select(metric =>
            data.GroupNames.Select(group =>
            {
                EntityResult[] entities = data.Entities.Where(e => e.Group.Equals(group, StringComparison.OrdinalIgnoreCase)).ToArray();
                var reasons = new Dictionary<string, int>(StringComparer.Ordinal);
                int usable = 0;
                foreach (EntityResult entity in entities)
                {
                    if (double.IsFinite(entity.Metrics[metric])) { usable++; continue; }
                    string reason = "nonfinite_metric_value";
                    if (measurements.TryGetValue(AnalysisEngine.Key(group, entity.Entity), out double[]? values))
                    {
                        string requirement = MetricRegistry.UnavailabilityReason(AnalysisEngine.MetricKeys[metric], values);
                        if (requirement.Length > 0) reason = requirement;
                    }
                    reasons[reason] = reasons.GetValueOrDefault(reason) + 1;
                }
                return new MetricGroupAvailability(group, entities.Length, usable, entities.Length - usable, reasons);
            }).ToArray()).ToArray();
    }
}
