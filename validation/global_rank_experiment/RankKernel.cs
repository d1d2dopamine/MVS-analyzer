using System.Buffers.Binary;
using System.Numerics;
using System.Security.Cryptography;
using System.Threading;
using MvsAnalyzer.Benchmarking;

namespace MvsAnalyzer.GlobalRankExperiment;

// Isolated test-only kernel. The global null is equality of the joint entity-vector
// distributions, with exchangeable complete entity labels. No omnibus sensitivity
// or partial-null strong-FWER claim is made. No continuity correction is applied.
internal static class RankKernel
{
    internal const int FamilySize = 12;
    internal const int MonteCarloDraws = 999;
    internal const int MaximumEntities = 128;

    internal readonly record struct ExactScore(long Numerator, long Denominator) : IComparable<ExactScore>
    {
        public int CompareTo(ExactScore other) =>
            ((BigInteger)Numerator * other.Denominator).CompareTo((BigInteger)other.Numerator * Denominator);
        internal double Value => (double)Numerator / Denominator;
    }

    internal sealed record ScoreVector(double[] Values, ExactScore[] Exact, int MaximumIndex)
    {
        internal double Maximum => Values[MaximumIndex];
    }

    internal sealed record Result(
        int DrawCount, ScoreVector Observed, int GlobalExceedanceCount, double GlobalPValue,
        int[] MarginalExceedanceCounts, double[] MarginalPValues,
        int[] MaxTExceedanceCounts, double[] MaxTAdjustedPValues,
        double[] BonferroniAdjustedPValues, bool GlobalReject, bool BonferroniReject,
        bool FixedMedianReject, bool FixedCvReject, string SampledLabelHash);

    internal static Prepared Prepare(double[][] rows, int nCase) => new(rows, nCase);

    internal sealed class Prepared
    {
        private readonly int[][] ranks;
        private readonly long[] q;
        internal int N { get; }
        internal int NCase { get; }
        internal int[][] DoubledCenteredRanks => ranks.Select(r => (int[])r.Clone()).ToArray();
        internal long[] Q => (long[])q.Clone();

        internal Prepared(double[][] rows, int nCase)
        {
            ArgumentNullException.ThrowIfNull(rows);
            if (rows.Length < 2 || rows.Length > MaximumEntities)
                throw new ArgumentOutOfRangeException(nameof(rows), "Complete entity count must be between 2 and 128.");
            if (nCase < 1 || nCase >= rows.Length)
                throw new ArgumentOutOfRangeException(nameof(nCase), "Both groups must be nonempty.");
            foreach (double[] row in rows)
                if (row is null || row.Length != FamilySize || row.Any(x => !double.IsFinite(x)))
                    throw new ArgumentException("Reject entire case: every entity must have exactly 12 finite metric slots; no omission is allowed.", nameof(rows));
            N = rows.Length;
            NCase = nCase;
            ranks = Enumerable.Range(0, N).Select(_ => new int[FamilySize]).ToArray();
            q = new long[FamilySize];
            for (int j = 0; j < FamilySize; j++)
            {
                int column = j;
                int[] order = Enumerable.Range(0, N).OrderBy(i => rows[i][column]).ToArray();
                int start = 0;
                while (start < N)
                {
                    int end = start + 1;
                    while (end < N && rows[order[end]][j] == rows[order[start]][j]) end++;
                    // One-based ranks start+1 through end have doubled midrank start+1+end.
                    int centered = start + end - N;
                    for (int k = start; k < end; k++) ranks[order[k]][j] = centered;
                    q[j] = checked(q[j] + (long)(end - start) * centered * centered);
                    start = end;
                }
            }
        }

        internal ScoreVector Score(int[] caseIndices)
        {
            ValidateSelection(caseIndices);
            var exact = new ExactScore[FamilySize];
            var values = new double[FamilySize];
            for (int j = 0; j < FamilySize; j++)
            {
                long d = 0;
                foreach (int i in caseIndices) d = checked(d + ranks[i][j]);
                exact[j] = q[j] == 0 ? new ExactScore(0, 1) : new ExactScore(
                    checked(d * d * N * (N - 1)), checked((long)NCase * (N - NCase) * q[j]));
                values[j] = exact[j].Value;
                if (!double.IsFinite(values[j])) throw new InvalidOperationException("Nonfinite rank statistic; case rejected.");
            }
            int maximum = 0;
            for (int j = 1; j < FamilySize; j++)
                if (CompareChecked(exact[j], values[j], exact[maximum], values[maximum]) > 0) maximum = j;
            return new ScoreVector(values, exact, maximum);
        }

        // Independent draws with replacement across assignments. Each fresh full
        // Fisher-Yates shuffle uses rejection-unbiased Next(bound); its first
        // NCase positions give one uniform subset shared by all twelve columns.
        // Identity and repeated assignments are neither rejected nor replaced.
        internal Result Run(int[] observedCaseIndices, ulong labelSeed, int draws = MonteCarloDraws, CancellationToken token = default)
        {
            if (draws != MonteCarloDraws)
                throw new ArgumentOutOfRangeException(nameof(draws), "The experiment requires exactly 999 Monte Carlo draws.");
            ValidateSelection(observedCaseIndices);
            var random = new BenchmarkRandom(labelSeed); // Never consumes the data RNG.
            var assignments = new int[draws][];
            for (int b = 0; b < draws; b++)
            {
                token.ThrowIfCancellationRequested();
                int[] permutation = Enumerable.Range(0, N).ToArray();
                for (int i = N - 1; i > 0; i--)
                {
                    int k = random.Next(i + 1);
                    (permutation[i], permutation[k]) = (permutation[k], permutation[i]);
                }
                assignments[b] = permutation.Take(NCase).ToArray();
            }
            return EvaluateAssignments(observedCaseIndices, assignments, token);
        }

        // For literal fixtures/oracle export only. This is the add-one Monte Carlo
        // calculation even if supplied assignments happen to enumerate an orbit;
        // it must not be described as an exhaustive-orbit p-value.
        internal Result EvaluateAssignments(int[] observedCaseIndices, int[][] assignments, CancellationToken token = default)
        {
            ArgumentNullException.ThrowIfNull(assignments);
            if (assignments.Length == 0) throw new ArgumentException("At least one complete draw is required.", nameof(assignments));
            ScoreVector observed = Score(observedCaseIndices);
            var marginalCounts = new int[FamilySize];
            var maxCounts = new int[FamilySize];
            var resamples = new double[assignments.Length][];
            int globalCount = 0;
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            // SHA256 of little-endian Int32 N, NCase, B, followed by B canonical
            // length-N label vectors (one byte/entity: case=1, control=0).
            Span<byte> header = stackalloc byte[12];
            BinaryPrimitives.WriteInt32LittleEndian(header, N);
            BinaryPrimitives.WriteInt32LittleEndian(header[4..], NCase);
            BinaryPrimitives.WriteInt32LittleEndian(header[8..], assignments.Length);
            hash.AppendData(header);
            var labels = new byte[N];
            for (int b = 0; b < assignments.Length; b++)
            {
                token.ThrowIfCancellationRequested();
                ScoreVector draw = Score(assignments[b]);
                resamples[b] = draw.Values;
                Array.Clear(labels, 0, labels.Length);
                foreach (int i in assignments[b]) labels[i] = 1;
                hash.AppendData(labels);
                int max = draw.MaximumIndex;
                for (int j = 0; j < FamilySize; j++)
                {
                    if (CompareChecked(draw.Exact[j], draw.Values[j], observed.Exact[j], observed.Values[j]) >= 0) marginalCounts[j]++;
                    if (CompareChecked(draw.Exact[max], draw.Values[max], observed.Exact[j], observed.Values[j]) >= 0) maxCounts[j]++;
                }
                if (CompareChecked(draw.Exact[max], draw.Values[max], observed.Exact[observed.MaximumIndex], observed.Maximum) >= 0) globalCount++;
            }
            MaxTResult helper = MaxT.MonteCarloSingleStep(observed.Values, resamples, FamilySize);
            double denominator = assignments.Length + 1.0;
            double[] marginal = marginalCounts.Select(c => (c + 1.0) / denominator).ToArray();
            double[] maxP = maxCounts.Select(c => (c + 1.0) / denominator).ToArray();
            for (int j = 0; j < FamilySize; j++)
                if (helper.ExceedanceCounts[j] != maxCounts[j] || helper.AdjustedPValues[j] != maxP[j])
                    throw new InvalidOperationException("Double MaxT and exact rational tails disagree; entire case rejected.");
            if (globalCount != maxCounts[observed.MaximumIndex])
                throw new InvalidOperationException("Global maximum and maxT count mismatch; entire case rejected.");
            double globalP = (globalCount + 1.0) / denominator;
            double[] bonferroni = marginal.Select(p => Math.Min(1.0, FamilySize * p)).ToArray();
            return new Result(assignments.Length, observed, globalCount, globalP, marginalCounts, marginal,
                maxCounts, maxP, bonferroni, globalP < .05, bonferroni.Any(p => p < .05),
                marginal[0] < .05, marginal[2] < .05, Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant());
        }

        private void ValidateSelection(int[] caseIndices)
        {
            ArgumentNullException.ThrowIfNull(caseIndices);
            if (caseIndices.Length != NCase) throw new ArgumentException("Assignment must preserve the fixed case count.", nameof(caseIndices));
            var seen = new bool[N];
            foreach (int index in caseIndices)
            {
                if (index < 0 || index >= N || seen[index])
                    throw new ArgumentException("Assignment requires distinct valid entity indices.", nameof(caseIndices));
                seen[index] = true;
            }
        }
    }

    private static int CompareChecked(ExactScore left, double leftDouble, ExactScore right, double rightDouble)
    {
        int exact = left.CompareTo(right);
        if (Math.Sign(leftDouble.CompareTo(rightDouble)) != Math.Sign(exact))
            throw new InvalidOperationException("Double and exact rational ordering (including equality) disagree; entire case rejected.");
        return exact;
    }
}
