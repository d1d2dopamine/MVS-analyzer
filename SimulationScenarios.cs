namespace MvsAnalyzer;

/// <summary>
/// The single place that decides what a simulation scenario name means.
/// Before this existed, ApplyScenario treated every unrecognised name as
/// "raise the level of the last group". A plugin profile asking for scenario=scale
/// therefore did not fail: it silently measured a location shift and reported the
/// answer as if the requested scenario had run. Names are validated once, at the
/// edge, and an unknown name is now an error instead of a wrong answer.
/// </summary>
internal static class SimulationScenarios
{
    public const string Location = "location";
    public const string Decrease = "decrease";
    public const string Variability = "variability";
    public const string Heterogeneity = "heterogeneity";
    public const string Default = Location;

    internal static readonly string[] All = { Location, Decrease, Variability, Heterogeneity };

    // docs/METHODS.md documented these as scale and location_down while the code only
    // answered to variability and decrease. Both spellings are accepted and normalised.
    private static readonly Dictionary<string,string> Aliases = new(StringComparer.OrdinalIgnoreCase)
    {
        ["location"] = Location,
        ["location_up"] = Location,
        ["increase"] = Location,
        ["decrease"] = Decrease,
        ["location_down"] = Decrease,
        ["variability"] = Variability,
        ["scale"] = Variability,
        ["dispersion"] = Variability,
        ["spread"] = Variability,
        ["within"] = Variability,
        ["within_variability"] = Variability,
        ["heterogeneity"] = Heterogeneity,
        ["between"] = Heterogeneity,
        ["between_heterogeneity"] = Heterogeneity
    };

    public static bool TryCanonical(string? value, out string canonical)
    {
        if (!string.IsNullOrWhiteSpace(value) && Aliases.TryGetValue(value.Trim(), out string? found)) { canonical = found; return true; }
        canonical = Default; return false;
    }

    /// <summary>Returns the canonical name, or throws. Never guesses.</summary>
    public static string Canonicalize(string? value)
    {
        if (TryCanonical(value, out string canonical)) return canonical;
        throw new ArgumentException("Unknown simulation scenario " + (value ?? "") + ". Use one of: " + string.Join(", ", All) + ".", nameof(value));
    }

    public static string Describe(string value, bool russian)
    {
        TryCanonical(value, out string canonical);
        if (canonical == Decrease) return russian ? "снижение уровня" : "decrease level";
        if (canonical == Variability) return russian ? "внутрисущностная вариативность" : "within-entity variability";
        if (canonical == Heterogeneity) return russian ? "межсущностная гетерогенность" : "between-entity heterogeneity";
        return russian ? "рост уровня" : "increase level";
    }
}
