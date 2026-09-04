namespace MvsAnalyzer.Benchmarking;

/// <summary>
/// The benchmark cannot use System.Random. Its algorithm is explicitly documented as an
/// implementation detail and it already changed once between .NET Framework and .NET Core,
/// so a number published today could not be reproduced by a future build of this program.
/// This is xoshiro256** seeded through splitmix64: a fixed, published algorithm whose stream
/// is pinned by a golden test, so the same seed gives the same benchmark on any machine,
/// any operating system and any future runtime.
/// </summary>
internal sealed class BenchmarkRandom
{
    private const ulong Golden = 0x9E3779B97F4A7C15UL;

    private ulong s0;
    private ulong s1;
    private ulong s2;
    private ulong s3;
    private double spare;
    private bool hasSpare;

    public BenchmarkRandom(ulong seed)
    {
        ulong x = seed;
        s0 = SplitMix(ref x);
        s1 = SplitMix(ref x);
        s2 = SplitMix(ref x);
        s3 = SplitMix(ref x);
        if ((s0 | s1 | s2 | s3) == 0UL) s0 = Golden;
    }

    /// <summary>
    /// Turns a run seed plus the coordinates of one unit of work into that unit's own seed.
    /// Every replication therefore owns an independent stream, which is what makes the
    /// parallel loops give bit-identical results no matter how the threads are scheduled.
    /// </summary>
    public static ulong Derive(ulong seed, ulong stage, ulong condition, ulong replication)
    {
        unchecked
        {
            ulong x = seed;
            x = Scramble(x + stage * 0x9E3779B97F4A7C15UL);
            x = Scramble(x + condition * 0xC2B2AE3D27D4EB4FUL);
            x = Scramble(x + replication * 0x165667B19E3779F9UL);
            return x;
        }
    }

    public ulong NextUInt64()
    {
        unchecked
        {
            ulong result = Rotl(s1 * 5UL, 7) * 9UL;
            ulong t = s1 << 17;
            s2 ^= s0;
            s3 ^= s1;
            s1 ^= s2;
            s0 ^= s3;
            s2 ^= t;
            s3 = Rotl(s3, 45);
            return result;
        }
    }

    /// <summary>Uniform in [0, 1) using the top 53 bits, exactly as the reference implementation.</summary>
    public double NextDouble() => (NextUInt64() >> 11) * (1.0 / 9007199254740992.0);

    /// <summary>
    /// Uniform integer in [0, bound). Rejection sampling instead of a plain modulo, so the
    /// low indices are not silently favoured.
    /// </summary>
    public int Next(int bound)
    {
        if (bound <= 0) throw new ArgumentOutOfRangeException(nameof(bound), "The bound must be positive.");
        ulong limit = (ulong)bound;
        ulong threshold = (ulong.MaxValue - limit + 1UL) % limit;
        while (true)
        {
            ulong draw = NextUInt64();
            if (draw >= threshold) return (int)(draw % limit);
        }
    }

    /// <summary>Standard normal, polar Box-Muller. The second value of each pair is kept, not discarded.</summary>
    public double NextGaussian()
    {
        if (hasSpare)
        {
            hasSpare = false;
            return spare;
        }
        double u;
        double v;
        double radius;
        do
        {
            u = NextDouble() * 2 - 1;
            v = NextDouble() * 2 - 1;
            radius = u * u + v * v;
        }
        while (radius <= 1e-300 || radius >= 1);
        double factor = Math.Sqrt(-2 * Math.Log(radius) / radius);
        spare = v * factor;
        hasSpare = true;
        return u * factor;
    }

    /// <summary>
    /// Student t rescaled to unit variance. Biological signals have heavier tails than a normal
    /// distribution, and a benchmark that only ever tests normal data would flatter every metric
    /// that assumes normality.
    /// </summary>
    public double NextStandardizedT(int degrees)
    {
        if (degrees < 3) throw new ArgumentOutOfRangeException(nameof(degrees), "At least three degrees of freedom are required for unit variance.");
        double z = NextGaussian();
        double chiSquare = 0;
        for (int i = 0; i < degrees; i++)
        {
            double g = NextGaussian();
            chiSquare += g * g;
        }
        if (chiSquare <= 1e-300) return 0;
        double t = z / Math.Sqrt(chiSquare / degrees);
        return t / Math.Sqrt(degrees / (double)(degrees - 2));
    }

    /// <summary>Right-skewed noise with mean 0 and unit variance, built from a lognormal.</summary>
    public double NextStandardizedLognormal(double sigma)
    {
        double raw = Math.Exp(sigma * NextGaussian());
        double mean = Math.Exp(sigma * sigma / 2);
        double variance = (Math.Exp(sigma * sigma) - 1) * Math.Exp(sigma * sigma);
        double deviation = Math.Sqrt(Math.Max(variance, 1e-300));
        return (raw - mean) / deviation;
    }

    private static ulong Rotl(ulong value, int count) => (value << count) | (value >> (64 - count));

    private static ulong Scramble(ulong value)
    {
        ulong x = value;
        return SplitMix(ref x);
    }

    private static ulong SplitMix(ref ulong x)
    {
        unchecked
        {
            x += Golden;
            ulong z = x;
            z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
            z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
            return z ^ (z >> 31);
        }
    }
}
