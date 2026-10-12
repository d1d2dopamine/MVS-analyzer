namespace MvsAnalyzer;

// Development comparator only. Shipped Results/calibration/benchmark decisions
// continue to use DecisionPolicy; this is not an activated inference method.
internal enum MultiplicityMethod { Bonferroni, Holm }

internal static class Multiplicity
{
    /// <summary>
    /// Adjust a complete, predeclared hypothesis family without modifying its input.
    /// NaN denotes an unavailable test, remains NaN, and still counts in familySize.
    /// Dropping unavailable entries before calling this method is not permitted.
    /// Holm uses the full family denominator, treating unavailable tests as last.
    /// Both methods have the same any-rejection event; Holm can reject more members.
    /// </summary>
    internal static double[] Adjust(double[] pValues, int familySize, MultiplicityMethod method)
    {
        ArgumentNullException.ThrowIfNull(pValues);
        if (familySize <= 0 || familySize != pValues.Length)
            throw new ArgumentException("familySize must equal the nonempty complete p-value vector length.", nameof(familySize));
        if (method != MultiplicityMethod.Bonferroni && method != MultiplicityMethod.Holm)
            throw new ArgumentOutOfRangeException(nameof(method));
        var adjusted = (double[])pValues.Clone();
        for (int i = 0; i < adjusted.Length; i++)
            ValidateP(adjusted[i], nameof(pValues));
        if (method == MultiplicityMethod.Bonferroni)
        {
            for (int i = 0; i < adjusted.Length; i++)
                if (!double.IsNaN(adjusted[i])) adjusted[i] = Math.Min(1, familySize * adjusted[i]);
            return adjusted;
        }

        int[] order = Enumerable.Range(0, adjusted.Length)
            .Where(i => !double.IsNaN(adjusted[i])).OrderBy(i => adjusted[i]).ToArray();
        double running = 0;
        for (int rank = 0; rank < order.Length; rank++)
        {
            int index = order[rank];
            running = Math.Max(running, Math.Min(1, (familySize - rank) * adjusted[index]));
            adjusted[index] = running;
        }
        return adjusted;
    }

    // Strict inequality matches the shipped decision convention. Unavailable is
    // never rejected. This helper does not decide equivalence or applicability.
    internal static bool IsRejected(double adjustedP, double alpha)
    {
        if (!double.IsFinite(alpha) || alpha <= 0 || alpha >= 1)
            throw new ArgumentOutOfRangeException(nameof(alpha));
        ValidateP(adjustedP, nameof(adjustedP));
        return !double.IsNaN(adjustedP) && adjustedP < alpha;
    }

    private static void ValidateP(double p, string parameter)
    {
        if (!double.IsNaN(p) && (!double.IsFinite(p) || p < 0 || p > 1))
            throw new ArgumentOutOfRangeException(parameter, "P-values must be in [0,1], or NaN for unavailable.");
    }
}
