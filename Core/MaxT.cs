namespace MvsAnalyzer;

internal record MaxTResult(int FamilySize, int ResampleCount, int[] ExceedanceCounts, double[] AdjustedPValues);

// Unused development arithmetic. No production inference or resampling scheme
// is selected by this helper, and no strong-FWER guarantee is implied.
internal static class MaxT
{
    /// <summary>
    /// Single-step Monte Carlo maxT for a complete, predeclared family of finite,
    /// comparable scores already oriented so that larger means more extreme.
    /// The caller owns the statistic, scientific null and valid joint resampling
    /// scheme, including exchangeability and any partial-null justification.
    /// Rows are the B declared Monte Carlo draws; identity draws may occur.
    /// This is not an exhaustive-orbit formula with identity already included.
    /// Exact ties count as exceedances; p_j = (1 + count(max(row) >= observed_j)) / (B + 1).
    /// No unavailable slot or failed row may be removed or replaced. A nonfinite
    /// score (including NaN) rejects the entire call. Inputs are never modified.
    /// </summary>
    internal static MaxTResult MonteCarloSingleStep(double[] observed, double[][] resamples, int familySize)
    {
        ArgumentNullException.ThrowIfNull(observed);
        ArgumentNullException.ThrowIfNull(resamples);
        if (familySize <= 0 || observed.Length != familySize)
            throw new ArgumentException("familySize must equal the nonempty complete observed score vector length.", nameof(familySize));
        if (resamples.Length == 0)
            throw new ArgumentException("At least one complete Monte Carlo resample is required.", nameof(resamples));
        for (int j = 0; j < familySize; j++)
            if (!double.IsFinite(observed[j]))
                throw new ArgumentOutOfRangeException(nameof(observed), "Every observed score must be finite; unavailable scores are not supported.");

        var counts = new int[familySize];
        foreach (double[] row in resamples)
        {
            if (row is null || row.Length != familySize)
                throw new ArgumentException("Every resample must contain the complete declared family.", nameof(resamples));
            double maximum = double.NegativeInfinity;
            foreach (double score in row)
            {
                if (!double.IsFinite(score))
                    throw new ArgumentOutOfRangeException(nameof(resamples), "Every resampled score must be finite; failed rows or slots cannot be omitted.");
                if (score > maximum) maximum = score;
            }
            for (int j = 0; j < familySize; j++)
                if (maximum >= observed[j]) counts[j]++;
        }

        var adjusted = new double[familySize];
        // Add in floating point so B + 1 cannot overflow an Int32 denominator.
        double denominator = resamples.Length + 1.0;
        for (int j = 0; j < familySize; j++)
            adjusted[j] = (counts[j] + 1.0) / denominator;
        return new MaxTResult(familySize, resamples.Length, counts, adjusted);
    }
}
